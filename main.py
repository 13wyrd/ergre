import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp
import subprocess
import random
import threading
import time

TOKEN = os.getenv('BOT_TOKEN')
if not TOKEN:
    print("Ошибка: не найден BOT_TOKEN")
    exit(1)

ADMIN_ID = 8153596056  # твой ID

bot = telebot.TeleBot(TOKEN)

# Хранилища
user_language = {}
active_urls = {}
users = set()
stats = {'downloads': 0, 'uniques': 0}
admin_state = {}
broadcast_control = {
    'running': False,
    'cancel': False,
    'progress_msg_id': None,
    'admin_chat_id': None,
    'total': 0,
    'sent': 0
}

# Тексты
texts = {
    'ru': {
        'welcome': "Привет! 👋\nЯ бот для скачивания видео из TikTok, Instagram Reels и YouTube Shorts.\nОтправь ссылку — я скачаю оригинал и спрошу, нужно ли уникализировать.\nУникализация: отзеркаливание + лёгкий шум (качество почти не теряется).\n⚠️ Используй только для своих видео или с разрешения автора!",
        'downloading': "📥 Скачиваю видео...",
        'downloaded': "✅ Видео скачано! Отправляю оригинал...",
        'original_caption': "Оригинальное видео (без изменений) 📹",
        'ask_unique': "Нужно уникализировать это видео?",
        'yes': "Да",
        'no': "Нет",
        'no_unique': "Ок, не уникализирую 🙂",
        'unique_processing': "🔄 Уникализирую видео (зеркало + лёгкий шум)...",
        'unique_caption': "Уникализированное видео 👌\n(отзеркаливание + лёгкий шум, качество сохранено)",
        'invalid': "Отправь ссылку на видео из TikTok, Reels или Shorts.",
        'error': "Ошибка: {error}\nВозможно, ссылка не поддерживается.",
        'admin_panel': "🔐 Админ-панель",
        'stats': "📊 Статистика:\n\n• Пользователей: {users}\n• Скачано видео: {downloads}\n• Уникализировано: {uniques}",
        'broadcast_start': "Отправьте сообщение для рассылки (текст, фото, видео и т.д.).\nДля отмены — /cancel",
        'broadcast_progress': "📢 Рассылка идёт...\nОтправлено: {sent} из {total}",
        'broadcast_cancel_btn': "❌ Отменить рассылку",
        'broadcast_cancelled': "Рассылка отменена.",
        'broadcast_sent': "✅ Рассылка завершена! Отправлено {sent} из {total} пользователям.",
        'not_admin': "Доступ запрещён.",
        'new_user': "Новый пользователь: {id} (@{username})"
    },
    'en': {
        'welcome': "Hi! 👋\nI'm a bot for downloading videos from TikTok, Instagram Reels, and YouTube Shorts.\nSend a link — I'll download the original and ask if you want to uniquify it.\nUniquification: mirroring + light noise (quality almost unchanged).\n⚠️ Use only for your own videos or with author's permission!",
        'downloading': "📥 Downloading video...",
        'downloaded': "✅ Video downloaded! Sending original...",
        'original_caption': "Original video (no changes) 📹",
        'ask_unique': "Do you want to uniquify this video?",
        'yes': "Yes",
        'no': "No",
        'no_unique': "Ok, won't uniquify 🙂",
        'unique_processing': "🔄 Uniquifying video (mirror + light noise)...",
        'unique_caption': "Uniquified video 👌\n(mirroring + light noise, quality preserved)",
        'invalid': "Send a link to a video from TikTok, Reels or Shorts.",
        'error': "Error: {error}\nPerhaps the link is not supported.",
        'admin_panel': "🔐 Admin Panel",
        'stats': "📊 Statistics:\n\n• Users: {users}\n• Videos downloaded: {downloads}\n• Videos uniquified: {uniques}",
        'broadcast_start': "Send the message to broadcast (text, photo, video, etc.).\nTo cancel — /cancel",
        'broadcast_progress': "📢 Broadcasting...\nSent: {sent} out of {total}",
        'broadcast_cancel_btn': "❌ Cancel broadcast",
        'broadcast_cancelled': "Broadcast cancelled.",
        'broadcast_sent': "✅ Broadcast completed! Sent to {sent} out of {total} users.",
        'not_admin': "Access denied.",
        'new_user': "New user: {id} (@{username})"
    }
}

def get_text(chat_id, key, **kwargs):
    lang = user_language.get(chat_id, 'ru')
    return texts[lang][key].format(**kwargs)

def add_user(chat_id, username=None):
    if chat_id not in users:
        users.add(chat_id)
        username = username or "без username"
        try:
            bot.send_message(ADMIN_ID, get_text(ADMIN_ID, 'new_user', id=chat_id, username=username))
        except:
            pass  # если админ заблокировал бота или ошибка

def download_video(url, output_path):
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': output_path.rsplit('.', 1)[0] + '.%(ext)s',
        'merge_output_format': 'mp4',
        'quiet': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        downloaded_file = ydl.prepare_filename(info)
        if downloaded_file != output_path:
            os.rename(downloaded_file, output_path)

def is_supported_url(url):
    return any(domain in url for domain in ['tiktok.com', 'instagram.com', 'youtube.com', 'youtu.be'])

# ====================== ОСНОВНЫЕ ХЕНДЛЕРЫ ======================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    add_user(chat_id, message.from_user.username)
    
    if chat_id in user_language:
        bot.reply_to(message, get_text(chat_id, 'welcome'))
    else:
        markup = InlineKeyboardMarkup()
        markup.row_width = 2
        markup.add(
            InlineKeyboardButton("Русский 🇷🇺", callback_data=f"lang_ru_{chat_id}"),
            InlineKeyboardButton("English 🇬🇧", callback_data=f"lang_en_{chat_id}")
        )
        bot.reply_to(message, "Выберите язык / Choose language:", reply_markup=markup)

@bot.message_handler(func=lambda m: is_supported_url(m.text or ''))
def handle_url(message):
    url = message.text.strip()
    chat_id = message.chat.id
    add_user(chat_id, message.from_user.username)

    active_urls.pop(chat_id, None)

    status_msg = bot.reply_to(message, get_text(chat_id, 'downloading'))

    input_path = f"temp_input_{chat_id}.mp4"

    try:
        download_video(url, input_path)
        stats['downloads'] += 1

        bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id,
                              text=get_text(chat_id, 'downloaded'))

        with open(input_path, 'rb') as video:
            sent_video_msg = bot.send_video(chat_id, video, caption=get_text(chat_id, 'original_caption'))

        os.remove(input_path)
        active_urls[chat_id] = url

        markup = InlineKeyboardMarkup()
        markup.row_width = 2
        markup.add(
            InlineKeyboardButton(get_text(chat_id, 'yes'), callback_data=f"unique_yes_{chat_id}"),
            InlineKeyboardButton(get_text(chat_id, 'no'), callback_data=f"unique_no_{chat_id}")
        )

        bot.send_message(chat_id, get_text(chat_id, 'ask_unique'), reply_markup=markup,
                         reply_to_message_id=sent_video_msg.message_id)

    except Exception as e:
        bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id,
                              text=get_text(chat_id, 'error', error=str(e)))
        if os.path.exists(input_path):
            os.remove(input_path)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    chat_id = call.message.chat.id
    data = call.data
    add_user(chat_id, call.from_user.username)

    if data.startswith('lang_'):
        parts = data.split('_')
        if len(parts) == 3:
            lang = parts[1]
            user_language[chat_id] = lang
            bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                                  text="✅ Язык выбран / Language selected")
            bot.send_message(chat_id, get_text(chat_id, 'welcome'))
            bot.answer_callback_query(call.id)
        return

    if data.startswith('admin_'):
        return

    if data == f"unique_no_{chat_id}":
        if chat_id not in active_urls:
            bot.answer_callback_query(call.id, "Сессия устарела.")
            return
        bot.answer_callback_query(call.id, get_text(chat_id, 'no_unique'))
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                              text=get_text(chat_id, 'no_unique'))
        active_urls.pop(chat_id, None)

    elif data == f"unique_yes_{chat_id}":
        url = active_urls.pop(chat_id, None)
        if not url:
            bot.answer_callback_query(call.id, "Сессия устарела.")
            return

        bot.answer_callback_query(call.id, "Уникализирую...")
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                              text=get_text(chat_id, 'unique_processing'))

        output_path = f"temp_output_{chat_id}.mp4"

        try:
            download_video(url, output_path)
            stats['uniques'] += 1

            flip = 'hflip,' if random.random() < 0.7 else ''
            noise_strength = random.randint(1, 5)
            vf_filters = f"{flip}noise=alls={noise_strength}:allf=t+u"

            cmd = [
                'ffmpeg', '-y', '-i', output_path,
                '-vf', vf_filters,
                '-c:v', 'libx264', '-crf', '18', '-preset', 'medium',
                '-c:a', 'copy',
                output_path
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            with open(output_path, 'rb') as video:
                bot.send_video(chat_id, video, caption=get_text(chat_id, 'unique_caption'))

            os.remove(output_path)

        except Exception as e:
            bot.send_message(chat_id, f"Ошибка уникализации: {str(e)}")
            if os.path.exists(output_path):
                os.remove(output_path)

    # Отмена рассылки
    elif data == "cancel_broadcast":
        if broadcast_control['running'] and chat_id == ADMIN_ID:
            broadcast_control['cancel'] = True
            bot.answer_callback_query(call.id, "Рассылка отменяется...")

# ====================== АДМИН-ПАНЕЛЬ ======================

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    chat_id = message.chat.id
    if chat_id != ADMIN_ID:
        bot.reply_to(message, get_text(chat_id, 'not_admin'))
        return

    markup = InlineKeyboardMarkup()
    markup.row_width = 1
    markup.add(
        InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
        InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")
    )
    bot.send_message(chat_id, get_text(chat_id, 'admin_panel'), reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
def admin_callback(call):
    chat_id = call.message.chat.id
    if chat_id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Доступ запрещён")
        return

    if call.data == "admin_stats":
        text = get_text(chat_id, 'stats',
                        users=len(users),
                        downloads=stats['downloads'],
                        uniques=stats['uniques'])
        bot.answer_callback_query(call.id)
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=text)

    elif call.data == "admin_broadcast":
        bot.answer_callback_query(call.id)
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                              text=get_text(chat_id, 'broadcast_start'))
        admin_state[chat_id] = 'waiting_broadcast'

# Рассылка — обработка сообщения
@bot.message_handler(func=lambda m: admin_state.get(m.chat.id) == 'waiting_broadcast')
def handle_broadcast_message(message):
    chat_id = message.chat.id
    if chat_id != ADMIN_ID:
        return

    if message.text and '/cancel' in message.text.lower():
        admin_state.pop(chat_id, None)
        bot.reply_to(message, get_text(chat_id, 'broadcast_cancelled'))
        return

    admin_state.pop(chat_id, None)

    # Запуск рассылки в отдельном потоке
    def broadcast_thread(original_message):
        global broadcast_control
        broadcast_control = {
            'running': True,
            'cancel': False,
            'admin_chat_id': chat_id,
            'total': len(users),
            'sent': 0
        }

        progress_msg = bot.send_message(chat_id, get_text(chat_id, 'broadcast_progress', sent=0, total=broadcast_control['total']),
                                        reply_markup=InlineKeyboardMarkup().add(
                                            InlineKeyboardButton(get_text(chat_id, 'broadcast_cancel_btn'), callback_data="cancel_broadcast")
                                        ))
        broadcast_control['progress_msg_id'] = progress_msg.message_id

        for user_id in list(users):
            if broadcast_control['cancel']:
                break
            try:
                bot.copy_message(user_id, chat_id, original_message.message_id)
                broadcast_control['sent'] += 1
            except:
                pass  # пользователь заблокировал бота

            # Обновление прогресса каждые 5 отправок
            if broadcast_control['sent'] % 5 == 0 or broadcast_control['sent'] == broadcast_control['total']:
                try:
                    bot.edit_message_text(chat_id=chat_id, message_id=progress_msg.message_id,
                                          text=get_text(chat_id, 'broadcast_progress', sent=broadcast_control['sent'], total=broadcast_control['total']),
                                          reply_markup=InlineKeyboardMarkup().add(
                                              InlineKeyboardButton(get_text(chat_id, 'broadcast_cancel_btn'), callback_data="cancel_broadcast")
                                          ) if not broadcast_control['cancel'] else None)
                except:
                    pass

            time.sleep(0.05)  # защита от rate limit

        final_text = get_text(chat_id, 'broadcast_sent' if not broadcast_control['cancel'] else 'broadcast_cancelled',
                              sent=broadcast_control['sent'], total=broadcast_control['total'])
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=progress_msg.message_id, text=final_text)
        except:
            bot.send_message(chat_id, final_text)

        broadcast_control['running'] = False

    threading.Thread(target=broadcast_thread, args=(message,)).start()
    bot.reply_to(message, "Рассылка запущена... Следите за прогрессом выше.")

# Команда отмены (на всякий случай)
@bot.message_handler(commands=['cancel'])
def cancel_broadcast_cmd(message):
    if message.chat.id == ADMIN_ID and broadcast_control['running']:
        broadcast_control['cancel'] = True
        bot.reply_to(message, "Рассылка отменяется...")

# ====================== ОСТАЛЬНОЕ ======================

@bot.message_handler(func=lambda message: True)
def other_messages(message):
    chat_id = message.chat.id
    add_user(chat_id, message.from_user.username)
    bot.reply_to(message, get_text(chat_id, 'invalid'))

print("Бот запущен...")
bot.infinity_polling()