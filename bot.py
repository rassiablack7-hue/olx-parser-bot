import os
import re
import time
import requests
from bs4 import BeautifulSoup

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

# Исправленный поисковый URL (убран лишний префикс /d/)
BASE_URL = "https://www.olx.kz/elektronika/telefony-i-accessories/mobilnye-telefony-smartfony/astana/q-iphone/?search%5Bfilter_float_price%3Ato%5D=325000"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
}

def send_telegram_msg(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Ошибка отправки в ТГ: {e}")

def extract_price(price_text):
    digits = re.sub(r"\D", "", price_text)
    return int(digits) if digits else None

def filter_iphone(title, price):
    title_lower = title.lower()
    
    # Сначала проверяем точные совпадения по длинным названиям
    sorted_models = sorted(PRICE_LIMITS.keys(), key=lambda x: len(x), reverse=True)
    
    for model in sorted_models:
        if model in title_lower:
            limit = PRICE_LIMITS[model]
            if price <= limit:
                return True, model, limit
            return False, model, limit

    # Если модель четко не распознана, но в заголовке есть iPhone / айфон
    if "iphone" in title_lower or "айфон" in title_lower:
        if price <= DEFAULT_MAX_PRICE:
            return True, "другой iphone", DEFAULT_MAX_PRICE
        return False, "другой iphone", DEFAULT_MAX_PRICE

    return False, None, 0

def check_olx():
    print("Парсим OLX Астана...")
    try:
        res = requests.get(BASE_URL, headers=HEADERS, timeout=10)
        if res.status_code != 200:
            print(f"Ошибка сайта: статус {res.status_code}")
            return

        soup = BeautifulSoup(res.text, "html.parser")
        cards = soup.find_all("div", data_testid="ad-card") or soup.find_all("div", class_=re.compile("css-"))
        
        for card in cards:
            title_el = card.find("h6") or card.find("h4")
            price_el = card.find("p", data_testid="ad-price")
            link_el = card.find("a", href=True)

            if not title_el or not price_el or not link_el:
                continue

            title = title_el.get_text(strip=True)
            price = extract_price(price_el.get_text(strip=True))
            
            link = link_el["href"]
            if not link.startswith("http"):
                link = "https://www.olx.kz" + link
            
            clean_link = link.split("#")[0].split("?")[0]

            if price and clean_link not in seen_ads:
                is_valid, model_name, limit = filter_iphone(title, price)
                
                # Запоминаем объявление
                seen_ads.add(clean_link)
                
                if is_valid:
                    msg = (
                        f"⚡️ <b>Новый iPhone в Астане!</b>\n\n"
                        f"📱 <b>Модель:</b> {model_name.upper()}\n"
                        f"📝 <b>Заголовок:</b> {title}\n"
                        f"💵 <b>Цена:</b> {price:,} KZT (Лимит: {limit:,} KZT)\n\n"
                        f"🔗 <a href='{clean_link}'>Открыть на OLX.kz</a>"
                    )
                    send_telegram_msg(msg)
                    time.sleep(1)
                    
    except Exception as e:
        print(f"Ошибка во время парсинга: {e}")

if __name__ == "__main__":
    print("Бот запущен на Railway (проверка каждые 15 секунд)!")
    while True:
        check_olx()
        # Задержка 15 секунд
        time.sleep(15)
    
