import os
from queue import Queue

import telebot

import storage
from config import TOKEN, ADMIN_ID, TEMP_DIR
import utils
import admin as admin_mod
from workers import start_workers
from media import download_video, make_unique

os.makedirs(TEMP_DIR, exist_ok=True)

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
task_queue: "Queue[dict]" = Queue()

storage.load_state()
utils.start_temp_cleaner()
start_workers(bot, task_queue)


def add_user_and_notify(message_or_call):
    chat_id = message_or_call.chat.id
    username = getattr(message_or_call.from_user, "username", None)
    is_new = storage.add_or_update_user(chat_id, username, default_lang="ru")
    if is_new:
        try:
            bot.send_message(ADMIN_ID, utils.t(ADMIN_ID, "new_user", id=chat_id, username=(username or "no_username")))
        except Exception:
            pass


@bot.message_handler(commands=["start"])
def cmd_start(message):
    add_user_and_notify(message)
    chat_id = message.chat.id

    if utils.is_admin(chat_id):
        bot.send_message(chat_id, utils.t(chat_id, "welcome_menu"), reply_markup=utils.main_menu_markup(chat_id))
        return

    # обычным — выбор языка
    bot.send_message(chat_id, utils.t(chat_id, "choose_lang"), reply_markup=utils.lang_markup())


@bot.message_handler(commands=["admin"])
def cmd_admin(message):
    add_user_and_notify(message)
    chat_id = message.chat.id

    if not utils.is_admin(chat_id):
        bot.send_message(chat_id, utils.t(chat_id, "not_admin"))
        return

    bot.send_message(chat_id, utils.t(chat_id, "admin_panel"), reply_markup=utils.admin_markup(chat_id, broadcast_running=admin_mod.broadcast_control["running"]))


@bot.message_handler(commands=["cancel"])
def cmd_cancel(message):
    chat_id = message.chat.id
    if utils.is_admin(chat_id) and admin_mod.admin_state.get(chat_id) == "await_broadcast":
        admin_mod.admin_state.pop(chat_id, None)
        bot.send_message(chat_id, utils.t(chat_id, "broadcast_cancelled"))
        return
    bot.send_message(chat_id, "OK.")


@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    # last_seen обновляем
    storage.add_or_update_user(call.message.chat.id, call.from_user.username, default_lang="ru")

    chat_id = call.message.chat.id
    data = call.data or ""

    # выбор языка (обычным)
    if data.startswith("lang|") and not utils.is_admin(chat_id):
        lang = data.split("|", 1)[1]
        if lang in ("ru", "en"):
            storage.set_lang(chat_id, lang)
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, utils.t(chat_id, "welcome_menu"), reply_markup=utils.main_menu_markup(chat_id))
        return

    # меню
    if data.startswith("menu|"):
        action = data.split("|", 1)[1]
        bot.answer_callback_query(call.id)
        if action == "download":
            utils.user_mode[chat_id] = "download"
            bot.send_message(chat_id, utils.t(chat_id, "send_link_download"))
        elif action == "unique":
            utils.user_mode[chat_id] = "unique"
            bot.send_message(chat_id, utils.t(chat_id, "send_link_unique"))
        return

    # админка
    if data.startswith("admin|"):
        if not utils.is_admin(chat_id):
            bot.answer_callback_query(call.id, utils.t(chat_id, "not_admin"))
            return

        action = data.split("|", 1)[1]
        bot.answer_callback_query(call.id)

        if action == "stats":
            users_count, stats = storage.get_stats_snapshot()
            active_24h = storage.count_active(24 * 3600)
            active_7d = storage.count_active(7 * 24 * 3600)
            active_30d = storage.count_active(30 * 24 * 3600)

            bot.send_message(
                chat_id,
                utils.t(
                    chat_id, "stats",
                    users=users_count,
                    active_24h=active_24h,
                    active_7d=active_7d,
                    active_30d=active_30d,
                    downloads=stats.get("downloads", 0),
                    uniques=stats.get("uniques", 0),
                    blocked=stats.get("blocked", 0),
                ),
                reply_markup=utils.admin_markup(chat_id, broadcast_running=admin_mod.broadcast_control["running"]),
            )
            return

        if action == "broadcast":
            admin_mod.admin_state[chat_id] = "await_broadcast"
            bot.send_message(chat_id, utils.t(chat_id, "broadcast_start"))
            return

        if action == "cancel_broadcast":
            if admin_mod.broadcast_control["running"]:
                admin_mod.broadcast_control["cancel"] = True
                bot.send_message(chat_id, utils.t(chat_id, "broadcast_cancelled"))
            return

        return

    # "Уникализировать?" после отправки оригинала
    if data.startswith(("postuniq_yes|", "postuniq_no|")):
        action, token = data.split("|", 1)
        bot.answer_callback_query(call.id)

        sess = utils.sessions.get(chat_id)
        if not sess or sess.get("token") != token:
            bot.send_message(chat_id, utils.t(chat_id, "session_expired"))
            utils.sessions.pop(chat_id, None)
            return

        if action == "postuniq_no":
            utils.sessions.pop(chat_id, None)
            return

        # YES: скачать заново -> уник -> отправить -> удалить
        url = sess["url"]
        utils.sessions.pop(chat_id, None)

        # антиспам
        with utils.busy_lock:
            if chat_id in utils.user_busy:
                bot.send_message(chat_id, utils.t(chat_id, "busy"))
                return
            utils.user_busy.add(chat_id)

        status = utils.safe_send_message(bot, chat_id, utils.t(chat_id, "unique_processing"))
        in_path = os.path.join(TEMP_DIR, f"in_{chat_id}_{os.urandom(4).hex()}.mp4")
        out_path = os.path.join(TEMP_DIR, f"out_{chat_id}_{os.urandom(4).hex()}.mp4")

        try:
            utils.cleanup_temp_dir()
            download_video(url, in_path)
            make_unique(in_path, out_path)
            storage.inc_stat("uniques", 1)

            if status:
                try:
                    bot.edit_message_text(chat_id=chat_id, message_id=status.message_id, text=utils.t(chat_id, "done"))
                except Exception:
                    pass

            with open(out_path, "rb") as f:
                bot.send_video(chat_id, f, caption=utils.t(chat_id, "unique_caption"))

        except Exception:
            bot.send_message(chat_id, utils.t(chat_id, "unique_error"))

        finally:
            for p in (in_path, out_path):
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
            with utils.busy_lock:
                utils.user_busy.discard(chat_id)

        return

    bot.answer_callback_query(call.id)


@bot.message_handler(func=lambda m: utils.is_supported_url(m.text or ""))
def handle_url(message):
    add_user_and_notify(message)
    chat_id = message.chat.id

    mode = utils.user_mode.get(chat_id)
    if mode is None:
        bot.send_message(chat_id, utils.t(chat_id, "welcome_menu"), reply_markup=utils.main_menu_markup(chat_id))
        return

    # антиспам
    with utils.busy_lock:
        if chat_id in utils.user_busy:
            bot.send_message(chat_id, utils.t(chat_id, "busy"))
            return
        utils.user_busy.add(chat_id)

    status = bot.reply_to(message, utils.t(chat_id, "downloading"))
    task_queue.put({
        "type": "download_flow",
        "chat_id": chat_id,
        "url": (message.text or "").strip(),
        "status_msg_id": status.message_id,
        "mode": mode,
    })


@bot.message_handler(func=lambda m: True, content_types=["text"])
def fallback_text(message):
    add_user_and_notify(message)
    chat_id = message.chat.id

    # ввод текста рассылки
    if utils.is_admin(chat_id) and admin_mod.admin_state.get(chat_id) == "await_broadcast":
        admin_mod.admin_state.pop(chat_id, None)
        admin_mod.start_broadcast(bot, chat_id, message.text or "")
        return

    if not utils.is_supported_url(message.text or ""):
        bot.send_message(chat_id, utils.t(chat_id, "invalid"))


print("Бот запущен...")
bot.infinity_polling(skip_pending=True)
