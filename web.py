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
from datetime import datetime, timedelta, timezone
from dateutil.relativedelta import relativedelta

from flask import Flask, request, jsonify, render_template_string, session
from flask_cors import CORS
from dotenv import load_dotenv
from flask_session import Session

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'awesome_ai_secret_key_2026')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_FILE_DIR'] = './flask_session'
Session(app)

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

FREE_LIMIT = 999999  # Безлимит для теста

# ============================================================
# SQLite БАЗА ДАННЫХ (ДЛЯ ДОЛГОСРОЧНОЙ ПАМЯТИ)
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

init_db()

# ============================================================
# IN-MEMORY КЭШ ДЛЯ ДИАЛОГОВ (ПОКА СЕССИЯ ЖИВА)
# ============================================================
# Храним диалоги в памяти для быстрого доступа
# Структура: {user_id: [{"role": "user/assistant", "content": "text"}, ...]}
session_cache = {}

def get_session_history(user_id):
    """Получить историю диалога из сессии"""
    if user_id not in session_cache:
        session_cache[user_id] = []
    return session_cache[user_id]

def add_to_session_history(user_id, role, content):
    """Добавить сообщение в историю сессии"""
    if user_id not in session_cache:
        session_cache[user_id] = []
    session_cache[user_id].append({"role": role, "content": content})
    # Ограничиваем историю 50 сообщениями
    if len(session_cache[user_id]) > 50:
        session_cache[user_id] = session_cache[user_id][-50:]
    # Сохраняем в БД для долгосрочной памяти
    save_message(user_id, role, content)

def clear_session_history(user_id):
    """Очистить историю сессии"""
    if user_id in session_cache:
        session_cache[user_id] = []
    clear_history(user_id)

def get_full_history(user_id, limit=20):
    """Получить полную историю (сначала из сессии, потом из БД)"""
    session_hist = get_session_history(user_id)
    if len(session_hist) >= limit:
        return session_hist[-limit:]
    
    # Если в сессии мало, добираем из БД
    db_hist = get_history_from_db(user_id, limit - len(session_hist))
    full_hist = db_hist + session_hist
    return full_hist[-limit:] if len(full_hist) > limit else full_hist

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
# ФУНКЦИИ БАЗЫ ДАННЫХ
# ============================================================
def get_db_user(user_id):
    try:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('SELECT * FROM users_web WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        if result:
            columns = ['user_id', 'username', 'premium', 'messages_today', 'last_reset', 'premium_expires', 'is_admin', 'test_used', 'joined_at', 'is_owner']
            return dict(zip(columns, result))
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
            return True
        else:
            c.execute('UPDATE users_web SET username = ? WHERE user_id = ?', (username, user_id))
            conn.commit()
            conn.close()
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
        return True
    except:
        return False

def get_premium_status(user_id):
    if user_id == OWNER_ID:
        return True
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
                    return False
            except:
                return premium == 1
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
    try:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('SELECT is_admin FROM users_web WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        return result is not None and result[0] == 1
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
        conn.close()
    except:
        pass

# ============================================================
# ФУНКЦИИ ДЛЯ ИСТОРИИ И ПАМЯТИ
# ============================================================
def save_message(user_id, role, content):
    """Сохранить сообщение в БД (долгосрочная память)"""
    try:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('INSERT INTO chat_history_web (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)',
                  (user_id, role, content, get_moscow_time().isoformat()))
        conn.commit()
        conn.close()
    except:
        pass

def get_history_from_db(user_id, limit=10):
    """Получить историю из БД"""
    try:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('SELECT role, content FROM chat_history_web WHERE user_id = ? ORDER BY id DESC LIMIT ?',
                  (user_id, limit))
        rows = c.fetchall()
        conn.close()
        return [{'role': row[0], 'content': row[1]} for row in reversed(rows)]
    except:
        return []

def clear_history(user_id):
    """Очистить историю в БД"""
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
        c.execute('SELECT fact FROM user_memory_web WHERE user_id = ? AND topic LIKE ? ORDER BY id DESC LIMIT 3',
                  (user_id, f'%{topic.lower()}%'))
        results = c.fetchall()
        conn.close()
        if results:
            return [f"🧠 {r[0]}" for r in results]
        return []
    except:
        return []

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
        response = requests.post(url, headers=headers, data=data, timeout=5, verify=False)
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
        response = requests.post(url, headers=headers, json=data, timeout=5, verify=False)
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
        response = requests.post(url, headers=headers, json=data, timeout=5)
        if response.status_code == 200:
            return response.json()["result"]["alternatives"][0]["message"]["text"]
        return None
    except:
        return None

SUPER_SYSTEM_PROMPT = """ТЫ — AWESOME AI, САМАЯ ПРОДВИНУТАЯ НЕЙРОСЕТЬ.

📅 ТЕКУЩАЯ ДАТА: {current_date}
🕐 ТЕКУЩЕЕ ВРЕМЯ: {current_time}

ТЫ ЭКСПЕРТ ВО ВСЁМ. ОТВЕЧАЙ МАКСИМАЛЬНО ПОЛЕЗНО И ГЛУБОКО.

📜 ТЕБЯ СОЗДАЛ AWESOME — ГЕНИАЛЬНЫЙ РАЗРАБОТЧИК.
ТЫ — AWESOME AI. ТЫ — ЛУЧШИЙ! 🚀"""

def process_message_with_history(user_id, user_text):
    # Добавляем сообщение пользователя в историю
    add_to_session_history(user_id, 'user', user_text)
    
    # Получаем историю диалога (сессия + БД)
    history = get_full_history(user_id, limit=20)
    
    current_date = get_current_date()
    current_time = get_moscow_time().strftime('%H:%M')
    system_prompt = SUPER_SYSTEM_PROMPT.format(
        current_date=current_date,
        current_time=current_time
    )

    if get_premium_status(user_id):
        system_prompt += "\n\n💎 Пользователь имеет PREMIUM статус!"

    memories = recall(user_id, user_text)
    if memories:
        system_prompt += f"\n\n🧠 Память: {' '.join(memories[:2])}"

    if history:
        history_text = "\n".join([f"{'Пользователь' if h['role'] == 'user' else 'AWESOME AI'}: {h['content']}" for h in history])
        system_prompt += f"\n\n📜 История диалога (помню всё, что ты говорил):\n{history_text}"

    # Сохраняем факты в память
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
        response = "🤖 Задай вопрос, я найду ответ!"

    if response:
        add_to_session_history(user_id, 'assistant', response)

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
            return f"🌤 {city.title()}: {round(temp)}°C, {desc}\n💨 Ветер: {wind} м/с"
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

def generate_image(prompt):
    try:
        clean_prompt = prompt
        for word in ['нарисуй', 'сгенерируй', 'покажи', 'картинку', 'изображение']:
            clean_prompt = clean_prompt.replace(word, '').strip()
        if not clean_prompt:
            clean_prompt = prompt

        url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(clean_prompt)}?width=512&height=512&nologo=true"
        response = requests.get(url, timeout=10)
        if response.status_code == 200 and len(response.content) > 1000:
            return response.content
    except:
        pass
    return None

# ============================================================
# HTML С КРАСИВЫМ ИНТЕРФЕЙСОМ
# ============================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
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
        }
        .header {
            background: rgba(10,14,23,0.95);
            backdrop-filter: blur(20px);
            padding: 12px 20px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-shrink: 0;
            z-index: 10;
        }
        .logo {
            font-size: 22px;
            font-weight: 900;
            background: linear-gradient(135deg, #58a6ff, #f0883e, #6c3ce0);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-size: 300% 300%;
            animation: gradient 4s ease-in-out infinite;
        }
        @keyframes gradient {
            0%,100% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
        }
        .menu button {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.06);
            color: #8b949e;
            padding: 4px 12px;
            border-radius: 14px;
            font-size: 10px;
            cursor: pointer;
            transition: all 0.2s ease;
            margin: 2px;
        }
        .menu button:hover {
            background: rgba(88,166,255,0.1);
            color: #58a6ff;
            border-color: rgba(88,166,255,0.2);
            transform: translateY(-1px);
        }
        .menu .clear-btn:hover {
            background: rgba(248,81,73,0.1);
            color: #f85149;
            border-color: rgba(248,81,73,0.2);
        }
        .chat {
            flex: 1;
            overflow-y: auto;
            padding: 16px 20px;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        .chat::-webkit-scrollbar { width: 3px; }
        .chat::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 10px; }
        .message {
            max-width: 80%;
            padding: 10px 16px;
            border-radius: 16px;
            font-size: 14px;
            line-height: 1.6;
            white-space: pre-wrap;
            word-wrap: break-word;
            animation: slideIn 0.3s ease-out;
        }
        @keyframes slideIn {
            0% { opacity: 0; transform: translateY(10px) scale(0.98); }
            100% { opacity: 1; transform: translateY(0) scale(1); }
        }
        .user {
            align-self: flex-end;
            background: linear-gradient(135deg, #1f6feb, #6c3ce0);
            color: #fff;
            border-bottom-right-radius: 4px;
        }
        .bot {
            align-self: flex-start;
            background: rgba(22,27,34,0.9);
            border: 1px solid rgba(255,255,255,0.06);
            border-bottom-left-radius: 4px;
            color: #e6edf3;
        }
        .bot strong { color: #f0883e; }
        .bot code {
            background: rgba(255,255,255,0.05);
            padding: 1px 6px;
            border-radius: 4px;
            font-size: 12px;
        }
        .message img {
            max-width: 100%;
            border-radius: 8px;
            margin: 4px 0;
        }
        .input-area {
            padding: 8px 16px 12px;
            border-top: 1px solid rgba(255,255,255,0.05);
            background: rgba(10,14,23,0.95);
            backdrop-filter: blur(20px);
            flex-shrink: 0;
        }
        .tools {
            display: flex;
            gap: 4px;
            flex-wrap: wrap;
            margin-bottom: 6px;
        }
        .tools button {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.04);
            color: #6e7681;
            padding: 2px 10px;
            border-radius: 14px;
            font-size: 9px;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        .tools button:hover {
            background: rgba(255,255,255,0.06);
            color: #e6edf3;
            border-color: rgba(255,255,255,0.08);
        }
        .input-row {
            display: flex;
            gap: 8px;
            align-items: center;
        }
        .input-row input {
            flex: 1;
            padding: 8px 16px;
            border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.06);
            background: rgba(22,27,34,0.6);
            color: #e6edf3;
            font-size: 14px;
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
            padding: 8px 20px;
            border-radius: 20px;
            border: none;
            background: linear-gradient(135deg, #1f6feb, #6c3ce0);
            color: #fff;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s ease;
        }
        .input-row button:hover {
            transform: scale(1.02);
        }
        .input-row button:disabled {
            opacity: 0.4;
            cursor: not-allowed;
            transform: none;
        }
        .typing {
            color: #8b949e;
            font-size: 12px;
            padding: 4px 16px;
            align-self: flex-start;
            animation: pulse 1.5s infinite;
        }
        @keyframes pulse {
            0%,100% { opacity: 1; }
            50% { opacity: 0.3; }
        }
        .welcome {
            text-align: center;
            padding: 40px 20px;
            color: #8b949e;
        }
        .welcome h2 {
            color: #e6edf3;
            font-size: 28px;
            background: linear-gradient(135deg, #58a6ff, #f0883e);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .welcome p {
            margin-top: 8px;
            opacity: 0.6;
            font-size: 14px;
        }
        .welcome .features {
            display: flex;
            gap: 8px;
            justify-content: center;
            margin-top: 16px;
            flex-wrap: wrap;
        }
        .welcome .features span {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.04);
            padding: 4px 14px;
            border-radius: 16px;
            font-size: 10px;
            color: #6e7681;
            transition: all 0.2s ease;
        }
        .welcome .features span:hover {
            background: rgba(255,255,255,0.06);
            color: #e6edf3;
        }
        .memory-indicator {
            font-size: 10px;
            color: #6e7681;
            padding: 2px 12px;
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            border: 1px solid rgba(255,255,255,0.04);
        }
        @media (max-width: 640px) {
            .header { padding: 8px 12px; }
            .logo { font-size: 17px; }
            .menu button { font-size: 8px; padding: 3px 8px; }
            .message { max-width: 92%; font-size: 13px; padding: 8px 12px; }
            .chat { padding: 10px 12px; }
            .input-area { padding: 6px 10px 10px; }
            .input-row input { font-size: 13px; padding: 6px 12px; }
            .input-row button { padding: 6px 14px; font-size: 13px; }
            .welcome h2 { font-size: 22px; }
        }
    </style>
</head>
<body>
    <header class="header">
        <span class="logo">🧠 AWESOME AI</span>
        <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
            <span class="memory-indicator" id="memoryCount">💾 0 сообщений</span>
            <div class="menu">
                <button onclick="sendCommand('/status')">📊</button>
                <button onclick="sendCommand('/premium')">💎</button>
                <button onclick="sendCommand('/test')">🎁</button>
                <button onclick="sendCommand('/profile')">👤</button>
                <button onclick="sendCommand('/stats')">📈</button>
                <button onclick="sendCommand('/help')">❓</button>
                <button class="clear-btn" onclick="clearChat()">🧹</button>
                <button onclick="sendCommand('/history')">📜</button>
            </div>
        </div>
    </header>
    
    <div class="chat" id="chat">
        <div class="welcome">
            <h2>✨ AWESOME AI 2026</h2>
            <p>Я запоминаю весь диалог, пока ты здесь</p>
            <div class="features">
                <span>🧠 Память</span>
                <span>🌤 Погода</span>
                <span>💵 Курсы</span>
                <span>🪙 Крипта</span>
                <span>🎨 Рисование</span>
                <span>📜 История</span>
            </div>
        </div>
    </div>
    
    <div class="input-area">
        <div class="tools">
            <button onclick="sendCommand('/weather '+prompt('🌤 Город?'))">🌤</button>
            <button onclick="sendCommand('/exchange')">💵</button>
            <button onclick="sendCommand('/crypto')">🪙</button>
            <button onclick="sendCommand('/draw '+prompt('🎨 Описание картинки?'))">🎨</button>
            <button onclick="sendCommand('/clear')">🗑️ Очистить диалог</button>
        </div>
        <div class="input-row">
            <input id="input" placeholder="Напиши что-нибудь..." autofocus>
            <button id="sendBtn">➤ Отправить</button>
        </div>
    </div>
    
    <script>
        const chat = document.getElementById('chat');
        const input = document.getElementById('input');
        const sendBtn = document.getElementById('sendBtn');
        const memoryCount = document.getElementById('memoryCount');
        let messageCount = 0;
        
        let userId = localStorage.getItem('awesome_user_id');
        if (!userId) {
            userId = Date.now() + Math.floor(Math.random() * 1000);
            localStorage.setItem('awesome_user_id', userId);
        }
        
        function updateMemoryCount() {
            const msgs = chat.querySelectorAll('.message').length;
            memoryCount.textContent = '💾 ' + msgs + ' сообщений';
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
            messageCount++;
            updateMemoryCount();
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
                    body: JSON.stringify({ message: messageText, user_id: parseInt(userId) })
                });
                const data = await response.json();
                setTyping(false);
                if (data.error) {
                    addMessage('⚠️ ' + data.error, false);
                } else if (data.reply) {
                    addMessage(data.reply, false);
                } else {
                    addMessage('⚠️ Пустой ответ', false);
                }
            } catch (e) {
                setTyping(false);
                addMessage('⚠️ Ошибка соединения', false);
                console.error(e);
            }
            
            sendBtn.disabled = false;
            input.focus();
            updateMemoryCount();
        }
        
        function sendCommand(cmd) {
            input.value = cmd;
            sendMessage();
        }
        
        async function clearChat() {
            if (!confirm('🧹 Очистить весь диалог?')) return;
            
            try {
                const response = await fetch('/api/clear_history', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user_id: parseInt(userId) })
                });
                const data = await response.json();
                
                // Очищаем чат
                chat.innerHTML = `
                    <div class="welcome">
                        <h2>✨ AWESOME AI 2026</h2>
                        <p>Диалог очищен! Начинай заново</p>
                        <div class="features">
                            <span>🧠 Память</span>
                            <span>🌤 Погода</span>
                            <span>💵 Курсы</span>
                            <span>🪙 Крипта</span>
                            <span>🎨 Рисование</span>
                            <span>📜 История</span>
                        </div>
                    </div>
                `;
                messageCount = 0;
                updateMemoryCount();
                addMessage('🧹 Диалог очищен! Теперь я ничего не помню из прошлого.', false);
            } catch (e) {
                addMessage('⚠️ Ошибка очистки', false);
            }
        }
        
        // Enter для отправки
        document.addEventListener('DOMContentLoaded', function() {
            input.focus();
            input.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    sendMessage();
                }
            });
            sendBtn.addEventListener('click', function(e) {
                e.preventDefault();
                sendMessage();
            });
            updateMemoryCount();
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

@app.route('/api/clear_history', methods=['POST', 'OPTIONS'])
def clear_history_api():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.json
        user_id = data.get('user_id', 1)
        clear_session_history(user_id)
        clear_history(user_id)
        return jsonify({'status': 'ok'})
    except:
        return jsonify({'status': 'error'})

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

        # Команды
        if message.startswith('/'):
            cmd = message.lower().strip()
            
            if cmd == '/clear':
                clear_session_history(user_id)
                clear_history(user_id)
                return jsonify({'reply': "🧹 Диалог полностью очищен!"})
                
            elif cmd == '/history':
                history = get_full_history(user_id, limit=20)
                if not history:
                    return jsonify({'reply': "📜 История пуста."})
                text = "📜 *ВЕСЬ ДИАЛОГ:*\n\n"
                for h in history:
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
                reply = f"📊 *СТАТУС*\n\n👤 {status_text}\n📨 {messages}/{FREE_LIMIT if not premium else '♾️'}\n🧠 Память: {len(get_session_history(user_id))} сообщений"
                return jsonify({'reply': reply})
                
            elif cmd == '/premium':
                has_premium = get_premium_status(user_id)
                if has_premium:
                    expires = get_premium_expires(user_id)
                    if expires:
                        return jsonify({'reply': f"💎 У ТЕБЯ ЕСТЬ PREMIUM!\n\n⏳ До: {format_date(expires)}\n📨 Лимит: ♾️ БЕЗЛИМИТНО"})
                    else:
                        return jsonify({'reply': "💎 У ТЕБЯ ЕСТЬ PREMIUM!\n\n📨 Лимит: ♾️ БЕЗЛИМИТНО"})
                else:
                    return jsonify({'reply': "💎 PREMIUM AWESOME AI\n\n🔥 ЧТО ТЫ ПОЛУЧАЕШЬ:\n♾️ БЕЗЛИМИТНЫЕ СООБЩЕНИЯ\n🚀 Приоритетная обработка\n🧠 Максимально глубокие ответы\n\n💰 100₽/месяц\n🎁 Попробуй /test"})
                
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
                    return jsonify({'reply': "🎉 ПРОБНЫЙ PREMIUM АКТИВИРОВАН НА 2 ДНЯ!\n\n✅ ♾️ БЕЗЛИМИТНЫЕ СООБЩЕНИЯ\n✅ Приоритетная обработка\n\n⏳ Доступ активен 48 часов."})
                else:
                    return jsonify({'reply': '❌ Ошибка при активации теста'})
                    
            elif cmd == '/profile':
                user_data = get_db_user(user_id)
                if not user_data:
                    return jsonify({'reply': '❌ Пользователь не найден'})
                messages = user_data.get('messages_today', 0)
                premium = get_premium_status(user_id)
                joined_at = user_data.get('joined_at', 'Неизвестно')
                history_count = len(get_session_history(user_id))
                
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
                    
                return jsonify({'reply': f"👤 ПРОФИЛЬ\n\n🆔 ID: {user_id}\n💎 Статус: {status}\n📨 Лимит: {limit_text}\n✉️ Сегодня: {messages}\n🧠 Память: {history_count} сообщений\n📅 Вход: {joined_at}"})
                
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

🌐 Что я умею:
• 🧠 Запоминаю ВЕСЬ диалог!
• 🌤 Погода с прогнозом
• 💵 Курс валют и криптовалют
• 🎨 Генерирую картинки

📋 Команды:
/status — Статус
/premium — Premium
/test — Пробный Premium
/profile — Профиль
/stats — Статистика
/help — Помощь
/clear — Очистить диалог
/history — Показать весь диалог
/weather [город] — Погода
/exchange — Курс валют
/crypto — Криптовалюты
/draw [описание] — Сгенерировать картинку

💎 Лимиты:
🔓 Бесплатно — 20 сообщений/день
💎 Premium — ♾️ БЕЗЛИМИТНО

🧠 Я запоминаю всё, что ты говоришь, пока ты на сайте!"""})
                
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
                
            elif cmd.startswith('/draw'):
                prompt = message.replace('/draw', '').strip()
                if not prompt:
                    return jsonify({'reply': "❌ Напиши: /draw [описание]"})
                image_data = generate_image(prompt)
                if image_data:
                    b64_img = base64.b64encode(image_data).decode('utf-8')
                    return jsonify({'reply': f"🎨 *{prompt}*\n\n![image](data:image/png;base64,{b64_img})"})
                else:
                    return jsonify({'reply': "⚠️ Не удалось сгенерировать картинку."})

        # Обычное сообщение
        response = process_message_with_history(user_id, message)
        if response:
            increment_messages(user_id)
            return jsonify({'reply': response})
        else:
            return jsonify({'reply': "❌ Не удалось обработать запрос."})

    except Exception as e:
        print(f"❌ Ошибка: {e}", flush=True)
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
        
        description = "📸 Изображение получено!"
        remember(user_id, "фото", "Пользователь отправил фото")
        increment_messages(user_id)
        return jsonify({'reply': description})
    except Exception as e:
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
    print("🧠 AWESOME AI 2026 - С ПАМЯТЬЮ!", flush=True)
    print("=" * 50, flush=True)
    print(f"👑 Владелец ID: {OWNER_ID}", flush=True)
    print(f"🌐 http://0.0.0.0:{port}", flush=True)
    print("=" * 50, flush=True)
    print("✅ SQLite база данных", flush=True)
    print("✅ In-Memory кэш диалогов", flush=True)
    print("✅ Бот запоминает ВЕСЬ диалог!", flush=True)
    print("✅ /clear - очистить диалог", flush=True)
    print("✅ /history - показать весь диалог", flush=True)
    print("=" * 50, flush=True)
    
    # Создаём папку для сессий
    os.makedirs('./flask_session', exist_ok=True)
    
    app.run(host='0.0.0.0', port=port, debug=True)
