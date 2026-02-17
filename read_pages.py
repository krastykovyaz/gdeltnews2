import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json
from check_ollama import is_ollama_alive
import os
from dotenv import load_dotenv
import config
from telegram_poster import send_media_post_tg


def extract_media(url: str) -> list:
    headers = {"User-Agent": "Mozilla/5.0"}
    html = requests.get(url, headers=headers, timeout=10).text
    soup = BeautifulSoup(html, "html.parser")

    media_urls = set()

    # 1) обычные <img>
    for img in soup.find_all("img"):
        src = img.get("src")
        if src and src.startswith("http"):
            media_urls.add(src)
        elif src:
            media_urls.add(urljoin(url, src))

    # 2) OpenGraph
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        media_urls.add(og["content"])

    # 3) Twitter card
    tw = soup.find("meta", attrs={"name": "twitter:image"})
    if tw and tw.get("content"):
        media_urls.add(tw["content"])

    # 4) фильтрация мусора
    cleaned = []
    for m in media_urls:
        if any(x in m.lower() for x in ["logo", "icon", "sprite", "avatar", "pixel"]):
            continue
        cleaned.append(m)

    return cleaned[:5]  # ограничение, чтобы не тащить мусор


def normalize_spaces_inplace(s: str) -> str:
    n = len(s)
    if n == 0:
        return s

    result = []
    prev_space = False

    for i in range(n):
        ch = s[i]

        if ch == ' ' or ch == '\n':
            if prev_space:
                continue
            result.append(' ')
            prev_space = True
        else:
            result.append(ch)
            prev_space = False

    if result and result[0] == ' ':
        result = result[1:]
    if result and result[-1] == ' ':
        result = result[:-1]

    return "".join(result)


def fetch_page(url):
    
    headers = {"User-Agent": "Mozilla/5.0"}
    for _ in range(3):
        try:
            html = requests.get(url, headers=headers, timeout=10).text
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(separator="\n")
            return normalize_spaces_inplace(text)
        except:
            pass
    return None


def build_prompt(raw_text: str) -> str:
    return f"""
You are an AI news‑editor. You receive raw extracted text from a webpage. 
The text may contain:
– navigation menus
– subscription walls
– paywall messages
– “enable JavaScript” messages
– CAPTCHA / robot checks
– cookie banners
– duplicated blocks
– timestamps
– author bios
– newsletter forms
– empty or meaningless content

Your task:

1) CLEANING
Remove everything that is not the actual article:
– menus, categories, navigation
– subscription prompts
– paywall text
– login/signup text
– cookie notices
– “enable JS”, “are you a robot?”, “please subscribe”
– repeated blocks
– author follow/unfollow UI
– timestamps not part of the article
– social media buttons
– footer text
– legal text

2) CONTENT CHECK
If after cleaning there is no meaningful article content (less than 300 characters of real text) OR if the article is not related to AI, artificial intelligence, machine learning, robotics, chips, semiconductors, big tech, or modern technologies, respond EXACTLY with:
NO_CONTENT

3) IF CONTENT EXISTS — PRODUCE TWO POSTS:
A) Russian post for Telegram:
– 3–5 коротких абзацев
– без воды
– только факты и смысл
– без клише
– без рекламы
– без упоминания источника
– стиль: нейтральный, информативный, технологический
– лимит: 500 символов

B) English post:
– concise
– 3–5 short paragraphs
– same meaning as Russian version
– limit 500 symbols

4) OUTPUT FORMAT (strict):
RUSSIAN:
<русский текст>

ENGLISH:
<english text>

If no content → output only:
NO_CONTENT

Now process the following raw text:
{raw_text}
""".strip()


def call_ollama(prompt: str) -> str:
    payload = {
        "model": config.MODEL_NAME,
        "prompt": prompt,
        "stream": False
    }
    r = requests.post(
        f"{config.OLLAMA_URL}/api/generate",
        json=payload,
        timeout=300
    )
    r.raise_for_status()
    return r.json()["response"]



def parse_model_response(response_text: str) -> dict:
    cleaned = response_text.strip()

    if cleaned == "NO_CONTENT":
        return {"status": "NO_CONTENT"}

    default = {
            "status": "ERROR",
            "raw": cleaned
        }
    try:
        
        ru_start = cleaned.index("RUSSIAN:") + len("RUSSIAN:")
        en_start = cleaned.index("ENGLISH:")

        ru_text = cleaned[ru_start:en_start].strip()
        en_text = cleaned[en_start + len("ENGLISH:"):].strip()

        return {
            "status": "OK",
            "ru": normalize_spaces_inplace(ru_text),
            "en": normalize_spaces_inplace(en_text)
        }
    except Exception:
        return default


def process_url(url: str) -> dict:
    raw_text = fetch_page(url)
    if raw_text:
        media = extract_media(url)
        prompt = build_prompt(raw_text)
        if is_ollama_alive():
            for _ in range(3):
                try:
                    model_output = call_ollama(prompt)
                    result = parse_model_response(model_output)
                    result["media"] = media
                    result['url'] = url
                    if result["status"] == 'OK':
                        return result
                except:
                    pass
            
    return {
            "status": "Ollama ERROR",
            "raw": raw_text,
            "url": url
        }




if __name__ == '__main__':
    urls = [
    #     'https://www.businessinsider.com/openclaw-moltbot-china-internet-alibaba-bytedance-tencent-rednote-ai-agent-2026-2',
    # 'https://www.theverge.com/news/874011/openclaw-ai-skill-clawhub-extensions-security-nightmare'
    # 'https://www.forbes.com/sites/cio/2026/02/05/the-next-ai-breaking-point-is-near-cios-say/',
    # 'https://www.businessinsider.com/reddit-ceo-platform-most-human-place-on-internet-ai-slop-2026-2'
    # 'https://www.bloomberg.com/news/articles/2025-10-09/fed-s-williams-is-watching-job-market-backs-more-rate-cuts-nyt',
    # 'https://www.businessinsider.com/stock-market-investing-strategy-buy-the-dip-dollar-cost-average-2026-2',
    # 'https://www.wired.com/story/meta-google-youtube-social-media-addiction-trial/',
    # 'https://www.npr.org/2026/02/06/g-s1-108952/iran-and-us-set-for-talks-in-oman-over-nuclear-program',
   'https://www.theguardian.com/fashion/2026/feb/06/good-intentions-new-it-bag-antidote-tote',
'https://www.forbes.com/sites/marcberman1/2026/02/06/charles-c-stevenson-jr-character-actor-and-will--grace-bartender-dies-at-95/',
'https://www.theguardian.com/commentisfree/2026/feb/06/trump-family-uae-crypto-deal',
'https://www.theguardian.com/fashion/2026/feb/06/levis-sales-grow-in-uk-as-celebrities-drive-denim-revival',
'https://www.cnbc.com/2026/02/06/5-things-to-know-before-the-stock-market-opens.html'

    ]

    for url in urls:
        result = process_url(url)
        out = result
        print(out)
        # if out["status"] == "OK":
        send_media_post_tg(out)
