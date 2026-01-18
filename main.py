import asyncio
import os
import re
import logging
from dataclasses import dataclass
from typing import Optional, List, Tuple

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (
    Message,
    ChatJoinRequest,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ErrorEvent,
)
from aiogram.client.default import DefaultBotProperties

import aiosqlite
from dotenv import load_dotenv


# =========================
# CONFIG
# =========================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL_ID = int(os.getenv("CHANNEL_ID")) if os.getenv("CHANNEL_ID") else None

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set")


# =========================
# ADMINS (можно прямо в коде)
# =========================
DEFAULT_ADMINS = {
    8153596056,  # <-- ВПИШИ СВОЙ TELEGRAM ID
}

ADMIN_IDS = set(
    int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
) or DEFAULT_ADMINS


# =========================
# CONSTANTS
# =========================
DB_PATH = "bot.db"
BROADCAST_RPS = 20

WELCOME_DEFAULT_TEXT = "Привет! 👋\nСпасибо за заявку."
WELCOME_DEFAULT_BUTTON_TEXT = "Открыть"
WELCOME_DEFAULT_BUTTON_URL = "https://t.me/"


# =========================
# HELPERS
# =========================
def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


# =========================
# DATABASE
# =========================
async def db_init():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        await db.execute("PRAGMA busy_timeout=5000;")

        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            is_blocked INTEGER DEFAULT 0
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS welcome (
            id INTEGER PRIMARY KEY CHECK (id=1),
            media_type TEXT,
            media_file_id TEXT,
            text TEXT,
            button_text TEXT,
            button_url TEXT
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS admin_state (
            admin_id INTEGER PRIMARY KEY,
            state TEXT
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS broadcast_lock (
            id INTEGER PRIMARY KEY CHECK (id=1),
            is_running INTEGER
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id=1),
            is_enabled INTEGER
        )
        """)

        await db.execute("""
        INSERT OR IGNORE INTO welcome VALUES
        (1, NULL, NULL, ?, ?, ?)
        """, (WELCOME_DEFAULT_TEXT, WELCOME_DEFAULT_BUTTON_TEXT, WELCOME_DEFAULT_BUTTON_URL))

        await db.execute("INSERT OR IGNORE INTO broadcast_lock VALUES (1,0)")
        await db.execute("INSERT OR IGNORE INTO settings VALUES (1,1)")

        await db.commit()


# =========================
# SETTINGS
# =========================
async def get_enabled() -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT is_enabled FROM settings WHERE id=1")
        return bool((await cur.fetchone())[0])


async def set_enabled(v: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE settings SET is_enabled=?", (1 if v else 0,))
        await db.commit()


# =========================
# WELCOME
# =========================
@dataclass
class Welcome:
    media_type: Optional[str]
    media_id: Optional[str]
    text: str
    btn_text: str
    btn_url: str


async def get_welcome() -> Welcome:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT media_type, media_file_id, text, button_text, button_url
            FROM welcome WHERE id=1
        """)
        return Welcome(*await cur.fetchone())


async def send_welcome(bot: Bot, uid: int):
    w = await get_welcome()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=w.btn_text, url=w.btn_url)]
    ])

    if w.media_type == "photo":
        await bot.send_photo(uid, w.media_id, caption=w.text, reply_markup=kb)
    elif w.media_type == "video":
        await bot.send_video(uid, w.media_id, caption=w.text, reply_markup=kb)
    else:
        await bot.send_message(uid, w.text, reply_markup=kb)


# =========================
# KEYBOARDS
# =========================
async def kb_admin():
    enabled = await get_enabled()
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🟢 Включен" if enabled else "🔴 Выключен")],
            [KeyboardButton(text="📌 Приветствие")],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
    )


# =========================
# HANDLERS
# =========================
async def on_join(event: ChatJoinRequest, bot: Bot):
    if not await get_enabled():
        return
    if CHANNEL_ID and event.chat.id != CHANNEL_ID:
        return
    await send_welcome(bot, event.user_chat_id)


async def cmd_start(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    await msg.answer("Админка 👇", reply_markup=await kb_admin())


async def admin_router(msg: Message):
    if msg.chat.type != "private":
        return
    if not is_admin(msg.from_user.id):
        return

    text = (msg.text or "").strip()

    if text in ("🟢 Включен", "🔴 Выключен"):
        await set_enabled(not await get_enabled())
        return await msg.answer("Готово", reply_markup=await kb_admin())

    if text == "❌ Отмена":
        return await msg.answer("Отменено", reply_markup=await kb_admin())


# =========================
# ERROR HANDLER
# =========================
async def on_error(event: ErrorEvent):
    logging.exception(event.exception)
    return True


# =========================
# START
# =========================
async def main():
    logging.basicConfig(level=logging.INFO)
    await db_init()

    bot = Bot(
        BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    dp = Dispatcher()
    dp.errors.register(on_error)

    dp.chat_join_request.register(on_join)
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(admin_router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
