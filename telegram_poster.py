import requests
import config
import telebot

bot = telebot.TeleBot(config.TELEGRAM_TOKEN, parse_mode=None)

def pick_best_media(media_list):
    headers = {"User-Agent": "Mozilla/5.0"}
    best_url = None
    best_size = 0

    for url in media_list:
        try:
            # HEAD быстрее и не качает файл
            r = requests.head(url, headers=headers, timeout=5, allow_redirects=True)

            # Иногда HEAD не возвращает тип — fallback на GET (stream)
            if "content-type" not in r.headers:
                r = requests.get(url, headers=headers, timeout=5, stream=True)

            ctype = r.headers.get("content-type", "").lower()

            # Только реальные изображения
            if not ctype.startswith("image/"):
                continue
            if "svg" in ctype or "gif" in ctype:
                continue

            # Фильтр пикселей
            if "1x1" in url or "pixel" in url:
                continue

            # Размер (качество)
            size = int(r.headers.get("content-length", 0))

            # Если размер неизвестен — пробуем получить первые 64 KB
            if size == 0:
                try:
                    test = requests.get(url, headers=headers, timeout=5, stream=True)
                    chunk = next(test.iter_content(65536))
                    size = len(chunk)
                except Exception:
                    continue

            # Выбираем самое большое изображение
            if size > best_size:
                best_size = size
                best_url = url

        except Exception:
            continue

    return best_url


def build_telegram_post(result, lang):
    if result["status"] == "OK":
        source = 'source' if lang == 'en' else 'Источник'
        text = result[lang] + f'\n\n{source}: ' + result["url"]
        media_url = pick_best_media(result.get("media", []))

        if media_url and len(text) < 1024:
            return {
                "type": "photo",
                "photo": media_url,
                "caption": text
            }
        else:
            return {
                "type": 'text',
                "text": text
            }
    # else:
    #     return {
    #             "type": 'text',
    #             "text": result["url"]
    #         }
        
        

def send_media_post_tg(result, channel, lang):
    tg_post = build_telegram_post(result, lang)
    if tg_post:
        if tg_post["type"] == "photo":
            bot.send_photo(
                chat_id=channel,
                photo=tg_post["photo"],
                caption=tg_post["caption"]
            )
        else:
            bot.send_message(
                chat_id=channel,
                text=tg_post["text"]
            )

if __name__=='__main__':

    result = {
        "status": "OK",
        "ru": "Высококлассный менеджер по управлению капиталом Jeffrey Fratarcangeli использует двухэтапную стратегию для клиентов с капиталом ~$10 млн.",
        "en": "High-net-worth money manager Jeffrey Fratarcangeli employs a two-part strategy for clients with ~$10 million net worth. ",
        "media": [
            "https://sb.scorecardresearch.com/p?c1=2&c2=9900186&cv=3.6.0&;cj=1&comscorekw=",
            "https://i.insider.com/65558c304ca513d8242a59ff?width=168&format=jpeg&auto=webp&crop=1:1,smart",
            "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1 1'%3E%3C/svg%3E",
            "https://i.insider.com/6983ba46d3c7faef0ecda2c3?width=700",
            "https://www.businessinsider.com/public/assets/badges/google-play-badge.svg"
        ]
        }
    tg_post = build_telegram_post(result, 'en')

    if tg_post["type"] == "photo":
        bot.send_photo(
            chat_id=config.TELEGRAM_CHANNELS[0],
            photo=tg_post["photo"],
            caption=tg_post["caption"]
        )
    else:
        bot.send_message(
            chat_id=config.TELEGRAM_CHANNELS[0],
            text=tg_post["text"]
        )
