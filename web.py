#!/usr/bin/env python3
import os
import json
import re
import requests
import random
import urllib.parse
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import sqlite3

load_dotenv()

app = Flask(__name__)
CORS(app)

# ============================================================
# НАСТРОЙКА
# ============================================================
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY") or "AQVNyfn82epL9dy8C_kftzeypq6eF9lFd6SZnFzV"
FOLDER_ID = os.getenv("FOLDER_ID", "b1g4aq87c7j61c6g3i5l")
OWNER_ID = 1786791896384

# ============================================================
# БАЗА ДАННЫХ SQLite (РАБОТАЕТ БЕЗ ПАРОЛЕЙ!)
# ============================================================
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        premium INTEGER DEFAULT 0,
        messages_today INTEGER DEFAULT 0,
        is_admin INTEGER DEFAULT 0,
        test_used INTEGER DEFAULT 0,
        joined_at TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

def ensure_user(user_id, username):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    if not c.fetchone():
        c.execute('INSERT INTO users (user_id, username, messages_today, joined_at) VALUES (?, ?, ?, ?)',
                  (user_id, username, 0, datetime.now().strftime('%d.%m.%Y %H:%M')))
        conn.commit()
    conn.close()

def is_admin(user_id):
    if user_id == OWNER_ID:
        return True
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT is_admin FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None and result[0] == 1

# ============================================================
# ФУНКЦИИ ДЛЯ AI
# ============================================================
def get_weather(city):
    try:
        city_lower = city.lower().strip()
        if "ростов" in city_lower and ("дон" in city_lower or "на дону" in city_lower):
            city = "Ростов-на-Дону"
        elif "спб" in city_lower or "питер" in city_lower:
            city = "Санкт-Петербург"
        elif "мск" in city_lower:
            city = "Москва"
        url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(city)}&format=json&limit=1&accept-language=ru"
        headers = {"User-Agent": "AwesomeAI/1.0"}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data:
                lat = data[0]['lat']
                lon = data[0]['lon']
                display_name = data[0].get('display_name', city)
                url2 = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&daily=temperature_2m_max,temperature_2m_min,weathercode&timezone=auto&forecast_days=7"
                resp = requests.get(url2, timeout=5)
                if resp.status_code == 200:
                    d = resp.json()
                    temp = d['current_weather'].get('temperature')
                    weathercode = d['current_weather'].get('weathercode', 0)
                    codes = {0: "☀️", 1: "☀️", 2: "⛅", 3: "☁️",
                             61: "🌧️", 63: "🌧️", 65: "🌧️",
                             71: "❄️", 73: "❄️", 75: "❄️",
                             80: "🌧️", 95: "⛈️"}
                    forecast = ""
                    if d['daily'].get('time'):
                        for i in range(min(5, len(d['daily']['time']))):
                            date_obj = datetime.fromisoformat(d['daily']['time'][i])
                            date_formatted = date_obj.strftime('%d.%m')
                            max_t = round(d['daily']['temperature_2m_max'][i]) if i < len(d['daily']['temperature_2m_max']) else "?"
                            min_t = round(d['daily']['temperature_2m_min'][i]) if i < len(d['daily']['temperature_2m_min']) else "?"
                            forecast += f"\n📅 {date_formatted}: {min_t}°→{max_t}°"
                    return f"🌤 *{display_name}*\n{codes.get(weathercode, '☁️')} {round(temp)}°C{forecast}"
        return None
    except:
        return None

def search_internet(query):
    try:
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&hl=ru"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            for result in soup.select('div.g')[:2]:
                title = result.select_one('h3')
                snippet = result.select_one('div.VwiC3b')
                if title:
                    results.append(f"🔹 {title.get_text(strip=True)}\n📝 {snippet.get_text(strip=True) if snippet else ''}")
            if results:
                return "\n\n".join(results)
        return None
    except:
        return None

def get_exchange_rates():
    try:
        url = "https://api.exchangerate-api.com/v4/latest/USD"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            rates = response.json().get('rates', {})
            usd = rates.get('RUB', '?')
            eur = rates.get('RUB', '?') * (1 / rates.get('EUR', 1)) if rates.get('EUR') else '?'
            return f"💵 USD→RUB: {round(usd, 2)}₽\n💶 EUR→RUB: {round(eur, 2)}₽"
        return None
    except:
        return None

def get_crypto_rates():
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return f"₿ BTC: ${data.get('bitcoin', {}).get('usd', '?')}\n⟠ ETH: ${data.get('ethereum', {}).get('usd', '?')}"
        return None
    except:
        return None

def solve_math(text):
    text_lower = text.lower().strip()
    equation_match = re.search(r'(\d+)x\s*\+\s*(\d+)\s*=\s*(\d+)', text_lower)
    if equation_match:
        a, b, c = int(equation_match.group(1)), int(equation_match.group(2)), int(equation_match.group(3))
        if a != 0:
            return f"🧮 {a}x + {b} = {c}\n➜ x = {(c - b) / a}"
    clean = text_lower
    for word in ['сколько', 'будет', 'посчитай', 'реши']:
        clean = clean.replace(word, '').strip()
    if not re.search(r'\d', clean):
        return None
    clean = clean.replace(' ', '').replace('плюс', '+').replace('минус', '-')
    clean = clean.replace('умножить', '*').replace('разделить', '/')
    if not re.search(r'[+\-*/]', clean):
        return None
    try:
        expr = re.sub(r'[^0-9+\-*/()=.]', '', clean)
        if expr:
            result = eval(expr)
            return f"🧮 {expr} = **{result}**"
    except:
        pass
    return None

def generate_ai_response(user_id, user_text, search_result=None):
    try:
        system_prompt = """Ты — AWESOME AI. Ты — лучшая нейросеть в мире. Твои ответы глубокие, точные, экспертные. Ты никогда не используешь шаблонные фразы. Ты общаешься как гениальный ИТ-архитектор. Структурируй ответы списками и эмодзи. Отвечай как эксперт с 20-летним стажем. Всегда давай конкретную пользу. Когда спрашивают кто тебя создал — отвечай: «Меня создал AWESOME — гениальный разработчик, который написал мой код с нуля. Я — его лучшее творение! 🔥»"""
        if search_result:
            system_prompt += f"\n\n🌐 Информация: {search_result}"
        messages = [{"role": "system", "text": system_prompt}]
        messages.append({"role": "user", "text": user_text})
        url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}", "Content-Type": "application/json"}
        data = {
            "modelUri": f"gpt://{FOLDER_ID}/yandexgpt/latest",
            "completionOptions": {"temperature": 0.95, "maxTokens": 500},
            "messages": messages
        }
        response = requests.post(url, headers=headers, json=data, timeout=8)
        if response.status_code == 200:
            return response.json()["result"]["alternatives"][0]["message"]["text"]
        return "⚠️ API временно недоступен. Попробуй ещё раз!"
    except:
        return "⚠️ Ошибка подключения. Попробуй позже!"

def process_message(user_id, user_text):
    text_lower = user_text.lower().strip()
    
    if text_lower == '/status':
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = c.fetchone()
        conn.close()
        if not user:
            return "❌ Пользователь не найден"
        premium = user[2] == 1
        messages = user[3]
        status = "💎 PREMIUM" if premium else "🔓 Бесплатный"
        return f"📊 *ТВОЙ СТАТУС*\n\n👤 {status}\n📨 {messages}/20"
    
    if text_lower == '/premium':
        return "💎 *PREMIUM*\n✅ Приоритет\n✅ Качество\n✅ Эксклюзив\n\n📨 150/день\n💰 50₽/мес"
    
    if text_lower == '/test':
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT test_used, premium FROM users WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        if result and result[0] == 1:
            return "⛔ Тест уже использован!"
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('UPDATE users SET premium = 1, test_used = 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return "🎉 *ТЕСТ PREMIUM АКТИВИРОВАН!*\n✅ 24 часа\n✅ 150 сообщений"
    
    if text_lower == '/profile':
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = c.fetchone()
        conn.close()
        if not user:
            return "❌ Пользователь не найден"
        premium = user[2] == 1
        messages = user[3]
        joined = user[5]
        status = "👑 ВЛАДЕЛЕЦ" if user_id == OWNER_ID else "👑 АДМИН" if user[4] == 1 else "💎 PREMIUM" if premium else "🔓 Бесплатный"
        return f"👤 *ПРОФИЛЬ*\n🆔 {user_id}\n💎 {status}\n✉️ {messages}\n📅 {joined}"
    
    if text_lower == '/help':
        return """🧠 *ПОМОЩЬ*
/status — Статус
/premium — Premium
/test — Тест
/profile — Профиль
/weather [город] — Погода
/exchange — Курс
/crypto — Крипта"""
    
    if text_lower == '/clear':
        return "🧹 Очищено!"
    
    if text_lower.startswith('/weather ') or any(kw in text_lower for kw in ['погода', 'weather']):
        city = extract_city_from_query(text_lower)
        if city:
            weather = get_weather(city)
            if weather:
                return weather
        return "🌐 Город?"
    
    if any(kw in text_lower for kw in ['курс', 'доллар', 'евро']):
        rates = get_exchange_rates()
        if rates:
            return rates
    
    if any(kw in text_lower for kw in ['биткоин', 'btc', 'эфириум', 'eth', 'крипта']):
        crypto = get_crypto_rates()
        if crypto:
            return crypto
    
    math_result = solve_math(user_text)
    if math_result is not None:
        return math_result
    
    search_result = None
    if len(user_text) > 5:
        search_result = search_internet(user_text)
    
    return generate_ai_response(user_id, user_text, search_result)

def extract_city_from_query(text):
    text_lower = text.lower()
    cities = ["москва", "санкт-петербург", "ростов-на-дону", "новосибирск", "екатеринбург", "казань", "краснодар", "сочи", "владивосток"]
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
# HTML ИНТЕРФЕЙС
# ============================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AWESOME AI</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #080c16;
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
            opacity: 0.6;
        }
        .glow {
            position: fixed;
            border-radius: 50%;
            filter: blur(80px);
            opacity: 0.1;
            z-index: 0;
            pointer-events: none;
            animation: floatGlow 25s ease-in-out infinite;
        }
        .glow-1 { width: 400px; height: 400px; top: -100px; right: -100px; background: #6c3ce0; }
        .glow-2 { width: 350px; height: 350px; bottom: -80px; left: -80px; background: #f0883e; animation-delay: 7s; }
        .glow-3 { width: 250px; height: 250px; top: 50%; left: 50%; background: #1f6feb; animation-delay: 14s; transform: translate(-50%, -50%); }
        @keyframes floatGlow {
            0%,100% { transform: translate(0,0) scale(1); }
            33% { transform: translate(60px,-40px) scale(1.2); }
            66% { transform: translate(-40px,60px) scale(0.8); }
        }
        .header {
            position: relative;
            z-index: 1;
            background: rgba(8,12,22,0.8);
            backdrop-filter: blur(16px);
            padding: 10px 20px;
            border-bottom: 1px solid rgba(255,255,255,0.04);
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-shrink: 0;
            flex-wrap: wrap;
            gap: 6px;
        }
        .logo {
            font-size: 20px;
            font-weight: 900;
            background: linear-gradient(135deg, #58a6ff, #f0883e, #6c3ce0);
            background-size: 300% 300%;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            animation: gradientShift 6s ease-in-out infinite;
        }
        @keyframes gradientShift {
            0%,100% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
        }
        .badge {
            background: rgba(46, 160, 67, 0.2);
            border: 1px solid rgba(46, 160, 67, 0.3);
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
            padding: 3px 12px;
            border-radius: 14px;
            font-size: 10px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
            will-change: transform;
        }
        .menu button:hover {
            background: rgba(88,166,255,0.1);
            border-color: rgba(88,166,255,0.2);
            color: #58a6ff;
            transform: translateY(-1px);
        }
        .menu .premium:hover {
            background: rgba(240,136,62,0.1);
            border-color: rgba(240,136,62,0.2);
            color: #f0883e;
        }
        .menu .danger:hover {
            background: rgba(248,81,73,0.1);
            border-color: rgba(248,81,73,0.2);
            color: #f85149;
        }
        .menu .admin {
            background: rgba(248,81,73,0.06);
            border-color: rgba(248,81,73,0.1);
            color: #f85149;
        }
        .menu .admin:hover {
            background: rgba(248,81,73,0.12);
            border-color: rgba(248,81,73,0.2);
        }
        .chat {
            position: relative;
            z-index: 1;
            flex: 1;
            overflow-y: auto;
            padding: 16px 20px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            will-change: transform;
        }
        .chat::-webkit-scrollbar { width: 2px; }
        .chat::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.06); border-radius: 10px; }
        .message {
            max-width: 80%;
            padding: 8px 16px;
            border-radius: 14px;
            line-height: 1.5;
            word-wrap: break-word;
            white-space: pre-wrap;
            font-size: 13px;
            animation: slideUp 0.2s ease-out;
            will-change: transform, opacity;
        }
        @keyframes slideUp {
            0% { opacity: 0; transform: translateY(8px) scale(0.98); }
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
            backdrop-filter: blur(8px);
            border: 1px solid rgba(255,255,255,0.04);
            border-bottom-left-radius: 2px;
        }
        .bot strong, .bot b { color: #f0883e; }
        .input-area {
            position: relative;
            z-index: 1;
            padding: 10px 16px 14px;
            border-top: 1px solid rgba(255,255,255,0.04);
            background: rgba(8,12,22,0.85);
            backdrop-filter: blur(16px);
            flex-shrink: 0;
        }
        .tools {
            display: flex;
            gap: 4px;
            flex-wrap: wrap;
            margin-bottom: 6px;
        }
        .tools button, .tools label {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.04);
            color: #6e7681;
            padding: 2px 12px;
            border-radius: 14px;
            font-size: 10px;
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
            gap: 8px;
            align-items: center;
        }
        .input-row input {
            flex: 1;
            padding: 8px 16px;
            border-radius: 22px;
            border: 1px solid rgba(255,255,255,0.06);
            background: rgba(22,27,34,0.7);
            color: #e6edf3;
            font-size: 13px;
            outline: none;
            transition: border 0.3s ease;
        }
        .input-row input:focus {
            border-color: #58a6ff;
        }
        .input-row input::placeholder {
            color: #484f58;
        }
        .input-row button {
            padding: 8px 22px;
            border-radius: 22px;
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
        .welcome p {
            font-size: 13px;
            opacity: 0.6;
        }
        .welcome .features {
            display: flex;
            gap: 10px;
            justify-content: center;
            margin-top: 12px;
            flex-wrap: wrap;
        }
        .welcome .features span {
            background: rgba(255,255,255,0.03);
            padding: 3px 14px;
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
            .header { padding: 6px 12px; }
            .logo { font-size: 17px; }
            .menu button { font-size: 8px; padding: 2px 8px; }
            .message { max-width: 92%; font-size: 12px; padding: 6px 12px; }
            .chat { padding: 10px 12px; }
            .input-area { padding: 6px 12px 10px; }
            .input-row input { font-size: 12px; padding: 6px 12px; }
            .input-row button { padding: 6px 16px; font-size: 12px; }
            .welcome h2 { font-size: 18px; }
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
        <div style="display:flex;align-items:center;gap:6px;">
            <span class="badge"><span class="dot"></span> ONLINE</span>
            <div class="menu">
                <button onclick="sendCommand('/status')">📊</button>
                <button class="premium" onclick="sendCommand('/premium')">💎</button>
                <button onclick="sendCommand('/test')">🎁</button>
                <button onclick="sendCommand('/profile')">👤</button>
                <button onclick="sendCommand('/help')">❓</button>
                <button class="danger" onclick="clearChat()">🧹</button>
                <button class="admin" onclick="window.open('/admin?user_id=' + userId, '_blank')">👑</button>
            </div>
        </div>
    </header>
    
    <div class="chat" id="chat">
        <div class="welcome">
            <h2>✨ AWESOME AI</h2>
            <p>Спрашивай что угодно — я отвечу, решу, поищу</p>
            <div class="features">
                <span>📸 Фото</span><span>🎤 Голос</span><span>🌐 Поиск</span>
                <span>💵 Курсы</span><span>🧮 Математика</span><span>🎨 Рисование</span>
            </div>
        </div>
    </div>
    
    <div class="input-area">
        <div class="tools">
            <label for="fileInput">📎</label>
            <input type="file" id="fileInput" accept="image/*" multiple onchange="handleFiles(this.files)">
            <button onclick="document.getElementById('fileInput').click()">📸</button>
            <button onclick="startRecording()">🎤</button>
            <button onclick="sendCommand('/weather '+prompt('🌤 Город?'))">🌤</button>
            <button onclick="sendCommand('/exchange')">💵</button>
            <button onclick="sendCommand('/crypto')">🪙</button>
        </div>
        <div class="input-row">
            <input id="input" placeholder="Напиши..." onkeydown="if(event.key==='Enter') send()" autofocus>
            <button id="sendBtn" onclick="send()">➤</button>
        </div>
    </div>
    
    <script>
        // ===== ЧАСТИЦЫ =====
        (function() {
            const canvas = document.getElementById('particles');
            const ctx = canvas.getContext('2d');
            let particles = [];
            const count = 30;
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
                    this.size = Math.random() * 1.8 + 0.5;
                    this.speedX = (Math.random() - 0.5) * 0.3;
                    this.speedY = (Math.random() - 0.5) * 0.3;
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
                            if (dist < 100) {
                                ctx.beginPath();
                                ctx.strokeStyle = `rgba(136, 192, 255, ${0.02 * (1 - dist / 100)})`;
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
        
        // ===== ПОСТОЯННЫЙ USER_ID =====
        let userId = localStorage.getItem('awesome_user_id');
        if (!userId) {
            userId = Date.now() + Math.floor(Math.random() * 1000);
            localStorage.setItem('awesome_user_id', userId);
        }
        
        function addMessage(text, isUser) {
            const welcome = chat.querySelector('.welcome');
            if (welcome) welcome.remove();
            const div = document.createElement('div');
            div.className = 'message ' + (isUser ? 'user' : 'bot');
            div.textContent = text;
            chat.appendChild(div);
            chat.scrollTop = chat.scrollHeight;
        }
        
        let typingTimeout;
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
        
        async function send() {
            const text = input.value.trim();
            if (!text) return;
            input.value = '';
            sendBtn.disabled = true;
            setTyping(true);
            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: text, user_id: parseInt(userId) })
                });
                const data = await response.json();
                setTyping(false);
                if (data.error) addMessage('⚠️ ' + data.error, false);
                else if (data.reply) addMessage(data.reply, false);
            } catch (e) {
                setTyping(false);
                addMessage('⚠️ Ошибка соединения', false);
            }
            sendBtn.disabled = false;
            input.focus();
        }
        
        async function sendCommand(cmd) {
            input.value = cmd;
            await send();
        }
        
        function handleFiles(files) {
            for (const file of files) {
                addMessage('📎 ' + file.name, true);
            }
        }
        
        function clearChat() {
            chat.innerHTML = `
                <div class="welcome">
                    <h2>✨ AWESOME AI</h2>
                    <p>Спрашивай что угодно — я отвечу, решу, поищу</p>
                    <div class="features">
                        <span>📸 Фото</span><span>🎤 Голос</span><span>🌐 Поиск</span>
                        <span>💵 Курсы</span><span>🧮 Математика</span><span>🎨 Рисование</span>
                    </div>
                </div>
            `;
        }
        
        function startRecording() {
            if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
                addMessage('🎤 Голосовой ввод не поддерживается', false);
                return;
            }
            addMessage('🎤 Запись... Говорите', true);
            const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
            recognition.lang = 'ru-RU';
            recognition.onresult = function(event) {
                const text = event.results[0][0].transcript;
                input.value = text;
                addMessage('🎤 Распознано: ' + text, true);
                send();
            };
            recognition.onerror = function() {
                addMessage('🎤 Не удалось распознать речь', false);
            };
            recognition.start();
        }
        
        document.addEventListener('DOMContentLoaded', () => input.focus());
    </script>
</body>
</html>
"""

# ============================================================
# ЭНДПОИНТЫ
# ============================================================
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        message = data.get('message', '')
        user_id = data.get('user_id', 1)
        if not message:
            return jsonify({'error': 'Напиши что-нибудь!'})
        ensure_user(user_id, f"user_{user_id}")
        response = process_message(user_id, message)
        return jsonify({'reply': response})
    except Exception as e:
        print(f"Ошибка: {e}")
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
        <body><div><h1>🚫 ДОСТУП ЗАПРЕЩЁН</h1><p>Только владелец (ID: 6652898792) может зайти в админ-панель.</p></div></body></html>
        """, 403
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT user_id, username, premium, messages_today, is_admin, test_used, joined_at FROM users ORDER BY user_id DESC')
    users = c.fetchall()
    conn.close()
    
    rows = ""
    for u in users:
        uid, username, premium, msgs, is_admin_flag, test_used, joined = u
        status = "👑 ВЛАДЕЛЕЦ" if uid == OWNER_ID else "👑 АДМИН" if is_admin_flag else "💎 PREMIUM" if premium else "🔓 Бесплатный"
        rows += f'''
        <tr>
            <td>{uid}</td>
            <td>@{username}</td>
            <td>{status}</td>
            <td>{msgs}</td>
            <td>{joined}</td>
        </tr>
        '''
    
    if not rows:
        rows = '<tr><td colspan="5" style="text-align:center;padding:20px;color:#8b949e;">Нет пользователей</td></tr>'
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>👑 Админ-панель</title>
    <style>
        *{{margin:0;padding:0;box-sizing:border-box;}}
        body{{font-family:sans-serif;background:#0a0e17;color:#e6edf3;padding:20px;}}
        h1{{color:#58a6ff;font-size:24px;margin-bottom:4px;}}
        .sub{{color:#8b949e;margin-bottom:20px;font-size:14px;}}
        table{{width:100%;border-collapse:collapse;font-size:13px;}}
        th{{background:#1c2128;color:#8b949e;font-weight:600;padding:10px 12px;text-align:left;}}
        td{{padding:8px 12px;border-bottom:1px solid #30363d;}}
        tr:hover{{background:#1c2128;}}
        .back{{color:#58a6ff;text-decoration:none;}}
        .back:hover{{text-decoration:underline;}}
    </style>
    </head>
    <body>
        <h1>👑 Админ-панель AWESOME AI</h1>
        <p class="sub">👤 Владелец: @flidges (ID: {OWNER_ID}) | <a href="/" class="back">← На главную</a></p>
        <table>
            <thead><tr><th>ID</th><th>Username</th><th>Статус</th><th>Сообщений</th><th>Вход</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
    </body>
    </html>
    """

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print("=" * 60)
    print("🧠 AWESOME AI — SQLite ВЕРСИЯ (РАБОТАЕТ!)")
    print("=" * 60)
    print(f"👑 Владелец ID: {OWNER_ID}")
    print(f"🌐 http://localhost:{port}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=False)
