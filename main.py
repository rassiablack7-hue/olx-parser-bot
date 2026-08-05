import requests, time, json

TOKEN   = "8675707834:AAHB2VIOpYyvzn-yJhv3EtrNZ8Flu8UxYu0"
CHAT_ID = "1806974839"

SEARCH_QUERIES = {
    "iPhone 16 Pro (до 325к)":     ("iphone 16 pro",     325000),
    "iPhone 16 Pro Max (до 325к)": ("iphone 16 pro max", 325000),
    "iPhone 16 Plus (до 280к)":    ("iphone 16 plus",    280000),
    "iPhone 16 (до 280к)":         ("iphone 16",         280000),
    "iPhone 15 Pro (до 300к)":     ("iphone 15 pro",     300000),
    "iPhone 15 Pro Max (до 300к)": ("iphone 15 pro max", 300000),
    "iPhone 15 Plus (до 200к)":    ("iphone 15 plus",    200000),
    "iPhone 15 (до 200к)":         ("iphone 15",         200000),
    "iPhone 14 Pro (до 200к)":     ("iphone 14 pro",     200000),
    "iPhone 14 Pro Max (до 200к)": ("iphone 14 pro max", 200000),
    "iPhone 14 Plus (до 105к)":    ("iphone 14 plus",    105000),
    "iPhone 14 (до 105к)":         ("iphone 14",         105000),
    "iPhone 13 Pro (до 120к)":     ("iphone 13 pro",     120000),
    "iPhone 13 Pro Max (до 120к)": ("iphone 13 pro max", 120000),
    "iPhone 13 Mini (до 90к)":     ("iphone 13 mini",    90000),
    "iPhone 13 (до 90к)":          ("iphone 13",         90000),
    "iPhone (до 250к)":            ("iphone",            250000),
}

CITY_ID, REGION_ID = 87, 13
CHECK_INTERVAL = 15
SEEN_FILE = "seen_ads.json"
API_URL = "https://www.olx.kz/api/v1/offers/"
HEADERS = {
    "User-Agent": "OLX-Android/15.27.0 (Android 12; Samsung SM-G991B)",
    "Accept": "application/json",
    "Accept-Language": "ru-RU",
    "Referer": "https://www.olx.kz/",
}

def fetch_ads(query, max_price):
    try:
        resp = requests.get(API_URL, headers=HEADERS, params={"query": query, "city_id": CITY_ID, "region_id": REGION_ID, "filter_float_price:to": max_price, "sort_by": "created_at:desc", "limit": 50}, timeout=10)
        print(f"    HTTP {resp.status_code}")
        if resp.status_code != 200:
            return []
        ads = []
        for o in resp.json().get("data", []):
            if o.get("location", {}).get("city", {}).get("id") != CITY_ID:
                continue
            price = "Цена не указана"
            for p in o.get("params", []):
                if p.get("key") == "price":
                    price = p.get("value", {}).get("label", price)
            if o.get("id") and o.get("url"):
                ads.append({"id": str(o["id"]), "title": o.get("title", "-"), "price": price, "url": o["url"]})
        return ads
    except Exception as e:
        print(f"    Ошибка: {e}")
        return []

def load_seen():
    try:
        with open(SEEN_FILE) as f: return set(json.load(f))
    except: return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f: json.dump(list(seen), f)

def send_telegram(text):
    try:
        r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False},
            timeout=10)
        return r.status_code == 200
    except: return False

def check_olx(seen):
    print(f"[{time.strftime('%H:%M:%S')}] Проверяю...")
    new_count = 0
    for name, (query, max_price) in SEARCH_QUERIES.items():
        print(f"  ▶ {name}")
        ads = fetch_ads(query, max_price)
        new_ads = [a for a in ads if a["id"] not in seen]
        print(f"    Найдено: {len(ads)}, новых: {len(new_ads)}")
        for ad in new_ads:
            seen.add(ad["id"])
            send_telegram(f"⚡️ <b>{name}</b>\n\n📌 {ad['title']}\n💰 {ad['price']}\n📍 Астана\n🔗 {ad['url']}")
            new_count += 1
            time.sleep(0.3)
        time.sleep(1)
    return new_count

seen = load_seen()
if not seen:
    print("Первый запуск — собираю базу...")
    for name, (query, max_price) in SEARCH_QUERIES.items():
        for a in fetch_ads(query, max_price): seen.add(a["id"])
        time.sleep(2)
    save_seen(seen)
    print(f"База: {len(seen)} объявлений")

send_telegram("✅ <b>OLX бот запущен!</b>\n📍 Астана\n\n" + "\n".join(f"• {n}" for n in SEARCH_QUERIES))

while True:
    n = check_olx(seen)
    save_seen(seen)
    print(f"Новых: {n}. Жду {CHECK_INTERVAL} сек...")
    time.sleep(CHECK_INTERVAL)
