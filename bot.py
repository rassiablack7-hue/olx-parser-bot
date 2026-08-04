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

async def fetch_listings() -> list[dict]:
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Referer": "https://www.olx.kz/",
        "Origin": "https://www.olx.kz",
    }

    # Ищем каждую модель отдельно через внутренний поиск OLX
    search_queries = ["iphone 13", "iphone 14", "iphone 15", "iphone 16"]

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for query in search_queries:
            try:
                url = f"https://www.olx.kz/elektronika/telefony-i-aksesuary/astana/q-{query.replace(' ', '-')}/"
                resp = await client.get(url, headers=headers)
                
                # Ищем JSON данные внутри HTML (Next.js __NEXT_DATA__)
                match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', resp.text, re.DOTALL)
                if not match:
                    logger.warning(f"No __NEXT_DATA__ for {query}")
                    continue

                data = json.loads(match.group(1))
                offers = (
                    data.get("props", {})
                    .get("pageProps", {})
                    .get("listing", {})
                    .get("listing", {})
                    .get("ads", [])
                )
                logger.info(f"'{query}': got {len(offers)} offers")

                for offer in offers:
                    try:
                        ad_id = str(offer.get("id", ""))
                        title = offer.get("title", "")
                        url_ad = offer.get("url", "")
                        location = offer.get("location", {}).get("cityName", "")
                        photos = offer.get("photos", [])
                        img_url = photos[0] if photos else None

                        # Цена
                        price_value = None
                        price_text = "Цена не указана"
                        for param in offer.get("params", []):
                            if param.get("key") == "price":
                                raw = param.get("value", {}).get("value", "")
                                digits = re.sub(r"[^\d]", "", str(raw))
                                if digits:
                                    price_value = int(digits)
                                    price_text = f"{price_value:,} ₸".replace(",", " ")
                                break

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
                            "url": url_ad,
                            "image": img_url,
                        })
                    except Exception as e:
                        logger.warning(f"Offer error: {e}")

                await asyncio.sleep(2)

            except Exception as e:
                logger.error(f"Fetch error for '{query}': {e}")

    # Убираем дубли
    seen_ids = set()
    unique = []
    for r in results:
        if r["id"] not in seen_ids:
            seen_ids.add(r["id"])
            unique.append(r)
    return unique

async def send_listing(listing: dict):
    savings_text = f"💸 Выгода: *{listing['savings']:,} ₸*\n".replace(",", " ") if listing.get("savings") else ""
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
    logger.info("🚀 iPhone Parser Bot — Астана (OLX.kz)")
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
                logger.info(f"✅ {len(new)} new deal(s)!")
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
