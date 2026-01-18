import os
import time
import threading
from uuid import uuid4
from queue import Empty

import storage
from config import TEMP_DIR, MAX_QUEUE_WORKERS
from utils import (
    sessions, user_busy, busy_lock,
    t, safe_send_message, safe_edit_message,
    ask_unique_markup, cleanup_temp_dir, expire_sessions,
)
from media import download_video, make_unique


def worker_loop(bot, task_queue):
    while True:
        try:
            task = task_queue.get(timeout=1)
        except Empty:
            expire_sessions()
            continue

        chat_id = task.get("chat_id")

        try:
            cleanup_temp_dir()

            if task.get("type") == "download_flow":
                url = task["url"]
                status_msg_id = task["status_msg_id"]
                mode = task.get("mode", "download")  # download | unique

                temp_in = os.path.join(TEMP_DIR, f"in_{chat_id}_{uuid4().hex[:8]}.mp4")
                temp_out = os.path.join(TEMP_DIR, f"out_{chat_id}_{uuid4().hex[:8]}.mp4")

                try:
                    download_video(url, temp_in)
                    storage.inc_stat("downloads", 1)

                    if mode == "unique":
                        safe_edit_message(bot, chat_id, status_msg_id, t(chat_id, "unique_processing"))
                        make_unique(temp_in, temp_out)
                        storage.inc_stat("uniques", 1)

                        safe_edit_message(bot, chat_id, status_msg_id, t(chat_id, "done"))
                        with open(temp_out, "rb") as f:
                            bot.send_video(chat_id, f, caption=t(chat_id, "unique_caption"))
                        return

                    # mode == download
                    safe_edit_message(bot, chat_id, status_msg_id, t(chat_id, "done"))
                    with open(temp_in, "rb") as f:
                        bot.send_video(chat_id, f, caption=t(chat_id, "original_caption"))

                    # для "Да" — храним только URL
                    token = uuid4().hex[:10]
                    sessions[chat_id] = {"url": url, "token": token, "created": time.time()}
                    safe_send_message(bot, chat_id, t(chat_id, "ask_unique"), reply_markup=ask_unique_markup(chat_id, token))

                except Exception as e:
                    safe_edit_message(bot, chat_id, status_msg_id, t(chat_id, "error", error=str(e)))

                finally:
                    # всегда удаляем файлы
                    for p in (temp_in, temp_out):
                        if os.path.exists(p):
                            try:
                                os.remove(p)
                            except Exception:
                                pass

        finally:
            # освобождаем busy
            if chat_id is not None:
                with busy_lock:
                    user_busy.discard(chat_id)
            task_queue.task_done()


def start_workers(bot, task_queue):
    os.makedirs(TEMP_DIR, exist_ok=True)
    for _ in range(MAX_QUEUE_WORKERS):
        threading.Thread(target=worker_loop, args=(bot, task_queue), daemon=True).start()
