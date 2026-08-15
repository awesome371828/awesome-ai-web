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
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from dotenv import load_dotenv
from PIL import Image, ImageEnhance, ImageFilter
from bs4 import BeautifulSoup
from supabase import create_client, Client
import time

load_dotenv()

app = Flask(__name__)
CORS(app)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

# ============================================================
# НАСТРОЙКА
# ============================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY") or "AQVNyfn82epL9dy8C_kftzeypq6eF9lFd6SZnFzV"
FOLDER_ID = os.getenv("FOLDER_ID", "b1g4aq87c7j61c6g3i5l")
OWNER_ID = 6652898792

FREE_LIMIT = 20
PREMIUM_LIMIT = 150

# ============================================================
# SUPABASE (ТА ЖЕ БАЗА, ЧТО И В ТГ БОТЕ)
# ============================================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")

supabase = None
try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Supabase подключен!")
except Exception as e:
    print(f"❌ Ошибка Supabase: {e}")

def get_db_user(user_id):
    if not supabase:
        return None
    try:
        response = supabase.table('users').select('*').eq('user_id', user_id).execute()
        if response.data:
            return response.data[0]
        return None
    except:
        return None

def ensure_user(user_id, username):
    if not supabase:
        return
    try:
        response = supabase.table('users').select('*').eq('user_id', user_id).execute()
        if not response.data:
            joined_at = datetime.now().strftime('%d.%m.%Y %H:%M')
            is_owner = 1 if user_id == OWNER_ID else 0
            data = {
                'user_id': user_id,
                'username': username,
                'messages_today': 0,
                'last_reset': datetime.now().strftime('%Y-%m-%d'),
                'is_admin': is_owner,
                'test_used': 0,
                'joined_at': joined_at,
                'is_owner': is_owner,
                'premium': 0,
                'premium_expires': None
            }
            supabase.table('users').insert(data).execute()
            try:
                supabase.table('total_stats').insert({'user_id': user_id, 'total_messages': 0}).execute()
            except:
                pass
    except Exception as e:
        print(f"⚠️ Supabase ошибка: {e}")

def update_db_user(user_id, data):
    if not supabase:
        return
    try:
        supabase.table('users').update(data).eq('user_id', user_id).execute()
    except:
        pass

def is_admin(user_id):
    if user_id == OWNER_ID:
        return True
    if not supabase:
        return False
    try:
        response = supabase.table('users').select('is_admin').eq('user_id', user_id).execute()
        if response.data:
            return response.data[0].get('is_admin', 0) == 1
        return False
    except:
        return False

def is_banned(user_id):
    if not supabase:
        return False
    try:
        response = supabase.table('banned').select('user_id').eq('user_id', user_id).execute()
        return len(response.data) > 0
    except:
        return False

def is_muted(user_id):
    if not supabase:
        return False
    try:
        response = supabase.table('muted').select('user_id').eq('user_id', user_id).execute()
        return len(response.data) > 0
    except:
        return False

def ban_user(user_id):
    if not supabase:
        return
    try:
        supabase.table('banned').insert({'user_id': user_id}).execute()
    except:
        pass

def unban_user(user_id):
    if not supabase:
        return
    try:
        supabase.table('banned').delete().eq('user_id', user_id).execute()
    except:
        pass

def mute_user(user_id):
    if not supabase:
        return
    try:
        supabase.table('muted').insert({'user_id': user_id}).execute()
    except:
        pass

def unmute_user(user_id):
    if not supabase:
        return
    try:
        supabase.table('muted').delete().eq('user_id', user_id).execute()
    except:
        pass

def set_premium(user_id, duration_str):
    if not supabase:
        return False
    now = datetime.now()
    if duration_str.endswith('d'):
        delta = timedelta(days=int(duration_str[:-1]))
    elif duration_str.endswith('m'):
        delta = timedelta(minutes=int(duration_str[:-1]))
    elif duration_str.endswith('h'):
        delta = timedelta(hours=int(duration_str[:-1]))
    elif duration_str.endswith('mes'):
        delta = timedelta(days=int(duration_str[:-3]) * 30)
    elif duration_str.endswith('y'):
        delta = timedelta(days=int(duration_str[:-1]) * 365)
    else:
        return False
    try:
        response = supabase.table('users').select('premium_expires').eq('user_id', user_id).execute()
        current_expires = response.data[0].get('premium_expires') if response.data else None
        if current_expires:
            try:
                current_date = datetime.strptime(current_expires, '%Y-%m-%d %H:%M:%S')
                if current_date > now:
                    expires = (current_date + delta).strftime('%Y-%m-%d %H:%M:%S')
                else:
                    expires = (now + delta).strftime('%Y-%m-%d %H:%M:%S')
            except:
                expires = (now + delta).strftime('%Y-%m-%d %H:%M:%S')
        else:
            expires = (now + delta).strftime('%Y-%m-%d %H:%M:%S')
        supabase.table('users').update({'premium': 1, 'premium_expires': expires}).eq('user_id', user_id).execute()
        return True
    except:
        return False

def remove_premium(user_id):
    if not supabase:
        return
    try:
        supabase.table('users').update({'premium': 0, 'premium_expires': None}).eq('user_id', user_id).execute()
    except:
        pass

def set_admin(user_id, status):
    if not supabase:
        return
    try:
        supabase.table('users').update({'is_admin': 1 if status else 0}).eq('user_id', user_id).execute()
    except:
        pass

def get_premium_status(user_id):
    if user_id == OWNER_ID:
        return True
    if not supabase:
        return False
    try:
        response = supabase.table('users').select('premium, premium_expires').eq('user_id', user_id).execute()
        if response.data:
            premium = response.data[0].get('premium', 0)
            expires = response.data[0].get('premium_expires')
            if premium == 1 and expires:
                try:
                    expires_date = datetime.strptime(expires, '%Y-%m-%d %H:%M:%S')
                    if datetime.now() > expires_date:
                        remove_premium(user_id)
                        return False
                except:
                    return premium == 1
            return premium == 1
        return False
    except:
        return False

def get_total_messages(user_id):
    if not supabase:
        return 0
    try:
        response = supabase.table('total_stats').select('total_messages').eq('user_id', user_id).execute()
        if response.data:
            return response.data[0].get('total_messages', 0)
        return 0
    except:
        return 0

def format_date(date_str):
    if not date_str:
        return "неизвестно"
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
        return date_obj.strftime('%d.%m.%Y %H:%M')
    except:
        return date_str

# ============================================================
# ВСЕ ФУНКЦИИ (погода, поиск, курсы, математика, картинки)
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
                lat = data[0].get('lat')
                lon = data[0].get('lon')
                display_name = data[0].get('display_name', city)
                url2 = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&daily=temperature_2m_max,temperature_2m_min,weathercode&timezone=auto&forecast_days=7"
                resp = requests.get(url2, timeout=5)
                if resp.status_code == 200:
                    data2 = resp.json()
                    current = data2.get('current_weather', {})
                    daily = data2.get('daily', {})
                    temp = current.get('temperature')
                    weathercode = current.get('weathercode', 0)
                    codes = {0: "☀️ Ясно", 1: "☀️ Ясно", 2: "⛅ Облачно", 3: "☁️ Пасмурно",
                             61: "🌧️ Дождь", 63: "🌧️ Дождь", 65: "🌧️ Дождь",
                             71: "❄️ Снег", 73: "❄️ Снег", 75: "❄️ Снег",
                             80: "🌧️ Ливень", 95: "⛈️ Гроза"}
                    condition = codes.get(weathercode, "☁️ Облачно")
                    forecast = ""
                    if daily.get('time'):
                        for i in range(min(5, len(daily['time']))):
                            date_obj = datetime.fromisoformat(daily['time'][i])
                            date_formatted = date_obj.strftime('%d.%m')
                            max_t = round(daily['temperature_2m_max'][i]) if i < len(daily['temperature_2m_max']) else "?"
                            min_t = round(daily['temperature_2m_min'][i]) if i < len(daily['temperature_2m_min']) else "?"
                            forecast += f"\n📅 {date_formatted}: {min_t}°C → {max_t}°C"
                    return f"🌤 *Погода в {display_name}*\n☀️ Сейчас: {condition}, {round(temp)}°C\n📊 Прогноз:{forecast}"
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
            data = response.json()
            rates = data.get('rates', {})
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

def generate_image(prompt):
    try:
        clean_prompt = prompt
        for word in ['нарисуй', 'сгенерируй', 'покажи', 'картинку', 'изображение']:
            clean_prompt = clean_prompt.replace(word, '').strip()
        if not clean_prompt:
            clean_prompt = prompt
        url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(clean_prompt)}?width=512&height=512&nologo=true"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200 and len(response.content) > 1000:
            return response.content
        return None
    except:
        return None

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
        "Понял! Сейчас подумаю и отвечу! 💪"
    ]
    return random.choice(phrases)

def process_message(user_id, user_text, image_description=None):
    text_lower = user_text.lower().strip()
    
    if is_banned(user_id):
        return "🚫 Ты забанен!"
    
    # Команды
    if text_lower == '/status':
        user_data = get_db_user(user_id)
        if not user_data:
            return "❌ Пользователь не найден"
        premium = get_premium_status(user_id)
        messages = user_data.get('messages_today', 0)
        total = get_total_messages(user_id)
        expires = user_data.get('premium_expires')
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
        user_data = get_db_user(user_id)
        if user_data and user_data.get('test_used', 0) == 1:
            return "⛔ Ты уже использовал тест Premium!"
        if get_premium_status(user_id):
            return "💎 У тебя уже есть Premium!"
        if set_premium(user_id, "1d"):
            update_db_user(user_id, {'test_used': 1})
            return "🎉 *ПРОБНЫЙ PREMIUM АКТИВИРОВАН!*\n\n✅ Приоритетная обработка\n✅ 150 сообщений в день\n✅ Более качественные ответы\n\n⏳ Доступ активен 24 часа."
        return "❌ Ошибка активации Premium"
    
    if text_lower == '/profile':
        user_data = get_db_user(user_id)
        if not user_data:
            return "❌ Пользователь не найден"
        premium = get_premium_status(user_id)
        messages = user_data.get('messages_today', 0)
        total = get_total_messages(user_id)
        joined = user_data.get('joined_at', 'Неизвестно')
        if user_id == OWNER_ID:
            status = "👑 ВЛАДЕЛЕЦ"
        elif user_data.get('is_admin', 0) == 1:
            status = "👑 АДМИН"
        elif premium:
            status = "💎 PREMIUM"
        else:
            status = "🔓 Бесплатный"
        return f"👤 *ТВОЙ ПРОФИЛЬ*\n\n🆔 ID: {user_id}\n💎 Статус: {status}\n✉️ Сегодня: {messages}\n📊 Всего: {total}\n📅 Вход: {joined}"
    
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
        if weather:
            return weather
        return f"🌐 Не нашёл город '{city}'"
    
    if text_lower == '/exchange':
        rates = get_exchange_rates()
        return rates or "💵 Не удалось получить курс валют."
    
    if text_lower == '/crypto':
        crypto = get_crypto_rates()
        return crypto or "🪙 Не удалось получить курс криптовалют."
    
    # Авто-определение
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
# ГЛАВНАЯ СТРАНИЦА (МЕГА-КРАСИВЫЙ ВИЗУАЛ)
# ============================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AWESOME AI</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Inter', sans-serif; background: #080c16; color: #e6edf3; height: 100vh; display: flex; flex-direction: column; overflow: hidden; position: relative; }
        #particles-canvas { position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: 0; pointer-events: none; }
        .glow { position: fixed; border-radius: 50%; filter: blur(100px); opacity: 0.15; z-index: 0; pointer-events: none; animation: floatGlow 20s ease-in-out infinite; }
        .glow-1 { width: 400px; height: 400px; top: -100px; right: -100px; background: #6c3ce0; }
        .glow-2 { width: 350px; height: 350px; bottom: -80px; left: -80px; background: #f0883e; animation-delay: 5s; }
        .glow-3 { width: 250px; height: 250px; top: 50%; left: 50%; background: #1f6feb; animation-delay: 10s; transform: translate(-50%, -50%); }
        @keyframes floatGlow { 0%,100% { transform: translate(0,0) scale(1); } 25% { transform: translate(50px,-30px) scale(1.1); } 50% { transform: translate(-30px,50px) scale(0.9); } 75% { transform: translate(20px,20px) scale(1.05); } }
        .header { position: relative; z-index: 1; background: rgba(8,12,22,0.85); backdrop-filter: blur(20px); padding: 10px 16px; border-bottom: 1px solid rgba(255,255,255,0.04); display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; flex-wrap: wrap; gap: 6px; }
        .header-left { display: flex; align-items: center; gap: 8px; }
        .logo { font-size: 18px; font-weight: 900; background: linear-gradient(135deg, #58a6ff, #f0883e, #6c3ce0); background-size: 300% 300%; -webkit-background-clip: text; -webkit-text-fill-color: transparent; animation: gradientShift 4s ease-in-out infinite; }
        @keyframes gradientShift { 0%,100% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } }
        .badge { background: linear-gradient(135deg, #238636, #2ea043); color: white; font-size: 8px; font-weight: 600; padding: 2px 8px; border-radius: 12px; text-transform: uppercase; -webkit-text-fill-color: white; display: flex; align-items: center; gap: 3px; }
        .status-dot { width: 5px; height: 5px; border-radius: 50%; background: #2ea043; display: inline-block; animation: pulse 1.5s ease-in-out infinite; }
        @keyframes pulse { 0%,100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.5; transform: scale(0.8); } }
        .menu-buttons { display: flex; gap: 3px; flex-wrap: wrap; }
        .menu-buttons button { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.05); color: #8b949e; padding: 3px 10px; border-radius: 14px; font-size: 10px; font-weight: 500; cursor: pointer; transition: all 0.25s ease; font-family: inherit; }
        .menu-buttons button:hover { background: rgba(88,166,255,0.12); border-color: rgba(88,166,255,0.2); color: #58a6ff; transform: translateY(-1px); }
        .menu-buttons button.premium-btn:hover { background: rgba(240,136,62,0.12); border-color: rgba(240,136,62,0.2); color: #f0883e; }
        .menu-buttons button.danger-btn:hover { background: rgba(248,81,73,0.12); border-color: rgba(248,81,73,0.2); color: #f85149; }
        .menu-buttons button.admin-btn:hover { background: rgba(248,81,73,0.12); border-color: rgba(248,81,73,0.2); color: #f85149; }
        .chat { position: relative; z-index: 1; flex: 1; overflow-y: auto; padding: 14px 18px; display: flex; flex-direction: column; gap: 8px; scroll-behavior: smooth; }
        .chat::-webkit-scrollbar { width: 3px; }
        .chat::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 10px; }
        .message { max-width: 82%; padding: 8px 14px; border-radius: 12px; line-height: 1.5; word-wrap: break-word; white-space: pre-wrap; font-size: 13px; animation: messageSlide 0.2s ease-out; }
        @keyframes messageSlide { 0% { opacity: 0; transform: translateY(8px) scale(0.97); } 100% { opacity: 1; transform: translateY(0) scale(1); } }
        .user { align-self: flex-end; background: linear-gradient(135deg, #1f6feb, #6c3ce0); color: white; border-bottom-right-radius: 3px; }
        .bot { align-self: flex-start; background: rgba(22,27,34,0.9); backdrop-filter: blur(12px); border: 1px solid rgba(255,255,255,0.04); border-bottom-left-radius: 3px; }
        .bot a { color: #58a6ff; }
        .bot strong, .bot b { color: #f0883e; }
        .message img { max-width: 250px; max-height: 200px; border-radius: 6px; margin-bottom: 4px; border: 1px solid rgba(255,255,255,0.06); }
        .input-area { position: relative; z-index: 1; padding: 8px 14px 12px; border-top: 1px solid rgba(255,255,255,0.04); background: rgba(8,12,22,0.9); backdrop-filter: blur(20px); flex-shrink: 0; }
        .tools-row { display: flex; gap: 3px; flex-wrap: wrap; margin-bottom: 5px; }
        .tools-row button, .tools-row label { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.04); color: #6e7681; padding: 2px 10px; border-radius: 12px; font-size: 10px; font-weight: 500; cursor: pointer; transition: all 0.25s ease; font-family: inherit; }
        .tools-row button:hover, .tools-row label:hover { background: rgba(255,255,255,0.06); border-color: rgba(255,255,255,0.08); color: #e6edf3; }
        .tools-row input[type="file"] { display: none; }
        .input-row { display: flex; gap: 6px; align-items: center; }
        .input-row input { flex: 1; padding: 8px 14px; border-radius: 20px; border: 1px solid rgba(255,255,255,0.06); background: rgba(22,27,34,0.8); color: #e6edf3; font-size: 13px; outline: none; transition: all 0.3s ease; font-family: inherit; }
        .input-row input:focus { border-color: #58a6ff; box-shadow: 0 0 30px rgba(88,166,255,0.05); }
        .input-row input::placeholder { color: #484f58; }
        .input-row button { padding: 8px 20px; border-radius: 20px; border: none; background: linear-gradient(135deg, #1f6feb, #6c3ce0); color: white; font-weight: 600; font-size: 13px; cursor: pointer; transition: all 0.25s ease; font-family: inherit; white-space: nowrap; }
        .input-row button:hover { transform: scale(1.02); box-shadow: 0 4px 25px rgba(88,166,255,0.15); }
        .input-row button:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }
        .typing { color: #8b949e; font-size: 12px; padding: 4px 16px; align-self: flex-start; animation: pulse 1.2s ease-in-out infinite; }
        .welcome { text-align: center; padding: 25px 20px; color: #8b949e; }
        .welcome h2 { color: #e6edf3; margin-bottom: 4px; font-size: 20px; font-weight: 800; background: linear-gradient(135deg, #58a6ff, #f0883e); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .welcome p { font-size: 13px; opacity: 0.6; }
        .welcome .features { display: flex; gap: 10px; justify-content: center; margin-top: 10px; flex-wrap: wrap; }
        .welcome .features span { background: rgba(255,255,255,0.03); padding: 3px 12px; border-radius: 14px; font-size: 10px; border: 1px solid rgba(255,255,255,0.04); color: #6e7681; }
        @media (max-width: 640px) { .header { padding: 6px 10px; } .logo { font-size: 15px; } .menu-buttons button { font-size: 8px; padding: 2px 7px; } .message { max-width: 92%; font-size: 12px; padding: 6px 10px; } .chat { padding: 8px 10px; } .input-area { padding: 6px 10px 10px; } .input-row input { font-size: 12px; padding: 6px 12px; } .input-row button { padding: 6px 14px; font-size: 12px; } .tools-row button, .tools-row label { font-size: 9px; padding: 2px 8px; } .welcome h2 { font-size: 16px; } }
    </style>
</head>
<body>
    <canvas id="particles-canvas"></canvas>
    <div class="glow glow-1"></div>
    <div class="glow glow-2"></div>
    <div class="glow glow-3"></div>
    <header class="header">
        <div class="header-left"><span class="logo">🧠 AWESOME AI</span><span class="badge"><span class="status-dot"></span> ONLINE</span></div>
        <div class="menu-buttons">
            <button onclick="sendCommand('/status')">📊</button>
            <button class="premium-btn" onclick="sendCommand('/premium')">💎</button>
            <button onclick="sendCommand('/test')">🎁</button>
            <button onclick="sendCommand('/profile')">👤</button>
            <button onclick="sendCommand('/help')">❓</button>
            <button class="danger-btn" onclick="clearChat()">🧹</button>
            <button class="admin-btn" onclick="window.open('/admin?user_id=' + userId, '_blank')">👑</button>
        </div>
    </header>
    <div class="chat" id="chat">
        <div class="welcome">
            <h2>✨ AWESOME AI</h2>
            <p>Спрашивай что угодно — я отвечу, решу, поищу</p>
            <div class="features"><span>📸 Фото</span><span>🎤 Голос</span><span>🌐 Поиск</span><span>💵 Курсы</span><span>🧮 Математика</span><span>🎨 Рисование</span></div>
        </div>
    </div>
    <div class="input-area">
        <div class="tools-row">
            <label for="fileInput">📎</label>
            <input type="file" id="fileInput" accept="image/*" multiple onchange="handleFiles(this.files)">
            <button onclick="document.getElementById('fileInput').click()">📸</button>
            <button onclick="startRecording()">🎤</button>
            <button onclick="sendCommand('/draw ' + prompt('🎨 Что нарисовать?'))">🎨</button>
            <button onclick="sendCommand('/weather ' + prompt('🌤 Город?'))">🌤</button>
            <button onclick="sendCommand('/exchange')">💵</button>
            <button onclick="sendCommand('/crypto')">🪙</button>
        </div>
        <div class="input-row">
            <input id="input" placeholder="Напиши..." onkeydown="if(event.key==='Enter') send()" autofocus>
            <button id="sendBtn" onclick="send()">➤</button>
        </div>
    </div>
    <script>
        (function() {
            const canvas = document.getElementById('particles-canvas');
            const ctx = canvas.getContext('2d');
            let particles = []; const count = 50;
            function resize() { canvas.width = window.innerWidth; canvas.height = window.innerHeight; }
            window.addEventListener('resize', resize); resize();
            class Particle { constructor() { this.x = Math.random() * canvas.width; this.y = Math.random() * canvas.height; this.size = Math.random() * 2 + 0.5; this.speedX = (Math.random() - 0.5) * 0.3; this.speedY = (Math.random() - 0.5) * 0.3; this.opacity = Math.random() * 0.3 + 0.1; } update() { this.x += this.speedX; this.y += this.speedY; if (this.x < 0 || this.x > canvas.width) this.speedX *= -1; if (this.y < 0 || this.y > canvas.height) this.speedY *= -1; } draw() { ctx.beginPath(); ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2); ctx.fillStyle = `rgba(100,150,255,${this.opacity})`; ctx.fill(); } }
            for (let i = 0; i < count; i++) particles.push(new Particle());
            function animate() {
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                particles.forEach(p => { p.update(); p.draw(); });
                for (let i = 0; i < particles.length; i++) {
                    for (let j = i + 1; j < particles.length; j++) {
                        const dx = particles[i].x - particles[j].x;
                        const dy = particles[i].y - particles[j].y;
                        const dist = Math.sqrt(dx * dx + dy * dy);
                        if (dist < 100) { ctx.beginPath(); ctx.strokeStyle = `rgba(100,150,255,${0.03 * (1 - dist / 100)})`; ctx.lineWidth = 0.5; ctx.moveTo(particles[i].x, particles[i].y); ctx.lineTo(particles[j].x, particles[j].y); ctx.stroke(); }
                    }
                }
                requestAnimationFrame(animate);
            }
            animate();
        })();
        
        const chat = document.getElementById('chat');
        const input = document.getElementById('input');
        const sendBtn = document.getElementById('sendBtn');
        let filesToSend = [];
        let userId = Date.now();
        
        function addMessage(text, isUser, filePreview = null) {
            const welcome = chat.querySelector('.welcome');
            if (welcome) welcome.remove();
            const div = document.createElement('div');
            div.className = 'message ' + (isUser ? 'user' : 'bot');
            if (filePreview) {
                const img = document.createElement('img');
                img.src = filePreview;
                div.appendChild(img);
                div.appendChild(document.createElement('br'));
            }
            let formattedText = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
            formattedText = formattedText.replace(/\n/g, '<br>');
            div.innerHTML = formattedText;
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
        
        async function send() {
            const text = input.value.trim();
            if (!text && filesToSend.length === 0) return;
            input.value = '';
            sendBtn.disabled = true;
            setTyping(true);
            const formData = new FormData();
            formData.append('message', text || '');
            formData.append('user_id', userId);
            for (const file of filesToSend) formData.append('files', file);
            filesToSend = [];
            try {
                const response = await fetch('/api/chat_full', { method: 'POST', body: formData });
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
            chat.innerHTML = `<div class="welcome"><h2>✨ AWESOME AI</h2><p>Спрашивай что угодно — я отвечу, решу, поищу</p><div class="features"><span>📸 Фото</span><span>🎤 Голос</span><span>🌐 Поиск</span><span>💵 Курсы</span><span>🧮 Математика</span><span>🎨 Рисование</span></div></div>`;
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
# АДМИН-ПАНЕЛЬ (ПОЛНОСТЬЮ РАБОЧАЯ)
# ============================================================
@app.route('/admin')
def admin_panel():
    user_id = request.args.get('user_id', type=int)
    if not user_id or user_id != OWNER_ID:
        return "<h1 style='color:#f85149;'>🚫 ДОСТУП ЗАПРЕЩЁН</h1><p>Только владелец</p>", 403
    
    if not supabase:
        return "<h1 style='color:#f85149;'>❌ Supabase не подключен</h1>", 500
    
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
        response = supabase.table('users').select('*').execute()
        users = response.data
        total = len(users)
        premium_count = sum(1 for u in users if u.get('premium', 0) == 1)
        admin_count = sum(1 for u in users if u.get('is_admin', 0) == 1)
        
        banned_response = supabase.table('banned').select('*').execute()
        banned_count = len(banned_response.data)
        
        muted_response = supabase.table('muted').select('*').execute()
        muted_count = len(muted_response.data)
    except:
        users = []
        total = premium_count = admin_count = banned_count = muted_count = 0
    
    rows = ""
    for u in users:
        uid = u.get('user_id')
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
                <a href="?user_id={OWNER_ID}&action=giveprem&target_id={uid}" style="background:#2ea043;color:#fff;padding:2px 8px;border-radius:3px;text-decoration:none;font-size:11px;">💎+</a>
                <a href="?user_id={OWNER_ID}&action=delprem&target_id={uid}" style="background:#da3633;color:#fff;padding:2px 8px;border-radius:3px;text-decoration:none;font-size:11px;">💎-</a>
                <a href="?user_id={OWNER_ID}&action=giveadmin&target_id={uid}" style="background:#f0883e;color:#fff;padding:2px 8px;border-radius:3px;text-decoration:none;font-size:11px;">👑+</a>
                <a href="?user_id={OWNER_ID}&action=deladmin&target_id={uid}" style="background:#da3633;color:#fff;padding:2px 8px;border-radius:3px;text-decoration:none;font-size:11px;">👑-</a>
                <a href="?user_id={OWNER_ID}&action=ban&target_id={uid}" style="background:#da3633;color:#fff;padding:2px 8px;border-radius:3px;text-decoration:none;font-size:11px;">🚫</a>
                <a href="?user_id={OWNER_ID}&action=unban&target_id={uid}" style="background:#2ea043;color:#fff;padding:2px 8px;border-radius:3px;text-decoration:none;font-size:11px;">✅</a>
                <a href="?user_id={OWNER_ID}&action=mute&target_id={uid}" style="background:#f0883e;color:#fff;padding:2px 8px;border-radius:3px;text-decoration:none;font-size:11px;">🔇</a>
                <a href="?user_id={OWNER_ID}&action=unmute&target_id={uid}" style="background:#2ea043;color:#fff;padding:2px 8px;border-radius:3px;text-decoration:none;font-size:11px;">🔊</a>
            </td>
        </tr>
        '''
    
    if not rows:
        rows = '<tr><td colspan="6" style="text-align:center;color:#8b949e;padding:15px;">Нет пользователей</td></tr>'
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>👑 Админ-панель</title>
    <style>
        *{{margin:0;padding:0;box-sizing:border-box;}}body{{font-family:sans-serif;background:#0a0e17;color:#e6edf3;padding:20px;}}
        h1{{color:#58a6ff;font-size:20px;margin-bottom:4px;}}.sub{{color:#8b949e;font-size:13px;margin-bottom:15px;}}
        .stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:10px;margin-bottom:15px;}}
        .card{{background:#161b22;padding:10px 14px;border-radius:8px;border:1px solid #30363d;}}
        .card span{{color:#8b949e;font-size:10px;}}.card .num{{font-size:20px;font-weight:700;color:#58a6ff;}}
        .card .num.gold{{color:#f0883e;}}.card .num.red{{color:#f85149;}}
        .section{{background:#161b22;border-radius:8px;border:1px solid #30363d;padding:12px 16px;margin-bottom:12px;}}
        .section h2{{font-size:14px;margin-bottom:8px;color:#58a6ff;}}
        table{{width:100%;border-collapse:collapse;font-size:11px;}}
        th{{background:#1c2128;color:#8b949e;font-weight:600;padding:6px 8px;text-align:left;}}
        td{{padding:5px 8px;border-bottom:1px solid #30363d;}}
        tr:hover{{background:#1c2128;}}
        .back{{color:#58a6ff;text-decoration:none;}}
        @media(max-width:600px){{table{{font-size:9px;}}td,th{{padding:3px 4px;}}}}
    </style>
    </head>
    <body>
        <h1>👑 Админ-панель</h1>
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
    '''

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
    return jsonify({'status': 'ok', 'supabase': supabase is not None})

# ============================================================
# ЗАПУСК
# ============================================================
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print("=" * 60)
    print("🧠 AWESOME AI — ПОЛНАЯ ВЕРСИЯ (SUPABASE)")
    print("=" * 60)
    print(f"👑 Владелец ID: {OWNER_ID}")
    print(f"☁️ Supabase: {'✅ ПОДКЛЮЧЕН' if supabase else '❌ НЕ ПОДКЛЮЧЕН'}")
    print(f"🌐 http://localhost:{port}")
    print(f"👑 Админ-панель: http://localhost:{port}/admin?user_id={OWNER_ID}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=False)
