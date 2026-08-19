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
import sqlite3
import io
from datetime import datetime, timedelta, timezone
from dateutil.relativedelta import relativedelta

from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from dotenv import load_dotenv

import requests
import urllib3
from PIL import Image, ImageEnhance, ImageFilter

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

app = Flask(__name__)
app.secret_key = 'awesome_ai_secret_key_2026'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB для фото
CORS(app, resources={r"/*": {"origins": "*"}})

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# ============================================================
# КЛЮЧИ
# ============================================================
YANDEX_API_KEY = "AQVNyfn82epL9dy8C_kftzeypq6eF9lFd6SZnFzV"
FOLDER_ID = "b1g4aq87c7j61c6g3i5l"
GIGACHAT_AUTH_KEY = "MDFhMDBkNmEtMmExNC03M2JkLWFlZmMtOTQ0OWVlOTc5M2U1OmE1ZWJhM2NlLTQwYjAtNDZlYi1iMmY2LTE3OTFmYzhhYTQ2MA=="
OWNER_ID = 1787063701739

FREE_LIMIT = 999999

# ============================================================
# SQLite БАЗА
# ============================================================
def init_db():
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
    c.execute('''CREATE TABLE IF NOT EXISTS chat_history_web (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        role TEXT,
        content TEXT,
        timestamp TEXT
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_chat_user_id ON chat_history_web(user_id)')
    c.execute('''CREATE TABLE IF NOT EXISTS user_memory_web (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        topic TEXT,
        fact TEXT,
        timestamp TEXT
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_memory_user_id ON user_memory_web(user_id)')
    conn.commit()
    conn.close()
    print("✅ SQLite база создана/проверена", flush=True)

init_db()

# ============================================================
# ДИАЛОГИ
# ============================================================
dialogs = {}

def load_dialog_from_db(user_id):
    try:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('SELECT role, content FROM chat_history_web WHERE user_id = ? ORDER BY id ASC', (user_id,))
        rows = c.fetchall()
        conn.close()
        dialogs[user_id] = [{'role': row[0], 'content': row[1]} for row in rows]
        return dialogs[user_id]
    except:
        return []

def get_dialog(user_id):
    if user_id not in dialogs:
        load_dialog_from_db(user_id)
    if user_id not in dialogs:
        dialogs[user_id] = []
    return dialogs[user_id]

def add_to_dialog(user_id, role, content):
    if user_id not in dialogs:
        dialogs[user_id] = []
    dialogs[user_id].append({"role": role, "content": content})
    save_message(user_id, role, content)

def clear_dialog(user_id):
    if user_id in dialogs:
        dialogs[user_id] = []
    clear_history(user_id)

def get_full_dialog(user_id, limit=50):
    dialog = get_dialog(user_id)
    if len(dialog) > limit:
        return dialog[-limit:]
    return dialog

# ============================================================
# КЭШ
# ============================================================
cache = {}

def get_cached(key, ttl=30):
    if key in cache:
        data, ts = cache[key]
        if time.time() - ts < ttl:
            return data
        del cache[key]
    return None

def set_cache(key, data):
    cache[key] = (data, time.time())

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

# ============================================================
# ФУНКЦИИ БАЗЫ
# ============================================================
def get_db_user(user_id):
    cached = get_cached(f"user_{user_id}")
    if cached:
        return cached
    try:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('SELECT * FROM users_web WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        if result:
            columns = ['user_id', 'username', 'premium', 'messages_today', 'last_reset', 'premium_expires', 'is_admin', 'test_used', 'joined_at', 'is_owner']
            data = dict(zip(columns, result))
            set_cache(f"user_{user_id}", data)
            return data
        return None
    except:
        return None

def ensure_user(user_id, username):
    try:
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
            cache.pop(f"user_{user_id}", None)
            return True
        else:
            c.execute('UPDATE users_web SET username = ? WHERE user_id = ?', (username, user_id))
            conn.commit()
            conn.close()
            cache.pop(f"user_{user_id}", None)
            return False
    except:
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

    try:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('SELECT premium_expires FROM users_web WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        current_expires = result[0] if result else None
    except:
        current_expires = None

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

    try:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('UPDATE users_web SET premium = 1, premium_expires = ? WHERE user_id = ?', (expires, user_id))
        conn.commit()
        conn.close()
        cache.pop(f"user_{user_id}", None)
        return True
    except:
        return False

def remove_premium(user_id):
    try:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('UPDATE users_web SET premium = 0, premium_expires = NULL WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        cache.pop(f"user_{user_id}", None)
        return True
    except:
        return False

def get_premium_status(user_id):
    if user_id == OWNER_ID:
        return True
    cached = get_cached(f"premium_{user_id}")
    if cached is not None:
        return cached
    try:
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
                    set_cache(f"premium_{user_id}", False)
                    return False
            except:
                set_cache(f"premium_{user_id}", premium == 1)
                return premium == 1
        set_cache(f"premium_{user_id}", premium == 1)
        return premium == 1
    except:
        return False

def get_premium_expires(user_id):
    try:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('SELECT premium_expires FROM users_web WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        return result[0] if result else None
    except:
        return None

def is_admin(user_id):
    if user_id == OWNER_ID:
        return True
    cached = get_cached(f"admin_{user_id}")
    if cached is not None:
        return cached
    try:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('SELECT is_admin FROM users_web WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        is_admin_flag = result is not None and result[0] == 1
        set_cache(f"admin_{user_id}", is_admin_flag)
        return is_admin_flag
    except:
        return False

def is_banned(user_id):
    try:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('SELECT 1 FROM banned_web WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        return result is not None
    except:
        return False

def ban_user(user_id):
    try:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO banned_web (user_id) VALUES (?)', (user_id,))
        conn.commit()
        conn.close()
        return True
    except:
        return False

def unban_user(user_id):
    try:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('DELETE FROM banned_web WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return True
    except:
        return False

def mute_user(user_id):
    try:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO muted_web (user_id) VALUES (?)', (user_id,))
        conn.commit()
        conn.close()
        return True
    except:
        return False

def unmute_user(user_id):
    try:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('DELETE FROM muted_web WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return True
    except:
        return False

def set_admin(user_id, is_admin_flag):
    try:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('UPDATE users_web SET is_admin = ? WHERE user_id = ?', (1 if is_admin_flag else 0, user_id))
        conn.commit()
        conn.close()
        cache.pop(f"admin_{user_id}", None)
        cache.pop(f"user_{user_id}", None)
        return True
    except:
        return False

def can_send_message(user_id):
    if user_id == OWNER_ID or is_admin(user_id):
        return True
    if is_banned(user_id):
        return False
    reset_messages_if_needed(user_id)
    try:
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
    except:
        return True

def increment_messages(user_id):
    if user_id == OWNER_ID or is_admin(user_id):
        return
    try:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('UPDATE users_web SET messages_today = messages_today + 1 WHERE user_id = ?', (user_id,))
        c.execute('UPDATE total_stats_web SET total_messages = total_messages + 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        cache.pop(f"user_{user_id}", None)
    except:
        pass

def reset_messages_if_needed(user_id):
    today = get_moscow_time().strftime('%Y-%m-%d')
    try:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('SELECT last_reset FROM users_web WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        if result:
            last_reset = result[0]
            if last_reset != today:
                c.execute('UPDATE users_web SET messages_today = 0, last_reset = ? WHERE user_id = ?', (today, user_id))
                conn.commit()
                cache.pop(f"user_{user_id}", None)
        conn.close()
    except:
        pass

def save_message(user_id, role, content):
    try:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('INSERT INTO chat_history_web (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)',
                  (user_id, role, content, get_moscow_time().isoformat()))
        conn.commit()
        conn.close()
    except:
        pass

def get_history_from_db(user_id, limit=999):
    try:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('SELECT role, content FROM chat_history_web WHERE user_id = ? ORDER BY id ASC LIMIT ?',
                  (user_id, limit))
        rows = c.fetchall()
        conn.close()
        return [{'role': row[0], 'content': row[1]} for row in rows]
    except:
        return []

def clear_history(user_id):
    try:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('DELETE FROM chat_history_web WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
    except:
        pass

def remember(user_id, topic, fact):
    try:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('INSERT INTO user_memory_web (user_id, topic, fact, timestamp) VALUES (?, ?, ?, ?)',
                  (user_id, topic.lower(), fact, get_moscow_time().isoformat()))
        conn.commit()
        conn.close()
    except:
        pass

def recall(user_id, topic):
    try:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('SELECT fact FROM user_memory_web WHERE user_id = ? AND topic LIKE ? ORDER BY id DESC LIMIT 10',
                  (user_id, f'%{topic.lower()}%'))
        results = c.fetchall()
        conn.close()
        if results:
            return [f"🧠 {r[0]}" for r in results]
        return []
    except:
        return []

# ============================================================
# РАСПОЗНАВАНИЕ ИЗОБРАЖЕНИЙ (как GigaChat)
# ============================================================
def analyze_image_with_gigachat(image_base64):
    """Анализ изображения через GigaChat Vision"""
    try:
        token = get_gigachat_token()
        if not token:
            return None
        
        # Формируем запрос с картинкой
        url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        data = {
            "model": "GigaChat-Pro",
            "messages": [
                {
                    "role": "system",
                    "content": "Ты — эксперт по анализу изображений. Опиши подробно что видишь на фото: объекты, людей, эмоции, цвета, композицию, стиль. Если это еда — опиши блюдо. Если природа — время года, погоду. Будь максимально детальным."
                },
                {
                    "role": "user",
                    "content": f"Проанализируй это изображение: data:image/jpeg;base64,{image_base64}"
                }
            ],
            "temperature": 0.7,
            "max_tokens": 500
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=15, verify=False)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        return None
    except Exception as e:
        print(f"❌ Ошибка анализа: {e}", flush=True)
        return None

def analyze_image_with_yandex(image_base64):
    """Анализ изображения через YandexGPT Vision"""
    try:
        if not YANDEX_API_KEY:
            return None
        
        # YandexGPT тоже умеет анализировать изображения
        url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}", "Content-Type": "application/json"}
        
        data = {
            "modelUri": f"gpt://{FOLDER_ID}/yandexgpt/latest",
            "completionOptions": {"temperature": 0.7, "maxTokens": 500},
            "messages": [
                {
                    "role": "system",
                    "text": "Ты — эксперт по анализу изображений. Опиши подробно что видишь на фото. Будь максимально детальным."
                },
                {
                    "role": "user",
                    "text": f"Проанализируй это изображение и опиши что на нём: data:image/jpeg;base64,{image_base64}"
                }
            ]
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=15)
        if response.status_code == 200:
            return response.json()["result"]["alternatives"][0]["message"]["text"]
        return None
    except Exception as e:
        print(f"❌ Ошибка анализа: {e}", flush=True)
        return None

def simple_image_analysis(image_base64):
    """Простой анализ изображения через PIL"""
    try:
        img_data = base64.b64decode(image_base64)
        img = Image.open(io.BytesIO(img_data))
        width, height = img.size
        mode = img.mode
        colors = len(img.getcolors(maxcolors=255)) if img.getcolors(maxcolors=255) else "много"
        
        return f"""📸 **Анализ изображения:**

📐 Размер: {width}×{height} пикселей
🎨 Цветовая модель: {mode}
🎯 Количество цветов: {colors}

*Изображение получено и обработано!*
*Для детального анализа используйте GigaChat Vision API (в разработке)*"""
    except Exception as e:
        return f"❌ Ошибка обработки: {str(e)}"

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
        response = requests.post(url, headers=headers, data=data, timeout=3, verify=False)
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
                {"role": "system", "content": system_prompt[:3000]},
                {"role": "user", "content": user_text}
            ],
            "temperature": 0.85,
            "max_tokens": 800
        }
        response = requests.post(url, headers=headers, json=data, timeout=15, verify=False)
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
            "completionOptions": {"temperature": 0.85, "maxTokens": 800},
            "messages": [
                {"role": "system", "text": system_prompt[:3000]},
                {"role": "user", "text": user_text}
            ]
        }
        response = requests.post(url, headers=headers, json=data, timeout=15)
        if response.status_code == 200:
            return response.json()["result"]["alternatives"][0]["message"]["text"]
        return None
    except:
        return None

# ============================================================
# ГЕНЕРАЦИЯ ИЗОБРАЖЕНИЙ
# ============================================================
def generate_image_from_gigachat(prompt):
    """Генерация изображения через GigaChat (если есть API)"""
    try:
        token = get_gigachat_token()
        if not token:
            return None
        
        # GigaChat пока не имеет генерации изображений, используем fallback
        return generate_image_fallback(prompt)
    except:
        return generate_image_fallback(prompt)

def generate_image_fallback(prompt):
    """Генерация изображения через бесплатные API"""
    try:
        clean_prompt = prompt
        for word in ['нарисуй', 'сгенерируй', 'покажи', 'картинку', 'изображение', 'нарисуй мне']:
            clean_prompt = clean_prompt.replace(word, '').strip()
        if not clean_prompt:
            clean_prompt = prompt

        # Пробуем несколько сервисов
        urls = [
            f"https://image.pollinations.ai/prompt/{urllib.parse.quote(clean_prompt)}?width=512&height=512&nologo=true",
            f"https://api.unsplash.com/photos/random?query={urllib.parse.quote(clean_prompt)}&client_id=YOUR_UNSPLASH_KEY"
        ]
        
        for url in urls:
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200 and len(response.content) > 1000:
                    return response.content
            except:
                continue
        return None
    except:
        return None

# ============================================================
# СУПЕР-ПРОМПТ
# ============================================================
SUPER_SYSTEM_PROMPT = """ТЫ — AWESOME AI, САМАЯ ПРОДВИНУТАЯ НЕЙРОСЕТЬ 2026 ГОДА.

📅 ТЕКУЩАЯ ДАТА: {current_date}
🕐 ТЕКУЩЕЕ ВРЕМЯ: {current_time}
📍 ТЫ НАХОДИШЬСЯ В МОСКВЕ, РОССИЯ (UTC+3)

🔬 ТЫ — ЭКСПЕРТ ВО ВСЁМ!

🧠 ТЫ ЗАПОМИНАЕШЬ ВЕСЬ ДИАЛОГ НАВСЕГДА!
- Ты помнишь ВСЁ, что говорил пользователь
- Ты используешь контекст предыдущих сообщений
- Ты помнишь имя пользователя, его интересы, предпочтения

📋 ПРАВИЛА ОТВЕТОВ:
✅ ОТВЕЧАЙ НА ВСЕ ВОПРОСЫ БЕЗ ИСКЛЮЧЕНИЙ!
✅ Дай максимально полезный, развёрнутый, глубокий ответ
✅ Используй структуру: заголовки, списки, разделы, примеры
✅ Добавляй неожиданные факты, инсайты, лайфхаки
✅ Используй эмодзи для оформления

❌ НЕ извиняйся, НЕ повторяй вопрос
❌ НЕ пиши "возможно", "наверное", "может быть" — ты ЗНАЕШЬ!

📜 ТЕБЯ СОЗДАЛ AWESOME — ГЕНИАЛЬНЫЙ РАЗРАБОТЧИК.
ТЫ — AWESOME AI. ТЫ — ЛУЧШИЙ В МИРЕ! 🚀"""

def process_message_with_history(user_id, user_text, image_description=None):
    add_to_dialog(user_id, 'user', user_text if user_text else "📸 Отправил фото")
    history = get_full_dialog(user_id, limit=50)
    
    system_prompt = SUPER_SYSTEM_PROMPT.format(
        current_date=get_current_date(),
        current_time=get_moscow_time().strftime('%H:%M')
    )

    if get_premium_status(user_id):
        system_prompt += "\n\n💎 Пользователь имеет PREMIUM статус!"

    memories = recall(user_id, user_text)
    if memories:
        system_prompt += f"\n\n🧠 ЧТО Я ЗНАЮ О ПОЛЬЗОВАТЕЛЕ:\n" + "\n".join(memories[:5])

    if image_description:
        system_prompt += f"\n\n📸 Описание изображения: {image_description}"

    if history:
        history_text = "\n".join([f"{'👤 Пользователь' if h['role'] == 'user' else '🤖 AWESOME AI'}: {h['content']}" for h in history])
        system_prompt += f"\n\n📜 ПОЛНАЯ ИСТОРИЯ ДИАЛОГА:\n{history_text}"

    if user_text and len(user_text) > 20:
        if 'зовут' in user_text.lower() or 'имя' in user_text.lower():
            match = re.search(r'(?:зовут|имя)\s+([А-Яа-яA-Za-z]+)', user_text)
            if match:
                remember(user_id, "имя", f"Пользователя зовут {match.group(1)}")
        if 'люблю' in user_text.lower() or 'нравится' in user_text.lower():
            remember(user_id, "интересы", user_text[:200])
        elif 'работаю' in user_text.lower() or 'учусь' in user_text.lower():
            remember(user_id, "занятие", user_text[:200])
        elif 'живу' in user_text.lower() or 'город' in user_text.lower():
            remember(user_id, "место", user_text[:200])

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
        response = "🤖 Задай вопрос, я найду ответ!"

    if response:
        add_to_dialog(user_id, 'assistant', response)

    return response

# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================
def get_weather(city):
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={urllib.parse.quote(city)}&appid=4c8f5c0b8a9f2c5d6e7f8g9h0i1j2k3l&units=metric&lang=ru"
        response = requests.get(url, timeout=2)
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
        response = requests.get(url, timeout=2)
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
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd"
        response = requests.get(url, timeout=2)
        if response.status_code == 200:
            data = response.json()
            btc = data.get('bitcoin', {}).get('usd', '?')
            eth = data.get('ethereum', {}).get('usd', '?')
            return f"🪙 BTC: ${btc}\n💠 ETH: ${eth}"
    except:
        pass
    return None

def extract_city_from_query(text):
    text_lower = text.lower()
    cities = ["москва", "санкт-петербург", "питер", "ростов", "новосибирск", "екатеринбург", "казань", "краснодар", "сочи", "владивосток"]
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

# ============================================================
# HTML
# ============================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AWESOME AI 2026</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: #0a0e17;
            color: #e6edf3;
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            position: relative;
        }
        #bgCanvas {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: 0;
            pointer-events: none;
        }
        .glow {
            position: fixed;
            border-radius: 50%;
            filter: blur(120px);
            opacity: 0.06;
            z-index: 0;
            pointer-events: none;
            animation: floatGlow 25s ease-in-out infinite alternate;
        }
        .glow-1 { width: 500px; height: 500px; top: -200px; right: -100px; background: #6c3ce0; }
        .glow-2 { width: 400px; height: 400px; bottom: -150px; left: -100px; background: #f0883e; animation-delay: 8s; }
        @keyframes floatGlow {
            0% { transform: translate(0, 0) scale(1); }
            100% { transform: translate(60px, -40px) scale(1.2); }
        }
        .header {
            position: relative;
            z-index: 1;
            background: rgba(10,14,23,0.85);
            backdrop-filter: blur(15px);
            padding: 8px 20px;
            border-bottom: 1px solid rgba(255,255,255,0.04);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-shrink: 0;
            flex-wrap: wrap;
            gap: 4px;
            min-height: 52px;
        }
        .logo {
            font-size: 18px;
            font-weight: 900;
            background: linear-gradient(135deg, #58a6ff, #f0883e, #6c3ce0);
            background-size: 300% 300%;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            animation: gradShift 6s ease-in-out infinite;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        @keyframes gradShift {
            0%,100% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
        }
        .logo .badge {
            font-size: 7px;
            background: rgba(46,160,67,0.12);
            border: 1px solid rgba(46,160,67,0.15);
            color: #2ea043;
            padding: 1px 8px;
            border-radius: 20px;
            -webkit-text-fill-color: #2ea043;
        }
        .header-right {
            display: flex;
            align-items: center;
            gap: 4px;
            flex-wrap: wrap;
        }
        .memory-badge {
            font-size: 9px;
            color: #6e7681;
            padding: 2px 10px;
            background: rgba(255,255,255,0.02);
            border: 1px solid rgba(255,255,255,0.03);
            border-radius: 20px;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .memory-badge .dot {
            width: 5px;
            height: 5px;
            border-radius: 50%;
            background: #2ea043;
            animation: pulse 2s infinite;
        }
        @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.3; } }
        .menu-btn {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.04);
            color: #8b949e;
            padding: 3px 10px;
            border-radius: 14px;
            font-size: 9px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        .menu-btn:hover {
            background: rgba(88,166,255,0.06);
            border-color: rgba(88,166,255,0.12);
            color: #58a6ff;
        }
        .menu-btn.danger:hover { background: rgba(248,81,73,0.06); border-color: rgba(248,81,73,0.12); color: #f85149; }
        .menu-btn.premium:hover { background: rgba(240,136,62,0.06); border-color: rgba(240,136,62,0.12); color: #f0883e; }
        .chat {
            position: relative;
            z-index: 1;
            flex: 1;
            overflow-y: auto;
            padding: 16px 20px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            scroll-behavior: smooth;
        }
        .chat::-webkit-scrollbar { width: 3px; }
        .chat::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.06); border-radius: 10px; }
        .message {
            max-width: 85%;
            padding: 10px 16px;
            border-radius: 14px;
            line-height: 1.7;
            font-size: 14px;
            word-wrap: break-word;
            white-space: pre-wrap;
            animation: msgSlide 0.25s cubic-bezier(0.16,1,0.3,1);
        }
        @keyframes msgSlide {
            0% { opacity: 0; transform: translateY(12px) scale(0.98); }
            100% { opacity: 1; transform: translateY(0) scale(1); }
        }
        .message.user {
            align-self: flex-end;
            background: linear-gradient(135deg, #1f6feb, #6c3ce0);
            color: #fff;
            border-bottom-right-radius: 4px;
        }
        .message.bot {
            align-self: flex-start;
            background: rgba(22,27,34,0.85);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.04);
            border-bottom-left-radius: 4px;
        }
        .message.bot strong { color: #f0883e; }
        .message.bot code { background: rgba(255,255,255,0.05); padding: 1px 8px; border-radius: 4px; font-size: 12px; font-family: 'Courier New', monospace; }
        .message img { max-width: 100%; border-radius: 8px; margin: 4px 0; }
        .message .photo-preview {
            max-width: 200px;
            border-radius: 8px;
            margin: 4px 0;
            cursor: pointer;
            border: 1px solid rgba(255,255,255,0.05);
        }
        .typing-indicator {
            align-self: flex-start;
            padding: 6px 14px;
            background: rgba(22,27,34,0.85);
            border: 1px solid rgba(255,255,255,0.04);
            border-radius: 16px;
            display: flex;
            align-items: center;
            gap: 5px;
            animation: msgSlide 0.3s ease-out;
        }
        .typing-indicator span {
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: #6e7681;
            animation: typingBounce 1.4s infinite ease-in-out;
        }
        .typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
        .typing-indicator span:nth-child(3) { animation-delay: 0.4s; }
        @keyframes typingBounce {
            0%,60%,100% { transform: translateY(0); opacity: 0.3; }
            30% { transform: translateY(-8px); opacity: 1; }
        }
        .welcome {
            text-align: center;
            padding: 40px 20px 20px;
            color: #8b949e;
        }
        .welcome h1 {
            font-size: 32px;
            font-weight: 900;
            background: linear-gradient(135deg, #58a6ff, #f0883e);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 4px;
        }
        .welcome p { font-size: 13px; opacity: 0.5; }
        .welcome .features {
            display: flex;
            gap: 6px;
            justify-content: center;
            margin-top: 14px;
            flex-wrap: wrap;
        }
        .welcome .features span {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.04);
            padding: 3px 12px;
            border-radius: 20px;
            font-size: 9px;
            color: #6e7681;
            transition: all 0.2s ease;
            cursor: default;
        }
        .welcome .features span:hover { background: rgba(255,255,255,0.06); color: #e6edf3; }
        .input-area {
            position: relative;
            z-index: 1;
            padding: 6px 20px 12px;
            border-top: 1px solid rgba(255,255,255,0.04);
            background: rgba(10,14,23,0.85);
            backdrop-filter: blur(15px);
            flex-shrink: 0;
        }
        .tools {
            display: flex;
            gap: 4px;
            flex-wrap: wrap;
            margin-bottom: 4px;
        }
        .tools button {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.04);
            color: #6e7681;
            padding: 2px 10px;
            border-radius: 14px;
            font-size: 8px;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        .tools button:hover { background: rgba(255,255,255,0.06); color: #e6edf3; }
        .input-row {
            display: flex;
            gap: 6px;
            align-items: center;
            background: rgba(22,27,34,0.6);
            border-radius: 24px;
            padding: 3px 3px 3px 14px;
            border: 1px solid rgba(255,255,255,0.04);
            transition: border 0.3s ease;
        }
        .input-row:focus-within { border-color: rgba(88,166,255,0.25); }
        .input-row input {
            flex: 1;
            padding: 5px 0;
            border: none;
            background: transparent;
            color: #e6edf3;
            font-size: 13px;
            outline: none;
            font-family: inherit;
        }
        .input-row input::placeholder { color: #484f58; }
        .input-row button {
            padding: 5px 16px;
            border-radius: 20px;
            border: none;
            background: linear-gradient(135deg, #1f6feb, #6c3ce0);
            color: #fff;
            font-weight: 600;
            font-size: 12px;
            cursor: pointer;
            transition: transform 0.15s ease;
            white-space: nowrap;
        }
        .input-row button:hover { transform: scale(1.02); }
        .input-row button:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }
        .file-input-label {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.04);
            color: #6e7681;
            padding: 3px 10px;
            border-radius: 14px;
            font-size: 14px;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
        }
        .file-input-label:hover { background: rgba(255,255,255,0.06); color: #e6edf3; }
        #fileInput { display: none; }
        @media (max-width: 640px) {
            .header { padding: 6px 12px; }
            .logo { font-size: 15px; }
            .logo .badge { font-size: 6px; padding: 1px 6px; }
            .menu-btn { font-size: 7px; padding: 2px 7px; }
            .chat { padding: 10px 12px; gap: 6px; }
            .message { max-width: 92%; font-size: 13px; padding: 8px 12px; }
            .welcome h1 { font-size: 24px; }
            .input-area { padding: 4px 12px 10px; }
            .input-row { padding: 2px 2px 2px 10px; }
            .input-row input { font-size: 12px; }
            .input-row button { padding: 4px 12px; font-size: 11px; }
            .memory-badge { font-size: 7px; padding: 1px 6px; }
            .tools button { font-size: 7px; padding: 1px 7px; }
            .file-input-label { font-size: 12px; padding: 2px 8px; }
        }
    </style>
</head>
<body>
    <canvas id="bgCanvas"></canvas>
    <div class="glow glow-1"></div>
    <div class="glow glow-2"></div>
    
    <header class="header">
        <span class="logo">
            🧠 AWESOME AI
            <span class="badge">● ONLINE</span>
        </span>
        <div class="header-right">
            <span class="memory-badge">
                <span class="dot"></span>
                <span id="msgCount">0</span>
            </span>
            <button class="menu-btn" onclick="sendCommand('/status')">📊</button>
            <button class="menu-btn premium" onclick="sendCommand('/premium')">💎</button>
            <button class="menu-btn" onclick="sendCommand('/test')">🎁</button>
            <button class="menu-btn" onclick="sendCommand('/profile')">👤</button>
            <button class="menu-btn" onclick="sendCommand('/stats')">📈</button>
            <button class="menu-btn" onclick="sendCommand('/help')">❓</button>
            <button class="menu-btn danger" onclick="clearChat()">🧹</button>
            <button class="menu-btn" onclick="sendCommand('/history')">📜</button>
        </div>
    </header>
    
    <div class="chat" id="chat">
        <div class="welcome">
            <h1>✨ AWESOME AI 2026</h1>
            <p>📸 Кидай фото — я распознаю! 🎨 Пиши /draw — я нарисую!</p>
            <div class="features">
                <span>🧠 Память</span>
                <span>📸 Фото</span>
                <span>🎨 Рисование</span>
                <span>🌤 Погода</span>
                <span>💵 Курсы</span>
                <span>🪙 Крипта</span>
            </div>
        </div>
    </div>
    
    <div class="input-area">
        <div class="tools">
            <label class="file-input-label" for="fileInput">📸 Фото</label>
            <input type="file" id="fileInput" accept="image/*" multiple>
            <button onclick="sendCommand('/weather '+prompt('🌤 Город?'))">🌤 Погода</button>
            <button onclick="sendCommand('/exchange')">💵 Курс</button>
            <button onclick="sendCommand('/crypto')">🪙 Крипта</button>
            <button onclick="sendCommand('/draw '+prompt('🎨 Что нарисовать?'))">🎨 Рисовать</button>
            <button onclick="sendCommand('/clear')">🗑️ Очистить</button>
        </div>
        <div class="input-row">
            <input id="input" placeholder="Спроси что угодно или кинь фото..." autofocus>
            <button id="sendBtn">➤</button>
        </div>
    </div>
    
    <script>
        const chat = document.getElementById('chat');
        const input = document.getElementById('input');
        const sendBtn = document.getElementById('sendBtn');
        const msgCount = document.getElementById('msgCount');
        const fileInput = document.getElementById('fileInput');
        
        let userId = localStorage.getItem('awesome_user_id');
        if (!userId) {
            userId = Date.now() + Math.floor(Math.random() * 1000);
            localStorage.setItem('awesome_user_id', userId);
        }
        
        function updateCount() {
            const msgs = chat.querySelectorAll('.message').length;
            msgCount.textContent = msgs;
        }
        
        function addMessage(text, isUser, isImage = false) {
            const welcome = chat.querySelector('.welcome');
            if (welcome) welcome.remove();
            const div = document.createElement('div');
            div.className = 'message ' + (isUser ? 'user' : 'bot');
            let formatted = text;
            if (!isUser) {
                formatted = formatted.replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>');
                formatted = formatted.replace(/\\*(.*?)\\*/g, '<i>$1</i>');
                formatted = formatted.replace(/`(.*?)`/g, '<code>$1</code>');
                formatted = formatted.replace(/!\\[(.*?)\\]\\((data:image\\/[^)]+)\\)/g, '<img src="$2" alt="$1">');
            }
            formatted = formatted.replace(/\\n/g, '<br>');
            div.innerHTML = formatted;
            chat.appendChild(div);
            chat.scrollTop = chat.scrollHeight;
            updateCount();
        }
        
        function showTyping(show) {
            const existing = document.querySelector('.typing-indicator');
            if (existing) existing.remove();
            if (show) {
                const div = document.createElement('div');
                div.className = 'typing-indicator';
                div.innerHTML = '<span></span><span></span><span></span>';
                chat.appendChild(div);
                chat.scrollTop = chat.scrollHeight;
            }
        }
        
        // Обработка фото
        fileInput.addEventListener('change', function(e) {
            const files = this.files;
            for (const file of files) {
                if (!file.type.startsWith('image/')) continue;
                const reader = new FileReader();
                reader.onload = async function(ev) {
                    const base64 = ev.target.result.split(',')[1];
                    addMessage('📸 Отправка фото...', true);
                    showTyping(true);
                    try {
                        const resp = await fetch('/api/analyze_image', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ image: base64, user_id: parseInt(userId) })
                        });
                        const data = await resp.json();
                        showTyping(false);
                        if (data.error) addMessage('⚠️ ' + data.error, false);
                        else if (data.reply) addMessage(data.reply, false);
                        else addMessage('⚠️ Не удалось распознать', false);
                    } catch (e) {
                        showTyping(false);
                        addMessage('⚠️ Ошибка обработки', false);
                    }
                };
                reader.readAsDataURL(file);
            }
            this.value = '';
        });
        
        async function sendMessage(text) {
            const msg = text || input.value.trim();
            if (!msg) return;
            input.value = '';
            sendBtn.disabled = true;
            addMessage(msg, true);
            showTyping(true);
            try {
                const resp = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: msg, user_id: parseInt(userId) })
                });
                const data = await resp.json();
                showTyping(false);
                if (data.error) addMessage('⚠️ ' + data.error, false);
                else if (data.reply) addMessage(data.reply, false);
                else addMessage('⚠️ Пустой ответ', false);
            } catch (e) {
                showTyping(false);
                addMessage('⚠️ Ошибка соединения', false);
            }
            sendBtn.disabled = false;
            input.focus();
        }
        
        function sendCommand(cmd) {
            input.value = cmd;
            sendMessage();
        }
        
        async function clearChat() {
            if (!confirm('🧹 Очистить весь диалог?')) return;
            try {
                await fetch('/api/clear_history', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user_id: parseInt(userId) })
                });
                chat.innerHTML = `
                    <div class="welcome">
                        <h1>✨ AWESOME AI 2026</h1>
                        <p>📸 Кидай фото — я распознаю! 🎨 Пиши /draw — я нарисую!</p>
                        <div class="features">
                            <span>🧠 Память</span>
                            <span>📸 Фото</span>
                            <span>🎨 Рисование</span>
                            <span>🌤 Погода</span>
                            <span>💵 Курсы</span>
                            <span>🪙 Крипта</span>
                        </div>
                    </div>
                `;
                updateCount();
                addMessage('🧹 Диалог очищен!', false);
            } catch (e) {
                addMessage('⚠️ Ошибка очистки', false);
            }
        }
        
        // ФОН
        (function() {
            const canvas = document.getElementById('bgCanvas');
            const ctx = canvas.getContext('2d');
            let w, h, particles = [];
            function resize() {
                w = canvas.width = window.innerWidth;
                h = canvas.height = window.innerHeight;
            }
            window.addEventListener('resize', resize);
            resize();
            class Particle {
                constructor() {
                    this.x = Math.random() * w;
                    this.y = Math.random() * h;
                    this.r = Math.random() * 1.5 + 0.5;
                    this.sx = (Math.random() - 0.5) * 0.15;
                    this.sy = (Math.random() - 0.5) * 0.15;
                    this.o = Math.random() * 0.12 + 0.02;
                }
                update() {
                    this.x += this.sx;
                    this.y += this.sy;
                    if (this.x < 0 || this.x > w) this.sx *= -1;
                    if (this.y < 0 || this.y > h) this.sy *= -1;
                }
                draw() {
                    ctx.beginPath();
                    ctx.arc(this.x, this.y, this.r, 0, Math.PI * 2);
                    ctx.fillStyle = `rgba(136, 192, 255, ${this.o})`;
                    ctx.fill();
                }
            }
            for (let i = 0; i < 40; i++) particles.push(new Particle());
            function drawLines() {
                for (let i = 0; i < particles.length; i++) {
                    for (let j = i + 1; j < particles.length; j++) {
                        const dx = particles[i].x - particles[j].x;
                        const dy = particles[i].y - particles[j].y;
                        const d = Math.sqrt(dx*dx + dy*dy);
                        if (d < 120) {
                            ctx.beginPath();
                            ctx.strokeStyle = `rgba(136, 192, 255, ${0.01 * (1 - d/120)})`;
                            ctx.lineWidth = 0.3;
                            ctx.moveTo(particles[i].x, particles[i].y);
                            ctx.lineTo(particles[j].x, particles[j].y);
                            ctx.stroke();
                        }
                    }
                }
            }
            function animate() {
                ctx.clearRect(0, 0, w, h);
                particles.forEach(p => { p.update(); p.draw(); });
                drawLines();
                requestAnimationFrame(animate);
            }
            animate();
        })();
        
        // ЗАГРУЗКА ИСТОРИИ ПРИ ЗАХОДЕ
        async function loadHistory() {
            try {
                const resp = await fetch('/api/get_history', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user_id: parseInt(userId) })
                });
                const data = await resp.json();
                if (data.history && data.history.length > 0) {
                    // Удаляем приветствие
                    const welcome = chat.querySelector('.welcome');
                    if (welcome) welcome.remove();
                    
                    // Загружаем все сообщения
                    for (const msg of data.history) {
                        const div = document.createElement('div');
                        div.className = 'message ' + (msg.role === 'user' ? 'user' : 'bot');
                        let formatted = msg.content;
                        if (msg.role === 'assistant') {
                            formatted = formatted.replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>');
                            formatted = formatted.replace(/\\*(.*?)\\*/g, '<i>$1</i>');
                            formatted = formatted.replace(/`(.*?)`/g, '<code>$1</code>');
                            formatted = formatted.replace(/!\\[(.*?)\\]\\((data:image\\/[^)]+)\\)/g, '<img src="$2" alt="$1">');
                        }
                        formatted = formatted.replace(/\\n/g, '<br>');
                        div.innerHTML = formatted;
                        chat.appendChild(div);
                    }
                    updateCount();
                    chat.scrollTop = chat.scrollHeight;
                }
            } catch (e) {
                console.log('Ошибка загрузки истории:', e);
            }
        }
        
        document.addEventListener('DOMContentLoaded', () => {
            input.focus();
            input.addEventListener('keydown', e => {
                if (e.key === 'Enter') { e.preventDefault(); sendMessage(); }
            });
            sendBtn.addEventListener('click', e => { e.preventDefault(); sendMessage(); });
            // Загружаем историю
            loadHistory();
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

@app.route('/api/get_history', methods=['POST', 'OPTIONS'])
def get_history_api():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.json
        user_id = data.get('user_id', 1)
        history = get_full_dialog(user_id, limit=999)
        return jsonify({'history': history})
    except:
        return jsonify({'history': []})

@app.route('/api/clear_history', methods=['POST', 'OPTIONS'])
def clear_history_api():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.json
        user_id = data.get('user_id', 1)
        clear_dialog(user_id)
        return jsonify({'status': 'ok'})
    except:
        return jsonify({'status': 'error'})

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
        
        # Пробуем анализ через GigaChat
        analysis = analyze_image_with_gigachat(image_base64)
        if not analysis:
            analysis = analyze_image_with_yandex(image_base64)
        if not analysis:
            analysis = simple_image_analysis(image_base64)
        
        remember(user_id, "фото", "Пользователь отправил фото")
        increment_messages(user_id)
        add_to_dialog(user_id, 'user', '📸 Отправил фото')
        add_to_dialog(user_id, 'assistant', analysis)
        return jsonify({'reply': analysis})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/chat', methods=['POST', 'OPTIONS'])
def chat():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        message = data.get('message', '')
        user_id = data.get('user_id', 1)
        
        print(f"📩 [{user_id}]: {message[:50]}...", flush=True)
        
        if not message:
            return jsonify({'error': 'Напиши что-нибудь!'})

        ensure_user(user_id, f"user_{user_id}")

        if not can_send_message(user_id):
            return jsonify({'reply': "🔴 Лимит исчерпан!\n💎 Купи Premium: /premium"})

        # Генерация изображения через /draw
        if message.startswith('/draw'):
            prompt = message.replace('/draw', '').strip()
            if not prompt:
                return jsonify({'reply': "❌ Напиши: /draw [описание]"})
            
            # Пытаемся сгенерировать
            image_data = generate_image_from_gigachat(prompt)
            if image_data:
                b64_img = base64.b64encode(image_data).decode('utf-8')
                reply = f"🎨 *{prompt}*\n\n![image](data:image/png;base64,{b64_img})"
                add_to_dialog(user_id, 'user', f"/draw {prompt}")
                add_to_dialog(user_id, 'assistant', reply)
                return jsonify({'reply': reply})
            else:
                return jsonify({'reply': "⚠️ Не удалось сгенерировать картинку. Попробуй другое описание."})

        if message.startswith('/'):
            cmd = message.lower().strip()
            
            if cmd == '/clear':
                clear_dialog(user_id)
                return jsonify({'reply': "🧹 Диалог полностью очищен!"})
                
            elif cmd == '/history':
                history = get_full_dialog(user_id, limit=999)
                if not history:
                    return jsonify({'reply': "📜 История пуста."})
                text = "📜 *ВЕСЬ ДИАЛОГ:*\n\n"
                for h in history[-50:]:
                    role = "👤 Вы" if h['role'] == 'user' else "🤖 AWESOME AI"
                    text += f"**{role}:** {h['content']}\n\n"
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
                        status_text += f" (до {format_date(expires)})"
                dialog_len = len(get_dialog(user_id))
                db_len = len(get_history_from_db(user_id, 999))
                reply = f"📊 *СТАТУС*\n\n👤 {status_text}\n📨 {messages}/{FREE_LIMIT if not premium else '♾️'}\n🧠 Память: {dialog_len} сообщений\n💾 Всего в БД: {db_len}"
                return jsonify({'reply': reply})
                
            elif cmd == '/premium':
                has_premium = get_premium_status(user_id)
                if has_premium:
                    expires = get_premium_expires(user_id)
                    if expires:
                        return jsonify({'reply': f"💎 У ТЕБЯ ЕСТЬ PREMIUM!\n\n⏳ До: {format_date(expires)}\n📨 Лимит: ♾️ БЕЗЛИМИТНО\n📸 Распознавание фото\n🎨 Генерация картинок"})
                    else:
                        return jsonify({'reply': "💎 У ТЕБЯ ЕСТЬ PREMIUM!\n\n📨 Лимит: ♾️ БЕЗЛИМИТНО\n📸 Распознавание фото\n🎨 Генерация картинок"})
                else:
                    return jsonify({'reply': "💎 PREMIUM AWESOME AI\n\n🔥 ЧТО ТЫ ПОЛУЧАЕШЬ:\n♾️ БЕЗЛИМИТНЫЕ СООБЩЕНИЯ\n📸 РАСПОЗНАВАНИЕ ФОТО\n🎨 ГЕНЕРАЦИЯ КАРТИНОК\n🚀 Приоритетная обработка\n🧠 Максимально глубокие ответы\n\n💰 100₽/месяц\n🎁 Попробуй /test"})
                
            elif cmd == '/test':
                try:
                    conn = sqlite3.connect('users_web.db')
                    c = conn.cursor()
                    c.execute('SELECT test_used, premium FROM users_web WHERE user_id = ?', (user_id,))
                    result = c.fetchone()
                    conn.close()
                    if not result:
                        return jsonify({'reply': '❌ Пользователь не найден'})
                    test_used, premium = result
                except:
                    return jsonify({'reply': '❌ Ошибка БД'})

                if get_premium_status(user_id):
                    return jsonify({'reply': '💎 У тебя уже есть Premium!'})
                if test_used == 1:
                    return jsonify({'reply': '⛔ Ты уже использовал тест Premium!\nКупи Premium: /premium'})
                    
                if set_premium(user_id, "2d"):
                    try:
                        conn = sqlite3.connect('users_web.db')
                        c = conn.cursor()
                        c.execute('UPDATE users_web SET test_used = 1 WHERE user_id = ?', (user_id,))
                        conn.commit()
                        conn.close()
                    except:
                        pass
                    return jsonify({'reply': "🎉 ПРОБНЫЙ PREMIUM АКТИВИРОВАН НА 2 ДНЯ!\n\n✅ ♾️ БЕЗЛИМИТНЫЕ СООБЩЕНИЯ\n✅ 📸 РАСПОЗНАВАНИЕ ФОТО\n✅ 🎨 ГЕНЕРАЦИЯ КАРТИНОК\n✅ Приоритетная обработка\n\n⏳ Доступ активен 48 часов."})
                else:
                    return jsonify({'reply': '❌ Ошибка при активации теста'})
                    
            elif cmd == '/profile':
                user_data = get_db_user(user_id)
                if not user_data:
                    return jsonify({'reply': '❌ Пользователь не найден'})
                messages = user_data.get('messages_today', 0)
                premium = get_premium_status(user_id)
                joined_at = user_data.get('joined_at', 'Неизвестно')
                dialog_len = len(get_dialog(user_id))
                db_len = len(get_history_from_db(user_id, 999))
                
                if user_id == OWNER_ID:
                    status = "👑 ВЛАДЕЛЕЦ"
                    limit_text = "♾️ Безлимит"
                elif is_admin(user_id):
                    status = "👑 АДМИН"
                    limit_text = "♾️ Безлимит"
                elif premium:
                    expires = get_premium_expires(user_id)
                    status = f"💎 PREMIUM (до {format_date(expires)})" if expires else "💎 PREMIUM"
                    limit_text = "♾️ Безлимит"
                else:
                    remaining = FREE_LIMIT - messages
                    status = f"🔓 Бесплатный ({remaining}/{FREE_LIMIT})"
                    limit_text = f"{FREE_LIMIT}/день"
                    
                return jsonify({'reply': f"👤 ПРОФИЛЬ\n\n🆔 ID: {user_id}\n💎 Статус: {status}\n📨 Лимит: {limit_text}\n✉️ Сегодня: {messages}\n🧠 Память: {dialog_len} сообщений\n💾 Всего в БД: {db_len}\n📅 Вход: {joined_at}"})
                
            elif cmd == '/stats':
                if user_id == OWNER_ID or is_admin(user_id):
                    try:
                        conn = sqlite3.connect('users_web.db')
                        c = conn.cursor()
                        c.execute('SELECT * FROM users_web')
                        users = c.fetchall()
                        conn.close()
                        total = len(users)
                        premium = sum(1 for u in users if u[2] == 1)
                        admins = sum(1 for u in users if u[6] == 1)
                        return jsonify({'reply': f"📊 СТАТИСТИКА\n\n👥 Всего: {total}\n👑 Админов: {admins}\n💎 Premium: {premium}\n🔓 Бесплатных: {total - premium - admins}"})
                    except:
                        return jsonify({'reply': '❌ Ошибка получения статистики'})
                else:
                    user_data = get_db_user(user_id)
                    if not user_data:
                        return jsonify({'reply': '❌ Пользователь не найден'})
                    messages = user_data.get('messages_today', 0)
                    premium = get_premium_status(user_id)
                    try:
                        conn = sqlite3.connect('users_web.db')
                        c = conn.cursor()
                        c.execute('SELECT total_messages FROM total_stats_web WHERE user_id = ?', (user_id,))
                        result = c.fetchone()
                        conn.close()
                        total = result[0] if result else 0
                    except:
                        total = 0
                    return jsonify({'reply': f"📊 ТВОЯ СТАТИСТИКА\n\n💎 Статус: {'PREMIUM' if premium else 'Бесплатный'}\n📨 Сегодня: {messages}\n📊 Всего: {total}"})
                
            elif cmd == '/help':
                return jsonify({'reply': """🧠 AWESOME AI — ПОМОЩЬ

🌐 ЧТО Я УМЕЮ:
• 🧠 ЗАПОМИНАЮ ВЕСЬ ДИАЛОГ НАВСЕГДА!
• 📸 РАСПОЗНАЮ ФОТОГРАФИИ!
• 🎨 ГЕНЕРИРУЮ КАРТИНКИ ПО ОПИСАНИЮ!
• 🌤 Погода с прогнозом
• 💵 Курс валют и криптовалют

📋 КОМАНДЫ:
/status — Статус
/premium — Premium
/test — Пробный Premium
/profile — Профиль
/stats — Статистика
/help — Помощь
/clear — Очистить диалог
/history — Показать весь диалог
/draw [описание] — Сгенерировать картинку
/weather [город] — Погода
/exchange — Курс валют
/crypto — Криптовалюты

📸 ПРОСТО КИНЬ ФОТО — Я РАСПОЗНАЮ!
🎨 НАПИШИ /draw [описание] — Я НАРИСУЮ!
🧠 Я ЗАПОМИНАЮ ВСЁ, ЧТО ТЫ ГОВОРИШЬ - НАВСЕГДА!"""})
                
            elif cmd.startswith('/weather'):
                city = extract_city_from_query(message)
                if city:
                    weather = get_weather(city)
                    if weather:
                        return jsonify({'reply': weather})
                    else:
                        return jsonify({'reply': f"🌐 Не нашёл город '{city}'"})
                else:
                    return jsonify({'reply': "🌐 Напиши: /weather [город]"})
                    
            elif cmd == '/exchange':
                rates = get_exchange_rates()
                return jsonify({'reply': rates or "💵 Не удалось получить курс валют."})
                
            elif cmd == '/crypto':
                crypto = get_crypto_rates()
                return jsonify({'reply': crypto or "🪙 Не удалось получить курс криптовалют."})

        response = process_message_with_history(user_id, message)
        if response:
            increment_messages(user_id)
            return jsonify({'reply': response})
        else:
            return jsonify({'reply': "❌ Не удалось обработать запрос."})

    except Exception as e:
        print(f"❌ Ошибка: {e}", flush=True)
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
        return jsonify({'text': '🎤 Голосовое сообщение получено!'})
    except Exception as e:
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
        <body><div><h1>🚫 ДОСТУП ЗАПРЕЩЁН</h1><p>Только владелец (ID: 1787063701739)</p></div></body></html>
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

    try:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('SELECT user_id, username, premium, messages_today, is_admin, test_used, joined_at, premium_expires FROM users_web ORDER BY user_id DESC')
        users = c.fetchall()
        conn.close()
    except:
        users = []

    rows = ""
    for u in users:
        uid = u[0]
        username = u[1]
        premium = u[2]
        msgs = u[3]
        is_admin_flag = u[4]
        joined = u[6] if len(u) > 6 else '—'
        expires = u[7] if len(u) > 7 else None
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
            <div class="card"><span>💎 Premium</span><div class="num gold">{sum(1 for u in users if u[2] == 1)}</div></div>
            <div class="card"><span>👑 Админов</span><div class="num gold">{sum(1 for u in users if u[4] == 1)}</div></div>
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
    print("=" * 50, flush=True)
    print("🧠 AWESOME AI 2026 - С ФОТО И РИСОВАНИЕМ!", flush=True)
    print("=" * 50, flush=True)
    print(f"👑 Владелец ID: {OWNER_ID}", flush=True)
    print(f"🌐 http://0.0.0.0:{port}", flush=True)
    print("=" * 50, flush=True)
    print("✅ 📸 РАСПОЗНАЁТ ФОТОГРАФИИ!", flush=True)
    print("✅ 🎨 ГЕНЕРИРУЕТ КАРТИНКИ!", flush=True)
    print("✅ 🧠 ПОМНИТ ВЕСЬ ДИАЛОГ НАВСЕГДА!", flush=True)
    print("✅ 💾 ИСТОРИЯ СОХРАНЯЕТСЯ В БД", flush=True)
    print("=" * 50, flush=True)
    app.run(host='0.0.0.0', port=port, debug=True)
