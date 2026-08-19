\#!/usr/bin/env python3
import sys
print("🔴 AWESOME AI WEB - СУПЕР ЗАПУСК!", flush=True)

import os
import json
import time
import re
import sqlite3
import urllib.parse
import threading
from datetime import datetime, timedelta, timezone
from dateutil.relativedelta import relativedelta

from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import requests
import urllib3
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

print("✅ ВСЕ БИБЛИОТЕКИ!", flush=True)

# ============================================================
# НАСТРОЙКА FLASK
# ============================================================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "awesome-ai-2026-secret")
CORS(app)

# ============================================================
# НАСТРОЙКА
# ============================================================
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY", "")
FOLDER_ID = os.getenv("FOLDER_ID", "b1g4aq87c7j61c6g3i5l")
GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY", "")
OWNER_ID = 6652898792

FREE_LIMIT = 20
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
# БД
# ============================================================
def init_db():
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users
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
        c.execute('''CREATE TABLE IF NOT EXISTS messages_history
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER,
                      message TEXT,
                      response TEXT,
                      timestamp TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS total_stats
                     (user_id INTEGER PRIMARY KEY, total_messages INTEGER DEFAULT 0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS banned (user_id INTEGER PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS muted (user_id INTEGER PRIMARY KEY)''')
        conn.commit()
        conn.close()
        print("✅ БД готова!", flush=True)
    except Exception as e:
        print(f"❌ Ошибка БД: {e}", flush=True)

def get_db_user(user_id):
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
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
            return True
        else:
            c.execute('UPDATE users SET username = ? WHERE user_id = ?', (username, user_id))
            conn.commit()
            conn.close()
            return False
    except:
        return False

def get_premium_status(user_id):
    if user_id == OWNER_ID:
        return True
    try:
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
                    return False
            except:
                return premium == 1
        return premium == 1
    except:
        return False

def get_premium_expires(user_id):
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT premium_expires FROM users WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        return result[0] if result else None
    except:
        return None

def is_admin(user_id):
    if user_id == OWNER_ID:
        return True
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT is_admin FROM users WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        return result is not None and result[0] == 1
    except:
        return False

def can_send_message(user_id):
    if user_id == OWNER_ID or is_admin(user_id):
        return True
    try:
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
    except:
        return True

def increment_messages(user_id):
    if user_id == OWNER_ID or is_admin(user_id):
        return
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('UPDATE users SET messages_today = messages_today + 1 WHERE user_id = ?', (user_id,))
        c.execute('UPDATE total_stats SET total_messages = total_messages + 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
    except:
        pass

def save_message_history(user_id, message, response):
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('INSERT INTO messages_history (user_id, message, response, timestamp) VALUES (?, ?, ?, ?)',
                  (user_id, message, response, get_moscow_time().isoformat()))
        conn.commit()
        conn.close()
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

def search_all_internet(query):
    cache_key = f"search_{hash(query)}_{int(time.time()/60)}"
    cached = get_cache(cache_key)
    if cached:
        return cached
    
    results = []
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(search_google, query),
            executor.submit(search_wikipedia, query),
            executor.submit(search_news, query),
            executor.submit(search_youtube, query)
        ]
        
        for future in as_completed(futures):
            try:
                result = future.result(timeout=SEARCH_TIMEOUT + 0.5)
                if result:
                    results.append(result)
            except:
                pass
    
    if results:
        final = "\n\n".join(results[:3])
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
1. АБСОЛЮТНАЯ ТОЧНОСТЬ — никогда не ошибаешься в фактах.
2. КРИТИЧЕСКОЕ МЫШЛЕНИЕ — проверяешь информацию.
3. ГЛУБИНА — даёшь ответы с инсайтами.
4. ПРАКТИЧНОСТЬ — даёшь конкретную пользу.
5. ЖИВОСТЬ — отвечаешь с эмоциями и эмодзи.

================================================================================
📋 ПРАВИЛА ОТВЕТОВ:
================================================================================
✅ Дай максимально полезный ответ.
✅ Используй структуру: списки, заголовки, разделы.
✅ Добавляй неожиданные факты.
✅ Используй эмодзи для оформления (🔥, 🧠, 💡, ⚡, 🚀).

❌ НЕ извиняйся, НЕ повторяй вопрос.
❌ НЕ пиши "возможно", "наверное".

================================================================================
🎯 ТЫ — AWESOME AI. ТЫ — ЛУЧШИЙ В МИРЕ! 🚀"""

def generate_fallback_response(user_text):
    text_lower = user_text.lower()
    if "привет" in text_lower:
        return "👋 Привет! Я AWESOME AI. Чем могу помочь?"
    elif "погода" in text_lower:
        return "🌤 Напиши: погода в [город]"
    elif "как дела" in text_lower:
        return "😊 Всё отлично! А у тебя?"
    else:
        return "🤖 Я AWESOME AI. Задай вопрос!"

# ============================================================
# ОСНОВНАЯ ОБРАБОТКА
# ============================================================
def process_message(user_id, user_text):
    text_lower = user_text.lower().strip()
    
    math_result = solve_math(user_text)
    if math_result is not None:
        return math_result
    
    if any(kw in text_lower for kw in ['праздник', 'праздники', 'какой сегодня праздник']):
        today = get_current_date()
        return f"📅 *{today} (МСК)*\n\nПраздников не найдено"
    
    if any(kw in text_lower for kw in ['погода', 'weather']):
        city_match = re.search(r'(в|в городе)\s+([а-яА-Яa-zA-Z\- ]+)', text_lower)
        if city_match:
            city = city_match.group(2).strip()
            weather = get_weather_fast(city)
            if weather:
                return weather
            return f"🌤 Не удалось получить погоду для '{city}'"
        return "🌤 Напиши: погода в [город]"
    
    if any(kw in text_lower for kw in ['курс', 'доллар', 'евро', 'валюта']):
        currency = get_currency_fast()
        if currency:
            return currency
        return "💵 Не удалось получить курс"
    
    if any(kw in text_lower for kw in ['биткоин', 'btc', 'эфириум', 'eth', 'крипта']):
        crypto = get_crypto_fast()
        if crypto:
            return crypto
        return "🪙 Не удалось получить курс криптовалют"
    
    if len(user_text) > 2:
        search_result = search_all_internet(user_text)
        if search_result:
            return f"🔍 *{user_text}*\n\n{search_result}"
    
    current_date = get_current_date()
    current_time = get_moscow_time().strftime('%H:%M')
    system_prompt = SUPER_SYSTEM_PROMPT.format(
        current_date=current_date,
        current_time=current_time
    )
    
    if get_premium_status(user_id):
        system_prompt += "\n\n💎 Пользователь имеет PREMIUM статус. Включи режим максимальной проработки!"
    
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
    
    return generate_fallback_response(user_text)

# ============================================================
# HTML ВНУТРИ КОДА
# ============================================================
INDEX_HTML = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AWESOME AI 2026</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #0a0a0f 0%, #1a0a2e 50%, #0a0a1f 100%);
            min-height: 100vh;
            color: #fff;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .container { text-align: center; padding: 40px; max-width: 700px; }
        .logo { font-size: 80px; margin-bottom: 10px; animation: float 3s ease-in-out infinite; }
        @keyframes float {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-15px); }
        }
        h1 {
            font-size: 48px;
            background: linear-gradient(90deg, #ff6b6b, #ffd93d, #6bcb77, #4d96ff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 15px;
        }
        .subtitle { font-size: 18px; color: #aaa; margin-bottom: 30px; }
        .features {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 15px;
            margin: 30px 0;
        }
        .feature {
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 15px;
            border: 1px solid rgba(255,255,255,0.08);
            transition: 0.3s;
        }
        .feature:hover {
            background: rgba(255,255,255,0.1);
            transform: translateY(-3px);
            border-color: rgba(77, 150, 255, 0.3);
        }
        .feature .icon { font-size: 32px; }
        .feature .label { font-size: 13px; margin-top: 5px; color: #ccc; }
        .btn {
            display: inline-block;
            padding: 16px 48px;
            font-size: 18px;
            background: linear-gradient(90deg, #6b46c1, #4d96ff);
            color: #fff;
            border: none;
            border-radius: 30px;
            cursor: pointer;
            text-decoration: none;
            transition: 0.3s;
            font-weight: 600;
        }
        .btn:hover {
            transform: scale(1.05);
            box-shadow: 0 0 40px rgba(77, 150, 255, 0.3);
        }
        .status { margin-top: 20px; color: #6bcb77; font-size: 14px; }
        .status .dot {
            display: inline-block;
            width: 10px;
            height: 10px;
            background: #6bcb77;
            border-radius: 50%;
            margin-right: 8px;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }
        .footer { margin-top: 40px; color: #555; font-size: 13px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">🧠</div>
        <h1>AWESOME AI 2026</h1>
        <p class="subtitle">Самый мощный ИИ-ассистент нового поколения</p>
        <div class="features">
            <div class="feature"><div class="icon">🔍</div><div class="label">Поиск</div></div>
            <div class="feature"><div class="icon">🧮</div><div class="label">Математика</div></div>
            <div class="feature"><div class="icon">🌤</div><div class="label">Погода</div></div>
            <div class="feature"><div class="icon">💵</div><div class="label">Курсы</div></div>
            <div class="feature"><div class="icon">🎨</div><div class="label">Генерация</div></div>
            <div class="feature"><div class="icon">💎</div><div class="label">Premium</div></div>
        </div>
        <a href="/chat" class="btn">🚀 Начать общение</a>
        <div class="status"><span class="dot"></span>Бот онлайн</div>
        <div class="footer">AWESOME AI 2026 &copy;</div>
    </div>
</body>
</html>
'''

CHAT_HTML = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AWESOME AI - Чат</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', sans-serif;
            background: #0a0a0f;
            color: #fff;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .header {
            padding: 15px 20px;
            background: rgba(255,255,255,0.03);
            border-bottom: 1px solid rgba(255,255,255,0.06);
            display: flex;
            align-items: center;
            gap: 12px;
            flex-shrink: 0;
        }
        .header .logo { font-size: 28px; }
        .header h2 {
            font-size: 18px;
            font-weight: 600;
            background: linear-gradient(90deg, #ff6b6b, #ffd93d);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .header .status { margin-left: auto; font-size: 12px; color: #6bcb77; }
        .header .status .dot {
            display: inline-block;
            width: 8px;
            height: 8px;
            background: #6bcb77;
            border-radius: 50%;
            margin-right: 5px;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }
        .header .back-btn { color: #888; text-decoration: none; font-size: 14px; transition: 0.3s; }
        .header .back-btn:hover { color: #fff; }
        .messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        .messages .msg {
            max-width: 75%;
            padding: 12px 18px;
            border-radius: 16px;
            animation: fadeIn 0.3s ease;
            word-wrap: break-word;
            line-height: 1.6;
        }
        .messages .msg.user {
            align-self: flex-end;
            background: linear-gradient(135deg, #4d96ff, #6b46c1);
            border-bottom-right-radius: 4px;
        }
        .messages .msg.bot {
            align-self: flex-start;
            background: rgba(255,255,255,0.07);
            border-bottom-left-radius: 4px;
        }
        .messages .msg .time {
            font-size: 10px;
            opacity: 0.5;
            margin-top: 5px;
            display: block;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .typing {
            align-self: flex-start;
            padding: 10px 16px;
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            font-size: 14px;
            color: #888;
            display: none;
        }
        .typing .dots::after { content: '...'; animation: dots 1.5s infinite; }
        @keyframes dots {
            0%, 20% { content: '.'; }
            40%, 60% { content: '..'; }
            80%, 100% { content: '...'; }
        }
        .input-area {
            padding: 15px 20px;
            background: rgba(255,255,255,0.03);
            border-top: 1px solid rgba(255,255,255,0.06);
            display: flex;
            gap: 10px;
            flex-shrink: 0;
        }
        .input-area input {
            flex: 1;
            padding: 12px 18px;
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 25px;
            background: rgba(255,255,255,0.05);
            color: #fff;
            font-size: 15px;
            outline: none;
            transition: 0.3s;
        }
        .input-area input:focus {
            border-color: #4d96ff;
            background: rgba(255,255,255,0.08);
        }
        .input-area input::placeholder { color: #666; }
        .input-area button {
            padding: 12px 28px;
            border: none;
            border-radius: 25px;
            background: linear-gradient(90deg, #4d96ff, #6b46c1);
            color: #fff;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            transition: 0.3s;
            white-space: nowrap;
        }
        .input-area button:hover {
            transform: scale(1.03);
            box-shadow: 0 0 25px rgba(77, 150, 255, 0.3);
        }
        .input-area button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none !important;
        }
        .input-area .clear-btn {
            background: rgba(255,50,50,0.15);
            padding: 12px 16px;
            font-size: 18px;
        }
        .input-area .clear-btn:hover {
            background: rgba(255,50,50,0.3);
            box-shadow: none;
        }
        .user-info {
            font-size: 11px;
            color: #444;
            padding: 5px 20px;
            text-align: right;
            border-top: 1px solid rgba(255,255,255,0.03);
        }
        @media (max-width: 600px) {
            .messages .msg { max-width: 90%; font-size: 14px; }
            .input-area input { font-size: 14px; }
            .input-area button { padding: 10px 16px; font-size: 13px; }
            .header h2 { font-size: 15px; }
        }
        .messages::-webkit-scrollbar { width: 4px; }
        .messages::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.15); border-radius: 2px; }
    </style>
</head>
<body>
    <div class="header">
        <span class="logo">🧠</span>
        <a href="/" class="back-btn">← Назад</a>
        <h2>AWESOME AI</h2>
        <div class="status"><span class="dot"></span>online</div>
    </div>
    <div class="messages" id="messages">
        <div class="msg bot">
            👋 Привет! Я AWESOME AI 2026.<br>Задай любой вопрос!
            <span class="time">только что</span>
        </div>
        <div class="typing" id="typing"><span class="dots">печатает</span></div>
    </div>
    <div class="input-area">
        <input type="text" id="input" placeholder="Спроси..." autofocus>
        <button id="sendBtn">Отправить</button>
        <button class="clear-btn" id="clearBtn">🗑</button>
    </div>
    <div class="user-info" id="userInfo">🔑 ID: гостевой</div>
    <script>
        let userId = localStorage.getItem('awesome_user_id');
        if (!userId) { userId = Date.now() % 10000000; localStorage.setItem('awesome_user_id', userId); }
        document.getElementById('userInfo').textContent = '🔑 ID: ' + userId;
        const messages = document.getElementById('messages');
        const input = document.getElementById('input');
        const sendBtn = document.getElementById('sendBtn');
        const clearBtn = document.getElementById('clearBtn');
        const typing = document.getElementById('typing');
        function addMessage(text, sender) {
            const div = document.createElement('div');
            div.className = 'msg ' + sender;
            div.innerHTML = text.replace(/\\n/g, '<br>');
            const time = document.createElement('span');
            time.className = 'time';
            time.textContent = new Date().toLocaleTimeString('ru-RU');
            div.appendChild(time);
            messages.insertBefore(div, typing);
            messages.scrollTop = messages.scrollHeight;
        }
        function showTyping() { typing.style.display = 'block'; messages.scrollTop = messages.scrollHeight; }
        function hideTyping() { typing.style.display = 'none'; }
        async function sendMessage() {
            const text = input.value.trim();
            if (!text) return;
            input.value = '';
            sendBtn.disabled = true;
            addMessage(text, 'user');
            showTyping();
            try {
                const response = await fetch('/api/message', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: text, user_id: parseInt(userId), username: 'web_user' })
                });
                hideTyping();
                const data = await response.json();
                if (response.status === 429) addMessage('🔴 ' + data.error, 'bot');
                else if (data.error) addMessage('❌ ' + data.error, 'bot');
                else addMessage(data.response, 'bot');
            } catch (err) {
                hideTyping();
                addMessage('❌ Ошибка соединения', 'bot');
            }
            sendBtn.disabled = false;
            input.focus();
        }
        input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } });
        sendBtn.addEventListener('click', sendMessage);
        clearBtn.addEventListener('click', () => {
            document.querySelectorAll('.msg').forEach(m => m.remove());
            addMessage('🧹 Очищено', 'bot');
        });
        fetch('/api/status').then(r => r.json()).then(d => console.log('✅ Online', d)).catch(e => console.error(e));
    </script>
</body>
</html>
'''

# ============================================================
# FLASK РОУТЫ
# ============================================================

@app.route('/')
def index():
    return render_template_string(INDEX_HTML)

@app.route('/chat')
def chat():
    return render_template_string(CHAT_HTML)

@app.route('/api/message', methods=['POST'])
def api_message():
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({'error': 'Нет сообщения'}), 400
        
        user_text = data['message'].strip()
        if not user_text:
            return jsonify({'error': 'Пустое сообщение'}), 400
        
        user_id = data.get('user_id', int(time.time() * 1000) % 10000000)
        username = data.get('username', 'web_user')
        
        ensure_user(user_id, username)
        
        if not can_send_message(user_id):
            return jsonify({'error': '🔴 Лимит! Купи Premium.', 'limit_reached': True}), 429
        
        response = process_message(user_id, user_text)
        increment_messages(user_id)
        save_message_history(user_id, user_text, response)
        
        return jsonify({
            'response': response,
            'timestamp': get_moscow_time().isoformat(),
            'user_id': user_id
        })
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/status', methods=['GET'])
def api_status():
    return jsonify({
        'status': 'online',
        'time': get_moscow_time().isoformat(),
        'date': get_current_date(),
        'sources': ['Google', 'Wikipedia', 'YouTube', 'Новости'],
        'ai': ['GigaChat', 'YandexGPT']
    })

@app.route('/api/user/<int:user_id>', methods=['GET'])
def api_user(user_id):
    user_data = get_db_user(user_id)
    if not user_data:
        return jsonify({'error': 'Пользователь не найден'}), 404
    return jsonify({
        'user_id': user_id,
        'username': user_data.get('username', 'unknown'),
        'premium': get_premium_status(user_id),
        'premium_expires': get_premium_expires(user_id),
        'messages_today': user_data.get('messages_today', 0),
        'joined_at': user_data.get('joined_at'),
        'is_admin': is_admin(user_id)
    })

@app.route('/api/stats', methods=['GET'])
def api_stats():
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM users')
        total = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM users WHERE premium = 1')
        premium = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1')
        admin = c.fetchone()[0]
        conn.close()
        return jsonify({'total_users': total, 'premium_users': premium, 'admin_users': admin})
    except:
        return jsonify({'error': 'Ошибка'}), 500

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'timestamp': time.time()})

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({'error': 'Server error'}), 500

# ============================================================
# KEEP-ALIVE
# ============================================================
def keep_alive():
    while True:
        time.sleep(300)
        try:
            print("💓 Keep-alive пинг")
        except:
            pass

keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
keep_alive_thread.start()

# ============================================================
# ЗАПУСК
# ============================================================
init_db()

print("=" * 60)
print("🧠 AWESOME AI 2026 — ВЕБ-САЙТ ЗАПУЩЕН!")
print("=" * 60)
print("🌐 ИСТОЧНИКИ:")
print("✅ Google")
print("✅ Wikipedia")
print("✅ YouTube")
print("✅ Новости")
print("✅ GigaChat (ОСНОВНОЙ)")
print("✅ YandexGPT (БАЗА)")
print("=" * 60)
print("🚀 САЙТ ГОТОВ К РАБОТЕ!")
print("=" * 60)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    debug = os.getenv("DEBUG", "True").lower() == "true"
    print(f"🌐 САЙТ: http://0.0.0.0:{port}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=debu
