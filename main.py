import os
import json
import sqlite3
import asyncio
import threading
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
def run():
    app_flask.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
def keep_alive():
    threading.Thread(target=run).start()

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
    ydl_opts = {'format': 'bestaudio/best', 'outtmpl': f'{chat_id}_%(id)s.%(ext)s', 'writethumbnail': True, 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '128'}, {'key': 'EmbedThumbnail', 'already_have_thumbnail': False}], 'quiet': True, 'noplaylist': True}
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
    if loop == 1:
        song = q['songs'][q['index']]
        asyncio.run_coroutine_threadsafe(play_audio(chat_id, song['url']), asyncio.get_event_loop())
        return
    if q['index'] + 1 < len(q['songs']):
        q['index'] += 1
    elif loop == 2:
        q['index'] = 0
    else:
        bgmode = get_setting(chat_id, 'bgmode')
        if bgmode == 0:
            asyncio.run_coroutine_threadsafe(call.leave_group_call(chat_id), asyncio.get_event_loop())
            return
    save_queue_to_db(chat_id)
    song = q['songs'][q['index']]
    asyncio.run_coroutine_threadsafe(play_audio(chat_id, song['url']), asyncio.get_event_loop())
    bot.send_message(chat_id, f"▶️ Now Playing: {song['title'][:60]}")

def add_to_queue_and_play(m, url, title):
    chat_id = m.chat.id
    if chat_id not in user_queue:
        user_queue[chat_id] = {'songs':[], 'index':-1}
    user_queue[chat_id]['songs'].append({'url':url, 'title':title})
    if user_queue[chat_id]['index'] == -1:
        user_queue[chat_id]['index'] = 0
        save_queue_to_db(chat_id)
        threading.Thread(target=lambda: asyncio.run(play_audio(chat_id, url))).start()
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

🔍 SEARCH
/gaana_name - Search 10 results
/album album_name - Full Album 🎶
/mood sad hindi - Mood + Language
/top5 singer - Top 5 Hits
YT Link - Direct MP3 ⬇️

/play song name - Voice Chat
/song song name - Download MP3
/queue - Dekho kya chal raha
/next - Skip
/back - Pichla gaana
/stop - Queue clear
/pause - Pause
/resume - Resume
/loop - Loop: off/song/queue
/bgmode - 24x7 Background Music

❤️ FAV & PLAYLIST
/fav - Add to favorite
/myfav - My favorites
/delfav - Remove favorite
/save name - Save queue
/playlist name - Load playlist
/delplaylist name - Delete playlist"""
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("😢 Mood", callback_data="mood_btn"), InlineKeyboardButton("🔥 Top5", callback_data="top5_btn"))
    markup.row(InlineKeyboardButton("🎶 Album", callback_data="album_btn"), InlineKeyboardButton("❤️ Favorites", callback_data="fav_btn"))
    markup.row(InlineKeyboardButton("📋 Queue", callback_data="queue_btn"), InlineKeyboardButton("⏭️ Next", callback_data="next_btn"))
    markup.row(InlineKeyboardButton("⏮️ Back", callback_data="back_btn"), InlineKeyboardButton("⏹️ Stop", callback_data="stop_btn"))
    markup.row(InlineKeyboardButton("🔁 Loop", callback_data="loop_btn"), InlineKeyboardButton("🎧 BG", callback_data="bg_btn"))
    if m.from_user.id == ADMIN_ID:
        markup.row(InlineKeyboardButton("👥 Users", callback_data="admin_users"), InlineKeyboardButton("📊 Stats", callback_data="admin_stats"))
        markup.row(InlineKeyboardButton("📅 Monthly", callback_data="admin_monthly"), InlineKeyboardButton("📋 AllUsers", callback_data="admin_allusers"))
    bot.send_message(m.chat.id, txt, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def menu_callback(call):
    cid = call.message.chat.id
    uid = call.from_user.id
    if call.data == "loop_btn": loop(call.message)
    elif call.data == "bg_btn": bgmode(call.message)
    elif call.data == "mood_btn":
        bot.send_message(cid, "Kaunsa mood? Ex: sad happy romantic\nLanguage: hindi punjabi english", reply_markup=ForceReply())
        user_state[uid] = "mood"
    elif call.data == "top5_btn":
        bot.send_message(cid, "Singer ka naam bhejo", reply_markup=ForceReply())
        user_state[uid] = "top5"
    elif call.data == "album_btn":
        bot.send_message(cid, "Album ka naam bhejo", reply_markup=ForceReply())
        user_state[uid] = "album"
    elif call.data == "fav_btn": my_fav(call.message)
    elif call.data == "queue_btn": show_queue(call.message)
    elif call.data == "next_btn": next_song(call.message)
    elif call.data == "back_btn": back_song(call.message)
    elif call.data == "stop_btn": stop_queue(call.message)
    elif call.data == "admin_users": users(call.message)
    elif call.data == "admin_allusers": all_users(call.message)
    elif call.data == "admin_stats": stats(call.message)
    elif call.data == "admin_monthly": monthly(call.message)
    elif call.data.startswith('play_'):
        i = int(call.data.split('_')[1])
        results = search_results.get(cid)
        if results and i < len(results):
            log_admin(call.message, f"Played: {results[i]['title']}")
            add_to_queue_and_play(call.message, results[i]['link'], results[i]['title'])
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: m.reply_to_message and m.from_user.id in user_state)
def handle_state(m):
    state = user_state.pop(m.from_user.id)
    if state == "mood": search_and_show(m, f"{m.text} songs", 10)
    elif state == "top5": search_and_show(m, f"{m.text} songs", 5)
    elif state == "album": search_and_show(m, f"{m.text} full album songs", 10)

@bot.message_handler(commands=['loop'])
def loop(m):
    chat_id = m.chat.id
    current = get_setting(chat_id, 'loop')
    new = (current + 1) % 3
    set_setting(chat_id, 'loop', new)
    status = ["Off", "Repeat Song", "Repeat Queue"]
    bot.reply_to(m, f"🔁 Loop: {status[new]}")

@bot.message_handler(commands=['bgmode'])
def bgmode(m):
    chat_id = m.chat.id
    current = get_setting(chat_id, 'bgmode')
    new = 0 if current == 1 else 1
    set_setting(chat_id, 'bgmode', new)
    status = "OFF" if new == 0 else "ON - 24x7"
    bot.reply_to(m, f"🎧 Background Mode: {status}")

@bot.message_handler(commands=['mood'])
def mood_command(m):
    if is_banned(m.from_user.id): return
    parts = m.text.split()
    if len(parts) < 2: return bot.reply_to(m, "Usage: /mood sad hindi")
    query = f"{parts[1]} songs {parts[2] if len(parts) > 2 else ''}".strip()
    search_and_show(m, query, 10)

@bot.message_handler(commands=['top5'])
def top5(m):
    if is_banned(m.from_user.id): return
    singer = m.text.replace('/top5 ', '')
    if not singer: return bot.reply_to(m, "Usage: /top5 singer_name")
    search_and_show(m, f"{singer} songs", 5)

@bot.message_handler(commands=['album'])
def album(m):
    if is_banned(m.from_user.id): return
    txt = m.text.replace('/album ', '')
    if " by " in txt.lower():
        singer = txt.split(" by ")[1].strip()
        search_and_show(m, f"{singer} album songs", 10)
    else:
        search_and_show(m, f"{txt} full album songs", 10)

@bot.message_handler(func=lambda m: not m.text.startswith('/') and not m.text.isdigit())
def search_anything(m):
    if is_banned(m.from_user.id): return
    query = m.text.strip()
    if len(query) < 3: return
    if " by " in query.lower(): search_query, limit = query, 5
    else: search_query, limit = f"{query} song", 10
    search_and_show(m, search_query, limit)

@bot.message_handler(func=lambda m: m.text.isdigit())
def play_number(m):
    if is_banned(m.from_user.id): return
    i = int(m.text) - 1
    results = search_results.get(m.chat.id)
    if results and 0 <= i < len(results):
        log_admin(m, f"Played Number: {results[i]['title']}")
        add_to_queue_and_play(m, results[i]['link'], results[i]['title'])
    else: bot.reply_to(m, "Pehle search karo")

@bot.message_handler(func=lambda m: 'youtube.com' in m.text or 'youtu.be' in m.text)
def yt_link(m):
    if is_banned(m.from_user.id): return
    save_user(m)
    url = m.text.strip()
    log_admin(m, f"YT Link: {url}")
    bot.reply_to(m, "Adding to queue... ⬇️")
    add_to_queue_and_play(m, url, "")

@bot.message_handler(commands=['play'])
def play_cmd(m):
    if is_banned(m.from_user.id): return
    if len(m.text.split()) < 2: return bot.reply_to(m, "Use: /play song name")
    song = m.text.split(" ", 1)[1]
    bot.reply_to(m, f"🔍 Searching: {song}")
    url, title = get_youtube_info(song)
    add_to_queue_and_play(m, url, title)

@bot.message_handler(commands=['song'])
def song_cmd(m):
    if is_banned(m.from_user.id): return
    if len(m.text.split()) < 2: return bot.reply_to(m, "Use: /song song name")
    song = m.text.split(" ", 1)[1]
    msg = bot.reply_to(m, f"🔍 Downloading: {song}")
    url, title = get_youtube_info(song)
    file, title, thumb = download_audio(url, m.chat.id)
    with open(file, 'rb') as audio:
        thumb_file = open(thumb, 'rb') if thumb else None
        bot.send_audio(m.chat.id, audio, title=title, performer="AK_X_MUSIC_BOT", thumb=thumb_file)
        if thumb_file: thumb_file.close()
    os.remove(file)
    if thumb and os.path.exists(thumb): os.remove(thumb)

@bot.message_handler(commands=['fav'])
def add_fav(m):
    log_admin(m, "Added to Fav")
    chat_id = m.chat.id
    if chat_id not in user_queue or user_queue[chat_id]['index']<0: return bot.reply_to(m, "Pehle gaana play karo")
    song = user_queue[chat_id]['songs'][user_queue[chat_id]['index']]
    conn.execute("INSERT OR IGNORE INTO favorites VALUES(?,?,?)", (m.from_user.id, song['url'], song['title']))
    conn.commit()
    bot.reply_to(m, f"Added to favorites: {song['title'][:40]}")

@bot.message_handler(commands=['myfav'])
def my_fav(m):
    log_admin(m, "Checked MyFav")
    res = conn.execute("SELECT title, url FROM favorites WHERE user_id=?", (m.from_user.id,)).fetchall()
    if not res: return bot.reply_to(m, "Favorite khali hai")
    msg = "Your Favorites:\n\n" + "\n".join([f"{i+1}. {r[0][:50]}" for i,r in enumerate(res)])
    bot.reply_to(m, msg)

@bot.message_handler(commands=['delfav'])
def del_fav(m):
    log_admin(m, "Deleted Fav")
    chat_id = m.chat.id
    if chat_id not in user_queue or user_queue[chat_id]['index']<0: return bot.reply_to(m, "Pehle gaana play karo")
    song = user_queue[chat_id]['songs'][user_queue[chat_id]['index']]
    conn.execute("DELETE FROM favorites WHERE user_id=? AND url=?", (m.from_user.id, song['url']))
    conn.commit()
    bot.reply_to(m, f"Removed from favorites: {song['title'][:40]}")

@bot.message_handler(commands=['save'])
def save_playlist(m):
    log_admin(m, f"Saved Playlist: {m.text}")
    chat_id = m.chat.id
    if chat_id not in user_queue: return bot.reply_to(m, "Queue khali hai")
    name = m.text.replace('/save ', '')
    songs = json.dumps(user_queue[chat_id]['songs'])
    conn.execute("INSERT OR REPLACE INTO playlists VALUES(?,?,?)", (m.from_user.id, name, songs))
    conn.commit()
    bot.reply_to(m, f"Playlist '{name}' save ho gyi")

@bot.message_handler(commands=['playlist'])
def load_playlist(m):
    log_admin(m, f"Loaded Playlist: {m.text}")
    name = m.text.replace('/playlist ', '')
    res = conn.execute("SELECT songs FROM playlists WHERE user_id=? AND name=?", (m.from_user.id, name)).fetchone()
    if not res: return bot.reply_to(m, "Playlist nahi mili")
    user_queue[m.chat.id] = {'songs':json.loads(res[0]), 'index':-1}
    save_queue_to_db(m.chat.id)
    bot.reply_to(m, f"Playlist '{name}' load. Auto play shuru")
    play_next(m.chat.id)

@bot.message_handler(commands=['delplaylist'])
def del_playlist(m):
    log_admin(m, f"Deleted Playlist: {m.text}")
    name = m.text.replace('/delplaylist ', '')
    conn.execute("DELETE FROM playlists WHERE user_id=? AND name=?", (m.from_user.id, name))
    conn.commit()
    bot.reply_to(m, f"Playlist '{name}' delete ho gyi")

@bot.message_handler(commands=['queue'])
def show_queue(m):
    log_admin(m, "Checked Queue")
    chat_id = m.chat.id
    if chat_id not in user_queue or not user_queue[chat_id]['songs']: return bot.reply_to(m, "Queue khali hai")
    q = user_queue[chat_id]
    msg = "Queue:\n\n" + "\n".join([f"{'▶️ Now: ' if i == q['index'] else f'{i+1}. '}{s['title'][:40]}" for i,s in enumerate(q['songs'])])
    bot.reply_to(m, msg)

@bot.message_handler(commands=['next'])
def next_song(m):
    log_admin(m, "Next Song")
    play_next(m.chat.id)

@bot.message_handler(commands=['back'])
def back_song(m):
    log_admin(m, "Back Song")
    chat_id = m.chat.id
    if chat_id not in user_queue: return bot.reply_to(m, "Queue nahi hai")
    q = user_queue[chat_id]
    if q['index'] - 1 < 0: return bot.reply_to(m, "Pehla gaana hai ye")
    q['index'] -= 1
    save_queue_to_db(chat_id)
    song = q['songs'][q['index']]
    asyncio.run_coroutine_threadsafe(play_audio(chat_id, song['url']), asyncio.get_event_loop())

@bot.message_handler(commands=['stop'])
def stop_queue(m):
    log_admin(m, "Stopped Queue")
    chat_id = m.chat.id
    asyncio.run_coroutine_threadsafe(call.leave_group_call(chat_id), asyncio.get_event_loop())
    if chat_id in user_queue:
        user_queue[chat_id] = {'songs':[], 'index':-1}
        conn.execute("DELETE FROM queues WHERE chat_id=?", (chat_id,))
        conn.commit()
    bot.reply_to(m, "Queue stop kar di")

@bot.message_handler(commands=['pause'])
def pause(m):
    log_admin(m, "Paused")
    asyncio.run_coroutine_threadsafe(call.pause_stream(m.chat.id), asyncio.get_event_loop())
    bot.reply_to(m, "⏸️ Paused")

@bot.message_handler(commands=['resume'])
def resume(m):
    log_admin(m, "Resumed")
    asyncio.run_coroutine_threadsafe(call.resume_stream(m.chat.id), asyncio.get_event_loop())
    bot.reply_to(m, "▶️ Resumed")

@bot.message_handler(commands=['users'])
def users(m):
    if m.from_user.id!= ADMIN_ID: return
    total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    bot.reply_to(m, f"Total Users: {total}")

@bot.message_handler(commands=['allusers'])
def all_users(m):
    if m.from_user.id!= ADMIN_ID: return
    res = conn.execute("SELECT id, first_name, username FROM users").fetchall()
    if not res: return bot.reply_to(m, "Koi user nahi hai")
    msg = f"Total Users: {len(res)}\n\n" + "\n".join([f"{i+1}. {r[1]} | {r[2]} | ID: {r[0]}" for i,r in enumerate(res)])
    for x in [msg[i:i+4000] for i in range(0, len(msg), 4000)]: bot.send_message(m.chat.id, x)

@bot.message_handler(commands=['stats'])
def stats(m):
    if m.from_user.id!= ADMIN_ID: return
    total = conn.execute("SELECT COUNT(*) FROM stats").fetchone()[0]
    this_month = datetime.now().strftime("%Y-%m")
    last_month = (datetime.now().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    this = conn.execute("SELECT COUNT(*) FROM stats WHERE date LIKE?", (this_month+'%',)).fetchone()[0]
    last = conn.execute("SELECT COUNT(*) FROM stats WHERE date LIKE?", (last_month+'%',)).fetchone()[0]
    all_users = conn.execute("SELECT u.id, u.first_name, COUNT(s.id) as c FROM users u LEFT JOIN stats s ON u.id=s.user_id GROUP BY u.id ORDER BY c DESC").fetchall()
    msg = f"Total Searches: {total}\nThis Month: {this}\nLast Month: {last}\n\nAll Users Stats:\n" + "\n".join([f"{i+1}. {t[1]} | ID: {t[0]} | {t[2]} searches" for i,t in enumerate(all_users)])
    for x in [msg[i:i+4000] for i in range(0, len(msg), 4000)]: bot.send_message(m.chat.id, x)

@bot.message_handler(commands=['monthly'])
def monthly(m):
    if m.from_user.id!= ADMIN_ID: return
    this_month = datetime.now().strftime("%Y-%m")
    this = conn.execute("SELECT COUNT(*) FROM stats WHERE date LIKE?", (this_month+'%',)).fetchone()[0]
    all_users = conn.execute("SELECT u.id, u.first_name, COUNT(s.id) as c FROM users u LEFT JOIN stats s ON u.id=s.user_id AND s.date LIKE? GROUP BY u.id ORDER BY c DESC", (this_month+'%',)).fetchall()
    msg = f"This Month: {this_month} - Total: {this}\n\nUser wise:\n" + "\n".join([f"{i+1}. {t[1]} | ID: {t[0]} | {t[2]} searches" for i,t in enumerate(all_users)])
    for x in [msg[i:i+4000] for i in range(0, len(msg), 4000)]: bot.send_message(m.chat.id, x)

@bot.message_handler(commands=['ban'])
def ban(m):
    if m.from_user.id!= ADMIN_ID: return
    try: uid = int(m.text.split()[1]); conn.execute("INSERT OR IGNORE INTO banned VALUES(?)", (uid,)); conn.commit(); bot.reply_to(m, f"Banned: {uid}")
    except: bot.reply_to(m, "Usage: /ban 123456")

@bot.message_handler(commands=['unban'])
def unban(m):
    if m.from_user.id!= ADMIN_ID: return
    try: uid = int(m.text.split()[1]); conn.execute("DELETE FROM banned WHERE user_id=?", (uid,)); conn.commit(); bot.reply_to(m, f"Unbanned: {uid}")
    except: bot.reply_to(m, "Usage: /unban 123456")

def start_both():
    threading.Thread(target=bot.polling, kwargs={'none_stop':True}).start()
    app.run()

keep_alive()
start_both()
