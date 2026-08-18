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
CORS(app, resources={r"/*": {"origins": "*"}})

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# ============================================================
# ТВОИ КЛЮЧИ - ИСПРАВЛЕНО!
# ============================================================
SUPABASE_URL = "https://1prxbm_shmuucymkgagwk.supabase.co"  # БЕЗ ПРОБЕЛА!  # БЕЗ ПРОБЕЛА!  # УБЕРИ ПРОБЕЛ!
# ДОЛЖНО БЫТЬ: https://lprxbm shmuucymkgaqwk.supabase.co
# ПРОСТО УБЕРИ ПРОБЕЛ МЕЖДУ lprxbm И shmuucymkgaqwk

SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxwcnhibXNobXV1Y3lta2dhcXdrIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4Njc0OTQyOCwiZXhwIjoyMTAyMzI1NDI4fQ.JSlHsddyJRATpVfCk35Q9XYtzZ0mvjnZjcIzxR2nDEw"

YANDEX_API_KEY = "AQVNyfn82epL9dy8C_kftzeypq6eF9lFd6SZnFzV"
FOLDER_ID = "b1g4aq87c7j61c6g3i5l"
GIGACHAT_AUTH_KEY = "MDFhMDBkNmEtMmExNC03M2JkLWFlZmMtOTQ0OWVlOTc5M2U1OmE1ZWJhM2NlLTQwYjAtNDZlYi1iMmY2LTE3OTFmYzhhYTQ2MA=="
OWNER_ID = 1787063701739

FREE_LIMIT = 20

# ============================================================
# ПОДКЛЮЧЕНИЕ К SUPABASE
# ============================================================
print("🔗 Подключение к Supabase...", flush=True)
print(f"📡 URL: {SUPABASE_URL}", flush=True)

try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    test = supabase.table('users_web').select('*').limit(1).execute()
    print("✅ Supabase подключен успешно!", flush=True)
except Exception as e:
    print(f"❌ ОШИБКА: {e}", flush=True)
    print("❌ УБЕРИ ПРОБЕЛ В URL!", flush=True)
    sys.exit(1)

# ============================================================
# СОЗДАЁМ ТАБЛИЦЫ
# ============================================================
print("📦 Создаём таблицы...", flush=True)

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
    
    supabase.sql("""
        CREATE TABLE IF NOT EXISTS chat_history_web (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            role TEXT,
            content TEXT,
            timestamp TEXT
        )
    """).execute()
    print("✅ chat_history_web", flush=True)
    
    supabase.sql("""
        CREATE TABLE IF NOT EXISTS total_stats_web (
            user_id BIGINT PRIMARY KEY,
            total_messages INTEGER DEFAULT 0
        )
    """).execute()
    print("✅ total_stats_web", flush=True)
    
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
    
    supabase.sql("""
        CREATE TABLE IF NOT EXISTS banned_web (user_id BIGINT PRIMARY KEY)
    """).execute()
    print("✅ banned_web", flush=True)
    
    supabase.sql("""
        CREATE TABLE IF NOT EXISTS muted_web (user_id BIGINT PRIMARY KEY)
    """).execute()
    print("✅ muted_web", flush=True)
    
    print("✅ ВСЕ ТАБЛИЦЫ СОЗДАНЫ!", flush=True)
    
except Exception as e:
    print(f"⚠️ Ошибка: {e}", flush=True)

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

def save_message(user_id, role, content):
    try:
        supabase.table('chat_history_web').insert({
            'user_id': user_id,
            'role': role,
            'content': content,
            'timestamp': get_moscow_time().isoformat()
        }).execute()
    except:
        pass

def get_history(user_id, limit=10):
    try:
        response = supabase.table('chat_history_web') \
            .select('role, content') \
            .eq('user_id', user_id) \
            .order('id', desc=True) \
            .limit(limit) \
            .execute()
        if response.data:
            return list(reversed(response.data))
        return []
    except:
        return []

def clear_history(user_id):
    try:
        supabase.table('chat_history_web').delete().eq('user_id', user_id).execute()
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
            .limit(3) \
            .execute()
        if response.data:
            return [f"🧠 {r['fact']}" for r in response.data]
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
        response = requests.post(url, headers=headers, json=data, timeout=3, verify=False)
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
        response = requests.post(url, headers=headers, json=data, timeout=3)
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
    save_message(user_id, 'user', user_text)
    history = get_history(user_id, limit=10)

    system_prompt = SUPER_SYSTEM_PROMPT.format(
        current_date=get_current_date(),
        current_time=get_moscow_time().strftime('%H:%M')
    )

    if get_premium_status(user_id):
        system_prompt += "\n\n💎 Пользователь имеет PREMIUM статус!"

    memories = recall(user_id, user_text)
    if memories:
        system_prompt += f"\n\n🧠 Память: {' '.join(memories[:2])}"

    if history:
        history_text = "\n".join([f"{'Пользователь' if h['role'] == 'user' else 'AWESOME AI'}: {h['content']}" for h in history])
        system_prompt += f"\n\n📜 История:\n{history_text}"

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
        save_message(user_id, 'assistant', response)

    return response

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
# HTML
# ============================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AWESOME AI</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0e17;
            color: #e6edf3;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .header {
            background: rgba(10,14,23,0.95);
            padding: 12px 20px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .logo { font-size: 20px; font-weight: 900; background: linear-gradient(135deg, #58a6ff, #f0883e); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .menu button {
            background: rgba(255,255,255,0.05);
            border: none;
            color: #8b949e;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 10px;
            cursor: pointer;
            margin: 2px;
        }
        .menu button:hover { background: rgba(88,166,255,0.1); color: #58a6ff; }
        .chat {
            flex: 1;
            overflow-y: auto;
            padding: 16px 20px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .message {
            max-width: 80%;
            padding: 8px 14px;
            border-radius: 14px;
            font-size: 13px;
            line-height: 1.6;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        .user { align-self: flex-end; background: linear-gradient(135deg, #1f6feb, #6c3ce0); color: #fff; border-bottom-right-radius: 2px; }
        .bot { align-self: flex-start; background: rgba(22,27,34,0.9); border: 1px solid rgba(255,255,255,0.05); border-bottom-left-radius: 2px; }
        .input-area {
            padding: 8px 16px 12px;
            border-top: 1px solid rgba(255,255,255,0.05);
            background: rgba(10,14,23,0.95);
        }
        .input-row { display: flex; gap: 8px; align-items: center; }
        .input-row input {
            flex: 1;
            padding: 8px 16px;
            border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.06);
            background: rgba(22,27,34,0.6);
            color: #e6edf3;
            font-size: 13px;
            outline: none;
        }
        .input-row input:focus { border-color: #58a6ff; }
        .input-row button {
            padding: 8px 20px;
            border-radius: 20px;
            border: none;
            background: linear-gradient(135deg, #1f6feb, #6c3ce0);
            color: #fff;
            font-weight: 600;
            cursor: pointer;
        }
        .input-row button:disabled { opacity: 0.4; cursor: not-allowed; }
        .typing { color: #8b949e; font-size: 12px; padding: 4px 16px; align-self: flex-start; }
        .welcome { text-align: center; padding: 40px 20px; color: #8b949e; }
        .welcome h2 { color: #e6edf3; font-size: 24px; background: linear-gradient(135deg, #58a6ff, #f0883e); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .tools { display: flex; gap: 4px; margin-bottom: 6px; flex-wrap: wrap; }
        .tools button {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.04);
            color: #6e7681;
            padding: 2px 10px;
            border-radius: 14px;
            font-size: 9px;
            cursor: pointer;
        }
        .tools button:hover { background: rgba(255,255,255,0.06); color: #e6edf3; }
    </style>
</head>
<body>
    <header class="header">
        <span class="logo">🧠 AWESOME AI</span>
        <div class="menu">
            <button onclick="sendCommand('/status')">📊</button>
            <button onclick="sendCommand('/premium')">💎</button>
            <button onclick="sendCommand('/test')">🎁</button>
            <button onclick="sendCommand('/profile')">👤</button>
            <button onclick="sendCommand('/stats')">📈</button>
            <button onclick="sendCommand('/help')">❓</button>
            <button onclick="sendCommand('/clear')">🗑️</button>
            <button onclick="sendCommand('/history')">📜</button>
        </div>
    </header>
    <div class="chat" id="chat">
        <div class="welcome">
            <h2>✨ AWESOME AI</h2>
            <p>Спрашивай что угодно</p>
        </div>
    </div>
    <div class="input-area">
        <div class="tools">
            <button onclick="sendCommand('/weather '+prompt('Город?'))">🌤</button>
            <button onclick="sendCommand('/exchange')">💵</button>
            <button onclick="sendCommand('/crypto')">🪙</button>
        </div>
        <div class="input-row">
            <input id="input" placeholder="Напиши..." autofocus>
            <button id="sendBtn">➤</button>
        </div>
    </div>
    <script>
        const chat = document.getElementById('chat');
        const input = document.getElementById('input');
        const sendBtn = document.getElementById('sendBtn');
        let userId = localStorage.getItem('awesome_user_id');
        if (!userId) { userId = Date.now() + Math.floor(Math.random() * 1000); localStorage.setItem('awesome_user_id', userId); }
        
        function addMessage(text, isUser) {
            const welcome = chat.querySelector('.welcome');
            if (welcome) welcome.remove();
            const div = document.createElement('div');
            div.className = 'message ' + (isUser ? 'user' : 'bot');
            div.innerHTML = text.replace(/\\n/g, '<br>');
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
                if (data.error) addMessage('⚠️ ' + data.error, false);
                else if (data.reply) addMessage(data.reply, false);
                else addMessage('⚠️ Пустой ответ', false);
            } catch (e) {
                setTyping(false);
                addMessage('⚠️ Ошибка соединения', false);
            }
            sendBtn.disabled = false;
            input.focus();
        }
        
        function sendCommand(cmd) {
            input.value = cmd;
            sendMessage();
        }
        
        document.addEventListener('DOMContentLoaded', function() {
            input.focus();
            input.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') { e.preventDefault(); sendMessage(); }
            });
            sendBtn.addEventListener('click', function(e) {
                e.preventDefault(); sendMessage();
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
        
        print(f"📩 Получено от {user_id}: {message[:30]}...", flush=True)
        
        if not message:
            return jsonify({'error': 'Напиши что-нибудь!'})

        ensure_user(user_id, f"user_{user_id}")

        if not can_send_message(user_id):
            user_data = get_db_user(user_id)
            messages = user_data.get('messages_today', 0) if user_data else 0
            remaining = FREE_LIMIT - messages
            return jsonify({'reply': f"🔴 Лимит: {remaining}/{FREE_LIMIT}\n💎 Купи Premium: /premium"})

        if message.startswith('/'):
            cmd = message.lower().strip()
            
            if cmd == '/clear':
                clear_history(user_id)
                return jsonify({'reply': "🧹 История очищена!"})
                
            elif cmd == '/history':
                history = get_history(user_id, limit=10)
                if not history:
                    return jsonify({'reply': "📜 История пуста."})
                text = "📜 Последние сообщения:\n"
                for h in history:
                    role = "👤 Вы" if h['role'] == 'user' else "🤖 AWESOME AI"
                    text += f"\n{role}: {h['content'][:100]}"
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
                remaining = FREE_LIMIT - messages if not premium else "♾️"
                return jsonify({'reply': f"📊 СТАТУС\n\n👤 {status_text}\n📨 {remaining}/{FREE_LIMIT if not premium else '♾️'}"})
                
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
                    response = supabase.table('users_web').select('test_used, premium').eq('user_id', user_id).execute()
                    if response.data:
                        test_used = response.data[0].get('test_used', 0)
                    else:
                        return jsonify({'reply': '❌ Пользователь не найден'})
                except:
                    return jsonify({'reply': '❌ Ошибка БД'})

                if get_premium_status(user_id):
                    return jsonify({'reply': '💎 У тебя уже есть Premium!'})
                if test_used == 1:
                    return jsonify({'reply': '⛔ Ты уже использовал тест Premium!\nКупи Premium: /premium'})
                    
                if set_premium(user_id, "2d"):
                    try:
                        supabase.table('users_web').update({'test_used': 1}).eq('user_id', user_id).execute()
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
                    
                return jsonify({'reply': f"👤 ПРОФИЛЬ\n\n🆔 ID: {user_id}\n💎 Статус: {status}\n📨 Лимит: {limit_text}\n✉️ Сегодня: {messages}\n📅 Вход: {joined_at}"})
                
            elif cmd == '/stats':
                if user_id == OWNER_ID or is_admin(user_id):
                    try:
                        response = supabase.table('users_web').select('*').execute()
                        users = response.data
                        total = len(users)
                        premium = sum(1 for u in users if u.get('premium', 0) == 1)
                        admins = sum(1 for u in users if u.get('is_admin', 0) == 1)
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
                        resp = supabase.table('total_stats_web').select('total_messages').eq('user_id', user_id).execute()
                        total = resp.data[0].get('total_messages', 0) if resp.data else 0
                    except:
                        total = 0
                    return jsonify({'reply': f"📊 ТВОЯ СТАТИСТИКА\n\n💎 Статус: {'PREMIUM' if premium else 'Бесплатный'}\n📨 Сегодня: {messages}\n📊 Всего: {total}"})
                
            elif cmd == '/help':
                return jsonify({'reply': """🧠 AWESOME AI — ПОМОЩЬ

🌐 Что я умею:
• 🌤 Погода с прогнозом
• 💵 Курс валют и криптовалют
• 🧠 Запоминаю факты о вас

📋 Команды:
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

💎 Лимиты:
🔓 Бесплатно — 20 сообщений/день
💎 Premium — ♾️ БЕЗЛИМИТНО"""})
                
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

        response = process_message_with_history(user_id, message)
        if response:
            increment_messages(user_id)
            return jsonify({'reply': response})
        else:
            return jsonify({'reply': "❌ Не удалось обработать запрос."})

    except Exception as e:
        print(f"❌ Ошибка: {e}", flush=True)
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
    print("=" * 50, flush=True)
    print("🧠 AWESOME AI 2026", flush=True)
    print("=" * 50, flush=True)
    print(f"👑 Владелец ID: {OWNER_ID}", flush=True)
    print(f"🌐 http://0.0.0.0:{port}", flush=True)
    print("=" * 50, flush=True)
    print("✅ ТОЛЬКО SUPABASE!", flush=True)
    print("=" * 50, flush=True)
    app.run(host='0.0.0.0', port=port, debug=True)
