#!/usr/bin/env python3
# OLX monitor — берет TELEGRAM_TOKEN и TELEGRAM_CHAT_ID из окружения.
import os, time, re, json, random, logging
from datetime import datetime
from urllib.parse import quote_plus, urljoin
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')  # <-- ставьте токен в Railway Variables
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')  # <-- ставьте chat_id в Railway Variables (1806974839)

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    logging.error("TELEGRAM_TOKEN and TELEGRAM_CHAT_ID must be set in environment variables.")
    raise SystemExit(1)

# остальные настройки (можно переопределить через env)
REGION_PATH = os.getenv('REGION_PATH', 'astana')
INTERVAL = int(os.getenv('INTERVAL_SECONDS', '300'))
GLOBAL_MAX = int(os.getenv('GLOBAL_MAX')) if os.getenv('GLOBAL_MAX') else None

MODELS = json.loads(os.getenv('MODELS_JSON')) if os.getenv('MODELS_JSON') else {
    "iphone 16 pro": 325000,
    "iphone 16 pro max": 325000,
    "iphone 16 plus": 280000,
    "iphone 16": 280000,
    "iphone 15 pro": 300000,
    "iphone 15 pro max": 300000,
    "iphone 15 plus": 200000,
    "iphone 15": 200000,
    "iphone 14 pro": 200000,
    "iphone 14 pro max": 200000,
    "iphone 14 plus": 105000,
    "iphone 14": 105000,
    "iphone 13 pro": 120000,
    "iphone 13 pro max": 120000,
    "iphone 13 mini": 90000,
    "iphone 13": 90000
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15",
]

price_re = re.compile(r'(\d[\d\s\u00A0]*)')

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        r = requests.post(url, data=payload, timeout=15)
        r.raise_for_status()
    except Exception:
        logging.exception("Telegram send failed")

def build_search_url(query):
    q = quote_plus(query)
    return f"https://www.olx.kz/d/{REGION_PATH}/q-{q}/"

def parse_price(text):
    if not text:
        return None
    m = price_re.search(text)
    if not m:
        return None
    digits = re.sub(r'\D', '', m.group(1))
    try:
        return int(digits)
    except:
        return None

def extract_listings(html):
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    for a in soup.find_all('a', href=True):
        title = a.get_text(separator=' ', strip=True)
        if not title or 'iphone' not in title.lower():
            continue
        href = a['href']
        if href.startswith('/'):
            href = urljoin("https://www.olx.kz", href)
        parent_text = a.parent.get_text(separator=' ', strip=True) if a.parent else title
        price = parse_price(parent_text) or parse_price(title)
        id_match = re.search(r'(\d{6,})', href)
        lid = id_match.group(1) if id_match else href
        items.append({'id': lid, 'title': title, 'price': price, 'url': href})
    # dedupe
    uniq = []
    seen = set()
    for it in items:
        if it['id'] in seen: continue
        seen.add(it['id'])
        uniq.append(it)
    return uniq

# Простой in-memory "seen" — при перезапуске на Railway используйте Postgres (DATABASE_URL)
seen = set()

def check_model(model, threshold):
    url = build_search_url(model)
    headers = {'User-Agent': random.choice(USER_AGENTS)}
    try:
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
    except Exception:
        logging.exception("Failed to fetch %s", url)
        return
    for it in extract_listings(r.text):
        price = it['price']
        if price is None: continue
        match_thresh = threshold
        if GLOBAL_MAX is not None and price <= GLOBAL_MAX:
            match_thresh = GLOBAL_MAX
        if price <= match_thresh and it['id'] not in seen:
            text = f"НАЙДЕНО: <b>{it['title']}</b>\nЦена: {price}\nМодель поиска: {model}\n{it['url']}"
            logging.info("ALERT: %s", text)
            send_telegram(text)
            seen.add(it['id'])

def main_loop():
    logging.info("Monitor started. Models: %s  global_max=%s", list(MODELS.keys()), GLOBAL_MAX)
    while True:
        for model, thresh in MODELS.items():
            try:
                check_model(model, int(thresh))
                time.sleep(random.uniform(2, 6))
            except Exception:
                logging.exception("Error checking %s", model)
        logging.info("Cycle complete, sleeping %s seconds", INTERVAL)
        time.sleep(INTERVAL)

if __name__ == '__main__':
    main_loop()
