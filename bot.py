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

BASE_URL = "https://www.olx.kz/elektronika/telefony-i-aksesuary/astana/"

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

async def fetch_page(client: httpx.AsyncClient, url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    resp = await client.get(url, headers=headers)
    logger.info(f"GET {url} -> {resp.status_code}")
    return resp.text

def parse_json_from_html(html: str) -> list[dict]:
    # Способ 1: __NEXT_DATA__
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            ads = (data.get("props", {})
                      .get("pageProps", {})
                      .get("listing", {})
                      .get("listing", {})
                      .get("ads", []))
            if ads:
                logger.info(f"Found {len(ads)} ads via __NEXT_DATA__")
                return ads
        except Exception as e:
            logger.warning(f"__NEXT_DATA__ parse error: {e}")

    # Способ 2: window.__PRERENDERED_STATE__
    match = re.search(r'window\.__PRERENDERED_STATE__\s*=\s*({.*?});\s*</script>', html, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            ads = data.get("listing", {}).get("listing", {}).get("ads", [])
            if ads:
                logger.info(f"Found {len(ads)} ads via PRERENDERED_STATE")
                return ads
        except Exception as e:
            logger.warning(f"PRERENDERED_STATE parse error: {e}")

    return []

def parse_html_cards(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    cards = soup.select("div[data-cy='l-card'], div[data-testid='listing-grid'] > div")
    logger.info(f"HTML cards found: {len(cards)}")
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
            title_tag = card.select_one("h4, h6, [data-cy='ad-card-title'] h4")
            title = title_tag.get_text(strip=True) if title_tag else ""
            price_tag = card.select_one("[data-testid='ad-price']")
            price_text = price_tag.get_text(strip=True) if price_tag else ""
            digits = re.sub(r"[^\d]", "", price_text)
            price_value = int(digits) if digits else None
            location_tag = card.select_one("[data-testid='location-date']")
            location = location_tag.get_text(strip=True) if location_tag else ""
            img = card.select_one("img")
            img_url = img.get("src") if img else None
            full_url = href if href.startswith("http") else f"https://www.olx.kz{href}"
            results.append({
                "id": ad_id, "title": title, "price_text": price_text,
                "price_value": price_value, "location": location,
                "url": full_url, "image": img_url,
            })
        except Exception as e:
            logger.warning(f"Card parse error: {e}")
    return results

async def fetch_listings() -> list[dict]:
    results = []
    queries = ["iphone+13", "iphone+14", "iphone+15", "iphone+16"]

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for q in queries:
            url = f"{BASE_URL}?search%5Bq%5D={q}"
            try:
                html = await fetch_page(client, url)

                # Пробуем извлечь из JSON
                ads = parse_json_from_html(html)
                if ads:
                    for offer in ads:
                        try:
                            ad_id = str(offer.get("id", ""))
                            title = offer.get("title", "")
                            url_ad = offer.get("url", "")
                            if not url_ad.startswith("http"):
                                url_ad = "https://www.olx.kz" + url_ad
                            location = offer.get("location", {}).get("cityName", "Астана")
                            photos = offer.get("photos", [])
                            img_url = photos[0] if photos and isinstance(photos[0], str) else None
                            if not img_url and photos and isinstance(photos[0], dict):
                                img_url = photos[0].get("link", "").replace("{width}", "400").replace("{height}", "400")

                            price_value = None
                            price_text = "Цена не указана"
                            for param in offer.get("params", []):
                                if param.get("key") == "price":
                                    raw = str(param.get("value", {}).get("value", ""))
                                    digits = re.sub(r"[^\d]", "", raw)
                                    if digits:
                                        price_value = int(digits)
                                        price_text = f"{price_value:,} ₸".replace(",", " ")
                                    break

                            model, max_price = match_model(title)
                            if not model or not price_value:
                                continue
                            if price_value >= max_price:
                                continue

                            results.append({
                                "id": ad_id, "title": title, "price": price_text,
                                "price_value": price_value, "savings": max_price - price_value,
                                "location": location, "url": url_ad, "image": img_url,
                            })
                        except Exception as e:
                            logger.warning(f"Offer error: {e}")
                else:
                    # Fallback: HTML парсинг
                    cards = parse_html_cards(html)
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
                logger.error(f"Fetch error '{q}': {e}")
            await asyncio.sleep(2)

    seen_ids, unique = set(), []
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
        f"🔗 [Открыть]({listing['url']})"
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
    logger.info("🚀 iPhone Parser Bot — Астана")
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
