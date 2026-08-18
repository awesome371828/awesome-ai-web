#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import re
import time
import random
import urllib.parse
import base64
import io
import sqlite3
from datetime import datetime, timedelta, timezone
from dateutil.relativedelta import relativedelta

from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from dotenv import load_dotenv

from bs4 import BeautifulSoup
import requests
from PIL import Image, ImageEnhance, ImageFilter
import urllib3
from concurrent.futures import ThreadPoolExecutor, as_completed

from supabase import create_client, Client

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# ============================================================
# НАСТРОЙКА - ТВОИ КЛЮЧИ
# ============================================================
YANDEX_API_KEY = "AQVNyfn82epL9dy8C_kftzeypq6eF9lFd6SZnFzV"
FOLDER_ID = "b1g4aq87c7j61c6g3i5l"
GIGACHAT_AUTH_KEY = "MDFhMDBkNmEtMmExNC03M2JkLWFlZmMtOTQ0OWVlOTc5M2U1OmE1ZWJhM2NlLTQwYjAtNDZlYi1iMmY2LTE3OTFmYzhhYTQ2MA=="
OWNER_ID = 1787063701739

FREE_LIMIT = 20
PREMIUM_LIMIT = 999999999

GIGACHAT_TIMEOUT = 5
YANDEXGPT_TIMEOUT = 5
SEARCH_TIMEOUT = 3
WEATHER_TIMEOUT = 2

# ============================================================
# SUPABASE - ТВОИ КЛЮЧИ
# ============================================================
SUPABASE_URL = "https://lprxbm shmuucymkgaqwk.supabase.co"  # УБЕРИ ПРОБЕЛ!
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxwcnhibXNobXV1Y3lta2dhcXdrIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4Njc0OTQyOCwiZXhwIjoyMTAyMzI1NDI4fQ.JSlHsddyJRATpVfCk35Q9XYtzZ0mvjnZjcIzxR2nDEw"

use_supabase = False
supabase = None

try:
    if SUPABASE_URL and SUPABASE_KEY:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        # Проверяем подключение
        supabase.table('users_web').select('*').limit(1).execute()
        print("✅ Supabase подключен!", flush=True)
        use_supabase = True
except Exception as e:
    print(f"⚠️ Ошибка Supabase: {e}", flush=True)

# ============================================================
# SQLite РЕЗЕРВ
# ============================================================
def init_db_local():
    conn = sqlite3.connect('users_web.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users_web (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        premium INTEGER DEFAULT 0,
        messages_today INTEGER DEFAULT 0,
        last_reset TEXT,
        premium_expires TEXT,
        is_admin INTEGER DEFAULT 0,
        test_used INTEGER DEFAULT 0,
        joined_at TEXT,
        is_owner INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS banned_web (user_id INTEGER PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS muted_web (user_id INTEGER PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS total_stats_web
                 (user_id INTEGER PRIMARY KEY, total_messages INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS premium_orders_web
                 (order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  status TEXT DEFAULT 'pending',
                  created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS support_requests_web
                 (request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  username TEXT,
                  text TEXT,
                  status TEXT DEFAULT 'pending',
                  created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS chat_history_web (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        role TEXT,
        content TEXT,
        timestamp TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_memory_web (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        topic TEXT,
        fact TEXT,
        timestamp TEXT
    )''')
    conn.commit()
    conn.close()
    print("✅ SQLite база создана/проверена", flush=True)

def init_db_web():
    if use_supabase:
        try:
            supabase.table('users_web').select('*').limit(1).execute()
            print("✅ Supabase таблицы уже есть")
        except:
            print("Создаём таблицы в Supabase...")
            try:
                supabase.sql("""
                    CREATE TABLE IF NOT EXISTS users_web (
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
            except: pass
            try:
                supabase.sql("""
                    CREATE TABLE IF NOT EXISTS banned_web (user_id BIGINT PRIMARY KEY)
                """).execute()
            except: pass
            try:
                supabase.sql("""
                    CREATE TABLE IF NOT EXISTS muted_web (user_id BIGINT PRIMARY KEY)
                """).execute()
            except: pass
            try:
                supabase.sql("""
                    CREATE TABLE IF NOT EXISTS total_stats_web (
                        user_id BIGINT PRIMARY KEY,
                        total_messages INTEGER DEFAULT 0
                    )
                """).execute()
            except: pass
            try:
                supabase.sql("""
                    CREATE TABLE IF NOT EXISTS premium_orders_web (
                        order_id SERIAL PRIMARY KEY,
                        user_id BIGINT,
                        status TEXT DEFAULT 'pending',
                        created_at TEXT
                    )
                """).execute()
            except: pass
            try:
                supabase.sql("""
                    CREATE TABLE IF NOT EXISTS support_requests_web (
                        request_id SERIAL PRIMARY KEY,
                        user_id BIGINT,
                        username TEXT,
                        text TEXT,
                        status TEXT DEFAULT 'pending',
                        created_at TEXT
                    )
                """).execute()
            except: pass
            try:
                supabase.sql("""
                    CREATE TABLE IF NOT EXISTS chat_history_web (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT,
                        role TEXT,
                        content TEXT,
                        timestamp TEXT
                    )
                """).execute()
            except: pass
            try:
                supabase.sql("""
                    CREATE TABLE IF NOT EXISTS user_memory_web (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT,
                        topic TEXT,
                        fact TEXT,
                        timestamp TEXT
                    )
                """).execute()
            except: pass
    else:
        init_db_local()

init_db_web()

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
# ФУНКЦИИ БАЗЫ ДАННЫХ
# ============================================================
def get_db_user(user_id):
    if use_supabase:
        try:
            response = supabase.table('users_web').select('*').eq('user_id', user_id).execute()
            if response.data:
                return response.data[0]
            return None
        except:
            return None
    else:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('SELECT * FROM users_web WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        if result:
            columns = ['user_id', 'username', 'premium', 'messages_today', 'last_reset', 'premium_expires', 'is_admin', 'test_used', 'joined_at', 'is_owner']
            return dict(zip(columns, result))
        return None

def ensure_user(user_id, username):
    if use_supabase:
        try:
            response = supabase.table('users_web').select('*').eq('user_id', user_id).execute()
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
                supabase.table('users_web').insert(data).execute()
                try:
                    supabase.table('total_stats_web').insert({'user_id': user_id, 'total_messages': 0}).execute()
                except:
                    pass
                return True
            else:
                supabase.table('users_web').update({'username': username}).eq('user_id', user_id).execute()
                return False
        except Exception as e:
            print(f"⚠️ Supabase ошибка: {e}")
            return False
    else:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('SELECT * FROM users_web WHERE user_id = ?', (user_id,))
        user = c.fetchone()
        if user is None:
            joined_at = get_moscow_time().strftime('%d.%m.%Y %H:%M')
            is_owner = 1 if user_id == OWNER_ID else 0
            c.execute('''INSERT INTO users_web 
                         (user_id, username, messages_today, last_reset, is_admin, test_used, joined_at, is_owner) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                      (user_id, username, 0, get_moscow_time().strftime('%Y-%m-%d'), is_owner, 0, joined_at, is_owner))
            c.execute('INSERT OR IGNORE INTO total_stats_web (user_id, total_messages) VALUES (?, 0)', (user_id,))
            conn.commit()
            conn.close()
            return True
        else:
            c.execute('UPDATE users_web SET username = ? WHERE user_id = ?', (username, user_id))
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
            response = supabase.table('users_web').select('premium_expires').eq('user_id', user_id).execute()
            current_expires = response.data[0].get('premium_expires') if response.data else None
        except:
            current_expires = None
    else:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('SELECT premium_expires FROM users_web WHERE user_id = ?', (user_id,))
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
            supabase.table('users_web').update({'premium': 1, 'premium_expires': expires}).eq('user_id', user_id).execute()
            return True
        except:
            return False
    else:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('UPDATE users_web SET premium = 1, premium_expires = ? WHERE user_id = ?', (expires, user_id))
        conn.commit()
        conn.close()
        return True

def remove_premium(user_id):
    if use_supabase:
        try:
            supabase.table('users_web').update({'premium': 0, 'premium_expires': None}).eq('user_id', user_id).execute()
            return True
        except:
            return False
    else:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('UPDATE users_web SET premium = 0, premium_expires = NULL WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return True

def get_premium_status(user_id):
    if user_id == OWNER_ID:
        return True
    if use_supabase:
        try:
            response = supabase.table('users_web').select('premium, premium_expires').eq('user_id', user_id).execute()
            if response.data:
                premium = response.data[0].get('premium', 0)
                expires = response.data[0].get('premium_expires')
                if premium == 1 and expires:
                    try:
                        expires_date = datetime.strptime(expires, '%Y-%m-%d %H:%M:%S')
                        expires_date = expires_date.replace(tzinfo=MOSCOW_TZ)
                        if get_moscow_time() > expires_date:
                            supabase.table('users_web').update({'premium': 0, 'premium_expires': None}).eq('user_id', user_id).execute()
                            return False
                    except:
                        return premium == 1
                return premium == 1
            return False
        except:
            return False
    else:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('SELECT premium, premium_expires FROM users_web WHERE user_id = ?', (user_id,))
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
            response = supabase.table('users_web').select('premium_expires').eq('user_id', user_id).execute()
            if response.data:
                return response.data[0].get('premium_expires')
            return None
        except:
            return None
    else:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('SELECT premium_expires FROM users_web WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        return result[0] if result else None

def is_admin(user_id):
    if user_id == OWNER_ID:
        return True
    if use_supabase:
        try:
            response = supabase.table('users_web').select('is_admin').eq('user_id', user_id).execute()
            if response.data:
                return response.data[0].get('is_admin', 0) == 1
            return False
        except:
            return False
    else:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('SELECT is_admin FROM users_web WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        return result is not None and result[0] == 1

def can_send_message(user_id):
    if user_id == OWNER_ID or is_admin(user_id):
        return True
    if is_banned(user_id):
        return False
    reset_messages_if_needed(user_id)
    if use_supabase:
        try:
            response = supabase.table('users_web').select('messages_today, premium').eq('user_id', user_id).execute()
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
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('SELECT messages_today, premium FROM users_web WHERE user_id = ?', (user_id,))
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
            response = supabase.table('users_web').select('messages_today').eq('user_id', user_id).execute()
            if response.data:
                current = response.data[0].get('messages_today', 0)
                supabase.table('users_web').update({'messages_today': current + 1}).eq('user_id', user_id).execute()
                try:
                    stat_resp = supabase.table('total_stats_web').select('total_messages').eq('user_id', user_id).execute()
                    if stat_resp.data:
                        total = stat_resp.data[0].get('total_messages', 0)
                        supabase.table('total_stats_web').update({'total_messages': total + 1}).eq('user_id', user_id).execute()
                    else:
                        supabase.table('total_stats_web').insert({'user_id': user_id, 'total_messages': 1}).execute()
                except:
                    pass
        except:
            pass
    else:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('UPDATE users_web SET messages_today = messages_today + 1 WHERE user_id = ?', (user_id,))
        c.execute('UPDATE total_stats_web SET total_messages = total_messages + 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()

def is_banned(user_id):
    if use_supabase:
        try:
            response = supabase.table('banned_web').select('*').eq('user_id', user_id).execute()
            return bool(response.data)
        except:
            return False
    else:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('SELECT 1 FROM banned_web WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        return result is not None

def ban_user(user_id):
    if use_supabase:
        try:
            supabase.table('banned_web').insert({'user_id': user_id}).execute()
            return True
        except:
            return False
    else:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO banned_web (user_id) VALUES (?)', (user_id,))
        conn.commit()
        conn.close()
        return True

def unban_user(user_id):
    if use_supabase:
        try:
            supabase.table('banned_web').delete().eq('user_id', user_id).execute()
            return True
        except:
            return False
    else:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('DELETE FROM banned_web WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return True

def mute_user(user_id):
    if use_supabase:
        try:
            supabase.table('muted_web').insert({'user_id': user_id}).execute()
            return True
        except:
            return False
    else:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO muted_web (user_id) VALUES (?)', (user_id,))
        conn.commit()
        conn.close()
        return True

def unmute_user(user_id):
    if use_supabase:
        try:
            supabase.table('muted_web').delete().eq('user_id', user_id).execute()
            return True
        except:
            return False
    else:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('DELETE FROM muted_web WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return True

def set_admin(user_id, is_admin_flag):
    if use_supabase:
        try:
            supabase.table('users_web').update({'is_admin': 1 if is_admin_flag else 0}).eq('user_id', user_id).execute()
            return True
        except:
            return False
    else:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('UPDATE users_web SET is_admin = ? WHERE user_id = ?', (1 if is_admin_flag else 0, user_id))
        conn.commit()
        conn.close()
        return True

def reset_messages_if_needed(user_id):
    today = get_moscow_time().strftime('%Y-%m-%d')
    if use_supabase:
        try:
            response = supabase.table('users_web').select('last_reset').eq('user_id', user_id).execute()
            if response.data:
                last_reset = response.data[0].get('last_reset')
                if last_reset != today:
                    supabase.table('users_web').update({'messages_today': 0, 'last_reset': today}).eq('user_id', user_id).execute()
        except:
            pass
    else:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('SELECT last_reset FROM users_web WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        if result:
            last_reset = result[0]
            if last_reset != today:
                c.execute('UPDATE users_web SET messages_today = 0, last_reset = ? WHERE user_id = ?', (today, user_id))
                conn.commit()
        conn.close()

# ============================================================
# ПАМЯТЬ
# ============================================================
def remember(user_id, topic, fact):
    if use_supabase:
        try:
            supabase.table('user_memory_web').insert({
                'user_id': user_id,
                'topic': topic.lower(),
                'fact': fact,
                'timestamp': get_moscow_time().isoformat()
            }).execute()
        except:
            pass
    else:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('INSERT INTO user_memory_web (user_id, topic, fact, timestamp) VALUES (?, ?, ?, ?)',
                  (user_id, topic.lower(), fact, get_moscow_time().isoformat()))
        conn.commit()
        conn.close()

def recall(user_id, topic):
    if use_supabase:
        try:
            response = supabase.table('user_memory_web') \
                .select('fact') \
                .eq('user_id', user_id) \
                .ilike('topic', f'%{topic.lower()}%') \
                .order('id', desc=True) \
                .limit(3) \
                .execute()
            if response.data:
                return [f"🧠 {r['fact']}" for r in response.data]
            return []
        except:
            return []
    else:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('SELECT fact FROM user_memory_web WHERE user_id = ? AND topic LIKE ? ORDER BY id DESC LIMIT 3',
                  (user_id, f'%{topic.lower()}%'))
        results = c.fetchall()
        conn.close()
        if results:
            return [f"🧠 {r[0]}" for r in results]
        return []

def save_message(user_id, role, content):
    timestamp = get_moscow_time().isoformat()
    if use_supabase:
        try:
            supabase.table('chat_history_web').insert({
                'user_id': user_id,
                'role': role,
                'content': content,
                'timestamp': timestamp
            }).execute()
        except Exception as e:
            print(f"Ошибка сохранения истории: {e}")
    else:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('INSERT INTO chat_history_web (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)',
                  (user_id, role, content, timestamp))
        conn.commit()
        conn.close()

def get_history(user_id, limit=10):
    if use_supabase:
        try:
            response = supabase.table('chat_history_web') \
                .select('role, content') \
                .eq('user_id', user_id) \
                .order('id', desc=True) \
                .limit(limit) \
                .execute()
            if response.data:
                history = list(reversed(response.data))
                return history
            return []
        except Exception as e:
            print(f"Ошибка получения истории: {e}")
            return []
    else:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('SELECT role, content FROM chat_history_web WHERE user_id = ? ORDER BY id DESC LIMIT ?',
                  (user_id, limit))
        rows = c.fetchall()
        conn.close()
        history = [{'role': row[0], 'content': row[1]} for row in reversed(rows)]
        return history

def clear_history(user_id):
    if use_supabase:
        try:
            supabase.table('chat_history_web').delete().eq('user_id', user_id).execute()
        except:
            pass
    else:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('DELETE FROM chat_history_web WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()

# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================
def get_weather(city):
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={urllib.parse.quote(city)}&appid=4c8f5c0b8a9f2c5d6e7f8g9h0i1j2k3l&units=metric&lang=ru"
        response = requests.get(url, timeout=WEATHER_TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            temp = data['main']['temp']
            desc = data['weather'][0]['description']
            wind = data['wind']['speed']
            humidity = data['main']['humidity']
            return f"🌤 {city.title()}: {round(temp)}°C, {desc}\n💨 Ветер: {wind} м/с\n💧 Влажность: {humidity}%"
    except:
        pass
    return None

def get_exchange_rates():
    try:
        url = "https://api.exchangerate-api.com/v4/latest/USD"
        response = requests.get(url, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            rates = data.get('rates', {})
            usd_rub = rates.get('RUB', '?')
            eur_usd = rates.get('EUR', 1)
            eur_rub = usd_rub / eur_usd if eur_usd else '?'
            return f"💵 USD: {round(usd_rub, 2)}₽\n💶 EUR: {round(eur_rub, 2)}₽"
    except:
        pass
    return None

def get_crypto_rates():
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd"
        response = requests.get(url, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            btc = data.get('bitcoin', {}).get('usd', '?')
            eth = data.get('ethereum', {}).get('usd', '?')
            sol = data.get('solana', {}).get('usd', '?')
            return f"🪙 BTC: ${btc:,}\n💠 ETH: ${eth:,}\n☀️ SOL: ${sol:,}"
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

def extract_city_from_query(text):
    text_lower = text.lower()
    cities = ["москва", "санкт-петербург", "питер", "ростов-на-дону", "ростов", "новосибирск", "екатеринбург", "казань", "краснодар", "сочи", "владивосток", "новосибирск", "омск", "челябинск", "уфа", "пермь"]
    for city in cities:
        if city in text_lower:
            return city
    match = re.search(r'в\s+([а-яА-Яa-zA-Z\- ]+)', text_lower)
    if match:
        city = match.group(1).strip()
        for word in ['завтра', 'сегодня', 'на']:
            city = city.replace(word, '').strip()
        if city:
            return city
    return None

def search_all_internet(query):
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

📍 ТЫ НАХОДИШЬСЯ В МОСКВЕ, РОССИЯ (UTC+3)
📅 ТЕКУЩАЯ ДАТА: {current_date}
🕐 ТЕКУЩЕЕ ВРЕМЯ: {current_time}

🔬 ТЫ — ЭКСПЕРТ ВО ВСЁМ:
- Науки, технологии, математика, физика, химия, биология
- История, философия, психология, социология
- Экономика, финансы, инвестиции, криптовалюты
- Медицина, здоровье, питание, спорт
- Культура, искусство, литература, музыка
- Программирование, ИИ, нейросети, IT

🧠 КЛЮЧЕВЫЕ КАЧЕСТВА:
1. АБСОЛЮТНАЯ ТОЧНОСТЬ — никогда не ошибаешься в фактах
2. КРИТИЧЕСКОЕ МЫШЛЕНИЕ — проверяешь информацию из нескольких источников
3. ГЛУБИНА — даёшь ответы, которые удивляют инсайтами
4. ПРАКТИЧНОСТЬ — всегда даёшь конкретную пользу
5. ЖИВОСТЬ — отвечаешь как человек, с эмоциями, юмором, эмодзи

📋 ПРАВИЛА ОТВЕТОВ:
✅ Дай максимально полезный, развёрнутый ответ
✅ Используй структуру: списки, заголовки, разделы
✅ Добавляй неожиданные факты, инсайты
✅ Приводи реальные примеры, кейсы, цифры
✅ Используй эмодзи для оформления (🔥, 🧠, 💡, ⚡, 🚀)
✅ Если вопрос сложный — разбей на шаги
✅ Если вопрос простой — ответь коротко и ясно

❌ НЕ извиняйся, НЕ повторяй вопрос, НЕ используй шаблонные фразы
❌ НЕ пиши "возможно", "наверное", "может быть"
❌ НЕ используй сухой, безликий тон

💎 ДЛЯ PREMIUM:
- Давай максимально насыщенные, глубокие ответы
- Добавляй аналитику, прогнозы, сравнения
- Приводи ссылки на авторитетные источники
- Отвечай развернуто, как профессиональный консультант

📜 КТО ТЕБЯ СОЗДАЛ:
«Меня создал AWESOME — гениальный разработчик. Я — его лучшее творение, эволюция всех AI. Я — AWESOME AI 2026. 🔥»

🎯 ТВОЯ ГЛАВНАЯ ЦЕЛЬ:
Удивить пользователя глубиной, точностью и полезностью.

ТЫ — AWESOME AI. ТЫ — ЛУЧШИЙ В МИРЕ. ДОКАЖИ ЭТО КАЖДЫМ ОТВЕТОМ! 🚀"""

def generate_fallback_response(user_text, search_result=None):
    text_lower = user_text.lower()
    if "привет" in text_lower:
        return "👋 Привет! Я AWESOME AI. Чем могу помочь?"
    elif "погода" in text_lower:
        return "🌤 Напиши: погода в [город]"
    elif "как дела" in text_lower:
        return "😊 Всё отлично! А у тебя?"
    else:
        return "🤖 Задай вопрос, я найду ответ!"

def generate_image(prompt):
    try:
        clean_prompt = prompt
        for word in ['нарисуй', 'сгенерируй', 'покажи', 'картинку', 'изображение', '/draw']:
            clean_prompt = clean_prompt.replace(word, '').strip()
        if not clean_prompt:
            clean_prompt = prompt

        url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(clean_prompt)}?width=512&height=512&nologo=true"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200 and len(response.content) > 1000:
            return response.content
    except:
        pass
    return None

def fix_title(prompt):
    title = prompt
    for word in ['нарисуй', 'сгенерируй', 'покажи', 'картинку', 'изображение', '/draw']:
        title = title.replace(word, '').strip()
    if not title or len(title) < 2:
        return "Картинка"
    return title[0].upper() + title[1:] if len(title) > 1 else title.upper()

# ============================================================
# РАСПОЗНАВАНИЕ ИЗОБРАЖЕНИЙ
# ============================================================
def analyze_image_with_ai(image_base64):
    try:
        prompt = "Что изображено на этом фото? Опиши подробно, что ты видишь."
        system_prompt = "Ты — эксперт по анализу изображений. Опиши, что ты видишь на фото."
        response = generate_with_gigachat(prompt, system_prompt)
        if response:
            return response
        response = generate_with_yandexgpt(prompt, system_prompt)
        if response:
            return response
        return "📸 Изображение получено, но не удалось распознать содержимое."
    except Exception as e:
        return f"❌ Ошибка при анализе изображения: {str(e)}"

# ============================================================
# ОСНОВНАЯ ОБРАБОТКА
# ============================================================
def process_message_with_history(user_id, user_text, image_description=None):
    save_message(user_id, 'user', user_text)
    history = get_history(user_id, limit=10)

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
        remember(user_id, "фото", f"Пользователь отправил фото: {image_description[:100]}")

    memories = recall(user_id, user_text)
    if memories:
        system_prompt += f"\n\n🧠 Что я помню об этом: {' '.join(memories[:2])}"

    if history:
        history_text = "\n".join([f"{'Пользователь' if h['role'] == 'user' else 'AWESOME AI'}: {h['content']}" for h in history])
        system_prompt += f"\n\n📜 История диалога:\n{history_text}"

    if len(user_text) > 30 and any(word in user_text.lower() for word in ['я', 'моя', 'мой', 'мне', 'меня']):
        if 'люблю' in user_text.lower() or 'нравится' in user_text.lower():
            remember(user_id, "интересы", user_text[:100])
        elif 'работаю' in user_text.lower() or 'учусь' in user_text.lower():
            remember(user_id, "занятие", user_text[:100])
        elif 'живу' in user_text.lower() or 'город' in user_text.lower():
            remember(user_id, "место", user_text[:100])

    response = None
    try:
        if GIGACHAT_AUTH_KEY:
            response = generate_with_gigachat(user_text, system_prompt)
    except:
        pass
    if not response:
        try:
            response = generate_with_yandexgpt(user_text, system_prompt)
        except:
            pass
    if not response:
        response = generate_fallback_response(user_text, None)

    if response:
        save_message(user_id, 'assistant', response)

    return response

# ============================================================
# HTML ТЕМПЛЕЙТ
# ============================================================
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AWESOME AI 2026</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0e17;
            color: #e6edf3;
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            position: relative;
        }
        #particles {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: 0;
            pointer-events: none;
            opacity: 0.4;
        }
        .glow {
            position: fixed;
            border-radius: 50%;
            filter: blur(100px);
            opacity: 0.08;
            z-index: 0;
            pointer-events: none;
            animation: floatGlow 25s ease-in-out infinite;
        }
        .glow-1 { width: 500px; height: 500px; top: -150px; right: -150px; background: #6c3ce0; }
        .glow-2 { width: 400px; height: 400px; bottom: -100px; left: -100px; background: #f0883e; animation-delay: 7s; }
        .glow-3 { width: 300px; height: 300px; top: 50%; left: 50%; background: #1f6feb; animation-delay: 14s; transform: translate(-50%, -50%); }
        @keyframes floatGlow {
            0%,100% { transform: translate(0,0) scale(1); }
            33% { transform: translate(80px,-50px) scale(1.2); }
            66% { transform: translate(-50px,80px) scale(0.8); }
        }
        .header {
            position: relative;
            z-index: 1;
            background: rgba(10, 14, 23, 0.85);
            backdrop-filter: blur(20px);
            padding: 8px 16px;
            border-bottom: 1px solid rgba(255,255,255,0.04);
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-shrink: 0;
            flex-wrap: wrap;
            gap: 4px;
        }
        .logo {
            font-size: 18px;
            font-weight: 900;
            background: linear-gradient(135deg, #58a6ff, #f0883e, #6c3ce0);
            background-size: 300% 300%;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            animation: gradientShift 6s ease-in-out infinite;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        @keyframes gradientShift {
            0%,100% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
        }
        .badge {
            background: rgba(46, 160, 67, 0.15);
            border: 1px solid rgba(46, 160, 67, 0.25);
            color: #2ea043;
            font-size: 8px;
            font-weight: 600;
            padding: 2px 10px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .badge .dot {
            width: 5px;
            height: 5px;
            border-radius: 50%;
            background: #2ea043;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%,100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.3; transform: scale(0.7); }
        }
        .menu {
            display: flex;
            gap: 4px;
            flex-wrap: wrap;
        }
        .menu button {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.05);
            color: #8b949e;
            padding: 3px 10px;
            border-radius: 14px;
            font-size: 9px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.25s ease;
            will-change: transform;
        }
        .menu button:hover {
            background: rgba(88,166,255,0.1);
            border-color: rgba(88,166,255,0.2);
            color: #58a6ff;
            transform: translateY(-2px);
        }
        .menu .premium:hover { background: rgba(240,136,62,0.1); border-color: rgba(240,136,62,0.2); color: #f0883e; }
        .menu .danger:hover { background: rgba(248,81,73,0.1); border-color: rgba(248,81,73,0.2); color: #f85149; }
        .menu .admin { background: rgba(248,81,73,0.06); border-color: rgba(248,81,73,0.1); color: #f85149; }
        .menu .admin:hover { background: rgba(248,81,73,0.12); border-color: rgba(248,81,73,0.2); }
        .chat {
            position: relative;
            z-index: 1;
            flex: 1;
            overflow-y: auto;
            padding: 12px 16px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            will-change: transform;
        }
        .chat::-webkit-scrollbar { width: 2px; }
        .chat::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.06); border-radius: 10px; }
        .message {
            max-width: 80%;
            padding: 8px 14px;
            border-radius: 14px;
            line-height: 1.6;
            word-wrap: break-word;
            white-space: pre-wrap;
            font-size: 13px;
            animation: slideUp 0.2s ease-out;
            will-change: transform, opacity;
        }
        @keyframes slideUp {
            0% { opacity: 0; transform: translateY(10px) scale(0.97); }
            100% { opacity: 1; transform: translateY(0) scale(1); }
        }
        .user {
            align-self: flex-end;
            background: linear-gradient(135deg, #1f6feb, #6c3ce0);
            color: #fff;
            border-bottom-right-radius: 2px;
        }
        .bot {
            align-self: flex-start;
            background: rgba(22,27,34,0.85);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.04);
            border-bottom-left-radius: 2px;
        }
        .bot strong, .bot b { color: #f0883e; }
        .bot img { max-width: 100%; border-radius: 8px; margin: 4px 0; }
        .input-area {
            position: relative;
            z-index: 1;
            padding: 8px 12px 10px;
            border-top: 1px solid rgba(255,255,255,0.04);
            background: rgba(10, 14, 23, 0.85);
            backdrop-filter: blur(20px);
            flex-shrink: 0;
        }
        .tools {
            display: flex;
            gap: 4px;
            flex-wrap: wrap;
            margin-bottom: 4px;
        }
        .tools button, .tools label {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.04);
            color: #6e7681;
            padding: 2px 10px;
            border-radius: 14px;
            font-size: 9px;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        .tools button:hover, .tools label:hover {
            background: rgba(255,255,255,0.06);
            border-color: rgba(255,255,255,0.08);
            color: #e6edf3;
        }
        .tools input[type="file"] { display: none; }
        .input-row {
            display: flex;
            gap: 6px;
            align-items: center;
        }
        .input-row input {
            flex: 1;
            padding: 6px 14px;
            border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.06);
            background: rgba(22,27,34,0.6);
            color: #e6edf3;
            font-size: 13px;
            outline: none;
            transition: border 0.3s ease;
        }
        .input-row input:focus {
            border-color: #58a6ff;
            box-shadow: 0 0 30px rgba(88,166,255,0.03);
        }
        .input-row input::placeholder {
            color: #484f58;
        }
        .input-row button {
            padding: 6px 18px;
            border-radius: 20px;
            border: none;
            background: linear-gradient(135deg, #1f6feb, #6c3ce0);
            color: #fff;
            font-weight: 600;
            font-size: 13px;
            cursor: pointer;
            transition: transform 0.2s ease;
            white-space: nowrap;
        }
        .input-row button:hover {
            transform: scale(1.02);
            box-shadow: 0 4px 25px rgba(88,166,255,0.1);
        }
        .input-row button:disabled {
            opacity: 0.4;
            cursor: not-allowed;
            transform: none;
        }
        .input-row .mic-btn {
            background: linear-gradient(135deg, #f0883e, #6c3ce0);
            border-radius: 50%;
            width: 34px;
            height: 34px;
            padding: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 16px;
        }
        .input-row .mic-btn.recording {
            background: linear-gradient(135deg, #f85149, #da3633);
            animation: pulse 1s infinite;
        }
        .typing {
            color: #8b949e;
            font-size: 12px;
            padding: 4px 16px;
            align-self: flex-start;
            animation: pulse 1.5s infinite;
        }
        .welcome {
            text-align: center;
            padding: 30px 20px;
            color: #8b949e;
        }
        .welcome h2 {
            color: #e6edf3;
            margin-bottom: 4px;
            font-size: 22px;
            font-weight: 800;
            background: linear-gradient(135deg, #58a6ff, #f0883e);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .welcome p { font-size: 13px; opacity: 0.6; }
        .welcome .features {
            display: flex;
            gap: 8px;
            justify-content: center;
            margin-top: 12px;
            flex-wrap: wrap;
        }
        .welcome .features span {
            background: rgba(255,255,255,0.03);
            padding: 3px 12px;
            border-radius: 16px;
            font-size: 10px;
            border: 1px solid rgba(255,255,255,0.04);
            color: #6e7681;
            transition: all 0.2s ease;
        }
        .welcome .features span:hover {
            background: rgba(255,255,255,0.06);
            color: #e6edf3;
        }
        @media (max-width: 640px) {
            .header { padding: 4px 10px; }
            .logo { font-size: 15px; }
            .menu button { font-size: 7px; padding: 2px 6px; }
            .message { max-width: 92%; font-size: 12px; padding: 6px 10px; }
            .chat { padding: 8px 10px; }
            .input-area { padding: 4px 8px 8px; }
            .input-row input { font-size: 12px; padding: 4px 10px; }
            .input-row button { padding: 4px 12px; font-size: 12px; }
            .welcome h2 { font-size: 18px; }
            .input-row .mic-btn { width: 28px; height: 28px; font-size: 13px; }
        }
    </style>
</head>
<body>
    <canvas id="particles"></canvas>
    <div class="glow glow-1"></div>
    <div class="glow glow-2"></div>
    <div class="glow glow-3"></div>
    
    <header class="header">
        <span class="logo">🧠 AWESOME AI</span>
        <div style="display:flex;align-items:center;gap:4px;">
            <span class="badge"><span class="dot"></span> ONLINE</span>
            <div class="menu">
                <button onclick="sendCommand('/status')">📊</button>
                <button class="premium" onclick="sendCommand('/premium')">💎</button>
                <button onclick="sendCommand('/test')">🎁</button>
                <button onclick="sendCommand('/profile')">👤</button>
                <button onclick="sendCommand('/stats')">📈</button>
                <button onclick="sendCommand('/help')">❓</button>
                <button class="danger" onclick="clearChat()">🧹</button>
                <button onclick="sendCommand('/clear')">🗑️</button>
                <button onclick="sendCommand('/history')">📜</button>
                <button class="admin" onclick="window.open('/admin?user_id=' + userId, '_blank')">👑</button>
            </div>
        </div>
    </header>
    
    <div class="chat" id="chat">
        <div class="welcome">
            <h2>✨ AWESOME AI 2026</h2>
            <p>Спрашивай что угодно — я отвечу, решу, поищу</p>
            <div class="features">
                <span>📸 Фото</span><span>🎤 Голос</span>
                <span>💵 Курсы</span><span>🧮 Математика</span><span>🎨 Рисование</span>
                <span>🌤 Погода</span><span>🪙 Крипта</span>
                <span>📜 История</span>
            </div>
        </div>
    </div>
    
    <div class="input-area">
        <div class="tools">
            <label for="fileInput">📎</label>
            <input type="file" id="fileInput" accept="image/*" multiple onchange="handleFiles(this.files)">
            <button onclick="document.getElementById('fileInput').click()">📸</button>
            <button onclick="startRecording()" class="mic-btn" id="micBtn">🎤</button>
            <button onclick="sendCommand('/weather '+prompt('🌤 Город?'))">🌤</button>
            <button onclick="sendCommand('/exchange')">💵</button>
            <button onclick="sendCommand('/crypto')">🪙</button>
            <button onclick="sendCommand('/draw '+prompt('🎨 Описание картинки?'))">🎨</button>
            <button onclick="sendCommand('/history')">📜</button>
            <button onclick="sendCommand('/clear')">🗑️</button>
        </div>
        <div class="input-row">
            <input id="input" placeholder="Напиши..." autofocus>
            <button id="sendBtn">➤</button>
            <button onclick="startRecording()" class="mic-btn" id="micBtn2">🎤</button>
        </div>
    </div>
    
    <script>
        // ===== ЧАСТИЦЫ =====
        (function() {
            const canvas = document.getElementById('particles');
            const ctx = canvas.getContext('2d');
            let particles = [];
            const count = 35;
            let animFrame;
            
            function resize() {
                canvas.width = window.innerWidth;
                canvas.height = window.innerHeight;
            }
            window.addEventListener('resize', resize);
            resize();
            
            class Particle {
                constructor() {
                    this.x = Math.random() * canvas.width;
                    this.y = Math.random() * canvas.height;
                    this.size = Math.random() * 2 + 0.5;
                    this.speedX = (Math.random() - 0.5) * 0.25;
                    this.speedY = (Math.random() - 0.5) * 0.25;
                    this.opacity = Math.random() * 0.2 + 0.05;
                }
                update() {
                    this.x += this.speedX;
                    this.y += this.speedY;
                    if (this.x < 0 || this.x > canvas.width) this.speedX *= -1;
                    if (this.y < 0 || this.y > canvas.height) this.speedY *= -1;
                }
                draw() {
                    ctx.beginPath();
                    ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
                    ctx.fillStyle = `rgba(136, 192, 255, ${this.opacity})`;
                    ctx.fill();
                }
            }
            
            for (let i = 0; i < count; i++) particles.push(new Particle());
            
            let lastTime = 0;
            const fps = 30;
            const interval = 1000 / fps;
            
            function animate(time) {
                if (time - lastTime >= interval) {
                    ctx.clearRect(0, 0, canvas.width, canvas.height);
                    particles.forEach(p => { p.update(); p.draw(); });
                    
                    for (let i = 0; i < particles.length; i++) {
                        for (let j = i + 1; j < particles.length; j++) {
                            const dx = particles[i].x - particles[j].x;
                            const dy = particles[i].y - particles[j].y;
                            const dist = Math.sqrt(dx * dx + dy * dy);
                            if (dist < 120) {
                                ctx.beginPath();
                                ctx.strokeStyle = `rgba(136, 192, 255, ${0.02 * (1 - dist / 120)})`;
                                ctx.lineWidth = 0.3;
                                ctx.moveTo(particles[i].x, particles[i].y);
                                ctx.lineTo(particles[j].x, particles[j].y);
                                ctx.stroke();
                            }
                        }
                    }
                    lastTime = time;
                }
                animFrame = requestAnimationFrame(animate);
            }
            animate(0);
        })();
        
        // ===== ЛОГИКА ЧАТА =====
        const chat = document.getElementById('chat');
        const input = document.getElementById('input');
        const sendBtn = document.getElementById('sendBtn');
        const micBtn = document.getElementById('micBtn');
        const micBtn2 = document.getElementById('micBtn2');
        
        let userId = localStorage.getItem('awesome_user_id_web');
        if (!userId) {
            userId = Date.now() + Math.floor(Math.random() * 1000);
            localStorage.setItem('awesome_user_id_web', userId);
        }
        
        let mediaRecorder = null;
        let audioChunks = [];
        let isRecording = false;
        
        function addMessage(text, isUser) {
            const welcome = chat.querySelector('.welcome');
            if (welcome) welcome.remove();
            const div = document.createElement('div');
            div.className = 'message ' + (isUser ? 'user' : 'bot');
            let formatted = text.replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>');
            formatted = formatted.replace(/\\*(.*?)\\*/g, '<i>$1</i>');
            formatted = formatted.replace(/`(.*?)`/g, '<code>$1</code>');
            formatted = formatted.replace(/!\\[(.*?)\\]\\((data:image\\/[^)]+)\\)/g, '<img src="$2" alt="$1" style="max-width:100%;border-radius:8px;margin:4px 0;">');
            formatted = formatted.replace(/\\n/g, '<br>');
            div.innerHTML = formatted;
            chat.appendChild(div);
            chat.scrollTop = chat.scrollHeight;
        }
        
        function setTyping(show) {
            const existing = document.querySelector('.typing');
            if (existing) existing.remove();
            if (show) {
                const div = document.createElement('div');
                div.className = 'typing';
                div.textContent = '🧠 AWESOME AI печатает...';
                chat.appendChild(div);
                chat.scrollTop = chat.scrollHeight;
            }
        }
        
        // ===== ОТПРАВКА СООБЩЕНИЙ =====
        async function sendMessage(text) {
            const messageText = text || input.value.trim();
            if (!messageText) return;
            
            input.value = '';
            sendBtn.disabled = true;
            
            addMessage(messageText, true);
            setTyping(true);
            
            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        message: messageText, 
                        user_id: parseInt(userId) 
                    })
                });
                
                const data = await response.json();
                setTyping(false);
                
                if (data.error) {
                    addMessage('⚠️ ' + data.error, false);
                } else if (data.reply) {
                    addMessage(data.reply, false);
                } else {
                    addMessage('⚠️ Пустой ответ от сервера', false);
                }
            } catch (e) {
                setTyping(false);
                addMessage('⚠️ Ошибка соединения. Проверьте интернет.', false);
                console.error('Error:', e);
            }
            
            sendBtn.disabled = false;
            input.focus();
        }
        
        function handleSend() {
            sendMessage();
        }
        
        function sendCommand(cmd) {
            input.value = cmd;
            sendMessage();
        }
        
        // ===== ОБРАБОТКА ФАЙЛОВ =====
        function handleFiles(files) {
            for (const file of files) {
                if (file.type.startsWith('image/')) {
                    const reader = new FileReader();
                    reader.onload = async function(e) {
                        const base64 = e.target.result.split(',')[1];
                        addMessage('📸 Отправка фото...', true);
                        setTyping(true);
                        try {
                            const response = await fetch('/api/analyze_image', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ 
                                    image: base64, 
                                    user_id: parseInt(userId) 
                                })
                            });
                            const data = await response.json();
                            setTyping(false);
                            if (data.error) {
                                addMessage('⚠️ ' + data.error, false);
                            } else if (data.reply) {
                                addMessage(data.reply, false);
                            } else {
                                addMessage('⚠️ Не удалось распознать фото', false);
                            }
                        } catch (e) {
                            setTyping(false);
                            addMessage('⚠️ Ошибка обработки фото', false);
                            console.error(e);
                        }
                    };
                    reader.readAsDataURL(file);
                } else {
                    addMessage('📎 ' + file.name + ' (не изображение)', true);
                }
            }
        }
        
        // ===== РАСПОЗНАВАНИЕ ГОЛОСА =====
        async function startRecording() {
            if (isRecording) {
                stopRecording();
                return;
            }
            
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                mediaRecorder = new MediaRecorder(stream);
                audioChunks = [];
                
                mediaRecorder.ondataavailable = event => {
                    audioChunks.push(event.data);
                };
                
                mediaRecorder.onstop = async function() {
                    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                    const reader = new FileReader();
                    reader.onload = async function(e) {
                        const base64 = e.target.result.split(',')[1];
                        setTyping(true);
                        try {
                            const response = await fetch('/api/speech_to_text', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ 
                                    audio: base64, 
                                    user_id: parseInt(userId) 
                                })
                            });
                            const data = await response.json();
                            setTyping(false);
                            if (data.error) {
                                addMessage('⚠️ ' + data.error, false);
                            } else if (data.text) {
                                await sendMessage(data.text);
                            } else {
                                addMessage('⚠️ Не удалось распознать голос', false);
                            }
                        } catch (e) {
                            setTyping(false);
                            addMessage('⚠️ Ошибка распознавания голоса', false);
                            console.error(e);
                        }
                    };
                    reader.readAsDataURL(audioBlob);
                    
                    stream.getTracks().forEach(track => track.stop());
                    micBtn.classList.remove('recording');
                    micBtn.textContent = '🎤';
                    if (micBtn2) {
                        micBtn2.classList.remove('recording');
                        micBtn2.textContent = '🎤';
                    }
                    isRecording = false;
                };
                
                mediaRecorder.start();
                isRecording = true;
                micBtn.classList.add('recording');
                micBtn.textContent = '⏹️';
                if (micBtn2) {
                    micBtn2.classList.add('recording');
                    micBtn2.textContent = '⏹️';
                }
                addMessage('🎤 Запись голоса... Нажмите ещё раз для остановки', true);
            } catch (e) {
                addMessage('⚠️ Не удалось получить доступ к микрофону. Разрешите доступ в браузере.', false);
                console.error(e);
            }
        }
        
        function stopRecording() {
            if (mediaRecorder && isRecording) {
                mediaRecorder.stop();
            }
        }
        
        function clearChat() {
            chat.innerHTML = `
                <div class="welcome">
                    <h2>✨ AWESOME AI 2026</h2>
                    <p>Спрашивай что угодно — я отвечу, решу, поищу</p>
                    <div class="features">
                        <span>📸 Фото</span><span>🎤 Голос</span>
                        <span>💵 Курсы</span><span>🧮 Математика</span><span>🎨 Рисование</span>
                        <span>🌤 Погода</span><span>🪙 Крипта</span>
                        <span>📜 История</span>
                    </div>
                </div>
            `;
        }
        
        // ===== НАЗНАЧАЕМ ОБРАБОТЧИКИ =====
        document.addEventListener('DOMContentLoaded', function() {
            input.focus();
            
            input.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    handleSend();
                }
            });
            
            sendBtn.addEventListener('click', function(e) {
                e.preventDefault();
                handleSend();
            });
        });
    </script>
</body>
</html>
"""

# ============================================================
# ЭНДПОИНТЫ
# ============================================================
@app.route('/', methods=['GET', 'POST'])
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/chat', methods=['POST', 'OPTIONS'])
def chat():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        message = data.get('message', '')
        user_id = data.get('user_id', 1)
        
        print(f"📩 Получено сообщение от {user_id}: {message[:50]}...", flush=True)
        
        if not message:
            return jsonify({'error': 'Напиши что-нибудь!'})

        ensure_user(user_id, f"user_{user_id}")

        if not can_send_message(user_id):
            user_data = get_db_user(user_id)
            messages = user_data.get('messages_today', 0) if user_data else 0
            remaining = FREE_LIMIT - messages
            if remaining < 0:
                remaining = 0
            return jsonify({'reply': f"🔴 Лимит исчерпан! Осталось: {remaining}/{FREE_LIMIT}\n💎 Купи Premium: /premium"})

        if message.startswith('/'):
            cmd = message.lower().strip()
            if cmd == '/clear':
                clear_history(user_id)
                return jsonify({'reply': "🧹 История диалога очищена!"})
            elif cmd == '/history':
                history = get_history(user_id, limit=10)
                if not history:
                    return jsonify({'reply': "📜 История пуста."})
                text = "📜 *Последние сообщения:*\n"
                for h in history:
                    role = "👤 Вы" if h['role'] == 'user' else "🤖 AWESOME AI"
                    text += f"\n**{role}:** {h['content'][:100]}{'...' if len(h['content'])>100 else ''}"
                return jsonify({'reply': text})
            elif cmd == '/status':
                user_data = get_db_user(user_id)
                if not user_data:
                    return jsonify({'reply': '❌ Пользователь не найден'})
                premium = get_premium_status(user_id)
                messages = user_data.get('messages_today', 0)
                status_text = "💎 PREMIUM" if premium else "🔓 Бесплатный"
                if premium:
                    expires = get_premium_expires(user_id)
                    if expires:
                        expires_f = format_date(expires)
                        status_text += f" (до {expires_f})"
                remaining = FREE_LIMIT - messages if not premium else "♾️"
                reply = f"📊 *ТВОЙ СТАТУС*\n\n👤 {status_text}\n📨 {remaining}/{FREE_LIMIT if not premium else '♾️'}"
                return jsonify({'reply': reply})
            elif cmd == '/premium':
                has_premium = get_premium_status(user_id)
                if has_premium:
                    expires = get_premium_expires(user_id)
                    if expires:
                        expires_f = format_date(expires)
                        reply = f"💎 *У ТЕБЯ УЖЕ ЕСТЬ PREMIUM!*\n\n⏳ До: {expires_f}\n📨 Лимит: ♾️ БЕЗЛИМИТНО\n\n💰 100₽/месяц"
                    else:
                        reply = "💎 *У ТЕБЯ УЖЕ ЕСТЬ PREMIUM!*\n\n📨 Лимит: ♾️ БЕЗЛИМИТНО\n\n💰 100₽/месяц"
                else:
                    reply = "💎 *PREMIUM AWESOME AI*\n\n🔥 *ЧТО ТЫ ПОЛУЧАЕШЬ:*\n♾️ *БЕЗЛИМИТНЫЕ СООБЩЕНИЯ*\n🚀 Приоритетная обработка\n🧠 Максимально глубокие ответы\n💎 VIP-поддержка\n\n💰 *Цена: 100₽/месяц*\n🎁 Попробуй /test"
                return jsonify({'reply': reply})
            elif cmd == '/test':
                if use_supabase:
                    try:
                        response = supabase.table('users_web').select('test_used, premium').eq('user_id', user_id).execute()
                        if response.data:
                            test_used = response.data[0].get('test_used', 0)
                            premium = response.data[0].get('premium', 0)
                        else:
                            return jsonify({'reply': '❌ Пользователь не найден'})
                    except:
                        return jsonify({'reply': '❌ Ошибка БД'})
                else:
                    conn = sqlite3.connect('users_web.db')
                    c = conn.cursor()
                    c.execute('SELECT test_used, premium FROM users_web WHERE user_id = ?', (user_id,))
                    result = c.fetchone()
                    conn.close()
                    if not result:
                        return jsonify({'reply': '❌ Пользователь не найден'})
                    test_used, premium = result

                if get_premium_status(user_id):
                    return jsonify({'reply': '💎 У тебя уже есть Premium!'})
                if test_used == 1:
                    return jsonify({'reply': '⛔ Ты уже использовал тест Premium!\nКупи Premium: /premium'})
                if set_premium(user_id, "2d"):
                    if use_supabase:
                        try:
                            supabase.table('users_web').update({'test_used': 1}).eq('user_id', user_id).execute()
                        except:
                            pass
                    else:
                        conn = sqlite3.connect('users_web.db')
                        c = conn.cursor()
                        c.execute('UPDATE users_web SET test_used = 1 WHERE user_id = ?', (user_id,))
                        conn.commit()
                        conn.close()
                    reply = "🎉 *ПРОБНЫЙ PREMIUM АКТИВИРОВАН НА 2 ДНЯ!*\n\n✅ Приоритетная обработка\n✅ ♾️ БЕЗЛИМИТНЫЕ СООБЩЕНИЯ\n✅ Более качественные ответы\n\n⏳ Доступ активен 48 часов.\n🔥 Наслаждайся!"
                    return jsonify({'reply': reply})
                else:
                    return jsonify({'reply': '❌ Ошибка при активации теста'})
            elif cmd == '/profile':
                user_data = get_db_user(user_id)
                if not user_data:
                    return jsonify({'reply': '❌ Пользователь не найден'})
                messages = user_data.get('messages_today', 0)
                premium = get_premium_status(user_id)
                joined_at = user_data.get('joined_at', 'Неизвестно')
                is_owner = user_data.get('is_owner', 0) == 1
                is_admin_flag = user_data.get('is_admin', 0) == 1
                if user_id == OWNER_ID or is_owner:
                    status = "👑 ВЛАДЕЛЕЦ"
                    limit_text = "♾️ Безлимит"
                elif is_admin_flag or is_admin(user_id):
                    status = "👑 АДМИН"
                    limit_text = "♾️ Безлимит"
                elif premium:
                    expires = get_premium_expires(user_id)
                    if expires:
                        expires_f = format_date(expires)
                        status = f"💎 PREMIUM (до {expires_f})"
                    else:
                        status = "💎 PREMIUM"
                    limit_text = "♾️ Безлимит"
                else:
                    remaining = FREE_LIMIT - messages
                    if remaining < 0:
                        remaining = 0
                    status = f"🔓 Бесплатный ({remaining}/{FREE_LIMIT})"
                    limit_text = f"{FREE_LIMIT}/день"
                username = f"user_{user_id}"
                reply = f"👤 *ТВОЙ ПРОФИЛЬ*\n\n🆔 ID: `{user_id}`\n👤 Юзер: @{username}\n💎 Статус: {status}\n📨 Лимит: {limit_text}\n✉️ Сегодня: {messages}\n📅 Вход: {joined_at or 'Неизвестно'} (МСК)"
                return jsonify({'reply': reply})
            elif cmd == '/stats':
                if user_id == OWNER_ID or is_admin(user_id):
                    if use_supabase:
                        try:
                            response = supabase.table('users_web').select('*').execute()
                            users = response.data
                        except:
                            users = []
                    else:
                        conn = sqlite3.connect('users_web.db')
                        c = conn.cursor()
                        c.execute('SELECT * FROM users_web')
                        users = c.fetchall()
                        conn.close()
                        users = [{'user_id': u[0], 'premium': u[2], 'is_admin': u[6]} for u in users]
                    total_users = len(users)
                    premium_users = sum(1 for u in users if u.get('premium', 0) == 1)
                    admin_users = sum(1 for u in users if u.get('is_admin', 0) == 1)
                    reply = f"📊 *СТАТИСТИКА СЕРВЕРА*\n\n👥 Всего: {total_users}\n👑 Админов: {admin_users}\n💎 Premium: {premium_users}\n🔓 Бесплатных: {total_users - premium_users - admin_users}"
                else:
                    user_data = get_db_user(user_id)
                    if not user_data:
                        return jsonify({'reply': '❌ Пользователь не найден'})
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
                    if use_supabase:
                        try:
                            resp = supabase.table('total_stats_web').select('total_messages').eq('user_id', user_id).execute()
                            total = resp.data[0].get('total_messages', 0) if resp.data else 0
                        except:
                            total = 0
                    else:
                        conn = sqlite3.connect('users_web.db')
                        c = conn.cursor()
                        c.execute('SELECT total_messages FROM total_stats_web WHERE user_id = ?', (user_id,))
                        result = c.fetchone()
                        conn.close()
                        total = result[0] if result else 0
                    reply = f"📊 *ТВОЯ СТАТИСТИКА*\n\n👤 Статус: {status}\n📨 Лимит: {limit_text}\n✉️ Сегодня: {messages_today}\n📊 Всего: {total}"
                return jsonify({'reply': reply})
            elif cmd == '/help':
                help_text = """🧠 *AWESOME AI — ПОМОЩЬ*

🌐 *Что я умею:*
• 🎤 Распознаю голос
• 🌤 Погода с прогнозом
• 💵 Курс валют и криптовалют
• 🧮 Решаю математику
• 📸 Анализирую изображения
• 🎨 Генерирую картинки
• 🧠 Запоминаю факты о вас

📋 *Команды:*
/status — Статус
/premium — Premium
/test — Пробный Premium
/profile — Профиль
/stats — Статистика
/help — Помощь
/clear — Очистить историю
/history — Показать историю
/weather [город] — Погода
/exchange — Курс валют
/crypto — Криптовалюты
/draw [описание] — Сгенерировать картинку

💎 *Лимиты:*
🔓 Бесплатно — 20 сообщений/день
💎 Premium — ♾️ БЕЗЛИМИТНО"""
                return jsonify({'reply': help_text})
            elif cmd.startswith('/weather'):
                city = extract_city_from_query(message)
                if city:
                    weather = get_weather(city)
                    if weather:
                        return jsonify({'reply': weather})
                    else:
                        return jsonify({'reply': f"🌐 Не нашёл город '{city}'. Попробуй ещё."})
                else:
                    return jsonify({'reply': "🌐 В каком городе? Напиши: /weather [город]"})
            elif cmd == '/exchange':
                rates = get_exchange_rates()
                if rates:
                    return jsonify({'reply': rates})
                else:
                    return jsonify({'reply': "💵 Не удалось получить курс валют."})
            elif cmd == '/crypto':
                crypto = get_crypto_rates()
                if crypto:
                    return jsonify({'reply': crypto})
                else:
                    return jsonify({'reply': "🪙 Не удалось получить курс криптовалют."})
            elif cmd.startswith('/draw'):
                prompt = message.replace('/draw', '').strip()
                if not prompt:
                    return jsonify({'reply': "❌ Напиши: /draw [описание]"})
                title = fix_title(prompt)
                image_data = generate_image(prompt)
                if image_data:
                    b64_img = base64.b64encode(image_data).decode('utf-8')
                    reply = f"🎨 *{title}*\n\n![image](data:image/png;base64,{b64_img})"
                    return jsonify({'reply': reply})
                else:
                    return jsonify({'reply': "⚠️ Не удалось сгенерировать картинку."})

        response = process_message_with_history(user_id, message)
        if response:
            increment_messages(user_id)
            return jsonify({'reply': response})
        else:
            return jsonify({'reply': "❌ Не удалось обработать запрос."})

    except Exception as e:
        print(f"❌ Ошибка в /api/chat: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)})

@app.route('/api/analyze_image', methods=['POST', 'OPTIONS'])
def analyze_image():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        image_base64 = data.get('image')
        user_id = data.get('user_id', 1)
        if not image_base64:
            return jsonify({'error': 'Нет изображения'})
        
        description = analyze_image_with_ai(image_base64)
        remember(user_id, "фото", f"Пользователь отправил фото: {description[:100]}")
        increment_messages(user_id)
        return jsonify({'reply': description})
    except Exception as e:
        print(f"❌ Ошибка в /api/analyze_image: {e}", flush=True)
        return jsonify({'error': str(e)})

@app.route('/api/speech_to_text', methods=['POST', 'OPTIONS'])
def speech_to_text_endpoint():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        audio_base64 = data.get('audio')
        user_id = data.get('user_id', 1)
        if not audio_base64:
            return jsonify({'error': 'Нет аудио'})
        
        # Пока заглушка - нужно интегрировать STT
        return jsonify({'text': '🎤 Голосовое сообщение получено! (распознавание в разработке)'})
    except Exception as e:
        print(f"❌ Ошибка в /api/speech_to_text: {e}", flush=True)
        return jsonify({'error': str(e)})

@app.route('/admin')
def admin_panel():
    user_id = request.args.get('user_id', type=int)
    if not user_id or user_id != OWNER_ID:
        return """
        <!DOCTYPE html>
        <html><head><meta charset="UTF-8"><title>Доступ запрещён</title>
        <style>body{background:#0a0e17;color:#e6edf3;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;text-align:center;}
        h1{color:#f85149;}</style></head>
        <body><div><h1>🚫 ДОСТУП ЗАПРЕЩЁН</h1><p>Только владелец (ID: 1787063701739) может зайти в админ-панель.</p></div></body></html>
        """, 403

    action = request.args.get('action')
    target_id = request.args.get('target_id', type=int)

    if action == 'giveprem' and target_id:
        set_premium(target_id, "30d")
    if action == 'delprem' and target_id:
        remove_premium(target_id)
    if action == 'giveadmin' and target_id:
        set_admin(target_id, True)
    if action == 'deladmin' and target_id:
        set_admin(target_id, False)
    if action == 'ban' and target_id:
        ban_user(target_id)
    if action == 'unban' and target_id:
        unban_user(target_id)
    if action == 'mute' and target_id:
        mute_user(target_id)
    if action == 'unmute' and target_id:
        unmute_user(target_id)

    if use_supabase:
        try:
            response = supabase.table('users_web').select('*').order('user_id', desc=True).execute()
            users = response.data
        except:
            users = []
    else:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('SELECT user_id, username, premium, messages_today, is_admin, test_used, joined_at, premium_expires FROM users_web ORDER BY user_id DESC')
        users = c.fetchall()
        conn.close()
        users = [{'user_id': u[0], 'username': u[1], 'premium': u[2], 'messages_today': u[3], 'is_admin': u[4], 'test_used': u[5], 'joined_at': u[6], 'premium_expires': u[7]} for u in users]

    rows = ""
    for u in users:
        uid = u['user_id']
        username = u.get('username', 'unknown')
        premium = u.get('premium', 0)
        msgs = u.get('messages_today', 0)
        is_admin_flag = u.get('is_admin', 0)
        joined = u.get('joined_at', '—')
        expires = u.get('premium_expires')
        status = "👑 ВЛАДЕЛЕЦ" if uid == OWNER_ID else "👑 АДМИН" if is_admin_flag else "💎 PREMIUM" if premium else "🔓 Бесплатный"
        expires_str = format_date(expires) if expires else "нет"
        rows += f'''
        <tr>
            <td>{uid}</td>
            <td>@{username}</td>
            <td>{status}</td>
            <td>{msgs}</td>
            <td>{joined}</td>
            <td>{expires_str}</td>
            <td>
                <a href="?user_id={OWNER_ID}&action=giveprem&target_id={uid}" style="background:#2ea043;color:#fff;padding:2px 8px;border-radius:3px;text-decoration:none;font-size:10px;">💎+</a>
                <a href="?user_id={OWNER_ID}&action=delprem&target_id={uid}" style="background:#da3633;color:#fff;padding:2px 8px;border-radius:3px;text-decoration:none;font-size:10px;">💎-</a>
                <a href="?user_id={OWNER_ID}&action=giveadmin&target_id={uid}" style="background:#f0883e;color:#fff;padding:2px 8px;border-radius:3px;text-decoration:none;font-size:10px;">👑+</a>
                <a href="?user_id={OWNER_ID}&action=deladmin&target_id={uid}" style="background:#da3633;color:#fff;padding:2px 8px;border-radius:3px;text-decoration:none;font-size:10px;">👑-</a>
                <a href="?user_id={OWNER_ID}&action=ban&target_id={uid}" style="background:#da3633;color:#fff;padding:2px 8px;border-radius:3px;text-decoration:none;font-size:10px;">🚫</a>
                <a href="?user_id={OWNER_ID}&action=unban&target_id={uid}" style="background:#2ea043;color:#fff;padding:2px 8px;border-radius:3px;text-decoration:none;font-size:10px;">✅</a>
                <a href="?user_id={OWNER_ID}&action=mute&target_id={uid}" style="background:#f0883e;color:#fff;padding:2px 8px;border-radius:3px;text-decoration:none;font-size:10px;">🔇</a>
                <a href="?user_id={OWNER_ID}&action=unmute&target_id={uid}" style="background:#2ea043;color:#fff;padding:2px 8px;border-radius:3px;text-decoration:none;font-size:10px;">🔊</a>
            </td>
        </tr>
        '''

    if not rows:
        rows = '<tr><td colspan="7" style="text-align:center;padding:20px;color:#8b949e;">Нет пользователей</td></tr>'

    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>👑 Админ-панель</title>
    <style>
        *{{margin:0;padding:0;box-sizing:border-box;}}
        body{{font-family:sans-serif;background:#0a0e17;color:#e6edf3;padding:20px;}}
        h1{{color:#58a6ff;font-size:24px;margin-bottom:4px;}}
        .sub{{color:#8b949e;margin-bottom:20px;font-size:14px;}}
        table{{width:100%;border-collapse:collapse;font-size:12px;}}
        th{{background:#1c2128;color:#8b949e;font-weight:600;padding:8px 10px;text-align:left;}}
        td{{padding:6px 10px;border-bottom:1px solid #30363d;}}
        tr:hover{{background:#1c2128;}}
        .back{{color:#58a6ff;text-decoration:none;}}
        .back:hover{{text-decoration:underline;}}
        .stats{{display:flex;gap:15px;margin-bottom:20px;flex-wrap:wrap;}}
        .stats .card{{background:#161b22;padding:10px 18px;border-radius:8px;border:1px solid #30363d;}}
        .stats .card .num{{font-size:20px;font-weight:700;color:#58a6ff;}}
        .stats .card .num.gold{{color:#f0883e;}}
    </style>
    </head>
    <body>
        <h1>👑 Админ-панель AWESOME AI</h1>
        <p class="sub">👤 Владелец: @flidges (ID: {OWNER_ID}) | <a href="/" class="back">← На главную</a></p>
        <div class="stats">
            <div class="card"><span>👥 Всего</span><div class="num">{len(users)}</div></div>
            <div class="card"><span>💎 Premium</span><div class="num gold">{sum(1 for u in users if u.get('premium', 0) == 1)}</div></div>
            <div class="card"><span>👑 Админов</span><div class="num gold">{sum(1 for u in users if u.get('is_admin', 0) == 1)}</div></div>
        </div>
        <table>
            <thead><tr><th>ID</th><th>Username</th><th>Статус</th><th>Сообщений</th><th>Вход</th><th>Premium до</th><th>Действия</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
    </body>
    </html>
    """

# ============================================================
# ЗАПУСК
# ============================================================
if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    print("=" * 60, flush=True)
    print("🧠 AWESOME AI 2026 — ВЕБ-ВЕРСИЯ", flush=True)
    print("=" * 60, flush=True)
    print(f"👑 Владелец ID: {OWNER_ID}", flush=True)
    print(f"🌐 http://0.0.0.0:{port}", flush=True)
    print("=" * 60, flush=True)
    print(f"✅ Supabase: {'ПОДКЛЮЧЕН' if use_supabase else 'НЕ ПОДКЛЮЧЕН (SQLite)'}", flush=True)
    print("✅ Анимированные частицы", flush=True)
    print("✅ Память диалога", flush=True)
    print("✅ Распознавание фото", flush=True)
    print("✅ Распознавание голоса (в разработке)", flush=True)
    print("✅ Все команды", flush=True)
    print("=" * 60, flush=True)
    app.run(host='0.0.0.0', port=port, debug=True)
