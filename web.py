#!/usr/bin/env python3
import os
import re
import json
import requests
import random
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from dotenv import load_dotenv
from bs4 import BeautifulSoup

load_dotenv()

app = Flask(__name__)
CORS(app)

# === НАСТРОЙКА ===
OWNER_ID = 6652898792

# === БАЗА ДАННЫХ ===
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

# === HTML ===
HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AWESOME AI</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: sans-serif; background: #0a0e17; color: #e6edf3; height: 100vh; display: flex; flex-direction: column; }
        .header { background: #161b22; padding: 12px 20px; border-bottom: 1px solid #30363d; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
        .logo { font-size: 20px; font-weight: bold; background: linear-gradient(135deg, #58a6ff, #f0883e); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .menu { display: flex; gap: 5px; flex-wrap: wrap; }
        .menu button { background: #21262d; border: 1px solid #30363d; color: #c9d1d9; padding: 4px 12px; border-radius: 16px; font-size: 12px; cursor: pointer; }
        .menu button:hover { background: #30363d; border-color: #58a6ff; color: #58a6ff; }
        .chat { flex: 1; overflow-y: auto; padding: 16px 20px; display: flex; flex-direction: column; gap: 10px; }
        .message { max-width: 80%; padding: 10px 16px; border-radius: 12px; line-height: 1.5; word-wrap: break-word; white-space: pre-wrap; }
        .user { align-self: flex-end; background: #1f6feb; color: #fff; }
        .bot { align-self: flex-start; background: #21262d; border: 1px solid #30363d; }
        .input-area { padding: 12px 20px; border-top: 1px solid #30363d; display: flex; gap: 10px; background: #0a0e17; }
        .input-area input { flex: 1; padding: 10px 16px; border-radius: 24px; border: 1px solid #30363d; background: #161b22; color: #fff; font-size: 14px; outline: none; }
        .input-area input:focus { border-color: #58a6ff; }
        .input-area button { padding: 10px 24px; border-radius: 24px; border: none; background: #1f6feb; color: #fff; font-weight: 600; font-size: 14px; cursor: pointer; }
        .input-area button:hover { background: #388bfd; }
        .input-area button:disabled { opacity: 0.5; cursor: not-allowed; }
        .welcome { text-align: center; padding: 30px 20px; color: #8b949e; }
        .welcome h2 { color: #e6edf3; margin-bottom: 6px; }
        .typing { color: #8b949e; padding: 4px 16px; align-self: flex-start; }
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
    </div>
</div>
<div class="chat" id="chat">
    <div class="welcome">
        <h2>✨ AWESOME AI</h2>
        <p>Спрашивай что угодно — я отвечу, решу, поищу</p>
    </div>
</div>
<div class="input-area">
    <input id="input" placeholder="Напиши..." onkeydown="if(event.key==='Enter') send()" autofocus>
    <button id="sendBtn" onclick="send()">➤</button>
</div>

<script>
const chat = document.getElementById('chat');
const input = document.getElementById('input');
const sendBtn = document.getElementById('sendBtn');
let userId = Date.now();

function addMessage(text, isUser) {
    const welcome = chat.querySelector('.welcome');
    if (welcome) welcome.remove();
    const div = document.createElement('div');
    div.className = 'message ' + (isUser ? 'user' : 'bot');
    div.textContent = text;
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
    setTyping(true);
    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, user_id: userId })
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

function clearChat() {
    chat.innerHTML = '<div class="welcome"><h2>✨ AWESOME AI</h2><p>Спрашивай что угодно — я отвечу, решу, поищу</p></div>';
}

document.addEventListener('DOMContentLoaded', () => input.focus());
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        message = data.get('message', '')
        user_id = data.get('user_id', 1)
        if not message:
            return jsonify({'error': 'Напиши что-нибудь!'})
        ensure_user(user_id, f"user_{user_id}")
        return jsonify({'reply': f"🤖 AWESOME AI:\n\n{message}"})
    except Exception as e:
        return jsonify({'error': str(e)})

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
