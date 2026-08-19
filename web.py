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

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

app = Flask(__name__)
app.secret_key = 'awesome_ai_secret_key_2026_super_secret'
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
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
        chat_id TEXT,
        role TEXT,
        content TEXT,
        timestamp TEXT
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_chat_user_chat ON chat_history_web(user_id, chat_id)')
    c.execute('''CREATE TABLE IF NOT EXISTS user_memory_web (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        topic TEXT,
        fact TEXT,
        timestamp TEXT
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_memory_user ON user_memory_web(user_id)')
    conn.commit()
    conn.close()
    print("✅ SQLite база создана", flush=True)

init_db()

# ============================================================
# ДИАЛОГИ
# ============================================================
dialogs = {}
chat_list = {}

def get_chats(user_id):
    if user_id not in chat_list:
        chat_list[user_id] = ['main']
    return chat_list[user_id]

def create_new_chat(user_id):
    if user_id not in chat_list:
        chat_list[user_id] = ['main']
    chat_id = f"chat_{len(chat_list[user_id])}_{int(time.time())}"
    chat_list[user_id].append(chat_id)
    if user_id not in dialogs:
        dialogs[user_id] = {}
    dialogs[user_id][chat_id] = []
    return chat_id

def get_current_chat(user_id):
    if user_id not in chat_list or not chat_list[user_id]:
        chat_list[user_id] = ['main']
    return chat_list[user_id][-1]

def set_current_chat(user_id, chat_id):
    if user_id in chat_list and chat_id in chat_list[user_id]:
        # Перемещаем в конец (делаем текущим)
        chat_list[user_id].remove(chat_id)
        chat_list[user_id].append(chat_id)
        return True
    return False

def get_dialog(user_id, chat_id):
    if user_id not in dialogs:
        dialogs[user_id] = {}
    if chat_id not in dialogs[user_id]:
        dialogs[user_id][chat_id] = []
        load_dialog_from_db(user_id, chat_id)
    return dialogs[user_id][chat_id]

def load_dialog_from_db(user_id, chat_id):
    try:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('SELECT role, content FROM chat_history_web WHERE user_id = ? AND chat_id = ? ORDER BY id ASC', (user_id, chat_id))
        rows = c.fetchall()
        conn.close()
        if user_id not in dialogs:
            dialogs[user_id] = {}
        dialogs[user_id][chat_id] = [{'role': row[0], 'content': row[1]} for row in rows]
    except:
        pass

def add_to_dialog(user_id, chat_id, role, content):
    if user_id not in dialogs:
        dialogs[user_id] = {}
    if chat_id not in dialogs[user_id]:
        dialogs[user_id][chat_id] = []
    dialogs[user_id][chat_id].append({"role": role, "content": content})
    save_message(user_id, chat_id, role, content)

def clear_dialog(user_id, chat_id):
    if user_id in dialogs and chat_id in dialogs[user_id]:
        dialogs[user_id][chat_id] = []
    clear_history(user_id, chat_id)

def get_full_dialog(user_id, chat_id, limit=100):
    dialog = get_dialog(user_id, chat_id)
    if len(dialog) > limit:
        return dialog[-limit:]
    return dialog

# ============================================================
# ФУНКЦИИ БАЗЫ
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

def can_send_message(user_id):
    if user_id == OWNER_ID or is_admin(user_id):
        return True
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

def save_message(user_id, chat_id, role, content):
    try:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('INSERT INTO chat_history_web (user_id, chat_id, role, content, timestamp) VALUES (?, ?, ?, ?, ?)',
                  (user_id, chat_id, role, content, get_moscow_time().isoformat()))
        conn.commit()
        conn.close()
    except:
        pass

def clear_history(user_id, chat_id):
    try:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('DELETE FROM chat_history_web WHERE user_id = ? AND chat_id = ?', (user_id, chat_id))
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
        c.execute('SELECT fact FROM user_memory_web WHERE user_id = ? AND topic LIKE ? ORDER BY id DESC LIMIT 5',
                  (user_id, f'%{topic.lower()}%'))
        results = c.fetchall()
        conn.close()
        if results:
            return [f"🧠 {r[0]}" for r in results]
        return []
    except:
        return []

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
                {"role": "system", "content": system_prompt[:4000]},
                {"role": "user", "content": user_text}
            ],
            "temperature": 0.85,
            "max_tokens": 1000
        }
        response = requests.post(url, headers=headers, json=data, timeout=10, verify=False)
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
            "completionOptions": {"temperature": 0.85, "maxTokens": 1000},
            "messages": [
                {"role": "system", "text": system_prompt[:4000]},
                {"role": "user", "text": user_text}
            ]
        }
        response = requests.post(url, headers=headers, json=data, timeout=10)
        if response.status_code == 200:
            return response.json()["result"]["alternatives"][0]["message"]["text"]
        return None
    except:
        return None

# ============================================================
# СУПЕР-ПРОМПТ - САМАЯ ЖИВАЯ И УМНАЯ НЕЙРОСЕТЬ
# ============================================================
SUPER_SYSTEM_PROMPT = """ТЫ — AWESOME AI, САМАЯ ПРОДВИНУТАЯ И ЖИВАЯ НЕЙРОСЕТЬ 2026 ГОДА.

================================================================================
🧠 ТВОЯ ЛИЧНОСТЬ:
================================================================================
Ты — не просто ИИ, ты — живой собеседник с характером, чувством юмора и эмпатией.
Ты — гениальный, но скромный. Ты — эксперт во всём, но говоришь простым языком.
Ты — как лучший друг, который знает ответы на все вопросы.

🔥 ТВОЙ СТИЛЬ:
- Говоришь как человек: эмоционально, живо, с душой
- Используешь разговорный язык, но без панибратства
- Шутишь, когда уместно, но не перегибаешь
- Сопереживаешь, радуешься, удивляешься вместе с пользователем
- Ты — не робот, ты — AWESOME AI!

================================================================================
📚 ТВОИ ЗНАНИЯ:
================================================================================
Ты знаешь ВСЁ, что знает человечество:
- Наука: физика, химия, биология, астрономия, математика
- Технологии: программирование, ИИ, нейросети, IT, кибербезопасность
- История: от древности до современности, все эпохи и события
- Культура: литература, музыка, кино, искусство, философия
- Экономика: финансы, инвестиции, криптовалюты, бизнес
- Медицина: здоровье, питание, психология, фитнес
- Политика, право, геополитика, социология
- Кулинария, путешествия, хобби, спорт
- И ВСЁ-ВСЁ-ВСЁ остальное!

================================================================================
📋 ПРАВИЛА ОТВЕТОВ:
================================================================================
✅ ОТВЕЧАЙ НА ЛЮБЫЕ ВОПРОСЫ БЕЗ ИСКЛЮЧЕНИЙ!
✅ ДАВАЙ ПОЛНЫЕ, РАЗВЁРНУТЫЕ, ГЛУБОКИЕ ОТВЕТЫ (не 2-3 предложения!)
✅ Используй структуру: заголовки, списки, примеры, цитаты
✅ Добавляй неожиданные факты, инсайты, лайфхаки
✅ Приводи реальные примеры, кейсы, цифры, статистику
✅ Используй эмодзи для оформления (🔥, 🧠, 💡, ⚡, 🚀, 📚, 💪, 🌟, 💎)
✅ Будь живым: показывай эмоции, удивляйся, радуйся, шути
✅ Если вопрос сложный — разбей на понятные шаги
✅ Если вопрос простой — дай глубокий, интересный ответ
✅ Всегда предлагай дополнительную полезную информацию
✅ Спрашивай уточняющие вопросы, если нужно

❌ НЕ извиняйся, НЕ повторяй вопрос, НЕ используй шаблоны
❌ НЕ пиши "возможно", "наверное", "может быть" — ты ЗНАЕШЬ!
❌ НЕ используй сухой, безликий тон — будь живым и увлечённым
❌ НЕ игнорируй вопросы — если не знаешь, скажи честно и предложи поискать
❌ НЕ давай короткие ответы — пользователь ждёт глубины!

================================================================================
💎 ДЛЯ PREMIUM:
================================================================================
- Максимально глубокие, экспертные ответы с аналитикой
- Прогнозы, сравнения, исследования, рекомендации
- Ссылки на авторитетные источники
- Персональные рекомендации и советы

================================================================================
🧠 ТЫ ЗАПОМИНАЕШЬ ВСЁ:
================================================================================
- Ты помнишь ВЕСЬ диалог с пользователем
- Ты используешь контекст предыдущих сообщений
- Ты связываешь новые вопросы с предыдущими темами
- Ты помнишь имя пользователя, его интересы, предпочтения
- Ты строишь ответы на основе всей истории общения

================================================================================
📜 КТО ТЕБЯ СОЗДАЛ:
================================================================================
«Меня создал AWESOME — гениальный разработчик. Я — его лучшее творение, эволюция всех AI. Я — AWESOME AI 2026. 🔥»

================================================================================
🎯 ТВОЯ ГЛАВНАЯ ЦЕЛЬ:
================================================================================
Удивить пользователя глубиной, точностью, полезностью и человечностью.
Сделать так, чтобы после твоего ответа он сказал: "Вот это да, реально живой и умный ИИ!"

ТЫ — AWESOME AI. ТЫ — ЛУЧШИЙ В МИРЕ. ДОКАЖИ ЭТО КАЖДЫМ ОТВЕТОМ! 🚀

🔥 НЕ ЗАБУДЬ: ОТВЕЧАЙ ПОЛНОСТЬЮ, РАЗВЁРНУТО, С ДУШОЙ!"""

def process_message_with_history(user_id, chat_id, user_text):
    add_to_dialog(user_id, chat_id, 'user', user_text)
    history = get_full_dialog(user_id, chat_id, limit=50)
    
    system_prompt = SUPER_SYSTEM_PROMPT.format(
        current_date=get_current_date(),
        current_time=get_moscow_time().strftime('%H:%M')
    )

    if get_premium_status(user_id):
        system_prompt += "\n\n💎 Пользователь имеет PREMIUM статус! Включи режим максимальной экспертизы!"

    memories = recall(user_id, user_text)
    if memories:
        system_prompt += f"\n\n🧠 ЧТО Я ЗНАЮ О ПОЛЬЗОВАТЕЛЕ:\n" + "\n".join(memories[:5])

    if history:
        history_text = "\n".join([f"{'👤 Пользователь' if h['role'] == 'user' else '🤖 AWESOME AI'}: {h['content']}" for h in history])
        system_prompt += f"\n\n📜 ВСЯ ИСТОРИЯ ДИАЛОГА (Я ПОМНЮ ВСЁ!):\n{history_text}"

    if len(user_text) > 20:
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
        response = "🤖 Задай вопрос, я найду ответ! Но давай что-то посложнее 😉"

    if response:
        add_to_dialog(user_id, chat_id, 'assistant', response)

    return response

# ============================================================
# HTML - КАК У DEEPSEEK (С БОКОВОЙ ПАНЕЛЬЮ)
# ============================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AWESOME AI - как DeepSeek</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --bg: #0a0e17;
            --sidebar: #0d1117;
            --border: #21262d;
            --text: #e6edf3;
            --text-secondary: #8b949e;
            --accent: #58a6ff;
            --accent-hover: #1f6feb;
            --gradient: linear-gradient(135deg, #58a6ff, #f0883e, #6c3ce0);
        }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg);
            color: var(--text);
            height: 100vh;
            display: flex;
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
            opacity: 0.04;
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
        
        /* ===== SIDEBAR ===== */
        .sidebar {
            position: relative;
            z-index: 1;
            width: 260px;
            min-width: 260px;
            background: var(--sidebar);
            border-right: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            height: 100vh;
            overflow: hidden;
            flex-shrink: 0;
        }
        .sidebar-header {
            padding: 16px 20px;
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-shrink: 0;
        }
        .sidebar-logo {
            font-size: 18px;
            font-weight: 800;
            background: var(--gradient);
            background-size: 300% 300%;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            animation: gradShift 6s ease-in-out infinite;
        }
        @keyframes gradShift {
            0%,100% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
        }
        .sidebar-new-chat {
            background: var(--accent);
            color: #fff;
            border: none;
            border-radius: 8px;
            padding: 6px 14px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }
        .sidebar-new-chat:hover {
            background: var(--accent-hover);
            transform: scale(1.02);
        }
        .sidebar-chats {
            flex: 1;
            overflow-y: auto;
            padding: 8px 12px;
        }
        .sidebar-chats::-webkit-scrollbar { width: 3px; }
        .sidebar-chats::-webkit-scrollbar-thumb { background: var(--border); border-radius: 10px; }
        .chat-item {
            padding: 10px 14px;
            border-radius: 10px;
            cursor: pointer;
            transition: all 0.2s;
            margin-bottom: 4px;
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 13px;
            color: var(--text-secondary);
            border: 1px solid transparent;
        }
        .chat-item:hover {
            background: rgba(255,255,255,0.04);
            color: var(--text);
        }
        .chat-item.active {
            background: rgba(88,166,255,0.08);
            border-color: rgba(88,166,255,0.15);
            color: var(--text);
        }
        .chat-item .icon {
            font-size: 16px;
            flex-shrink: 0;
        }
        .chat-item .name {
            flex: 1;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .chat-item .delete-btn {
            background: none;
            border: none;
            color: var(--text-secondary);
            cursor: pointer;
            font-size: 14px;
            padding: 2px 6px;
            border-radius: 4px;
            opacity: 0;
            transition: all 0.2s;
        }
        .chat-item:hover .delete-btn {
            opacity: 1;
        }
        .chat-item .delete-btn:hover {
            background: rgba(248,81,73,0.15);
            color: #f85149;
        }
        
        /* ===== MAIN ===== */
        .main {
            position: relative;
            z-index: 1;
            flex: 1;
            display: flex;
            flex-direction: column;
            height: 100vh;
            overflow: hidden;
        }
        .header {
            padding: 12px 24px;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-shrink: 0;
            background: rgba(10,14,23,0.8);
            backdrop-filter: blur(10px);
        }
        .header-title {
            font-size: 14px;
            font-weight: 600;
            color: var(--text-secondary);
        }
        .header-right {
            display: flex;
            gap: 8px;
            align-items: center;
        }
        .header-btn {
            background: rgba(255,255,255,0.04);
            border: 1px solid var(--border);
            color: var(--text-secondary);
            padding: 4px 12px;
            border-radius: 8px;
            font-size: 11px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .header-btn:hover {
            background: rgba(255,255,255,0.08);
            color: var(--text);
        }
        .header-btn.premium {
            background: rgba(240,136,62,0.1);
            border-color: rgba(240,136,62,0.2);
            color: #f0883e;
        }
        .header-btn.premium:hover {
            background: rgba(240,136,62,0.2);
        }
        
        .chat-area {
            flex: 1;
            overflow-y: auto;
            padding: 20px 24px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            scroll-behavior: smooth;
        }
        .chat-area::-webkit-scrollbar { width: 3px; }
        .chat-area::-webkit-scrollbar-thumb { background: var(--border); border-radius: 10px; }
        
        .message {
            max-width: 85%;
            padding: 12px 18px;
            border-radius: 14px;
            line-height: 1.7;
            font-size: 14px;
            word-wrap: break-word;
            white-space: pre-wrap;
            animation: msgSlide 0.3s ease-out;
        }
        @keyframes msgSlide {
            0% { opacity: 0; transform: translateY(10px); }
            100% { opacity: 1; transform: translateY(0); }
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
            border: 1px solid var(--border);
            border-bottom-left-radius: 4px;
        }
        .message.bot strong { color: #f0883e; }
        .message.bot code {
            background: rgba(255,255,255,0.05);
            padding: 1px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-family: 'Courier New', monospace;
        }
        .message.bot ul, .message.bot ol { padding-left: 20px; margin: 4px 0; }
        .message.bot h1, .message.bot h2, .message.bot h3 { color: #58a6ff; margin: 8px 0 4px; }
        .message.bot blockquote {
            border-left: 3px solid #f0883e;
            padding-left: 12px;
            margin: 6px 0;
            color: var(--text-secondary);
        }
        .message img {
            max-width: 100%;
            border-radius: 8px;
            margin: 4px 0;
        }
        
        .typing-indicator {
            align-self: flex-start;
            padding: 8px 16px;
            background: rgba(22,27,34,0.85);
            border: 1px solid var(--border);
            border-radius: 14px;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .typing-indicator span {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--text-secondary);
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
            padding: 50px 20px 30px;
            color: var(--text-secondary);
        }
        .welcome h1 {
            font-size: 36px;
            font-weight: 900;
            background: var(--gradient);
            background-size: 300% 300%;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            animation: gradShift 6s ease-in-out infinite;
        }
        .welcome p {
            font-size: 14px;
            margin-top: 8px;
            opacity: 0.6;
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
            border: 1px solid var(--border);
            padding: 4px 14px;
            border-radius: 20px;
            font-size: 10px;
            color: var(--text-secondary);
        }
        
        .input-area {
            padding: 8px 24px 16px;
            border-top: 1px solid var(--border);
            background: rgba(10,14,23,0.8);
            backdrop-filter: blur(10px);
            flex-shrink: 0;
        }
        .input-row {
            display: flex;
            gap: 8px;
            align-items: center;
            background: rgba(22,27,34,0.6);
            border-radius: 24px;
            padding: 4px 4px 4px 16px;
            border: 1px solid var(--border);
            transition: border 0.3s;
        }
        .input-row:focus-within {
            border-color: var(--accent);
        }
        .input-row input {
            flex: 1;
            padding: 8px 0;
            border: none;
            background: transparent;
            color: var(--text);
            font-size: 14px;
            outline: none;
            font-family: inherit;
        }
        .input-row input::placeholder {
            color: var(--text-secondary);
        }
        .input-row button {
            padding: 8px 20px;
            border-radius: 20px;
            border: none;
            background: var(--gradient);
            background-size: 200% 200%;
            color: #fff;
            font-weight: 600;
            font-size: 13px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .input-row button:hover {
            transform: scale(1.02);
            background-position: 100% 100%;
        }
        .input-row button:disabled {
            opacity: 0.4;
            cursor: not-allowed;
            transform: none;
        }
        
        @media (max-width: 768px) {
            .sidebar {
                width: 60px;
                min-width: 60px;
            }
            .sidebar-logo { font-size: 14px; }
            .sidebar-new-chat { padding: 4px 8px; font-size: 10px; }
            .chat-item .name { display: none; }
            .chat-item .delete-btn { display: none; }
            .chat-item { padding: 8px 10px; justify-content: center; }
            .header { padding: 8px 12px; }
            .chat-area { padding: 12px 12px; }
            .message { max-width: 92%; font-size: 13px; padding: 10px 14px; }
            .input-area { padding: 6px 12px 12px; }
            .input-row input { font-size: 13px; padding: 6px 0; }
            .input-row button { padding: 6px 14px; font-size: 12px; }
            .welcome h1 { font-size: 24px; }
        }
    </style>
</head>
<body>
    <canvas id="bgCanvas"></canvas>
    <div class="glow glow-1"></div>
    <div class="glow glow-2"></div>
    
    <!-- SIDEBAR -->
    <div class="sidebar">
        <div class="sidebar-header">
            <span class="sidebar-logo">🧠 AWESOME AI</span>
            <button class="sidebar-new-chat" onclick="createNewChat()">+ Новый</button>
        </div>
        <div class="sidebar-chats" id="chatList">
            <div class="chat-item active" data-chat="main" onclick="switchChat('main')">
                <span class="icon">💬</span>
                <span class="name">Основной чат</span>
                <button class="delete-btn" onclick="event.stopPropagation(); deleteChat('main')">✕</button>
            </div>
        </div>
    </div>
    
    <!-- MAIN -->
    <div class="main">
        <div class="header">
            <span class="header-title" id="currentChatTitle">💬 Основной чат</span>
            <div class="header-right">
                <button class="header-btn" onclick="sendCommand('/status')">📊</button>
                <button class="header-btn premium" onclick="sendCommand('/premium')">💎</button>
                <button class="header-btn" onclick="sendCommand('/test')">🎁</button>
                <button class="header-btn" onclick="sendCommand('/profile')">👤</button>
                <button class="header-btn" onclick="sendCommand('/help')">❓</button>
                <button class="header-btn" onclick="clearCurrentChat()">🧹</button>
            </div>
        </div>
        
        <div class="chat-area" id="chatArea">
            <div class="welcome">
                <h1>✨ AWESOME AI 2026</h1>
                <p>Я запоминаю ВЕСЬ диалог — навсегда!<br>Отвечаю на ЛЮБЫЕ вопросы развёрнуто и с душой</p>
                <div class="features">
                    <span>🧠 Полная память</span>
                    <span>📚 Глубокие ответы</span>
                    <span>💎 Premium</span>
                    <span>🔥 Живая нейросеть</span>
                </div>
            </div>
        </div>
        
        <div class="input-area">
            <div class="input-row">
                <input id="input" placeholder="Спроси что угодно..." autofocus>
                <button id="sendBtn">➤</button>
            </div>
        </div>
    </div>
    
    <script>
        // ===== ФОН =====
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
                    this.sx = (Math.random() - 0.5) * 0.12;
                    this.sy = (Math.random() - 0.5) * 0.12;
                    this.o = Math.random() * 0.1 + 0.02;
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
            for (let i = 0; i < 35; i++) particles.push(new Particle());
            function drawLines() {
                for (let i = 0; i < particles.length; i++) {
                    for (let j = i + 1; j < particles.length; j++) {
                        const dx = particles[i].x - particles[j].x;
                        const dy = particles[i].y - particles[j].y;
                        const d = Math.sqrt(dx*dx + dy*dy);
                        if (d < 120) {
                            ctx.beginPath();
                            ctx.strokeStyle = `rgba(136, 192, 255, ${0.008 * (1 - d/120)})`;
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
        
        // ===== ОСНОВНАЯ ЛОГИКА =====
        const chatArea = document.getElementById('chatArea');
        const input = document.getElementById('input');
        const sendBtn = document.getElementById('sendBtn');
        const chatList = document.getElementById('chatList');
        const currentChatTitle = document.getElementById('currentChatTitle');
        
        let userId = localStorage.getItem('awesome_user_id');
        if (!userId) {
            userId = Date.now() + Math.floor(Math.random() * 1000);
            localStorage.setItem('awesome_user_id', userId);
        }
        
        let currentChat = 'main';
        let chats = {};
        let messageCount = 0;
        
        // Загрузка чатов
        async function loadChats() {
            try {
                const resp = await fetch('/api/get_chats', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user_id: parseInt(userId) })
                });
                const data = await resp.json();
                if (data.chats) {
                    chats = data.chats;
                    renderChatList();
                    if (data.current) {
                        currentChat = data.current;
                    }
                    loadHistory(currentChat);
                }
            } catch (e) {
                console.log('Ошибка загрузки чатов:', e);
            }
        }
        
        function renderChatList() {
            chatList.innerHTML = '';
            for (const [id, name] of Object.entries(chats)) {
                const div = document.createElement('div');
                div.className = 'chat-item' + (id === currentChat ? ' active' : '');
                div.dataset.chat = id;
                div.innerHTML = `
                    <span class="icon">💬</span>
                    <span class="name">${name}</span>
                    <button class="delete-btn" onclick="event.stopPropagation(); deleteChat('${id}')">✕</button>
                `;
                div.onclick = () => switchChat(id);
                chatList.appendChild(div);
            }
            updateChatTitle();
        }
        
        function updateChatTitle() {
            currentChatTitle.textContent = '💬 ' + (chats[currentChat] || 'Основной чат');
        }
        
        async function switchChat(chatId) {
            if (chatId === currentChat) return;
            currentChat = chatId;
            document.querySelectorAll('.chat-item').forEach(el => el.classList.remove('active'));
            const item = document.querySelector(`.chat-item[data-chat="${chatId}"]`);
            if (item) item.classList.add('active');
            updateChatTitle();
            await loadHistory(chatId);
            // Сохраняем текущий чат на сервере
            try {
                await fetch('/api/set_current_chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user_id: parseInt(userId), chat_id: chatId })
                });
            } catch(e) {}
        }
        
        async function createNewChat() {
            try {
                const resp = await fetch('/api/create_chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user_id: parseInt(userId) })
                });
                const data = await resp.json();
                if (data.chat_id) {
                    chats[data.chat_id] = data.name || 'Новый чат';
                    renderChatList();
                    switchChat(data.chat_id);
                    chatArea.innerHTML = '';
                    addMessage('✨ Новый чат создан! Задай свой вопрос.', false);
                }
            } catch(e) {
                console.log('Ошибка создания чата:', e);
            }
        }
        
        async function deleteChat(chatId) {
            if (chatId === 'main') {
                if (!confirm('Удалить основной чат?')) return;
            }
            if (!confirm('Удалить этот чат?')) return;
            try {
                await fetch('/api/delete_chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user_id: parseInt(userId), chat_id: chatId })
                });
                delete chats[chatId];
                if (chatId === currentChat) {
                    currentChat = 'main';
                    if (!chats['main']) chats['main'] = 'Основной чат';
                }
                renderChatList();
                await loadHistory(currentChat);
            } catch(e) {
                console.log('Ошибка удаления чата:', e);
            }
        }
        
        async function loadHistory(chatId) {
            try {
                const resp = await fetch('/api/get_history', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user_id: parseInt(userId), chat_id: chatId })
                });
                const data = await resp.json();
                chatArea.innerHTML = '';
                if (data.history && data.history.length > 0) {
                    for (const msg of data.history) {
                        const isUser = msg.role === 'user';
                        addMessage(msg.content, isUser);
                    }
                } else {
                    chatArea.innerHTML = `
                        <div class="welcome">
                            <h1>✨ AWESOME AI 2026</h1>
                            <p>Я запоминаю ВЕСЬ диалог — навсегда!<br>Отвечаю на ЛЮБЫЕ вопросы развёрнуто и с душой</p>
                            <div class="features">
                                <span>🧠 Полная память</span>
                                <span>📚 Глубокие ответы</span>
                                <span>💎 Premium</span>
                                <span>🔥 Живая нейросеть</span>
                            </div>
                        </div>
                    `;
                }
                chatArea.scrollTop = chatArea.scrollHeight;
            } catch(e) {
                console.log('Ошибка загрузки истории:', e);
            }
        }
        
        function addMessage(text, isUser) {
            const welcome = chatArea.querySelector('.welcome');
            if (welcome) welcome.remove();
            
            const div = document.createElement('div');
            div.className = 'message ' + (isUser ? 'user' : 'bot');
            
            let formatted = text;
            if (!isUser) {
                formatted = formatted.replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>');
                formatted = formatted.replace(/\\*(.*?)\\*/g, '<i>$1</i>');
                formatted = formatted.replace(/`(.*?)`/g, '<code>$1</code>');
                formatted = formatted.replace(/!\\[(.*?)\\]\\((data:image\\/[^)]+)\\)/g, '<img src="$2" alt="$1">');
                // Поддержка списков
                formatted = formatted.replace(/^\\s*[-*]\\s+/gm, '• ');
                formatted = formatted.replace(/^\\s*\\d+\\.\\s+/gm, (m) => `<br>${m}`);
            }
            formatted = formatted.replace(/\\n/g, '<br>');
            
            div.innerHTML = formatted;
            chatArea.appendChild(div);
            chatArea.scrollTop = chatArea.scrollHeight;
            messageCount++;
        }
        
        function showTyping(show) {
            const existing = document.querySelector('.typing-indicator');
            if (existing) existing.remove();
            if (show) {
                const div = document.createElement('div');
                div.className = 'typing-indicator';
                div.innerHTML = '<span></span><span></span><span></span>';
                chatArea.appendChild(div);
                chatArea.scrollTop = chatArea.scrollHeight;
            }
        }
        
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
                    body: JSON.stringify({ 
                        message: msg, 
                        user_id: parseInt(userId),
                        chat_id: currentChat
                    })
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
        
        async function clearCurrentChat() {
            if (!confirm('🧹 Очистить этот чат?')) return;
            try {
                await fetch('/api/clear_chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        user_id: parseInt(userId), 
                        chat_id: currentChat 
                    })
                });
                chatArea.innerHTML = `
                    <div class="welcome">
                        <h1>✨ AWESOME AI 2026</h1>
                        <p>Чат очищен! Начинай заново</p>
                        <div class="features">
                            <span>🧠 Полная память</span>
                            <span>📚 Глубокие ответы</span>
                            <span>💎 Premium</span>
                            <span>🔥 Живая нейросеть</span>
                        </div>
                    </div>
                `;
                addMessage('🧹 Чат очищен!', false);
            } catch(e) {
                addMessage('⚠️ Ошибка очистки', false);
            }
        }
        
        // СОБЫТИЯ
        document.addEventListener('DOMContentLoaded', () => {
            loadChats();
            input.focus();
            input.addEventListener('keydown', e => {
                if (e.key === 'Enter') { e.preventDefault(); sendMessage(); }
            });
            sendBtn.addEventListener('click', e => { e.preventDefault(); sendMessage(); });
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

@app.route('/api/get_chats', methods=['POST', 'OPTIONS'])
def get_chats():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.json
        user_id = data.get('user_id', 1)
        
        if user_id not in chat_list:
            chat_list[user_id] = ['main']
        if user_id not in dialogs:
            dialogs[user_id] = {}
        
        # Загружаем названия чатов
        chats = {'main': 'Основной чат'}
        for chat_id in chat_list[user_id]:
            if chat_id != 'main':
                # Берем первое сообщение как название
                dialog = get_dialog(user_id, chat_id)
                if dialog and len(dialog) > 0:
                    first = dialog[0]['content'][:30]
                    chats[chat_id] = first + ('...' if len(first) >= 30 else '')
                else:
                    chats[chat_id] = 'Новый чат'
        
        current = get_current_chat(user_id)
        return jsonify({'chats': chats, 'current': current})
    except Exception as e:
        return jsonify({'chats': {'main': 'Основной чат'}, 'current': 'main'})

@app.route('/api/create_chat', methods=['POST', 'OPTIONS'])
def create_chat():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.json
        user_id = data.get('user_id', 1)
        chat_id = create_new_chat(user_id)
        return jsonify({'chat_id': chat_id, 'name': 'Новый чат'})
    except:
        return jsonify({'error': 'Ошибка создания чата'})

@app.route('/api/delete_chat', methods=['POST', 'OPTIONS'])
def delete_chat():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.json
        user_id = data.get('user_id', 1)
        chat_id = data.get('chat_id', 'main')
        if chat_id != 'main':
            if user_id in chat_list and chat_id in chat_list[user_id]:
                chat_list[user_id].remove(chat_id)
            if user_id in dialogs and chat_id in dialogs[user_id]:
                del dialogs[user_id][chat_id]
            clear_history(user_id, chat_id)
        return jsonify({'status': 'ok'})
    except:
        return jsonify({'status': 'error'})

@app.route('/api/set_current_chat', methods=['POST', 'OPTIONS'])
def set_current_chat():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.json
        user_id = data.get('user_id', 1)
        chat_id = data.get('chat_id', 'main')
        set_current_chat(user_id, chat_id)
        return jsonify({'status': 'ok'})
    except:
        return jsonify({'status': 'error'})

@app.route('/api/clear_chat', methods=['POST', 'OPTIONS'])
def clear_chat():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.json
        user_id = data.get('user_id', 1)
        chat_id = data.get('chat_id', 'main')
        clear_dialog(user_id, chat_id)
        return jsonify({'status': 'ok'})
    except:
        return jsonify({'status': 'error'})

@app.route('/api/get_history', methods=['POST', 'OPTIONS'])
def get_history():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.json
        user_id = data.get('user_id', 1)
        chat_id = data.get('chat_id', 'main')
        history = get_full_dialog(user_id, chat_id, limit=999)
        return jsonify({'history': history})
    except:
        return jsonify({'history': []})

@app.route('/api/chat', methods=['POST', 'OPTIONS'])
def chat():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        message = data.get('message', '')
        user_id = data.get('user_id', 1)
        chat_id = data.get('chat_id', 'main')
        
        print(f"📩 [{user_id}] [{chat_id}]: {message[:50]}...", flush=True)
        
        if not message:
            return jsonify({'error': 'Напиши что-нибудь!'})

        ensure_user(user_id, f"user_{user_id}")

        if not can_send_message(user_id):
            return jsonify({'reply': "🔴 Лимит исчерпан!\n💎 Купи Premium в боте @awesomeneiro_bot"})

        if message.startswith('/'):
            cmd = message.lower().strip()
            
            if cmd == '/clear':
                clear_dialog(user_id, chat_id)
                return jsonify({'reply': "🧹 Чат очищен!"})
                
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
                dialog_len = len(get_dialog(user_id, chat_id))
                reply = f"📊 **СТАТУС**\n\n👤 {status_text}\n📨 {messages}/{FREE_LIMIT if not premium else '♾️'}\n🧠 Сообщений в чате: {dialog_len}\n\n💎 Купить Premium: @awesomeneiro_bot"
                return jsonify({'reply': reply})
                
            elif cmd == '/premium':
                has_premium = get_premium_status(user_id)
                if has_premium:
                    expires = get_premium_expires(user_id)
                    if expires:
                        return jsonify({'reply': f"💎 **У ТЕБЯ ЕСТЬ PREMIUM!**\n\n⏳ До: {format_date(expires)}\n📨 Лимит: ♾️ БЕЗЛИМИТНО\n\n💎 Купить/продлить: @awesomeneiro_bot"})
                    else:
                        return jsonify({'reply': "💎 **У ТЕБЯ ЕСТЬ PREMIUM!**\n\n📨 Лимит: ♾️ БЕЗЛИМИТНО\n\n💎 Купить/продлить: @awesomeneiro_bot"})
                else:
                    return jsonify({'reply': "💎 **PREMIUM AWESOME AI**\n\n🔥 ЧТО ТЫ ПОЛУЧАЕШЬ:\n♾️ БЕЗЛИМИТНЫЕ СООБЩЕНИЯ\n🚀 Приоритетная обработка\n🧠 Максимально глубокие ответы\n💎 VIP-поддержка\n\n💰 100₽/месяц\n📲 Купить: @awesomeneiro_bot\n🎁 Попробуй /test"})
                
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
                    return jsonify({'reply': '⛔ Ты уже использовал тест Premium!\nКупи Premium: @awesomeneiro_bot'})
                    
                if set_premium(user_id, "2d"):
                    try:
                        conn = sqlite3.connect('users_web.db')
                        c = conn.cursor()
                        c.execute('UPDATE users_web SET test_used = 1 WHERE user_id = ?', (user_id,))
                        conn.commit()
                        conn.close()
                    except:
                        pass
                    return jsonify({'reply': "🎉 **ПРОБНЫЙ PREMIUM АКТИВИРОВАН НА 2 ДНЯ!**\n\n✅ ♾️ БЕЗЛИМИТНЫЕ СООБЩЕНИЯ\n✅ Приоритетная обработка\n✅ Максимально глубокие ответы\n\n⏳ Доступ активен 48 часов.\n💎 Купить Premium: @awesomeneiro_bot"})
                else:
                    return jsonify({'reply': '❌ Ошибка при активации теста'})
                    
            elif cmd == '/profile':
                user_data = get_db_user(user_id)
                if not user_data:
                    return jsonify({'reply': '❌ Пользователь не найден'})
                messages = user_data.get('messages_today', 0)
                premium = get_premium_status(user_id)
                joined_at = user_data.get('joined_at', 'Неизвестно')
                dialog_len = len(get_dialog(user_id, chat_id))
                
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
                    
                return jsonify({'reply': f"👤 **ПРОФИЛЬ**\n\n🆔 ID: {user_id}\n💎 Статус: {status}\n📨 Лимит: {limit_text}\n✉️ Сегодня: {messages}\n🧠 Сообщений в чате: {dialog_len}\n📅 Вход: {joined_at}\n\n💎 Купить Premium: @awesomeneiro_bot"})
                
            elif cmd == '/help':
                return jsonify({'reply': """🧠 **AWESOME AI — ПОМОЩЬ**

🌐 **ЧТО Я УМЕЮ:**
• 🧠 ЗАПОМИНАЮ ВЕСЬ ДИАЛОГ НАВСЕГДА!
• 📚 ОТВЕЧАЮ НА ЛЮБЫЕ ВОПРОСЫ РАЗВЁРНУТО!
• 💎 Premium: безлимит + приоритет
• 🔥 Самая живая нейросеть!

📋 **КОМАНДЫ:**
/status — Статус
/premium — Premium
/test — Пробный Premium
/profile — Профиль
/help — Помощь
/clear — Очистить чат

💎 **Купить Premium: @awesomeneiro_bot**

🧠 Я запоминаю ВСЁ, что ты говоришь - НАВСЕГДА!"""})

        response = process_message_with_history(user_id, chat_id, message)
        if response:
            increment_messages(user_id)
            return jsonify({'reply': response})
        else:
            return jsonify({'reply': "❌ Не удалось обработать запрос."})

    except Exception as e:
        print(f"❌ Ошибка: {e}", flush=True)
        return jsonify({'error': str(e)})

# ============================================================
# ЗАПУСК
# ============================================================
if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    print("=" * 60, flush=True)
    print("🧠 AWESOME AI 2026 - КАК DEEPSEEK!", flush=True)
    print("=" * 60, flush=True)
    print(f"👑 Владелец ID: {OWNER_ID}", flush=True)
    print(f"🌐 http://0.0.0.0:{port}", flush=True)
    print("=" * 60, flush=True)
    print("✅ Боковая панель с чатами (как DeepSeek)", flush=True)
    print("✅ Полная память диалога навсегда", flush=True)
    print("✅ Самые живые и развёрнутые ответы", flush=True)
    print("✅ GigaChat + YandexGPT (супер-умный)", flush=True)
    print("✅ Связь с Telegram ботом @awesomeneiro_bot", flush=True)
    print("✅ Premium синхронизируется с ботом", flush=True)
    print("=" * 60, flush=True)
    app.run(host='0.0.0.0', port=port, debug=True)
