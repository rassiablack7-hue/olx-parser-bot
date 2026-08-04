import os
import re
import time
import cloudscraper

# Данные твоего Telegram бота
BOT_TOKEN = "8675707834:AAHB2VIOpYyvzn-yJhv3EtrNZ8Flu8UxYu0"
CHAT_ID = "1806974839"

# Таблица максимальных цен (в KZT)
PRICE_LIMITS = {
    "16 pro max": 325000,
    "16 pro": 325000,
    "16 plus": 280000,
    "16": 280000,
    "15 pro max": 300000,
    "15 pro": 300000,
    "15 plus": 200000,
    "15": 200000,
    "14 pro max": 200000,
    "14 pro": 200000,
    "14 plus": 105000,
    "14": 105000,
    "13 pro max": 120000,
    "13 pro": 120000,
    "13 mini": 90000,
    "13": 90000,
}
DEFAULT_MAX_PRICE = 250000

# Запрос к API OLX
API_URL = "https://www.olx.kz/api/v1/offers/?offset=0&limit=40&query=iphone&filter_float_price%3Ato=325000&city_id=190"

# Создаем scraper для обхода Cloudflare
scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
)

seen_ads = set()

def send_telegram_msg(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        scraper.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Ошибка отправки в Telegram: {e}")

def get_price_from_item(item):
    if "price" in item and isinstance(item["price"], dict):
        val = item["price"].get("value") or item["price"].get("regularPrice", {}).get("value")
        if val:
            return int(val)
            
    for p in item.get("params", []):
        if p.get("key") == "price":
            val = p.get("value", {})
            if isinstance(val, dict):
                v = val.get("value")
                if v:
                    return int(v)
            elif isinstance(val, (int, float)):
                return int(val)
    return None

def normalize_title(title):
    t = title.lower()
    t = t.replace("айфон", "iphone")
    t = t.replace("про", "pro")
    t = t.replace("макс", "max")
    t = t.replace("мини", "mini")
    t = re.sub(r"\s+", " ", t)
    return t

def filter_iphone(title, price):
    norm_title = normalize_title(title)
    sorted_models = sorted(PRICE_LIMITS.keys(), key=lambda x: len(x), reverse=True)
    
    for model in sorted_models:
        if model in norm_title:
            limit = PRICE_LIMITS[model]
            if price <= limit:
                return True, f"iphone {model}", limit
            return False, f"iphone {model}", limit

    if "iphone" in norm_title:
        if price <= DEFAULT_MAX_PRICE:
            return True, "другой iphone", DEFAULT_MAX_PRICE
        return False, "другой iphone", DEFAULT_MAX_PRICE

    return False, None, 0

def check_olx():
    print("Сканирование OLX...")
    try:
        res = scraper.get(API_URL, timeout=15)
        if res.status_code != 200:
            print(f"Ошибка HTTP: {res.status_code}")
            return

        data = res.json()
        items = data.get("data", [])
        print(f"Получено объявлений из API: {len(items)}")

        for item in items:
            ad_id = str(item.get("id"))
            title = item.get("title", "")
            url = item.get("url", "")
            price = get_price_from_item(item)

            if ad_id not in seen_ads:
                seen_ads.add(ad_id)
                if price:
                    is_valid, model_name, limit = filter_iphone(title, price)
                    if is_valid:
                        print(f"MATCH: {title} | Цена: {price} <= {limit}")
                        msg = (
                            f"⚡️ <b>Новый iPhone в Астане!</b>\n\n"
                            f"📱 <b>Модель:</b> {model_name.upper()}\n"
                            f"📝 <b>Заголовок:</b> {title}\n"
                            f"💵 <b>Цена:</b> {price:,} KZT (Лимит: {limit:,} KZT)\n\n"
                            f"🔗 <a href='{url}'>Открыть на OLX.kz</a>"
                        )
                        send_telegram_msg(msg)
                        time.sleep(1)
                    else:
                        if model_name:
                            print(f"SKIP: {title} ({price} KZT > {limit} KZT)")

    except Exception as e:
        print(f"Ошибка во время сканирования: {e}")

if __name__ == "__main__":
    print("Бот запущен с обходом Cloudflare!")
    while True:
        check_olx()
        time.sleep(15)
