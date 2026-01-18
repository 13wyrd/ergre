import os
import time
import threading

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

import storage
from config import TEMP_DIR, TEMP_FILE_TTL_SEC, TEMP_CLEAN_INTERVAL_SEC, SESSION_TTL_SEC, ADMIN_ID
from texts import TEXTS

# Временная сессия: храним только URL (не файлы)
sessions = {}  # chat_id -> {"url": str, "token": str, "created": ts}

# режим пользователя: download|unique
user_mode = {}

# антиспам: 1 активная задача на пользователя
user_busy = set()
busy_lock = threading.Lock()


def is_admin(chat_id: int) -> bool:
    return chat_id == ADMIN_ID


def is_supported_url(url: str) -> bool:
    if not url:
        return False
    u = url.lower().strip()
    return any(d in u for d in ["tiktok.com", "instagram.com", "youtube.com", "youtu.be"])


def t(chat_id: int, key: str, **kwargs) -> str:
    # админка всегда ru
    lang = "ru" if is_admin(chat_id) else storage.get_lang(chat_id)
    base = TEXTS.get(lang, TEXTS["ru"])
    s = base.get(key, TEXTS["ru"].get(key, key))
    return s.format(**kwargs)


def lang_markup():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(TEXTS["ru"]["lang_ru"], callback_data="lang|ru"),
        InlineKeyboardButton(TEXTS["ru"]["lang_en"], callback_data="lang|en"),
    )
    return kb


def main_menu_markup(chat_id: int):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(t(chat_id, "btn_menu_download"), callback_data="menu|download"),
        InlineKeyboardButton(t(chat_id, "btn_menu_unique"), callback_data="menu|unique"),
    )
    return kb


def ask_unique_markup(chat_id: int, token: str):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(t(chat_id, "btn_yes"), callback_data=f"postuniq_yes|{token}"),
        InlineKeyboardButton(t(chat_id, "btn_no"), callback_data=f"postuniq_no|{token}"),
    )
    return kb


def admin_markup(chat_id: int, broadcast_running: bool):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(t(chat_id, "admin_btn_stats"), callback_data="admin|stats"),
        InlineKeyboardButton(t(chat_id, "admin_btn_broadcast"), callback_data="admin|broadcast"),
    )
    if broadcast_running:
        kb.add(InlineKeyboardButton(t(chat_id, "admin_btn_cancel"), callback_data="admin|cancel_broadcast"))
    return kb


def safe_send_message(bot, chat_id: int, text: str, **kwargs):
    try:
        return bot.send_message(chat_id, text, **kwargs)
    except Exception:
        return None


def safe_edit_message(bot, chat_id: int, message_id: int, text: str, **kwargs):
    try:
        bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, **kwargs)
        return True
    except Exception:
        return False


def expire_sessions():
    now = time.time()
    for chat_id, sess in list(sessions.items()):
        if now - sess.get("created", now) > SESSION_TTL_SEC:
            sessions.pop(chat_id, None)


def cleanup_temp_dir():
    now = time.time()
    try:
        for name in os.listdir(TEMP_DIR):
            path = os.path.join(TEMP_DIR, name)
            if not os.path.isfile(path):
                continue
            try:
                mtime = os.path.getmtime(path)
            except Exception:
                continue
            if now - mtime > TEMP_FILE_TTL_SEC:
                try:
                    os.remove(path)
                except Exception:
                    pass
    except Exception:
        pass


def _temp_cleaner_loop():
    while True:
        cleanup_temp_dir()
        time.sleep(TEMP_CLEAN_INTERVAL_SEC)


def start_temp_cleaner():
    os.makedirs(TEMP_DIR, exist_ok=True)
    cleanup_temp_dir()
    th = threading.Thread(target=_temp_cleaner_loop, daemon=True)
    th.start()
