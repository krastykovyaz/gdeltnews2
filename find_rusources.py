"""
GDELT Russian News Scraper
==========================
Скачивает данные из GDELT за заданный период (месяц/год).
Проверяет язык каждой статьи и сохраняет ТОЛЬКО русскоязычные материалы.
Без предварительной фильтрации по источникам.

Использование:
    python gdelt_scraper_ru.py --month 1 --year 2024
    python gdelt_scraper_ru.py --month 3 --year 2023 --output ./data --workers 8 --limit 500
    python gdelt_scraper_ru.py --debug

Зависимости:
    pip install requests beautifulsoup4 lxml tqdm langdetect pandas
"""

import argparse
import csv
import io
import logging
import os
import re
import time
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

# ─── Настройки ────────────────────────────────────────────────────────────────

GDELT_MASTERLIST_URL = "http://data.gdeltproject.org/gdeltv2/masterfilelist.txt"

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:97.0) "
        "Gecko/20100101 Firefox/97.0"
    )
}
REQUEST_TIMEOUT  = 10   # секунд
SLEEP_BETWEEN    = 0    # задержка между запросами внутри одного воркера (сек)
MAX_ARTICLE_LEN  = 50_000

# Колонки GDELT v2 export (tab-separated)
GDELT_COL_DATE   = 1   # SQLDATE  (YYYYMMDD)
GDELT_COL_SOURCE = 4   # SourceCommonName
GDELT_COL_URL    = 60  # SOURCEURL

# ─── Настройки логирования ────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── langdetect ───────────────────────────────────────────────────────────────

try:
    from langdetect import DetectorFactory
    from langdetect import detect as _langdetect
    DetectorFactory.seed = 42
    _HAS_LANGDETECT = True
except ImportError:
    _HAS_LANGDETECT = False
    log.warning("langdetect не установлен. Проверка языка будет упрощённой (по URL и HTML-тегам).")

# ─── Упрощённая проверка языка по URL и HTML (без langdetect) ────────────────

def is_russian_url(url: str) -> bool:
    """Проверяет URL на наличие признаков русского языка."""
    url_lower = url.lower()
    ru_indicators = [
        '.ru/', '.ru?', '.ru#',           # домены .ru
        'russian.', 'russia.',             # английские слова
        '/ru/', '/ru?', '/ru#',            # /ru/ в пути
        '?lang=ru', '&lang=ru',            # параметры языка
        'ria.ru', 'tass.ru', 'interfax.ru', 'kommersant.ru',  # российские СМИ
        'rbc.ru', 'iz.ru', 'kp.ru', 'mk.ru', 'gazeta.ru',
        'lenta.ru', 'meduza.io', 'novayagazeta.ru',
    ]
    return any(indicator in url_lower for indicator in ru_indicators)


def _check_html_lang(soup: BeautifulSoup) -> str | None:
    """Проверяет HTML-теги на указание языка. Возвращает код языка или None."""
    html_tag = soup.find("html")
    if html_tag:
        lang = (html_tag.get("lang") or html_tag.get("xml:lang") or "").lower()
        if lang:
            return lang[:2]  # берём первые два символа (ru, en, de...)
    
    og = soup.find("meta", property="og:locale")
    if og:
        locale = (og.get("content") or "").lower()
        if locale:
            return locale[:2]
    
    return None


def detect_language_simple(text: str, url: str = "", soup: BeautifulSoup = None) -> str:
    """
    Определяет язык текста упрощённым методом:
    1. По HTML-тегам (если есть soup)
    2. По процентному соотношению кириллических символов
    3. По URL (как запасной вариант)
    Возвращает 'ru' или 'unknown'.
    """
    # Сначала проверяем HTML-теги, если есть soup
    if soup:
        html_lang = _check_html_lang(soup)
        if html_lang == 'ru':
            return 'ru'
        elif html_lang and html_lang != 'ru':
            return html_lang
    
    # Проверяем текст на наличие кириллицы
    if text and len(text) > 100:
        # Удаляем пробелы и знаки препинания для подсчёта
        text_clean = re.sub(r'[^\w\s]', '', text[:5000])
        text_clean = re.sub(r'\s+', '', text_clean)
        
        if text_clean:
            # Считаем кириллические символы (диапазон Unicode для русских букв)
            cyrillic_chars = sum(1 for c in text_clean if '\u0400' <= c <= '\u04FF' or '\u0500' <= c <= '\u052F')
            total_chars = len(text_clean)
            
            if total_chars > 0:
                cyrillic_percent = cyrillic_chars / total_chars
                if cyrillic_percent > 0.3:  # более 30% кириллицы - вероятно русский
                    return 'ru'
                elif cyrillic_percent < 0.01 and total_chars > 200:
                    return 'en'  # почти нет кириллицы - вероятно английский
    
    # Если текст слишком короткий, пробуем URL
    if url and is_russian_url(url):
        return 'ru'
    
    return 'unknown'


def is_russian_text(text: str, url: str = "", soup: BeautifulSoup = None) -> bool:
    """
    Основная функция проверки языка.
    Использует langdetect если доступен, иначе упрощённую проверку.
    """
    if not text and not url:
        return False
    
    # Если текст слишком короткий, полагаемся на URL
    if len(text) < 60 and url:
        return is_russian_url(url)
    
    # Используем langdetect если доступен
    if _HAS_LANGDETECT:
        try:
            # Берём до 3000 символов для определения языка
            text_for_detect = text[:3000]
            detected = _langdetect(text_for_detect)
            return detected == 'ru'
        except Exception as e:
            log.debug("langdetect error: %s", e)
            # При ошибке переходим к упрощённому методу
            return detect_language_simple(text, url, soup) == 'ru'
    else:
        # Упрощённый метод
        return detect_language_simple(text, url, soup) == 'ru'


# ─── GDELT helpers ────────────────────────────────────────────────────────────

def get_gdelt_file_list(month: int, year: int) -> list[str]:
    """Получает список GDELT-файлов за указанный месяц."""
    log.info("Загружаем список файлов GDELT (может занять 10-20 сек)…")
    resp = requests.get(GDELT_MASTERLIST_URL, timeout=60, stream=True)
    resp.raise_for_status()
    prefix = f"{year}{month:02d}"
    urls: list[str] = []
    for line in resp.iter_lines(decode_unicode=True):
        parts = line.strip().split()
        if len(parts) >= 3 and ".export.CSV.zip" in parts[2] and f"/{prefix}" in parts[2]:
            urls.append(parts[2])
    log.info("Найдено файлов за %04d-%02d: %d", year, month, len(urls))
    return urls


def download_gdelt_zip(zip_url: str) -> list[list[str]]:
    """Скачивает и распаковывает GDELT-файл."""
    try:
        resp = requests.get(zip_url, timeout=60)
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            with zf.open(zf.namelist()[0]) as f:
                content = f.read().decode("utf-8", errors="replace")
        return [line.split("\t") for line in content.splitlines() if line]
    except Exception as e:
        log.debug("Ошибка загрузки %s: %s", zip_url, e)
        return []


def extract_records(rows: list[list[str]]) -> list[dict]:
    """
    Извлекает записи из GDELT.
    БЕЗ фильтрации по источникам - сохраняем ВСЁ для последующей проверки языка.
    """
    records: list[dict] = []
    for cols in rows:
        try:
            if len(cols) <= GDELT_COL_URL:
                continue
            url = cols[GDELT_COL_URL].strip()
            if not url or not url.startswith("http"):
                continue
            
            date = datetime.strptime(cols[GDELT_COL_DATE], "%Y%m%d").date()
            source = cols[GDELT_COL_SOURCE] if len(cols) > GDELT_COL_SOURCE else ""
            
            records.append({
                "date": date,
                "source": source,
                "link": url,
            })
        except Exception as e:
            log.debug("Ошибка парсинга строки GDELT: %s", e)
            continue
    
    return records


# ─── Парсинг статьи (requests + BeautifulSoup) ────────────────────────────────

def url_to_title_fallback(url: str) -> str:
    """Генерирует заголовок из URL если не удалось извлечь."""
    try:
        slug = urlparse(url).path.rstrip("/").split("/")[-1]
        slug = re.sub(r"\.\w{2,5}$", "", slug)
        slug = re.sub(r"[-_]+", " ", slug).strip()
        return slug.title() if slug else url
    except Exception:
        return url


_BODY_SELECTORS = [
    {"name": "article"},
    {"name": "main"},
    {"attrs": {"itemprop": "articleBody"}},
    {"attrs": {"class": re.compile(
        r"article[_-]?(?:body|text|content)|post[_-]?(?:body|content)|"
        r"entry[_-]?content|story[_-]?(?:body|content)|"
        r"news[_-]?(?:body|content)|content[_-]?body",
        re.I,
    )}},
]


def fetch_article(record: dict) -> dict | None:
    """
    Открывает ссылку, парсит статью и проверяет язык.
    Возвращает запись только если статья на русском языке.
    """
    url = record["link"]
    
    try:
        # HTTP-запрос
        response = requests.get(
            url,
            headers=REQUEST_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        page_source = response.text

        soup = BeautifulSoup(page_source, "lxml")

        # ── Заголовок ─────────────────────────────────────────────────────────
        title = ""
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"].strip()
        if not title and soup.title:
            title = soup.title.get_text(strip=True)
        if not title:
            h1 = soup.find("h1")
            title = h1.get_text(strip=True) if h1 else ""

        # ── Тело статьи ─────────────────────────────────────────────────────
        body = ""
        
        # Пытаемся найти основной контент по селекторам
        for sel in _BODY_SELECTORS:
            tag = soup.find(**sel)
            if tag:
                paras = [p.get_text(strip=True) for p in tag.find_all("p")]
                body = " ".join(p for p in paras if len(p) > 40)
                if body:
                    break

        # Фоллбек: все <p> на странице
        if not body:
            paras = [p.get_text(strip=True) for p in soup.find_all("p")]
            body = " ".join(p for p in paras if len(p) > 40)

        # Очистка текста
        body = re.sub(r"\s+", " ", body).strip()[:MAX_ARTICLE_LEN]
        title = re.sub(r"\s+", " ", title).strip()

        # КЛЮЧЕВОЙ МОМЕНТ: проверяем язык статьи
        # Берём заголовок + начало текста для определения языка
        text_for_lang = f"{title} {body[:2000]}"
        
        if not is_russian_text(text_for_lang, url, soup):
            log.debug("Пропуск (не русский язык): %s", url)
            return None

        # Сохраняем только русскоязычные статьи
        record["title"] = title or url_to_title_fallback(url)
        record["news_body"] = body

        if SLEEP_BETWEEN > 0:
            time.sleep(SLEEP_BETWEEN)
        
        log.debug("✅ Русская статья: %s", title[:100] if title else url[:100])
        return record

    except requests.exceptions.RequestException as e:
        log.debug("Ошибка HTTP [%s]: %s", url, e)
    except Exception as e:
        log.debug("Ошибка парсинга [%s]: %s", url, e)
    
    return None


# ─── Основная логика ──────────────────────────────────────────────────────────

def scrape(
    month: int,
    year: int,
    output_dir: str,
    workers: int,
    limit: int | None,
    debug: bool = False,
) -> None:
    """Основная функция сбора данных."""
    
    if debug:
        log.setLevel(logging.DEBUG)
    
    os.makedirs(output_dir, exist_ok=True)

    # 1. Список файлов GDELT за нужный месяц
    file_urls = get_gdelt_file_list(month, year)
    if not file_urls:
        log.error("Файлы GDELT для %04d-%02d не найдены.", year, month)
        return

    # 2. Скачиваем ВСЕ записи БЕЗ фильтрации по источникам
    log.info("Скачиваем GDELT-файлы и собираем ВСЕ ссылки (без фильтрации по источникам)…")
    all_records: list[dict] = []
    seen_urls: set[str] = set()
    total_raw = 0

    for furl in tqdm(file_urls, desc="GDELT files", unit="file"):
        rows = download_gdelt_zip(furl)
        total_raw += len(rows)
        for rec in extract_records(rows):
            if rec["link"] not in seen_urls:
                seen_urls.add(rec["link"])
                all_records.append(rec)

    log.info(
        "Всего строк в GDELT: %d  |  Уникальных ссылок: %d",
        total_raw, len(all_records),
    )
    
    # Статистика по источникам (топ-20)
    src_counts = Counter(r["source"] for r in all_records if r["source"])
    log.info("Топ-20 источников (до фильтрации по языку):")
    for src, cnt in src_counts.most_common(20):
        log.info("  %-45s %d", src, cnt)

    if limit:
        all_records = all_records[:limit]
        log.info("Лимит записей: %d", len(all_records))

    # 3. Параллельный обход ссылок и проверка языка
    log.info("Скачиваем статьи и проверяем язык (%d потоков)…", workers)
    
    russian_articles: list[dict] = []
    processed = 0
    language_stats = {
        'russian': 0,
        'other': 0,
        'error': 0,
    }

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_article, rec): rec for rec in all_records}
        pbar = tqdm(total=len(all_records), desc="Articles", unit="art")
        
        for future in as_completed(futures):
            try:
                result = future.result()
                processed += 1
                
                if result is None:
                    language_stats['other'] += 1
                else:
                    russian_articles.append(result)
                    language_stats['russian'] += 1
                    
            except Exception as e:
                language_stats['error'] += 1
                log.debug("Future error: %s", e)
            
            pbar.update(1)
            
            # Периодическая статистика
            if processed % 100 == 0:
                log.debug(
                    "Прогресс: %d/%d | Русских: %d | Другие: %d | Ошибок: %d",
                    processed, len(all_records),
                    language_stats['russian'],
                    language_stats['other'],
                    language_stats['error'],
                )
        
        pbar.close()

    # 4. Итоговая статистика
    log.info("=" * 60)
    log.info("ИТОГОВАЯ СТАТИСТИКА:")
    log.info("  Всего обработано ссылок: %d", len(all_records))
    log.info("  Найдено русскоязычных статей: %d (%.1f%%)", 
             language_stats['russian'],
             100 * language_stats['russian'] / len(all_records) if len(all_records) > 0 else 0)
    log.info("  Другие языки: %d", language_stats['other'])
    log.info("  Ошибок загрузки/парсинга: %d", language_stats['error'])
    
    # Топ-источники русскоязычных статей
    if russian_articles:
        ru_sources = Counter(r["source"] for r in russian_articles if r.get("source"))
        log.info("\nТоп-15 источников русскоязычных статей:")
        for src, cnt in ru_sources.most_common(15):
            log.info("  %-45s %d", src, cnt)
    log.info("=" * 60)

    # 5. Сортировка и запись CSV
    if russian_articles:
        russian_articles.sort(key=lambda r: r.get("date", ""))
        out_file = os.path.join(output_dir, f"gdelt_ru_{year}_{month:02d}.csv")

        with open(out_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["date", "title", "news_body", "link", "source"],
                extrasaction="ignore",
                quoting=csv.QUOTE_ALL,
            )
            writer.writeheader()
            writer.writerows(russian_articles)

        log.info("✅ Готово! %d русскоязычных статей → %s", 
                 len(russian_articles), os.path.abspath(out_file))
        
        # Сохраняем также статистику
        stats_file = os.path.join(output_dir, f"stats_{year}_{month:02d}.txt")
        with open(stats_file, "w", encoding="utf-8") as f:
            f.write(f"GDELT Russian News Statistics\n")
            f.write(f"Period: {year}-{month:02d}\n")
            f.write(f"Total URLs processed: {len(all_records)}\n")
            f.write(f"Russian articles found: {language_stats['russian']}\n")
            f.write(f"Other languages: {language_stats['other']}\n")
            f.write(f"Errors: {language_stats['error']}\n\n")
            f.write("Top Russian sources:\n")
            for src, cnt in ru_sources.most_common(30):
                f.write(f"  {src}: {cnt}\n")
        
        log.info("📊 Статистика сохранена в %s", os.path.abspath(stats_file))
    else:
        log.warning("⚠️ Русскоязычных статей не найдено!")


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "GDELT Russian News Scraper\n"
            "Скачивает новости из GDELT и сохраняет ТОЛЬКО русскоязычные материалы.\n"
            "Без предварительной фильтрации по источникам.\n"
            "CSV: date, title, news_body, link, source"
        ),
    )
    parser.add_argument("--month", type=int, help="Месяц (1-12)")
    parser.add_argument("--year", type=int, help="Год (от 2015)")
    parser.add_argument("--output", default="./gdelt_ru_data", help="Папка для CSV")
    parser.add_argument(
        "--workers", type=int, default=8,
        help="Параллельных потоков (по умолчанию: 8)",
    )
    parser.add_argument("--limit", type=int, default=None, help="Макс. ссылок для обработки")
    parser.add_argument(
        "--sleep", type=float, default=0.0,
        help="Задержка между запросами внутри воркера, сек (по умолчанию: 0)",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Режим отладки (подробное логирование)",
    )
    args = parser.parse_args()

    if not args.month or not args.year:
        parser.error("Укажите --month и --year")
    if not (1 <= args.month <= 12):
        parser.error("--month: от 1 до 12")
    if args.year < 2015:
        parser.error("GDELT v2 доступен с 2015 года")

    global SLEEP_BETWEEN
    SLEEP_BETWEEN = args.sleep

    scrape(
        month=args.month,
        year=args.year,
        output_dir=args.output,
        workers=args.workers,
        limit=args.limit,
        debug=args.debug,
    )


if __name__ == "__main__":
    main()