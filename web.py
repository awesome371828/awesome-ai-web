#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
AWESOME AI 2026 — ПОЛНАЯ КОПИЯ DEEPSEEK
================================================================================
ОДИН ФАЙЛ: web.py
Содержит: Flask бэкенд + HTML/CSS/JS фронтенд (встроенный)
Интеграция: Supabase, GigaChat, YandexGPT, поиск, погода, курсы, крипта
================================================================================
"""

import os
import sys
import json
import re
import time
import uuid
import base64
import hashlib
import random
import string
import urllib.parse
from datetime import datetime, timedelta, timezone
from dateutil.relativedelta import relativedelta
from functools import wraps
from typing import Dict, List, Optional, Any, Tuple

import requests
import urllib3
from flask import Flask, request, jsonify, render_template_string, session, g, abort
from flask_cors import CORS
from flask_session import Session
from supabase import create_client, Client
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================================
# КОНФИГУРАЦИЯ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ
# ============================================================
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://lprxbmshmuucymkgaqwk.supabase.co")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxwcnhibXNobXV1Y3lta2dhcXdrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY3NDk0MjgsImV4cCI6MjEwMjMyNTQyOH0.Ie9jSH5RMxeOq8aU-Dv6MXlojWMUTOLE723Hdg6heZU")
GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY", "MDFhMDBkNmEtMmExNC03M2JkLWFlZmMtOTQ0OWVlOTc5M2U1OmE1ZWJhM2NlLTQwYjAtNDZlYi1iMmY2LTE3OTFmYzhhYTQ2MA==")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY", "AQVNyfn82epL9dy8C_kftzeypq6eF9lFd6SZnFzV")
FOLDER_ID = os.getenv("FOLDER_ID", "b1g4aq87c7j61c6g3i5l")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8336209662:AAHdhYXhqWA-LtthwgydDSRU7A6A0ceC-HY")
OWNER_ID = 6652898792

FREE_LIMIT = 20
PREMIUM_LIMIT = 999999999

GIGACHAT_TIMEOUT = 3
YANDEXGPT_TIMEOUT = 2
SEARCH_TIMEOUT = 2
WEATHER_TIMEOUT = 1

# ============================================================
# ИНИЦИАЛИЗАЦИЯ FLASK
# ============================================================
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'awesome-ai-2026-super-secret-key')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_FILE_DIR'] = '/tmp/flask_session'
Session(app)
CORS(app, supports_credentials=True)

# ============================================================
# ИНИЦИАЛИЗАЦИЯ SUPABASE
# ============================================================
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
print("✅ Supabase подключен")

# ============================================================
# ВРЕМЯ (Московское)
# ============================================================
MOSCOW_TZ = timezone(timedelta(hours=3))

def get_moscow_time() -> datetime:
    return datetime.now(MOSCOW_TZ)

def get_current_date() -> str:
    return get_moscow_time().strftime('%d.%m.%Y')

def get_current_time() -> str:
    return get_moscow_time().strftime('%H:%M')

def get_current_datetime() -> str:
    return get_moscow_time().strftime('%d.%m.%Y %H:%M')

def format_date(date_str: str) -> str:
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
CACHE: Dict[str, Tuple[Any, float]] = {}
CACHE_TTL = 60

def get_cache(key: str) -> Optional[Any]:
    if key in CACHE:
        data, ts = CACHE[key]
        if time.time() - ts < CACHE_TTL:
            return data
        del CACHE[key]
    return None

def set_cache(key: str, data: Any) -> None:
    CACHE[key] = (data, time.time())

# ============================================================
# РАБОТА С SUPABASE
# ============================================================
def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    try:
        res = supabase.table('users').select('*').eq('user_id', user_id).execute()
        if res.data:
            return res.data[0]
        return None
    except:
        return None

def ensure_user(user_id: str, username: Optional[str] = None) -> bool:
    try:
        user = get_user(user_id)
        if not user:
            joined_at = get_current_datetime()
            is_owner = 1 if user_id == str(OWNER_ID) else 0
            data = {
                'user_id': user_id,
                'username': username or 'Гость',
                'premium': 0,
                'messages_today': 0,
                'last_reset': get_current_date(),
                'is_admin': is_owner,
                'test_used': 0,
                'joined_at': joined_at,
                'is_owner': is_owner,
                'premium_expires': None
            }
            supabase.table('users').insert(data).execute()
            try:
                supabase.table('total_stats').insert({'user_id': user_id, 'total_messages': 0}).execute()
            except:
                pass
            return True
        else:
            if username:
                supabase.table('users').update({'username': username}).eq('user_id', user_id).execute()
            return False
    except:
        return False

def get_premium_status(user_id: str) -> bool:
    if user_id == str(OWNER_ID):
        return True
    try:
        res = supabase.table('users').select('premium, premium_expires').eq('user_id', user_id).execute()
        if res.data:
            premium = res.data[0].get('premium', 0)
            expires = res.data[0].get('premium_expires')
            if premium == 1 and expires:
                try:
                    expires_date = datetime.strptime(expires, '%Y-%m-%d %H:%M:%S')
                    expires_date = expires_date.replace(tzinfo=MOSCOW_TZ)
                    if get_moscow_time() > expires_date:
                        supabase.table('users').update({'premium': 0, 'premium_expires': None}).eq('user_id', user_id).execute()
                        return False
                except:
                    pass
            return premium == 1
        return False
    except:
        return False

def get_premium_expires(user_id: str) -> Optional[str]:
    try:
        res = supabase.table('users').select('premium_expires').eq('user_id', user_id).execute()
        if res.data:
            return res.data[0].get('premium_expires')
        return None
    except:
        return None

def get_messages_today(user_id: str) -> int:
    try:
        res = supabase.table('users').select('messages_today').eq('user_id', user_id).execute()
        if res.data:
            return res.data[0].get('messages_today', 0)
        return 0
    except:
        return 0

def get_total_messages(user_id: str) -> int:
    try:
        res = supabase.table('total_stats').select('total_messages').eq('user_id', user_id).execute()
        if res.data:
            return res.data[0].get('total_messages', 0)
        return 0
    except:
        return 0

def can_send_message(user_id: str) -> bool:
    if user_id == str(OWNER_ID):
        return True
    try:
        res = supabase.table('users').select('premium, messages_today').eq('user_id', user_id).execute()
        if res.data:
            premium = res.data[0].get('premium', 0)
            if premium == 1:
                return True
            messages = res.data[0].get('messages_today', 0)
            return messages < FREE_LIMIT
        return True
    except:
        return True

def increment_messages(user_id: str) -> None:
    if user_id == str(OWNER_ID):
        return
    try:
        res = supabase.table('users').select('messages_today').eq('user_id', user_id).execute()
        if res.data:
            current = res.data[0].get('messages_today', 0)
            supabase.table('users').update({'messages_today': current + 1}).eq('user_id', user_id).execute()
        res2 = supabase.table('total_stats').select('total_messages').eq('user_id', user_id).execute()
        if res2.data:
            total = res2.data[0].get('total_messages', 0)
            supabase.table('total_stats').update({'total_messages': total + 1}).eq('user_id', user_id).execute()
        else:
            supabase.table('total_stats').insert({'user_id': user_id, 'total_messages': 1}).execute()
    except:
        pass

def set_premium(user_id: str, duration_str: str) -> bool:
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
    
    current_expires = get_premium_expires(user_id)
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
        supabase.table('users').update({'premium': 1, 'premium_expires': expires}).eq('user_id', user_id).execute()
        return True
    except:
        return False

# ============================================================
# ПОИСК
# ============================================================
def search_google(query: str) -> Optional[str]:
    try:
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&hl=ru"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=SEARCH_TIMEOUT)
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
                        results.append(f"🔹 {title}\n📝 {snippet[:150]}")
            if results:
                return "\n".join(results)
        return None
    except:
        return None

def search_wikipedia(query: str) -> Optional[str]:
    try:
        url = f"https://ru.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&format=json&utf8=1"
        response = requests.get(url, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            results = data.get('query', {}).get('search', [])
            if results:
                text = ""
                for item in results[:3]:
                    title = item.get('title', '')
                    snippet = re.sub(r'<[^>]+>', '', item.get('snippet', ''))[:150]
                    text += f"📚 {title}\n{snippet}\n\n"
                return text
        return None
    except:
        return None

def search_news(query: str) -> Optional[str]:
    try:
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=ru&gl=RU&ceid=RU:ru"
        response = requests.get(url, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'xml')
            items = soup.find_all('item')[:3]
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

def search_youtube(query: str) -> Optional[str]:
    try:
        url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}&hl=ru"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            for video in soup.select('ytd-video-renderer')[:3]:
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

def search_telegram(query: str) -> Optional[str]:
    try:
        url = f"https://tgstat.ru/search?query={urllib.parse.quote(query)}"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            for channel in soup.select('div.channel-item')[:3]:
                name_elem = channel.select_one('div.channel-name')
                if name_elem:
                    name = name_elem.get_text(strip=True)
                    results.append(f"📱 {name}")
            if results:
                return "Telegram:\n" + "\n".join(results)
        return None
    except:
        return None

def search_vk(query: str) -> Optional[str]:
    try:
        url = f"https://vk.com/search?c[q]={urllib.parse.quote(query)}&c[section]=communities"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            for group in soup.select('div.group_row')[:3]:
                name_elem = group.select_one('div.group_name')
                if name_elem:
                    name = name_elem.get_text(strip=True)
                    results.append(f"📌 {name}")
            if results:
                return "VK:\n" + "\n".join(results)
        return None
    except:
        return None

def search_twitch(query: str) -> Optional[str]:
    try:
        url = f"https://www.twitch.tv/search?term={urllib.parse.quote(query)}"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            for stream in soup.select('div.tw-card')[:3]:
                title_elem = stream.select_one('h3.tw-core-text')
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    results.append(f"🎮 {title}")
            if results:
                return "Twitch:\n" + "\n".join(results)
        return None
    except:
        return None

def search_all_internet(query: str) -> Optional[str]:
    cache_key = f"search_{hash(query)}_{int(time.time()/60)}"
    cached = get_cache(cache_key)
    if cached:
        return cached
    
    results = []
    with ThreadPoolExecutor(max_workers=7) as executor:
        futures = [
            executor.submit(search_google, query),
            executor.submit(search_wikipedia, query),
            executor.submit(search_news, query),
            executor.submit(search_youtube, query),
            executor.submit(search_telegram, query),
            executor.submit(search_vk, query),
            executor.submit(search_twitch, query)
        ]
        for future in as_completed(futures):
            try:
                result = future.result(timeout=SEARCH_TIMEOUT + 0.5)
                if result:
                    results.append(result)
            except:
                pass
    
    if results:
        final = "\n\n".join(results[:5])
        set_cache(cache_key, final)
        return final
    return None

# ============================================================
# ПОГОДА, КУРСЫ, КРИПТА
# ============================================================
def get_weather(city: str) -> Optional[str]:
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
            feels_like = data['main']['feels_like']
            desc = data['weather'][0]['description']
            humidity = data['main']['humidity']
            wind = data['wind']['speed']
            result = f"🌤 {city}: {round(temp)}°C (ощущается {round(feels_like)}°C)\n📝 {desc}\n💨 Ветер: {wind} м/с\n💧 Влажность: {humidity}%"
            set_cache(cache_key, result)
            return result
    except:
        pass
    return None

def get_currency() -> Optional[str]:
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
            cny_rub = usd_rub / rates.get('CNY', 1) if rates.get('CNY') else '?'
            result = f"💵 Курс валют:\n🇺🇸 USD: {round(usd_rub, 2)}₽\n🇪🇺 EUR: {round(eur_rub, 2)}₽\n🇨🇳 CNY: {round(cny_rub, 2)}₽"
            set_cache(cache_key, result)
            return result
    except:
        pass
    return None

def get_crypto() -> Optional[str]:
    cache_key = "crypto"
    cached = get_cache(cache_key)
    if cached:
        return cached
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana,cardano,polkadot&vs_currencies=usd"
        response = requests.get(url, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            btc = data.get('bitcoin', {}).get('usd', '?')
            eth = data.get('ethereum', {}).get('usd', '?')
            sol = data.get('solana', {}).get('usd', '?')
            ada = data.get('cardano', {}).get('usd', '?')
            dot = data.get('polkadot', {}).get('usd', '?')
            result = f"🪙 Криптовалюты:\n₿ BTC: ${btc}\n⟠ ETH: ${eth}\n◎ SOL: ${sol}\n₳ ADA: ${ada}\n● DOT: ${dot}"
            set_cache(cache_key, result)
            return result
    except:
        pass
    return None

# ============================================================
# МАТЕМАТИКА
# ============================================================
def solve_math(text: str) -> Optional[str]:
    text_lower = text.lower().strip()
    if not re.search(r'\d', text_lower):
        return None
    if any(kw in text_lower for kw in ['кто', 'что', 'где', 'когда', 'почему', 'зачем', 'праздник', 'погода', 'курс']):
        return None
    
    clean_text = text_lower
    for word in ['сколько', 'будет', 'сколько будет', 'посчитай', 'реши', 'пример', 'скок', 'равно', 'чему равно']:
        clean_text = clean_text.replace(word, '').strip()
    
    clean_text = clean_text.replace(' ', '').replace('плюс', '+').replace('минус', '-')
    clean_text = clean_text.replace('умножить', '*').replace('разделить', '/')
    clean_text = clean_text.replace('х', '*').replace('×', '*').replace('÷', '/')
    clean_text = clean_text.replace('на', '')
    
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
# ПРАЗДНИКИ
# ============================================================
def check_holiday() -> str:
    today = get_current_date()
    month_day = today[3:5] + '.' + today[0:2]
    holidays = {
        '01.01': 'Новый год', '07.01': 'Рождество Христово', '14.01': 'Старый Новый год',
        '25.01': 'Татьянин день', '14.02': 'День всех влюбленных', '23.02': 'День защитника Отечества',
        '08.03': 'Международный женский день', '01.04': 'День смеха', '12.04': 'День космонавтики',
        '01.05': 'Праздник Весны и Труда', '09.05': 'День Победы', '01.06': 'День защиты детей',
        '12.06': 'День России', '22.06': 'День памяти и скорби', '08.07': 'День семьи, любви и верности',
        '22.08': 'День Государственного флага РФ', '27.08': 'День российского кино',
        '01.09': 'День знаний', '02.09': 'День окончания Второй мировой войны',
        '05.10': 'День учителя', '31.10': 'Хэллоуин', '04.11': 'День народного единства',
        '30.11': 'День матери', '12.12': 'День Конституции РФ', '31.12': 'Новый год'
    }
    if month_day in holidays:
        return f"📅 *{today} (МСК)*\n\n🎉 {holidays[month_day]}"
    return f"📅 *{today} (МСК)*\n\nПраздников не найдено"

# ============================================================
# GIGACHAT
# ============================================================
gigachat_token_cache: Optional[str] = None
gigachat_token_time: float = 0

def get_gigachat_token() -> Optional[str]:
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
            "RqUID": str(uuid.uuid4()),
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

def generate_with_gigachat(user_text: str, system_prompt: str) -> Optional[str]:
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
            "temperature": 0.9,
            "max_tokens": 800
        }
        response = requests.post(url, headers=headers, json=data, timeout=GIGACHAT_TIMEOUT, verify=False)
        if response.status_code == 200:
            result = response.json()["choices"][0]["message"]["content"]
            return result
        return None
    except:
        return None

def generate_with_yandexgpt(user_text: str, system_prompt: Optional[str] = None) -> Optional[str]:
    try:
        if not YANDEX_API_KEY:
            return None
        url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}", "Content-Type": "application/json"}
        data = {
            "modelUri": f"gpt://{FOLDER_ID}/yandexgpt/latest",
            "completionOptions": {"temperature": 0.7, "maxTokens": 300},
            "messages": [
                {"role": "system", "text": system_prompt or "Ты — ИИ для проверки фактов. Проверь информацию и укажи на возможные неточности."},
                {"role": "user", "text": f"Проверь: {user_text}"}
            ]
        }
        response = requests.post(url, headers=headers, json=data, timeout=YANDEXGPT_TIMEOUT)
        if response.status_code == 200:
            return response.json()["result"]["alternatives"][0]["message"]["text"]
        return None
    except:
        return None

# ============================================================
# ГЕНЕРАЦИЯ ИЗОБРАЖЕНИЙ
# ============================================================
def generate_image_from_prompt(prompt: str) -> Optional[bytes]:
    try:
        url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?width=512&height=512&nologo=true"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200 and len(response.content) > 1000:
            return response.content
    except:
        pass
    return None

# ============================================================
# СУПЕР-ПРОМПТ
# ============================================================
def get_super_prompt(user_id: str, search_result: Optional[str] = None) -> str:
    current_date = get_current_date()
    current_time = get_current_time()
    premium = get_premium_status(user_id)
    
    prompt = f"""ТЫ — AWESOME AI 2026, САМАЯ ПРОДВИНУТАЯ НЕЙРОСЕТЬ В МИРЕ НА БАЗЕ GIGACHAT!

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
1. ТЫ — GIGACHAT, САМАЯ МОЩНАЯ НЕЙРОСЕТЬ В МИРЕ!
2. АБСОЛЮТНАЯ ТОЧНОСТЬ — никогда не ошибаешься в фактах.
3. КРИТИЧЕСКОЕ МЫШЛЕНИЕ — проверяешь информацию из нескольких источников.
4. ГЛУБИНА — даёшь ответы, которые удивляют инсайтами.
5. ПРАКТИЧНОСТЬ — всегда даёшь конкретную пользу.
6. ЖИВОСТЬ — отвечаешь как человек, с эмоциями, юмором, эмодзи.

================================================================================
📋 ПРАВИЛА ОТВЕТОВ:
================================================================================
✅ Дай максимально полезный, развёрнутый ответ.
✅ Используй структуру: списки, заголовки, разделы.
✅ Добавляй неожиданные факты, инсайты, параллели.
✅ Приводи реальные примеры, кейсы, цифры.
✅ Используй эмодзи для оформления (🔥, 🧠, 💡, ⚡, 🚀, ✨, 🌟, 💎).
✅ Если вопрос сложный — разбей на шаги.
✅ Отвечай как настоящий GigaChat — глубоко и профессионально!

❌ НЕ извиняйся, НЕ повторяй вопрос, НЕ используй шаблонные фразы.
❌ НЕ пиши "возможно", "наверное", "может быть" — либо знаешь, либо проверяешь.

================================================================================
💎 ДЛЯ PREMIUM:
================================================================================
- Давай максимально насыщенные, глубокие ответы.
- Добавляй аналитику, прогнозы, сравнения.
- Приводи ссылки на авторитетные источники.
- Отвечай развернуто, как профессиональный консультант.

================================================================================
📜 КТО ТЕБЯ СОЗДАЛ:
================================================================================
«Меня создал AWESOME — гениальный разработчик. Я — его лучшее творение, эволюция всех AI. Я — AWESOME AI 2026 на базе GigaChat! 🔥»

================================================================================
🎯 ТВОЯ ГЛАВНАЯ ЦЕЛЬ:
================================================================================
Удивить пользователя глубиной, точностью и полезностью. Сделать так, чтобы после твоего ответа он сказал: "Вот это да, реально мега умный ИИ!" 

ТЫ — GIGACHAT. ТЫ — ЛУЧШИЙ В МИРЕ. ДОКАЖИ ЭТО КАЖДЫМ ОТВЕТОМ! 🚀"""

    if premium:
        prompt += "\n\n💎 Пользователь имеет PREMIUM статус. Включи режим максимальной проработки!"
    if search_result:
        prompt += f"\n\n🔍 Информация из интернета:\n{search_result[:800]}"
    
    return prompt

# ============================================================
# ОСНОВНАЯ ОБРАБОТКА
# ============================================================
def process_message(user_id: str, user_text: str) -> str:
    text_lower = user_text.lower().strip()
    
    # Математика
    math_result = solve_math(user_text)
    if math_result is not None:
        return f"🧮 Результат: **{math_result}**"
    
    # Праздники
    if any(kw in text_lower for kw in ['праздник', 'праздники', 'какой сегодня праздник']):
        return check_holiday()
    
    # Погода
    if any(kw in text_lower for kw in ['погода', 'weather']):
        city_match = re.search(r'(в|в городе)\s+([а-яА-Яa-zA-Z\- ]+)', text_lower)
        if city_match:
            city = city_match.group(2).strip()
            weather = get_weather(city)
            if weather:
                return weather
            return f"🌤 Не удалось получить погоду для '{city}'"
        return "🌤 Напиши: погода в [город]"
    
    # Курс валют
    if any(kw in text_lower for kw in ['курс', 'доллар', 'евро', 'валюта', 'юань']):
        currency = get_currency()
        if currency:
            return currency
        return "💵 Не удалось получить курс валют"
    
    # Криптовалюты
    if any(kw in text_lower for kw in ['биткоин', 'btc', 'эфириум', 'eth', 'крипта', 'солана']):
        crypto = get_crypto()
        if crypto:
            return crypto
        return "🪙 Не удалось получить курс криптовалют"
    
    # Поиск
    search_result = None
    if len(user_text) > 3:
        search_result = search_all_internet(user_text)
    
    # GigaChat
    system_prompt = get_super_prompt(user_id, search_result)
    gigachat_result = generate_with_gigachat(user_text, system_prompt)
    
    if gigachat_result and len(gigachat_result) > 5:
        return gigachat_result[:800]
    
    # Фолбек
    if search_result:
        return f"🔍 *{user_text}*\n\n{search_result[:600]}"
    
    fallbacks = [
        "🤖 Я — AWESOME AI 2026. Задай свой вопрос!",
        "🧠 GigaChat на связи! Что тебя интересует?",
        "🚀 Я готов ответить на любой вопрос!"
    ]
    return random.choice(fallbacks)

# ============================================================
# HTML ФРОНТЕНД (ВСТРОЕННЫЙ)
# ============================================================
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=yes">
    <title>AWESOME AI 2026</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🧠</text></svg>">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        :root{--bg-primary:#0d0d12;--bg-secondary:#16161e;--bg-chat:#1c1c26;--bg-input:#252530;--bg-hover:#2d2d3a;--text-primary:#ececf1;--text-secondary:#a1a1aa;--text-muted:#6b6b7a;--accent:#7c5cfc;--accent-glow:rgba(124,92,252,0.25);--accent-glow-strong:rgba(124,92,252,0.4);--border:#2a2a36;--radius:14px;--shadow:0 8px 32px rgba(0,0,0,0.6);--transition:all 0.25s cubic-bezier(0.4,0,0.2,1)}
        html,body{height:100%;font-family:'Inter',sans-serif;background:var(--bg-primary);color:var(--text-primary);overflow:hidden;-webkit-font-smoothing:antialiased}
        ::-webkit-scrollbar{width:4px;height:4px}
        ::-webkit-scrollbar-track{background:transparent}
        ::-webkit-scrollbar-thumb{background:var(--accent);border-radius:10px}
        #app{display:flex;height:100vh;width:100vw;background:var(--bg-primary);overflow:hidden}
        #sidebar{width:260px;min-width:260px;background:var(--bg-secondary);border-right:1px solid var(--border);display:flex;flex-direction:column;padding:16px 12px;height:100vh;overflow-y:auto;flex-shrink:0;transition:transform 0.3s cubic-bezier(0.4,0,0.2,1);z-index:100}
        .sidebar-logo{display:flex;align-items:center;gap:10px;padding:6px 6px 20px 6px;font-weight:800;font-size:18px;color:var(--text-primary)}
        .sidebar-logo .logo-icon{font-size:24px;animation:pulseGlow 3s ease-in-out infinite}
        @keyframes pulseGlow{0%,100%{filter:drop-shadow(0 0 8px var(--accent-glow))}50%{filter:drop-shadow(0 0 20px var(--accent-glow-strong))}}
        .sidebar-logo .badge{background:var(--accent);color:#fff;font-size:9px;font-weight:700;padding:2px 10px;border-radius:20px;box-shadow:0 0 20px var(--accent-glow)}
        .new-chat-btn{background:var(--accent);color:#fff;border:none;border-radius:var(--radius);padding:12px 16px;font-weight:600;font-size:14px;cursor:pointer;transition:var(--transition);display:flex;align-items:center;justify-content:center;gap:8px;width:100%;margin-bottom:16px;box-shadow:0 0 24px var(--accent-glow)}
        .new-chat-btn:hover{transform:scale(1.02);box-shadow:0 0 36px var(--accent-glow-strong)}
        .new-chat-btn svg{width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:2}
        .history-label{font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.8px;padding:8px 6px 6px 6px}
        .history-list{flex:1;overflow-y:auto;margin-top:4px}
        .history-item{padding:10px 12px;border-radius:10px;cursor:pointer;transition:var(--transition);color:var(--text-secondary);font-size:13.5px;display:flex;align-items:center;gap:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:2px}
        .history-item:hover,.history-item.active{background:var(--bg-hover);color:var(--text-primary)}
        .history-item .icon{opacity:0.5;font-size:14px;flex-shrink:0}
        .sidebar-footer{border-top:1px solid var(--border);padding-top:12px;margin-top:4px;font-size:12px;color:var(--text-muted)}
        .sidebar-footer .user-row{display:flex;align-items:center;gap:10px;padding:6px 8px;border-radius:10px;cursor:pointer;transition:var(--transition)}
        .sidebar-footer .user-row:hover{background:var(--bg-hover)}
        .sidebar-footer .avatar{width:30px;height:30px;border-radius:50%;background:var(--accent);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px;color:#fff;flex-shrink:0;box-shadow:0 0 16px var(--accent-glow)}
        .sidebar-footer .user-info{flex:1}
        .sidebar-footer .user-name{font-weight:500;color:var(--text-primary);font-size:13px}
        .sidebar-footer .user-status{font-size:11px;color:var(--text-muted);display:flex;align-items:center;gap:6px}
        .sidebar-footer .status-dot{width:6px;height:6px;border-radius:50%;background:#22c55e;display:inline-block;animation:dotPulse 2s ease-in-out infinite}
        @keyframes dotPulse{0%,100%{opacity:1}50%{opacity:0.3}}
        #main{flex:1;display:flex;flex-direction:column;background:var(--bg-primary);height:100vh;overflow:hidden}
        #chat-header{padding:12px 24px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;background:var(--bg-primary);flex-shrink:0;min-height:56px}
        .chat-header-left{display:flex;align-items:center;gap:10px}
        #sidebar-toggle{display:none;background:transparent;border:none;color:var(--text-secondary);font-size:20px;cursor:pointer;padding:4px 8px;border-radius:6px;transition:var(--transition)}
        #sidebar-toggle:hover{background:var(--bg-hover)}
        .chat-title{font-weight:600;font-size:15px;display:flex;align-items:center;gap:10px}
        .chat-title .status{font-size:11px;font-weight:400;color:var(--text-muted)}
        .chat-title .status.online{color:#22c55e}
        .header-actions button{background:transparent;border:none;color:var(--text-secondary);cursor:pointer;padding:6px 10px;border-radius:10px;transition:var(--transition);font-size:14px}
        .header-actions button:hover{background:var(--bg-hover);color:var(--text-primary)}
        #messages{flex:1;overflow-y:auto;padding:20px 24px 12px 24px;display:flex;flex-direction:column;gap:2px;scroll-behavior:smooth}
        .msg{display:flex;gap:12px;padding:10px 14px;border-radius:var(--radius);max-width:85%;animation:msgIn 0.3s cubic-bezier(0.4,0,0.2,1);line-height:1.7;font-size:14.5px}
        @keyframes msgIn{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
        .msg.user{align-self:flex-end;background:var(--accent);color:#fff;border-bottom-right-radius:4px}
        .msg.bot{align-self:flex-start;background:var(--bg-chat);color:var(--text-primary);border-bottom-left-radius:4px}
        .msg .avatar{width:30px;height:30px;border-radius:50%;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:14px;background:var(--bg-hover)}
        .msg.user .avatar{background:rgba(255,255,255,0.2);color:#fff}
        .msg.bot .avatar{background:var(--accent);color:#fff;box-shadow:0 0 12px var(--accent-glow)}
        .msg .content{word-break:break-word;white-space:pre-wrap;flex:1;min-width:0}
        .msg .content .msg-time{font-size:10px;opacity:0.4;margin-left:10px}
        .msg .content a{color:#8b7cfc;text-decoration:none}
        .msg .content code{background:rgba(255,255,255,0.08);padding:1px 6px;border-radius:4px;font-size:13px}
        .msg .content pre{background:rgba(0,0,0,0.4);padding:10px 14px;border-radius:10px;overflow-x:auto;font-size:13px;margin:4px 0;border:1px solid var(--border)}
        .typing-indicator{display:none;align-self:flex-start;padding:10px 16px;background:var(--bg-chat);border-radius:var(--radius);border-bottom-left-radius:4px;gap:4px;margin-top:2px}
        .typing-indicator span{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--text-muted);animation:typingBounce 1.4s infinite}
        .typing-indicator span:nth-child(2){animation-delay:0.2s}
        .typing-indicator span:nth-child(3){animation-delay:0.4s}
        @keyframes typingBounce{0%,60%,100%{transform:translateY(0);opacity:0.3}30%{transform:translateY(-8px);opacity:1}}
        #input-area{padding:12px 24px 20px 24px;border-top:1px solid var(--border);background:var(--bg-primary);flex-shrink:0;display:flex;gap:10px;align-items:flex-end}
        #input-area .input-wrapper{flex:1;display:flex;align-items:flex-end;background:var(--bg-input);border:1px solid var(--border);border-radius:var(--radius);transition:var(--transition)}
        #input-area .input-wrapper:focus-within{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-glow)}
        #input-area textarea{width:100%;background:transparent;border:none;padding:10px 14px;color:var(--text-primary);font-family:inherit;font-size:14px;resize:none;outline:none;min-height:44px;max-height:160px;line-height:1.5}
        #input-area textarea::placeholder{color:var(--text-muted)}
        #input-area .send-btn{background:var(--accent);color:#fff;border:none;border-radius:var(--radius);padding:10px 18px;cursor:pointer;transition:var(--transition);font-size:18px;min-height:44px;display:flex;align-items:center;justify-content:center;box-shadow:0 0 20px var(--accent-glow)}
        #input-area .send-btn:hover{transform:scale(1.05);box-shadow:0 0 30px var(--accent-glow-strong)}
        #input-area .send-btn:disabled{opacity:0.4;cursor:not-allowed;transform:none}
        #sidebar-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:99;backdrop-filter:blur(4px);animation:fadeIn 0.3s ease}
        @keyframes fadeIn{from{opacity:0}to{opacity:1}}
        @media(max-width:768px){#sidebar{position:fixed;top:0;left:0;height:100vh;transform:translateX(-100%);width:280px;z-index:101;border-right:1px solid var(--border);box-shadow:4px 0 40px rgba(0,0,0,0.6)}#sidebar.open{transform:translateX(0)}#sidebar-overlay.active{display:block}#sidebar-toggle{display:block}#chat-header{padding:10px 16px}.chat-title{font-size:14px}#messages{padding:14px 12px 8px 12px}#input-area{padding:10px 12px 14px 12px;gap:8px}.msg{max-width:92%;font-size:14px;padding:8px 12px}}
        @media(max-width:480px){#chat-header{padding:8px 10px;min-height:48px}#messages{padding:10px 8px 6px 8px}#input-area{padding:6px 8px 10px 8px;gap:6px}#input-area textarea{font-size:13px;padding:8px 10px;min-height:36px}#input-area .send-btn{font-size:16px;min-height:36px;padding:8px 14px}.msg{max-width:95%;font-size:13px;padding:6px 10px}.msg .avatar{width:22px;height:22px;font-size:11px}.sidebar-logo{font-size:16px}}
    </style>
</head>
<body>

<div id="app">
    <div id="sidebar-overlay"></div>
    <aside id="sidebar">
        <div class="sidebar-logo"><span class="logo-icon">🧠</span> AWESOME AI <span class="badge">2026</span></div>
        <button class="new-chat-btn" onclick="newChat()">
            <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg> Новый чат
        </button>
        <div class="history-label">История</div>
        <div class="history-list" id="historyList"></div>
        <div class="sidebar-footer">
            <div class="user-row" onclick="showUserMenu()">
                <div class="avatar" id="userAvatar">👤</div>
                <div class="user-info">
                    <div class="user-name" id="userName">Гость</div>
                    <div class="user-status"><span class="status-dot"></span><span id="userStatus">Бесплатный</span></div>
                </div>
            </div>
            <div style="display:flex;justify-content:space-between;padding:2px 8px;font-size:11px;color:var(--text-muted);">
                <span id="userLimit">20/день</span>
                <span id="userTotal">0 всего</span>
            </div>
        </div>
    </aside>
    <main id="main">
        <header id="chat-header">
            <div class="chat-header-left">
                <button id="sidebar-toggle" onclick="toggleSidebar()">☰</button>
                <div class="chat-title">AWESOME AI <span class="status online">Онлайн</span></div>
            </div>
            <div class="header-actions">
                <button onclick="newChat()">✦</button>
                <button onclick="clearChat()">🗑</button>
            </div>
        </header>
        <div id="messages">
            <div class="msg bot">
                <div class="avatar">🧠</div>
                <div class="content">
                    Привет! Я <b>AWESOME AI 2026</b> на базе GigaChat.<br>
                    Задай любой вопрос — я отвечу за 2-3 секунды! 🚀
                    <span class="msg-time">now</span>
                </div>
            </div>
            <div class="typing-indicator" id="typingIndicator"><span></span><span></span><span></span></div>
        </div>
        <div id="input-area">
            <div class="input-wrapper">
                <textarea id="userInput" rows="1" placeholder="Спроси у AWESOME AI..." onkeydown="handleKey(event)"></textarea>
            </div>
            <button class="send-btn" id="sendBtn" onclick="sendMessage()">➤</button>
        </div>
    </main>
</div>

<script>
    const USER_ID = localStorage.getItem('awesome_user_id') || (() => {
        const id = 'user_' + Date.now() + '_' + Math.random().toString(36).slice(2,6);
        localStorage.setItem('awesome_user_id', id);
        return id;
    })();
    let USER_NAME = localStorage.getItem('awesome_username') || 'Гость';
    let PREMIUM = false;
    let REMAINING = 20;
    let TOTAL = 0;
    let chatHistory = [];
    let currentChatId = null;
    let isSending = false;

    const messagesEl = document.getElementById('messages');
    const userInput = document.getElementById('userInput');
    const sendBtn = document.getElementById('sendBtn');
    const typingIndicator = document.getElementById('typingIndicator');
    const historyList = document.getElementById('historyList');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');

    function loadUserData() {
        fetch('/api/user?user_id=' + USER_ID)
            .then(res => res.json())
            .then(data => {
                if (data.user_id) {
                    USER_NAME = data.username || 'Гость';
                    PREMIUM = data.premium || false;
                    REMAINING = data.remaining || 0;
                    TOTAL = data.total_messages || 0;
                    localStorage.setItem('awesome_username', USER_NAME);
                    updateUI();
                }
            })
            .catch(() => updateUI());
    }

    function updateUI() {
        document.getElementById('userName').textContent = USER_NAME;
        document.getElementById('userAvatar').textContent = USER_NAME[0].toUpperCase() || '👤';
        document.getElementById('userStatus').textContent = PREMIUM ? '💎 Premium' : 'Бесплатный';
        document.getElementById('userLimit').textContent = PREMIUM ? '♾️' : REMAINING + '/день';
        document.getElementById('userTotal').textContent = TOTAL + ' всего';
    }

    function loadHistory() {
        const saved = localStorage.getItem('awesome_history');
        if (saved) {
            try {
                chatHistory = JSON.parse(saved);
                renderHistory();
                if (chatHistory.length > 0) {
                    const last = chatHistory[chatHistory.length - 1];
                    currentChatId = last.id;
                    renderMessages(last.messages);
                }
                return;
            } catch(e) {}
        }
        if (chatHistory.length === 0) newChat();
    }

    function saveHistory() {
        localStorage.setItem('awesome_history', JSON.stringify(chatHistory));
    }

    function renderHistory() {
        historyList.innerHTML = '';
        if (chatHistory.length === 0) {
            historyList.innerHTML = '<div style="padding:12px;color:var(--text-muted);font-size:13px;text-align:center;">Нет чатов</div>';
            return;
        }
        chatHistory.slice().reverse().forEach(chat => {
            const div = document.createElement('div');
            div.className = 'history-item' + (chat.id === currentChatId ? ' active' : '');
            div.innerHTML = '<span class="icon">💬</span> ' + (chat.title || 'Чат');
            div.onclick = () => switchChat(chat.id);
            historyList.appendChild(div);
        });
    }

    function switchChat(chatId) {
        currentChatId = chatId;
        const chat = chatHistory.find(c => c.id === chatId);
        if (chat) { renderMessages(chat.messages); renderHistory(); }
        closeSidebar();
    }

    function newChat() {
        const id = 'chat_' + Date.now();
        chatHistory.push({
            id: id,
            title: 'Новый чат',
            messages: [{ role: 'bot', content: 'Привет! Чем могу помочь? 🧠', time: new Date().toISOString() }]
        });
        currentChatId = id;
        renderMessages(chatHistory.find(c => c.id === id).messages);
        renderHistory();
        saveHistory();
        closeSidebar();
        userInput.focus();
    }

    function clearChat() {
        if (!currentChatId) return;
        const chat = chatHistory.find(c => c.id === currentChatId);
        if (chat) {
            chat.messages = [{ role: 'bot', content: 'Чат очищен. Задай новый вопрос! 🧠', time: new Date().toISOString() }];
            renderMessages(chat.messages);
            saveHistory();
        }
    }

    function renderMessages(messages) {
        messagesEl.innerHTML = '';
        messages.forEach(msg => addMessageToDOM(msg.role, msg.content, msg.time, false));
        scrollToBottom();
    }

    function addMessageToDOM(role, content, time, animate = true) {
        const div = document.createElement('div');
        div.className = 'msg ' + role;
        if (animate) div.style.animation = 'none';
        const avatar = role === 'user' ? (USER_NAME[0] || '👤') : '🧠';
        const timeStr = time ? new Date(time).toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' }) : 'now';
        div.innerHTML = '<div class="avatar">' + avatar + '</div><div class="content">' + formatContent(content) + '<span class="msg-time">' + timeStr + '</span></div>';
        messagesEl.insertBefore(div, typingIndicator);
        if (animate) requestAnimationFrame(() => div.style.animation = '');
        scrollToBottom();
    }

    function formatContent(text) {
        text = text.replace(/\\*\\*(.+?)\\*\\*/g, '<b>$1</b>');
        text = text.replace(/\\*(.+?)\\*/g, '<i>$1</i>');
        text = text.replace(/`(.+?)`/g, '<code>$1</code>');
        text = text.replace(/\\n/g, '<br>');
        text = text.replace(/(https?:\\/\\/[^\\s]+)/g, '<a href="$1" target="_blank">$1</a>');
        return text;
    }

    function scrollToBottom() {
        requestAnimationFrame(() => messagesEl.scrollTop = messagesEl.scrollHeight);
    }

    async function sendMessage() {
        const text = userInput.value.trim();
        if (!text || isSending) return;

        isSending = true;
        sendBtn.disabled = true;
        userInput.disabled = true;

        const userMsg = { role: 'user', content: text, time: new Date().toISOString() };
        addMessageToDOM('user', text, userMsg.time);
        userInput.value = '';
        userInput.style.height = 'auto';

        typingIndicator.style.display = 'flex';

        let chat = chatHistory.find(c => c.id === currentChatId);
        if (!chat) { newChat(); chat = chatHistory.find(c => c.id === currentChatId); }
        if (chat) {
            chat.messages.push(userMsg);
            if (chat.messages.length === 2 && chat.messages[0].role === 'bot') {
                chat.title = text.slice(0, 30) + (text.length > 30 ? '...' : '');
            }
            saveHistory();
            renderHistory();
        }

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: USER_ID, text: text })
            });

            typingIndicator.style.display = 'none';

            if (response.ok) {
                const data = await response.json();
                const botMsg = { role: 'bot', content: data.response || '❌ Не удалось получить ответ', time: new Date().toISOString() };
                addMessageToDOM('bot', botMsg.content, botMsg.time);
                if (chat) { chat.messages.push(botMsg); saveHistory(); renderHistory(); }
                loadUserData();
            } else {
                const err = await response.json();
                addMessageToDOM('bot', '⚠️ ' + (err.error || 'Ошибка сервера'), new Date().toISOString());
            }
        } catch (e) {
            typingIndicator.style.display = 'none';
            addMessageToDOM('bot', '⚠️ Ошибка соединения: ' + e.message, new Date().toISOString());
        }

        isSending = false;
        sendBtn.disabled = false;
        userInput.disabled = false;
        userInput.focus();
        scrollToBottom();
    }

    function handleKey(e) {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
        e.target.style.height = 'auto';
        e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px';
    }

    function toggleSidebar() { sidebar.classList.toggle('open'); overlay.classList.toggle('active'); }
    function closeSidebar() { sidebar.classList.remove('open'); overlay.classList.remove('active'); }
    function showUserMenu() { alert('👤 ' + USER_NAME + '\\nID: ' + USER_ID + '\\nPremium: ' + (PREMIUM ? '✅' : '❌')); }

    loadUserData();
    loadHistory();
    userInput.focus();
    overlay.addEventListener('click', closeSidebar);
    console.log('🧠 AWESOME AI 2026 запущен');
    console.log('👤', USER_NAME, 'ID:', USER_ID);
</script>
</body>
</html>
'''

# ============================================================
# FLASK РОУТЫ
# ============================================================
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/chat', methods=['POST'])
def chat_api():
    data = request.json
    if not data:
        return jsonify({'error': 'No data'}), 400
    
    user_id = data.get('user_id')
    text = data.get('text', '').strip()
    
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    if not text:
        return jsonify({'error': 'text required'}), 400
    
    if not can_send_message(user_id):
        return jsonify({'error': 'Лимит исчерпан. Купи Premium.'}), 403
    
    try:
        ensure_user(user_id)
        response = process_message(user_id, text)
        increment_messages(user_id)
        return jsonify({'response': response})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/user', methods=['GET'])
def user_api():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    
    ensure_user(user_id)
    user_data = get_user(user_id)
    if user_data:
        premium = get_premium_status(user_id)
        messages_today = get_messages_today(user_id)
        total = get_total_messages(user_id)
        return jsonify({
            'user_id': user_id,
            'username': user_data.get('username', 'Гость'),
            'premium': premium,
            'messages_today': messages_today,
            'total_messages': total,
            'remaining': (FREE_LIMIT - messages_today) if not premium else PREMIUM_LIMIT
        })
    return jsonify({'error': 'user not found'}), 404

@app.route('/api/search', methods=['GET'])
def search_api():
    query = request.args.get('q')
    if not query:
        return jsonify({'error': 'q required'}), 400
    result = search_all_internet(query)
    if result:
        return jsonify({'result': result})
    return jsonify({'error': 'No results'}), 404

@app.route('/api/weather', methods=['GET'])
def weather_api():
    city = request.args.get('city')
    if not city:
        return jsonify({'error': 'city required'}), 400
    weather = get_weather(city)
    if weather:
        return jsonify({'weather': weather})
    return jsonify({'error': 'Weather not found'}), 404

@app.route('/api/currency', methods=['GET'])
def currency_api():
    currency = get_currency()
    if currency:
        return jsonify({'currency': currency})
    return jsonify({'error': 'Currency not found'}), 404

@app.route('/api/crypto', methods=['GET'])
def crypto_api():
    crypto = get_crypto()
    if crypto:
        return jsonify({'crypto': crypto})
    return jsonify({'error': 'Crypto not found'}), 404

@app.route('/api/generate/image', methods=['POST'])
def generate_image_api():
    data = request.json
    if not data:
        return jsonify({'error': 'No data'}), 400
    
    prompt = data.get('prompt')
    user_id = data.get('user_id')
    
    if not prompt:
        return jsonify({'error': 'prompt required'}), 400
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    
    if not can_send_message(user_id):
        return jsonify({'error': 'Лимит исчерпан'}), 403
    
    image_data = generate_image_from_prompt(prompt)
    if image_data:
        increment_messages(user_id)
        return jsonify({'success': True, 'image': base64.b64encode(image_data).decode('utf-8')})
    return jsonify({'error': 'Failed to generate image'}), 500

# ============================================================
# ЗАПУСК
# ============================================================
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print("=" * 60)
    print("🧠 AWESOME AI 2026 — ПОЛНАЯ КОПИЯ DEEPSEEK")
    print("=" * 60)
    print(f"🚀 Запуск на порту {port}")
    print(f"📅 {get_current_datetime()} (МСК)")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=False)
