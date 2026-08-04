import os, json, logging

# Попытка из окружения
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Если не заданы в окружении — пробуем локальный config.json
if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            cfg = json.load(f)
            TELEGRAM_TOKEN = TELEGRAM_TOKEN or cfg.get('telegram_token')
            TELEGRAM_CHAT_ID = TELEGRAM_CHAT_ID or str(cfg.get('telegram_chat_id'))
            logging.info("Loaded TELEGRAM_TOKEN/chat_id from config.json")
    except FileNotFoundError:
        logging.info("config.json not found")
    except Exception:
        logging.exception("Failed to load config.json")

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    logging.error("TELEGRAM_TOKEN and TELEGRAM_CHAT_ID must be set in environment variables or config.json.")
    raise SystemExit(1)
