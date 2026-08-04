import asyncio
import logging
import os
import json
import re
from pathlib import Path

import httpx
from telegram import Bot
from telegram.constants import ParseMode

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8675707834:AAHB2VIOpYyvzn-yJhv3EtrNZ8Flu8UxYu0")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "1806974839")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "15"))
SEEN_FILE = Path("seen_ids.json")

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

# OLX.kz API — Астана, категория телефоны
API_URL = "https://www.olx.kz/api/v1/offers/"
API_PARAMS = {
    "offset": 0,
    "limit": 50,
    "category_id": 1307,  # Мобильные телефоны
    "region_id": 4,       # Астана
    "query": "iphone",
    "sort_by": "created_at:desc",
}

bot = Bot(token=TELEGRAM_TOKEN)

def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()

def save_seen(seen: set):
    SEEN_FILE.write_text(json.dumps(list(seen)))

def extract_price(offer: dict) -> int | None:
    try:
        for param in offer.get("params", []):
            if param.get("key") == "price":
                value = param.get("value", {})
                return int(value.get("value", 0))
    except:
        pass
    return None

def match_model(title: str) -> tuple[str | None, int | None]:
    title_lower = title.lower()
    for model, max_price in sorted(MAX_PRICES.items(), key=lambda x: -len(x[0])):
        if model in title_lower:
            return model, max_price
    return None, None

async def fetch_listings() -> list[dict]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    results = []
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(API_URL, params=API_PARAMS, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            offers = data.get("data", [])
            logger.info(f"Got {len(offers)} offers from API")

            for offer in offers:
                try:
                    ad_id = str(offer.get("id", ""))
                    title = offer.get("title", "")
                    url = offer.get("url", "")
                    price_value = extract_price(offer)
                    price_text = f"{price_value:,} ₸" if price_value else "Цена не указана"
                    location = offer.get("location", {}).get("city", {}).get("name", "")
                    photos = offer.get("photos", [])
                    img_url = photos[0].get("link", "").replace("{width}", "400").replace("{height}", "400") if photos else None

                    model, max_price = match_model(title)
                    if not model:
                        continue
                    if price_value and max_price and price_value >= max_price:
                        continue

                    savings = max_price - price_value if price_value and max_price else None

                    results.append({
                        "id": ad_id,
                        "title": title,
                        "price": price_text,
                        "price_value": price_value,
                        "savings": savings,
                        "location": location,
                        "url": url,
                        "image": img_url,
                    })
                except Exception as e:
                    logger.warning(f"Error processing offer: {e}")
        except Exception as e:
            logger.error(f"API error: {e}")
    return results

async def send_listing(listing: dict):
    savings_text = f"💸 Выгода: *{listing['savings']:,} ₸*\n" if listing.get("savings") else ""
    text = (
        f"📱 *{listing['title']}*\n"
        f"💰 Цена: *{listing['price']}*\n"
        f"{savings_text}"
        f"📍 {listing['location']}\n"
        f"🔗 [Открыть объявление]({listing['url']})"
    )
    try:
        if listing.get("image"):
            await bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=listing["image"], caption=text, parse_mode=ParseMode.MARKDOWN)
        else:
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Send error: {e}")
        try:
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode=ParseMode.MARKDOWN)
        except:
            pass

async def main():
    logger.info("🚀 iPhone Parser Bot — Астана (OLX.kz API)")
    seen = load_seen()

    if not seen:
        logger.info("First run — saving existing IDs...")
        listings = await fetch_listings()
        for l in listings:
            seen.add(l["id"])
        save_seen(seen)
        logger.info(f"Saved {len(seen)} IDs. Watching for new deals...")

    while True:
        try:
            listings = await fetch_listings()
            new = [l for l in listings if l["id"] not in seen]
            if new:
                logger.info(f"✅ {len(new)} new deal(s) found!")
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
