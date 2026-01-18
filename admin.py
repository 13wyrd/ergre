import threading
import time

import storage
from config import BROADCAST_SLEEP
from utils import t, admin_markup, safe_edit_message

broadcast_control = {
    "running": False,
    "cancel": False,
    "progress_msg_id": None,
    "admin_chat_id": None,
    "total": 0,
    "sent": 0,
}

admin_state = {}  # admin_id -> "await_broadcast"


def start_broadcast(bot, admin_chat_id: int, text: str):
    user_ids = storage.list_user_ids()
    if not user_ids:
        bot.send_message(admin_chat_id, t(admin_chat_id, "broadcast_no_users"))
        return

    if broadcast_control["running"]:
        bot.send_message(admin_chat_id, t(admin_chat_id, "broadcast_already"))
        return

    broadcast_control.update({
        "running": True,
        "cancel": False,
        "admin_chat_id": admin_chat_id,
        "total": len(user_ids),
        "sent": 0,
    })

    progress = bot.send_message(
        admin_chat_id,
        t(admin_chat_id, "broadcast_progress", sent=0, total=len(user_ids)),
        reply_markup=admin_markup(admin_chat_id, broadcast_running=True),
    )
    broadcast_control["progress_msg_id"] = progress.message_id

    def run():
        sent = 0
        total = len(user_ids)

        for uid in user_ids:
            if broadcast_control["cancel"]:
                break

            try:
                bot.send_message(uid, text)
                sent += 1
            except Exception as e:
                msg = str(e).lower()
                is_block = ("403" in msg) or ("blocked by the user" in msg) or ("user is deactivated" in msg)
                if is_block:
                    storage.inc_stat("blocked", 1)
                    storage.remove_user(uid)

            broadcast_control["sent"] = sent

            if sent % 10 == 0:
                safe_edit_message(
                    bot,
                    admin_chat_id,
                    broadcast_control["progress_msg_id"],
                    t(admin_chat_id, "broadcast_progress", sent=sent, total=total),
                    reply_markup=admin_markup(admin_chat_id, broadcast_running=True),
                )

            time.sleep(BROADCAST_SLEEP)

        if broadcast_control["cancel"]:
            safe_edit_message(
                bot,
                admin_chat_id,
                broadcast_control["progress_msg_id"],
                t(admin_chat_id, "broadcast_cancelled"),
                reply_markup=admin_markup(admin_chat_id, broadcast_running=False),
            )
        else:
            safe_edit_message(
                bot,
                admin_chat_id,
                broadcast_control["progress_msg_id"],
                t(admin_chat_id, "broadcast_sent", sent=sent, total=total),
                reply_markup=admin_markup(admin_chat_id, broadcast_running=False),
            )

        broadcast_control["running"] = False
        broadcast_control["cancel"] = False

    threading.Thread(target=run, daemon=True).start()
