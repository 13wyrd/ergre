import asyncio
import os
import re
import logging
from dataclasses import dataclass
from typing import Optional, List, Tuple

import aiosqlite
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
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

# =========================
# CONFIG
# =========================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL_ID = int(os.getenv("CHANNEL_ID")) if os.getenv("CHANNEL_ID") else None

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing (set it in ENV, not in code).")

# Admins: ENV overrides defaults, otherwise defaults used
DEFAULT_ADMINS = {
    123456789,  # <-- PUT YOUR TELEGRAM ID HERE
}

ADMIN_IDS = set(int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()) or DEFAULT_ADMINS

DB_PATH = "bot.db"
BROADCAST_RPS = 20

WELCOME_DEFAULT_TEXT = "Привет! 👋\nСпасибо за заявку. Вот полезная информация:"
WELCOME_DEFAULT_BUTTON_TEXT = "Открыть"
WELCOME_DEFAULT_BUTTON_URL = "https://t.me/"


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


# =========================
# DB
# =========================
async def db_init():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        await db.execute("PRAGMA busy_timeout=5000;")

        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            created_at INTEGER,
            is_blocked INTEGER DEFAULT 0
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS welcome (
            id INTEGER PRIMARY KEY CHECK (id = 1),
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
            id INTEGER PRIMARY KEY CHECK (id = 1),
            is_running INTEGER NOT NULL
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            is_enabled INTEGER NOT NULL
        )
        """)

        # Ensure singleton welcome row
        cur = await db.execute("SELECT COUNT(*) FROM welcome WHERE id=1")
        (count,) = await cur.fetchone()
        if count == 0:
            await db.execute(
                "INSERT INTO welcome (id, media_type, media_file_id, text, button_text, button_url) "
                "VALUES (1, NULL, NULL, ?, ?, ?)",
                (WELCOME_DEFAULT_TEXT, WELCOME_DEFAULT_BUTTON_TEXT, WELCOME_DEFAULT_BUTTON_URL),
            )

        # Ensure broadcast lock row
        cur = await db.execute("SELECT COUNT(*) FROM broadcast_lock WHERE id=1")
        (lcount,) = await cur.fetchone()
        if lcount == 0:
            await db.execute("INSERT INTO broadcast_lock (id, is_running) VALUES (1, 0)")

        # Ensure settings row (enabled by default)
        cur = await db.execute("SELECT COUNT(*) FROM settings WHERE id=1")
        (scount,) = await cur.fetchone()
        if scount == 0:
            await db.execute("INSERT INTO settings (id, is_enabled) VALUES (1, 1)")

        await db.commit()


async def get_enabled() -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA busy_timeout=5000;")
        cur = await db.execute("SELECT is_enabled FROM settings WHERE id=1")
        (v,) = await cur.fetchone()
        return bool(v)


async def set_enabled(enabled: bool) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA busy_timeout=5000;")
        await db.execute("UPDATE settings SET is_enabled=? WHERE id=1", (1 if enabled else 0,))
        await db.commit()


async def upsert_user(user) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA busy_timeout=5000;")
        await db.execute("""
        INSERT INTO users (user_id, username, first_name, last_name, created_at, is_blocked)
        VALUES (?, ?, ?, ?, strftime('%s','now'), 0)
        ON CONFLICT(user_id) DO UPDATE SET
            username=excluded.username,
            first_name=excluded.first_name,
            last_name=excluded.last_name
        """, (user.id, user.username, user.first_name, user.last_name))
        await db.commit()


async def mark_blocked(user_id: int, blocked: bool = True) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA busy_timeout=5000;")
        await db.execute("UPDATE users SET is_blocked=? WHERE user_id=?", (1 if blocked else 0, user_id))
        await db.commit()


@dataclass
class WelcomeConfig:
    media_type: Optional[str]
    media_file_id: Optional[str]
    text: str
    button_text: str
    button_url: str


async def get_welcome() -> WelcomeConfig:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA busy_timeout=5000;")
        cur = await db.execute("""
            SELECT media_type, media_file_id, text, button_text, button_url
            FROM welcome WHERE id=1
        """)
        row = await cur.fetchone()
        return WelcomeConfig(
            media_type=row[0],
            media_file_id=row[1],
            text=row[2] or "",
            button_text=row[3] or "Открыть",
            button_url=row[4] or "https://t.me/",
        )


async def set_welcome_text(text: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA busy_timeout=5000;")
        await db.execute("UPDATE welcome SET text=? WHERE id=1", (text,))
        await db.commit()


async def set_welcome_button(btn_text: str, btn_url: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA busy_timeout=5000;")
        await db.execute("UPDATE welcome SET button_text=?, button_url=? WHERE id=1", (btn_text, btn_url))
        await db.commit()


async def set_welcome_media(media_type: Optional[str], media_file_id: Optional[str]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA busy_timeout=5000;")
        await db.execute("UPDATE welcome SET media_type=?, media_file_id=? WHERE id=1", (media_type, media_file_id))
        await db.commit()


async def get_stats() -> Tuple[int, int]:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA busy_timeout=5000;")
        cur = await db.execute("SELECT COUNT(*) FROM users")
        (total,) = await cur.fetchone()
        cur = await db.execute("SELECT COUNT(*) FROM users WHERE is_blocked=1")
        (blocked,) = await cur.fetchone()
        return total, blocked


async def get_broadcast_targets() -> List[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA busy_timeout=5000;")
        cur = await db.execute("SELECT user_id FROM users WHERE is_blocked=0")
        rows = await cur.fetchall()
        return [r[0] for r in rows]


async def admin_state_set(admin_id: int, state: Optional[str]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA busy_timeout=5000;")
        if state is None:
            await db.execute("DELETE FROM admin_state WHERE admin_id=?", (admin_id,))
        else:
            await db.execute("INSERT OR REPLACE INTO admin_state (admin_id, state) VALUES (?,?)", (admin_id, state))
        await db.commit()


async def admin_state_get(admin_id: int) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA busy_timeout=5000;")
        cur = await db.execute("SELECT state FROM admin_state WHERE admin_id=?", (admin_id,))
        row = await cur.fetchone()
        return row[0] if row else None


async def broadcast_is_running() -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA busy_timeout=5000;")
        cur = await db.execute("SELECT is_running FROM broadcast_lock WHERE id=1")
        (v,) = await cur.fetchone()
        return bool(v)


async def broadcast_lock_set(running: bool) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA busy_timeout=5000;")
        await db.execute("UPDATE broadcast_lock SET is_running=? WHERE id=1", (1 if running else 0,))
        await db.commit()


# =========================
# UI (Reply keyboards only)
# =========================
async def kb_admin_main() -> ReplyKeyboardMarkup:
    enabled = await get_enabled()
    toggle_label = "🟢 Бот включен" if enabled else "🔴 Бот выключен"
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=toggle_label)],
            [KeyboardButton(text="📌 Приветствие"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="📣 Рассылка"), KeyboardButton(text="⛔ Стоп рассылка")],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def kb_welcome_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✏️ Текст приветствия"), KeyboardButton(text="🖼/🎥 Медиа")],
            [KeyboardButton(text="🔘 Кнопка"), KeyboardButton(text="🗑 Удалить медиа")],
            [KeyboardButton(text="👀 Предпросмотр"), KeyboardButton(text="⬅️ Назад")],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def welcome_inline_kb(cfg: WelcomeConfig) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=cfg.button_text, url=cfg.button_url)]])


async def show_admin_panel(message: Message):
    await message.answer("Админ-панель 👇", reply_markup=await kb_admin_main())


async def show_welcome_panel(message: Message):
    await message.answer("Настройки приветствия 👇", reply_markup=kb_welcome_menu())


# =========================
# Core: send welcome
# =========================
async def send_welcome(bot: Bot, chat_id: int, cfg: WelcomeConfig) -> None:
    kb = welcome_inline_kb(cfg)

    if cfg.media_type == "photo" and cfg.media_file_id:
        await bot.send_photo(chat_id, photo=cfg.media_file_id, caption=cfg.text, reply_markup=kb)
        return

    if cfg.media_type == "video" and cfg.media_file_id:
        await bot.send_video(chat_id, video=cfg.media_file_id, caption=cfg.text, reply_markup=kb)
        return

    await bot.send_message(chat_id, cfg.text, reply_markup=kb)


# =========================
# Broadcast
# =========================
BROADCAST_STOP = False


async def run_broadcast(bot: Bot, admin_id: int, payload_type: str, payload_id: Optional[str], payload_caption: str):
    global BROADCAST_STOP
    BROADCAST_STOP = False

    try:
        await broadcast_lock_set(True)

        targets = await get_broadcast_targets()
        sent = 0
        failed = 0
        delay = 1.0 / max(1, BROADCAST_RPS)

        for uid in targets:
            if BROADCAST_STOP:
                break
            try:
                if payload_type == "photo":
                    await bot.send_photo(uid, photo=payload_id, caption=payload_caption)
                elif payload_type == "video":
                    await bot.send_video(uid, video=payload_id, caption=payload_caption)
                else:
                    await bot.send_message(uid, payload_caption)
                sent += 1
            except Exception as e:
                failed += 1
                msg = str(e).lower()
                if "blocked" in msg or "forbidden" in msg:
                    await mark_blocked(uid, True)

            await asyncio.sleep(delay)

        if BROADCAST_STOP:
            await bot.send_message(admin_id, f"⛔ Рассылка остановлена.\nОтправлено: {sent}\nОшибок: {failed}")
        else:
            await bot.send_message(admin_id, f"✅ Рассылка завершена.\nОтправлено: {sent}\nОшибок: {failed}")

    except Exception:
        logging.exception("Broadcast crashed")
        try:
            await bot.send_message(admin_id, "⚠️ Рассылка упала с ошибкой. Смотрите консоль.")
        except Exception:
            pass
    finally:
        await broadcast_lock_set(False)


# =========================
# Error handler (anti-crash)
# =========================
async def on_error(event: ErrorEvent):
    logging.exception("Unhandled error: %s", event.exception)
    return True


# =========================
# Handlers
# =========================
async def cmd_start(message: Message):
    # store user anyway
    try:
        await upsert_user(message.from_user)
    except Exception:
        pass

    # users -> silence
    if not is_admin(message.from_user.id):
        return

    await show_admin_panel(message)


async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    await admin_state_set(message.from_user.id, None)
    await show_admin_panel(message)


async def on_join_request(event: ChatJoinRequest, bot: Bot):
    # if disabled -> do nothing
    if not await get_enabled():
        return

    if CHANNEL_ID is not None and event.chat.id != CHANNEL_ID:
        return

    await upsert_user(event.from_user)
    cfg = await get_welcome()

    try:
        await send_welcome(bot, event.user_chat_id, cfg)
    except Exception as e:
        msg = str(e).lower()
        if "blocked" in msg or "forbidden" in msg:
            await mark_blocked(event.from_user.id, True)


async def admin_router(message: Message, bot: Bot):
    global BROADCAST_STOP

    # admin panel only in private chat
    if message.chat.type != "private":
        return
    if not message.from_user or not is_admin(message.from_user.id):
        return

    txt_raw = (message.text or "").strip()
    txt = txt_raw.lower()

    # Toggle bot enabled
    if txt_raw in {"🟢 Бот включен", "🔴 Бот выключен"}:
        cur = await get_enabled()
        await set_enabled(not cur)
        await admin_state_set(message.from_user.id, None)
        status = "🟢 Включил" if not cur else "🔴 Выключил"
        return await message.answer(f"{status}.", reply_markup=await kb_admin_main())

    # Cancel
    if txt_raw == "❌ Отмена" or txt in {"отмена", "/cancel"}:
        await admin_state_set(message.from_user.id, None)
        return await message.answer("Ок, отменено.", reply_markup=await kb_admin_main())

    # Stop broadcast
    if txt_raw == "⛔ Стоп рассылка" or txt in {"стоп рассылка", "stop"}:
        if await broadcast_is_running():
            BROADCAST_STOP = True
            return await message.answer("⛔ Останавливаю рассылку…", reply_markup=await kb_admin_main())
        return await message.answer("Сейчас рассылка не идёт.", reply_markup=await kb_admin_main())

    # Welcome menu
    if txt in {"📌 приветствие", "приветствие"}:
        await admin_state_set(message.from_user.id, None)
        return await show_welcome_panel(message)

    # Back
    if txt_raw == "⬅️ Назад" or txt in {"назад"}:
        await admin_state_set(message.from_user.id, None)
        return await show_admin_panel(message)

    # Stats
    if txt in {"📊 статистика", "статистика"}:
        await admin_state_set(message.from_user.id, None)
        total, blocked = await get_stats()
        enabled = await get_enabled()
        st = "🟢 Включен" if enabled else "🔴 Выключен"
        return await message.answer(
            f"📊 Статистика\n\n"
            f"Статус: <b>{st}</b>\n"
            f"Всего пользователей: <b>{total}</b>\n"
            f"Недоступны: <b>{blocked}</b>\n"
            f"Доступны: <b>{max(0, total - blocked)}</b>",
            reply_markup=await kb_admin_main(),
        )

    # Broadcast start
    if txt in {"📣 рассылка", "рассылка"}:
        if await broadcast_is_running():
            return await message.answer(
                "⏳ Рассылка уже идёт. Дождитесь завершения или нажмите ⛔ Стоп рассылка.",
                reply_markup=await kb_admin_main(),
            )
        await admin_state_set(message.from_user.id, "broadcast_wait_message")
        return await message.answer(
            "📣 Пришлите сообщение для рассылки:\n— текст\n— или фото/видео с подписью\n\nОтмена: ❌ Отмена",
            reply_markup=await kb_admin_main(),
        )

    # Welcome actions
    if txt_raw == "✏️ Текст приветствия":
        await admin_state_set(message.from_user.id, "welcome_wait_text")
        return await message.answer("Пришлите новый текст приветствия (можно HTML).", reply_markup=kb_welcome_menu())

    if txt_raw == "🖼/🎥 Медиа":
        await admin_state_set(message.from_user.id, "welcome_wait_media")
        return await message.answer("Пришлите ОДНО: фото или видео для приветствия.", reply_markup=kb_welcome_menu())

    if txt_raw == "🔘 Кнопка":
        await admin_state_set(message.from_user.id, "welcome_wait_button")
        return await message.answer(
            "Пришлите кнопку в формате:\n\n<b>Текст</b> | <b>https://ссылка</b>\n\nПример:\nПравила | https://t.me/yourchannel/123",
            reply_markup=kb_welcome_menu(),
        )

    if txt_raw == "🗑 Удалить медиа":
        await set_welcome_media(None, None)
        await admin_state_set(message.from_user.id, None)
        return await message.answer("✅ Медиа удалено.", reply_markup=kb_welcome_menu())

    if txt_raw == "👀 Предпросмотр":
        cfg = await get_welcome()
        await admin_state_set(message.from_user.id, None)
        await message.answer("Предпросмотр (как увидит пользователь):", reply_markup=kb_welcome_menu())
        try:
            await send_welcome(bot, message.from_user.id, cfg)
        except Exception:
            await message.answer("Не удалось отправить предпросмотр.")
        return

    # State machine
    state = await admin_state_get(message.from_user.id)
    if not state:
        return

    if state == "welcome_wait_text":
        text_value = (message.html_text or message.text or "").strip()
        if not text_value:
            return await message.answer("Текст пустой. Пришлите ещё раз или нажмите ❌ Отмена.")
        await set_welcome_text(text_value)
        await admin_state_set(message.from_user.id, None)
        return await message.answer("✅ Текст сохранён.", reply_markup=kb_welcome_menu())

    if state == "welcome_wait_button":
        raw = (message.text or "").strip()
        m = re.match(r"^(.*?)\s*\|\s*(https?://\S+)\s*$", raw)
        if not m:
            return await message.answer("Формат неверный. Пример:\nПравила | https://t.me/yourchannel/123")
        btn_text = m.group(1).strip()
        btn_url = m.group(2).strip()
        await set_welcome_button(btn_text, btn_url)
        await admin_state_set(message.from_user.id, None)
        return await message.answer("✅ Кнопка обновлена.", reply_markup=kb_welcome_menu())

    if state == "welcome_wait_media":
        if message.photo:
            file_id = message.photo[-1].file_id
            await set_welcome_media("photo", file_id)
            await admin_state_set(message.from_user.id, None)
            return await message.answer("✅ Фото сохранено.", reply_markup=kb_welcome_menu())
        if message.video:
            file_id = message.video.file_id
            await set_welcome_media("video", file_id)
            await admin_state_set(message.from_user.id, None)
            return await message.answer("✅ Видео сохранено.", reply_markup=kb_welcome_menu())
        return await message.answer("Нужно прислать фото или видео. Или нажмите ❌ Отмена.")

    if state == "broadcast_wait_message":
        if await broadcast_is_running():
            await admin_state_set(message.from_user.id, None)
            return await message.answer(
                "⏳ Рассылка уже идёт. Дождитесь завершения или нажмите ⛔ Стоп рассылка.",
                reply_markup=await kb_admin_main(),
            )

        targets_count = len(await get_broadcast_targets())
        if targets_count == 0:
            await admin_state_set(message.from_user.id, None)
            return await message.answer("Нет пользователей для рассылки.", reply_markup=await kb_admin_main())

        if message.photo:
            payload_type = "photo"
            payload_id = message.photo[-1].file_id
            payload_caption = message.html_text or message.caption or ""
        elif message.video:
            payload_type = "video"
            payload_id = message.video.file_id
            payload_caption = message.html_text or message.caption or ""
        else:
            payload_type = "text"
            payload_id = None
            payload_caption = message.html_text or message.text or ""

        await admin_state_set(message.from_user.id, None)
        await message.answer(
            f"✅ Принято. Запускаю рассылку в фоне.\nПользователей: {targets_count}\n(Бот продолжит работать)",
            reply_markup=await kb_admin_main(),
        )
        asyncio.create_task(run_broadcast(bot, message.from_user.id, payload_type, payload_id, payload_caption))
        return


# =========================
# MAIN
# =========================
async def main():
    logging.basicConfig(level=logging.INFO)

    await db_init()

    bot = Bot(
        BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()
    dp.errors.register(on_error)

    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_admin, Command("admin"))

    dp.chat_join_request.register(on_join_request)

    # Admin-only router (admins only)
    dp.message.register(admin_router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
