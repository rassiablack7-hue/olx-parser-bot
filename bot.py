import os
import re
import time
import requests
from bs4 import BeautifulSoup

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

# Рабочий базовый URL категории смартфонов Астаны
BASE_URL = "https://www.olx.kz/elektronika/telefony-i-accessories/mobilnye-telefony-smartfony/astana/"

PARAMS = {
    "search[search_term]": "iphone",
    "search[filter_float_price:to]": "325000"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
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

def extract_price(price_str):
    digits = re.sub(r"\D", "", price_str)
    return int(digits) if digits else None

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
    print("Сканирование OLX.kz...")
    try:
        session = requests.Session()
        res = session.get(BASE_URL, params=PARAMS, headers=HEADERS, timeout=15)
        
        if res.status_code != 200:
            print(f"Ошибка HTTP: {res.status_code}")
            return

        soup = BeautifulSoup(res.text, "html.parser")
        
        # Поиск всех карточек объявлений
        cards = soup.find_all("div", data_testid="ad-card")
        if not cards:
            cards = soup.find_all("div", class_=re.compile("css-"))

        print(f"Успешный ответ (200 OK)! Найдено карточек: {len(cards)}")

        for card in cards:
            link_el = card.find("a", href=True)
            title_el = card.find("h6") or card.find("h4")
            price_el = card.find("p", data_testid="ad-price") or card.find("p", class_=re.compile("price"))

            if not link_el or not title_el or not price_el:
                continue

            title = title_el.get_text(strip=True)
            price = extract_price(price_el.get_text(strip=True))
            
            href = link_el["href"]
            if not href.startswith("http"):
                href = "https://www.olx.kz" + href
            
            ad_id = href.split("#")[0].split("?")[0]

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
                            f"🔗 <a href='{href}'>Открыть на OLX.kz</a>"
                        )
                        send_telegram_msg(msg)
                        time.sleep(1)
                    else:
                        if model_name:
                            print(f"SKIP: {title} ({price} KZT > {limit} KZT)")

    except Exception as e:
        print(f"Ошибка парсинга: {e}")

if __name__ == "__main__":
    print("Бот запущен!")
    while True:
        check_olx()
        time.sleep(20)
    
