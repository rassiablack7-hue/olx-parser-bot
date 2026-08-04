#!/usr/bin/env python3
"""
OLX monitor for Astana — deploy to Railway.
Reads settings from environment variables:
- 8675707834:AAHB2VIOpYyvzn-yJhv3EtrNZ8Flu8UxYu0 (required)
- 1806974839 (required)
- MODELS_JSON (optional) — JSON string mapping model->threshold
- GLOBAL_MAX (optional) — integer threshold for any iPhone
- REGION_PATH (optional, default "astana")
- INTERVAL_SECONDS (optional, default 300)
- DATABASE_URL (optional, if provided will use Postgres)
"""
import os
import time
import re
import json
import random
import logging
from datetime import datetime
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

# DB imports chosen at runtime
import sqlite3
try:
    import psycopg2
except Exception:
    psycopg2 = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

# ENV / config
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
MODELS_JSON = os.getenv('MODELS_JSON')  # e.g. '{"iphone 16 pro": 325000, ... }'
GLOBAL_MAX = int(os.getenv('GLOBAL_MAX')) if os.getenv('GLOBAL_MAX') else None
REGION_PATH = os.getenv('REGION_PATH', 'astana')
INTERVAL = int(os.getenv('INTERVAL_SECONDS', '300'))
DATABASE_URL = os.getenv('DATABASE_URL')  # Railway Postgres URL, optional

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    logging.error("TELEGRAM_TOKEN and TELEGRAM_CHAT_ID must be set in env vars.")
    raise SystemExit(1)

# default models (will be overridden by MODELS_JSON if provided)
DEFAULT_MODELS = {
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

if MODELS_JSON:
    try:
        MODELS = json.loads(MODELS_JSON)
    except Exception:
        logging.exception("MODELS_JSON parse error — using defaults")
        MODELS = DEFAULT_MODELS
else:
    MODELS = DEFAULT_MODELS

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15",
]

price_re = re.compile(r'(\d[\d\s\u00A0]*)')

# DB layer: use Postgres if DATABASE_URL provided and psycopg2 available, otherwise SQLite
use_postgres = DATABASE_URL and psycopg2 is not None

if use_postgres:
    logging.info("Using Postgres DB from DATABASE_URL")
    pg_conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    pg_conn.autocommit = True
    with pg_conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS seen (
                id TEXT PRIMARY KEY,
                title TEXT,
                price INTEGER,
                url TEXT,
                seen_at TIMESTAMP
            )
        """)
else:
    DB_FILE = os.getenv('SQLITE_FILE', 'seen.db')
    logging.info("Using SQLite DB file: %s", DB_FILE)
    sqlite_conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    sc = sqlite_conn.cursor()
    sc.execute('CREATE TABLE IF NOT EXISTS seen(id TEXT PRIMARY KEY, title TEXT, price INTEGER, url TEXT, seen_at TEXT)')
    sqlite_conn.commit()

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        r = requests.post(url, data=payload, timeout=15)
        r.raise_for_status()
    except Exception:
        logging.exception("Telegram send failed")

def build_search_url(query, page=1):
    q = quote_plus(query)
    return f"https://www.olx.kz/d/{REGION_PATH}/q-{q}/?page={page}"

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
        if not title:
            continue
        if 'iphone' not in title.lower():
            continue
        href = a['href']
        if href.startswith('/'):
            href = urljoin("https://www.olx.kz", href)
        # try to find price in parent text
        try:
            parent = a.parent
            parent_text = parent.get_text(separator=' ', strip=True)
        except Exception:
            parent_text = title
        price = parse_price(parent_text) or parse_price(title)
        id_match = re.search(r'(\d{6,})', href)
        lid = id_match.group(1) if id_match else href
        items.append({'id': lid, 'title': title, 'price': price, 'url': href})
    # dedupe
    uniq = []
    seen_ids = set()
    for it in items:
        if it['id'] in seen_ids:
            continue
        seen_ids.add(it['id'])
        uniq.append(it)
    return uniq

def already_seen(lid):
    if use_postgres:
        with pg_conn.cursor() as cur:
            cur.execute("SELECT 1 FROM seen WHERE id=%s", (lid,))
            return cur.fetchone() is not None
    else:
        sc.execute('SELECT 1 FROM seen WHERE id=?', (lid,))
        return sc.fetchone() is not None

def mark_seen(item):
    if use_postgres:
        with pg_conn.cursor() as cur:
            cur.execute("INSERT INTO seen(id, title, price, url, seen_at) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                        (item['id'], item['title'], item['price'] or 0, item['url'], datetime.utcnow()))
    else:
        sc.execute('INSERT OR IGNORE INTO seen(id, title, price, url, seen_at) VALUES (?, ?, ?, ?, ?)',
                   (item['id'], item['title'], item['price'] or 0, item['url'], datetime.utcnow().isoformat()))
        sqlite_conn.commit()

def check_model(model, threshold):
    url = build_search_url(model)
    headers = {'User-Agent': random.choice(USER_AGENTS)}
    try:
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
    except Exception:
        logging.exception("Failed to fetch %s", url)
        return
    listings = extract_listings(r.text)
    for it in listings:
        price = it['price']
        if price is None:
            continue
        match_thresh = threshold
        if GLOBAL_MAX is not None and price <= GLOBAL_MAX:
            match_thresh = GLOBAL_MAX
        if price <= match_thresh:
            if not already_seen(it['id']):
                text = f"НАЙДЕНО: <b>{it['title']}</b>\nЦена: {price}\nИскали: {model}\n{it['url']}"
                logging.info("ALERT: %s", text)
                send_telegram(text)
                mark_seen(it)

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
