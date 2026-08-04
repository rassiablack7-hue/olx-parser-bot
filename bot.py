import asyncio
import logging
import os
import json
import re
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from telegram import Bot
from telegram.constants import ParseMode

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8675707834:AAHB2VIOpYyvzn-yJhv3EtrNZ8Flu8UxYu0")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "1806974839")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "15"))
SEEN_FILE = Path("seen_ids.json")
SCRAPER_KEY = "70e24f105bb051b79d46e7c52a85b2be"

MAX_PRICES = {
    "iphone 16 pro max": 325000,
    "iphone 16 pro": 325000,
    "iphone 16 plus": 280000,
    "iphone 16": 280000,
    "iphone 15 pro max": 300000,
    "iphone 15 pro": 300000,
    "iphone 15 plus": 200000,
    "iphone 15": 200000,
    "iphone 14 pro max": 200000,
    "iphone 14 pro": 200000,
    "iphone 14 plus": 105000,
    "iphone 14": 105000,
    "iphone 13 pro max": 120000,
    "iphone 13 pro": 120000,
    "iphone 13 mini": 90000,
    "iphone 13": 90000,
}

BASE_URL = "https://www.olx.kz/astana/elektronika/telefony-i-aksesuary/"
bot = Bot(token=TELEGRAM_TOKEN)

def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()

def save_seen(seen: set):
    SEEN_FILE.write_text(json.dumps(list(seen)))

def match_model(title: str) -> tuple[str | None, int | None]:
    title_lower = title.lower()
    for model, max_price in sorted(MAX_PRICES.items(), key=lambda x: -len(x[0])):
        if model in title_lower:
            return model, max_price
    return None, None

def parse_html_cards(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    cards = soup.select("div[data-cy='l-card']")
    logger.info(f"Cards found: {len(cards)}")
    for card in cards:
        try:
            link = card.select_one("a[href]")
            if not link:
                continue
            href = link["href"]
            m = re.search(r"-(\d+)\.html", href)
            if not m:
                continue
            ad_id = m.group(1)
            title_tag = card.select_one("h4, h6")
            title = title_tag.get_text(strip=True) if title_tag else ""
            price_tag = card.select_one("[data-testid='ad-price']")
            price_text = price_tag.get_text(strip=True) if price_tag else ""
            digits = re.sub(r"[^\d]", "", price_text)
            price_value = int(digits) if digits else None
            location_tag = card.select_one("[data-testid='location-date']")
            location = location_tag.get_text(strip=True) if location_tag else "Астана"
            img = card.select_one("img")
            img_url = img.get("src") if img else None
            full_url = href if href.startswith("http") else f"https://www.olx.kz{href}"
            results.append({
                "id": ad_id, "title": title, "price_text": price_text,
                "price_value": price_value, "location": location,
                "url": full_url, "image": img_url,
            })
        except Exception as e:
            logger.warning(f"Card error: {e}")
    return results

async def fetch_listings() -> list[dict]:
    results = []
    queries = ["iphone+13", "iphone+14", "iphone+15", "iphone+16"]
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        for q in queries:
            try:
                target_url = f"{BASE_URL}?search%5Bq%5D={q}"
                scraper_url = f"http://api.scraperapi.com?api_key={SCRAPER_KEY}&url={target_url}&render=true"
                resp = await client.get(scraper_url)
                logger.info(f"GET {q} -> {resp.status_code}")
                cards = parse_html_cards(resp.text)
                for card in cards:
                    model, max_price = match_model(card["title"])
                    if not model or not card["price_value"]:
                        continue
                    if card["price_value"] >= max_price:
                        continue
                    results.append({
                        "id": card["id"], "title": card["title"],
                        "price": card["price_text"], "price_value": card["price_value"],
                        "savings": max_price - card["price_value"],
                        "location": card["location"], "url": card["url"], "image": card["image"],
                    })
            except Exception as e:
                logger.error(f"Error '{q}': {e}")
            await asyncio.sleep(3)

    seen_ids, unique = set(), []
    for r in results:
        if r["id"] not in seen_ids:
            seen_ids.add(r["id"])
            unique.append(r)
    return unique

async def send_listing(listing: dict):
    savings_text = f"💸 Выгода: {listing['savings']:,} ₸\n".replace(",", " ") if listing.get("savings") else ""
    text = (
        f"📱 {listing['title']}\n"
        f"💰 Цена: {listing['price']}\n"
        f"{savings_text}"
        f"📍 {listing['location']}\n"
        f"🔗 {listing['url']}"
    )
    try:
        if listing.get("image"):
            await bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=listing["image"], caption=text)
        else:
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)
    except Exception as e:
        logger.error(f"Send error: {e}")
        try:
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)
        except:
            pass

async def main():
    logger.info("🚀 iPhone Parser Bot — Астана")
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🚀 Бот запущен! Слежу за iPhone в Астане...")
    seen = load_seen()
    if not seen:
        logger.info("First run — saving existing IDs...")
        listings = await fetch_listings()
        for l in listings:
            seen.add(l["id"])
        save_seen(seen)
        logger.info(f"Saved {len(seen)} IDs.")
    while True:
        try:
            listings = await fetch_listings()
            new = [l for l in listings if l["id"] not in seen]
            if new:
                logger.info(f"✅ {len(new)} new!")
                for listing in new:
                    await send_listing(listing)
                    seen.add(listing["id"])
                    await asyncio.sleep(1)
                save_seen(seen)
            else:
                logger.info("No new deals")
        except Exception as e:
            logger.error(f"Error: {e}")
        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
