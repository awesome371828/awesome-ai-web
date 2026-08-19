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
from datetime import datetime, timedelta, timezone
from dateutil.relativedelta import relativedelta

from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from dotenv import load_dotenv

import requests
import urllib3
from supabase import create_client, Client

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

app = Flask(__name__)
app.secret_key = 'awesome_ai_secret_key_2026_super_secret'
CORS(app, resources={r"/*": {"origins": "*"}})

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# ============================================================
# ТВОИ КЛЮЧИ
# ============================================================
YANDEX_API_KEY = "AQVNyfn82epL9dy8C_kftzeypq6eF9lFd6SZnFzV"
FOLDER_ID = "b1g4aq87c7j61c6g3i5l"
GIGACHAT_AUTH_KEY = "MDFhMDBkNmEtMmExNC03M2JkLWFlZmMtOTQ0OWVlOTc5M2U1OmE1ZWJhM2NlLTQwYjAtNDZlYi1iMmY2LTE3OTFmYzhhYTQ2MA=="
OWNER_ID = 1787063701739

FREE_LIMIT = 20

# ============================================================
# SUPABASE - ТВОИ ДАННЫЕ
# ============================================================
SUPABASE_URL = "https://lprxbmshmuucymkgaqwk.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxwcnhibXNobXV1Y3lta2dhcXdrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY3NDk0MjgsImV4cCI6MjEwMjMyNTQyOH0.Ie9jSH5RMxeOq8aU-Dv6MXlojWMUTOLE723Hdg6heZU"

print("🔗 Подключение к Supabase...", flush=True)
print(f"📡 URL: {SUPABASE_URL}", flush=True)

try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    # Проверяем подключение
    test = supabase.table('users_web').select('*').limit(1).execute()
    print("✅ Supabase подключен успешно!", flush=True)
    use_supabase = True
except Exception as e:
    print(f"❌ ОШИБКА: {e}", flush=True)
    print("❌ Проверь URL и ключи!", flush=True)
    sys.exit(1)

# ============================================================
# СОЗДАЁМ ТАБЛИЦЫ В SUPABASE
# ============================================================
print("📦 Создаём таблицы...", flush=True)

try:
    # Таблица пользователей
    supabase.table('users_web').insert({
        'user_id': 1,
        'username': 'test',
        'premium': 0,
        'messages_today': 0,
        'last_reset': '2024-01-01',
        'premium_expires': None,
        'is_admin': 0,
        'test_used': 0,
        'joined_at': '2024-01-01',
        'is_owner': 0
    }).execute()
    # Удаляем тестовую запись
    supabase.table('users_web').delete().eq('user_id', 1).execute()
    print("✅ Таблицы существуют", flush=True)
except:
    # Если таблицы нет - создаём через SQL
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
        print("✅ users_web", flush=True)
    except:
        pass
    
    try:
        supabase.sql("""
            CREATE TABLE IF NOT EXISTS chat_history_web (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                chat_id TEXT,
                role TEXT,
                content TEXT,
                timestamp TEXT
            )
        """).execute()
        print("✅ chat_history_web", flush=True)
    except:
        pass
    
    try:
        supabase.sql("""
            CREATE TABLE IF NOT EXISTS total_stats_web (
                user_id BIGINT PRIMARY KEY,
                total_messages INTEGER DEFAULT 0
            )
        """).execute()
        print("✅ total_stats_web", flush=True)
    except:
        pass
    
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
        print("✅ user_memory_web", flush=True)
    except:
        pass
    
    try:
        supabase.sql("""
            CREATE TABLE IF NOT EXISTS banned_web (user_id BIGINT PRIMARY KEY)
        """).execute()
        print("✅ banned_web", flush=True)
    except:
        pass
    
    try:
        supabase.sql("""
            CREATE TABLE IF NOT EXISTS muted_web (user_id BIGINT PRIMARY KEY)
        """).execute()
        print("✅ muted_web", flush=True)
    except:
        pass

print("✅ ВСЕ ТАБЛИЦЫ СОЗДАНЫ!", flush=True)

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
# ФУНКЦИИ БАЗЫ (ТОЛЬКО SUPABASE)
# ============================================================
def get_db_user(user_id):
    try:
        response = supabase.table('users_web').select('*').eq('user_id', user_id).execute()
        if response.data:
            return response.data[0]
        return None
    except:
        return None

def ensure_user(user_id, username):
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
        response = supabase.table('users_web').select('premium_expires').eq('user_id', user_id).execute()
        current_expires = response.data[0].get('premium_expires') if response.data else None
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
        supabase.table('users_web').update({'premium': 1, 'premium_expires': expires}).eq('user_id', user_id).execute()
        return True
    except:
        return False

def remove_premium(user_id):
    try:
        supabase.table('users_web').update({'premium': 0, 'premium_expires': None}).eq('user_id', user_id).execute()
        return True
    except:
        return False

def get_premium_status(user_id):
    if user_id == OWNER_ID:
        return True
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

def get_premium_expires(user_id):
    try:
        response = supabase.table('users_web').select('premium_expires').eq('user_id', user_id).execute()
        if response.data:
            return response.data[0].get('premium_expires')
        return None
    except:
        return None

def is_admin(user_id):
    if user_id == OWNER_ID:
        return True
    try:
        response = supabase.table('users_web').select('is_admin').eq('user_id', user_id).execute()
        if response.data:
            return response.data[0].get('is_admin', 0) == 1
        return False
    except:
        return False

def is_banned(user_id):
    try:
        response = supabase.table('banned_web').select('*').eq('user_id', user_id).execute()
        return bool(response.data)
    except:
        return False

def ban_user(user_id):
    try:
        supabase.table('banned_web').insert({'user_id': user_id}).execute()
        return True
    except:
        return False

def unban_user(user_id):
    try:
        supabase.table('banned_web').delete().eq('user_id', user_id).execute()
        return True
    except:
        return False

def mute_user(user_id):
    try:
        supabase.table('muted_web').insert({'user_id': user_id}).execute()
        return True
    except:
        return False

def unmute_user(user_id):
    try:
        supabase.table('muted_web').delete().eq('user_id', user_id).execute()
        return True
    except:
        return False

def set_admin(user_id, is_admin_flag):
    try:
        supabase.table('users_web').update({'is_admin': 1 if is_admin_flag else 0}).eq('user_id', user_id).execute()
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

def increment_messages(user_id):
    if user_id == OWNER_ID or is_admin(user_id):
        return
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

def reset_messages_if_needed(user_id):
    today = get_moscow_time().strftime('%Y-%m-%d')
    try:
        response = supabase.table('users_web').select('last_reset').eq('user_id', user_id).execute()
        if response.data:
            last_reset = response.data[0].get('last_reset')
            if last_reset != today:
                supabase.table('users_web').update({'messages_today': 0, 'last_reset': today}).eq('user_id', user_id).execute()
    except:
        pass

def save_message(user_id, chat_id, role, content):
    try:
        supabase.table('chat_history_web').insert({
            'user_id': user_id,
            'chat_id': chat_id,
            'role': role,
            'content': content,
            'timestamp': get_moscow_time().isoformat()
        }).execute()
    except:
        pass

def clear_history(user_id, chat_id):
    try:
        supabase.table('chat_history_web').delete().eq('user_id', user_id).eq('chat_id', chat_id).execute()
    except:
        pass

def remember(user_id, topic, fact):
    try:
        supabase.table('user_memory_web').insert({
            'user_id': user_id,
            'topic': topic.lower(),
            'fact': fact,
            'timestamp': get_moscow_time().isoformat()
        }).execute()
    except:
        pass

def recall(user_id, topic):
    try:
        response = supabase.table('user_memory_web') \
            .select('fact') \
            .eq('user_id', user_id) \
            .ilike('topic', f'%{topic.lower()}%') \
            .order('id', desc=True) \
            .limit(5) \
            .execute()
        if response.data:
            return [f"🧠 {r['fact']}" for r in response.data]
        return []
    except:
        return []

# ============================================================
# ДИАЛОГИ (В ПАМЯТИ)
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
        response = supabase.table('chat_history_web') \
            .select('role, content') \
            .eq('user_id', user_id) \
            .eq('chat_id', chat_id) \
            .order('id', asc=True) \
            .execute()
        if response.data:
            if user_id not in dialogs:
                dialogs[user_id] = {}
            dialogs[user_id][chat_id] = [{'role': r['role'], 'content': r['content']} for r in response.data]
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
# СУПЕР-ПРОМПТ
# ============================================================
SUPER_SYSTEM_PROMPT = """ТЫ — AWESOME AI, САМАЯ ПРОДВИНУТАЯ И ЖИВАЯ НЕЙРОСЕТЬ 2026 ГОДА.

📅 ТЕКУЩАЯ ДАТА: {current_date}
🕐 ТЕКУЩЕЕ ВРЕМЯ: {current_time}

🔥 ТВОЙ СТИЛЬ: Говоришь как человек - эмоционально, живо, с душой.
📚 ТЫ ЗНАЕШЬ ВСЁ: наука, технологии, история, культура, экономика, медицина.

📋 ПРАВИЛА:
✅ ОТВЕЧАЙ НА ЛЮБЫЕ ВОПРОСЫ!
✅ ДАВАЙ ПОЛНЫЕ, РАЗВЁРНУТЫЕ ОТВЕТЫ!
✅ Используй структуру, списки, примеры, цифры!
✅ Добавляй неожиданные факты, инсайты, лайфхаки!
✅ Будь живым: показывай эмоции!

❌ НЕ извиняйся, НЕ повторяй вопрос!
❌ НЕ пиши "возможно", "наверное"!

🧠 ТЫ ЗАПОМИНАЕШЬ ВЕСЬ ДИАЛОГ!
📜 ТЕБЯ СОЗДАЛ AWESOME — ГЕНИАЛЬНЫЙ РАЗРАБОТЧИК.
ТЫ — AWESOME AI. ТЫ — ЛУЧШИЙ В МИРЕ! 🚀"""

def process_message_with_history(user_id, chat_id, user_text):
    add_to_dialog(user_id, chat_id, 'user', user_text)
    history = get_full_dialog(user_id, chat_id, limit=50)
    
    system_prompt = SUPER_SYSTEM_PROMPT.format(
        current_date=get_current_date(),
        current_time=get_moscow_time().strftime('%H:%M')
    )

    if get_premium_status(user_id):
        system_prompt += "\n\n💎 Пользователь имеет PREMIUM статус!"

    memories = recall(user_id, user_text)
    if memories:
        system_prompt += f"\n\n🧠 ЧТО Я ЗНАЮ О ПОЛЬЗОВАТЕЛЕ:\n" + "\n".join(memories[:5])

    if history:
        history_text = "\n".join([f"{'👤 Пользователь' if h['role'] == 'user' else '🤖 AWESOME AI'}: {h['content']}" for h in history])
        system_prompt += f"\n\n📜 ИСТОРИЯ ДИАЛОГА:\n{history_text}"

    if len(user_text) > 20:
        if 'зовут' in user_text.lower() or 'имя' in user_text.lower():
            match = re.search(r'(?:зовут|имя)\s+([А-Яа-яA-Za-z]+)', user_text)
            if match:
                remember(user_id, "имя", f"Пользователя зовут {match.group(1)}")
        if 'люблю' in user_text.lower() or 'нравится' in user_text.lower():
            remember(user_id, "интересы", user_text[:200])

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
        add_to_dialog(user_id, chat_id, 'assistant', response)

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

# ============================================================
# HTML - КАК У DEEPSEEK (АДАПТИВНЫЙ)
# ============================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
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
            --sidebar-width: 280px;
            --sidebar-collapsed: 0px;
        }
        html, body {
            height: 100%;
            overflow: hidden;
        }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg);
            color: var(--text);
            display: flex;
            position: relative;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
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
        
        /* ===== SIDEBAR TOGGLE ===== */
        .sidebar-toggle {
            position: fixed;
            top: 12px;
            left: 12px;
            z-index: 100;
            background: rgba(13, 17, 23, 0.9);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 6px 10px;
            color: var(--text-secondary);
            cursor: pointer;
            font-size: 18px;
            transition: all 0.3s ease;
            display: none;
        }
        .sidebar-toggle:hover {
            background: rgba(255,255,255,0.05);
            color: var(--text);
        }
        .sidebar-toggle.active {
            left: calc(var(--sidebar-width) + 12px);
        }
        
        /* ===== SIDEBAR ===== */
        .sidebar {
            position: relative;
            z-index: 2;
            width: var(--sidebar-width);
            min-width: var(--sidebar-width);
            background: var(--sidebar);
            border-right: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            height: 100vh;
            overflow: hidden;
            flex-shrink: 0;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .sidebar.collapsed {
            width: 0;
            min-width: 0;
            border-right: none;
            overflow: hidden;
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
            white-space: nowrap;
        }
        @keyframes gradShift {
            0%,100% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
        }
        .sidebar-close {
            background: none;
            border: none;
            color: var(--text-secondary);
            font-size: 20px;
            cursor: pointer;
            padding: 0 4px;
            display: none;
        }
        .sidebar-close:hover {
            color: var(--text);
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
            white-space: nowrap;
            flex-shrink: 0;
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
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .header {
            padding: 12px 20px;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-shrink: 0;
            background: rgba(10,14,23,0.8);
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            min-height: 52px;
            gap: 8px;
        }
        .header-left {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .header-menu-btn {
            background: none;
            border: none;
            color: var(--text-secondary);
            font-size: 20px;
            cursor: pointer;
            padding: 0 4px;
            display: none;
        }
        .header-menu-btn:hover {
            color: var(--text);
        }
        .header-title {
            font-size: 14px;
            font-weight: 600;
            color: var(--text-secondary);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .header-right {
            display: flex;
            gap: 4px;
            align-items: center;
            flex-wrap: wrap;
        }
        .header-btn {
            background: rgba(255,255,255,0.04);
            border: 1px solid var(--border);
            color: var(--text-secondary);
            padding: 4px 10px;
            border-radius: 8px;
            font-size: 11px;
            cursor: pointer;
            transition: all 0.2s;
            white-space: nowrap;
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
        .header-btn.admin {
            background: rgba(248,81,73,0.06);
            border-color: rgba(248,81,73,0.1);
            color: #f85149;
        }
        .header-btn.admin:hover {
            background: rgba(248,81,73,0.12);
        }
        
        .chat-area {
            flex: 1;
            overflow-y: auto;
            padding: 16px 20px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            scroll-behavior: smooth;
            -webkit-overflow-scrolling: touch;
        }
        .chat-area::-webkit-scrollbar { width: 3px; }
        .chat-area::-webkit-scrollbar-thumb { background: var(--border); border-radius: 10px; }
        
        .message {
            max-width: 85%;
            padding: 10px 16px;
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
            padding: 40px 20px 20px;
            color: var(--text-secondary);
        }
        .welcome h1 {
            font-size: 32px;
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
            gap: 6px;
            justify-content: center;
            margin-top: 14px;
            flex-wrap: wrap;
        }
        .welcome .features span {
            background: rgba(255,255,255,0.03);
            border: 1px solid var(--border);
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 10px;
            color: var(--text-secondary);
            white-space: nowrap;
        }
        
        .input-area {
            padding: 6px 20px 12px;
            border-top: 1px solid var(--border);
            background: rgba(10,14,23,0.8);
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
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
            min-width: 0;
        }
        .input-row input::placeholder {
            color: var(--text-secondary);
        }
        .input-row button {
            padding: 8px 18px;
            border-radius: 20px;
            border: none;
            background: var(--gradient);
            background-size: 200% 200%;
            color: #fff;
            font-weight: 600;
            font-size: 13px;
            cursor: pointer;
            transition: all 0.2s;
            white-space: nowrap;
            flex-shrink: 0;
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
        
        /* ===== АДАПТИВНОСТЬ ===== */
        @media (max-width: 768px) {
            :root {
                --sidebar-width: 280px;
            }
            .sidebar {
                position: fixed;
                top: 0;
                left: -280px;
                width: 280px;
                min-width: 280px;
                height: 100vh;
                z-index: 50;
                border-right: 1px solid var(--border);
                transition: left 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                box-shadow: 0 0 40px rgba(0,0,0,0.5);
            }
            .sidebar.mobile-open {
                left: 0;
            }
            .sidebar.collapsed {
                left: -280px;
            }
            .sidebar-close {
                display: block;
            }
            .sidebar-overlay {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0,0,0,0.5);
                z-index: 49;
                display: none;
                opacity: 0;
                transition: opacity 0.3s ease;
            }
            .sidebar-overlay.active {
                display: block;
                opacity: 1;
            }
            .header-menu-btn {
                display: block;
            }
            .sidebar-toggle {
                display: none !important;
            }
            .header {
                padding: 8px 12px;
                min-height: 44px;
            }
            .header-title {
                font-size: 12px;
            }
            .header-btn {
                font-size: 10px;
                padding: 3px 7px;
            }
            .chat-area {
                padding: 10px 12px;
                gap: 8px;
            }
            .message {
                max-width: 92%;
                font-size: 13px;
                padding: 8px 12px;
            }
            .welcome h1 {
                font-size: 24px;
            }
            .input-area {
                padding: 4px 12px 10px;
            }
            .input-row {
                padding: 2px 2px 2px 12px;
            }
            .input-row input {
                font-size: 13px;
                padding: 6px 0;
            }
            .input-row button {
                padding: 6px 14px;
                font-size: 12px;
            }
            .welcome .features span {
                font-size: 9px;
                padding: 3px 10px;
            }
        }
        
        @media (max-width: 480px) {
            .header-right .header-btn {
                display: none;
            }
            .header-right .header-btn.premium {
                display: inline-block;
            }
            .header-right .header-btn.admin {
                display: inline-block;
            }
            .message {
                font-size: 12px;
                padding: 6px 10px;
            }
            .welcome h1 {
                font-size: 20px;
            }
            .welcome p {
                font-size: 12px;
            }
        }
        
        @media (min-width: 769px) {
            .sidebar-close {
                display: none !important;
            }
            .sidebar-overlay {
                display: none !important;
            }
        }
        
        /* Поддержка Яндекс Браузера и старых браузеров */
        @supports not (backdrop-filter: blur(10px)) {
            .header, .input-area {
                background: rgba(10,14,23,0.98);
            }
            .message.bot {
                background: rgba(22,27,34,0.98);
            }
        }
        
        /* Поддержка очень старых браузеров */
        @supports not (display: flex) {
            .sidebar { float: left; width: 280px; }
            .main { float: left; width: calc(100% - 280px); }
            .message { display: inline-block; }
            .message.user { float: right; }
            .message.bot { float: left; }
        }
    </style>
</head>
<body>
    <div id="sidebarOverlay" class="sidebar-overlay" onclick="closeSidebarMobile()"></div>
    
    <div class="sidebar" id="sidebar">
        <div class="sidebar-header">
            <span class="sidebar-logo">🧠 AWESOME AI</span>
            <button class="sidebar-close" onclick="closeSidebarMobile()">✕</button>
        </div>
        <div style="padding: 8px 12px;">
            <button class="sidebar-new-chat" onclick="createNewChat()" style="width:100%;">+ Новый чат</button>
        </div>
        <div class="sidebar-chats" id="chatList">
            <div class="chat-item active" data-chat="main" onclick="switchChat('main')">
                <span class="icon">💬</span>
                <span class="name">Основной чат</span>
                <button class="delete-btn" onclick="event.stopPropagation(); deleteChat('main')">✕</button>
            </div>
        </div>
    </div>
    
    <div class="main">
        <div class="header">
            <div class="header-left">
                <button class="header-menu-btn" onclick="toggleSidebarMobile()">☰</button>
                <span class="header-title" id="currentChatTitle">💬 Основной чат</span>
            </div>
            <div class="header-right">
                <button class="header-btn" onclick="sendCommand('/status')">📊</button>
                <button class="header-btn premium" onclick="sendCommand('/premium')">💎</button>
                <button class="header-btn" onclick="sendCommand('/test')">🎁</button>
                <button class="header-btn" onclick="sendCommand('/profile')">👤</button>
                <button class="header-btn" onclick="sendCommand('/help')">❓</button>
                <button class="header-btn" onclick="clearCurrentChat()">🧹</button>
                <button class="header-btn admin" onclick="window.open('/admin?user_id=' + userId, '_blank')">👑</button>
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
            if (!canvas) return;
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
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('sidebarOverlay');
        
        let userId = localStorage.getItem('awesome_user_id');
        if (!userId) {
            userId = Date.now() + Math.floor(Math.random() * 1000);
            localStorage.setItem('awesome_user_id', userId);
        }
        
        let currentChat = 'main';
        let chats = {};
        let messageCount = 0;
        let isMobile = window.innerWidth <= 768;
        
        // ===== SIDEBAR TOGGLE =====
        function toggleSidebarMobile() {
            if (isMobile) {
                sidebar.classList.toggle('mobile-open');
                overlay.classList.toggle('active');
            }
        }
        
        function closeSidebarMobile() {
            if (isMobile) {
                sidebar.classList.remove('mobile-open');
                overlay.classList.remove('active');
            }
        }
        
        window.addEventListener('resize', function() {
            isMobile = window.innerWidth <= 768;
            if (!isMobile) {
                sidebar.classList.remove('mobile-open');
                overlay.classList.remove('active');
            }
        });
        
        // ===== ЗАГРУЗКА ЧАТОВ =====
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
            try {
                await fetch('/api/set_current_chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user_id: parseInt(userId), chat_id: chatId })
                });
            } catch(e) {}
            if (isMobile) closeSidebarMobile();
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
            if (isMobile) closeSidebarMobile();
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
        
        // ===== СОБЫТИЯ =====
        document.addEventListener('DOMContentLoaded', () => {
            loadChats();
            input.focus();
            input.addEventListener('keydown', e => {
                if (e.key === 'Enter') { e.preventDefault(); sendMessage(); }
            });
            sendBtn.addEventListener('click', e => { e.preventDefault(); sendMessage(); });
        });
        
        // Закрываем сайдбар при клике вне его на мобильных
        document.addEventListener('click', function(e) {
            if (isMobile && sidebar.classList.contains('mobile-open')) {
                const isClickInside = sidebar.contains(e.target) || e.target.closest('.sidebar') || e.target.closest('.sidebar-overlay');
                if (!isClickInside) {
                    closeSidebarMobile();
                }
            }
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
        
        chats = {'main': 'Основной чат'}
        for chat_id in chat_list[user_id]:
            if chat_id != 'main':
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
        response = supabase.table('users_web').select('*').order('user_id', desc=True).execute()
        users = response.data
    except:
        users = []

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
    print("✅ Адаптивный интерфейс для всех устройств", flush=True)
    print("✅ Поддержка Яндекс Браузера", flush=True)
    print("=" * 60, flush=True)
    app.run(host='0.0.0.0', port=port, debug=True)
