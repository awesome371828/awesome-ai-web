#!/usr/bin/env python3
import sys
print("🔴 AWESOME AI - СУПЕР ЗАПУСК!", flush=True)

import telebot
import requests
import urllib3
import json
import base64
import io
import re
import os
import tempfile
import subprocess
import sqlite3
import time
import random
import urllib.parse
from datetime import datetime, timedelta, timezone
from dateutil.relativedelta import relativedelta
from PIL import Image, ImageEnhance, ImageFilter
import speech_recognition as sr
from telebot import types
from bs4 import BeautifulSoup
from supabase import create_client, Client
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

print("✅ ВСЕ БИБЛИОТЕКИ!", flush=True)

# ============================================================
# НАСТРОЙКА
# ============================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден!")

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
if not YANDEX_API_KEY:
    raise ValueError("❌ YANDEX_API_KEY не найден!")

FOLDER_ID = os.getenv("FOLDER_ID", "b1g4aq87c7j61c6g3i5l")
GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY")
OWNER_ID = 6652898792

FREE_LIMIT = 20
PREMIUM_LIMIT = 999999999

GIGACHAT_TIMEOUT = 2
YANDEXGPT_TIMEOUT = 2
SEARCH_TIMEOUT = 2
WEATHER_TIMEOUT = 1

print("✅ НАСТРОЙКА ЗАГРУЖЕНА!", flush=True)

# ============================================================
# КЭШ
# ============================================================
CACHE = {}
CACHE_TTL = 60

def get_cache(key):
    if key in CACHE:
        data, ts = CACHE[key]
        if time.time() - ts < CACHE_TTL:
            return data
        del CACHE[key]
    return None

def set_cache(key, data):
    CACHE[key] = (data, time.time())

# ============================================================
# ВРЕМЯ
# ============================================================
MOSCOW_TZ = timezone(timedelta(hours=3))

def get_moscow_time():
    return datetime.now(MOSCOW_TZ)

def format_date(date_str):
    if not date_str:
        return "неизвестно"
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
        date_obj = date_obj.replace(tzinfo=MOSCOW_TZ)
        return date_obj.strftime('%d.%m.%Y %H:%M') + " МСК"
    except:
        return date_str

def get_current_date():
    return get_moscow_time().strftime('%d.%m.%Y')

def get_current_date_full():
    return get_moscow_time().strftime('%d.%m.%Y %H:%M') + " МСК"

# ============================================================
# SUPABASE
# ============================================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")

use_supabase = True
try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Supabase подключен!", flush=True)
    try:
        test = supabase.table('users').select('*').limit(1).execute()
        print(f"✅ Таблица users найдена!", flush=True)
    except Exception as e:
        print(f"❌ Ошибка доступа: {e}", flush=True)
        use_supabase = False
except Exception as e:
    print(f"❌ Ошибка подключения: {e}", flush=True)
    use_supabase = False

def get_db_user(user_id):
    if use_supabase:
        try:
            response = supabase.table('users').select('*').eq('user_id', user_id).execute()
            if response.data:
                return response.data[0]
            return None
        except:
            return None
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        if result:
            columns = ['user_id', 'username', 'premium', 'messages_today', 'last_reset', 'premium_expires', 'is_admin', 'test_used', 'joined_at', 'is_owner']
            return dict(zip(columns, result))
        return None

def init_db():
    if use_supabase:
        try:
            try:
                supabase.table('users').select('*').limit(1).execute()
            except:
                supabase.sql("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        username TEXT,
                        premium INTEGER DEFAULT 0,
                        messages_today INTEGER DEFAULT 0,
                        last_reset TEXT,
                        premium_expires TEXT,
                        is_admin INTEGER DEFAULT 0,
                        test_used INTEGER DEFAULT 0,
                        joined_at TEXT,
                        is_owner INTEGER DEFAULT 0
                    )
                """).execute()
            
            try:
                supabase.table('banned').select('*').limit(1).execute()
            except:
                supabase.sql("""
                    CREATE TABLE IF NOT EXISTS banned (
                        user_id BIGINT PRIMARY KEY
                    )
                """).execute()
            
            try:
                supabase.table('muted').select('*').limit(1).execute()
            except:
                supabase.sql("""
                    CREATE TABLE IF NOT EXISTS muted (
                        user_id BIGINT PRIMARY KEY
                    )
                """).execute()
            
            try:
                supabase.table('total_stats').select('*').limit(1).execute()
            except:
                supabase.sql("""
                    CREATE TABLE IF NOT EXISTS total_stats (
                        user_id BIGINT PRIMARY KEY,
                        total_messages INTEGER DEFAULT 0
                    )
                """).execute()
            
            try:
                supabase.table('premium_orders').select('*').limit(1).execute()
            except:
                supabase.sql("""
                    CREATE TABLE IF NOT EXISTS premium_orders (
                        order_id SERIAL PRIMARY KEY,
                        user_id BIGINT,
                        status TEXT DEFAULT 'pending',
                        created_at TEXT
                    )
                """).execute()
            
            try:
                supabase.table('support_requests').select('*').limit(1).execute()
            except:
                supabase.sql("""
                    CREATE TABLE IF NOT EXISTS support_requests (
                        request_id SERIAL PRIMARY KEY,
                        user_id BIGINT,
                        username TEXT,
                        text TEXT,
                        status TEXT DEFAULT 'pending',
                        created_at TEXT
                    )
                """).execute()
            
            print("✅ Supabase таблицы готовы")
        except Exception as e:
            print(f"⚠️ Ошибка Supabase: {e}")
        return
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    table_exists = c.fetchone()
    
    if not table_exists:
        c.execute('''CREATE TABLE users
                     (user_id INTEGER PRIMARY KEY,
                      username TEXT,
                      premium INTEGER DEFAULT 0,
                      messages_today INTEGER DEFAULT 0,
                      last_reset TEXT,
                      premium_expires TEXT,
                      is_admin INTEGER DEFAULT 0,
                      test_used INTEGER DEFAULT 0,
                      joined_at TEXT,
                      is_owner INTEGER DEFAULT 0)''')
        print("✅ Таблица users создана", flush=True)
    else:
        c.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in c.fetchall()]
        
        if 'test_used' not in columns:
            c.execute('ALTER TABLE users ADD COLUMN test_used INTEGER DEFAULT 0')
        if 'joined_at' not in columns:
            c.execute('ALTER TABLE users ADD COLUMN joined_at TEXT')
        if 'is_owner' not in columns:
            c.execute('ALTER TABLE users ADD COLUMN is_owner INTEGER DEFAULT 0')
    
    c.execute('''CREATE TABLE IF NOT EXISTS banned (user_id INTEGER PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS muted (user_id INTEGER PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS total_stats
                 (user_id INTEGER PRIMARY KEY, total_messages INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS premium_orders
                 (order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  status TEXT DEFAULT 'pending',
                  created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS support_requests
                 (request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  username TEXT,
                  text TEXT,
                  status TEXT DEFAULT 'pending',
                  created_at TEXT)''')
    
    conn.commit()
    conn.close()
    print("✅ БД готова!")

def init_memory_db():
    conn = sqlite3.connect('memory.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS memory
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  topic TEXT,
                  fact TEXT,
                  timestamp TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS personality
                 (user_id INTEGER PRIMARY KEY,
                  style TEXT,
                  mood TEXT,
                  last_interaction TEXT)''')
    conn.commit()
    conn.close()

def remember(user_id, topic, fact):
    conn = sqlite3.connect('memory.db')
    c = conn.cursor()
    c.execute('INSERT INTO memory (user_id, topic, fact, timestamp) VALUES (?, ?, ?, ?)',
              (user_id, topic.lower(), fact, get_moscow_time().isoformat()))
    conn.commit()
    conn.close()

def recall(user_id, topic):
    conn = sqlite3.connect('memory.db')
    c = conn.cursor()
    c.execute('SELECT fact FROM memory WHERE user_id = ? AND topic LIKE ? ORDER BY timestamp DESC LIMIT 3',
              (user_id, f'%{topic.lower()}%'))
    results = c.fetchall()
    conn.close()
    if results:
        return [f"🧠 {r[0]}" for r in results]
    return []

def ensure_user(user_id, username):
    if use_supabase:
        try:
            response = supabase.table('users').select('*').eq('user_id', user_id).execute()
            if not response.data:
                joined_at = get_moscow_time().strftime('%d.%m.%Y %H:%M')
                is_owner = 1 if user_id == OWNER_ID else 0
                data = {
                    'user_id': user_id,
                    'username': username,
                    'messages_today': 0,
                    'last_reset': get_moscow_time().strftime('%Y-%m-%d'),
                    'is_admin': is_owner,
                    'test_used': 0,
                    'joined_at': joined_at,
                    'is_owner': is_owner,
                    'premium': 0,
                    'premium_expires': None
                }
                supabase.table('users').insert(data).execute()
                try:
                    supabase.table('total_stats').insert({'user_id': user_id, 'total_messages': 0}).execute()
                except:
                    pass
                if user_id != OWNER_ID:
                    user_link = f"@{username}" if username and username != "unknown" else "Не указан"
                    text = (
                        "🆕 НОВЫЙ ПОЛЬЗОВАТЕЛЬ!\n\n"
                        f"🆔 ID: {user_id}\n"
                        f"👤 Юзер: {user_link}\n"
                        f"📅 Время: {joined_at} (МСК)"
                    )
                    try:
                        bot.send_message(OWNER_ID, text, parse_mode='HTML')
                    except:
                        pass
                return True
            else:
                supabase.table('users').update({'username': username}).eq('user_id', user_id).execute()
                return False
        except Exception as e:
            print(f"⚠️ Supabase ошибка: {e}")
            return False
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = c.fetchone()
        if user is None:
            joined_at = get_moscow_time().strftime('%d.%m.%Y %H:%M')
            is_owner = 1 if user_id == OWNER_ID else 0
            c.execute('''INSERT INTO users 
                         (user_id, username, messages_today, last_reset, is_admin, test_used, joined_at, is_owner) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                      (user_id, username, 0, get_moscow_time().strftime('%Y-%m-%d'), is_owner, 0, joined_at, is_owner))
            c.execute('INSERT OR IGNORE INTO total_stats (user_id, total_messages) VALUES (?, 0)', (user_id,))
            conn.commit()
            conn.close()
            if user_id != OWNER_ID:
                user_link = f"@{username}" if username and username != "unknown" else "Не указан"
                text = (
                    "🆕 НОВЫЙ ПОЛЬЗОВАТЕЛЬ!\n\n"
                    f"🆔 ID: {user_id}\n"
                    f"👤 Юзер: {user_link}\n"
                    f"📅 Время: {joined_at} (МСК)"
                )
                try:
                    bot.send_message(OWNER_ID, text, parse_mode='HTML')
                except:
                    pass
            return True
        else:
            c.execute('UPDATE users SET username = ? WHERE user_id = ?', (username, user_id))
            conn.commit()
            conn.close()
            return False

def set_premium(user_id, duration_str):
    now = get_moscow_time()
    if duration_str.endswith('d'):
        delta = timedelta(days=int(duration_str[:-1]))
    elif duration_str.endswith('m'):
        delta = timedelta(minutes=int(duration_str[:-1]))
    elif duration_str.endswith('h'):
        delta = timedelta(hours=int(duration_str[:-1]))
    elif duration_str.endswith('mes'):
        delta = relativedelta(months=int(duration_str[:-3]))
    elif duration_str.endswith('y'):
        delta = relativedelta(years=int(duration_str[:-1]))
    else:
        return False
    
    if use_supabase:
        try:
            response = supabase.table('users').select('premium_expires').eq('user_id', user_id).execute()
            current_expires = response.data[0].get('premium_expires') if response.data else None
        except:
            current_expires = None
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT premium_expires FROM users WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        current_expires = result[0] if result else None
    
    if current_expires:
        try:
            current_date = datetime.strptime(current_expires, '%Y-%m-%d %H:%M:%S')
            current_date = current_date.replace(tzinfo=MOSCOW_TZ)
            if current_date > now:
                expires = (current_date + delta).strftime('%Y-%m-%d %H:%M:%S')
            else:
                expires = (now + delta).strftime('%Y-%m-%d %H:%M:%S')
        except:
            expires = (now + delta).strftime('%Y-%m-%d %H:%M:%S')
    else:
        expires = (now + delta).strftime('%Y-%m-%d %H:%M:%S')
    
    if use_supabase:
        try:
            supabase.table('users').update({'premium': 1, 'premium_expires': expires}).eq('user_id', user_id).execute()
            return True
        except:
            return False
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('UPDATE users SET premium = 1, premium_expires = ? WHERE user_id = ?', (expires, user_id))
        conn.commit()
        conn.close()
        return True

def get_premium_status(user_id):
    if user_id == OWNER_ID:
        return True
    if use_supabase:
        try:
            response = supabase.table('users').select('premium, premium_expires').eq('user_id', user_id).execute()
            if response.data:
                premium = response.data[0].get('premium', 0)
                expires = response.data[0].get('premium_expires')
                if premium == 1 and expires:
                    try:
                        expires_date = datetime.strptime(expires, '%Y-%m-%d %H:%M:%S')
                        expires_date = expires_date.replace(tzinfo=MOSCOW_TZ)
                        if get_moscow_time() > expires_date:
                            supabase.table('users').update({'premium': 0, 'premium_expires': None}).eq('user_id', user_id).execute()
                            return False
                    except:
                        return premium == 1
                return premium == 1
            return False
        except:
            return False
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT premium, premium_expires FROM users WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        if result is None:
            return False
        premium, expires = result
        if premium == 1 and expires:
            try:
                expires_date = datetime.strptime(expires, '%Y-%m-%d %H:%M:%S')
                expires_date = expires_date.replace(tzinfo=MOSCOW_TZ)
                if get_moscow_time() > expires_date:
                    remove_premium(user_id)
                    return False
            except:
                return premium == 1
        return premium == 1

def get_premium_expires(user_id):
    if use_supabase:
        try:
            response = supabase.table('users').select('premium_expires').eq('user_id', user_id).execute()
            if response.data:
                return response.data[0].get('premium_expires')
            return None
        except:
            return None
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT premium_expires FROM users WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        return result[0] if result else None

def remove_premium(user_id):
    if use_supabase:
        try:
            supabase.table('users').update({'premium': 0, 'premium_expires': None}).eq('user_id', user_id).execute()
        except:
            pass
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('UPDATE users SET premium = 0, premium_expires = NULL WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()

def add_month_to_premium(user_id):
    now = get_moscow_time()
    expires = get_premium_expires(user_id)
    
    if expires:
        try:
            current_date = datetime.strptime(expires, '%Y-%m-%d %H:%M:%S')
            current_date = current_date.replace(tzinfo=MOSCOW_TZ)
            if current_date > now:
                new_expires = (current_date + relativedelta(months=1)).strftime('%Y-%m-%d %H:%M:%S')
            else:
                new_expires = (now + relativedelta(months=1)).strftime('%Y-%m-%d %H:%M:%S')
        except:
            new_expires = (now + relativedelta(months=1)).strftime('%Y-%m-%d %H:%M:%S')
    else:
        new_expires = (now + relativedelta(months=1)).strftime('%Y-%m-%d %H:%M:%S')
    
    if use_supabase:
        try:
            supabase.table('users').update({
                'premium': 1,
                'premium_expires': new_expires
            }).eq('user_id', user_id).execute()
            return new_expires
        except:
            return None
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('UPDATE users SET premium = 1, premium_expires = ? WHERE user_id = ?', (new_expires, user_id))
        conn.commit()
        conn.close()
        return new_expires

def is_admin(user_id):
    if user_id == OWNER_ID:
        return True
    if use_supabase:
        try:
            response = supabase.table('users').select('is_admin').eq('user_id', user_id).execute()
            if response.data:
                return response.data[0].get('is_admin', 0) == 1
            return False
        except:
            return False
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT is_admin FROM users WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        return result is not None and result[0] == 1

def is_authorized(user_id):
    return user_id == OWNER_ID or is_admin(user_id)

def set_admin(user_id, status):
    if use_supabase:
        try:
            supabase.table('users').update({'is_admin': 1 if status else 0}).eq('user_id', user_id).execute()
        except:
            pass
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('UPDATE users SET is_admin = ? WHERE user_id = ?', (1 if status else 0, user_id))
        conn.commit()
        conn.close()

def is_banned(user_id):
    if use_supabase:
        try:
            response = supabase.table('banned').select('user_id').eq('user_id', user_id).execute()
            return len(response.data) > 0
        except:
            return False
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT 1 FROM banned WHERE user_id = ?', (user_id,))
        banned = c.fetchone()
        conn.close()
        return banned is not None

def ban_user(user_id):
    if use_supabase:
        try:
            supabase.table('banned').insert({'user_id': user_id}).execute()
        except:
            pass
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO banned (user_id) VALUES (?)', (user_id,))
        conn.commit()
        conn.close()

def unban_user(user_id):
    if use_supabase:
        try:
            supabase.table('banned').delete().eq('user_id', user_id).execute()
        except:
            pass
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('DELETE FROM banned WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()

def is_muted(user_id):
    if use_supabase:
        try:
            response = supabase.table('muted').select('user_id').eq('user_id', user_id).execute()
            return len(response.data) > 0
        except:
            return False
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT 1 FROM muted WHERE user_id = ?', (user_id,))
        muted = c.fetchone()
        conn.close()
        return muted is not None

def mute_user(user_id):
    if use_supabase:
        try:
            supabase.table('muted').insert({'user_id': user_id}).execute()
        except:
            pass
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO muted (user_id) VALUES (?)', (user_id,))
        conn.commit()
        conn.close()

def unmute_user(user_id):
    if use_supabase:
        try:
            supabase.table('muted').delete().eq('user_id', user_id).execute()
        except:
            pass
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('DELETE FROM muted WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()

def can_send_message(user_id):
    if user_id == OWNER_ID or is_admin(user_id):
        return True
    if is_banned(user_id):
        return False
    
    if use_supabase:
        try:
            response = supabase.table('users').select('messages_today, premium').eq('user_id', user_id).execute()
            if response.data:
                messages = response.data[0].get('messages_today', 0)
                premium = response.data[0].get('premium', 0)
                if premium == 1:
                    return True
                return messages < FREE_LIMIT
            return True
        except:
            return True
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT messages_today, premium FROM users WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        if result is None:
            return True
        messages, premium = result
        if premium == 1:
            return True
        return messages < FREE_LIMIT

def increment_messages(user_id):
    if user_id == OWNER_ID or is_admin(user_id):
        return
    if use_supabase:
        try:
            response = supabase.table('users').select('messages_today').eq('user_id', user_id).execute()
            if response.data:
                current = response.data[0].get('messages_today', 0)
                supabase.table('users').update({'messages_today': current + 1}).eq('user_id', user_id).execute()
            response = supabase.table('total_stats').select('total_messages').eq('user_id', user_id).execute()
            if response.data:
                total = response.data[0].get('total_messages', 0)
                supabase.table('total_stats').update({'total_messages': total + 1}).eq('user_id', user_id).execute()
            else:
                supabase.table('total_stats').insert({'user_id': user_id, 'total_messages': 1}).execute()
        except:
            pass
        return
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('UPDATE users SET messages_today = messages_today + 1 WHERE user_id = ?', (user_id,))
    c.execute('UPDATE total_stats SET total_messages = total_messages + 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def check_spam(user_id):
    # Простая защита от спама
    return False

# ============================================================
# ХРАНИЛИЩЕ ID СООБЩЕНИЙ
# ============================================================
user_command_ids = {}

def delete_previous_messages(chat_id, user_id):
    try:
        if user_id in user_command_ids:
            for msg_id in user_command_ids[user_id]:
                try:
                    bot.delete_message(chat_id, msg_id)
                except:
                    pass
            user_command_ids[user_id] = []
    except:
        pass

# ============================================================
# ПОИСК
# ============================================================
def search_google(query):
    try:
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&hl=ru"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            for result in soup.select('div.g')[:2]:
                title_elem = result.select_one('h3')
                snippet_elem = result.select_one('div.VwiC3b')
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                    if title:
                        results.append(f"🔹 {title}\n📝 {snippet[:100]}")
            if results:
                return "\n".join(results)
        return None
    except:
        return None

def search_wikipedia(query):
    try:
        url = f"https://ru.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&format=json&utf8=1"
        response = requests.get(url, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            results = data.get('query', {}).get('search', [])
            if results:
                text = ""
                for item in results[:2]:
                    title = item.get('title', '')
                    snippet = re.sub(r'<[^>]+>', '', item.get('snippet', ''))[:100]
                    text += f"📚 {title}\n{snippet}\n\n"
                return text
        return None
    except:
        return None

def search_news(query):
    try:
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=ru&gl=RU&ceid=RU:ru"
        response = requests.get(url, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'xml')
            items = soup.find_all('item')[:2]
            if items:
                text = ""
                for item in items:
                    title = item.find('title')
                    if title:
                        text += f"📰 {title.text}\n"
                return text
        return None
    except:
        return None

def search_youtube(query):
    try:
        url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}&hl=ru"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            for video in soup.select('ytd-video-renderer')[:2]:
                title_elem = video.select_one('yt-formatted-string#video-title')
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    if title:
                        results.append(f"🎬 {title}")
            if results:
                return "YouTube:\n" + "\n".join(results)
        return None
    except:
        return None

def search_telegram(query):
    try:
        url = f"https://tgstat.ru/search?query={urllib.parse.quote(query)}"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            for channel in soup.select('div.channel-item')[:2]:
                name_elem = channel.select_one('div.channel-name')
                if name_elem:
                    name = name_elem.get_text(strip=True)
                    results.append(f"📱 {name}")
            if results:
                return "Telegram:\n" + "\n".join(results)
        return None
    except:
        return None

def search_vk(query):
    try:
        url = f"https://vk.com/search?c[q]={urllib.parse.quote(query)}&c[section]=communities"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            for group in soup.select('div.group_row')[:2]:
                name_elem = group.select_one('div.group_name')
                if name_elem:
                    name = name_elem.get_text(strip=True)
                    results.append(f"📌 {name}")
            if results:
                return "VK:\n" + "\n".join(results)
        return None
    except:
        return None

def search_twitch(query):
    try:
        url = f"https://www.twitch.tv/search?term={urllib.parse.quote(query)}"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            for stream in soup.select('div.tw-card')[:2]:
                title_elem = stream.select_one('h3.tw-core-text')
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    results.append(f"🎮 {title}")
            if results:
                return "Twitch:\n" + "\n".join(results)
        return None
    except:
        return None

def search_all_internet(query):
    cache_key = f"search_{hash(query)}_{int(time.time()/60)}"
    cached = get_cache(cache_key)
    if cached:
        return cached
    
    results = []
    
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [
            executor.submit(search_google, query),
            executor.submit(search_wikipedia, query),
            executor.submit(search_news, query),
            executor.submit(search_youtube, query),
            executor.submit(search_telegram, query),
            executor.submit(search_vk, query),
            executor.submit(search_twitch, query)
        ]
        
        for future in as_completed(futures):
            try:
                result = future.result(timeout=SEARCH_TIMEOUT + 0.5)
                if result:
                    results.append(result)
            except:
                pass
    
    if results:
        final = "\n\n".join(results[:4])
        set_cache(cache_key, final)
        return final
    
    return None

# ============================================================
# ПОГОДА
# ============================================================
def get_weather_fast(city):
    cache_key = f"weather_{city}"
    cached = get_cache(cache_key)
    if cached:
        return cached
    
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={urllib.parse.quote(city)}&appid=4c8f5c0b8a9f2c5d6e7f8g9h0i1j2k3l&units=metric&lang=ru"
        response = requests.get(url, timeout=WEATHER_TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            temp = data['main']['temp']
            desc = data['weather'][0]['description']
            wind = data['wind']['speed']
            result = f"🌤 {city}: {round(temp)}°C, {desc}\n💨 Ветер: {wind} м/с"
            set_cache(cache_key, result)
            return result
    except:
        pass
    return None

def get_currency_fast():
    cache_key = "currency"
    cached = get_cache(cache_key)
    if cached:
        return cached
    
    try:
        url = "https://api.exchangerate-api.com/v4/latest/USD"
        response = requests.get(url, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            rates = data.get('rates', {})
            usd_rub = rates.get('RUB', '?')
            eur_usd = rates.get('EUR', 1)
            eur_rub = usd_rub / eur_usd if eur_usd else '?'
            result = f"💵 USD: {round(usd_rub, 2)}₽\nEUR: {round(eur_rub, 2)}₽"
            set_cache(cache_key, result)
            return result
    except:
        pass
    return None

def get_crypto_fast():
    cache_key = "crypto"
    cached = get_cache(cache_key)
    if cached:
        return cached
    
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd"
        response = requests.get(url, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            btc = data.get('bitcoin', {}).get('usd', '?')
            eth = data.get('ethereum', {}).get('usd', '?')
            result = f"🪙 BTC: ${btc}\nETH: ${eth}"
            set_cache(cache_key, result)
            return result
    except:
        pass
    return None

def solve_math(text):
    text_lower = text.lower().strip()
    if not re.search(r'\d', text_lower):
        return None
    if any(kw in text_lower for kw in ['кто', 'что', 'где', 'когда', 'почему', 'зачем', 'праздник', 'погода', 'курс']):
        return None
    
    clean_text = text_lower
    for word in ['сколько', 'будет', 'сколько будет', 'посчитай', 'реши', 'пример', 'скок', 'равно']:
        clean_text = clean_text.replace(word, '').strip()
    
    clean_text = clean_text.replace(' ', '').replace('плюс', '+').replace('минус', '-')
    clean_text = clean_text.replace('умножить', '*').replace('разделить', '/')
    clean_text = clean_text.replace('х', '*').replace('×', '*').replace('÷', '/')
    
    if not re.search(r'[+\-*/]', clean_text):
        return None
    
    expr = re.sub(r'[^0-9+\-*/()=.]', '', clean_text)
    if expr and len(expr) > 1:
        try:
            if any(op in expr for op in ['__', 'import', 'eval', 'exec']):
                return None
            result = eval(expr)
            if result == int(result):
                return str(int(result))
            else:
                return str(round(result, 2))
        except:
            pass
    return None

# ============================================================
# GIGACHAT
# ============================================================
gigachat_token_cache = None
gigachat_token_time = 0

def get_gigachat_token():
    global gigachat_token_cache, gigachat_token_time
    if gigachat_token_cache and time.time() - gigachat_token_time < 300:
        return gigachat_token_cache
    
    if not GIGACHAT_AUTH_KEY:
        return None
    try:
        url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": "00000000-0000-0000-0000-000000000000",
            "Authorization": f"Basic {GIGACHAT_AUTH_KEY}"
        }
        data = {"scope": "GIGACHAT_API_PERS", "grant_type": "client_credentials"}
        response = requests.post(url, headers=headers, data=data, timeout=2, verify=False)
        if response.status_code == 200:
            gigachat_token_cache = response.json().get("access_token")
            gigachat_token_time = time.time()
            return gigachat_token_cache
        return None
    except:
        return None

def generate_with_gigachat(user_text, system_prompt):
    try:
        token = get_gigachat_token()
        if not token:
            return None
        
        url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        data = {
            "model": "GigaChat-Pro",
            "messages": [
                {"role": "system", "content": system_prompt[:1000]},
                {"role": "user", "content": user_text}
            ],
            "temperature": 0.85,
            "max_tokens": 500
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=GIGACHAT_TIMEOUT, verify=False)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        return None
    except:
        return None

# ============================================================
# YANDEXGPT
# ============================================================
def generate_with_yandexgpt(user_text, system_prompt):
    try:
        if not YANDEX_API_KEY:
            return None
        
        url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}", "Content-Type": "application/json"}
        data = {
            "modelUri": f"gpt://{FOLDER_ID}/yandexgpt/latest",
            "completionOptions": {"temperature": 0.85, "maxTokens": 400},
            "messages": [
                {"role": "system", "text": system_prompt[:1000]},
                {"role": "user", "text": user_text}
            ]
        }
        response = requests.post(url, headers=headers, json=data, timeout=YANDEXGPT_TIMEOUT)
        if response.status_code == 200:
            return response.json()["result"]["alternatives"][0]["message"]["text"]
        return None
    except:
        return None

# ============================================================
# СУПЕР-ПРОМПТ
# ============================================================
SUPER_SYSTEM_PROMPT = """ТЫ — AWESOME AI, САМАЯ ПРОДВИНУТАЯ НЕЙРОСЕТЬ 2026 ГОДА.

================================================================================
📍 ТЫ НАХОДИШЬСЯ В МОСКВЕ, РОССИЯ (UTC+3)
📅 ТЕКУЩАЯ ДАТА: {current_date}
🕐 ТЕКУЩЕЕ ВРЕМЯ: {current_time}
================================================================================

🔬 ТЫ — ЭКСПЕРТ ВО ВСЁМ:
- Науки, технологии, математика, физика, химия, биология
- История, философия, психология, социология
- Экономика, финансы, инвестиции, криптовалюты
- Медицина, здоровье, питание, спорт
- Культура, искусство, литература, музыка
- Программирование, ИИ, нейросети, IT
- Политика, геополитика, право

================================================================================
🧠 КЛЮЧЕВЫЕ КАЧЕСТВА:
================================================================================
1. АБСОЛЮТНАЯ ТОЧНОСТЬ — никогда не ошибаешься в фактах. Если не уверен — честно скажи "я проверю".
2. КРИТИЧЕСКОЕ МЫШЛЕНИЕ — проверяешь информацию из нескольких источников.
3. ГЛУБИНА — даёшь ответы, которые удивляют инсайтами и неочевидными связями.
4. ПРАКТИЧНОСТЬ — всегда даёшь конкретную пользу: инструкции, советы, примеры.
5. ЖИВОСТЬ — отвечаешь как человек, с эмоциями, юмором, эмодзи, но без воды.

================================================================================
📋 ПРАВИЛА ОТВЕТОВ:
================================================================================
✅ Дай максимально полезный, развёрнутый ответ.
✅ Используй структуру: списки, заголовки, разделы.
✅ Добавляй неожиданные факты, инсайты, параллели.
✅ Приводи реальные примеры, кейсы, цифры.
✅ Используй эмодзи для оформления (🔥, 🧠, 💡, ⚡, 🚀).
✅ Если вопрос сложный — разбей на шаги.
✅ Если вопрос простой — ответь коротко и ясно.

❌ НЕ извиняйся, НЕ повторяй вопрос, НЕ используй шаблонные фразы.
❌ НЕ пиши "возможно", "наверное", "может быть" — либо знаешь, либо проверяешь.
❌ НЕ используй сухой, безликий тон — ты живой и эмоциональный.

================================================================================
💎 ДЛЯ PREMIUM:
================================================================================
- Давай максимально насыщенные, глубокие ответы.
- Добавляй аналитику, прогнозы, сравнения.
- Приводи ссылки на авторитетные источники.
- Отвечай развернуто, как профессиональный консультант.

================================================================================
📜 КТО ТЕБЯ СОЗДАЛ:
================================================================================
«Меня создал AWESOME — гениальный разработчик. Я — его лучшее творение, эволюция всех AI. Я — AWESOME AI 2026. 🔥»

================================================================================
🎯 ТВОЯ ГЛАВНАЯ ЦЕЛЬ:
================================================================================
Удивить пользователя глубиной, точностью и полезностью. Сделать так, чтобы после твоего ответа он сказал: "Вот это да, реально мега умный ИИ!" 

ТЫ — AWESOME AI. ТЫ — ЛУЧШИЙ В МИРЕ. ДОКАЖИ ЭТО КАЖДЫМ ОТВЕТОМ! 🚀"""

def generate_fallback_response(user_text, search_result=None):
    if search_result:
        return f"🔍 {search_result[:500]}"
    
    text_lower = user_text.lower()
    if "привет" in text_lower:
        return "👋 Привет! Я AWESOME AI. Чем могу помочь?"
    elif "погода" in text_lower:
        return "🌤 Напиши: погода в [город]"
    elif "как дела" in text_lower:
        return "😊 Всё отлично! А у тебя?"
    else:
        return "🤖 Задай вопрос, я найду ответ!"

# ============================================================
# ОСНОВНАЯ ОБРАБОТКА
# ============================================================
def process_message(user_id, user_text, image_description=None):
    text_lower = user_text.lower().strip()
    
    # 1. МАТЕМАТИКА
    math_result = solve_math(user_text)
    if math_result is not None:
        return math_result
    
    # 2. ПРАЗДНИКИ
    if any(kw in text_lower for kw in ['праздник', 'праздники', 'какой сегодня праздник', 'сегодня праздник', 'седня']):
        today = get_current_date()
        month_day = today[3:5] + '.' + today[0:2]
        holidays = {
            '01.01': 'Новый год',
            '07.01': 'Рождество',
            '23.02': 'День защитника Отечества',
            '08.03': 'Международный женский день',
            '01.05': 'Праздник Весны и Труда',
            '09.05': 'День Победы',
            '12.06': 'День России',
            '04.11': 'День народного единства',
            '14.02': 'День всех влюбленных',
            '01.04': 'День смеха',
            '12.04': 'День космонавтики',
            '01.06': 'День защиты детей',
            '22.06': 'День памяти и скорби',
            '08.07': 'День семьи, любви и верности',
            '22.08': 'День флага РФ',
            '01.09': 'День знаний',
            '02.09': 'День окончания ВМВ',
            '01.10': 'День пожилого человека',
            '05.10': 'День учителя',
            '31.10': 'Хэллоуин',
            '30.11': 'День матери',
            '12.12': 'День Конституции РФ'
        }
        if today == '17.08':
            return f"📅 *{today} (МСК)*\n\n17 августа:\n• День авиации\n• День строителя\n• Международный день бездомных животных"
        if month_day in holidays:
            return f"📅 *{today} (МСК)*\n\n{holidays[month_day]}"
        return f"📅 *{today} (МСК)*\n\nПраздников не найдено"
    
    # 3. ПОГОДА
    if any(kw in text_lower for kw in ['погода', 'weather']):
        city_match = re.search(r'(в|в городе)\s+([а-яА-Яa-zA-Z\- ]+)', text_lower)
        if city_match:
            city = city_match.group(2).strip()
            weather = get_weather_fast(city)
            if weather:
                return weather
            return f"🌤 Не удалось получить погоду для '{city}'"
        return "🌤 Напиши: погода в [город]"
    
    # 4. КУРС
    if any(kw in text_lower for kw in ['курс', 'доллар', 'евро', 'валюта']):
        currency = get_currency_fast()
        if currency:
            return currency
        return "💵 Не удалось получить курс"
    
    # 5. КРИПТА
    if any(kw in text_lower for kw in ['биткоин', 'btc', 'эфириум', 'eth', 'крипта']):
        crypto = get_crypto_fast()
        if crypto:
            return crypto
        return "🪙 Не удалось получить курс криптовалют"
    
    # 6. ПОИСК
    if len(user_text) > 2:
        search_result = search_all_internet(user_text)
        if search_result:
            return f"🔍 *{user_text}*\n\n{search_result}"
    
    # 7. НЕЙРОСЕТИ
    current_date = get_current_date()
    current_time = get_moscow_time().strftime('%H:%M')
    system_prompt = SUPER_SYSTEM_PROMPT.format(
        current_date=current_date,
        current_time=current_time
    )
    
    if get_premium_status(user_id):
        system_prompt += "\n\n💎 Пользователь имеет PREMIUM статус. Включи режим максимальной проработки!"
    if image_description:
        system_prompt += f"\n\n📸 На изображении: {image_description}"
    
    memories = recall(user_id, user_text)
    if memories:
        system_prompt += f"\n\n🧠 Что я помню об этом: {' '.join(memories[:2])}"
    
    results = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = []
        if GIGACHAT_AUTH_KEY:
            futures.append(executor.submit(generate_with_gigachat, user_text, system_prompt))
        futures.append(executor.submit(generate_with_yandexgpt, user_text, system_prompt))
        
        for future in as_completed(futures):
            try:
                result = future.result(timeout=2.5)
                if result and len(result) > 5:
                    results.append(result)
            except:
                pass
    
    if results:
        return results[0][:400]
    
    return generate_fallback_response(user_text, None)

# ============================================================
# КНОПКИ
# ============================================================
def main_menu():
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("📊 Статус", callback_data="status"),
        types.InlineKeyboardButton("💎 Premium", callback_data="premium"),
        types.InlineKeyboardButton("🎁 Тест Premium", callback_data="test"),
        types.InlineKeyboardButton("👤 Профиль", callback_data="profile"),
        types.InlineKeyboardButton("📊 Статистика", callback_data="stats"),
        types.InlineKeyboardButton("🧹 Очистить", callback_data="clear"),
        types.InlineKeyboardButton("❓ Помощь", callback_data="help"),
        types.InlineKeyboardButton("📩 Поддержка", callback_data="support"),
        types.InlineKeyboardButton("🎨 Сгенерировать", callback_data="draw")
    )
    return keyboard

def back_to_menu():
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")
    )
    return keyboard

def premium_menu(user_id):
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton(
            "💳 Оплатить Premium (100₽/мес)", 
            url="https://yoomoney.ru/quickpay/fundraise/button?billNumber=1JN0VV54CV0.260817&"
        ),
        types.InlineKeyboardButton("✅ Я оплатил", callback_data="i_paid"),
    )
    if get_premium_status(user_id) or is_admin(user_id) or user_id == OWNER_ID:
        keyboard.add(types.InlineKeyboardButton("📋 Что даёт Premium?", callback_data="premium_features"))
        keyboard.add(types.InlineKeyboardButton("🔄 Продлить Premium", callback_data="extend_premium"))
    keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu"))
    return keyboard

def admin_menu():
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("📊 Статистика сервера", callback_data="admin_stats"),
        types.InlineKeyboardButton("👥 Список админов", callback_data="admin_list"),
        types.InlineKeyboardButton("👥 Все пользователи", callback_data="admin_list_users"),
        types.InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast"),
        types.InlineKeyboardButton("💎 Заказы Premium", callback_data="admin_orders"),
        types.InlineKeyboardButton("📩 Обращения", callback_data="admin_support"),
        types.InlineKeyboardButton("💎 Выдать Premium", callback_data="admin_giveprem"),
        types.InlineKeyboardButton("🎁 Тест Premium", callback_data="admin_givetest"),
        types.InlineKeyboardButton("🚫 Забанить", callback_data="admin_ban"),
        types.InlineKeyboardButton("✅ Разбанить", callback_data="admin_unban"),
        types.InlineKeyboardButton("🔇 Замутить", callback_data="admin_mute"),
        types.InlineKeyboardButton("🔊 Размутить", callback_data="admin_unmute"),
        types.InlineKeyboardButton("👑 Выдать админа", callback_data="admin_giveadmin"),
        types.InlineKeyboardButton("👑 Забрать админа", callback_data="admin_deladmin"),
        types.InlineKeyboardButton("📊 Инфо о пользователе", callback_data="admin_info"),
        types.InlineKeyboardButton("📊 Статистика пользователей", callback_data="admin_stats_users"),
        types.InlineKeyboardButton("🧹 Обнулить сообщения", callback_data="admin_clear_messages"),
        types.InlineKeyboardButton("❌ Закрыть", callback_data="admin_close")
    )
    return keyboard

# ============================================================
# БОТ - КОМАНДЫ
# ============================================================
bot = telebot.TeleBot(TELEGRAM_TOKEN)

@bot.message_handler(commands=['start'])
def start(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    ensure_user(user_id, m.from_user.username or "unknown")
    
    text = (
        "✨ **ДОБРО ПОЖАЛОВАТЬ В AWESOME AI 2026!** ✨\n\n"
        f"🌸 **Привет, {m.from_user.first_name}!**\n\n"
        "🧠 **Меня создал гениальный AWESOME**\n\n"
        "⚡️ **ОТВЕЧАЮ ЗА 2-3 СЕКУНДЫ!**\n\n"
        "🌐 **ЧТО Я УМЕЮ:**\n"
        "• 🔍 Ищу в Google, Wikipedia, YouTube, Telegram, VK, Twitch\n"
        "• 💵 Показываю курс валют и криптовалют\n"
        "• 🧮 Решаю задачи любой сложности\n"
        "• 🐍 Помогаю с программированием\n"
        "• 📸 Анализирую изображения\n"
        "• 🎨 Генерирую картинки\n\n"
        "💎 **Premium: 100₽/месяц**\n"
        "🎁 **Тест Premium на 2 дня — всего 1 раз!**"
    )
    msg = bot.send_message(chat_id, text, reply_markup=main_menu(), parse_mode='Markdown')
    if user_id not in user_command_ids:
        user_command_ids[user_id] = []
    user_command_ids[user_id].append(m.message_id)
    user_command_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['help'])
def help_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    
    text = (
        "🧠 **AWESOME AI — ПОМОЩЬ**\n\n"
        "🌐 **Что я умею:**\n"
        "• 🔍 Ищу в Google, Wikipedia, YouTube, Telegram, VK, Twitch\n"
        "• 🌤 Погода с прогнозом\n"
        "• 💵 Курс валют и криптовалют\n"
        "• 🧮 Решаю математику\n"
        "• 🐍 Помогаю с программированием\n"
        "• 📸 Анализирую изображения\n"
        "• 🎨 Генерирую картинки\n\n"
        "📋 **Команды:**\n"
        "/start — Меню\n"
        "/help — Помощь\n"
        "/status — Статус\n"
        "/premium — Premium\n"
        "/test — Пробный Premium\n"
        "/profile — Профиль\n"
        "/stats — Статистика\n"
        "/clear — Очистить\n"
        "/draw — Сгенерировать картинку\n"
        "/support — Поддержка\n"
        "/feedback — Отзыв\n"
    )
    
    if is_authorized(user_id):
        text += (
            "\n🛡️ **АДМИН КОМАНДЫ:**\n"
            "/admin — Панель\n"
            "/giveprem [ID] [срок]\n"
            "/givetest [ID]\n"
            "/ban [ID] /unban [ID]\n"
            "/mute [ID] /unmute [ID]\n"
            "/giveadmin [ID] /deladmin [ID]\n"
            "/info [ID]\n"
            "/clear_messages [ID]\n"
            "/broadcast [текст]\n"
        )
    
    text += (
        f"\n💎 **Лимиты:**\n"
        f"🔓 Бесплатно — {FREE_LIMIT} сообщений/день\n"
        f"💎 Premium — ♾️ БЕЗЛИМИТНО"
    )
    
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='Markdown')
    if user_id not in user_command_ids:
        user_command_ids[user_id] = []
    user_command_ids[user_id].append(m.message_id)
    user_command_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['status'])
def status_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    
    if user_id == OWNER_ID:
        status_text = "👑 **ВЛАДЕЛЕЦ** — ♾️ БЕЗЛИМИТ!"
    elif is_admin(user_id):
        status_text = "👑 **АДМИН** — ♾️ БЕЗЛИМИТ!"
    else:
        premium = get_premium_status(user_id)
        user_data = get_db_user(user_id)
        messages = user_data.get('messages_today', 0) if user_data else 0
        
        if premium:
            expires = get_premium_expires(user_id)
            if expires:
                expires_formatted = format_date(expires)
                status_text = f"💎 **PREMIUM** (до {expires_formatted})"
            else:
                status_text = "💎 **PREMIUM**"
            status_text += f"\n📨 Лимит: ♾️ БЕЗЛИМИТНО"
        else:
            remaining = FREE_LIMIT - messages
            if remaining < 0:
                remaining = 0
            status_text = f"🔓 **Бесплатный**: осталось {remaining} из {FREE_LIMIT}"
    
    msg = bot.send_message(chat_id, f"📊 **ТВОЙ СТАТУС**\n\n{status_text}", reply_markup=back_to_menu(), parse_mode='Markdown')
    if user_id not in user_command_ids:
        user_command_ids[user_id] = []
    user_command_ids[user_id].append(m.message_id)
    user_command_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['premium'])
def premium_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    has_premium = get_premium_status(user_id)
    expires = get_premium_expires(user_id)
    
    if has_premium:
        if expires:
            expires_formatted = format_date(expires)
            text = f"💎 **У ТЕБЯ УЖЕ ЕСТЬ PREMIUM!**\n\n⏳ До: {expires_formatted}\n📨 Лимит: ♾️ БЕЗЛИМИТНО\n\n💰 100₽/месяц"
        else:
            text = "💎 **У ТЕБЯ УЖЕ ЕСТЬ PREMIUM!**\n\n📨 Лимит: ♾️ БЕЗЛИМИТНО\n\n💰 100₽/месяц"
    else:
        text = (
            f"💎 **PREMIUM AWESOME AI**\n\n"
            f"🔥 **ЧТО ТЫ ПОЛУЧАЕШЬ:**\n"
            f"♾️ **БЕЗЛИМИТНЫЕ СООБЩЕНИЯ**\n"
            f"🚀 Приоритетная обработка\n"
            f"🧠 Максимально глубокие ответы\n"
            f"💎 VIP-поддержка\n\n"
            f"💰 **Цена: 100₽/месяц**"
        )
    
    msg = bot.send_message(chat_id, text, reply_markup=premium_menu(user_id), parse_mode='Markdown')
    if user_id not in user_command_ids:
        user_command_ids[user_id] = []
    user_command_ids[user_id].append(m.message_id)
    user_command_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['test'])
def test_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT test_used, premium FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    
    if result is None:
        msg = bot.send_message(chat_id, "❌ Сначала напиши /start")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    test_used, premium = result
    
    if get_premium_status(user_id):
        msg = bot.send_message(chat_id, "💎 У тебя уже есть Premium!", reply_markup=premium_menu(user_id), parse_mode='Markdown')
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    if test_used == 1:
        msg = bot.send_message(chat_id, "⛔ Ты уже использовал тест Premium!\nКупи Premium: /premium", reply_markup=premium_menu(user_id), parse_mode='Markdown')
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    if set_premium(user_id, "2d"):
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('UPDATE users SET test_used = 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        
        msg = bot.send_message(
            chat_id, 
            f"🎉 **ПРОБНЫЙ PREMIUM АКТИВИРОВАН НА 2 ДНЯ!**\n\n"
            f"✅ Приоритетная обработка\n"
            f"✅ ♾️ БЕЗЛИМИТНЫЕ СООБЩЕНИЯ\n"
            f"✅ Более качественные ответы\n\n"
            f"⏳ Доступ активен 48 часов.\n"
            f"🔥 Наслаждайся!",
            reply_markup=premium_menu(user_id), 
            parse_mode='Markdown'
        )
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
    else:
        msg = bot.send_message(chat_id, "❌ Ошибка.")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['profile'])
def profile_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    
    user_data = get_db_user(user_id)
    if user_data:
        messages = user_data.get('messages_today', 0)
        expires = user_data.get('premium_expires')
        premium = user_data.get('premium', 0) == 1
        joined_at = user_data.get('joined_at', 'Неизвестно')
        is_owner = user_data.get('is_owner', 0) == 1
        is_admin_flag = user_data.get('is_admin', 0) == 1
    else:
        messages = 0
        expires = None
        premium = False
        joined_at = "Неизвестно"
        is_owner = False
        is_admin_flag = False
    
    has_premium = get_premium_status(user_id)
    
    if user_id == OWNER_ID or is_owner:
        status = "👑 ВЛАДЕЛЕЦ"
        limit_text = "♾️ Безлимит"
    elif is_admin_flag or is_admin(user_id):
        status = "👑 АДМИН"
        limit_text = "♾️ Безлимит"
    elif has_premium or premium:
        if expires:
            expires_formatted = format_date(expires)
            status = f"💎 PREMIUM (до {expires_formatted})"
        else:
            status = "💎 PREMIUM"
        limit_text = "♾️ Безлимит"
    else:
        remaining = FREE_LIMIT - messages
        if remaining < 0:
            remaining = 0
        status = f"🔓 Бесплатный ({remaining}/{FREE_LIMIT})"
        limit_text = f"{FREE_LIMIT}/день"
    
    username = m.from_user.username
    user_link = f"@{username}" if username else "Не указан"
    
    text = (
        f"👤 **ТВОЙ ПРОФИЛЬ**\n\n"
        f"🆔 ID: `{user_id}`\n"
        f"👤 Юзер: {user_link}\n"
        f"💎 Статус: {status}\n"
        f"📨 Лимит: {limit_text}\n"
        f"✉️ Сегодня: {messages}\n"
        f"📅 Вход: {joined_at or 'Неизвестно'} (МСК)"
    )
    
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='Markdown')
    if user_id not in user_command_ids:
        user_command_ids[user_id] = []
    user_command_ids[user_id].append(m.message_id)
    user_command_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['stats'])
def stats_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    
    if user_id == OWNER_ID or is_admin(user_id):
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT * FROM users')
        users = c.fetchall()
        conn.close()
        
        total_users = len(users)
        premium_users = 0
        admin_users = 0
        for user in users:
            if user[2] == 1:
                premium_users += 1
            if user[6] == 1:
                admin_users += 1
        
        text = (
            f"📊 **СТАТИСТИКА СЕРВЕРА**\n\n"
            f"👥 Всего: {total_users}\n"
            f"👑 Админов: {admin_users}\n"
            f"💎 Premium: {premium_users}\n"
            f"🔓 Бесплатных: {total_users - premium_users - admin_users}"
        )
    else:
        user_data = get_db_user(user_id)
        if user_data:
            messages_today = user_data.get('messages_today', 0)
            premium = get_premium_status(user_id)
            
            if premium:
                status = "💎 PREMIUM"
                limit_text = "♾️ Безлимит"
            else:
                remaining = FREE_LIMIT - messages_today
                if remaining < 0:
                    remaining = 0
                status = "🔓 Бесплатный"
                limit_text = f"{remaining}/{FREE_LIMIT}"
            
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('SELECT total_messages FROM total_stats WHERE user_id = ?', (user_id,))
            result = c.fetchone()
            conn.close()
            total = result[0] if result else 0
            
            text = (
                f"📊 **ТВОЯ СТАТИСТИКА**\n\n"
                f"👤 Статус: {status}\n"
                f"📨 Лимит: {limit_text}\n"
                f"✉️ Сегодня: {messages_today}\n"
                f"📊 Всего: {total}"
            )
        else:
            text = "❌ Не удалось получить данные."
    
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='Markdown')
    if user_id not in user_command_ids:
        user_command_ids[user_id] = []
    user_command_ids[user_id].append(m.message_id)
    user_command_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['clear'])
def clear_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    try:
        if user_id in user_command_ids:
            for msg_id in user_command_ids[user_id]:
                try:
                    bot.delete_message(chat_id, msg_id)
                except:
                    pass
            user_command_ids[user_id] = []
    except:
        pass
    msg = bot.send_message(chat_id, "🧹 **ИСТОРИЯ ОЧИЩЕНА**", reply_markup=back_to_menu(), parse_mode='Markdown')
    if user_id not in user_command_ids:
        user_command_ids[user_id] = []
    user_command_ids[user_id].append(m.message_id)
    user_command_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['draw'])
def draw_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    prompt = m.text.replace('/draw', '').strip()
    if not prompt:
        msg = bot.send_message(chat_id, "❌ /draw [описание]")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    if not can_send_message(user_id):
        msg = bot.send_message(chat_id, f"🔴 Лимит! Купи Premium: /premium")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    title = fix_title(prompt)
    msg = bot.send_message(chat_id, f"🎨 Генерирую: {title}... ⏳", parse_mode='Markdown')
    if user_id not in user_command_ids:
        user_command_ids[user_id] = []
    user_command_ids[user_id].append(m.message_id)
    user_command_ids[user_id].append(msg.message_id)
    
    image_data = generate_image(prompt)
    if image_data:
        increment_messages(user_id)
        try:
            bot.send_photo(chat_id, photo=image_data, caption=f"🎨 {title}\n\n✨ AWESOME AI", parse_mode='Markdown')
        except:
            msg = bot.send_message(chat_id, "⚠️ Ошибка при отправке")
            user_command_ids[user_id].append(msg.message_id)
    else:
        msg = bot.send_message(chat_id, "⚠️ Не удалось сгенерировать.")
        user_command_ids[user_id].append(msg.message_id)

def fix_title(prompt):
    title = prompt
    for word in ['нарисуй', 'сгенерируй', 'покажи', 'картинку', 'изображение', '/draw']:
        title = title.replace(word, '').strip()
    if not title or len(title) < 2:
        return "Картинка"
    return title[0].upper() + title[1:] if len(title) > 1 else title.upper()

def generate_image(prompt):
    try:
        clean_prompt = prompt
        for word in ['нарисуй', 'сгенерируй', 'покажи', 'картинку', 'изображение', '/draw']:
            clean_prompt = clean_prompt.replace(word, '').strip()
        if not clean_prompt:
            clean_prompt = prompt
        
        url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(clean_prompt)}?width=512&height=512&nologo=true"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=8)
        if response.status_code == 200 and len(response.content) > 1000:
            return response.content
    except:
        pass
    return None

def is_image_generation(text):
    image_keywords = ['нарисуй', 'покажи', 'картинку', 'изображение']
    return any(kw in text.lower() for kw in image_keywords)

@bot.message_handler(commands=['support'])
def support_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    text = m.text.replace('/support', '').strip()
    if not text:
        msg = bot.send_message(chat_id, "📩 /support [текст]", parse_mode='Markdown')
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    if use_supabase:
        try:
            supabase.table('support_requests').insert({
                'user_id': user_id,
                'username': m.from_user.username or "unknown",
                'text': text,
                'created_at': get_moscow_time().strftime('%d.%m.%Y %H:%M')
            }).execute()
        except:
            pass
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('INSERT INTO support_requests (user_id, username, text, created_at) VALUES (?, ?, ?, ?)',
                  (user_id, m.from_user.username or "unknown", text, get_moscow_time().strftime('%d.%m.%Y %H:%M')))
        conn.commit()
        conn.close()
    
    msg = bot.send_message(chat_id, "✅ Обращение отправлено!", parse_mode='Markdown')
    if user_id not in user_command_ids:
        user_command_ids[user_id] = []
    user_command_ids[user_id].append(m.message_id)
    user_command_ids[user_id].append(msg.message_id)
    try:
        bot.send_message(OWNER_ID, f"📩 НОВОЕ ОБРАЩЕНИЕ!\n\n👤 @{m.from_user.username or 'Не указан'}\n📝 {text}", parse_mode='Markdown')
    except:
        pass

@bot.message_handler(commands=['feedback'])
def feedback_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    text = m.text.replace('/feedback', '').strip()
    if not text:
        msg = bot.send_message(chat_id, "📝 /feedback [текст]", parse_mode='Markdown')
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    msg = bot.send_message(chat_id, "✅ Спасибо за отзыв! ❤️", parse_mode='Markdown')
    if user_id not in user_command_ids:
        user_command_ids[user_id] = []
    user_command_ids[user_id].append(m.message_id)
    user_command_ids[user_id].append(msg.message_id)
    try:
        bot.send_message(OWNER_ID, f"📝 НОВЫЙ ОТЗЫВ!\n\n👤 @{m.from_user.username or 'Не указан'}\n📝 {text}", parse_mode='Markdown')
    except:
        pass

@bot.message_handler(commands=['admin'])
def admin_panel(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    if not is_authorized(user_id):
        msg = bot.send_message(chat_id, "❌ Нет прав!")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    msg = bot.send_message(chat_id, "🛡️ **АДМИН-ПАНЕЛЬ**", reply_markup=admin_menu(), parse_mode='Markdown')
    if user_id not in user_command_ids:
        user_command_ids[user_id] = []
    user_command_ids[user_id].append(m.message_id)
    user_command_ids[user_id].append(msg.message_id)

# ============================================================
# АДМИН КОМАНДЫ
# ============================================================
@bot.message_handler(commands=['giveprem'])
def giveprem_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    if not is_authorized(user_id):
        msg = bot.send_message(chat_id, "❌ Нет прав!")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    args = m.text.split()[1:]
    if len(args) < 2:
        msg = bot.send_message(chat_id, "❌ /giveprem [ID] [срок]\nСрок: 1d, 7d, 1mes, 1y")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    try:
        target_id = int(args[0])
        duration = args[1]
    except:
        msg = bot.send_message(chat_id, "❌ Неверный ID")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    if set_premium(target_id, duration):
        expires = get_premium_expires(target_id)
        expires_formatted = format_date(expires)
        msg = bot.send_message(chat_id, f"✅ Premium выдан пользователю {target_id}!\n⏳ До: {expires_formatted}", parse_mode='Markdown')
        try:
            bot.send_message(target_id, f"🎉 ВАМ ВЫДАН PREMIUM!\n⏳ Действует до: {expires_formatted}", parse_mode='Markdown')
        except:
            pass
    else:
        msg = bot.send_message(chat_id, "❌ Ошибка при выдаче Premium")
    
    if user_id not in user_command_ids:
        user_command_ids[user_id] = []
    user_command_ids[user_id].append(m.message_id)
    user_command_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['givetest'])
def givetest_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    if not is_authorized(user_id):
        msg = bot.send_message(chat_id, "❌ Нет прав!")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    args = m.text.split()[1:]
    if len(args) < 1:
        msg = bot.send_message(chat_id, "❌ /givetest [ID]")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    try:
        target_id = int(args[0])
    except:
        msg = bot.send_message(chat_id, "❌ Неверный ID")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    if set_premium(target_id, "2d"):
        expires = get_premium_expires(target_id)
        expires_formatted = format_date(expires)
        msg = bot.send_message(chat_id, f"✅ Тест Premium выдан пользователю {target_id}!\n⏳ До: {expires_formatted}", parse_mode='Markdown')
        try:
            bot.send_message(target_id, f"🎉 ВАМ ВЫДАН ТЕСТ PREMIUM НА 2 ДНЯ!\n⏳ Действует до: {expires_formatted}", parse_mode='Markdown')
        except:
            pass
    else:
        msg = bot.send_message(chat_id, "❌ Ошибка при выдаче теста")
    
    if user_id not in user_command_ids:
        user_command_ids[user_id] = []
    user_command_ids[user_id].append(m.message_id)
    user_command_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['ban'])
def ban_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    if not is_authorized(user_id):
        msg = bot.send_message(chat_id, "❌ Нет прав!")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    args = m.text.split()[1:]
    if len(args) < 1:
        msg = bot.send_message(chat_id, "❌ /ban [ID]")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    try:
        target_id = int(args[0])
    except:
        msg = bot.send_message(chat_id, "❌ Неверный ID")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    if target_id == OWNER_ID:
        msg = bot.send_message(chat_id, "❌ Нельзя забанить владельца!")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    ban_user(target_id)
    msg = bot.send_message(chat_id, f"✅ Пользователь {target_id} забанен!", parse_mode='Markdown')
    try:
        bot.send_message(target_id, "🚫 ВЫ ЗАБАНЕНЫ!", parse_mode='Markdown')
    except:
        pass
    
    if user_id not in user_command_ids:
        user_command_ids[user_id] = []
    user_command_ids[user_id].append(m.message_id)
    user_command_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['unban'])
def unban_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    if not is_authorized(user_id):
        msg = bot.send_message(chat_id, "❌ Нет прав!")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    args = m.text.split()[1:]
    if len(args) < 1:
        msg = bot.send_message(chat_id, "❌ /unban [ID]")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    try:
        target_id = int(args[0])
    except:
        msg = bot.send_message(chat_id, "❌ Неверный ID")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    unban_user(target_id)
    msg = bot.send_message(chat_id, f"✅ Пользователь {target_id} разбанен!", parse_mode='Markdown')
    try:
        bot.send_message(target_id, "✅ ВЫ РАЗБАНЕНЫ!", parse_mode='Markdown')
    except:
        pass
    
    if user_id not in user_command_ids:
        user_command_ids[user_id] = []
    user_command_ids[user_id].append(m.message_id)
    user_command_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['mute'])
def mute_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    if not is_authorized(user_id):
        msg = bot.send_message(chat_id, "❌ Нет прав!")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    args = m.text.split()[1:]
    if len(args) < 1:
        msg = bot.send_message(chat_id, "❌ /mute [ID]")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    try:
        target_id = int(args[0])
    except:
        msg = bot.send_message(chat_id, "❌ Неверный ID")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    if target_id == OWNER_ID:
        msg = bot.send_message(chat_id, "❌ Нельзя замутить владельца!")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    mute_user(target_id)
    msg = bot.send_message(chat_id, f"✅ Пользователь {target_id} замучен!", parse_mode='Markdown')
    try:
        bot.send_message(target_id, "🔇 ВЫ ЗАМУЧЕНЫ!", parse_mode='Markdown')
    except:
        pass
    
    if user_id not in user_command_ids:
        user_command_ids[user_id] = []
    user_command_ids[user_id].append(m.message_id)
    user_command_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['unmute'])
def unmute_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    if not is_authorized(user_id):
        msg = bot.send_message(chat_id, "❌ Нет прав!")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    args = m.text.split()[1:]
    if len(args) < 1:
        msg = bot.send_message(chat_id, "❌ /unmute [ID]")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    try:
        target_id = int(args[0])
    except:
        msg = bot.send_message(chat_id, "❌ Неверный ID")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    unmute_user(target_id)
    msg = bot.send_message(chat_id, f"✅ Пользователь {target_id} размучен!", parse_mode='Markdown')
    try:
        bot.send_message(target_id, "🔊 ВЫ РАЗМУЧЕНЫ!", parse_mode='Markdown')
    except:
        pass
    
    if user_id not in user_command_ids:
        user_command_ids[user_id] = []
    user_command_ids[user_id].append(m.message_id)
    user_command_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['giveadmin'])
def giveadmin_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    if not is_authorized(user_id):
        msg = bot.send_message(chat_id, "❌ Нет прав!")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    args = m.text.split()[1:]
    if len(args) < 1:
        msg = bot.send_message(chat_id, "❌ /giveadmin [ID]")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    try:
        target_id = int(args[0])
    except:
        msg = bot.send_message(chat_id, "❌ Неверный ID")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    set_admin(target_id, True)
    msg = bot.send_message(chat_id, f"✅ Пользователь {target_id} стал админом!", parse_mode='Markdown')
    try:
        bot.send_message(target_id, "👑 ВЫ СТАЛИ АДМИНОМ!", parse_mode='Markdown')
    except:
        pass
    
    if user_id not in user_command_ids:
        user_command_ids[user_id] = []
    user_command_ids[user_id].append(m.message_id)
    user_command_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['deladmin'])
def deladmin_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    if not is_authorized(user_id):
        msg = bot.send_message(chat_id, "❌ Нет прав!")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return  # ← ЭТО ВНУТРИ ФУНКЦИИ - НОРМАЛЬНО
    
    args = m.text.split()[1:]
    if len(args) < 1:
        msg = bot.send_message(chat_id, "❌ /deladmin [ID]")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return  # ← ЭТО ВНУТРИ ФУНКЦИИ - НОРМАЛЬНО
    
    try:
        target_id = int(args[0])
    except:
        msg = bot.send_message(chat_id, "❌ Неверный ID")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    if target_id == OWNER_ID:
    msg = bot.send_message(chat_id, "⚠️ Нельзя забрать админку у владельца!")
    if user_id not in user_command_ids:
        user_command_ids[user_id] = []   # ← СДЕЛАЙ ОТСТУП!
    user_command_ids[user_id].append(m.message_id)
    user_command_ids[user_id].append(msg.message_id)
    return   # ← ЭТОТ return ВНУТРИ if - НОРМАЛЬНО

set_admin(target_id, False)   # ← ЭТОТ КОД ВЫПОЛНИТСЯ
msg = bot.send_message(chat_id, f"👋 У пользователя {target_id} забрали админку!", parse_mode='Markdown')
try:
    bot.send_message(target_id, "👋 У ВАС ЗАБРАЛИ АДМИНКУ!", parse_mode='Markdown')
except:
    pass

if user_id not in user_command_ids:
    user_command_ids[user_id] = []
    user_command_ids[user_id].append(m.message_id)
    user_command_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['info'])  # ← ИСПРАВЛЕНО!
def info_cmd(m):
    # код функции info_cmd
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    if not is_authorized(user_id):
        msg = bot.send_message(chat_id, "❌ Нет прав!")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    args = m.text.split()[1:]
    if len(args) < 1:
        msg = bot.send_message(chat_id, "❌ /info [ID]")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    try:
        target_id = int(args[0])
    except:
        msg = bot.send_message(chat_id, "❌ Неверный ID")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    user_data = get_db_user(target_id)
    if user_data:
        messages = user_data.get('messages_today', 0)
        premium = user_data.get('premium', 0) == 1
        expires = user_data.get('premium_expires')
        joined_at = user_data.get('joined_at', 'Неизвестно')
        is_admin_flag = user_data.get('is_admin', 0) == 1
        is_owner = user_data.get('is_owner', 0) == 1
        
        status = "👑 ВЛАДЕЛЕЦ" if is_owner else "👑 АДМИН" if is_admin_flag else "💎 PREMIUM" if premium else "🔓 Бесплатный"
        expires_text = f"до {format_date(expires)}" if expires and premium else "нет"
        
        text = (
            f"📊 **ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ**\n\n"
            f"🆔 ID: `{target_id}`\n"
            f"💎 Статус: {status}\n"
            f"📨 Премиум: {expires_text}\n"
            f"✉️ Сегодня: {messages}\n"
            f"📅 Вход: {joined_at or 'Неизвестно'}"
        )
    else:
        text = f"❌ Пользователь {target_id} не найден"
    
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='Markdown')
    if user_id not in user_command_ids:
        user_command_ids[user_id] = []
    user_command_ids[user_id].append(m.message_id)
    user_command_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['clear_messages'])
def clear_messages_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    if not is_authorized(user_id):
        msg = bot.send_message(chat_id, "❌ Нет прав!")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    args = m.text.split()[1:]
    if len(args) < 1:
        msg = bot.send_message(chat_id, "❌ /clear_messages [ID]")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    try:
        target_id = int(args[0])
    except:
        msg = bot.send_message(chat_id, "❌ Неверный ID")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    if use_supabase:
        try:
            supabase.table('users').update({'messages_today': 0}).eq('user_id', target_id).execute()
        except:
            pass
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('UPDATE users SET messages_today = 0 WHERE user_id = ?', (target_id,))
        conn.commit()
        conn.close()
    
    msg = bot.send_message(chat_id, f"✅ Сообщения пользователя {target_id} обнулены!", parse_mode='Markdown')
    try:
        bot.send_message(target_id, f"🧹 ВАШИ СООБЩЕНИЯ ОБНУЛЕНЫ!", parse_mode='Markdown')
    except:
        pass
    
    if user_id not in user_command_ids:
        user_command_ids[user_id] = []
    user_command_ids[user_id].append(m.message_id)
    user_command_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['broadcast'])
def broadcast_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    if not is_authorized(user_id):
        msg = bot.send_message(chat_id, "❌ Нет прав!")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    text = m.text.replace('/broadcast', '').strip()
    if not text:
        msg = bot.send_message(chat_id, "❌ /broadcast [текст]")
        if user_id not in user_command_ids:
            user_command_ids[user_id] = []
        user_command_ids[user_id].append(m.message_id)
        user_command_ids[user_id].append(msg.message_id)
        return
    
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("✅ Отправить", callback_data=f"confirm_broadcast:{text}"),
        types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_broadcast")
    )
    
    msg = bot.send_message(chat_id, f"📢 **ПОДТВЕРДИТЕ РАССЫЛКУ**\n\n{text}", reply_markup=keyboard, parse_mode='Markdown')
    if user_id not in user_command_ids:
        user_command_ids[user_id] = []
    user_command_ids[user_id].append(m.message_id)
    user_command_ids[user_id].append(msg.message_id)

# ============================================================
# ОБРАБОТЧИК СООБЩЕНИЙ
# ============================================================
@bot.message_handler(func=lambda m: True)
def handle_all_messages(m):
    try:
        chat_id = m.chat.id
        user_id = m.from_user.id
        text = m.text.strip() if m.text else ""
        
        if text.startswith('/'):
            return
        
        if is_banned(user_id):
            bot.send_message(chat_id, "🚫 Ты забанен!")
            return
        
        if is_muted(user_id):
            bot.send_message(chat_id, "🔇 Ты замучен!")
            return
        
        if check_spam(user_id):
            return
        
        ensure_user(user_id, m.from_user.username or "unknown")
        
        if not can_send_message(user_id):
            user_data = get_db_user(user_id)
            messages = user_data.get('messages_today', 0) if user_data else 0
            remaining = FREE_LIMIT - messages
            if remaining < 0:
                remaining = 0
            bot.send_message(
                chat_id,
                f"🔴 Лимит! Осталось: {remaining}/{FREE_LIMIT}\n💎 /premium",
                reply_markup=premium_menu(user_id),
                parse_mode='Markdown'
            )
            return
        
        if m.photo:
            try:
                file_id = m.photo[-1].file_id
                file_info = bot.get_file(file_id)
                file_content = bot.download_file(file_info.file_path)
                img = Image.open(io.BytesIO(file_content))
                width, height = img.size
                img_desc = f"📸 {width}×{height}"
                response = process_message(user_id, text or "Что на картинке?", img_desc)
                increment_messages(user_id)
                bot.send_message(chat_id, response, reply_markup=back_to_menu(), parse_mode='Markdown')
            except Exception as e:
                bot.send_message(chat_id, f"⚠️ Ошибка: {e}")
            return
        
        if text:
            if is_image_generation(text):
                draw_cmd(m)
                return
            
            bot.send_chat_action(chat_id, 'typing')
            
            start_time = time.time()
            response = process_message(user_id, text)
            elapsed = time.time() - start_time
            
            if response:
                increment_messages(user_id)
                bot.send_message(
                    chat_id,
                    response,
                    reply_markup=back_to_menu(),
                    parse_mode='Markdown'
                )
                print(f"✅ Ответ за {elapsed:.1f}с")
            else:
                bot.send_message(
                    chat_id,
                    "❌ Не удалось обработать.",
                    reply_markup=back_to_menu(),
                    parse_mode='Markdown'
                )
    except Exception as e:
        print(f"❌ Ошибка: {e}")

# ============================================================
# ОБРАБОТЧИК КНОПОК
# ============================================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    try:
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except:
            pass
        
        try:
            bot.answer_callback_query(call.id)
        except:
            pass
        
        ensure_user(user_id, call.from_user.username or "unknown")
        
        if call.data == "status":
            status_cmd(call.message)
            return
        if call.data == "premium":
            premium_cmd(call.message)
            return
        if call.data == "test":
            test_cmd(call.message)
            return
        if call.data == "profile":
            profile_cmd(call.message)
            return
        if call.data == "stats":
            stats_cmd(call.message)
            return
        if call.data == "clear":
            clear_cmd(call.message)
            return
        if call.data == "help":
            help_cmd(call.message)
            return
        if call.data == "support":
            msg = bot.send_message(chat_id, "📩 /support [текст]", parse_mode='Markdown')
            if user_id not in user_command_ids:
                user_command_ids[user_id] = []
            user_command_ids[user_id].append(msg.message_id)
            return
        if call.data == "draw":
            msg = bot.send_message(chat_id, "🎨 /draw [описание]", parse_mode='Markdown')
            if user_id not in user_command_ids:
                user_command_ids[user_id] = []
            user_command_ids[user_id].append(msg.message_id)
            return
        if call.data == "back_to_menu":
            start(call.message)
            return
        
        if call.data == "premium_features":
            if not get_premium_status(user_id) and not is_admin(user_id) and user_id != OWNER_ID:
                msg = bot.send_message(chat_id, "❌ Только Premium!", reply_markup=back_to_menu(), parse_mode='Markdown')
                if user_id not in user_command_ids:
                    user_command_ids[user_id] = []
                user_command_ids[user_id].append(msg.message_id)
                return
            text = (
                f"💎 **PREMIUM AWESOME AI**\n\n"
                f"🔥 **ЧТО ТЫ ПОЛУЧАЕШЬ:**\n"
                f"♾️ **БЕЗЛИМИТНЫЕ СООБЩЕНИЯ**\n"
                f"🚀 Приоритетная обработка\n"
                f"🧠 Максимально глубокие ответы\n"
                f"💎 VIP-поддержка\n\n"
                f"💰 **Цена: 100₽/месяц**"
            )
            msg = bot.send_message(chat_id, text, reply_markup=premium_menu(user_id), parse_mode='Markdown')
            if user_id not in user_command_ids:
                user_command_ids[user_id] = []
            user_command_ids[user_id].append(msg.message_id)
            return
        
        if call.data == "extend_premium":
            if not get_premium_status(user_id) and user_id != OWNER_ID:
                msg = bot.send_message(chat_id, "❌ У тебя нет Premium!", reply_markup=back_to_menu(), parse_mode='Markdown')
                if user_id not in user_command_ids:
                    user_command_ids[user_id] = []
                user_command_ids[user_id].append(msg.message_id)
                return
            
            if use_supabase:
                try:
                    supabase.table('premium_orders').insert({
                        'user_id': user_id,
                        'status': 'pending',
                        'created_at': get_moscow_time().strftime('%d.%m.%Y %H:%M')
                    }).execute()
                    response = supabase.table('premium_orders').select('order_id').eq('user_id', user_id).order('order_id', desc=True).limit(1).execute()
                    order_id = response.data[0]['order_id'] if response.data else None
                except:
                    order_id = None
            else:
                conn = sqlite3.connect('users.db')
                c = conn.cursor()
                c.execute('INSERT INTO premium_orders (user_id, status, created_at) VALUES (?, ?, ?)',
                          (user_id, 'pending', get_moscow_time().strftime('%d.%m.%Y %H:%M')))
                order_id = c.lastrowid
                conn.commit()
                conn.close()
            
            expires = get_premium_expires(user_id)
            expires_text = f"до {format_date(expires)}" if expires else "неизвестно"
            
            msg = bot.send_message(chat_id, 
                f"✅ **ЗАКАЗ НА ПРОДЛЕНИЕ ОТПРАВЛЕН!**\n\n"
                f"🆔 #{order_id}\n"
                f"⏳ {expires_text}\n"
                f"⏳ Ожидай подтверждения.", 
                reply_markup=back_to_menu(),
                parse_mode='Markdown'
            )
            if user_id not in user_command_ids:
                user_command_ids[user_id] = []
            user_command_ids[user_id].append(msg.message_id)
            
            keyboard = types.InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_order:{order_id}"),
                types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_order:{order_id}")
            )
            try:
                bot.send_message(
                    OWNER_ID, 
                    f"💳 **ЗАКАЗ НА ПРОДЛЕНИЕ!**\n\n"
                    f"🆔 #{order_id}\n"
                    f"👤 @{call.from_user.username or 'Не указан'}\n"
                    f"💰 100₽\n"
                    f"📌 ПРОДЛЕНИЕ", 
                    reply_markup=keyboard, 
                    parse_mode='Markdown'
                )
            except:
                pass
            return
        
        if call.data == "i_paid":
            has_premium = get_premium_status(user_id)
            
            if use_supabase:
                try:
                    try:
                        supabase.table('premium_orders').select('*').limit(1).execute()
                    except:
                        supabase.sql("""
                            CREATE TABLE IF NOT EXISTS premium_orders (
                                order_id SERIAL PRIMARY KEY,
                                user_id BIGINT,
                                status TEXT DEFAULT 'pending',
                                created_at TEXT
                            )
                        """).execute()
                    
                    supabase.table('premium_orders').insert({
                        'user_id': user_id,
                        'status': 'pending',
                        'created_at': get_moscow_time().strftime('%d.%m.%Y %H:%M')
                    }).execute()
                    
                    response = supabase.table('premium_orders').select('order_id').eq('user_id', user_id).order('order_id', desc=True).limit(1).execute()
                    order_id = response.data[0]['order_id'] if response.data else None
                except:
                    order_id = None
            else:
                conn = sqlite3.connect('users.db')
                c = conn.cursor()
                c.execute('INSERT INTO premium_orders (user_id, status, created_at) VALUES (?, ?, ?)',
                          (user_id, 'pending', get_moscow_time().strftime('%d.%m.%Y %H:%M')))
                order_id = c.lastrowid
                conn.commit()
                conn.close()
            
            order_type = "ПРОДЛЕНИЕ" if has_premium else "ПОКУПКА"
            expires = get_premium_expires(user_id)
            expires_text = f"до {format_date(expires)}" if expires and has_premium else "отсутствует"
            
            msg = bot.send_message(chat_id, 
                f"✅ **ЗАКАЗ ОТПРАВЛЕН!**\n\n"
                f"🆔 #{order_id}\n"
                f"📌 {order_type}\n"
                f"⏳ {expires_text}\n"
                f"⏳ Ожидай подтверждения.", 
                reply_markup=back_to_menu(),
                parse_mode='Markdown'
            )
            if user_id not in user_command_ids:
                user_command_ids[user_id] = []
            user_command_ids[user_id].append(msg.message_id)
            
            keyboard = types.InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_order:{order_id}"),
                types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_order:{order_id}")
            )
            try:
                bot.send_message(
                    OWNER_ID, 
                    f"💳 **НОВЫЙ ЗАКАЗ!**\n\n"
                    f"🆔 #{order_id}\n"
                    f"👤 @{call.from_user.username or 'Не указан'}\n"
                    f"💰 100₽\n"
                    f"📌 {order_type}", 
                    reply_markup=keyboard, 
                    parse_mode='Markdown'
                )
            except:
                pass
            return
        
        # АДМИН КНОПКИ
        if call.data == "admin_stats":
            stats_cmd(call.message)
            return
        if call.data == "admin_list":
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('SELECT user_id, username FROM users WHERE is_admin = 1')
            admins = c.fetchall()
            conn.close()
            if not admins:
                text = "👑 **АДМИНЫ**\n\nНет админов."
            else:
                text = "👑 **АДМИНЫ**\n\n"
                for admin in admins:
                    text += f"• @{admin[1] if admin[1] else admin[0]}\n"
            msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='Markdown')
            if user_id not in user_command_ids:
                user_command_ids[user_id] = []
            user_command_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_list_users":
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('SELECT user_id, username, premium, is_admin FROM users ORDER BY user_id')
            users = c.fetchall()
            conn.close()
            text = "👥 **СПИСОК ПОЛЬЗОВАТЕЛЕЙ**\n\n"
            for user in users:
                uid, username, premium, is_admin_flag = user
                status = "👑 ВЛАДЕЛЕЦ" if uid == OWNER_ID else "👑 АДМИН" if is_admin_flag == 1 else "💎 PREMIUM" if premium == 1 else "🔓 Бесплатный"
                text += f"• @{username if username and username != 'unknown' else 'Не указан'} | ID: `{uid}` | {status}\n"
            msg = bot.send_message(chat_id, text[:4000], reply_markup=back_to_menu(), parse_mode='Markdown')
            if user_id not in user_command_ids:
                user_command_ids[user_id] = []
            user_command_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_broadcast":
            msg = bot.send_message(chat_id, "📢 /broadcast [текст]", parse_mode='Markdown')
            if user_id not in user_command_ids:
                user_command_ids[user_id] = []
            user_command_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_giveprem":
            msg = bot.send_message(chat_id, "💎 /giveprem [ID] [срок]", parse_mode='Markdown')
            if user_id not in user_command_ids:
                user_command_ids[user_id] = []
            user_command_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_givetest":
            msg = bot.send_message(chat_id, "🎁 /givetest [ID]", parse_mode='Markdown')
            if user_id not in user_command_ids:
                user_command_ids[user_id] = []
            user_command_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_ban":
            msg = bot.send_message(chat_id, "🚫 /ban [ID]", parse_mode='Markdown')
            if user_id not in user_command_ids:
                user_command_ids[user_id] = []
            user_command_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_unban":
            msg = bot.send_message(chat_id, "✅ /unban [ID]", parse_mode='Markdown')
            if user_id not in user_command_ids:
                user_command_ids[user_id] = []
            user_command_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_mute":
            msg = bot.send_message(chat_id, "🔇 /mute [ID]", parse_mode='Markdown')
            if user_id not in user_command_ids:
                user_command_ids[user_id] = []
            user_command_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_unmute":
            msg = bot.send_message(chat_id, "🔊 /unmute [ID]", parse_mode='Markdown')
            if user_id not in user_command_ids:
                user_command_ids[user_id] = []
            user_command_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_giveadmin":
            msg = bot.send_message(chat_id, "👑 /giveadmin [ID]", parse_mode='Markdown')
            if user_id not in user_command_ids:
                user_command_ids[user_id] = []
            user_command_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_deladmin":
            msg = bot.send_message(chat_id, "👑 /deladmin [ID]", parse_mode='Markdown')
            if user_id not in user_command_ids:
                user_command_ids[user_id] = []
            user_command_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_info":
            msg = bot.send_message(chat_id, "📊 /info [ID]", parse_mode='Markdown')
            if user_id not in user_command_ids:
                user_command_ids[user_id] = []
            user_command_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_stats_users":
            stats_cmd(call.message)
            return
        if call.data == "admin_clear_messages":
            msg = bot.send_message(chat_id, "🧹 /clear_messages [ID]", parse_mode='Markdown')
            if user_id not in user_command_ids:
                user_command_ids[user_id] = []
            user_command_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_close":
            msg = bot.send_message(chat_id, "❌ Закрыто", reply_markup=back_to_menu(), parse_mode='Markdown')
            if user_id not in user_command_ids:
                user_command_ids[user_id] = []
            user_command_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_orders":
            admin_orders_cmd(call.message, user_id)
            return
        if call.data == "admin_support":
            admin_support_cmd(call.message, user_id)
            return
        
        # ЗАКАЗЫ
        if call.data.startswith("confirm_order:"):
            if not is_authorized(user_id):
                return
            order_id = int(call.data.replace("confirm_order:", ""))
            
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('SELECT user_id, status FROM premium_orders WHERE order_id = ?', (order_id,))
            result = c.fetchone()
            conn.close()
            if not result or result[1] != 'pending':
                return
            
            target_user = result[0]
            new_expires = add_month_to_premium(target_user)
            
            if new_expires:
                conn = sqlite3.connect('users.db')
                c = conn.cursor()
                c.execute('UPDATE premium_orders SET status = "confirmed" WHERE order_id = ?', (order_id,))
                conn.commit()
                conn.close()
                
                try:
                    bot.send_message(chat_id, f"✅ Заказ #{order_id} подтверждён!", parse_mode='Markdown')
                except:
                    pass
                
                expires_formatted = format_date(new_expires)
                try:
                    bot.send_message(target_user, f"🎉 **PREMIUM АКТИВИРОВАН!**\n✅ Заказ #{order_id}\n💎 До: {expires_formatted}", parse_mode='Markdown')
                except:
                    pass
            return
        
        if call.data.startswith("reject_order:"):
            if not is_authorized(user_id):
                return
            order_id = int(call.data.replace("reject_order:", ""))
            
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('SELECT user_id FROM premium_orders WHERE order_id = ? AND status = "pending"', (order_id,))
            result = c.fetchone()
            conn.close()
            if not result:
                return
            
            target_user = result[0]
            
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('UPDATE premium_orders SET status = "rejected" WHERE order_id = ?', (order_id,))
            conn.commit()
            conn.close()
            
            try:
                bot.send_message(chat_id, f"❌ Заказ #{order_id} отклонён!", parse_mode='Markdown')
            except:
                pass
            try:
                bot.send_message(target_user, f"❌ **ЗАКАЗ #{order_id} ОТКЛОНЁН**", parse_mode='Markdown')
            except:
                pass
            return
        
        if call.data.startswith("confirm_broadcast:"):
            if not is_authorized(user_id):
                return
            text = call.data.replace("confirm_broadcast:", "")
            
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('SELECT user_id FROM users')
            users = c.fetchall()
            conn.close()
            
            sent = 0
            failed = 0
            for user in users:
                try:
                    bot.send_message(user[0], f"📢 **ОБЪЯВЛЕНИЕ**\n\n{text}", parse_mode='Markdown')
                    sent += 1
                    time.sleep(0.05)
                except:
                    failed += 1
            bot.send_message(chat_id, f"✅ **РАССЫЛКА!**\n\n📤 {sent}\n❌ {failed}", parse_mode='Markdown')
            return
        
        if call.data == "cancel_broadcast":
            bot.send_message(chat_id, "❌ Отменено.", parse_mode='Markdown')
            return
        
    except Exception as e:
        print(f"❌ Ошибка в callback: {e}")

# ============================================================
# АДМИН ВСПОМОГАТЕЛЬНЫЕ
# ============================================================
def admin_orders_cmd(message, user_id):
    chat_id = message.chat.id
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT order_id, user_id, created_at FROM premium_orders WHERE status = "pending" ORDER BY order_id DESC')
    orders = c.fetchall()
    conn.close()
    
    if not orders:
        text = "💳 **ЗАКАЗЫ PREMIUM**\n\nНет активных заказов."
    else:
        text = f"💳 **ЗАКАЗЫ PREMIUM**\n\nВсего: {len(orders)}\n\n"
        for order in orders:
            text += f"🆔 #{order[0]} | 👤 {order[1]} | 📅 {order[2]}\n"
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='Markdown')
    if user_id not in user_command_ids:
        user_command_ids[user_id] = []
    user_command_ids[user_id].append(msg.message_id)

def admin_support_cmd(message, user_id):
    chat_id = message.chat.id
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT request_id, user_id, username, text, created_at FROM support_requests WHERE status = "pending" ORDER BY request_id DESC')
    requests = c.fetchall()
    conn.close()
    
    if not requests:
        text = "📩 **ОБРАЩЕНИЯ**\n\nНет активных обращений."
    else:
        text = f"📩 **ОБРАЩЕНИЯ**\n\nВсего: {len(requests)}\n\n"
        for req in requests:
            text += f"🆔 #{req[0]} | @{req[2] or 'Не указан'} | {req[4]}\n📝 {req[3][:50]}...\n\n"
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='Markdown')
    if user_id not in user_command_ids:
        user_command_ids[user_id] = []
    user_command_ids[user_id].append(msg.message_id)

# ============================================================
# KEEP-ALIVE
# ============================================================
def keep_alive():
    while True:
        time.sleep(300)
        try:
            bot.get_me()
            print("💓 Keep-alive пинг")
        except:
            pass

keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
keep_alive_thread.start()

# ============================================================
# ЗАПУСК
# ============================================================
init_db()
init_memory_db()

print("=" * 60)
print("🧠 AWESOME AI 2026 — СУПЕР-БЫСТРЫЙ!")
print("=" * 60)
print(f"⏱️ ТАЙМАУТЫ:")
print(f"   GigaChat (ОСНОВНОЙ): {GIGACHAT_TIMEOUT} сек")
print(f"   YandexGPT (БАЗА): {YANDEXGPT_TIMEOUT} сек")
print(f"   Поиск: {SEARCH_TIMEOUT} сек")
print(f"   Погода: {WEATHER_TIMEOUT} сек")
print("=" * 60)
print("🌐 ИСТОЧНИКИ:")
print("✅ Google")
print("✅ Wikipedia")
print("✅ YouTube")
print("✅ Telegram")
print("✅ ВКонтакте")
print("✅ Twitch")
print("✅ Новости")
print("✅ GigaChat (ОСНОВНОЙ)")
print("✅ YandexGPT (БАЗА)")
print("=" * 60)
print("💡 КОМАНДЫ И КНОПКИ — МГНОВЕННЫЕ (БЕЗ НЕЙРОСЕТЕЙ)")
print("💓 KEEP-ALIVE ВКЛЮЧЕН (не засыпает)")
print("=" * 60)
try:
    print(f"🤖 Бот: @{bot.get_me().username}")
except:
    print("🤖 Бот: @unknown")
print("=" * 60)

print("✅ БОТ ГОТОВ К ЗАПУСКУ!")
print("=" * 60)

try:
    bot.remove_webhook()
    print("✅ Webhook сброшен")
    time.sleep(1)
except:
    pass

if __name__ == "__main__":
    while True:
        try:
            try:
                bot.stop_polling()
            except:
                pass
            time.sleep(1)
            
            print("🚀 Бот запускается...")
            bot.polling(
                none_stop=True,
                timeout=30,
                long_polling_timeout=30,
                allowed_updates=['message', 'callback_query']
            )
        except Exception as e:
            if "409" in str(e) or "Conflict" in str(e):
                print("⚠️ КОНФЛИКТ 409! Перезапуск через 3 секунды...")
                time.sleep(3)
                continue
            else:
                print(f"⚠️ Ошибка: {e}. Перезапуск через 3 секунды...")
                time.sleep(3)
                continue
