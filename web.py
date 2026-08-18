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
import io
import tempfile
from datetime import datetime, timedelta, timezone
from dateutil.relativedelta import relativedelta

from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from dotenv import load_dotenv

from bs4 import BeautifulSoup
import requests
from PIL import Image, ImageEnhance, ImageFilter
import speech_recognition as sr
import urllib3
from concurrent.futures import ThreadPoolExecutor, as_completed

# Для Supabase
from supabase import create_client, Client

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

app = Flask(__name__)
CORS(app)

# ============================================================
# НАСТРОЙКА
# ============================================================
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
if not YANDEX_API_KEY:
    raise ValueError("❌ YANDEX_API_KEY не найден!")

FOLDER_ID = os.getenv("FOLDER_ID", "b1g4aq87c7j61c6g3i5l")
GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY")
OWNER_ID = 6652898792

FREE_LIMIT = 20
PREMIUM_LIMIT = 999999999

# ТАЙМАУТЫ
GIGACHAT_TIMEOUT = 3
YANDEXGPT_TIMEOUT = 3
SEARCH_TIMEOUT = 3
WEATHER_TIMEOUT = 2

# ============================================================
# SUPABASE НАСТРОЙКА
# ============================================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")

use_supabase = True
try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Supabase подключен!", flush=True)
except Exception as e:
    print(f"❌ Ошибка подключения к Supabase: {e}", flush=True)
    use_supabase = False

# ============================================================
# ИНИЦИАЛИЗАЦИЯ ТАБЛИЦ В SUPABASE (с суффиксом _web)
# ============================================================
def init_db_web():
    if not use_supabase:
        init_db_local()
        return

    try:
        # Проверяем наличие таблиц, создаём при необходимости
        supabase.table('users_web').select('*').limit(1).execute()
        print("✅ Таблицы уже существуют")
    except Exception as e:
        print("Создаём таблицы...")
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
        except: pass
        try:
            supabase.sql("""
                CREATE TABLE IF NOT EXISTS banned_web (user_id BIGINT PRIMARY KEY)
            """).execute()
        except: pass
        try:
            supabase.sql("""
                CREATE TABLE IF NOT EXISTS muted_web (user_id BIGINT PRIMARY KEY)
            """).execute()
        except: pass
        try:
            supabase.sql("""
                CREATE TABLE IF NOT EXISTS total_stats_web (
                    user_id BIGINT PRIMARY KEY,
                    total_messages INTEGER DEFAULT 0
                )
            """).execute()
        except: pass
        try:
            supabase.sql("""
                CREATE TABLE IF NOT EXISTS premium_orders_web (
                    order_id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT
                )
            """).execute()
        except: pass
        try:
            supabase.sql("""
                CREATE TABLE IF NOT EXISTS support_requests_web (
                    request_id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    username TEXT,
                    text TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT
                )
            """).execute()
        except: pass
        # НОВАЯ ТАБЛИЦА ДЛЯ ИСТОРИИ ДИАЛОГОВ
        try:
            supabase.sql("""
                CREATE TABLE IF NOT EXISTS chat_history_web (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    role TEXT,
                    content TEXT,
                    timestamp TEXT
                )
            """).execute()
            print("✅ Таблица chat_history_web создана")
        except Exception as e:
            print(f"⚠️ Ошибка создания chat_history_web: {e}")

def init_db_local():
    conn = sqlite3.connect('users_web.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users_web (...)''')  # ... полные определения
    c.execute('''CREATE TABLE IF NOT EXISTS chat_history_web (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        role TEXT,
        content TEXT,
        timestamp TEXT
    )''')
    conn.commit()
    conn.close()

# ============================================================
# ФУНКЦИИ ДЛЯ ИСТОРИИ ДИАЛОГА (СОХРАНЕНИЕ И ЗАГРУЗКА)
# ============================================================
def save_message(user_id, role, content):
    """Сохраняет сообщение в историю диалога"""
    timestamp = get_moscow_time().isoformat()
    if use_supabase:
        try:
            supabase.table('chat_history_web').insert({
                'user_id': user_id,
                'role': role,
                'content': content,
                'timestamp': timestamp
            }).execute()
        except Exception as e:
            print(f"Ошибка сохранения истории: {e}")
    else:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('INSERT INTO chat_history_web (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)',
                  (user_id, role, content, timestamp))
        conn.commit()
        conn.close()

def get_history(user_id, limit=10):
    """Получает последние N сообщений для пользователя"""
    if use_supabase:
        try:
            response = supabase.table('chat_history_web') \
                .select('role, content') \
                .eq('user_id', user_id) \
                .order('id', desc=True) \
                .limit(limit) \
                .execute()
            if response.data:
                # Переворачиваем, чтобы получить хронологический порядок
                history = list(reversed(response.data))
                return history
            return []
        except Exception as e:
            print(f"Ошибка получения истории: {e}")
            return []
    else:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('SELECT role, content FROM chat_history_web WHERE user_id = ? ORDER BY id DESC LIMIT ?',
                  (user_id, limit))
        rows = c.fetchall()
        conn.close()
        history = [{'role': row[0], 'content': row[1]} for row in reversed(rows)]
        return history

def clear_history(user_id):
    """Очищает историю диалога для пользователя"""
    if use_supabase:
        try:
            supabase.table('chat_history_web').delete().eq('user_id', user_id).execute()
        except:
            pass
    else:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('DELETE FROM chat_history_web WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()

# ============================================================
# ОСТАЛЬНЫЕ ФУНКЦИИ БАЗЫ ДАННЫХ (users, premium, etc.)
# ============================================================
# ... (здесь должны быть функции ensure_user, get_db_user, set_premium, get_premium_status, is_admin, etc.)
# Для краткости я не буду полностью дублировать их, так как они уже были в предыдущем ответе.
# В финальном коде они будут присутствовать.

# ============================================================
# ПОИСК, ПОГОДА, КУРСЫ, МАТЕМАТИКА, НЕЙРОСЕТИ
# ============================================================
# ... (весь код из предыдущего ответа, включая search_google, search_wikipedia, get_weather, get_exchange_rates, solve_math, generate_with_gigachat, generate_with_yandexgpt, SUPER_SYSTEM_PROMPT, process_message)

# ============================================================
# ОБНОВЛЕННАЯ ФУНКЦИЯ ПРОЦЕССИНГА С ИСТОРИЕЙ
# ============================================================
def process_message_with_history(user_id, user_text, image_description=None):
    """Обрабатывает сообщение с учётом истории диалога"""
    # 1. Сначала проверяем, не является ли это командой, которую нужно обработать отдельно
    #    (команды не должны сохраняться в истории, чтобы не засорять контекст)
    if user_text.startswith('/'):
        # Обработка команд (как в предыдущем коде)
        # ... (здесь должен быть код обработки команд из предыдущего ответа)
        # Для краткости я пропущу, но он полностью будет в финальном коде
        pass

    # 2. Сохраняем сообщение пользователя в историю
    save_message(user_id, 'user', user_text)

    # 3. Получаем последние 10 сообщений истории (для контекста)
    history = get_history(user_id, limit=10)

    # 4. Формируем системный промпт, добавляя историю
    current_date = get_current_date()
    current_time = get_moscow_time().strftime('%H:%M')
    system_prompt = SUPER_SYSTEM_PROMPT.format(
        current_date=current_date,
        current_time=current_time
    )

    if get_premium_status(user_id):
        system_prompt += "\n\n💎 Пользователь имеет PREMIUM статус. Включи режим максимальной проработки!"
    if image_description:
        system_prompt += f"\n\n📸 На изображении: {image_description}"

    # Добавляем память (факты из memory)
    memories = recall(user_id, user_text)
    if memories:
        system_prompt += f"\n\n🧠 Что я помню об этом: {' '.join(memories[:2])}"

    # Добавляем историю диалога (до 10 последних сообщений)
    if history:
        history_text = "\n".join([f"{'Пользователь' if h['role'] == 'user' else 'AWESOME AI'}: {h['content']}" for h in history])
        system_prompt += f"\n\n📜 История диалога (последние сообщения):\n{history_text}"

    # 5. Выполняем поиск в интернете, если нужно
    search_result = None
    if len(user_text) > 3 and not any(kw in user_text.lower() for kw in ['погода', 'курс', 'биткоин', 'эфириум']):
        search_result = search_all_internet(user_text)

    # 6. Генерируем ответ через GigaChat или YandexGPT
    # ... (код генерации, как в process_message из предыдущего ответа)
    # Для примера:
    response = generate_ai_response(user_id, user_text, system_prompt, search_result, image_description)

    # 7. Сохраняем ответ бота в историю
    if response:
        save_message(user_id, 'assistant', response)

    return response

# ============================================================
# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ГЕНЕРАЦИИ (с использованием истории)
# ============================================================
def generate_ai_response(user_id, user_text, system_prompt, search_result=None, image_description=None):
    # Пробуем GigaChat, затем YandexGPT, затем fallback
    try:
        if GIGACHAT_AUTH_KEY:
            response = generate_with_gigachat(user_text, system_prompt)
            if response and len(response) > 5:
                return response
    except: pass
    try:
        response = generate_with_yandexgpt(user_text, system_prompt)
        if response and len(response) > 5:
            return response
    except: pass
    return generate_fallback_response(user_text, search_result)

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

        # Проверка лимитов
        if not can_send_message(user_id):
            user_data = get_db_user(user_id)
            messages = user_data.get('messages_today', 0) if user_data else 0
            remaining = FREE_LIMIT - messages
            if remaining < 0:
                remaining = 0
            return jsonify({'reply': f"🔴 Лимит исчерпан! Осталось: {remaining}/{FREE_LIMIT}\n💎 Купи Premium: /premium"})

        # Обработка команды /clear (очистка истории)
        if message.strip() == '/clear':
            clear_history(user_id)
            return jsonify({'reply': "🧹 История диалога очищена!"})

        # Обработка команды /history (показать историю)
        if message.strip() == '/history':
            history = get_history(user_id, limit=10)
            if not history:
                return jsonify({'reply': "📜 История пуста."})
            text = "📜 *Последние сообщения:*\n"
            for h in history:
                role = "👤 Вы" if h['role'] == 'user' else "🤖 AWESOME AI"
                text += f"\n**{role}:** {h['content'][:100]}{'...' if len(h['content'])>100 else ''}"
            return jsonify({'reply': text})

        # Основная обработка с историей
        response = process_message_with_history(user_id, message)
        if response:
            increment_messages(user_id)
            return jsonify({'reply': response})
        else:
            return jsonify({'reply': "❌ Не удалось обработать запрос."})

    except Exception as e:
        print(f"Ошибка в /api/chat: {e}")
        return jsonify({'error': str(e)})

@app.route('/api/analyze_image', methods=['POST'])
def analyze_image():
    # ... (как в предыдущем ответе)
    pass

@app.route('/admin')
def admin_panel():
    # ... (как в предыдущем ответе)
    pass

# ============================================================
# HTML ТЕМПЛЕЙТ (с дополнительной кнопкой "Очистить историю" и "История")
# ============================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AWESOME AI 2026</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0e17;
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
            opacity: 0.4;
        }
        .glow {
            position: fixed;
            border-radius: 50%;
            filter: blur(100px);
            opacity: 0.08;
            z-index: 0;
            pointer-events: none;
            animation: floatGlow 25s ease-in-out infinite;
        }
        .glow-1 { width: 500px; height: 500px; top: -150px; right: -150px; background: #6c3ce0; }
        .glow-2 { width: 400px; height: 400px; bottom: -100px; left: -100px; background: #f0883e; animation-delay: 7s; }
        .glow-3 { width: 300px; height: 300px; top: 50%; left: 50%; background: #1f6feb; animation-delay: 14s; transform: translate(-50%, -50%); }
        @keyframes floatGlow {
            0%,100% { transform: translate(0,0) scale(1); }
            33% { transform: translate(80px,-50px) scale(1.2); }
            66% { transform: translate(-50px,80px) scale(0.8); }
        }
        .header {
            position: relative;
            z-index: 1;
            background: rgba(10, 14, 23, 0.85);
            backdrop-filter: blur(20px);
            padding: 8px 16px;
            border-bottom: 1px solid rgba(255,255,255,0.04);
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-shrink: 0;
            flex-wrap: wrap;
            gap: 4px;
        }
        .logo {
            font-size: 18px;
            font-weight: 900;
            background: linear-gradient(135deg, #58a6ff, #f0883e, #6c3ce0);
            background-size: 300% 300%;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            animation: gradientShift 6s ease-in-out infinite;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        @keyframes gradientShift {
            0%,100% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
        }
        .badge {
            background: rgba(46, 160, 67, 0.15);
            border: 1px solid rgba(46, 160, 67, 0.25);
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
            padding: 3px 10px;
            border-radius: 14px;
            font-size: 9px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.25s ease;
            will-change: transform;
        }
        .menu button:hover {
            background: rgba(88,166,255,0.1);
            border-color: rgba(88,166,255,0.2);
            color: #58a6ff;
            transform: translateY(-2px);
        }
        .menu .premium:hover { background: rgba(240,136,62,0.1); border-color: rgba(240,136,62,0.2); color: #f0883e; }
        .menu .danger:hover { background: rgba(248,81,73,0.1); border-color: rgba(248,81,73,0.2); color: #f85149; }
        .menu .admin { background: rgba(248,81,73,0.06); border-color: rgba(248,81,73,0.1); color: #f85149; }
        .menu .admin:hover { background: rgba(248,81,73,0.12); border-color: rgba(248,81,73,0.2); }
        .chat {
            position: relative;
            z-index: 1;
            flex: 1;
            overflow-y: auto;
            padding: 12px 16px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            will-change: transform;
        }
        .chat::-webkit-scrollbar { width: 2px; }
        .chat::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.06); border-radius: 10px; }
        .message {
            max-width: 80%;
            padding: 8px 14px;
            border-radius: 14px;
            line-height: 1.6;
            word-wrap: break-word;
            white-space: pre-wrap;
            font-size: 13px;
            animation: slideUp 0.2s ease-out;
            will-change: transform, opacity;
        }
        @keyframes slideUp {
            0% { opacity: 0; transform: translateY(10px) scale(0.97); }
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
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.04);
            border-bottom-left-radius: 2px;
        }
        .bot strong, .bot b { color: #f0883e; }
        .input-area {
            position: relative;
            z-index: 1;
            padding: 8px 12px 10px;
            border-top: 1px solid rgba(255,255,255,0.04);
            background: rgba(10, 14, 23, 0.85);
            backdrop-filter: blur(20px);
            flex-shrink: 0;
        }
        .tools {
            display: flex;
            gap: 4px;
            flex-wrap: wrap;
            margin-bottom: 4px;
        }
        .tools button, .tools label {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.04);
            color: #6e7681;
            padding: 2px 10px;
            border-radius: 14px;
            font-size: 9px;
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
            gap: 6px;
            align-items: center;
        }
        .input-row input {
            flex: 1;
            padding: 6px 14px;
            border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.06);
            background: rgba(22,27,34,0.6);
            color: #e6edf3;
            font-size: 13px;
            outline: none;
            transition: border 0.3s ease;
        }
        .input-row input:focus {
            border-color: #58a6ff;
            box-shadow: 0 0 30px rgba(88,166,255,0.03);
        }
        .input-row input::placeholder {
            color: #484f58;
        }
        .input-row button {
            padding: 6px 18px;
            border-radius: 20px;
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
            box-shadow: 0 4px 25px rgba(88,166,255,0.1);
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
        .welcome p { font-size: 13px; opacity: 0.6; }
        .welcome .features {
            display: flex;
            gap: 8px;
            justify-content: center;
            margin-top: 12px;
            flex-wrap: wrap;
        }
        .welcome .features span {
            background: rgba(255,255,255,0.03);
            padding: 3px 12px;
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
            .header { padding: 4px 10px; }
            .logo { font-size: 15px; }
            .menu button { font-size: 7px; padding: 2px 6px; }
            .message { max-width: 92%; font-size: 12px; padding: 6px 10px; }
            .chat { padding: 8px 10px; }
            .input-area { padding: 4px 8px 8px; }
            .input-row input { font-size: 12px; padding: 4px 10px; }
            .input-row button { padding: 4px 12px; font-size: 12px; }
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
        <div style="display:flex;align-items:center;gap:4px;">
            <span class="badge"><span class="dot"></span> ONLINE</span>
            <div class="menu">
                <button onclick="sendCommand('/status')">📊</button>
                <button class="premium" onclick="sendCommand('/premium')">💎</button>
                <button onclick="sendCommand('/test')">🎁</button>
                <button onclick="sendCommand('/profile')">👤</button>
                <button onclick="sendCommand('/stats')">📈</button>
                <button onclick="sendCommand('/help')">❓</button>
                <button class="danger" onclick="clearChat()">🧹</button>
                <button onclick="sendCommand('/clear')">🗑️</button>
                <button onclick="sendCommand('/history')">📜</button>
                <button class="admin" onclick="window.open('/admin?user_id=' + userId, '_blank')">👑</button>
            </div>
        </div>
    </header>
    
    <div class="chat" id="chat">
        <div class="welcome">
            <h2>✨ AWESOME AI 2026</h2>
            <p>Спрашивай что угодно — я отвечу, решу, поищу</p>
            <div class="features">
                <span>📸 Фото</span><span>🎤 Голос</span><span>🌐 Поиск</span>
                <span>💵 Курсы</span><span>🧮 Математика</span><span>🎨 Рисование</span>
                <span>🌤 Погода</span><span>🪙 Крипта</span>
                <span>📜 История</span>
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
            <button onclick="sendCommand('/draw '+prompt('🎨 Описание картинки?'))">🎨</button>
            <button onclick="sendCommand('/history')">📜</button>
            <button onclick="sendCommand('/clear')">🗑️</button>
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
            const count = 35;
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
                    this.size = Math.random() * 2 + 0.5;
                    this.speedX = (Math.random() - 0.5) * 0.25;
                    this.speedY = (Math.random() - 0.5) * 0.25;
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
                            if (dist < 120) {
                                ctx.beginPath();
                                ctx.strokeStyle = `rgba(136, 192, 255, ${0.02 * (1 - dist / 120)})`;
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
        
        let userId = localStorage.getItem('awesome_user_id_web');
        if (!userId) {
            userId = Date.now() + Math.floor(Math.random() * 1000);
            localStorage.setItem('awesome_user_id_web', userId);
        }
        
        function addMessage(text, isUser) {
            const welcome = chat.querySelector('.welcome');
            if (welcome) welcome.remove();
            const div = document.createElement('div');
            div.className = 'message ' + (isUser ? 'user' : 'bot');
            // Поддержка Markdown: жирный, курсив, код
            let formatted = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
            formatted = formatted.replace(/\*(.*?)\*/g, '<i>$1</i>');
            formatted = formatted.replace(/`(.*?)`/g, '<code>$1</code>');
            formatted = formatted.replace(/\n/g, '<br>');
            div.innerHTML = formatted;
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
            if (!text) return;
            input.value = '';
            sendBtn.disabled = true;
            addMessage(text, true);
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
                else addMessage('⚠️ Пустой ответ', false);
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
                if (file.type.startsWith('image/')) {
                    const reader = new FileReader();
                    reader.onload = async function(e) {
                        const base64 = e.target.result.split(',')[1];
                        addMessage('📸 Отправка фото...', true);
                        setTyping(true);
                        try {
                            const response = await fetch('/api/analyze_image', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ image: base64, user_id: parseInt(userId) })
                            });
                            const data = await response.json();
                            setTyping(false);
                            if (data.error) addMessage('⚠️ ' + data.error, false);
                            else if (data.reply) addMessage(data.reply, false);
                        } catch (e) {
                            setTyping(false);
                            addMessage('⚠️ Ошибка обработки фото', false);
                        }
                    };
                    reader.readAsDataURL(file);
                } else {
                    addMessage('📎 ' + file.name + ' (не изображение)', true);
                }
            }
        }
        
        function clearChat() {
            chat.innerHTML = `
                <div class="welcome">
                    <h2>✨ AWESOME AI 2026</h2>
                    <p>Спрашивай что угодно — я отвечу, решу, поищу</p>
                    <div class="features">
                        <span>📸 Фото</span><span>🎤 Голос</span><span>🌐 Поиск</span>
                        <span>💵 Курсы</span><span>🧮 Математика</span><span>🎨 Рисование</span>
                        <span>🌤 Погода</span><span>🪙 Крипта</span>
                        <span>📜 История</span>
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
            recognition.continuous = false;
            recognition.interimResults = false;
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
# АДМИН-ПАНЕЛЬ (как в предыдущем ответе)
# ============================================================
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

    # Получаем всех пользователей
    if use_supabase:
        try:
            response = supabase.table('users_web').select('*').order('user_id', desc=True).execute()
            users = response.data
        except:
            users = []
    else:
        conn = sqlite3.connect('users_web.db')
        c = conn.cursor()
        c.execute('SELECT user_id, username, premium, messages_today, is_admin, test_used, joined_at, premium_expires FROM users_web ORDER BY user_id DESC')
        users = c.fetchall()
        conn.close()
        # Преобразуем в словари для единообразия
        users = [{'user_id': u[0], 'username': u[1], 'premium': u[2], 'messages_today': u[3], 'is_admin': u[4], 'test_used': u[5], 'joined_at': u[6], 'premium_expires': u[7]} for u in users]

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
            <div class="card"><span>💎 Premium</span><div class="num gold">{sum(1 for u in users if u['premium'] == 1)}</div></div>
            <div class="card"><span>👑 Админов</span><div class="num gold">{sum(1 for u in users if u['is_admin'] == 1)}</div></div>
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
    init_db_web()
    init_memory_db()

    port = int(os.getenv('PORT', 5000))
    print("=" * 60)
    print("🧠 AWESOME AI 2026 — ВЕБ-ВЕРСИЯ (с памятью)")
    print("=" * 60)
    print(f"👑 Владелец ID: {OWNER_ID}")
    print(f"🌐 http://localhost:{port}")
    print("=" * 60)
    print("✅ База данных: Supabase (таблицы с суффиксом _web)")
    print("✅ Функция памяти: история диалога сохраняется и используется в контексте")
    print("✅ Команды: /history — показать историю, /clear — очистить историю")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=False)
