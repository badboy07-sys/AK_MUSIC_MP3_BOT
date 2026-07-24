import os
import json
import sqlite3
import asyncio
import threading
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask
from yt_dlp import YoutubeDL

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply

from pyrogram import Client
from pytgcalls import PyTgCalls
from pytgcalls.types.input_stream import AudioPiped
from pytgcalls.types.stream import StreamType

load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')
ADMIN_ID = int(os.getenv('ADMIN_ID', 6670168751))

bot = telebot.TeleBot(TOKEN)
app = Client("voice_session", api_id=API_ID, api_hash=API_HASH, bot_token=TOKEN)
call = PyTgCalls(app)

app_flask = Flask('')
@app_flask.route('/')
def home():
    return "AK_X_MUSIC_BOT is alive"
threading.Thread(target=lambda: app_flask.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080))), daemon=True).start()

loop_obj = asyncio.new_event_loop()
asyncio.set_event_loop(loop_obj)
threading.Thread(target=loop_obj.run_forever, daemon=True).start()

conn = sqlite3.connect('bot.db', check_same_thread=False)
conn.execute('CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, first_name TEXT, username TEXT, date TEXT)')
conn.execute('CREATE TABLE IF NOT EXISTS stats(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, query TEXT, date TEXT)')
conn.execute('CREATE TABLE IF NOT EXISTS banned(user_id INTEGER PRIMARY KEY)')
conn.execute('CREATE TABLE IF NOT EXISTS playlists(user_id INTEGER, name TEXT, songs TEXT, PRIMARY KEY(user_id, name))')
conn.execute('CREATE TABLE IF NOT EXISTS favorites(user_id INTEGER, url TEXT, title TEXT, PRIMARY KEY(user_id, url))')
conn.execute('CREATE TABLE IF NOT EXISTS queues(chat_id INTEGER PRIMARY KEY, data TEXT)')
conn.execute('CREATE TABLE IF NOT EXISTS settings(chat_id INTEGER PRIMARY KEY, loop INTEGER DEFAULT 0, bgmode INTEGER DEFAULT 0)')
conn.commit()

search_results = {}
user_queue = {}
user_state = {}

def load_queues():
    global user_queue
    for row in conn.execute("SELECT chat_id, data FROM queues"):
        user_queue[row[0]] = json.loads(row[1])

def save_queue_to_db(chat_id):
    if chat_id in user_queue:
        conn.execute("INSERT OR REPLACE INTO queues VALUES(?,?)", (chat_id, json.dumps(user_queue[chat_id])))
        conn.commit()

def get_setting(chat_id, key):
    res = conn.execute(f"SELECT {key} FROM settings WHERE chat_id=?", (chat_id,)).fetchone()
    return res[0] if res else 0

def set_setting(chat_id, key, value):
    conn.execute("INSERT OR REPLACE INTO settings(chat_id, loop, bgmode) VALUES(?,?,?)", (chat_id, get_setting(chat_id, 'loop'), get_setting(chat_id, 'bgmode')))
    conn.execute(f"UPDATE settings SET {key}=? WHERE chat_id=?", (value, chat_id))
    conn.commit()

load_queues()

def is_banned(user_id):
    return conn.execute("SELECT * FROM banned WHERE user_id=?", (user_id,)).fetchone() is not None

def log_admin(m, action):
    username = "@" + m.from_user.username if m.from_user.username else "NoUsername"
    msg = f"""User Activity!
Name: {m.from_user.first_name}
Username: {username}
User ID: {m.from_user.id}
Action: {action}
Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}"""
    try: bot.send_message(ADMIN_ID, msg)
    except: pass

def save_user(m):
    username = "@" + m.from_user.username if m.from_user.username else "NoUsername"
    conn.execute("INSERT OR IGNORE INTO users(id, first_name, username, date) VALUES(?,?,?,?)", (m.from_user.id, m.from_user.first_name, username, datetime.now().strftime("%Y-%m-%d")))
    conn.commit()

def save_stat(user_id, query):
    conn.execute("INSERT INTO stats(user_id, query, date) VALUES(?,?,?)", (user_id, query, datetime.now().strftime("%Y-%m-%d")))
    conn.commit()

def get_youtube_info(query):
    ydl_opts = {'format': 'bestaudio[ext=m4a]', 'noplaylist': True, 'quiet': True}
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0]
        return info['url'], info['title']

def download_audio(url, chat_id):
    ydl_opts = {'format': 'bastaudio/best', 'outtmpl': f'{chat_id}_%(id)s.%(ext)s', 'writethumbnail': True, 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '128'}, {'key': 'EmbedThumbnail', 'already_have_thumbnail': False}], 'quiet': True, 'noplaylist': True}
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info).replace('.webm', '.mp3').replace('.m4a', '.mp3')
        thumb = f"{chat_id}_{info['id']}.webp"
        if not os.path.exists(thumb):
            thumb = f"{chat_id}_{info['id']}.jpg"
        title = info['title']
    return filename, title, thumb if os.path.exists(thumb) else None

async def play_audio(chat_id, url):
    await call.join_group_call(chat_id, AudioPiped(url), stream_type=StreamType().pulse_stream)

def play_next(chat_id):
    if chat_id not in user_queue: return
    q = user_queue[chat_id]
    loop = get_setting(chat_id, 'loop')
    bgmode = get_setting(chat_id, 'bgmode')

    if loop == 1:
        song = q['songs'][q['index']]
    elif q['index'] + 1 < len(q['songs']):
        q['index'] += 1
        song = q['songs'][q['index']]
    elif loop == 2:
        q['index'] = 0
        song = q['songs'][q['index']]
    elif bgmode == 1:
        q['index'] = 0
        song = q['songs'][q['index']]
    else:
        asyncio.run_coroutine_threadsafe(call.leave_group_call(chat_id), loop_obj)
        return
    save_queue_to_db(chat_id)
    asyncio.run_coroutine_threadsafe(play_audio(chat_id, song['url']), loop_obj)
    try: bot.send_message(chat_id, f"▶️ Now Playing: {song['title'][:60]}")
    except: pass

def add_to_queue_and_play(m, url, title):
    chat_id = m.chat.id
    if chat_id not in user_queue:
        user_queue[chat_id] = {'songs':[], 'index':-1}
    user_queue[chat_id]['songs'].append({'url':url, 'title':title})
    if user_queue[chat_id]['index'] == -1:
        user_queue[chat_id]['index'] = 0
        save_queue_to_db(chat_id)
        asyncio.run_coroutine_threadsafe(play_audio(chat_id, url), loop_obj)
        bot.send_message(chat_id, f"▶️ Now Playing: {title}")
    else:
        save_queue_to_db(chat_id)
        bot.send_message(chat_id, f"➕ Added to queue: {title[:40]}")

@call.on_stream_end()
async def stream_end(client, update):
    play_next(update.chat_id)

def search_and_show(m, query, limit=10):
    save_user(m)
    log_admin(m, f"Search: {query}")
    save_stat(m.from_user.id, query)
    msg = bot.reply_to(m, f"Searching: {query} 🔍")
    try:
        ydl_opts = {'quiet': True, 'extract_flat': True}
        with YoutubeDL(ydl_opts) as ydl:
            results = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)['entries']
    except:
        bot.edit_message_text("Error", msg.chat.id, msg.message_id)
        return
    if not results:
        bot.edit_message_text("Koi result nahi mila 😔", msg.chat.id, msg.message_id)
        return
    search_results[m.chat.id] = [{'title': r['title'], 'link': r['url']} for r in results]
    text = f"Top {limit} Results for: {query}\n\n"
    markup = InlineKeyboardMarkup()
    for i, s in enumerate(search_results[m.chat.id]):
        text += f"{i+1}. {s['title'][:60]}\n"
        markup.add(InlineKeyboardButton(f"▶️ Play {i+1}", callback_data=f"play_{i}"))
    bot.edit_message_text(text, msg.chat.id, msg.message_id, reply_markup=markup)

@bot.message_handler(commands=['start'])
def start(m):
    save_user(m)
    log_admin(m, "Started Bot")
    txt = f"""🎵 Welcome {m.from_user.first_name}! 🎵
⚡ AK_X_MUSIC_BOT - Pro Music Bot ⚡

/play song name - Voice Chat
/song song name - Download MP3
/queue - Dekho kya chal raha
/next - Skip
/back - Pichla gaana
/stop - Queue clear
/pause - Pause
/resume - Resume
/loop - Loop: Off/Song/Queue
/bgmode - 24x7 Background Mode
/fav - Add to favorite
/myfav - My favorites
/delfav - Remove favorite
/save name - Save queue
/playlist name - Load playlist
/delplaylist name - Delete playlist"""
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("📋 Queue", callback_data="queue_btn"), InlineKeyboardButton("⏭️ Next", callback_data="next_btn"))
    markup.row(InlineKeyboardButton("⏮️ Back", callback_data="back_btn"), InlineKeyboardButton("⏹️ Stop", callback_data="stop_btn"))
    markup.row(InlineKeyboardButton("🔁 Loop", callback_data="loop_btn"), InlineKeyboardButton("🎧 BG", callback_data="bg_btn"))
    bot.send_message(m.chat.id, txt, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def menu_callback(call):
    cid = call.message.chat.id
    uid = call.from_user.id
    if call.data == "loop_btn": loop(call.message)
    elif call.data == "bg_btn": bgmode(call.message)
    elif call.data == "queue_btn": show_queue(call.message)
    elif call.data == "next_btn": next_song(call.message)
    elif call.data == "back_btn": back_song(call.message)
    elif call.data == "stop_btn": stop_queue(call.message)
    elif call.data.startswith('play_'):
        i = int(call.data.split('_')[1])
        results = search_results.get(cid)
        if results and i < len(results):
            add_to_queue_and_play(call.message, results[i]['link'], results[i]['title'])
    bot.answer_callback_query(call.id)

@bot.message_handler(commands=['loop'])
def loop(m):
    chat_id = m.chat.id
    new = (get_setting(chat_id, 'loop') + 1) % 3
    set_setting(chat_id, 'loop', new)
    status = ["Off", "Repeat Song", "Repeat Queue"]
    bot.reply_to(m, f"🔁 Loop: {status[new]}")

@bot.message_handler(commands=['bgmode'])
def bgmode(m):
    chat_id = m.chat.id
    new = 0 if get_setting(chat_id, 'bgmode') == 1 else 1
    set_setting(chat_id, 'bgmode', new)
    status = "OFF" if new == 0 else "ON - 24x7"
    bot.reply_to(m, f"🎧 BG Mode: {status}")

@bot.message_handler(commands=['play'])
def play_cmd(m):
    if is_banned(m.from_user.id): return
    if len(m.text.split()) < 2: return bot.reply_to(m, "Use: /play song name")
    url, title = get_youtube_info(m.text.split(" ", 1)[1])
    add_to_queue_and_play(m, url, title)

@bot.message_handler(commands=['song'])
def song_cmd(m):
    if is_banned(m.from_user.id): return
    if len(m.text.split()) < 2: return bot.reply_to(m, "Use: /song song name")
    url, title = get_youtube_info(m.text.split(" ", 1)[1])
    file, title, thumb = download_audio(url, m.chat.id)
    with open(file, 'rb') as audio:
        thumb_file = open(thumb, 'rb') if thumb else None
        bot.send_audio(m.chat.id, audio, title=title, performer="AK_X_MUSIC_BOT", thumb=thumb_file)
        if thumb_file: thumb_file.close()
    os.remove(file)
    if thumb and os.path.exists(thumb): os.remove(thumb)

@bot.message_handler(commands=['queue'])
def show_queue(m):
    chat_id = m.chat.id
    if chat_id not in user_queue or not user_queue[chat_id]['songs']: return bot.reply_to(m, "Queue khali hai")
    q = user_queue[chat_id]
    msg = "Queue:\n\n" + "\n".join([f"{'▶️ Now: ' if i==q['index'] else f'{i+1}. '}{s['title'][:40]}" for i,s in enumerate(q['songs'])])
    bot.reply_to(m, msg)

@bot.message_handler(commands=['next'])
def next_song(m): play_next(m.chat.id)

@bot.message_handler(commands=['back'])
def back_song(m):
    chat_id = m.chat.id
    if chat_id not in user_queue: return bot.reply_to(m, "Queue nahi hai")
    q = user_queue[chat_id]
    if q['index'] - 1 < 0: return bot.reply_to(m, "Pehla gaana hai ye")
    q['index'] -= 1
    save_queue_to_db(chat_id)
    song = q['songs'][q['index']]
    asyncio.run_coroutine_threadsafe(play_audio(chat_id, song['url']), loop_obj)

@bot.message_handler(commands=['stop'])
def stop_queue(m):
    chat_id = m.chat.id
    asyncio.run_coroutine_threadsafe(call.leave_group_call(chat_id), loop_obj)
    if chat_id in user_queue:
        user_queue[chat_id] = {'songs':[], 'index':-1}
        conn.execute("DELETE FROM queues WHERE chat_id=?", (chat_id,))
        conn.commit()
    bot.reply_to(m, "Queue stop kar di")

@bot.message_handler(commands=['pause'])
def pause(m): asyncio.run_coroutine_threadsafe(call.pause_stream(m.chat.id), loop_obj)

@bot.message_handler(commands=['resume'])
def resume(m): asyncio.run_coroutine_threadsafe(call.resume_stream(m.chat.id), loop_obj)

def keep_alive():
    while True:
        time.sleep(300)
        try: bot.get_me()
        except: pass
threading.Thread(target=keep_alive, daemon=True).start()

bot.polling(none_stop=True)
