import os

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise SystemExit("Ошибка: не найден BOT_TOKEN")

# ВАЖНО: поставь свой Telegram user id
ADMIN_ID = 8153596056

DATA_DIR = "data"
TEMP_DIR = "temp"
STATE_FILE = os.path.join(DATA_DIR, "state.json")

# сколько держим ссылку для кнопки "Уникализировать?" после отправки оригинала
SESSION_TTL_SEC = 15 * 60

# защита от мусора при падениях
TEMP_FILE_TTL_SEC = 30 * 60
TEMP_CLEAN_INTERVAL_SEC = 10 * 60

# параллельные воркеры очереди
MAX_QUEUE_WORKERS = 2

# задержка в рассылке (антифлуд)
BROADCAST_SLEEP = 0.05
