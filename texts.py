TEXTS = {
    "ru": {
        "choose_lang": "Выберите язык / Choose language:",
        "lang_ru": "🇷🇺 Русский",
        "lang_en": "🇬🇧 English",

        "welcome_menu": "Привет! 👋\nЯ бот, который умеет скачивать и уникализировать видео.\n\nВыбери действие кнопками ниже:",
        "btn_menu_download": "Скачать видео",
        "btn_menu_unique": "Уникализатор",
        "send_link_download": "Пришли ссылку на видео (TikTok / Reels / Shorts) — я скачаю и отправлю оригинал.",
        "send_link_unique": "Пришли ссылку на видео (TikTok / Reels / Shorts) — я скачаю и отправлю уникализированное.",

        "invalid": "Отправь ссылку на видео из TikTok, Reels или Shorts.",
        "busy": "⏳ Подожди, я уже обрабатываю твой запрос. Пришли ссылку чуть позже.",

        "downloading": "📥 Скачиваю видео...",
        "done": "✅ Готово!",
        "original_caption": "Оригинальное видео (без изменений) 📹",

        "ask_unique": "Нужно уникализировать это видео?",
        "btn_yes": "✅ Да",
        "btn_no": "❌ Нет",

        "unique_processing": "🔄 Уникализирую (кроп/цвет/шум/fps + лёгкое аудио)...",
        "unique_caption": "Уникализированное видео 👌",
        "unique_error": "Ошибка уникализации: ffmpeg недоступен или произошла другая ошибка.",
        "session_expired": "Сессия устарела. Пришли ссылку заново.",

        "error": "Ошибка: {error}",

        # Админка всегда на русском
        "admin_panel": "🔐 Админ-панель",
        "not_admin": "Доступ запрещён.",
        "admin_btn_stats": "📊 Статистика",
        "admin_btn_broadcast": "📢 Рассылка",
        "admin_btn_cancel": "❌ Отменить",

        "stats": (
            "📊 Статистика:\n"
            "• Пользователей: {users}\n"
            "• Активные 24ч: {active_24h}\n"
            "• Активные 7д: {active_7d}\n"
            "• Активные 30д: {active_30d}\n"
            "• Скачано: {downloads}\n"
            "• Уникализировано: {uniques}\n"
            "• Заблокировали: {blocked}"
        ),
        "new_user": "👤 Новый пользователь: <code>{id}</code> (@{username})",

        "broadcast_start": "Отправьте сообщение для рассылки.\n/cancel — отменить",
        "broadcast_progress": "📢 Рассылка...\nОтправлено: {sent} из {total}",
        "broadcast_cancelled": "Рассылка отменена.",
        "broadcast_sent": "✅ Рассылка завершена! Отправлено {sent} из {total}.",
        "broadcast_no_users": "Нет пользователей для рассылки.",
        "broadcast_already": "Рассылка уже идёт.",
    },

    "en": {
        "choose_lang": "Choose language / Выберите язык:",
        "lang_ru": "🇷🇺 Русский",
        "lang_en": "🇬🇧 English",

        "welcome_menu": "Hi! 👋\nI can download and make videos unique.\n\nChoose an action below:",
        "btn_menu_download": "Download video",
        "btn_menu_unique": "Unique tool",
        "send_link_download": "Send a video link (TikTok / Reels / Shorts) — I’ll download and send the original.",
        "send_link_unique": "Send a video link (TikTok / Reels / Shorts) — I’ll download and send the unique version.",

        "invalid": "Send a TikTok / Reels / Shorts link.",
        "busy": "⏳ Please wait, I’m already processing your request. Try again in a moment.",

        "downloading": "📥 Downloading...",
        "done": "✅ Done!",
        "original_caption": "Original video (no changes) 📹",

        "ask_unique": "Make it unique?",
        "btn_yes": "✅ Yes",
        "btn_no": "❌ No",

        "unique_processing": "🔄 Making unique...",
        "unique_caption": "Unique video 👌",
        "unique_error": "Unique processing failed: ffmpeg missing or another error.",
        "session_expired": "Session expired. Send the link again.",

        "error": "Error: {error}",
    },
}
