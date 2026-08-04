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
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "60"))
SEEN_FILE = Path("seen_ids.json")

# Максимальные цены (тенге) — если дешевле, отправляем
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

# OLX Казахстан — Астана — поиск iPhone
OLX_URLS = [
    "https://www.olx.kz/astana/elektronika/telefony-i-aksessuary/mobilnye-telefony-smartfony/?search%5Bfilter_float_price%3Ato%5D=325000&search%5Bq%5D=iphone",
]

bot = Bot(token=TELEGRAM_TOKEN)


def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def save_seen(seen: set):
    SEEN_FILE.write_text(json.dumps(list(seen)))


def extract_price(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def match_model(title: str) -> tuple[str | None, int | None]:
    title_lower = title.lower()
    # Проверяем от самых длинных моделей к коротким
    for model, max_price in sorted(MAX_PRICES.items(), key=lambda x: -len(x[0])):
        if model in title_lower:
            return model, max_price
    return None, None


def parse_listings(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    listings = []
    cards = soup.select("div[data-cy='l-card']")

    for card in cards:
        try:
            link_tag = card.select_one("a[href]")
            if not link_tag:
                continue
            href = link_tag.get("href", "")
            match = re.search(r"-(\d+)\.html", href)
            if not match:
                continue
            ad_id = match.group(1)

            title_tag = card.select_one("h6, h4, [data-cy='ad-card-title']")
            title = title_tag.get_text(strip=True) if title_tag else ""
            if not title:
                continue

            price_tag = card.select_one("[data-testid='ad-price'], .price")
            price_text = price_tag.get_text(strip=True) if price_tag else ""
            price_value = extract_price(price_text)

            location_tag = card.select_one("[data-testid='location-date'], .location")
            location = location_tag.get_text(strip=True) if location_tag else ""

            img_tag = card.select_one("img")
            img_url = img_tag.get("src") if img_tag else None

            full_url = href if href.startswith("http") else f"https://www.olx.kz{href}"

            # Проверяем модель и цену
            model, max_price = match_model(title)
            if not model:
                continue
            if price_value and max_price and price_value >= max_price:
                continue  # Дороже нашего лимита — пропускаем

            savings = max_price - price_value if price_value and max_price else None

            listings.append({
                "id": ad_id,
                "title": title,
                "model": model,
                "price": price_text,
                "price_value": price_value,
                "max_price": max_price,
                "savings": savings,
                "location": location,
                "url": full_url,
                "image": img_url,
            })
        except Exception as e:
            logger.warning(f"Error parsing card: {e}")
    return listings


async def fetch_listings() -> list[dict]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9",
    }
    all_listings = []
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for url in OLX_URLS:
            try:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                all_listings.extend(parse_listings(resp.text))
            except Exception as e:
                logger.error(f"Fetch error {url}: {e}")
    return all_listings


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
            await bot.send_photo(
                chat_id=TELEGRAM_CHAT_ID,
                photo=listing["image"],
                caption=text,
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=text,
                parse_mode=ParseMode.MARKDOWN,
            )
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
