import json
import os
import time
import threading

from config import STATE_FILE, DATA_DIR

os.makedirs(DATA_DIR, exist_ok=True)

_lock = threading.Lock()

state = {
    "users": {},
    "stats": {"downloads": 0, "uniques": 0, "blocked": 0},
}


def load_state():
    global state
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            pass

    with _lock:
        state.setdefault("users", {})
        state.setdefault("stats", {})
        state["stats"].setdefault("downloads", 0)
        state["stats"].setdefault("uniques", 0)
        state["stats"].setdefault("blocked", 0)
        save_state()


def save_state():
    tmp = STATE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE_FILE)
    except Exception:
        pass


def add_or_update_user(chat_id: int, username: str | None, default_lang: str = "ru") -> bool:
    """Возвращает True, если пользователь новый."""
    username = username or "no_username"
    now = int(time.time())
    is_new = False

    with _lock:
        u = state["users"].get(str(chat_id))
        if not u:
            state["users"][str(chat_id)] = {
                "username": username,
                "lang": default_lang,
                "first_seen": now,
                "last_seen": now,
            }
            is_new = True
        else:
            u["username"] = username
            u["last_seen"] = now
        save_state()

    return is_new


def set_lang(chat_id: int, lang: str):
    with _lock:
        u = state["users"].get(str(chat_id))
        if u:
            u["lang"] = lang
            u["last_seen"] = int(time.time())
            save_state()


def get_lang(chat_id: int) -> str:
    with _lock:
        u = state["users"].get(str(chat_id))
        return (u or {}).get("lang", "ru")


def inc_stat(key: str, amount: int = 1):
    with _lock:
        state["stats"][key] = int(state["stats"].get(key, 0)) + amount
        save_state()


def get_stats_snapshot():
    with _lock:
        users_count = len(state["users"])
        stats = dict(state["stats"])
    return users_count, stats


def list_user_ids():
    with _lock:
        return [int(uid) for uid in state["users"].keys() if uid.isdigit()]


def remove_user(chat_id: int):
    with _lock:
        state["users"].pop(str(chat_id), None)
        save_state()


def count_active(seconds: int) -> int:
    now = int(time.time())
    with _lock:
        cnt = 0
        for u in state["users"].values():
            last = int(u.get("last_seen", 0) or 0)
            if last and (now - last) <= seconds:
                cnt += 1
        return cnt
