import os
import yt_dlp
from replit import db
from datetime import datetime
from telebot import TeleBot, types
from youtube_search import YoutubeSearch
import requests
from flask import Flask
from threading import Thread

app = Flask('')
@app.route('/')
def home():
    return "AK_X_MUSIC_BOT is Alive!"
def run():
    app.run(host='0.0.0.0', port=8080)
def keep_alive():
    t = Thread(target=run)
    t.start()

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6670168751
bot = TeleBot(TOKEN)

def get_banned(): return db.get("banned", [])
def ban_user(uid):
    arr = get_banned()
    if uid not in arr: arr.append(uid); db["banned"] = arr
def unban_user(uid):
    arr = get_banned()
    if uid in arr: arr.remove(uid); db["banned"] = arr
def get_favs(uid): return db.get(f"fav_{uid}", [])
def add_fav(uid, item):
    arr = get_favs(uid)
    if item not in arr: arr.append(item); db[f"fav_{uid}"] = arr
def get_queue(uid): return db.get(f"queue_{uid}", [])
def set_queue(uid, q): db[f"queue_{uid}"] = q
def get_current(uid): return db.get(f"current_{uid}", 0)
def set_current(uid, i): db[f"current_{uid}"] = i
def get_playlist(uid): return db.get(f"playlist_{uid}", [])
def add_playlist(uid, item):
    arr = get_playlist(uid)
    if item not in arr: arr.append(item); db[f"playlist_{uid}"] = arr

def track_user(uid):
    today = datetime.now().strftime("%Y-%m-%d")
    month = datetime.now().strftime("%Y-%m")
    users = db.get("users", [])
    if uid not in users: users.append(uid); db["users"] = users
    monthly = db.get(f"monthly_{month}", [])
    if uid not in monthly: monthly.append(uid); db[f"monthly_{month}"] = monthly
    daily = db.get(f"daily_{today}", [])
    if uid not in daily: daily.append(uid); db[f"daily_{today}"] = daily

MOODS = {
    'sad': 'sad hindi songs', 'happy': 'happy songs', 'romantic': 'romantic songs',
    'party': 'party dance songs', 'chill': 'chill songs', 'angry': 'angry songs',
    'old': '90s hindi songs', '90s': '90s hindi songs', '2000s': '2000s hindi songs',
    'new': 'new hindi songs 2026', 'bhajan': 'hanuman bhajan', 'ghazal': 'ghazal',
    'rap': 'hindi rap songs', 'lofi': 'lofi hindi songs', 'bgm': 'movie bgm',
    'remix': 'hindi remix songs', 'hindi': 'hindi songs 2026', 'punjabi': 'punjabi songs 2026',
    'bengali': 'bengali songs 2026', 'bangla': 'bangla songs 2026',
    'tamil': 'tamil songs 2026', 'telugu': 'telugu songs 2026',
    'marathi': 'marathi songs 2026', 'gujarati': 'gujarati songs 2026',
    'kannada': 'kannada songs 2026', 'malayalam': 'malayalam songs 2026',
    'bhojpuri': 'bhojpuri songs 2026', 'haryanvi': 'haryanvi songs 2026',
    'english': 'english songs 2026'
}

searching = set()

@bot.message_handler(commands=['start'])
def start(m):
    track_user(m.from_user.id)
    name = m.from_user.first_name
    msg = f"""🎵 AK_X_MUSIC_BOT PRO 🎵

Swagat hai {name}!

Commands:
Gaane ka naam - Search
YT Link - Direct MP3
/mood - 20+ Mood + Language
/queue - Queue dekho
/playlist - Save playlist
/next /back /stop - Control
/fav - Favourite list

Sirf MP3 | Thumbnail + Fast Download"""
    bot.reply_to(m, msg)
    if m.from_user.id!= ADMIN_ID:
        bot.send_message(ADMIN_ID, f"🔔 New User\nName: {name}\nID: {m.from_user.id}")

@bot.message_handler(commands=['mood'])
def mood_list(m):
    text = "🎭 AK_X_MUSIC_BOT - Types:\n" + "\n".join([f"/mood {k}" for k in MOODS.keys()])
    bot.reply_to(m, text)

@bot.message_handler(commands=['queue'])
def show_queue(m):
    q = get_queue(m.chat.id)
    if not q: return bot.reply_to(m, "Queue khali hai")
    text = "📜 Queue:\n" + "\n".join([f"{i+1}. {s['title'][:35]}" for i,s in enumerate(q)])
    bot.reply_to(m, text)

@bot.message_handler(commands=['playlist'])
def show_playlist(m):
    arr = get_playlist(m.chat.id)
    if not arr: return bot.reply_to(m, "Playlist khali hai")
    kb = types.InlineKeyboardMarkup()
    for i,url in enumerate(arr): kb.add(types.InlineKeyboardButton(f"▶️ Play {i+1}", callback_data=f"playlist|{url}"))
    bot.reply_to(m, "🎶 Your Playlist", reply_markup=kb)

@bot.message_handler(commands=['stop'])
def stop_song(m): set_current(m.chat.id, -1); bot.reply_to(m, "⏹️ Ruk gaya")

@bot.message_handler(commands=['next'])
def next_song(m): play_from_queue(m.chat.id, 1)

@bot.message_handler(commands=['back'])
def back_song(m): play_from_queue(m.chat.id, -1)

@bot.message_handler(commands=['fav'])
def favs(m):
    arr = get_favs(m.chat.id)
    if not arr: return bot.reply_to(m, "Fav khali hai")
    kb = types.InlineKeyboardMarkup()
    for i,url in enumerate(arr): kb.add(types.InlineKeyboardButton(f"▶️ Play {i+1}", callback_data=f"playfav|{url}"))
    bot.reply_to(m, "❤️ Fav List", reply_markup=kb)

@bot.message_handler(commands=['ban', 'unban', 'stats', 'monthly', 'users'])
def admin_cmds(m):
    if m.from_user.id!= ADMIN_ID: return
    parts = m.text.split()
    if parts[0] == '/ban': ban_user(int(parts[1])); bot.reply_to(m, f"🚫 Ban: {parts[1]}")
    if parts[0] == '/unban': unban_user(int(parts[1])); bot.reply_to(m, f"✅ Unban: {parts[1]}")
    if parts[0] == '/users':
        users = db.get("users", [])
        if not users: return bot.reply_to(m, "Abhi koi user nahi")
        text = f"👥 Total Users: {len(users)}\n\n"
        for i,uid in enumerate(users):
            text += f"{i+1}. {uid}\n"
        for i in range(0, len(text), 4000):
            bot.send_message(m.chat.id, text[i:i+4000])
    if parts[0] == '/stats':
        total = len(db.get("users", [])); month = datetime.now().strftime("%Y-%m"); today = datetime.now().strftime("%Y-%m-%d")
        monthly = len(db.get(f"monthly_{month}", [])); daily = len(db.get(f"daily_{today}", [])); banned = len(get_banned())
        bot.reply_to(m, f"📊 AK_X_MUSIC_BOT Stats\nTotal: {total}\nIs Mahine: {monthly}\nAaj: {daily}\nBanned: {banned}")
    if parts[0] == '/monthly':
        month = datetime.now().strftime("%Y-%m"); monthly_users = len(db.get(f"monthly_{month}", []))
        bot.reply_to(m, f"📅 {month} Report\nNaye Users: {monthly_users}")

@bot.message_handler(func=lambda m: True)
def handle_msg(m):
    if m.from_user.id in get_banned(): return bot.reply_to(m, "🚫 Ban ho")
    if m.chat.id in searching: return
    track_user(m.from_user.id)
    text = m.text.lower()
    if text.startswith('/mood '):
        key = text.split()[1]
        if key in MOODS: search_and_queue(m.chat.id, MOODS[key])
        else: bot.reply_to(m, "Type nahi hai")
    elif 'youtube.com' in text or 'youtu.be' in text:
        download_and_send(m.chat.id, text)
    else:
        search_and_queue(m.chat.id, m.text)
        bot.send_message(ADMIN_ID, f"🔔 Activity\nUser: {m.from_user.first_name}\nID: {m.from_user.id}\nSearch: {m.text}")

def search_and_queue(chat_id, query):
    searching.add(chat_id)
    try:
        results = YoutubeSearch(query, max_results=10).to_dict()
        q = [{'title': r['title'], 'url': 'https://youtube.com' + r['url_suffix'], 'thumb': r['thumbnails'][0]} for r in results]
        set_queue(chat_id, q); set_current(chat_id, 0)
        kb = types.InlineKeyboardMarkup()
        kb.row(types.InlineKeyboardButton("▶️ Play", callback_data="playqueue"))
        kb.row(types.InlineKeyboardButton("💾 Save Playlist", callback_data="saveplaylist"))
        kb.row(types.InlineKeyboardButton("⏮️ Back", callback_data="back"), types.InlineKeyboardButton("⏹️ Stop", callback_data="stop"), types.InlineKeyboardButton("⏭️ Next", callback_data="next"))
        bot.send_message(chat_id, f"✅ 10 gaane mil gaye\nPehla: {q[0]['title']}", reply_markup=kb)
    except: bot.send_message(chat_id, "Error aaya")
    searching.discard(chat_id)

def play_from_queue(chat_id, direction):
    q = get_queue(chat_id)
    if not q: return bot.send_message(chat_id, "Queue khali hai")
    i = get_current(chat_id) + direction
    if i < 0 or i >= len(q): return bot.send_message(chat_id, "Queue khatam")
    set_current(chat_id, i)
    download_and_send(chat_id, q[i]['url'], q[i]['title'], q[i]['thumb'])

def download_and_send(chat_id, url, title="Song", thumb=None):
    try:
        opts = {'format': 'bestaudio', 'outtmpl': f'{chat_id}.%(ext)s', 'quiet': True,
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '128'}]}
        with yt_dlp.YoutubeDL(opts) as ydl: info = ydl.extract_info(url, download=True)
        audio = open(f'{chat_id}.mp3','rb')
        thumb_file = None
        if thumb:
            r = requests.get(thumb)
            open(f'{chat_id}.jpg','wb').write(r.content)
            thumb_file = open(f'{chat_id}.jpg','rb')
        bot.send_audio(chat_id, audio, title=title[:50], thumb=thumb_file)
        audio.close()
        if thumb_file: thumb_file.close()
        os.remove(f'{chat_id}.mp3')
        if thumb: os.remove(f'{chat_id}.jpg')
    except: bot.send_message(chat_id, "Download error")

@bot.callback_query_handler(func=lambda call: True)
def cb(call):
    if call.data == "playqueue": play_from_queue(call.message.chat.id, 0)
    if call.data == "next": next_song(call.message)
    if call.data == "back": back_song(call.message)
    if call.data == "stop": stop_song(call.message)
    if call.data == "saveplaylist":
        q = get_queue(call.message.chat.id)
        for item in q: add_playlist(call.message.chat.id, item['url'])
        bot.answer_callback_query(call.id, "Playlist me save ho gaya")
    if call.data.startswith("playfav|"):
        url = call.data.split("|")[1]
        download_and_send(call.message.chat.id, url)
    if call.data.startswith("playlist|"):
        url = call.data.split("|")[1]
        download_and_send(call.message.chat.id, url)

print("AK_X_MUSIC_BOT PRO Chal Gaya")
keep_alive()
bot.infinity_polling(none_stop=True)
