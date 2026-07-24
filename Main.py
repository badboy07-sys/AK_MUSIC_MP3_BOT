import os
import telebot
import yt_dlp
import threading
import json
import tempfile
from youtubesearchpython import VideosSearch
from flask import Flask
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = 6670168751

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

users_file = 'users.json'
queue_file = 'queue.json'

if not os.path.exists(users_file):
    with open(users_file, 'w') as f:
        json.dump({"users": []}, f)

if not os.path.exists(queue_file):
    with open(queue_file, 'w') as f:
        json.dump({}, f)

def load_users():
    with open(users_file, 'r') as f:
        return json.load(f)

def save_users(data):
    with open(users_file, 'w') as f:
        json.dump(data, f)

def load_queue():
    with open(queue_file, 'r') as f:
        return json.load(f)

def save_queue(data):
    with open(queue_file, 'w') as f:
        json.dump(data, f)

def track_user(user_id):
    data = load_users()
    if user_id not in data["users"]:
        data["users"].append(user_id)
        save_users(data)

user_queue = {}
current_song = {}
search_results = {}

def get_queue(chat_id):
    chat_id = str(chat_id)
    if chat_id not in user_queue:
        user_queue[chat_id] = []
        saved = load_queue()
        if chat_id in saved:
            user_queue[chat_id] = saved[chat_id]
    return user_queue[chat_id]

def save_all_queue():
    saved = {}
    for chat_id, q in user_queue.items():
        if q:
            saved[chat_id] = q
    save_queue(saved)

def download_and_send(chat_id, url, title):
    try:
        bot.send_message(chat_id, f"🎵 Downloading: {title}")
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(tempfile.gettempdir(), '%(title)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'noplaylist': True,
            'quiet': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info).replace('.webm', '.mp3').replace('.m4a', '.mp3')
        with open(filename, 'rb') as audio:
            bot.send_audio(chat_id, audio, title=title)
        os.remove(filename)
        bot.send_message(chat_id, "✅ Ho gaya!")
        play_next(chat_id)
    except:
        bot.send_message(chat_id, "❌ Download error")
        play_next(chat_id)

def play_next(chat_id):
    q = get_queue(chat_id)
    if q:
        song = q.pop(0)
        save_all_queue()
        download_and_send(chat_id, song['url'], song['title'])
        current_song[str(chat_id)] = song
    else:
        current_song[str(chat_id)] = None
        save_all_queue()

@bot.message_handler(commands=['start'])
def start(m):
    track_user(m.from_user.id)
    name = m.from_user.first_name
    username = "@" + m.from_user.username if m.from_user.username else "Username nahi hai"
    user_id = m.from_user.id
    msg = f"""🎵 AK_X_MUSIC_BOT PRO 🎵

Swagat hai {name}!

Name: {name}
Username: {username}

Commands:
Gaane ka naam - 10 Results
YT Link - Direct MP3
/queue - Queue dekho
/stop - Roko
/next - Agla gaana"""
    bot.reply_to(m, msg)
    if m.from_user.id!= ADMIN_ID:
        admin_msg = f"""🔔 New User Started Bot

Name: {name}
Username: {username}
User ID: `{user_id}`"""
        bot.send_message(ADMIN_ID, admin_msg)

@bot.message_handler(commands=['queue'])
def show_queue(m):
    q = get_queue(m.chat.id)
    if not q:
        bot.reply_to(m, "Queue khali hai")
    else:
        txt = f"Queue me {len(q)} gaane hai\n"
        for i,s in enumerate(q[:5]):
            txt += f"{i+1}. {s['title']}\n"
        bot.reply_to(m, txt)

@bot.message_handler(commands=['stop'])
def stop_song(m):
    current_song[str(m.chat.id)] = None
    user_queue[str(m.chat.id)] = []
    save_all_queue()
    bot.reply_to(m, "⏹️ Ruk gaya")

@bot.message_handler(commands=['next'])
def next_song(m):
    play_next(m.chat.id)

@bot.message_handler(func=lambda message: True)
def handle_msg(m):
    text = m.text
    if 'youtube.com' in text or 'youtu.be' in text:
        url = text
        search = VideosSearch(url, limit=1)
        result = search.result()['result'][0]
        q = get_queue(m.chat.id)
        q.append({'url': url, 'title': result['title']})
        save_all_queue()
        bot.reply_to(m, f"➕ Queue me add: {result['title']}")
        if current_song.get(str(m.chat.id)) is None:
            play_next(m.chat.id)
    else:
        search = VideosSearch(text, limit=10)
        results = search.result()['result']
        search_results[m.chat.id] = results
        msg = f"✅ 10 gaane\nPehla: {results[0]['title']}"
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("▶️ Play", callback_data=f"play_0"))
        markup.row(InlineKeyboardButton("💾 Save Playlist", callback_data="save"))
        markup.row(
            InlineKeyboardButton("⏮️ Back", callback_data="back"),
            InlineKeyboardButton("⏹️ Stop", callback_data="stop"),
            InlineKeyboardButton("⏭️ Next", callback_data="next")
        )
        bot.send_message(m.chat.id, msg, reply_markup=markup)
        admin_msg = f"""🔔 Activity
User: {m.from_user.first_name}
ID: {m.from_user.id}
Search: {text}"""
        bot.send_message(ADMIN_ID, admin_msg)

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    chat_id = call.message.chat.id
    if call.data.startswith("play_"):
        index = int(call.data.split("_")[1])
        song = search_results[chat_id][index]
        q = get_queue(chat_id)
        q.append({'url': song['link'], 'title': song['title']})
        save_all_queue()
        bot.answer_callback_query(call.id, f"Added: {song['title']}")
        if current_song.get(str(chat_id)) is None:
            play_next(chat_id)
    elif call.data == "next":
        play_next(chat_id)
    elif call.data == "stop":
        stop_song(call.message)

@app.route('/')
def home():
    return "AK_X_MUSIC_BOT is Alive!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

if __name__ == '__main__':
    threading.Thread(target=run_flask).start()
    bot.infinity_polling()
