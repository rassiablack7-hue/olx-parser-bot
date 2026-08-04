import os
import re
import time
import requests

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

# Запрос к API OLX (поиск iphone в Астане до 325000 KZT)
API_URL = "https://www.olx.kz/api/v1/offers/?offset=0&limit=40&query=iphone&filter_float_price%3Ato=325000&city_id=190"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

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

def get_price_from_item(item):
    """Извлекает цену из любого доступного поля ответа API."""
    # Вариант 1: прямое поле price
    if "price" in item and isinstance(item["price"], dict):
        val = item["price"].get("value") or item["price"].get("regularPrice", {}).get("value")
        if val:
            return int(val)
            
    # Вариант 2: поиск в params
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
    """Нормализует название для гибкого поиска (убирает лишнее)."""
    t = title.lower()
    t = t.replace("айфон", "iphone")
    t = t.replace("про", "pro")
    t = t.replace("макс", "max")
    t = t.replace("мини", "mini")
    # Убираем двойные пробелы
    t = re.sub(r"\s+", " ", t)
    return t

def filter_iphone(title, price):
    norm_title = normalize_title(title)
    
    # Сортируем от самых длинных названий к коротким
    sorted_models = sorted(PRICE_LIMITS.keys(), key=lambda x: len(x), reverse=True)
    
    for model in sorted_models:
        # Проверяем наличие модели в названии (например '13 pro max' или '13 pro')
        if model in norm_title:
            limit = PRICE_LIMITS[model]
            if price <= limit:
                return True, f"iphone {model}", limit
            return False, f"iphone {model}", limit

    # Если конкретную модель 13-16 не распознали, но это iPhone
    if "iphone" in norm_title:
        if price <= DEFAULT_MAX_PRICE:
            return True, "другой iphone", DEFAULT_MAX_PRICE
        return False, "другой iphone", DEFAULT_MAX_PRICE

    return False, None, 0

def check_olx():
    print("Сканирование OLX...")
    try:
        res = requests.get(API_URL, headers=HEADERS, timeout=10)
        if res.status_code != 200:
            print(f"Ошибка API: {res.status_code}")
            return

        data = res.json()
        items = data.get("data", [])
        print(f"Получено объявлений из API: {len(items)}")

        for item in items:
            ad_id = str(item.get("id"))
            title = item.get("title", "")
            url = item.get("url", "")
            price = get_price_from_item(item)

            if price and ad_id not in seen_ads:
                seen_ads.add(ad_id)
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
                        print(f"SKIP (дороже лимита): {title} ({price} > {limit})")

    except Exception as e:
        print(f"Ошибка во время сканирования: {e}")

if __name__ == "__main__":
    print("Бот запущен с обновленным поиском!")
    while True:
        check_olx()
        time.sleep(15)
    
