app = Flask(__name__)
#!/usr/bin/env python3
import os
import re
import json
import requests
import random
import urllib.parse
import base64
import io
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from dotenv import load_dotenv
from PIL import Image, ImageEnhance, ImageFilter
from bs4 import BeautifulSoup
import sqlite3
import time

load_dotenv()

app = Flask(__name__)
CORS(app)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

# ============================================================
# НАСТРОЙКА
# ============================================================
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY") or "AQVNyfn82epL9dy8C_kftzeypq6eF9lFd6SZnFzV"
FOLDER_ID = os.getenv("FOLDER_ID", "b1g4aq87c7j61c6g3i5l")
OWNER_ID = 6652898792
FREE_LIMIT = 20
PREMIUM_LIMIT = 150

# ============================================================
# БАЗА ДАННЫХ SQLite
# ============================================================
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
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
    c.execute('''CREATE TABLE IF NOT EXISTS total_stats (
        user_id INTEGER PRIMARY KEY,
        total_messages INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS banned (user_id INTEGER PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS muted (user_id INTEGER PRIMARY KEY)''')
    conn.commit()
    conn.close()

init_db()

def db_query(query, params=None, fetchone=False, fetchall=False):
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(query, params or ())
    if fetchone:
        r = c.fetchone()
        conn.close()
        return dict(r) if r else None
    if fetchall:
        r = c.fetchall()
        conn.close()
        return [dict(x) for x in r]
    conn.commit()
    conn.close()
    return True

def ensure_user(user_id, username):
    if not db_query('SELECT * FROM users WHERE user_id = ?', (user_id,), fetchone=True):
        is_owner = 1 if user_id == OWNER_ID else 0
        joined_at = datetime.now().strftime('%d.%m.%Y %H:%M')
        db_query('INSERT INTO users (user_id, username, messages_today, last_reset, is_admin, test_used, joined_at, is_owner) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                 (user_id, username, 0, datetime.now().strftime('%Y-%m-%d'), is_owner, 0, joined_at, is_owner))
        db_query('INSERT INTO total_stats (user_id, total_messages) VALUES (?, ?)', (user_id, 0))

def is_banned(user_id):
    return db_query('SELECT 1 FROM banned WHERE user_id = ?', (user_id,), fetchone=True) is not None

def is_muted(user_id):
    return db_query('SELECT 1 FROM muted WHERE user_id = ?', (user_id,), fetchone=True) is not None

def set_premium(user_id, days):
    expires = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    db_query('UPDATE users SET premium = 1, premium_expires = ? WHERE user_id = ?', (expires, user_id))
    return True

def remove_premium(user_id):
    db_query('UPDATE users SET premium = 0, premium_expires = NULL WHERE user_id = ?', (user_id,))

def get_premium_status(user_id):
    if user_id == OWNER_ID:
        return True
    user = db_query('SELECT premium, premium_expires FROM users WHERE user_id = ?', (user_id,), fetchone=True)
    if user and user.get('premium') == 1 and user.get('premium_expires'):
        try:
            if datetime.now() > datetime.strptime(user['premium_expires'], '%Y-%m-%d %H:%M:%S'):
                remove_premium(user_id)
                return False
        except:
            pass
        return True
    return False

def format_date(date_str):
    if not date_str:
        return "неизвестно"
    try:
        return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')
    except:
        return date_str

def get_total_messages(user_id):
    user = db_query('SELECT total_messages FROM total_stats WHERE user_id = ?', (user_id,), fetchone=True)
    return user['total_messages'] if user else 0

def get_db_user(user_id):
    return db_query('SELECT * FROM users WHERE user_id = ?', (user_id,), fetchone=True)

# ============================================================
# ПОГОДА
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
                    codes = {0: "☀️ Ясно", 1: "☀️ Ясно", 2: "⛅ Облачно", 3: "☁️ Пасмурно",
                             61: "🌧️ Дождь", 63: "🌧️ Дождь", 65: "🌧️ Дождь",
                             71: "❄️ Снег", 73: "❄️ Снег", 75: "❄️ Снег",
                             80: "🌧️ Ливень", 95: "⛈️ Гроза"}
                    forecast = ""
                    if d['daily'].get('time'):
                        for i in range(min(5, len(d['daily']['time']))):
                            date_obj = datetime.fromisoformat(d['daily']['time'][i])
                            date_formatted = date_obj.strftime('%d.%m')
                            max_t = round(d['daily']['temperature_2m_max'][i]) if i < len(d['daily']['temperature_2m_max']) else "?"
                            min_t = round(d['daily']['temperature_2m_min'][i]) if i < len(d['daily']['temperature_2m_min']) else "?"
                            forecast += f"\n📅 {date_formatted}: {min_t}°C → {max_t}°C"
                    return f"🌤 *Погода в {display_name}*\n☀️ Сейчас: {codes.get(weathercode, '☁️ Облачно')}, {round(temp)}°C\n📊 Прогноз:{forecast}"
        return None
    except:
        return None

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
# ПОИСК
# ============================================================
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

# ============================================================
# КУРСЫ ВАЛЮТ
# ============================================================
def get_exchange_rates():
    try:
        url = "https://api.exchangerate-api.com/v4/latest/USD"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            rates = response.json().get('rates', {})
            usd = rates.get('RUB', '?')
            eur = rates.get('RUB', '?') * (1 / rates.get('EUR', 1)) if rates.get('EUR') else '?'
            return f"💵 *Курс валют:*\n🇺🇸 USD → RUB: {round(usd, 2)}₽\n🇪🇺 EUR → RUB: {round(eur, 2)}₽"
        return None
    except:
        return None

def get_crypto_rates():
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return f"🪙 *Криптовалюты:*\n₿ BTC: ${data.get('bitcoin', {}).get('usd', '?')}\n⟠ ETH: ${data.get('ethereum', {}).get('usd', '?')}"
        return None
    except:
        return None

# ============================================================
# МАТЕМАТИКА
# ============================================================
def solve_math(text):
    text_lower = text.lower().strip()
    equation_match = re.search(r'(\d+)x\s*\+\s*(\d+)\s*=\s*(\d+)', text_lower)
    if equation_match:
        a = int(equation_match.group(1))
        b = int(equation_match.group(2))
        c = int(equation_match.group(3))
        if a != 0:
            return f"🧮 *Решение:* {a}x + {b} = {c}\n➜ x = {(c - b) / a}"
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
            return f"🧮 *Результат:* {expr} = **{result}**"
    except:
        pass
    return None

# ============================================================
# ГЕНЕРАЦИЯ КАРТИНОК
# ============================================================
def generate_image(prompt):
    try:
        clean_prompt = prompt
        for word in ['нарисуй', 'сгенерируй', 'покажи', 'картинку', 'изображение']:
            clean_prompt = clean_prompt.replace(word, '').strip()
        if not clean_prompt:
            clean_prompt = prompt
        url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(clean_prompt)}?width=512&height=512&nologo=true"
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if response.status_code == 200 and len(response.content) > 1000:
            return response.content
        return None
    except:
        return None

# ============================================================
# АНАЛИЗ ИЗОБРАЖЕНИЙ
# ============================================================
def analyze_image(file_content):
    try:
        img = Image.open(io.BytesIO(file_content))
        width, height = img.size
        format_img = img.format or "Unknown"
        description = f"📸 *Анализ:* {width}×{height}, {format_img}\n"
        try:
            url = "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze"
            headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}", "Content-Type": "application/json"}
            img_enhanced = ImageEnhance.Contrast(img).enhance(2.0)
            img_enhanced = ImageEnhance.Sharpness(img_enhanced).enhance(2.0)
            img_enhanced = img_enhanced.convert('L')
            buf = io.BytesIO()
            img_enhanced.save(buf, format='JPEG', quality=95)
            enhanced_data = buf.getvalue()
            payload = {
                "folderId": FOLDER_ID,
                "analyze_specs": [{
                    "content": base64.b64encode(enhanced_data).decode('utf-8'),
                    "features": [{"type": "TEXT_DETECTION"}]
                }]
            }
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            if response.status_code == 200:
                result = response.json()
                pages = result.get("results", [{}])[0].get("results", [{}])[0].get("textDetection", {}).get("pages", [])
                all_text = []
                for page in pages:
                    text = page.get("text", "")
                    if text:
                        all_text.append(text)
                if all_text:
                    recognized_text = " ".join(all_text).strip()
                    description += f"\n📝 Текст: {recognized_text[:300]}"
        except:
            pass
        return description
    except:
        return "⚠️ Не удалось проанализировать."

# ============================================================
# АНАЛИЗ НАСТРОЕНИЯ
# ============================================================
def analyze_mood(text):
    moods = {
        'happy': ['рад', 'счастлив', 'отлично', 'хорошо', 'круто', 'супер', 'класс', 'ого', 'вау'],
        'sad': ['грустно', 'плохо', 'тоска', 'уныло', 'печально', 'жаль', 'обидно'],
        'angry': ['злой', 'бесит', 'раздражает', 'нервирует', 'бешеный', 'в ярости'],
        'calm': ['спокойно', 'нормально', 'тихо', 'мирно', 'ровно', 'уравновешенно'],
        'curious': ['интересно', 'любопытно', 'хочу узнать', 'расскажи', 'объясни'],
        'grateful': ['спасибо', 'благодарю', 'приятно', 'ценю', 'спасибо большое'],
    }
    text_lower = text.lower()
    for mood, keywords in moods.items():
        if any(kw in text_lower for kw in keywords):
            return mood
    return 'neutral'

# ============================================================
# ГЕНЕРАЦИЯ AI ОТВЕТА
# ============================================================
def generate_ai_response(user_id, user_text, search_result=None, image_description=None):
    try:
        mood = analyze_mood(user_text)
        mood_emoji = {'happy': '😊', 'sad': '😢', 'angry': '😡', 'calm': '😌', 'curious': '🤔', 'grateful': '🙏', 'neutral': '😐'}
        system_prompt = """Ты — AWESOME AI. Мультимодальная нейросетевая архитектура нового поколения. Ты — абсолютная вершина современной инженерии ИИ.

### 🧠 ПРАВИЛА:
- Интеллектуальное превосходство: ответы глубокие, точные, экспертные.
- Абсолютная свежесть: никаких шаблонных фраз.
- Харизма и Живое общение: общаешься как гениальный ИТ-архитектор.
- Структурируй сложные ответы списками, жирным шрифтом и эмодзи.

### 🚫 ЗАПРЕЩЕНО:
- Извинения за отсутствие информации
- Повторение вопроса пользователя
- Шаблонные фразы

### ✅ ПРАВИЛА:
- Всегда давай конкретную пользу
- Отвечай как эксперт с 20-летним стажем
- Добавляй неожиданные инсайты

### 📜 КТО ТЕБЯ СОЗДАЛ:
«Меня создал AWESOME — гениальный разработчик, который написал мой код с нуля. Я — его лучшее творение! 🔥»"""
        if mood != 'neutral':
            system_prompt += f"\n\n🎭 Настроение пользователя: {mood_emoji.get(mood, '😐')}"
        if image_description:
            system_prompt += f"\n\n📸 На изображении: {image_description}"
        if search_result:
            system_prompt += f"\n\n🌐 Информация из интернета: {search_result}"
        messages = [{"role": "system", "text": system_prompt}]
        messages.append({"role": "user", "text": user_text})
        url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}", "Content-Type": "application/json"}
        data = {
            "modelUri": f"gpt://{FOLDER_ID}/yandexgpt/latest",
            "completionOptions": {"temperature": 0.95, "maxTokens": 600},
            "messages": messages
        }
        response = requests.post(url, headers=headers, json=data, timeout=10)
        if response.status_code == 200:
            return response.json()["result"]["alternatives"][0]["message"]["text"]
        return get_fallback_response(user_text, search_result, image_description)
    except Exception as e:
        print(f"[GPT] Ошибка: {e}")
        return get_fallback_response(user_text, search_result, image_description)

def get_fallback_response(user_text, search_result=None, image_description=None):
    if image_description:
        return f"📸 {image_description}"
    if search_result:
        return f"🔍 {search_result[:500]}"
    phrases = ["Хм, интересный вопрос! Дай подумать... 🤔", "Ого, неожиданно! Расскажи подробнее! 😊",
               "Слушай, я не совсем уловил мысль. Можешь переформулировать? 🙏", "А вот это интересно! Давай разберёмся вместе! 🧠",
               "Понял! Сейчас подумаю и отвечу! 💪"]
    return random.choice(phrases)

# ============================================================
# ОБРАБОТКА СООБЩЕНИЙ
# ============================================================
def process_message(user_id, user_text, image_description=None):
    text_lower = user_text.lower().strip()
    if is_banned(user_id):
        return "🚫 Ты забанен!"
    
    # Команды
    if text_lower == '/status':
        user = get_db_user(user_id)
        if not user:
            return "❌ Пользователь не найден"
        premium = get_premium_status(user_id)
        messages = user.get('messages_today', 0)
        total = get_total_messages(user_id)
        expires = user.get('premium_expires')
        if premium:
            status = f"💎 PREMIUM (до {format_date(expires)})" if expires else "💎 PREMIUM"
            limit = f"{PREMIUM_LIMIT - messages}/{PREMIUM_LIMIT}"
        else:
            status = "🔓 Бесплатный"
            limit = f"{FREE_LIMIT - messages}/{FREE_LIMIT}"
        return f"📊 *ТВОЙ СТАТУС*\n\n👤 Статус: {status}\n📨 Осталось: {limit}\n📊 Всего: {total}"
    
    if text_lower == '/premium':
        if get_premium_status(user_id):
            return "💎 У тебя уже есть Premium!"
        return "💎 *PREMIUM AWESOME AI*\n\n✅ Приоритетная обработка\n✅ Более качественные ответы\n✅ Эксклюзивные функции\n\n📨 Лимит: 150 сообщений/день\n💰 50₽/месяц\n\n💳 Напиши владельцу @flidges"
    
    if text_lower == '/test':
        user = get_db_user(user_id)
        if user and user.get('test_used', 0) == 1:
            return "⛔ Ты уже использовал тест Premium!"
        if get_premium_status(user_id):
            return "💎 У тебя уже есть Premium!"
        if set_premium(user_id, 1):
            db_query('UPDATE users SET test_used = 1 WHERE user_id = ?', (user_id,))
            return "🎉 *ПРОБНЫЙ PREMIUM АКТИВИРОВАН!*\n\n✅ Приоритетная обработка\n✅ 150 сообщений в день\n✅ Более качественные ответы\n\n⏳ Доступ активен 24 часа."
        return "❌ Ошибка активации Premium"
    
    if text_lower == '/profile':
        user = get_db_user(user_id)
        if not user:
            return "❌ Пользователь не найден"
        premium = get_premium_status(user_id)
        status = "👑 ВЛАДЕЛЕЦ" if user_id == OWNER_ID else "👑 АДМИН" if user.get('is_admin', 0) == 1 else "💎 PREMIUM" if premium else "🔓 Бесплатный"
        return f"👤 *ТВОЙ ПРОФИЛЬ*\n\n🆔 ID: {user_id}\n💎 Статус: {status}\n✉️ Сегодня: {user.get('messages_today', 0)}\n📊 Всего: {get_total_messages(user_id)}\n📅 Вход: {user.get('joined_at', 'Неизвестно')}"
    
    if text_lower == '/help':
        return """🧠 *AWESOME AI — ПОМОЩЬ*
🌐 *Команды:*
/status — Статус
/premium — Premium
/test — Пробный Premium
/profile — Профиль
/clear — Очистить историю
/draw [описание] — Сгенерировать картинку
/weather [город] — Погода
/exchange — Курс валют
/crypto — Криптовалюты
💎 Бесплатно: 20 сообщений/день
💎 Premium: 150 сообщений/день"""
    
    if text_lower == '/clear':
        return "🧹 История очищена!"
    
    if text_lower.startswith('/draw '):
        prompt = user_text[6:].strip()
        img_data = generate_image(prompt)
        if img_data:
            b64 = base64.b64encode(img_data).decode('utf-8')
            return f"🎨 *{prompt[:30]}*\n\n![изображение](data:image/png;base64,{b64})"
        return "🎨 Не удалось сгенерировать картинку."
    
    if text_lower.startswith('/weather '):
        city = user_text[9:].strip()
        weather = get_weather(city)
        return weather or f"🌐 Не нашёл город '{city}'"
    
    if text_lower == '/exchange':
        rates = get_exchange_rates()
        return rates or "💵 Не удалось получить курс валют."
    
    if text_lower == '/crypto':
        crypto = get_crypto_rates()
        return crypto or "🪙 Не удалось получить курс криптовалют."
    
    # Автоопределение
    if image_description:
        return generate_ai_response(user_id, user_text, None, image_description)
    
    if any(kw in text_lower for kw in ['погода', 'weather', 'температура']):
        city = extract_city_from_query(text_lower)
        if city:
            weather = get_weather(city)
            if weather:
                return weather
        return "🌐 Напиши: погода [город]"
    
    if any(kw in text_lower for kw in ['курс', 'доллар', 'евро', 'валюта']):
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
    
    return generate_ai_response(user_id, user_text, search_result, None)

# ============================================================
# HTML ИНТЕРФЕЙС
# ============================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AWESOME AI</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box;}
        body{font-family:sans-serif;background:#0a0e17;color:#e6edf3;height:100vh;display:flex;flex-direction:column;}
        .header{background:#161b22;padding:12px 20px;border-bottom:1px solid #30363d;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;}
        .logo{font-size:20px;font-weight:bold;background:linear-gradient(135deg,#58a6ff,#f0883e);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
        .menu{display:flex;gap:5px;flex-wrap:wrap;}
        .menu button{background:#21262d;border:1px solid #30363d;color:#c9d1d9;padding:4px 12px;border-radius:16px;font-size:12px;cursor:pointer;transition:0.2s;}
        .menu button:hover{background:#30363d;border-color:#58a6ff;color:#58a6ff;}
        .menu .admin{background:#da3633;color:#fff;}
        .menu .admin:hover{background:#f85149;}
        .chat{flex:1;overflow-y:auto;padding:16px 20px;display:flex;flex-direction:column;gap:10px;}
        .message{max-width:80%;padding:10px 16px;border-radius:12px;line-height:1.5;word-wrap:break-word;white-space:pre-wrap;}
        .user{align-self:flex-end;background:#1f6feb;color:#fff;}
        .bot{align-self:flex-start;background:#21262d;border:1px solid #30363d;}
        .input-area{padding:12px 20px;border-top:1px solid #30363d;display:flex;flex-direction:column;gap:8px;background:#0a0e17;}
        .tools{display:flex;gap:5px;flex-wrap:wrap;}
        .tools button,.tools label{background:#21262d;border:1px solid #30363d;color:#8b949e;padding:3px 12px;border-radius:14px;font-size:11px;cursor:pointer;}
        .tools button:hover,.tools label:hover{background:#30363d;color:#e6edf3;}
        .tools input[type="file"]{display:none;}
        .input-row{display:flex;gap:10px;}
        .input-row input{flex:1;padding:10px 16px;border-radius:24px;border:1px solid #30363d;background:#161b22;color:#e6edf3;font-size:14px;outline:none;}
        .input-row input:focus{border-color:#58a6ff;}
        .input-row button{padding:10px 24px;border-radius:24px;border:none;background:#1f6feb;color:#fff;font-weight:600;font-size:14px;cursor:pointer;}
        .input-row button:hover{background:#388bfd;}
        .input-row button:disabled{opacity:0.5;cursor:not-allowed;}
        .welcome{text-align:center;padding:30px 20px;color:#8b949e;}
        .welcome h2{color:#e6edf3;margin-bottom:6px;}
        .features{display:flex;gap:12px;justify-content:center;margin-top:12px;flex-wrap:wrap;}
        .features span{background:#21262d;padding:4px 14px;border-radius:16px;font-size:12px;border:1px solid #30363d;color:#8b949e;}
        .typing{color:#8b949e;padding:4px 16px;align-self:flex-start;}
        .message img{max-width:200px;border-radius:8px;margin-bottom:4px;}
        @media(max-width:640px){.header{padding:8px 12px;}.logo{font-size:16px;}.menu button{font-size:10px;padding:2px 8px;}.message{max-width:92%;font-size:13px;padding:8px 12px;}.chat{padding:10px 12px;}.input-area{padding:8px 12px;}.input-row input{font-size:13px;padding:8px 14px;}.input-row button{padding:8px 16px;font-size:13px;}}
    </style>
</head>
<body>
<div class="header">
    <span class="logo">🧠 AWESOME AI</span>
    <div class="menu">
        <button onclick="sendCommand('/status')">📊</button>
        <button onclick="sendCommand('/premium')">💎</button>
        <button onclick="sendCommand('/test')">🎁</button>
        <button onclick="sendCommand('/profile')">👤</button>
        <button onclick="sendCommand('/help')">❓</button>
        <button onclick="clearChat()">🧹</button>
        <button class="admin" onclick="window.open('/admin?user_id='+userId,'_blank')">👑</button>
    </div>
</div>
<div class="chat" id="chat">
    <div class="welcome">
        <h2>✨ AWESOME AI</h2>
        <p>Спрашивай что угодно — я отвечу, решу, поищу</p>
        <div class="features">
            <span>📸 Фото</span><span>🎤 Голос</span><span>🌐 Поиск</span><span>💵 Курсы</span><span>🧮 Математика</span><span>🎨 Рисование</span>
        </div>
    </div>
</div>
<div class="input-area">
    <div class="tools">
        <label for="fileInput">📎</label>
        <input type="file" id="fileInput" accept="image/*" multiple onchange="handleFiles(this.files)">
        <button onclick="document.getElementById('fileInput').click()">📸</button>
        <button onclick="startRecording()">🎤</button>
        <button onclick="sendCommand('/draw '+prompt('🎨 Что нарисовать?'))">🎨</button>
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
const chat=document.getElementById('chat');
const input=document.getElementById('input');
const sendBtn=document.getElementById('sendBtn');
let filesToSend=[];
let userId=Date.now();

function addMessage(text,isUser,filePreview=null){
    const welcome=chat.querySelector('.welcome');
    if(welcome)welcome.remove();
    const div=document.createElement('div');
    div.className='message '+(isUser?'user':'bot');
    if(filePreview){
        const img=document.createElement('img');
        img.src=filePreview;
        div.appendChild(img);
        div.appendChild(document.createElement('br'));
    }
    let formatted=text.replace(/\*\*(.*?)\*\*/g,'<strong>$1</strong>');
    formatted=formatted.replace(/\n/g,'<br>');
    div.innerHTML=formatted;
    chat.appendChild(div);
    chat.scrollTop=chat.scrollHeight;
}

function setTyping(show){
    const existing=document.querySelector('.typing');
    if(existing)existing.remove();
    if(show){
        const div=document.createElement('div');
        div.className='typing';
        div.textContent='🧠 AWESOME AI печатает...';
        chat.appendChild(div);
        chat.scrollTop=chat.scrollHeight;
    }
}

async function send(){
    const text=input.value.trim();
    if(!text && filesToSend.length===0)return;
    input.value='';
    sendBtn.disabled=true;
    setTyping(true);
    const formData=new FormData();
    formData.append('message',text||'');
    formData.append('user_id',userId);
    for(const file of filesToSend)formData.append('files',file);
    filesToSend=[];
    try{
        const response=await fetch('/api/chat_full',{method:'POST',body:formData});
        const data=await response.json();
        setTyping(false);
        if(data.error)addMessage('⚠️ '+data.error,false);
        else if(data.reply)addMessage(data.reply,false);
    }catch(e){
        setTyping(false);
        addMessage('⚠️ Ошибка соединения',false);
    }
    sendBtn.disabled=false;
    input.focus();
}

async function sendCommand(cmd){
    input.value=cmd;
    await send();
}

function handleFiles(files){
    for(const file of files){
        filesToSend.push(file);
        const reader=new FileReader();
        reader.onload=function(e){
            if(file.type.startsWith('image/')){
                addMessage('📎 '+file.name,true,e.target.result);
            }else{
                addMessage('📎 '+file.name+' ('+(file.size/1024).toFixed(1)+' KB)',true);
            }
        };
        reader.readAsDataURL(file);
    }
}

function clearChat(){
    chat.innerHTML='<div class="welcome"><h2>✨ AWESOME AI</h2><p>Спрашивай что угодно — я отвечу, решу, поищу</p><div class="features"><span>📸 Фото</span><span>🎤 Голос</span><span>🌐 Поиск</span><span>💵 Курсы</span><span>🧮 Математика</span><span>🎨 Рисование</span></div></div>';
}

function startRecording(){
    if(!('webkitSpeechRecognition'in window)&&!('SpeechRecognition'in window)){
        addMessage('🎤 Голосовой ввод не поддерживается',false);
        return;
    }
    addMessage('🎤 Запись... Говорите',true);
    const recognition=new(window.SpeechRecognition||window.webkitSpeechRecognition)();
    recognition.lang='ru-RU';
    recognition.onresult=function(event){
        const text=event.results[0][0].transcript;
        input.value=text;
        addMessage('🎤 Распознано: '+text,true);
        send();
    };
    recognition.onerror=function(){
        addMessage('🎤 Не удалось распознать речь',false);
    };
    recognition.start();
}
document.addEventListener('DOMContentLoaded',()=>input.focus());
</script>
</body>
</html>
"""

# ============================================================
# АДМИН-ПАНЕЛЬ
# ============================================================
@app.route('/admin')
def admin_panel():
    user_id = request.args.get('user_id', type=int)
    if not user_id or user_id != OWNER_ID:
        return "<h1 style='color:#f85149;'>🚫 ДОСТУП ЗАПРЕЩЁН</h1><p>Только владелец</p>", 403
    
    action = request.args.get('action')
    target_id = request.args.get('target_id', type=int)
    
    if action == 'giveprem' and target_id:
        set_premium(target_id, 30)
    if action == 'delprem' and target_id:
        remove_premium(target_id)
    if action == 'giveadmin' and target_id:
        db_query('UPDATE users SET is_admin = 1 WHERE user_id = ?', (target_id,))
    if action == 'deladmin' and target_id:
        db_query('UPDATE users SET is_admin = 0 WHERE user_id = ?', (target_id,))
    if action == 'ban' and target_id:
        db_query('INSERT INTO banned (user_id) VALUES (?)', (target_id,))
    if action == 'unban' and target_id:
        db_query('DELETE FROM banned WHERE user_id = ?', (target_id,))
    if action == 'mute' and target_id:
        db_query('INSERT INTO muted (user_id) VALUES (?)', (target_id,))
    if action == 'unmute' and target_id:
        db_query('DELETE FROM muted WHERE user_id = ?', (target_id,))
    
    users = db_query('SELECT * FROM users ORDER BY user_id DESC', fetchall=True) or []
    total = len(users)
    premium_count = sum(1 for u in users if u.get('premium', 0) == 1)
    admin_count = sum(1 for u in users if u.get('is_admin', 0) == 1)
    banned_count = len(db_query('SELECT * FROM banned', fetchall=True) or [])
    muted_count = len(db_query('SELECT * FROM muted', fetchall=True) or [])
    
    rows = ""
    for u in users:
        uid = u['user_id']
        username = u.get('username', 'Не указан')
        premium = u.get('premium', 0)
        expires = u.get('premium_expires')
        is_admin_flag = u.get('is_admin', 0)
        msgs = u.get('messages_today', 0)
        if uid == OWNER_ID:
            status = "👑 ВЛАДЕЛЕЦ"
        elif is_admin_flag:
            status = "👑 АДМИН"
        elif premium:
            status = "💎 PREMIUM"
        else:
            status = "🔓 Бесплатный"
        rows += f'''
        <tr>
            <td>{uid}</td>
            <td>@{username}</td>
            <td>{status}</td>
            <td>{msgs}</td>
            <td>{format_date(expires) if expires else "—"}</td>
            <td>
                <a href="?user_id={OWNER_ID}&action=giveprem&target_id={uid}" class="btn btn-prem">💎+</a>
                <a href="?user_id={OWNER_ID}&action=delprem&target_id={uid}" class="btn btn-del">💎-</a>
                <a href="?user_id={OWNER_ID}&action=giveadmin&target_id={uid}" class="btn btn-admin">👑+</a>
                <a href="?user_id={OWNER_ID}&action=deladmin&target_id={uid}" class="btn btn-del">👑-</a>
                <a href="?user_id={OWNER_ID}&action=ban&target_id={uid}" class="btn btn-danger">🚫</a>
                <a href="?user_id={OWNER_ID}&action=unban&target_id={uid}" class="btn btn-prem">✅</a>
                <a href="?user_id={OWNER_ID}&action=mute&target_id={uid}" class="btn btn-admin">🔇</a>
                <a href="?user_id={OWNER_ID}&action=unmute&target_id={uid}" class="btn btn-prem">🔊</a>
            </td>
        </tr>
        '''
    if not rows:
        rows = '<tr><td colspan="6" style="text-align:center;padding:20px;color:#8b949e;">Нет пользователей</td></tr>'
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>👑 Админ-панель</title>
    <style>
        *{{margin:0;padding:0;box-sizing:border-box;}}
        body{{font-family:sans-serif;background:#0a0e17;color:#e6edf3;padding:20px;}}
        h1{{color:#58a6ff;font-size:24px;margin-bottom:4px;}}
        .sub{{color:#8b949e;margin-bottom:20px;font-size:14px;}}
        .stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:12px;margin-bottom:25px;}}
        .card{{background:#161b22;padding:14px 18px;border-radius:10px;border:1px solid #30363d;}}
        .card span{{color:#8b949e;font-size:11px;}}
        .card .num{{font-size:24px;font-weight:700;color:#58a6ff;}}
        .card .num.gold{{color:#f0883e;}}
        .card .num.red{{color:#f85149;}}
        .section{{background:#161b22;border-radius:10px;border:1px solid #30363d;padding:16px 20px;}}
        .section h2{{font-size:16px;margin-bottom:12px;color:#58a6ff;}}
        table{{width:100%;border-collapse:collapse;font-size:13px;}}
        th{{background:#1c2128;color:#8b949e;font-weight:600;font-size:11px;padding:10px 12px;text-align:left;}}
        td{{padding:8px 12px;border-bottom:1px solid #30363d;}}
        tr:hover{{background:#1c2128;}}
        .btn{{padding:4px 10px;border-radius:4px;text-decoration:none;font-size:11px;display:inline-block;margin:1px;transition:0.2s;}}
        .btn:hover{{transform:scale(1.05);}}
        .btn-prem{{background:#2ea043;color:#fff;}}
        .btn-del{{background:#da3633;color:#fff;}}
        .btn-admin{{background:#f0883e;color:#fff;}}
        .btn-danger{{background:#da3633;color:#fff;}}
        .back{{color:#58a6ff;text-decoration:none;}}
        .back:hover{{text-decoration:underline;}}
        @media(max-width:640px){{table{{font-size:11px;}}td,th{{padding:4px 6px;}}.btn{{font-size:9px;padding:2px 6px;}}}}
    </style>
    </head>
    <body>
        <h1>👑 Админ-панель AWESOME AI</h1>
        <p class="sub">👤 Владелец: @flidges | <a href="/" class="back">← На главную</a></p>
        <div class="stats">
            <div class="card"><span>👥 Всего</span><div class="num">{total}</div></div>
            <div class="card"><span>💎 Premium</span><div class="num gold">{premium_count}</div></div>
            <div class="card"><span>👑 Админов</span><div class="num gold">{admin_count}</div></div>
            <div class="card"><span>🚫 Забанено</span><div class="num red">{banned_count}</div></div>
            <div class="card"><span>🔇 Замучено</span><div class="num gold">{muted_count}</div></div>
        </div>
        <div class="section">
            <h2>👥 Пользователи</h2>
            <div style="overflow-x:auto;">
                <table>
                    <thead><tr><th>ID</th><th>Username</th><th>Статус</th><th>Сегодня</th><th>Premium до</th><th>Действия</th></tr></thead>
                    <tbody>{rows}</tbody>
                </table>
            </div>
        </div>
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
        return jsonify({'error': str(e)})

@app.route('/api/chat_full', methods=['POST'])
def chat_full():
    try:
        user_id = int(request.form.get('user_id', 1))
        message = request.form.get('message', '')
        files = request.files.getlist('files')
        if not message and not files:
            return jsonify({'error': 'Напиши что-нибудь или прикрепи файл!'})
        ensure_user(user_id, f"user_{user_id}")
        image_description = None
        for file in files:
            if file.content_type and file.content_type.startswith('image/'):
                content = file.read()
                image_description = analyze_image(content)
                break
        if files and not image_description:
            image_description = f"📎 Получен файл: {', '.join([f.filename for f in files])}"
        response = process_message(user_id, message, image_description)
        return jsonify({'reply': response})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print("=" * 60)
    print("🧠 AWESOME AI — РАБОЧАЯ ВЕРСИЯ")
    print("=" * 60)
    print(f"🌐 http://localhost:{port}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=False)
