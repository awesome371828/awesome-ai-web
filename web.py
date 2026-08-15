#!/usr/bin/env python3
import os
import json
import requests
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from dotenv import load_dotenv
import sqlite3

load_dotenv()

app = Flask(__name__)
CORS(app)

# ============================================================
# НАСТРОЙКА
# ============================================================
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY") or "AQVNyfn82epL9dy8C_kftzeypq6eF9lFd6SZnFzV"
FOLDER_ID = os.getenv("FOLDER_ID", "b1g4aq87c7j61c6g3i5l")
OWNER_ID = 6652898792

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

# ============================================================
# HTML — МЕГА-КРАСИВЫЙ С АНИМАЦИЯМИ (РАБОЧАЯ ВЕРСИЯ!)
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
        
        /* ===== ФОН С ЧАСТИЦАМИ ===== */
        #particles {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: 0;
            pointer-events: none;
        }
        
        /* ===== НЕОНОВОЕ СВЕЧЕНИЕ ===== */
        .glow {
            position: fixed;
            border-radius: 50%;
            filter: blur(120px);
            opacity: 0.15;
            z-index: 0;
            pointer-events: none;
            animation: floatGlow 20s ease-in-out infinite;
        }
        .glow-1 { width: 500px; height: 500px; top: -150px; right: -150px; background: #6c3ce0; }
        .glow-2 { width: 400px; height: 400px; bottom: -100px; left: -100px; background: #f0883e; animation-delay: 5s; }
        .glow-3 { width: 300px; height: 300px; top: 50%; left: 50%; background: #1f6feb; animation-delay: 10s; transform: translate(-50%, -50%); }
        @keyframes floatGlow {
            0%,100% { transform: translate(0,0) scale(1); }
            25% { transform: translate(80px,-50px) scale(1.2); }
            50% { transform: translate(-50px,80px) scale(0.8); }
            75% { transform: translate(40px,40px) scale(1.1); }
        }
        
        /* ===== ШАПКА ===== */
        .header {
            position: relative;
            z-index: 1;
            background: rgba(8,12,22,0.85);
            backdrop-filter: blur(24px);
            padding: 14px 24px;
            border-bottom: 1px solid rgba(255,255,255,0.04);
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-shrink: 0;
            flex-wrap: wrap;
            gap: 10px;
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
            0%,100% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
        }
        .badge {
            background: linear-gradient(135deg, #238636, #2ea043);
            color: #fff;
            font-size: 9px;
            font-weight: 600;
            padding: 3px 12px;
            border-radius: 20px;
            display: flex;
            align-items: center;
            gap: 5px;
            -webkit-text-fill-color: white;
        }
        .badge .dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: #2ea043;
            animation: pulse 1.5s infinite;
        }
        @keyframes pulse {
            0%,100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.4; transform: scale(0.7); }
        }
        
        .menu {
            display: flex;
            gap: 5px;
            flex-wrap: wrap;
        }
        .menu button {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.06);
            color: #8b949e;
            padding: 4px 14px;
            border-radius: 18px;
            font-size: 11px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.25s ease;
        }
        .menu button:hover {
            background: rgba(88,166,255,0.12);
            border-color: rgba(88,166,255,0.2);
            color: #58a6ff;
            transform: translateY(-2px);
            box-shadow: 0 4px 20px rgba(88,166,255,0.08);
        }
        .menu .premium:hover {
            background: rgba(240,136,62,0.12);
            border-color: rgba(240,136,62,0.2);
            color: #f0883e;
        }
        .menu .danger:hover {
            background: rgba(248,81,73,0.12);
            border-color: rgba(248,81,73,0.2);
            color: #f85149;
        }
        .menu .admin {
            background: rgba(248,81,73,0.08);
            border-color: rgba(248,81,73,0.15);
            color: #f85149;
        }
        .menu .admin:hover {
            background: rgba(248,81,73,0.15);
            border-color: rgba(248,81,73,0.3);
        }
        
        /* ===== ЧАТ ===== */
        .chat {
            position: relative;
            z-index: 1;
            flex: 1;
            overflow-y: auto;
            padding: 18px 24px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        .chat::-webkit-scrollbar {
            width: 3px;
        }
        .chat::-webkit-scrollbar-thumb {
            background: rgba(255,255,255,0.08);
            border-radius: 10px;
        }
        
        /* ===== СООБЩЕНИЯ ===== */
        .message {
            max-width: 82%;
            padding: 10px 18px;
            border-radius: 16px;
            line-height: 1.6;
            word-wrap: break-word;
            white-space: pre-wrap;
            font-size: 14px;
            animation: slideUp 0.3s ease-out;
            position: relative;
        }
        @keyframes slideUp {
            0% { opacity: 0; transform: translateY(12px) scale(0.97); }
            100% { opacity: 1; transform: translateY(0) scale(1); }
        }
        .user {
            align-self: flex-end;
            background: linear-gradient(135deg, #1f6feb, #6c3ce0);
            color: #fff;
            border-bottom-right-radius: 3px;
        }
        .bot {
            align-self: flex-start;
            background: rgba(22,27,34,0.9);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255,255,255,0.04);
            border-bottom-left-radius: 3px;
        }
        .bot strong, .bot b {
            color: #f0883e;
        }
        
        /* ===== ВВОД ===== */
        .input-area {
            position: relative;
            z-index: 1;
            padding: 12px 20px 16px;
            border-top: 1px solid rgba(255,255,255,0.04);
            background: rgba(8,12,22,0.9);
            backdrop-filter: blur(20px);
            flex-shrink: 0;
        }
        .tools {
            display: flex;
            gap: 5px;
            flex-wrap: wrap;
            margin-bottom: 8px;
        }
        .tools button, .tools label {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.04);
            color: #6e7681;
            padding: 3px 14px;
            border-radius: 16px;
            font-size: 11px;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        .tools button:hover, .tools label:hover {
            background: rgba(255,255,255,0.06);
            border-color: rgba(255,255,255,0.08);
            color: #e6edf3;
        }
        .tools input[type="file"] {
            display: none;
        }
        
        .input-row {
            display: flex;
            gap: 10px;
            align-items: center;
        }
        .input-row input {
            flex: 1;
            padding: 10px 18px;
            border-radius: 24px;
            border: 1px solid rgba(255,255,255,0.06);
            background: rgba(22,27,34,0.8);
            color: #e6edf3;
            font-size: 14px;
            outline: none;
            transition: all 0.3s ease;
        }
        .input-row input:focus {
            border-color: #58a6ff;
            box-shadow: 0 0 30px rgba(88,166,255,0.05);
        }
        .input-row input::placeholder {
            color: #484f58;
        }
        .input-row button {
            padding: 10px 28px;
            border-radius: 24px;
            border: none;
            background: linear-gradient(135deg, #1f6feb, #6c3ce0);
            color: #fff;
            font-weight: 600;
            font-size: 14px;
            cursor: pointer;
            transition: all 0.25s ease;
            white-space: nowrap;
        }
        .input-row button:hover {
            transform: scale(1.03);
            box-shadow: 0 4px 30px rgba(88,166,255,0.2);
        }
        .input-row button:disabled {
            opacity: 0.4;
            cursor: not-allowed;
            transform: none;
        }
        
        .typing {
            color: #8b949e;
            font-size: 13px;
            padding: 4px 18px;
            align-self: flex-start;
            animation: pulse 1.2s infinite;
        }
        
        .welcome {
            text-align: center;
            padding: 35px 20px;
            color: #8b949e;
        }
        .welcome h2 {
            color: #e6edf3;
            margin-bottom: 4px;
            font-size: 24px;
            font-weight: 800;
            background: linear-gradient(135deg, #58a6ff, #f0883e);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .welcome p {
            font-size: 14px;
            opacity: 0.6;
        }
        .welcome .features {
            display: flex;
            gap: 14px;
            justify-content: center;
            margin-top: 14px;
            flex-wrap: wrap;
        }
        .welcome .features span {
            background: rgba(255,255,255,0.03);
            padding: 5px 16px;
            border-radius: 18px;
            font-size: 11px;
            border: 1px solid rgba(255,255,255,0.04);
            color: #6e7681;
            transition: all 0.3s ease;
        }
        .welcome .features span:hover {
            background: rgba(255,255,255,0.06);
            color: #e6edf3;
            transform: translateY(-2px);
        }
        
        @media (max-width: 640px) {
            .header { padding: 8px 14px; }
            .logo { font-size: 17px; }
            .menu button { font-size: 9px; padding: 2px 10px; }
            .message { max-width: 92%; font-size: 13px; padding: 8px 14px; }
            .chat { padding: 12px 14px; }
            .input-area { padding: 8px 14px 12px; }
            .input-row input { font-size: 13px; padding: 8px 14px; }
            .input-row button { padding: 8px 18px; font-size: 13px; }
            .tools button, .tools label { font-size: 9px; padding: 2px 10px; }
            .welcome h2 { font-size: 19px; }
            .welcome .features span { font-size: 10px; padding: 3px 12px; }
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
        <div style="display:flex;align-items:center;gap:8px;">
            <span class="badge"><span class="dot"></span> ONLINE</span>
            <div class="menu">
                <button onclick="sendCommand('/status')">📊</button>
                <button class="premium" onclick="sendCommand('/premium')">💎</button>
                <button onclick="sendCommand('/test')">🎁</button>
                <button onclick="sendCommand('/profile')">👤</button>
                <button onclick="sendCommand('/help')">❓</button>
                <button class="danger" onclick="clearChat()">🧹</button>
                <button class="admin" onclick="window.open('/admin?user_id='+userId,'_blank')">👑</button>
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
        // ===== ЧАСТИЦЫ =====
        (function() {
            const canvas = document.getElementById('particles');
            const ctx = canvas.getContext('2d');
            let particles = [];
            const count = 65;
            
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
                    this.size = Math.random() * 2.5 + 0.5;
                    this.speedX = (Math.random() - 0.5) * 0.4;
                    this.speedY = (Math.random() - 0.5) * 0.4;
                    this.opacity = Math.random() * 0.3 + 0.1;
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
            
            function animate() {
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                particles.forEach(p => { p.update(); p.draw(); });
                
                // Линии между частицами
                for (let i = 0; i < particles.length; i++) {
                    for (let j = i + 1; j < particles.length; j++) {
                        const dx = particles[i].x - particles[j].x;
                        const dy = particles[i].y - particles[j].y;
                        const dist = Math.sqrt(dx * dx + dy * dy);
                        if (dist < 120) {
                            ctx.beginPath();
                            ctx.strokeStyle = `rgba(136, 192, 255, ${0.04 * (1 - dist / 120)})`;
                            ctx.lineWidth = 0.5;
                            ctx.moveTo(particles[i].x, particles[i].y);
                            ctx.lineTo(particles[j].x, particles[j].y);
                            ctx.stroke();
                        }
                    }
                }
                requestAnimationFrame(animate);
            }
            animate();
        })();
        
        // ===== ЛОГИКА ЧАТА =====
        const chat = document.getElementById('chat');
        const input = document.getElementById('input');
        const sendBtn = document.getElementById('sendBtn');
        let filesToSend = [];
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
                if (data.error) {
                    addMessage('⚠️ ' + data.error, false);
                } else if (data.reply) {
                    addMessage(data.reply, false);
                }
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
                const reader = new FileReader();
                reader.onload = function(e) {
                    if (file.type.startsWith('image/')) {
                        addMessage('📎 ' + file.name, true);
                    } else {
                        addMessage('📎 ' + file.name, true);
                    }
                };
                reader.readAsDataURL(file);
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
        return jsonify({'reply': f"🤖 AWESOME AI:\n\nТы написал: {message}\n\nЯ работаю! Напиши что-нибудь ещё."})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/admin')
def admin_panel():
    user_id = request.args.get('user_id', type=int)
    if not user_id or user_id != OWNER_ID:
        return "<h1 style='color:#f85149;'>🚫 ДОСТУП ЗАПРЕЩЁН</h1><p>Только владелец</p>", 403
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT * FROM users ORDER BY user_id DESC')
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
        h1{{color:#58a6ff;font-size:24px;}}
        .sub{{color:#8b949e;margin-bottom:20px;}}
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
        <p class="sub">👤 Владелец: @flidges | <a href="/" class="back">← На главную</a></p>
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
    print("🧠 AWESOME AI — МЕГА-КРАСИВАЯ ВЕРСИЯ")
    print("=" * 60)
    print(f"🌐 http://localhost:{port}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=False)
