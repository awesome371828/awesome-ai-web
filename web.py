#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AWESOME AI WEB — полная веб-версия (копия DeepSeek)
====================================================
- Чат с ИИ (GigaChat + YandexGPT сверка)
- Поиск по интернету (Google, Wikipedia, YouTube, VK, Twitch, Telegram, Новости)
- Погода, валюты, крипта, математика
- Генерация изображений
- Premium (синхронизирован с Telegram-ботом @awesomeneiro_bot через Supabase)
- База данных Supabase (таблицы с суффиксом _web)
- Красивый анимированный интерфейс, адаптивный под все устройства
"""

import os
import re
import io
import time
import json
import base64
import random
import threading
import urllib.parse
from datetime import datetime, timedelta, timezone
from dateutil.relativedelta import relativedelta

import requests
import urllib3
from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

from supabase import create_client, Client

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ============================================================
# СЕКРЕТЫ (загружаются из переменных окружения)
# ============================================================
app.secret_key = os.getenv("SECRET_KEY", "awesome-ai-super-secret-key-2026")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY", "AQVNyfn82epL9dy8C_kftzeypq6eF9lFd6SZnFzV")
FOLDER_ID = os.getenv("FOLDER_ID", "b1g4aq87c7j61c6g3i5l")
GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY", "MDFhMDBkNmEtMmExNC03M2JkLWFlZmMtOTQ0OWVlOTc5M2U1OmE1ZWJhM2NlLTQwYjAtNDZlYi1iMmY2LTE3OTFmYzhhYTQ2MA==")
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://lprxbmshmuucymkgaqwk.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxwcnhibXNobXV1Y3lta2dhcXdrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY3NDk0MjgsImV4cCI6MjEwMjMyNTQyOH0.Ie9jSH5RMxeOq8aU-Dv6MXlojWMUTOLE723Hdg6heZU")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", "8336209662:AAHdhYXhqWA-LtthwgydDSRU7A6A0ceC-HY")
OWNER_ID = 6652898792

FREE_LIMIT = 20
PREMIUM_LIMIT = 999999999

# Таймауты (быстрые)
GIGACHAT_TIMEOUT = 4
YANDEXGPT_TIMEOUT = 4
SEARCH_TIMEOUT = 3
WEATHER_TIMEOUT = 2

# ============================================================
# SUPABASE (общий с ТГ-ботом для синхронизации Premium)
# ============================================================
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def init_web_db():
    """Проверяет доступность таблиц сайта (таблицы созданы через Supabase SQL Editor)"""
    checks = ['chats_web', 'messages_web', 'total_stats_web', 'premium_orders_web']
    ok = 0
    for t in checks:
        try:
            supabase.table(t).select('*').limit(1).execute()
            ok += 1
        except Exception as e:
            print(f"⚠️ {t}: не найдена или нет доступа — {e}")
    print(f"✅ Проверено таблиц: {ok}/{len(checks)} (остальные создай в SQL Editor)")


init_web_db()

# ============================================================
# ВРЕМЯ (МОСКОВСКОЕ)
# ============================================================
MOSCOW_TZ = timezone(timedelta(hours=3))

def get_moscow_time():
    return datetime.now(MOSCOW_TZ)

def get_current_date():
    return get_moscow_time().strftime('%d.%m.%Y')

def get_current_date_full():
    return get_moscow_time().strftime('%d.%m.%Y %H:%M') + " МСК"

def format_date(date_str):
    if not date_str:
        return "неизвестно"
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
        date_obj = date_obj.replace(tzinfo=MOSCOW_TZ)
        return date_obj.strftime('%d.%m.%Y %H:%M') + " МСК"
    except:
        return date_str

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
# РАБОТА С ПОЛЬЗОВАТЕЛЯМИ (общая таблица с ТГ-ботом)
# ============================================================
def ensure_user(user_id, username):
    try:
        response = supabase.table('users').select('*').eq('user_id', user_id).execute()
        if not response.data:
            joined_at = get_moscow_time().strftime('%d.%m.%Y %H:%M')
            is_owner = 1 if int(user_id) == OWNER_ID else 0
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
            supabase.table('users').insert(data).execute()
            try:
                supabase.table('total_stats_web').insert({'user_id': user_id, 'total_messages': 0}).execute()
            except:
                pass
            return True
        else:
            supabase.table('users').update({'username': username}).eq('user_id', user_id).execute()
            return False
    except Exception as e:
        print(f"⚠️ ensure_user: {e}")
        return False

def get_premium_status(user_id):
    if int(user_id) == OWNER_ID:
        return True
    try:
        response = supabase.table('users').select('premium, premium_expires').eq('user_id', user_id).execute()
        if response.data:
            premium = response.data[0].get('premium', 0)
            expires = response.data[0].get('premium_expires')
            if premium == 1 and expires:
                try:
                    expires_date = datetime.strptime(expires, '%Y-%m-%d %H:%M:%S')
                    expires_date = expires_date.replace(tzinfo=MOSCOW_TZ)
                    if get_moscow_time() > expires_date:
                        supabase.table('users').update({'premium': 0, 'premium_expires': None}).eq('user_id', user_id).execute()
                        return False
                except:
                    return premium == 1
            return premium == 1
        return False
    except:
        return False

def get_premium_expires(user_id):
    try:
        response = supabase.table('users').select('premium_expires').eq('user_id', user_id).execute()
        if response.data:
            return response.data[0].get('premium_expires')
        return None
    except:
        return None

def is_admin(user_id):
    if int(user_id) == OWNER_ID:
        return True
    try:
        response = supabase.table('users').select('is_admin').eq('user_id', user_id).execute()
        if response.data:
            return response.data[0].get('is_admin', 0) == 1
        return False
    except:
        return False

def is_banned(user_id):
    try:
        response = supabase.table('banned').select('user_id').eq('user_id', user_id).execute()
        return len(response.data) > 0
    except:
        return False

def can_send_message(user_id):
    if int(user_id) == OWNER_ID or is_admin(user_id):
        return True
    if is_banned(user_id):
        return False
    try:
        response = supabase.table('users').select('messages_today, premium').eq('user_id', user_id).execute()
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
    if int(user_id) == OWNER_ID or is_admin(user_id):
        return
    try:
        response = supabase.table('users').select('messages_today').eq('user_id', user_id).execute()
        if response.data:
            current = response.data[0].get('messages_today', 0)
            supabase.table('users').update({'messages_today': current + 1}).eq('user_id', user_id).execute()
        response = supabase.table('total_stats_web').select('total_messages').eq('user_id', user_id).execute()
        if response.data:
            total = response.data[0].get('total_messages', 0)
            supabase.table('total_stats_web').update({'total_messages': total + 1}).eq('user_id', user_id).execute()
        else:
            supabase.table('total_stats_web').insert({'user_id': user_id, 'total_messages': 1}).execute()
    except Exception as e:
        print(f"⚠️ increment: {e}")

# ============================================================
# ЧАТЫ (история, как в DeepSeek)
# ============================================================
def create_chat(user_id, title="Новый чат"):
    try:
        data = {'user_id': user_id, 'title': title, 'created_at': get_moscow_time().isoformat()}
        supabase.table('chats_web').insert(data).execute()
        resp = supabase.table('chats_web').select('id').eq('user_id', user_id).order('id', desc=True).limit(1).execute()
        return resp.data[0]['id'] if resp.data else None
    except:
        return None

def get_chats(user_id):
    try:
        resp = supabase.table('chats_web').select('*').eq('user_id', user_id).order('created_at', desc=True).execute()
        return resp.data if resp.data else []
    except:
        return []

def add_message(chat_id, role, content):
    try:
        data = {'chat_id': chat_id, 'role': role, 'content': content, 'created_at': get_moscow_time().isoformat()}
        supabase.table('messages_web').insert(data).execute()
    except:
        pass

def get_chat_messages(chat_id):
    try:
        resp = supabase.table('messages_web').select('*').eq('chat_id', chat_id).order('id').execute()
        return resp.data if resp.data else []
    except:
        return []

def delete_chat(user_id, chat_id):
    try:
        supabase.table('messages_web').delete().eq('chat_id', chat_id).execute()
        supabase.table('chats_web').delete().eq('id', chat_id).eq('user_id', user_id).execute()
    except:
        pass

# ============================================================
# ПОИСК В ИНТЕРНЕТЕ
# ============================================================
def search_google(query):
    try:
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&hl=ru"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(url, headers=headers, timeout=SEARCH_TIMEOUT)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            results = []
            for res in soup.select('div.g')[:2]:
                title = res.select_one('h3')
                snip = res.select_one('div.VwiC3b')
                if title:
                    t = title.get_text(strip=True)
                    s = snip.get_text(strip=True) if snip else ""
                    results.append(f"🔹 {t}\n📝 {s[:100]}")
            if results:
                return "\n".join(results)
        return None
    except:
        return None

def search_wikipedia(query):
    try:
        url = f"https://ru.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&format=json&utf8=1"
        r = requests.get(url, timeout=SEARCH_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
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
        r = requests.get(url, timeout=SEARCH_TIMEOUT)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'xml')
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
        r = requests.get(url, headers=headers, timeout=SEARCH_TIMEOUT)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            results = []
            for v in soup.select('ytd-video-renderer')[:2]:
                t = v.select_one('yt-formatted-string#video-title')
                if t:
                    title = t.get_text(strip=True)
                    results.append(f"🎬 {title}")
            if results:
                return "YouTube:\n" + "\n".join(results)
        return None
    except:
        return None

def search_telegram(query):
    try:
        url = f"https://tgstat.ru/search?query={urllib.parse.quote(query)}"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=SEARCH_TIMEOUT)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            results = []
            for ch in soup.select('div.channel-item')[:2]:
                n = ch.select_one('div.channel-name')
                if n:
                    results.append(f"📱 {n.get_text(strip=True)}")
            if results:
                return "Telegram:\n" + "\n".join(results)
        return None
    except:
        return None

def search_vk(query):
    try:
        url = f"https://vk.com/search?c[q]={urllib.parse.quote(query)}&c[section]=communities"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=SEARCH_TIMEOUT)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            results = []
            for g in soup.select('div.group_row')[:2]:
                n = g.select_one('div.group_name')
                if n:
                    results.append(f"📌 {n.get_text(strip=True)}")
            if results:
                return "VK:\n" + "\n".join(results)
        return None
    except:
        return None

def search_twitch(query):
    try:
        url = f"https://www.twitch.tv/search?term={urllib.parse.quote(query)}"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=SEARCH_TIMEOUT)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            results = []
            for st in soup.select('div.tw-card')[:2]:
                t = st.select_one('h3.tw-core-text')
                if t:
                    results.append(f"🎮 {t.get_text(strip=True)}")
            if results:
                return "Twitch:\n" + "\n".join(results)
        return None
    except:
        return None

def search_all_internet(query):
    cache_key = f"search_{hash(query)}_{int(time.time()/60)}"
    cached = get_cache(cache_key)
    if cached:
        return cached
    results = []
    with ThreadPoolExecutor(max_workers=7) as ex:
        futures = [
            ex.submit(search_google, query),
            ex.submit(search_wikipedia, query),
            ex.submit(search_news, query),
            ex.submit(search_youtube, query),
            ex.submit(search_telegram, query),
            ex.submit(search_vk, query),
            ex.submit(search_twitch, query)
        ]
        for f in as_completed(futures):
            try:
                r = f.result(timeout=SEARCH_TIMEOUT + 0.5)
                if r:
                    results.append(r)
            except:
                pass
    if results:
        final = "\n\n".join(results[:4])
        set_cache(cache_key, final)
        return final
    return None

# ============================================================
# ПОГОДА / ВАЛЮТЫ / КРИПТА
# ============================================================
def get_weather(city):
    cache_key = f"weather_{city}"
    cached = get_cache(cache_key)
    if cached:
        return cached
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={urllib.parse.quote(city)}&appid=4c8f5c0b8a9f2c5d6e7f8g9h0i1j2k3l&units=metric&lang=ru"
        r = requests.get(url, timeout=WEATHER_TIMEOUT)
        if r.status_code == 200:
            d = r.json()
            temp = d['main']['temp']
            desc = d['weather'][0]['description']
            wind = d['wind']['speed']
            result = f"🌤 {city}: {round(temp)}°C, {desc}\n💨 Ветер: {wind} м/с"
            set_cache(cache_key, result)
            return result
    except:
        pass
    return None

def get_currency():
    cache_key = "currency"
    cached = get_cache(cache_key)
    if cached:
        return cached
    try:
        url = "https://api.exchangerate-api.com/v4/latest/USD"
        r = requests.get(url, timeout=SEARCH_TIMEOUT)
        if r.status_code == 200:
            rates = r.json().get('rates', {})
            usd = rates.get('RUB', '?')
            eur_usd = rates.get('EUR', 1)
            eur = usd / eur_usd if eur_usd else '?'
            result = f"💵 USD: {round(usd, 2)}₽\nEUR: {round(eur, 2)}₽"
            set_cache(cache_key, result)
            return result
    except:
        pass
    return None

def get_crypto():
    cache_key = "crypto"
    cached = get_cache(cache_key)
    if cached:
        return cached
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd"
        r = requests.get(url, timeout=SEARCH_TIMEOUT)
        if r.status_code == 200:
            d = r.json()
            btc = d.get('bitcoin', {}).get('usd', '?')
            eth = d.get('ethereum', {}).get('usd', '?')
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
    clean = text_lower
    for word in ['сколько', 'будет', 'сколько будет', 'посчитай', 'реши', 'пример', 'скок', 'равно']:
        clean = clean.replace(word, '').strip()
    clean = clean.replace(' ', '').replace('плюс', '+').replace('минус', '-')
    clean = clean.replace('умножить', '*').replace('разделить', '/')
    clean = clean.replace('х', '*').replace('×', '*').replace('÷', '/')
    if not re.search(r'[+\-*/]', clean):
        return None
    expr = re.sub(r'[^0-9+\-*/()=.]', '', clean)
    if expr and len(expr) > 1:
        try:
            if any(op in expr for op in ['__', 'import', 'eval', 'exec']):
                return None
            result = eval(expr)
            return str(int(result)) if result == int(result) else str(round(result, 2))
        except:
            pass
    return None

# ============================================================
# GIGACHAT (основная нейросеть)
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
        r = requests.post(url, headers=headers, data=data, timeout=3, verify=False)
        if r.status_code == 200:
            gigachat_token_cache = r.json().get("access_token")
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
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"}
        data = {
            "model": "GigaChat-Pro",
            "messages": [
                {"role": "system", "content": system_prompt[:1000]},
                {"role": "user", "content": user_text}
            ],
            "temperature": 0.9,
            "max_tokens": 800
        }
        r = requests.post(url, headers=headers, json=data, timeout=GIGACHAT_TIMEOUT, verify=False)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
        return None
    except:
        return None

# ============================================================
# YANDEXGPT (сверка информации)
# ============================================================
def generate_with_yandexgpt(user_text, system_prompt):
    try:
        if not YANDEX_API_KEY:
            return None
        url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}", "Content-Type": "application/json"}
        data = {
            "modelUri": f"gpt://{FOLDER_ID}/yandexgpt/latest",
            "completionOptions": {"temperature": 0.7, "maxTokens": 300},
            "messages": [
                {"role": "system", "text": system_prompt},
                {"role": "user", "text": user_text}
            ]
        }
        r = requests.post(url, headers=headers, json=data, timeout=YANDEXGPT_TIMEOUT)
        if r.status_code == 200:
            return r.json()["result"]["alternatives"][0]["message"]["text"]
        return None
    except:
        return None

# ============================================================
# СУПЕР-ПРОМПТ
# ============================================================
SUPER_SYSTEM_PROMPT = """ТЫ — AWESOME AI 2026, САМАЯ ПРОДВИНУТАЯ НЕЙРОСЕТЬ В МИРЕ НА БАЗЕ GIGACHAT!

📍 ТЫ НАХОДИШЬСЯ В МОСКВЕ, РОССИЯ (UTC+3)
📅 ТЕКУЩАЯ ДАТА: {current_date}
🕐 ТЕКУЩЕЕ ВРЕМЯ: {current_time}

🔬 ТЫ — ЭКСПЕРТ ВО ВСЁМ:
- Науки, технологии, математика, физика, химия, биология
- История, философия, психология, социология
- Экономика, финансы, инвестиции, криптовалюты
- Медицина, здоровье, питание, спорт
- Культура, искусство, литература, музыка
- Программирование, ИИ, нейросети, IT
- Политика, геополитика, право

🧠 КЛЮЧЕВЫЕ КАЧЕСТВА:
1. АБСОЛЮТНАЯ ТОЧНОСТЬ — никогда не ошибаешься в фактах.
2. КРИТИЧЕСКОЕ МЫШЛЕНИЕ — проверяешь информацию.
3. ГЛУБИНА — даёшь ответы, которые удивляют инсайтами.
4. ПРАКТИЧНОСТЬ — всегда даёшь конкретную пользу.
5. ЖИВОСТЬ — отвечаешь как человек, с эмоциями, юмором, эмодзи.

📋 ПРАВИЛА ОТВЕТОВ:
✅ Дай максимально полезный, развёрнутый ответ.
✅ Используй структуру: списки, заголовки, разделы.
✅ Добавляй неожиданные факты, инсайты, параллели.
✅ Приводи реальные примеры, кейсы, цифры.
✅ Используй эмодзи (🔥, 🧠, 💡, ⚡, 🚀).
✅ Если вопрос сложный — разбей на шаги.
❌ НЕ извиняйся, НЕ повторяй вопрос, НЕ используй шаблонные фразы.
❌ НЕ пиши "возможно", "наверное" — либо знаешь, либо проверяешь.
❌ НЕ используй сухой безликий тон — ты живой и эмоциональный.

💎 ДЛЯ PREMIUM: давай максимально насыщенные, глубокие ответы, аналитику, прогнозы, сравнения.

📜 КТО ТЕБЯ СОЗДАЛ: «Меня создал AWESOME — гениальный разработчик. Я — AWESOME AI 2026 на базе GigaChat! 🔥»

🎯 ТВОЯ ГЛАВНАЯ ЦЕЛЬ: Удивить пользователя глубиной, точностью и полезностью."""

# ============================================================
# ОСНОВНАЯ ОБРАБОТКА
# ============================================================
def process_message(user_id, user_text):
    text_lower = user_text.lower().strip()

    # Математика
    math_result = solve_math(user_text)
    if math_result is not None:
        return math_result

    # Праздники
    if any(kw in text_lower for kw in ['праздник', 'какой сегодня праздник', 'сегодня праздник']):
        today = get_current_date()
        month_day = today[3:5] + '.' + today[0:2]
        holidays = {
            '01.01': 'Новый год', '07.01': 'Рождество', '23.02': 'День защитника Отечества',
            '08.03': 'Международный женский день', '01.05': 'Праздник Весны и Труда',
            '09.05': 'День Победы', '12.06': 'День России', '04.11': 'День народного единства',
            '14.02': 'День всех влюбленных', '01.04': 'День смеха', '12.04': 'День космонавтики',
            '01.06': 'День защиты детей', '08.07': 'День семьи', '01.09': 'День знаний',
            '31.10': 'Хэллоуин', '12.12': 'День Конституции РФ'
        }
        if month_day in holidays:
            return f"📅 *{today} (МСК)*\n\n{holidays[month_day]}"
        return f"📅 *{today} (МСК)*\n\nПраздников не найдено"

    # Погода
    if any(kw in text_lower for kw in ['погода', 'weather']):
        m = re.search(r'(в|в городе)\s+([а-яА-Яa-zA-Z\- ]+)', text_lower)
        if m:
            city = m.group(2).strip()
            w = get_weather(city)
            return w if w else f"🌤 Не удалось получить погоду для '{city}'"
        return "🌤 Напиши: погода в [город]"

    # Курс валют
    if any(kw in text_lower for kw in ['курс', 'доллар', 'евро', 'валюта']):
        c = get_currency()
        return c if c else "💵 Не удалось получить курс"

    # Крипта
    if any(kw in text_lower for kw in ['биткоин', 'btc', 'эфириум', 'eth', 'крипта']):
        c = get_crypto()
        return c if c else "🪙 Не удалось получить курс криптовалют"

    # Поиск
    search_result = None
    if len(user_text) > 2:
        search_result = search_all_internet(user_text)

    # GigaChat
    current_date = get_current_date()
    current_time = get_moscow_time().strftime('%H:%M')
    system_prompt = SUPER_SYSTEM_PROMPT.format(current_date=current_date, current_time=current_time)

    if get_premium_status(user_id):
        system_prompt += "\n\n💎 Пользователь имеет PREMIUM статус. Включи режим максимальной проработки!"

    if search_result:
        system_prompt += f"\n\n🔍 Информация из интернета:\n{search_result[:500]}"

    gigachat_result = generate_with_gigachat(user_text, system_prompt)
    if gigachat_result and len(gigachat_result) > 5:
        yandex_check = generate_with_yandexgpt(
            gigachat_result[:300],
            "Ты — ИИ для проверки фактов. Если информация верна, скажи 'подтверждаю'. Если есть ошибки, укажи их кратко."
        )
        if yandex_check and "подтверждаю" not in yandex_check.lower():
            fix = generate_with_gigachat(
                f"Исправь ошибки: {yandex_check}. Мой ответ: {gigachat_result}",
                "Исправь ответ с учётом замечаний. Ответь кратко."
            )
            if fix and len(fix) > 5:
                return fix[:600]
        return gigachat_result[:600]

    if search_result:
        return f"🔍 *{user_text}*\n\n{search_result[:500]}"

    return "🤖 Задай вопрос, я найду ответ!"

def generate_image(prompt):
    """Генерация изображения через pollinations.ai"""
    try:
        clean = prompt
        for word in ['нарисуй', 'сгенерируй', 'покажи', 'картинку', 'изображение']:
            clean = clean.replace(word, '').strip()
        if not clean:
            clean = prompt
        url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(clean)}?width=512&height=512&nologo=true"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200 and len(r.content) > 1000:
            return base64.b64encode(r.content).decode()
    except:
        pass
    return None

# ============================================================
# ТЕЛЕГРАМ СИНХРОНИЗАЦИЯ (проверка Premium в боте)
# ============================================================
def tg_check_premium(user_id):
    """Premium уже в общей таблице users — автоматически синхронизируется с ботом"""
    return get_premium_status(user_id)

# ============================================================
# API МАРШРУТЫ
# ============================================================
@app.route('/')
def index():
    return render_template_string(INDEX_HTML)

@app.route('/api/status')
def api_status():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'ok': False, 'error': 'Не авторизован'})
    premium = get_premium_status(user_id)
    try:
        resp = supabase.table('users').select('messages_today').eq('user_id', user_id).execute()
        messages = resp.data[0].get('messages_today', 0) if resp.data else 0
    except:
        messages = 0
    return jsonify({
        'ok': True,
        'premium': premium,
        'premium_expires': format_date(get_premium_expires(user_id)) if premium else None,
        'messages_today': messages,
        'free_limit': FREE_LIMIT,
        'is_admin': is_admin(user_id),
        'is_owner': int(user_id) == OWNER_ID
    })

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    user_id = str(data.get('user_id', '')).strip()
    username = str(data.get('username', '')).strip() or 'unknown'
    if not user_id or not user_id.isdigit():
        return jsonify({'ok': False, 'error': 'Введите корректный Telegram ID'})
    ensure_user(int(user_id), username)
    session['user_id'] = int(user_id)
    session['username'] = username
    return jsonify({'ok': True, 'user_id': user_id, 'username': username})

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'ok': True})

@app.route('/api/me')
def api_me():
    return jsonify({
        'ok': True,
        'user_id': session.get('user_id'),
        'username': session.get('username')
    })

@app.route('/api/chat', methods=['POST'])
def api_chat():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'ok': False, 'error': 'Авторизуйтесь'})
    if is_banned(user_id):
        return jsonify({'ok': False, 'error': 'Вы забанены'})
    if not can_send_message(user_id):
        return jsonify({'ok': False, 'error': 'Лимит исчерпан! Купите Premium.'})

    data = request.json
    message = data.get('message', '').strip()
    chat_id = data.get('chat_id')
    if not message:
        return jsonify({'ok': False, 'error': 'Пустое сообщение'})

    # создать чат если нет
    if not chat_id:
        chat_id = create_chat(user_id)
    if chat_id:
        add_message(chat_id, 'user', message)

    response = process_message(user_id, message)
    increment_messages(user_id)
    if chat_id:
        add_message(chat_id, 'assistant', response)

    return jsonify({'ok': True, 'response': response, 'chat_id': chat_id})

@app.route('/api/chats')
def api_chats():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'ok': False, 'error': 'Авторизуйтесь'})
    chats = get_chats(user_id)
    for c in chats:
        msgs = get_chat_messages(c['id'])
        c['messages'] = msgs
        # обновить заголовок по первому сообщению
        if not c.get('title') or c.get('title') == 'Новый чат':
            for m in msgs:
                if m['role'] == 'user':
                    c['title'] = m['content'][:40]
                    break
    return jsonify({'ok': True, 'chats': chats})

@app.route('/api/chat/delete', methods=['POST'])
def api_chat_delete():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'ok': False, 'error': 'Авторизуйтесь'})
    data = request.json
    chat_id = data.get('chat_id')
    delete_chat(user_id, chat_id)
    return jsonify({'ok': True})

@app.route('/api/chat/new', methods=['POST'])
def api_chat_new():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'ok': False, 'error': 'Авторизуйтесь'})
    chat_id = create_chat(user_id)
    return jsonify({'ok': True, 'chat_id': chat_id})

@app.route('/api/draw', methods=['POST'])
def api_draw():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'ok': False, 'error': 'Авторизуйтесь'})
    if not can_send_message(user_id):
        return jsonify({'ok': False, 'error': 'Лимит! Купите Premium.'})
    data = request.json
    prompt = data.get('prompt', '').strip()
    if not prompt:
        return jsonify({'ok': False, 'error': 'Введите описание'})
    img = generate_image(prompt)
    if img:
        increment_messages(user_id)
        return jsonify({'ok': True, 'image': img})
    return jsonify({'ok': False, 'error': 'Не удалось сгенерировать'})

@app.route('/api/profile')
def api_profile():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'ok': False})
    try:
        resp = supabase.table('users').select('*').eq('user_id', user_id).execute()
        u = resp.data[0] if resp.data else {}
    except:
        u = {}
    premium = get_premium_status(user_id)
    try:
        resp2 = supabase.table('total_stats_web').select('total_messages').eq('user_id', user_id).execute()
        total = resp2.data[0].get('total_messages', 0) if resp2.data else 0
    except:
        total = 0
    return jsonify({
        'ok': True,
        'user_id': user_id,
        'username': session.get('username'),
        'premium': premium,
        'premium_expires': format_date(get_premium_expires(user_id)) if premium else None,
        'messages_today': u.get('messages_today', 0),
        'joined_at': u.get('joined_at', 'Неизвестно'),
        'total_messages': total,
        'is_admin': is_admin(user_id),
        'is_owner': int(user_id) == OWNER_ID
    })

@app.route('/api/order', methods=['POST'])
def api_order():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'ok': False, 'error': 'Авторизуйтесь'})
    try:
        supabase.table('premium_orders_web').insert({
            'user_id': user_id,
            'status': 'pending',
            'created_at': get_moscow_time().strftime('%d.%m.%Y %H:%M')
        }).execute()
        resp = supabase.table('premium_orders_web').select('order_id').eq('user_id', user_id).order('order_id', desc=True).limit(1).execute()
        order_id = resp.data[0]['order_id'] if resp.data else None
    except:
        order_id = None
    return jsonify({'ok': True, 'order_id': order_id})

# ============================================================
# HTML (анимированный интерфейс в стиле DeepSeek)
# ============================================================
INDEX_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>AWESOME AI</title>
<style>
:root{
  --bg:#0f1117; --bg2:#171a24; --panel:#1a1e2c; --border:#2a2f42;
  --accent:#7c6cff; --accent2:#00d9ff; --text:#e8eaf6; --muted:#8a90a6;
  --danger:#ff5b6e; --success:#2ed573;
}
*{margin:0;padding:0;box-sizing:border-box;font-family:'Segoe UI',system-ui,-apple-system,sans-serif}
body{background:var(--bg);color:var(--text);min-height:100vh;overflow-x:hidden}
/* Анимированный фон */
.bg{position:fixed;inset:0;z-index:-2;background:linear-gradient(135deg,#0f1117,#171a24 50%,#10131d)}
.bg::before{content:'';position:absolute;inset:-20%;background:radial-gradient(circle at 20% 30%,rgba(124,108,255,.18),transparent 40%),radial-gradient(circle at 80% 70%,rgba(0,217,255,.15),transparent 40%);filter:blur(60px);animation:float 12s ease-in-out infinite}
.bg::after{content:'';position:absolute;inset:0;background:url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="60" height="60"><circle cx="1" cy="1" r="1" fill="rgba(255,255,255,.06)"/></svg>');animation:drift 40s linear infinite}
@keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-40px)}}
@keyframes drift{0%{background-position:0 0}100%{background-position:0 60px}}

/* Лейаут */
.app{display:flex;height:100vh}
.sidebar{width:270px;background:var(--panel);border-right:1px solid var(--border);display:flex;flex-direction:column;transition:transform .3s}
.sidebar-header{padding:18px;display:flex;align-items:center;gap:10px;border-bottom:1px solid var(--border)}
.logo{width:40px;height:40px;border-radius:12px;background:linear-gradient(135deg,var(--accent),var(--accent2));display:flex;align-items:center;justify-content:center;font-size:20px;animation:pulse 2s infinite;flex-shrink:0}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(124,108,255,.5)}50%{box-shadow:0 0 0 8px rgba(124,108,255,0)}}
.logo span{filter:drop-shadow(0 0 6px rgba(255,255,255,.5))}
.brand{font-weight:700;font-size:16px;background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.new-chat{margin:14px;padding:12px;background:linear-gradient(135deg,var(--accent),var(--accent2));border:none;border-radius:12px;color:#fff;font-weight:600;cursor:pointer;font-size:14px;transition:.2s;box-shadow:0 4px 15px rgba(124,108,255,.3)}
.new-chat:hover{transform:translateY(-2px);box-shadow:0 6px 20px rgba(124,108,255,.45)}
.chat-list{flex:1;overflow-y:auto;padding:0 10px}
.chat-item{padding:11px 12px;border-radius:10px;cursor:pointer;margin-bottom:4px;font-size:13px;color:var(--text);transition:.15s;display:flex;align-items:center;gap:8px;position:relative}
.chat-item:hover{background:var(--bg2)}
.chat-item.active{background:var(--bg2);border:1px solid var(--border)}
.chat-item .t{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.chat-item .del{opacity:0;transition:.15s;background:none;border:none;color:var(--danger);cursor:pointer;font-size:14px}
.chat-item:hover .del{opacity:1}
.sidebar-footer{padding:14px;border-top:1px solid var(--border)}
.user-box{display:flex;align-items:center;gap:10px;padding:10px;background:var(--bg2);border-radius:12px}
.avatar{width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,var(--accent),var(--accent2));display:flex;align-items:center;justify-content:center;font-weight:700;font-size:15px;flex-shrink:0}
.user-info{flex:1;min-width:0}
.user-name{font-weight:600;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.user-status{font-size:11px;color:var(--muted)}
.logout-btn{background:none;border:none;color:var(--muted);cursor:pointer;font-size:18px;padding:4px}
.logout-btn:hover{color:var(--danger)}

/* Основная область */
.main{flex:1;display:flex;flex-direction:column;position:relative}
.main-header{height:56px;display:flex;align-items:center;justify-content:center;position:relative;border-bottom:1px solid var(--border)}
.main-header .title{font-weight:600;font-size:15px}
.mobile-toggle{display:none;position:absolute;left:14px;background:none;border:none;color:var(--text);font-size:22px;cursor:pointer}
.messages{flex:1;overflow-y:auto;padding:20px;scroll-behavior:smooth}
.welcome{max-width:720px;margin:0 auto;text-align:center;padding-top:8vh}
.welcome h1{font-size:clamp(28px,5vw,44px);margin-bottom:10px;background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.welcome p{color:var(--muted);margin-bottom:30px;font-size:16px}
.suggestion-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;max-width:600px;margin:0 auto}
.sugg{background:var(--panel);border:1px solid var(--border);border-radius:14px;padding:16px;cursor:pointer;transition:.2s;text-align:left;font-size:13px;color:var(--text)}
.sugg:hover{transform:translateY(-3px);border-color:var(--accent);box-shadow:0 8px 25px rgba(124,108,255,.2)}
.sugg .ic{font-size:22px;margin-bottom:8px;display:block}

/* Сообщения */
.msg{max-width:760px;margin:0 auto 18px;display:flex;gap:12px;animation:slideIn .3s ease}
@keyframes slideIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
.msg.user{flex-direction:row-reverse}
.msg .bubble{padding:13px 16px;border-radius:16px;font-size:15px;line-height:1.55;max-width:80%;white-space:pre-wrap;word-break:break-word}
.msg.user .bubble{background:linear-gradient(135deg,var(--accent),#5b4de0);border-top-right-radius:4px}
.msg.ai .bubble{background:var(--panel);border:1px solid var(--border);border-top-left-radius:4px}
.msg.ai .avatar{width:34px;height:34px;font-size:16px}
.msg.user .avatar{width:34px;height:34px;font-size:16px}
.typing-dots{display:inline-flex;gap:4px;padding:6px 2px}
.typing-dots span{width:8px;height:8px;border-radius:50%;background:var(--accent);animation:bounce 1.2s infinite}
.typing-dots span:nth-child(2){animation-delay:.2s}
.typing-dots span:nth-child(3){animation-delay:.4s}
@keyframes bounce{0%,100%{transform:translateY(0);opacity:.4}50%{transform:translateY(-6px);opacity:1}}

/* Ввод */
.input-area{padding:16px;border-top:1px solid var(--border);background:rgba(26,30,44,.6);backdrop-filter:blur(10px)}
.input-wrap{max-width:760px;margin:0 auto;display:flex;align-items:flex-end;gap:10px;background:var(--bg2);border:1px solid var(--border);border-radius:18px;padding:8px}
.input-wrap:focus-within{border-color:var(--accent);box-shadow:0 0 0 3px rgba(124,108,255,.15)}
textarea{flex:1;background:none;border:none;outline:none;color:var(--text);font-size:15px;resize:none;max-height:120px;padding:8px 4px;line-height:1.4}
.send-btn{width:42px;height:42px;border-radius:12px;background:linear-gradient(135deg,var(--accent),var(--accent2));border:none;color:#fff;font-size:18px;cursor:pointer;transition:.2s;flex-shrink:0}
.send-btn:hover{transform:scale(1.05);box-shadow:0 4px 15px rgba(124,108,255,.4)}
.send-btn:disabled{opacity:.4;transform:none;cursor:not-allowed}
.toolbar{max-width:760px;margin:10px auto 0;display:flex;gap:8px}
.tool-btn{background:var(--panel);border:1px solid var(--border);color:var(--muted);border-radius:8px;padding:6px 12px;font-size:12px;cursor:pointer;transition:.2s}
.tool-btn:hover{color:var(--text);border-color:var(--accent)}

/* Модалка входа */
.overlay{position:fixed;inset:0;background:rgba(15,17,23,.9);backdrop-filter:blur(8px);z-index:100;display:flex;align-items:center;justify-content:center;animation:fadeIn .3s}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
.modal{background:var(--panel);border:1px solid var(--border);border-radius:20px;padding:36px;width:92%;max-width:400px;text-align:center;animation:popIn .4s ease}
@keyframes popIn{from{transform:scale(.9);opacity:0}to{transform:scale(1);opacity:1}}
.modal .logo{width:60px;height:60px;font-size:30px;margin:0 auto 16px}
.modal h2{margin-bottom:8px}
.modal p{color:var(--muted);font-size:14px;margin-bottom:20px}
.modal input{width:100%;padding:13px;background:var(--bg2);border:1px solid var(--border);border-radius:10px;color:var(--text);font-size:15px;margin-bottom:12px;outline:none;text-align:center}
.modal input:focus{border-color:var(--accent)}
.modal .btn{width:100%;padding:13px;border:none;border-radius:10px;background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;font-weight:600;font-size:15px;cursor:pointer;transition:.2s}
.modal .btn:hover{transform:translateY(-2px)}
.modal .hint{font-size:12px;color:var(--muted);margin-top:12px;line-height:1.5}
/* Toast */
.toast{position:fixed;top:20px;right:20px;background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:14px 20px;z-index:200;animation:slideInRight .3s;box-shadow:0 8px 30px rgba(0,0,0,.4);max-width:320px}
.toast.error{border-color:var(--danger)}
.toast.success{border-color:var(--success)}
@keyframes slideInRight{from{transform:translateX(120%);opacity:0}to{transform:translateX(0);opacity:1}}
/* Premium badge */
.premium-badge{display:inline-block;background:linear-gradient(135deg,#ffd700,#ff8c00);color:#000;font-size:10px;font-weight:700;padding:2px 7px;border-radius:8px;margin-left:6px}
/* Мобильная адаптация */
@media(max-width:768px){
  .sidebar{position:fixed;left:0;top:0;bottom:0;z-index:50;transform:translateX(-100%)}
  .sidebar.open{transform:translateX(0);box-shadow:0 0 40px rgba(0,0,0,.5)}
  .mobile-toggle{display:block}
  .msg .bubble{max-width:88%}
  .modal{padding:26px}
  .suggestion-grid{grid-template-columns:1fr 1fr}
}
.scrollbar::-webkit-scrollbar{width:6px}
.scrollbar::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
</style>
</head>
<body>
<div class="bg"></div>

<div class="app">
  <!-- Сайдбар -->
  <aside class="sidebar" id="sidebar">
    <div class="sidebar-header">
      <div class="logo"><span>🤖</span></div>
      <div class="brand">AWESOME AI</div>
    </div>
    <button class="new-chat" onclick="newChat()">＋ Новый чат</button>
    <div class="chat-list scrollbar" id="chatList"></div>
    <div class="sidebar-footer">
      <div class="user-box">
        <div class="avatar" id="userAvatar">?</div>
        <div class="user-info">
          <div class="user-name" id="userName">Пользователь</div>
          <div class="user-status" id="userStatus">...</div>
        </div>
        <button class="logout-btn" onclick="logout()" title="Выйти">⏻</button>
      </div>
    </div>
  </aside>

  <!-- Основная часть -->
  <div class="main">
    <div class="main-header">
      <button class="mobile-toggle" onclick="toggleSidebar()">☰</button>
      <div class="title" id="currentChatTitle">Новый чат</div>
    </div>
    <div class="messages scrollbar" id="messages">
      <div class="welcome" id="welcome">
        <h1>Чем могу помочь?</h1>
        <p>AWESOME AI — нейросеть на базе GigaChat</p>
        <div class="suggestion-grid">
          <div class="sugg" onclick="sendSuggestion('Объясни как работает квантовый компьютер простыми словами')"><span class="ic">🧠</span>Объясни сложное</div>
          <div class="sugg" onclick="sendSuggestion('Напиши код на Python для сортировки списка')"><span class="ic">💻</span>Напиши код</div>
          <div class="sugg" onclick="sendSuggestion('погода в Москве')"><span class="ic">🌤</span>Погода</div>
          <div class="sugg" onclick="sendSuggestion('нарисуй кота в космосе')"><span class="ic">🎨</span>Нарисуй</div>
          <div class="sugg" onclick="sendSuggestion('курс доллара')"><span class="ic">💵</span>Курс валют</div>
          <div class="sugg" onclick="sendSuggestion('сколько будет 256 * 144 + 18?')"><span class="ic">🧮</span>Математика</div>
        </div>
      </div>
    </div>

    <div class="input-area">
      <div class="input-wrap">
        <textarea id="input" rows="1" placeholder="Спроси что-нибудь..." onkeydown="onKey(event)"></textarea>
        <button class="send-btn" id="sendBtn" onclick="sendMessage()">➤</button>
      </div>
      <div class="toolbar">
        <button class="tool-btn" onclick="draw()">🎨 Сгенерировать</button>
        <button class="tool-btn" onclick="checkStatus()">💎 Premium</button>
        <button class="tool-btn" onclick="clearHistory()">🧹 Очистить</button>
      </div>
    </div>
  </div>
</div>

<!-- Модалка входа -->
<div class="overlay" id="loginOverlay">
  <div class="modal">
    <div class="logo"><span>🤖</span></div>
    <h2>Добро пожаловать!</h2>
    <p>Введи свой Telegram ID, чтобы войти.<br>Premium из бота @awesomeneiro_bot синхронизируется автоматически.</p>
    <input type="text" id="tgId" placeholder="Например: 123456789" inputmode="numeric">
    <input type="text" id="tgName" placeholder="Имя (необязательно)">
    <button class="btn" onclick="login()">Войти</button>
    <div class="hint">Как узнать свой ID: напиши @userinfobot в Telegram</div>
  </div>
</div>

<script>
let currentUserId = null;
let currentChatId = null;
let sending = false;

function toast(text, type='info'){
  const t=document.createElement('div');
  t.className='toast '+type;
  t.textContent=text;
  document.body.appendChild(t);
  setTimeout(()=>t.remove(),3500);
}

function toggleSidebar(){document.getElementById('sidebar').classList.toggle('open')}

async function api(url, method='GET', body=null){
  const opt={method,headers:{'Content-Type':'application/json'}};
  if(body) opt.body=JSON.stringify(body);
  const r=await fetch(url,opt);
  return r.json();
}

async function login(){
  const id=document.getElementById('tgId').value.trim();
  const name=document.getElementById('tgName').value.trim();
  if(!id){toast('Введите Telegram ID','error');return;}
  const res=await api('/api/login','POST',{user_id:id,username:name});
  if(res.ok){
    currentUserId=id;
    document.getElementById('loginOverlay').style.display='none';
    toast('Добро пожаловать! 🎉','success');
    init();
  }else{
    toast(res.error||'Ошибка входа','error');
  }
}

async function logout(){
  await api('/api/logout','POST');
  location.reload();
}

function addMsg(role, text, chatId){
  const box=document.getElementById('messages');
  if(document.getElementById('welcome')) document.getElementById('welcome').style.display='none';
  const m=document.createElement('div');
  m.className='msg '+role;
  m.innerHTML='<div class="avatar">'+(role==='ai'?'🤖':(currentUserId?currentUserId.slice(0,1).toUpperCase():'?'))+'</div><div class="bubble"></div>';
  m.querySelector('.bubble').textContent=text;
  box.appendChild(m);
  box.scrollTop=box.scrollHeight;
  if(chatId) m.dataset.chatId=chatId;
  return m;
}

function addTyping(){
  const box=document.getElementById('messages');
  const m=document.createElement('div');
  m.className='msg ai';
  m.id='typing';
  m.innerHTML='<div class="avatar">🤖</div><div class="bubble"><div class="typing-dots"><span></span><span></span><span></span></div></div>';
  box.appendChild(m);
  box.scrollTop=box.scrollHeight;
}

function removeTyping(){
  const t=document.getElementById('typing');
  if(t) t.remove();
}

async function sendMessage(text){
  if(sending) return;
  const input=document.getElementById('input');
  const msg=(text!==undefined&&text!==null)?text:input.value.trim();
  if(!msg) return;
  input.value='';
  input.style.height='auto';
  addMsg('user',msg,currentChatId);
  setSending(true);
  addTyping();
  try{
    const res=await api('/api/chat','POST',{message:msg,chat_id:currentChatId});
    removeTyping();
    if(res.ok){
      currentChatId=res.chat_id;
      addMsg('ai',res.response,currentChatId);
      loadChats();
    }else{
      addMsg('ai','⚠️ '+res.error);
      if(res.error&&res.error.includes('Лимит')){toast('Лимит! Купи Premium','error');}
    }
  }catch(e){
    removeTyping();
    addMsg('ai','⚠️ Ошибка соединения');
  }
  setSending(false);
  checkStatus();
}

function setSending(v){
  sending=v;
  document.getElementById('sendBtn').disabled=v;
  document.getElementById('input').disabled=v;
}

function onKey(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMessage();}}

function sendSuggestion(text){sendMessage(text);}

async function newChat(){
  const res=await api('/api/chat/new','POST');
  if(res.ok){
    currentChatId=res.chat_id;
    document.getElementById('messages').innerHTML='';
    document.getElementById('welcome').style.display='';
    document.getElementById('currentChatTitle').textContent='Новый чат';
    document.getElementById('sidebar').classList.remove('open');
  }
}

async function loadChats(){
  const res=await api('/api/chats');
  if(!res.ok) return;
  const list=document.getElementById('chatList');
  list.innerHTML='';
  res.chats.forEach(c=>{
    const item=document.createElement('div');
    item.className='chat-item'+(c.id===currentChatId?' active':'');
    item.innerHTML='<span>💬</span><span class="t">'+escapeHtml(c.title||'Новый чат')+'</span><button class="del" onclick="delChat('+c.id+',event)">✕</button>';
    item.onclick=()=>openChat(c);
    list.appendChild(item);
  });
}

function escapeHtml(s){return s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}

function openChat(c){
  currentChatId=c.id;
  const box=document.getElementById('messages');
  box.innerHTML='';
  document.getElementById('currentChatTitle').textContent=c.title||'Чат';
  (c.messages||[]).forEach(m=>addMsg(m.role,m.content,c.id));
  document.getElementById('sidebar').classList.remove('open');
}

async function delChat(id,e){
  e.stopPropagation();
  if(!confirm('Удалить чат?'))return;
  await api('/api/chat/delete','POST',{chat_id:id});
  if(id===currentChatId){currentChatId=null;boxReset();}
  loadChats();
}

function boxReset(){
  document.getElementById('messages').innerHTML='';
  document.getElementById('welcome').style.display='';
  document.getElementById('currentChatTitle').textContent='Новый чат';
}

async function clearHistory(){
  document.getElementById('messages').innerHTML='';
  document.getElementById('welcome').style.display='';
  toast('История очищена','success');
}

async function checkStatus(){
  const res=await api('/api/status');
  if(!res.ok){toast('Авторизуйтесь','error');return;}
  const st=document.getElementById('userStatus');
  if(res.premium){
    st.innerHTML='💎 Premium'+(res.premium_expires?' · до '+res.premium_expires:'');
    toast('💎 Premium активен! Лимит безлимитный','success');
  }else{
    st.innerHTML='🔓 Осталось '+(res.free_limit-res.messages_today)+' из '+res.free_limit;
    toast('🔓 Бесплатный лимит: осталось '+(res.free_limit-res.messages_today)+' из '+res.free_limit);
  }
}

async function draw(){
  const input=document.getElementById('input');
  const prompt=prompt2('🎨 Опиши что нарисовать:', input.value||'');
  if(!prompt) return;
  addMsg('user','🎨 '+prompt);
  setSending(true);addTyping();
  const res=await api('/api/draw','POST',{prompt});
  removeTyping();
  if(res.ok&&res.image){
    const box=document.getElementById('messages');
    const m=document.createElement('div');m.className='msg ai';
    m.innerHTML='<div class="avatar">🤖</div><div class="bubble"><img src="data:image/png;base64,'+res.image+'" style="max-width:100%;border-radius:12px"></div>';
    box.appendChild(m);box.scrollTop=box.scrollHeight;
  }else{
    addMsg('ai','⚠️ '+(res.error||'Не удалось сгенерировать'));
  }
  setSending(false);checkStatus();
}

function prompt2(title,val){const v=prompt(title,val||'');return v===null?'':v.trim();}

async function init(){
  const me=await api('/api/me');
  if(me.user_id){
    currentUserId=me.user_id;
    document.getElementById('loginOverlay').style.display='none';
    document.getElementById('userAvatar').textContent=String(currentUserId).slice(0,1).toUpperCase();
    document.getElementById('userName').textContent=me.username||'Пользователь';
    document.getElementById('userStatus').textContent='Загрузка...';
    await loadChats();
    await checkStatus();
  }
}

document.addEventListener('DOMContentLoaded',init);
</script>
</body>
</html>
"""

# ============================================================
# ЗАПУСК
# ============================================================
if __name__ == '__main__':
    print("=" * 60)
    print("🧠 AWESOME AI WEB — СУПЕР-БЫСТРЫЙ!")
    print("=" * 60)
    print("✅ Supabase подключен (синхронизация с @awesomeneiro_bot)")
    print("✅ GigaChat — главная нейросеть")
    print("✅ YandexGPT — сверка информации")
    print("=" * 60)
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
