import os
import re
import time
import requests

# Данные твоего Telegram бота
BOT_TOKEN = "8675707834:AAHB2VIOpYyvzn-yJhv3EtrNZ8Flu8UxYu0"
CHAT_ID = "1806974839"

# Твоя таблица максимальных цен для Астаны (в KZT)
PRICE_LIMITS = {
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
DEFAULT_MAX_PRICE = 250000

# API OLX.kz: Астана (city_id=190), запрос 'iphone', фильтр по цене до 325000 KZT
API_URL = "https://www.olx.kz/api/v1/offers/?offset=0&limit=30&query=iphone&filter_float_price%3Ato=325000&city_id=190"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

# Множество отправленных объявлений
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
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Ошибка отправки в Telegram: {e}")

def filter_iphone(title, price):
    title_lower = title.lower()
    sorted_models = sorted(PRICE_LIMITS.keys(), key=lambda x: len(x), reverse=True)
    
    for model in sorted_models:
        if model in title_lower:
            limit = PRICE_LIMITS[model]
            if price <= limit:
                return True, model, limit
            return False, model, limit

    if "iphone" in title_lower or "айфон" in title_lower:
        if price <= DEFAULT_MAX_PRICE:
            return True, "другой iphone", DEFAULT_MAX_PRICE
        return False, "другой iphone", DEFAULT_MAX_PRICE

    return False, None, 0

def check_olx():
    print("Парсим OLX Астана через API...")
    try:
        res = requests.get(API_URL, headers=HEADERS, timeout=10)
        
        if res.status_code != 200:
            print(f"Ошибка API OLX: статус {res.status_code}")
            return

        data = res.json()
        items = data.get("data", [])

        for item in items:
            ad_id = str(item.get("id"))
            title = item.get("title", "")
            url = item.get("url", "")
            
            # Извлечение цены
            params = item.get("params", [])
            price = None
            for p in params:
                if p.get("key") == "price":
                    price_val = p.get("value", {})
                    price = price_val.get("value")
                    break

            if price and ad_id not in seen_ads:
                seen_ads.add(ad_id)
                is_valid, model_name, limit = filter_iphone(title, price)

                if is_valid:
                    msg = (
                        f"⚡️ <b>Новый iPhone в Астане!</b>\n\n"
                        f"📱 <b>Модель:</b> {model_name.upper()}\n"
                        f"📝 <b>Заголовок:</b> {title}\n"
                        f"💵 <b>Цена:</b> {price:,} KZT (Лимит: {limit:,} KZT)\n\n"
                        f"🔗 <a href='{url}'>Открыть на OLX.kz</a>"
                    )
                    send_telegram_msg(msg)
                    time.sleep(1)

    except Exception as e:
        print(f"Ошибка при запросе к API: {e}")

if __name__ == "__main__":
    print("Бот запущен на Railway через API OLX.kz (проверка каждые 15 секунд)!")
    while True:
        check_olx()
        time.sleep(15)
    
