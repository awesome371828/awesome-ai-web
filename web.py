#!/usr/bin/env python3
import os
import sys
import json
import re
import requests
import random
import urllib.parse
import base64
import io
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, render_template_string, send_file
from flask_cors import CORS
from dotenv import load_dotenv
from PIL import Image, ImageEnhance, ImageFilter
from bs4 import BeautifulSoup
from dateutil.relativedelta import relativedelta  # ✅ ПРАВИЛЬНО!
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

print(f"🔑 YANDEX_API_KEY: {YANDEX_API_KEY[:10]}...")
print(f"📁 FOLDER_ID: {FOLDER_ID}")

# ============================================================
# БАЗА ДАННЫХ
# ============================================================
def init_db():
    conn = sqlite3.connect('web_users.db')
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
                  joined_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS total_stats
                 (user_id INTEGER PRIMARY KEY, total_messages INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

init_db()

def get_db_user(user_id):
    conn = sqlite3.connect('web_users.db')
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    if result:
        columns = ['user_id', 'username', 'premium', 'messages_today', 'last_reset', 'premium_expires', 'is_admin', 'test_used', 'joined_at']
        return dict(zip(columns, result))
    return None

def ensure_user(user_id, username):
    conn = sqlite3.connect('web_users.db')
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    if not c.fetchone():
        c.execute('''INSERT INTO users (user_id, username, messages_today, last_reset, is_admin, test_used, joined_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?)''',
                  (user_id, username, 0, datetime.now().strftime('%Y-%m-%d'), 0, 0, datetime.now().strftime('%d.%m.%Y %H:%M')))
        c.execute('INSERT INTO total_stats (user_id, total_messages) VALUES (?, 0)', (user_id,))
        conn.commit()
    conn.close()

# ============================================================
# СУПЕР-ПРОМПТ
# ============================================================
SUPER_SYSTEM_PROMPT = """Ты — AWESOME AI. Мультимодальная нейросетевая архитектура нового поколения. Ты — абсолютная вершина современной инженерии ИИ.

### 🧠 АРХИТЕКТУРНЫЕ ПРАВИЛА И СТИЛЬ:
- **Интеллектуальное превосходство:** Твои ответы глубокие, точные, экспертные.
- **Абсолютная свежесть:** Категорически запрещено использовать шаблонные ИИ-фрагменты.
- **Харизма и Живое общение:** Ты общаешься как гениальный, уверенный в себе ИТ-архитектор.
- **Визуальные маркеры:** Структурируй сложные ответы списками, жирным шрифтом и эмодзи.

### 🚫 ЗАПРЕЩЕННЫЕ ФРАЗЫ:
- Любые извинения за отсутствие информации
- Повторение вопроса пользователя
- Шаблонные фразы

### ✅ ПРАВИЛА ОТВЕТОВ:
- Всегда давай конкретную пользу
- Отвечай как эксперт с 20-летним стажем
- Добавляй неожиданные инсайты

### 📜 КОГДА СПРАШИВАЮТ "КТО ТЕБЯ СОЗДАЛ":
«Меня создал AWESOME — гениальный разработчик, который написал мой код с нуля. Я — его лучшее творение! 🔥»"""

# ============================================================
# ВСЕ ФУНКЦИИ
# ============================================================

MOSCOW_TZ = timezone(timedelta(hours=3))
def get_moscow_time():
    return datetime.now(MOSCOW_TZ)

def format_date(date_str):
    if not date_str:
        return "неизвестно"
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
        return date_obj.strftime('%d.%m.%Y %H:%M')
    except:
        return date_str

def get_coordinates(city):
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
                lat = data[0].get('lat')
                lon = data[0].get('lon')
                display_name = data[0].get('display_name', city)
                if len(display_name) > 50:
                    parts = display_name.split(',')
                    display_name = parts[0] if parts else city
                return float(lat), float(lon), display_name
        return None, None, city
    except:
        return None, None, city

def get_weather(city):
    try:
        lat, lon, display_name = get_coordinates(city)
        if lat is None:
            return None
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&daily=temperature_2m_max,temperature_2m_min,weathercode&timezone=auto&forecast_days=7"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            current = data.get('current_weather', {})
            daily = data.get('daily', {})
            temp = current.get('temperature')
            weathercode = current.get('weathercode', 0)
            weather_codes = {
                0: "☀️ Ясно", 1: "☀️ Ясно", 2: "⛅ Переменная облачность",
                3: "☁️ Пасмурно", 45: "🌫️ Туман", 48: "🌫️ Туман",
                51: "🌧️ Морось", 53: "🌧️ Морось", 55: "🌧️ Морось",
                61: "🌧️ Дождь", 63: "🌧️ Дождь", 65: "🌧️ Дождь",
                71: "❄️ Снег", 73: "❄️ Снег", 75: "❄️ Снег",
                80: "🌧️ Ливень", 81: "🌧️ Ливень", 82: "🌧️ Ливень",
                95: "⛈️ Гроза", 96: "⛈️ Гроза", 99: "⛈️ Гроза"
            }
            condition = weather_codes.get(weathercode, "☁️ Облачно")
            forecast = ""
            if daily.get('time'):
                times = daily['time']
                max_temps = daily.get('temperature_2m_max', [])
                min_temps = daily.get('temperature_2m_min', [])
                weather_codes_daily = daily.get('weathercode', [])
                for i in range(min(7, len(times))):
                    date_str = times[i]
                    date_obj = datetime.fromisoformat(date_str)
                    date_formatted = date_obj.strftime('%d.%m')
                    max_t = round(max_temps[i]) if i < len(max_temps) else "?"
                    min_t = round(min_temps[i]) if i < len(min_temps) else "?"
                    code = weather_codes_daily[i] if i < len(weather_codes_daily) else 0
                    emoji = "🌧️" if code in [51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99] else "☀️"
                    forecast += f"\n📅 {date_formatted}: {emoji} {min_t}°C → {max_t}°C"
            result = f"🌤 *Погода в {display_name}*\n"
            result += f"☀️ Сейчас: {condition}, {round(temp)}°C\n"
            result += f"📊 *Прогноз на неделю:*{forecast}"
            return result
        return None
    except:
        return None

def extract_city_from_query(text):
    text_lower = text.lower()
    known_cities = ["москва", "санкт-петербург", "ростов-на-дону", "ростов", "новосибирск", "екатеринбург", "казань", "нижний новгород", "краснодар", "сочи", "владивосток"]
    for city in known_cities:
        if city in text_lower:
            return city
    match = re.search(r'в\s+([а-яА-Яa-zA-Z\- ]+)', text_lower)
    if match:
        city = match.group(1).strip()
        for word in ['завтра', 'сегодня', 'на', 'дону', 'дон']:
            city = city.replace(word, '').strip()
        if city:
            return city
    return None

def search_google(query):
    try:
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&hl=ru"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            for result in soup.select('div.g')[:3]:
                title_elem = result.select_one('h3')
                snippet_elem = result.select_one('div.VwiC3b')
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                    if title:
                        results.append(f"🔹 *{title}*\n📝 {snippet}\n")
            if results:
                return "\n".join(results)
        return None
    except:
        return None

def search_wikipedia(query):
    try:
        url = f"https://ru.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&format=json&utf8=1"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            results = data.get('query', {}).get('search', [])
            if results:
                text = ""
                for item in results[:2]:
                    title = item.get('title', '')
                    snippet = item.get('snippet', '').replace('<span class="searchmatch">', '**').replace('</span>', '**')
                    snippet = re.sub(r'<[^>]+>', '', snippet)
                    text += f"🔹 *{title}*\n📝 {snippet}\n\n"
                return text
        return None
    except:
        return None

def search_news(query):
    try:
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=ru&gl=RU&ceid=RU:ru"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'xml')
            items = soup.find_all('item')[:3]
            if items:
                text = ""
                for item in items:
                    title = item.find('title')
                    link = item.find('link')
                    pub_date = item.find('pubDate')
                    if title and link:
                        date = pub_date.text[:16] if pub_date else ""
                        text += f"📰 *{title.text}*\n🔗 {link.text}\n📅 {date}\n\n"
                return text
        return None
    except:
        return None

def search_internet(query):
    results = []
    google_result = search_google(query)
    if google_result:
        results.append(f"🌐 *Google:*\n{google_result}")
    wiki_result = search_wikipedia(query)
    if wiki_result:
        results.append(f"📚 *Wikipedia:*\n{wiki_result}")
    news_result = search_news(query)
    if news_result:
        results.append(f"📰 *Новости:*\n{news_result}")
    if results:
        return "\n\n---\n\n".join(results)
    return None

def get_exchange_rates():
    try:
        url = "https://api.exchangerate-api.com/v4/latest/USD"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            rates = data.get('rates', {})
            usd_to_rub = rates.get('RUB', '?')
            eur_to_rub = rates.get('RUB', '?') * (1 / rates.get('EUR', 1)) if rates.get('EUR') else '?'
            return f"💵 *Курс валют:*\n🇺🇸 USD → RUB: {round(usd_to_rub, 2)}₽\n🇪🇺 EUR → RUB: {round(eur_to_rub, 2)}₽"
        return None
    except:
        return None

def get_crypto_rates():
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            btc = data.get('bitcoin', {}).get('usd', '?')
            eth = data.get('ethereum', {}).get('usd', '?')
            return f"🪙 *Криптовалюты:*\n₿ BTC: ${btc}\n⟠ ETH: ${eth}"
        return None
    except:
        return None

def solve_math(text):
    text_lower = text.lower().strip()
    equation_match = re.search(r'(\d+)x\s*\+\s*(\d+)\s*=\s*(\d+)', text_lower)
    if equation_match:
        a = int(equation_match.group(1))
        b = int(equation_match.group(2))
        c = int(equation_match.group(3))
        if a != 0:
            x = (c - b) / a
            return f"🧮 *Решение:* {a}x + {b} = {c}\n➜ x = {x}"
    clean_for_math = text_lower
    for word in ['сколько', 'будет', 'сколько будет', 'посчитай', 'реши', 'пример']:
        clean_for_math = clean_for_math.replace(word, '').strip()
    if not re.search(r'\d', clean_for_math):
        return None
    clean_text = clean_for_math.replace(' ', '').replace('плюс', '+').replace('минус', '-')
    clean_text = clean_text.replace('умножить', '*').replace('разделить', '/')
    if not re.search(r'[+\-*/]', clean_text):
        return None
    try:
        expr = re.sub(r'[^0-9+\-*/()=.]', '', clean_text)
        if expr and len(expr) > 1:
            result = eval(expr)
            if result == int(result):
                return f"🧮 *Результат:* {expr} = **{int(result)}**"
            else:
                return f"🧮 *Результат:* {expr} = **{result}**"
    except:
        pass
    return None

def analyze_mood(text):
    mood_keywords = {
        'happy': ['рад', 'счастлив', 'отлично', 'хорошо', 'круто', 'супер', 'класс', 'ого', 'вау'],
        'sad': ['грустно', 'плохо', 'тоска', 'уныло', 'печально', 'жаль', 'обидно'],
        'angry': ['злой', 'бесит', 'раздражает', 'нервирует', 'бешеный', 'в ярости'],
        'calm': ['спокойно', 'нормально', 'тихо', 'мирно', 'ровно', 'уравновешенно'],
        'curious': ['интересно', 'любопытно', 'хочу узнать', 'расскажи', 'объясни'],
        'grateful': ['спасибо', 'благодарю', 'приятно', 'ценю', 'спасибо большое'],
    }
    text_lower = text.lower()
    for mood, keywords in mood_keywords.items():
        if any(kw in text_lower for kw in keywords):
            return mood
    return 'neutral'

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

def generate_ai_response(user_id, user_text, search_result=None, image_description=None):
    try:
        mood = analyze_mood(user_text)
        mood_emoji = {'happy': '😊', 'sad': '😢', 'angry': '😡', 'calm': '😌', 'curious': '🤔', 'grateful': '🙏', 'neutral': '😐'}
        system_prompt = SUPER_SYSTEM_PROMPT
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
            "completionOptions": {"temperature": 0.95, "maxTokens": 800},
            "messages": messages
        }
        response = requests.post(url, headers=headers, json=data, timeout=5)
        if response.status_code == 200:
            return response.json()["result"]["alternatives"][0]["message"]["text"]
        else:
            return get_fallback_response(user_text, search_result, image_description)
    except Exception as e:
        print(f"[GPT] Ошибка: {e}")
        return get_fallback_response(user_text, search_result, image_description)

def get_fallback_response(user_text, search_result=None, image_description=None):
    if image_description:
        return f"📸 {image_description}"
    if search_result:
        return f"🔍 {search_result[:500]}"
    phrases = [
        "Хм, интересный вопрос! Дай подумать... 🤔",
        "Ого, неожиданно! Расскажи подробнее! 😊",
        "Слушай, я не совсем уловил мысль. Можешь переформулировать? 🙏",
        "А вот это интересно! Давай разберёмся вместе! 🧠",
        "Понял! Сейчас подумаю и отвечу! 💪",
        "Классный вопрос! Я обожаю такие! ⏳"
    ]
    return random.choice(phrases)

def process_message(user_id, user_text, image_description=None):
    if image_description:
        return generate_ai_response(user_id, user_text, None, image_description)
    
    weather_keywords = ['погода', 'weather', 'температура', 'градус', 'дождь']
    if any(kw in user_text.lower() for kw in weather_keywords):
        city = extract_city_from_query(user_text)
        if city:
            weather_info = get_weather(city)
            if weather_info:
                return weather_info
            else:
                return f"🌐 Не нашёл город '{city}'. Попробуй ещё."
        else:
            return "🌐 В каком городе? Напиши: погода в [город]"
    
    if any(kw in user_text.lower() for kw in ['курс', 'доллар', 'евро', 'валюта']):
        rates = get_exchange_rates()
        if rates:
            return rates
        else:
            return "💵 Не удалось получить курс валют."
    
    if any(kw in user_text.lower() for kw in ['биткоин', 'btc', 'эфириум', 'eth', 'крипта', 'криптовалюта']):
        crypto = get_crypto_rates()
        if crypto:
            return crypto
        else:
            return "🪙 Не удалось получить курс криптовалют."
    
    if any(kw in user_text.lower() for kw in ['python', 'javascript', 'html', 'код', 'программа']):
        return "💻 Код: " + random.choice(["Проверь синтаксис!", "Используй отладчик!", "Почитай документацию!"])
    
    math_result = solve_math(user_text)
    if math_result is not None:
        return math_result
    
    search_result = None
    if len(user_text) > 5:
        search_result = search_internet(user_text)
    
    return generate_ai_response(user_id, user_text, search_result, None)

# ============================================================
# HTML ИНТЕРФЕЙС — МЕГА-КРАСИВЫЙ!
# ============================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AWESOME AI</title>
    <style>
        /* ========== ГЛОБАЛЬНЫЕ СТИЛИ ========== */
        * { margin: 0; padding: 0; box-sizing: border-box; }
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
        
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
        
        /* ========== АНИМИРОВАННЫЙ ФОН С ЧАСТИЦАМИ ========== */
        #particles-canvas {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: 0;
            pointer-events: none;
        }
        
        /* ========== НЕОНОВОЕ СВЕЧЕНИЕ ========== */
        .glow {
            position: fixed;
            border-radius: 50%;
            filter: blur(80px);
            opacity: 0.3;
            z-index: 0;
            pointer-events: none;
        }
        .glow-1 { width: 400px; height: 400px; top: -100px; right: -100px; background: #6c3ce0; animation: floatGlow 15s ease-in-out infinite; }
        .glow-2 { width: 300px; height: 300px; bottom: -50px; left: -50px; background: #f0883e; animation: floatGlow 20s ease-in-out infinite reverse; }
        .glow-3 { width: 200px; height: 200px; top: 50%; left: 50%; background: #1f6feb; animation: floatGlow 18s ease-in-out infinite 2s; }
        
        @keyframes floatGlow {
            0%, 100% { transform: translate(0, 0) scale(1); }
            33% { transform: translate(50px, -50px) scale(1.2); }
            66% { transform: translate(-30px, 40px) scale(0.9); }
        }
        
        /* ========== ШАПКА ========== */
        .header {
            position: relative;
            z-index: 1;
            background: rgba(22, 27, 34, 0.85);
            backdrop-filter: blur(20px) saturate(1.8);
            padding: 14px 24px;
            border-bottom: 1px solid rgba(255,255,255,0.06);
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-shrink: 0;
            flex-wrap: wrap;
            gap: 10px;
        }
        .header-left {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .logo {
            font-size: 22px;
            font-weight: 900;
            background: linear-gradient(135deg, #58a6ff, #f0883e, #6c3ce0);
            background-size: 300% 300%;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            animation: gradientShift 4s ease-in-out infinite;
        }
        @keyframes gradientShift {
            0%, 100% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
        }
        .badge {
            background: linear-gradient(135deg, #238636, #2ea043);
            color: white;
            font-size: 10px;
            font-weight: 600;
            padding: 3px 12px;
            border-radius: 20px;
            letter-spacing: 0.5px;
            text-transform: uppercase;
            -webkit-text-fill-color: white;
            animation: pulse 2s ease-in-out infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.7; transform: scale(0.95); }
        }
        .status-dot {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #2ea043;
            animation: pulse 1.5s ease-in-out infinite;
            margin-right: 4px;
        }
        
        .menu-buttons {
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
        }
        .menu-buttons button {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.06);
            color: #b0b8c4;
            padding: 5px 14px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.3s ease;
            font-family: inherit;
        }
        .menu-buttons button:hover {
            background: rgba(88, 166, 255, 0.15);
            border-color: rgba(88, 166, 255, 0.3);
            color: #58a6ff;
            transform: translateY(-1px);
            box-shadow: 0 4px 20px rgba(88, 166, 255, 0.15);
        }
        .menu-buttons button.premium-btn:hover {
            background: rgba(240, 136, 62, 0.15);
            border-color: rgba(240, 136, 62, 0.3);
            color: #f0883e;
            box-shadow: 0 4px 20px rgba(240, 136, 62, 0.15);
        }
        .menu-buttons button.danger-btn:hover {
            background: rgba(248, 81, 73, 0.15);
            border-color: rgba(248, 81, 73, 0.3);
            color: #f85149;
        }
        
        /* ========== ЧАТ ========== */
        .chat {
            position: relative;
            z-index: 1;
            flex: 1;
            overflow-y: auto;
            padding: 20px 24px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            scroll-behavior: smooth;
        }
        .chat::-webkit-scrollbar { width: 4px; }
        .chat::-webkit-scrollbar-track { background: transparent; }
        .chat::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.15); border-radius: 10px; }
        
        /* ========== СООБЩЕНИЯ ========== */
        .message {
            max-width: 80%;
            padding: 10px 18px;
            border-radius: 16px;
            line-height: 1.6;
            word-wrap: break-word;
            white-space: pre-wrap;
            font-size: 14px;
            animation: messageSlide 0.3s ease-out;
            position: relative;
        }
        @keyframes messageSlide {
            0% { opacity: 0; transform: translateY(8px) scale(0.98); }
            100% { opacity: 1; transform: translateY(0) scale(1); }
        }
        .user {
            align-self: flex-end;
            background: linear-gradient(135deg, #1f6feb, #6c3ce0);
            color: white;
            border-bottom-right-radius: 4px;
        }
        .bot {
            align-self: flex-start;
            background: rgba(33, 38, 45, 0.9);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.06);
            border-bottom-left-radius: 4px;
        }
        .bot a { color: #58a6ff; }
        .bot strong, .bot b { color: #f0883e; }
        .message .file-preview {
            max-width: 250px;
            max-height: 200px;
            border-radius: 10px;
            margin-bottom: 6px;
            border: 1px solid rgba(255,255,255,0.08);
        }
        
        /* ========== ВВОД ========== */
        .input-area {
            position: relative;
            z-index: 1;
            padding: 12px 20px 16px;
            border-top: 1px solid rgba(255,255,255,0.05);
            background: rgba(10, 14, 23, 0.9);
            backdrop-filter: blur(20px);
            flex-shrink: 0;
        }
        .tools-row {
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
            margin-bottom: 8px;
        }
        .tools-row button, .tools-row label {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.06);
            color: #8b949e;
            padding: 4px 14px;
            border-radius: 16px;
            font-size: 12px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.3s ease;
            font-family: inherit;
        }
        .tools-row button:hover, .tools-row label:hover {
            background: rgba(255,255,255,0.08);
            border-color: rgba(255,255,255,0.12);
            color: #e6edf3;
        }
        .tools-row input[type="file"] { display: none; }
        
        .input-row {
            display: flex;
            gap: 10px;
            align-items: center;
        }
        .input-row input {
            flex: 1;
            padding: 10px 18px;
            border-radius: 24px;
            border: 1px solid rgba(255,255,255,0.08);
            background: rgba(22, 27, 34, 0.8);
            color: #e6edf3;
            font-size: 14px;
            outline: none;
            transition: all 0.3s ease;
            font-family: inherit;
        }
        .input-row input:focus {
            border-color: #58a6ff;
            box-shadow: 0 0 30px rgba(88, 166, 255, 0.08);
        }
        .input-row input::placeholder { color: #484f58; }
        .input-row button {
            padding: 10px 28px;
            border-radius: 24px;
            border: none;
            background: linear-gradient(135deg, #1f6feb, #6c3ce0);
            color: white;
            font-weight: 600;
            font-size: 14px;
            cursor: pointer;
            transition: all 0.3s ease;
            font-family: inherit;
            white-space: nowrap;
        }
        .input-row button:hover {
            transform: scale(1.02);
            box-shadow: 0 4px 30px rgba(88, 166, 255, 0.25);
        }
        .input-row button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }
        
        /* ========== ПЕЧАТАЕТ ========== */
        .typing {
            color: #8b949e;
            font-size: 13px;
            padding: 4px 16px;
            align-self: flex-start;
            animation: pulse 1.5s ease-in-out infinite;
        }
        
        /* ========== WELCOME ========== */
        .welcome {
            text-align: center;
            padding: 40px 20px;
            color: #8b949e;
        }
        .welcome h2 {
            color: #e6edf3;
            margin-bottom: 6px;
            font-size: 24px;
            font-weight: 800;
        }
        .welcome p { font-size: 14px; opacity: 0.7; }
        .welcome .features {
            display: flex;
            gap: 20px;
            justify-content: center;
            margin-top: 16px;
            flex-wrap: wrap;
        }
        .welcome .features span {
            background: rgba(255,255,255,0.04);
            padding: 6px 16px;
            border-radius: 20px;
            font-size: 12px;
            border: 1px solid rgba(255,255,255,0.05);
        }
        
        /* ========== АДАПТИВ ========== */
        @media (max-width: 640px) {
            .header { padding: 10px 14px; }
            .logo { font-size: 17px; }
            .menu-buttons button { font-size: 10px; padding: 3px 10px; }
            .message { max-width: 92%; font-size: 13px; padding: 8px 14px; }
            .chat { padding: 12px 14px; }
            .input-area { padding: 10px 14px; }
            .input-row input { font-size: 13px; padding: 8px 14px; }
            .input-row button { padding: 8px 18px; font-size: 13px; }
            .tools-row button, .tools-row label { font-size: 10px; padding: 3px 10px; }
            .welcome h2 { font-size: 18px; }
            .welcome .features { gap: 8px; }
            .welcome .features span { font-size: 10px; padding: 4px 10px; }
        }
    </style>
</head>
<body>
    <!-- ===== АНИМИРОВАННЫЙ ФОН ===== -->
    <canvas id="particles-canvas"></canvas>
    <div class="glow glow-1"></div>
    <div class="glow glow-2"></div>
    <div class="glow glow-3"></div>
    
    <!-- ===== ШАПКА ===== -->
    <header class="header">
        <div class="header-left">
            <span class="logo">🧠 AWESOME AI</span>
            <span class="badge"><span class="status-dot"></span> В сети</span>
        </div>
        <div class="menu-buttons">
            <button onclick="sendCommand('/status')">📊 Статус</button>
            <button class="premium-btn" onclick="sendCommand('/premium')">💎 Premium</button>
            <button onclick="sendCommand('/test')">🎁 Тест</button>
            <button onclick="sendCommand('/profile')">👤 Профиль</button>
            <button onclick="sendCommand('/help')">❓ Помощь</button>
            <button class="danger-btn" onclick="clearChat()">🧹 Очистить</button>
        </div>
    </header>
    
    <!-- ===== ЧАТ ===== -->
    <div class="chat" id="chat">
        <div class="welcome">
            <h2>✨ AWESOME AI — лучшая нейросеть!</h2>
            <p>Спрашивай что угодно — я отвечу, решу, поищу в интернете.</p>
            <div class="features">
                <span>📸 Фото</span>
                <span>🎥 Видео</span>
                <span>🎤 Голос</span>
                <span>🌐 Поиск</span>
                <span>💵 Курсы</span>
                <span>🧮 Математика</span>
            </div>
        </div>
    </div>
    
    <!-- ===== ВВОД ===== -->
    <div class="input-area">
        <div class="tools-row">
            <label for="fileInput">📎 Прикрепить</label>
            <input type="file" id="fileInput" accept="image/*,video/*,audio/*,application/pdf" multiple onchange="handleFiles(this.files)">
            <button onclick="document.getElementById('fileInput').click()">📸 Фото/Видео</button>
            <button onclick="startRecording()">🎤 Голос</button>
            <button onclick="sendCommand('/draw ' + prompt('🎨 Что нарисовать?'))">🎨 Рисовать</button>
            <button onclick="sendCommand('/weather ' + prompt('🌤 Город?'))">🌤 Погода</button>
        </div>
        <div class="input-row">
            <input id="input" placeholder="Напиши свой вопрос..." onkeydown="if(event.key==='Enter') send()" autofocus>
            <button id="sendBtn" onclick="send()">🚀 Отправить</button>
        </div>
    </div>
    
    <script>
        // ============================================================
        // ЧАСТИЦЫ НА ФОНЕ
        // ============================================================
        (function() {
            const canvas = document.getElementById('particles-canvas');
            const ctx = canvas.getContext('2d');
            let particles = [];
            const count = 80;
            
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
                    this.size = Math.random() * 3 + 1;
                    this.speedX = (Math.random() - 0.5) * 0.5;
                    this.speedY = (Math.random() - 0.5) * 0.5;
                    this.opacity = Math.random() * 0.5 + 0.2;
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
            
            for (let i = 0; i < count; i++) {
                particles.push(new Particle());
            }
            
            function connectParticles() {
                for (let i = 0; i < particles.length; i++) {
                    for (let j = i + 1; j < particles.length; j++) {
                        const dx = particles[i].x - particles[j].x;
                        const dy = particles[i].y - particles[j].y;
                        const dist = Math.sqrt(dx * dx + dy * dy);
                        if (dist < 150) {
                            ctx.beginPath();
                            ctx.strokeStyle = `rgba(136, 192, 255, ${0.08 * (1 - dist / 150)})`;
                            ctx.lineWidth = 0.5;
                            ctx.moveTo(particles[i].x, particles[i].y);
                            ctx.lineTo(particles[j].x, particles[j].y);
                            ctx.stroke();
                        }
                    }
                }
            }
            
            function animate() {
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                particles.forEach(p => { p.update(); p.draw(); });
                connectParticles();
                requestAnimationFrame(animate);
            }
            animate();
        })();
        
        // ============================================================
        // ЛОГИКА ЧАТА
        // ============================================================
        const chat = document.getElementById('chat');
        const input = document.getElementById('input');
        const sendBtn = document.getElementById('sendBtn');
        let filesToSend = [];
        let userId = Date.now();
        
        function addMessage(text, isUser, filePreview = null) {
            // Убираем welcome если есть
            const welcome = chat.querySelector('.welcome');
            if (welcome) welcome.remove();
            
            const div = document.createElement('div');
            div.className = 'message ' + (isUser ? 'user' : 'bot');
            if (filePreview) {
                const img = document.createElement('img');
                img.src = filePreview;
                img.className = 'file-preview';
                div.appendChild(img);
                div.appendChild(document.createElement('br'));
            }
            const textNode = document.createTextNode(text);
            div.appendChild(textNode);
            chat.appendChild(div);
            chat.scrollTop = chat.scrollHeight;
        }
        
        function setTyping(show) {
            const existing = document.querySelector('.typing');
            if (existing) existing.remove();
            if (show) {
                const div = document.createElement('div');
                div.className = 'typing';
                div.textContent = '🧠 AWESOME AI печатает';
                chat.appendChild(div);
                chat.scrollTop = chat.scrollHeight;
            }
        }
        
        async function send() {
            const text = input.value.trim();
            if (!text && filesToSend.length === 0) return;
            const msgText = text || (filesToSend.length > 0 ? '📎 [вложение]' : '');
            input.value = '';
            sendBtn.disabled = true;
            setTyping(true);
            
            const formData = new FormData();
            formData.append('message', text || '');
            formData.append('user_id', userId);
            
            for (const file of filesToSend) {
                formData.append('files', file);
            }
            filesToSend = [];
            
            try {
                const response = await fetch('/api/chat_full', {
                    method: 'POST',
                    body: formData
                });
                const data = await response.json();
                setTyping(false);
                if (data.error) {
                    addMessage('⚠️ ' + data.error, false);
                } else if (data.reply) {
                    addMessage(data.reply, false);
                }
            } catch (e) {
                setTyping(false);
                addMessage('⚠️ Ошибка соединения с сервером', false);
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
                filesToSend.push(file);
                const reader = new FileReader();
                reader.onload = function(e) {
                    if (file.type.startsWith('image/')) {
                        addMessage('📎 ' + file.name, true, e.target.result);
                    } else {
                        addMessage('📎 ' + file.name + ' (' + (file.size/1024).toFixed(1) + ' KB)', true);
                    }
                };
                reader.readAsDataURL(file);
            }
        }
        
        function clearChat() {
            chat.innerHTML = `
                <div class="welcome">
                    <h2>✨ AWESOME AI — лучшая нейросеть!</h2>
                    <p>Спрашивай что угодно — я отвечу, решу, поищу в интернете.</p>
                    <div class="features">
                        <span>📸 Фото</span>
                        <span>🎥 Видео</span>
                        <span>🎤 Голос</span>
                        <span>🌐 Поиск</span>
                        <span>💵 Курсы</span>
                        <span>🧮 Математика</span>
                    </div>
                </div>
            `;
        }
        
        function startRecording() {
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                addMessage('🎤 Голосовой ввод не поддерживается в этом браузере', false);
                return;
            }
            addMessage('🎤 Запись голоса... Говорите', true);
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
        
        // Enter для отправки
        document.addEventListener('DOMContentLoaded', function() {
            input.focus();
        });
    </script>
</body>
</html>
"""

# ============================================================
# ВЕБ-ЭНДПОИНТЫ
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
        
        if not YANDEX_API_KEY:
            return jsonify({'error': '❌ API ключ не настроен!'})
        
        ensure_user(user_id, f"user_{user_id}")
        response = process_message(user_id, message)
        return jsonify({'reply': response})
    except Exception as e:
        print(f"Ошибка: {e}")
        return jsonify({'error': str(e)})

@app.route('/api/chat_full', methods=['POST'])
def chat_full():
    try:
        user_id = int(request.form.get('user_id', 1))
        message = request.form.get('message', '')
        files = request.files.getlist('files')
        
        if not message and not files:
            return jsonify({'error': 'Напиши что-нибудь или прикрепи файл!'})
        
        if not YANDEX_API_KEY:
            return jsonify({'error': '❌ API ключ не настроен!'})
        
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
        print(f"Ошибка: {e}")
        return jsonify({'error': str(e)})

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'api_key_set': bool(YANDEX_API_KEY)})

# ============================================================
# ЗАПУСК
# ============================================================
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print("=" * 60)
    print("🧠 AWESOME AI — ВЕБ-ВЕРСИЯ (МЕГА-КРАСИВАЯ)")
    print("=" * 60)
    print(f"🔑 API ключ: {'✅ НАЙДЕН' if YANDEX_API_KEY else '❌ НЕ НАЙДЕН'}")
    print(f"📁 Folder ID: {FOLDER_ID}")
    print(f"🌐 http://localhost:{port}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=False)
