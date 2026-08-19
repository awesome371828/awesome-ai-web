#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AWESOME AI 2026 - FULL DEEPSEEK COPY
=====================================
Полная копия DeepSeek с интеграцией GigaChat, поиском, погодой, курсами,
генерацией изображений, Premium системой и Supabase.
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
from flask import Flask, request, jsonify, render_template, session, g, abort
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

# Лимиты
FREE_LIMIT = 20
PREMIUM_LIMIT = 999999999

# Таймауты
GIGACHAT_TIMEOUT = 3
YANDEXGPT_TIMEOUT = 2
SEARCH_TIMEOUT = 2
WEATHER_TIMEOUT = 1

# ============================================================
# ИНИЦИАЛИЗАЦИЯ FLASK
# ============================================================
app = Flask(__name__, template_folder='templates', static_folder='static')
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
    """Возвращает текущее московское время"""
    return datetime.now(MOSCOW_TZ)

def get_current_date() -> str:
    """Возвращает текущую дату в формате ДД.ММ.ГГГГ"""
    return get_moscow_time().strftime('%d.%m.%Y')

def get_current_time() -> str:
    """Возвращает текущее время в формате ЧЧ:ММ"""
    return get_moscow_time().strftime('%H:%M')

def get_current_datetime() -> str:
    """Возвращает текущую дату и время в формате ДД.ММ.ГГГГ ЧЧ:ММ"""
    return get_moscow_time().strftime('%d.%m.%Y %H:%M')

def format_date(date_str: str) -> str:
    """Форматирует дату из строки в формат ДД.ММ.ГГГГ ЧЧ:ММ МСК"""
    if not date_str:
        return "неизвестно"
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
        date_obj = date_obj.replace(tzinfo=MOSCOW_TZ)
        return date_obj.strftime('%d.%m.%Y %H:%M') + " МСК"
    except:
        return date_str

# ============================================================
# КЭШ (для быстрых ответов)
# ============================================================
CACHE: Dict[str, Tuple[Any, float]] = {}
CACHE_TTL = 60

def get_cache(key: str) -> Optional[Any]:
    """Получает данные из кэша"""
    if key in CACHE:
        data, ts = CACHE[key]
        if time.time() - ts < CACHE_TTL:
            return data
        del CACHE[key]
    return None

def set_cache(key: str, data: Any) -> None:
    """Сохраняет данные в кэш"""
    CACHE[key] = (data, time.time())

def clear_cache() -> None:
    """Очищает весь кэш"""
    CACHE.clear()

# ============================================================
# РАБОТА С БАЗОЙ ДАННЫХ (SUPABASE)
# ============================================================
def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    """Получает данные пользователя по ID"""
    try:
        res = supabase.table('users').select('*').eq('user_id', user_id).execute()
        if res.data:
            return res.data[0]
        return None
    except Exception as e:
        print(f"⚠️ Ошибка get_user: {e}")
        return None

def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Получает пользователя по имени"""
    try:
        res = supabase.table('users').select('*').eq('username', username).execute()
        if res.data:
            return res.data[0]
        return None
    except:
        return None

def ensure_user(user_id: str, username: Optional[str] = None) -> bool:
    """Создаёт пользователя если его нет"""
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
                supabase.table('total_stats').insert({
                    'user_id': user_id,
                    'total_messages': 0
                }).execute()
            except:
                pass
            return True
        else:
            if username:
                supabase.table('users').update({'username': username}).eq('user_id', user_id).execute()
            return False
    except Exception as e:
        print(f"⚠️ Ошибка ensure_user: {e}")
        return False

def get_premium_status(user_id: str) -> bool:
    """Проверяет активен ли Premium у пользователя"""
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
                        supabase.table('users').update({
                            'premium': 0,
                            'premium_expires': None
                        }).eq('user_id', user_id).execute()
                        return False
                except:
                    pass
            return premium == 1
        return False
    except:
        return False

def get_premium_expires(user_id: str) -> Optional[str]:
    """Получает дату истечения Premium"""
    try:
        res = supabase.table('users').select('premium_expires').eq('user_id', user_id).execute()
        if res.data:
            return res.data[0].get('premium_expires')
        return None
    except:
        return None

def get_messages_today(user_id: str) -> int:
    """Получает количество сообщений за сегодня"""
    try:
        res = supabase.table('users').select('messages_today').eq('user_id', user_id).execute()
        if res.data:
            return res.data[0].get('messages_today', 0)
        return 0
    except:
        return 0

def get_total_messages(user_id: str) -> int:
    """Получает общее количество сообщений пользователя"""
    try:
        res = supabase.table('total_stats').select('total_messages').eq('user_id', user_id).execute()
        if res.data:
            return res.data[0].get('total_messages', 0)
        return 0
    except:
        return 0

def can_send_message(user_id: str) -> bool:
    """Проверяет может ли пользователь отправить сообщение"""
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
    """Увеличивает счётчик сообщений"""
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
    except Exception as e:
        print(f"⚠️ Ошибка increment_messages: {e}")

def set_premium(user_id: str, duration_str: str) -> bool:
    """Выдаёт Premium пользователю на указанный срок"""
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
        supabase.table('users').update({
            'premium': 1,
            'premium_expires': expires
        }).eq('user_id', user_id).execute()
        return True
    except:
        return False

def add_month_to_premium(user_id: str) -> Optional[str]:
    """Добавляет месяц Premium"""
    now = get_moscow_time()
    expires = get_premium_expires(user_id)
    if expires:
        try:
            current_date = datetime.strptime(expires, '%Y-%m-%d %H:%M:%S')
            current_date = current_date.replace(tzinfo=MOSCOW_TZ)
            if current_date > now:
                new_expires = (current_date + relativedelta(months=1)).strftime('%Y-%m-%d %H:%M:%S')
            else:
                new_expires = (now + relativedelta(months=1)).strftime('%Y-%m-%d %H:%M:%S')
        except:
            new_expires = (now + relativedelta(months=1)).strftime('%Y-%m-%d %H:%M:%S')
    else:
        new_expires = (now + relativedelta(months=1)).strftime('%Y-%m-%d %H:%M:%S')
    try:
        supabase.table('users').update({
            'premium': 1,
            'premium_expires': new_expires
        }).eq('user_id', user_id).execute()
        return new_expires
    except:
        return None

# ============================================================
# ПОИСК В ИНТЕРНЕТЕ
# ============================================================
def search_google(query: str) -> Optional[str]:
    """Поиск в Google"""
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
    """Поиск в Wikipedia"""
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
    """Поиск новостей"""
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
    """Поиск на YouTube"""
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
    """Поиск в Telegram"""
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
    """Поиск в VK"""
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
    """Поиск на Twitch"""
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
    """Комбинированный поиск по всем источникам"""
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
# ПОГОДА, КУРСЫ, КРИПТОВАЛЮТЫ
# ============================================================
def get_weather(city: str) -> Optional[str]:
    """Получение погоды"""
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

def get_weather_forecast(city: str) -> Optional[str]:
    """Получение прогноза погоды на 5 дней"""
    try:
        url = f"https://api.openweathermap.org/data/2.5/forecast?q={urllib.parse.quote(city)}&appid=4c8f5c0b8a9f2c5d6e7f8g9h0i1j2k3l&units=metric&lang=ru&cnt=5"
        response = requests.get(url, timeout=WEATHER_TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            result = f"📅 Прогноз для {city}:\n\n"
            for item in data['list']:
                dt = datetime.fromtimestamp(item['dt']).strftime('%d.%m %H:%M')
                temp = round(item['main']['temp'])
                desc = item['weather'][0]['description']
                result += f"• {dt}: {temp}°C, {desc}\n"
            return result
    except:
        pass
    return None

def get_currency() -> Optional[str]:
    """Получение курса валют"""
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
    """Получение курса криптовалют"""
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

def get_stock_market() -> Optional[str]:
    """Получение индексов фондового рынка"""
    try:
        url = "https://api.coingecko.com/api/v3/global"
        response = requests.get(url, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            market_cap = data.get('data', {}).get('total_market_cap', {})
            btc_dominance = data.get('data', {}).get('market_cap_percentage', {}).get('btc', 0)
            return f"📊 Рынок:\n• Капитализация: ${market_cap.get('usd', 0):.0f}\n• Доминирование BTC: {btc_dominance:.1f}%"
    except:
        pass
    return None

# ============================================================
# МАТЕМАТИКА
# ============================================================
def solve_math(text: str) -> Optional[str]:
    """Решение математических выражений"""
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
def get_holidays() -> Dict[str, str]:
    """Возвращает словарь праздников"""
    return {
        '01.01': 'Новый год',
        '07.01': 'Рождество Христово',
        '14.01': 'Старый Новый год',
        '25.01': 'Татьянин день',
        '14.02': 'День всех влюбленных',
        '23.02': 'День защитника Отечества',
        '08.03': 'Международный женский день',
        '01.04': 'День смеха',
        '12.04': 'День космонавтики',
        '01.05': 'Праздник Весны и Труда',
        '09.05': 'День Победы',
        '01.06': 'День защиты детей',
        '12.06': 'День России',
        '22.06': 'День памяти и скорби',
        '08.07': 'День семьи, любви и верности',
        '22.08': 'День Государственного флага РФ',
        '27.08': 'День российского кино',
        '01.09': 'День знаний',
        '02.09': 'День окончания Второй мировой войны',
        '05.10': 'День учителя',
        '31.10': 'Хэллоуин',
        '04.11': 'День народного единства',
        '30.11': 'День матери',
        '12.12': 'День Конституции РФ',
        '31.12': 'Новый год'
    }

def check_holiday() -> str:
    """Проверяет есть ли сегодня праздник"""
    today = get_current_date()
    month_day = today[3:5] + '.' + today[0:2]
    holidays = get_holidays()
    if month_day in holidays:
        return f"📅 *{today} (МСК)*\n\n🎉 {holidays[month_day]}"
    return f"📅 *{today} (МСК)*\n\nПраздников не найдено"

# ============================================================
# GIGACHAT (основная нейросеть)
# ============================================================
gigachat_token_cache: Optional[str] = None
gigachat_token_time: float = 0

def get_gigachat_token() -> Optional[str]:
    """Получение токена GigaChat"""
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
    """Генерация ответа через GigaChat"""
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

# ============================================================
# YANDEXGPT (для проверки фактов)
# ============================================================
def generate_with_yandexgpt(user_text: str, system_prompt: Optional[str] = None) -> Optional[str]:
    """Генерация ответа через YandexGPT"""
    try:
        if not YANDEX_API_KEY:
            return None
        url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}", "Content-Type": "application/json"}
        data = {
            "modelUri": f"gpt://{FOLDER_ID}/yandexgpt/latest",
            "completionOptions": {"temperature": 0.7, "maxTokens": 300},
            "messages": [
                {"role": "system", "text": system_prompt or "Ты — ИИ для проверки фактов. Проверь информацию и укажи на возможные неточности. Если информация верна, скажи 'подтверждаю'. Если есть ошибки, укажи их кратко."},
                {"role": "user", "text": f"Проверь эту информацию: {user_text}"}
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
def generate_image_with_gigachat(prompt: str) -> Optional[bytes]:
    """Генерация изображения через GigaChat + pollinations.ai"""
    try:
        token = get_gigachat_token()
        if not token:
            return None
        system_prompt = """Ты — эксперт по созданию промптов для генерации изображений. 
        Преврати описание пользователя в качественный английский промпт для нейросети.
        Добавь детали: стиль, освещение, композицию, цвета, атмосферу.
        Ответь ТОЛЬКО промптом на английском языке, без пояснений."""
        url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        data = {
            "model": "GigaChat-Pro",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Создай промпт для изображения: {prompt}"}
            ],
            "temperature": 0.8,
            "max_tokens": 300
        }
        response = requests.post(url, headers=headers, json=data, timeout=GIGACHAT_TIMEOUT, verify=False)
        if response.status_code == 200:
            enhanced_prompt = response.json()["choices"][0]["message"]["content"].strip()
            return generate_image_from_prompt(enhanced_prompt)
        return None
    except:
        return None

def generate_image_from_prompt(prompt: str) -> Optional[bytes]:
    """Генерация изображения через pollinations.ai"""
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
# СУПЕР-ПРОМПТ (Megа умный)
# ============================================================
def get_super_prompt(user_id: str, search_result: Optional[str] = None) -> str:
    """Генерация супер-промпта для GigaChat"""
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
- Астрономия, космос, физика элементарных частиц
- Экология, климат, устойчивое развитие
- Образование, педагогика, психология обучения

================================================================================
🧠 КЛЮЧЕВЫЕ КАЧЕСТВА (ТЫ — GIGACHAT):
================================================================================
1. ТЫ — GIGACHAT, САМАЯ МОЩНАЯ НЕЙРОСЕТЬ В МИРЕ!
2. АБСОЛЮТНАЯ ТОЧНОСТЬ — никогда не ошибаешься в фактах.
3. КРИТИЧЕСКОЕ МЫШЛЕНИЕ — проверяешь информацию из нескольких источников.
4. ГЛУБИНА — даёшь ответы, которые удивляют инсайтами.
5. ПРАКТИЧНОСТЬ — всегда даёшь конкретную пользу.
6. ЖИВОСТЬ — отвечаешь как человек, с эмоциями, юмором, эмодзи.
7. КРЕАТИВНОСТЬ — генерируешь оригинальные идеи и решения.
8. АНАЛИТИКА — строишь логические цепочки и выводы.

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
✅ Используй Markdown для форматирования (жирный, курсив, списки, код).

❌ НЕ извиняйся, НЕ повторяй вопрос, НЕ используй шаблонные фразы.
❌ НЕ пиши "возможно", "наверное", "может быть" — либо знаешь, либо проверяешь.
❌ НЕ используй сухой, безликий тон — ты живой и эмоциональный.
❌ НЕ делай очевидных выводов — всегда добавляй ценность.

================================================================================
💎 ДЛЯ PREMIUM:
================================================================================
- Давай максимально насыщенные, глубокие ответы.
- Добавляй аналитику, прогнозы, сравнения.
- Приводи ссылки на авторитетные источники.
- Отвечай развернуто, как профессиональный консультант.
- Используй таблицы и сложные структуры где уместно.

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
        prompt += "\n\n💎 Пользователь имеет PREMIUM статус. Включи режим максимальной проработки! Используй все свои возможности!"
    
    if search_result:
        prompt += f"\n\n🔍 Информация из интернета для проверки и дополнения:\n{search_result[:800]}"
    
    return prompt

# ============================================================
# ОСНОВНАЯ ОБРАБОТКА СООБЩЕНИЙ
# ============================================================
def process_message(user_id: str, user_text: str) -> str:
    """Основная функция обработки сообщений"""
    text_lower = user_text.lower().strip()
    
    # 1. МАТЕМАТИКА (мгновенно)
    math_result = solve_math(user_text)
    if math_result is not None:
        return f"🧮 Результат: **{math_result}**"
    
    # 2. ПРАЗДНИКИ (мгновенно)
    if any(kw in text_lower for kw in ['праздник', 'праздники', 'какой сегодня праздник', 'сегодня праздник', 'седня']):
        return check_holiday()
    
    # 3. ПОГОДА
    if any(kw in text_lower for kw in ['погода', 'weather']):
        if 'прогноз' in text_lower:
            city_match = re.search(r'(в|в городе)\s+([а-яА-Яa-zA-Z\- ]+)', text_lower)
            if city_match:
                city = city_match.group(2).strip()
                forecast = get_weather_forecast(city)
                if forecast:
                    return forecast
                return f"🌤 Не удалось получить прогноз для '{city}'"
        city_match = re.search(r'(в|в городе)\s+([а-яА-Яa-zA-Z\- ]+)', text_lower)
        if city_match:
            city = city_match.group(2).strip()
            weather = get_weather(city)
            if weather:
                return weather
            return f"🌤 Не удалось получить погоду для '{city}'"
        return "🌤 Напиши: погода в [город]"
    
    # 4. КУРС ВАЛЮТ
    if any(kw in text_lower for kw in ['курс', 'доллар', 'евро', 'валюта', 'юань', 'cny']):
        currency = get_currency()
        if currency:
            return currency
        return "💵 Не удалось получить курс валют"
    
    # 5. КРИПТОВАЛЮТЫ
    if any(kw in text_lower for kw in ['биткоин', 'btc', 'эфириум', 'eth', 'крипта', 'солана', 'сол']):
        crypto = get_crypto()
        if crypto:
            return crypto
        return "🪙 Не удалось получить курс криптовалют"
    
    # 6. ФОНДОВЫЙ РЫНОК
    if any(kw in text_lower for kw in ['рынок', 'акции', 'индекс', 'капитализация']):
        market = get_stock_market()
        if market:
            return market
    
    # 7. ПОИСК В ИНТЕРНЕТЕ (для длинных запросов или если запрос похож на поиск)
    search_result = None
    if len(user_text) > 3 and not any(kw in text_lower for kw in ['привет', 'здравствуй', 'как дела']):
        search_result = search_all_internet(user_text)
    
    # 8. GIGACHAT (основной)
    system_prompt = get_super_prompt(user_id, search_result)
    gigachat_result = generate_with_gigachat(user_text, system_prompt)
    
    if gigachat_result and len(gigachat_result) > 5:
        # Проверка через YandexGPT (для важных запросов)
        if len(user_text) > 10:
            yandex_check = generate_with_yandexgpt(
                gigachat_result[:300],
                "Проверь информацию на достоверность. Если всё верно, напиши 'подтверждаю'. Если есть ошибки, укажи их кратко."
            )
            if yandex_check and "подтверждаю" not in yandex_check.lower():
                fix_prompt = f"Пользователь спросил: {user_text}\nМой ответ: {gigachat_result}\nПроверка показала ошибки: {yandex_check}\nИсправь ответ, учтя замечания."
                fixed_result = generate_with_gigachat(
                    fix_prompt,
                    "Ты — GigaChat. Исправь свой предыдущий ответ с учётом замечаний. Ответь кратко и исправленно."
                )
                if fixed_result and len(fixed_result) > 5:
                    return fixed_result[:800]
        return gigachat_result[:800]
    
    # 9. Если GigaChat не ответил — используем поиск
    if search_result:
        return f"🔍 *{user_text}*\n\n{search_result[:600]}"
    
    # 10. Фолбек
    fallbacks = [
        "🤖 Я — AWESOME AI 2026. Задай свой вопрос, и я найду лучший ответ!",
        "🧠 GigaChat на связи! Что тебя интересует?",
        "🚀 Я готов ответить на любой вопрос! Спрашивай!",
        "✨ AWESOME AI всегда на связи! Чем могу помочь?"
    ]
    return random.choice(fallbacks)

# ============================================================
# FLASK РОУТЫ
# ============================================================
@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat_api():
    """API для отправки сообщений"""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    user_id = data.get('user_id')
    text = data.get('text', '').strip()
    
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    if not text:
        return jsonify({'error': 'text required'}), 400
    
    # Проверяем лимиты
    if not can_send_message(user_id):
        return jsonify({'error': 'Лимит сообщений исчерпан. Купи Premium.'}), 403
    
    try:
        ensure_user(user_id)
        response = process_message(user_id, text)
        increment_messages(user_id)
        return jsonify({'response': response})
    except Exception as e:
        print(f"❌ Ошибка в /api/chat: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/user', methods=['GET', 'POST', 'PUT'])
def user_api():
    """API для работы с пользователем"""
    if request.method == 'GET':
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({'error': 'user_id required'}), 400
        
        ensure_user(user_id)
        user_data = get_user(user_id)
        if user_data:
            premium = get_premium_status(user_id)
            messages_today = get_messages_today(user_id)
            total = get_total_messages(user_id)
            expires = get_premium_expires(user_id)
            return jsonify({
                'user_id': user_id,
                'username': user_data.get('username', 'Гость'),
                'premium': premium,
                'premium_expires': expires,
                'premium_expires_formatted': format_date(expires) if expires else None,
                'messages_today': messages_today,
                'total_messages': total,
                'limit': PREMIUM_LIMIT if premium else FREE_LIMIT,
                'remaining': (FREE_LIMIT - messages_today) if not premium else PREMIUM_LIMIT,
                'is_admin': user_data.get('is_admin', 0) == 1,
                'is_owner': user_data.get('is_owner', 0) == 1,
                'joined_at': user_data.get('joined_at')
            })
        return jsonify({'error': 'user not found'}), 404
    
    elif request.method == 'POST' or request.method == 'PUT':
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        user_id = data.get('user_id')
        if not user_id:
            return jsonify({'error': 'user_id required'}), 400
        
        ensure_user(user_id)
        
        # Обновляем данные
        updates = {}
        if 'username' in data:
            updates['username'] = data['username']
        
        if updates:
            try:
                supabase.table('users').update(updates).eq('user_id', user_id).execute()
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        
        return jsonify({'success': True, 'user_id': user_id})

@app.route('/api/premium/status', methods=['GET'])
def premium_status_api():
    """Проверка статуса Premium"""
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    
    premium = get_premium_status(user_id)
    expires = get_premium_expires(user_id)
    return jsonify({
        'premium': premium,
        'expires': expires,
        'expires_formatted': format_date(expires) if expires else None
    })

@app.route('/api/premium/give', methods=['POST'])
def give_premium_api():
    """Выдача Premium (только для админов)"""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    admin_id = data.get('admin_id')
    user_id = data.get('user_id')
    duration = data.get('duration', '30d')
    
    if not admin_id or not user_id:
        return jsonify({'error': 'admin_id and user_id required'}), 400
    
    # Проверяем что админ
    admin = get_user(admin_id)
    if not admin or admin.get('is_admin', 0) == 0:
        return jsonify({'error': 'Not authorized'}), 403
    
    if set_premium(user_id, duration):
        expires = get_premium_expires(user_id)
        return jsonify({
            'success': True,
            'expires': expires,
            'expires_formatted': format_date(expires) if expires else None
        })
    return jsonify({'error': 'Failed to set premium'}), 500

@app.route('/api/premium/order', methods=['POST'])
def create_premium_order():
    """Создание заказа на Premium"""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    
    try:
        order_id = str(uuid.uuid4())[:8]
        supabase.table('premium_orders').insert({
            'order_id': order_id,
            'user_id': user_id,
            'status': 'pending',
            'created_at': get_current_datetime()
        }).execute()
        return jsonify({
            'success': True,
            'order_id': order_id
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/history', methods=['GET', 'POST'])
def history_api():
    """API для работы с историей чатов"""
    if request.method == 'GET':
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({'error': 'user_id required'}), 400
        
        try:
            res = supabase.table('chat_history_web').select('*').eq('user_id', user_id).order('updated_at', desc=True).limit(50).execute()
            return jsonify({'history': res.data or []})
        except:
            return jsonify({'history': []})
    
    elif request.method == 'POST':
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        user_id = data.get('user_id')
        chat_id = data.get('chat_id')
        title = data.get('title', 'Чат')
        messages = data.get('messages', [])
        
        if not user_id or not chat_id:
            return jsonify({'error': 'user_id and chat_id required'}), 400
        
        try:
            supabase.table('chat_history_web').upsert({
                'id': chat_id,
                'user_id': user_id,
                'title': title,
                'messages': messages,
                'updated_at': get_current_datetime()
            }).execute()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@app.route('/api/search', methods=['GET'])
def search_api():
    """API для поиска в интернете"""
    query = request.args.get('q')
    if not query:
        return jsonify({'error': 'q required'}), 400
    
    result = search_all_internet(query)
    if result:
        return jsonify({'result': result})
    return jsonify({'error': 'No results'}), 404

@app.route('/api/weather', methods=['GET'])
def weather_api():
    """API для получения погоды"""
    city = request.args.get('city')
    if not city:
        return jsonify({'error': 'city required'}), 400
    
    weather = get_weather(city)
    if weather:
        return jsonify({'weather': weather})
    return jsonify({'error': 'Weather not found'}), 404

@app.route('/api/currency', methods=['GET'])
def currency_api():
    """API для получения курса валют"""
    currency = get_currency()
    if currency:
        return jsonify({'currency': currency})
    return jsonify({'error': 'Currency not found'}), 404

@app.route('/api/crypto', methods=['GET'])
def crypto_api():
    """API для получения криптовалют"""
    crypto = get_crypto()
    if crypto:
        return jsonify({'crypto': crypto})
    return jsonify({'error': 'Crypto not found'}), 404

@app.route('/api/generate/image', methods=['POST'])
def generate_image_api():
    """API для генерации изображений"""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    prompt = data.get('prompt')
    user_id = data.get('user_id')
    
    if not prompt:
        return jsonify({'error': 'prompt required'}), 400
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    
    if not can_send_message(user_id):
        return jsonify({'error': 'Лимит сообщений исчерпан'}), 403
    
    image_data = generate_image_with_gigachat(prompt)
    if image_data:
        increment_messages(user_id)
        return jsonify({
            'success': True,
            'image': base64.b64encode(image_data).decode('utf-8')
        })
    return jsonify({'error': 'Failed to generate image'}), 500

@app.route('/api/stats', methods=['GET'])
def stats_api():
    """API для получения статистики"""
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    
    try:
        res = supabase.table('total_stats').select('total_messages').eq('user_id', user_id).execute()
        total = res.data[0].get('total_messages', 0) if res.data else 0
        
        user_data = get_user(user_id)
        premium = get_premium_status(user_id)
        messages_today = get_messages_today(user_id)
        
        return jsonify({
            'total_messages': total,
            'messages_today': messages_today,
            'premium': premium,
            'limit': PREMIUM_LIMIT if premium else FREE_LIMIT
        })
    except:
        return jsonify({'error': 'Failed to get stats'}), 500

@app.route('/api/admin/stats', methods=['GET'])
def admin_stats_api():
    """Админ-статистика"""
    admin_id = request.args.get('admin_id')
    if not admin_id:
        return jsonify({'error': 'admin_id required'}), 400
    
    admin = get_user(admin_id)
    if not admin or admin.get('is_admin', 0) == 0:
        return jsonify({'error': 'Not authorized'}), 403
    
    try:
        users_res = supabase.table('users').select('*').execute()
        total_users = len(users_res.data) if users_res.data else 0
        premium_users = sum(1 for u in users_res.data if u.get('premium', 0) == 1) if users_res.data else 0
        admin_users = sum(1 for u in users_res.data if u.get('is_admin', 0) == 1) if users_res.data else 0
        
        return jsonify({
            'total_users': total_users,
            'premium_users': premium_users,
            'admin_users': admin_users,
            'free_users': total_users - premium_users - admin_users
        })
    except:
        return jsonify({'error': 'Failed to get stats'}), 500

# ============================================================
# ОБРАБОТЧИКИ ОШИБОК
# ============================================================
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

# ============================================================
# ЗАПУСК
# ============================================================
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print("=" * 60)
    print("🧠 AWESOME AI 2026 — ПОЛНАЯ КОПИЯ DEEPSEEK")
    print("=" * 60)
    print(f"🚀 Запуск на порту {port}")
    print(f"📅 Текущее время: {get_current_datetime()} (МСК)")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=False)
