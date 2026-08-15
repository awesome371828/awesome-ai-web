#!/usr/bin/env python3
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import os
import json
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

# База данных
DB_PATH = 'users.db'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
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

OWNER_ID = 6652898792

def ensure_user(user_id, username):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    if not c.fetchone():
        is_owner = 1 if user_id == OWNER_ID else 0
        c.execute('INSERT INTO users (user_id, username, messages_today, last_reset, is_admin, test_used, joined_at, is_owner) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                  (user_id, username, 0, datetime.now().strftime('%Y-%m-%d'), is_owner, 0, datetime.now().strftime('%d.%m.%Y %H:%M'), is_owner))
        c.execute('INSERT OR IGNORE INTO total_stats (user_id, total_messages) VALUES (?, 0)', (user_id,))
        conn.commit()
    conn.close()

# HTML
HTML = """
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>AWESOME AI</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;}body{font-family:sans-serif;background:#0a0e17;color:#fff;height:100vh;display:flex;flex-direction:column;}
.header{background:#161b22;padding:12px 20px;border-bottom:1px solid #30363d;display:flex;justify-content:space-between;align-items:center;}
.logo{font-size:20px;font-weight:bold;background:linear-gradient(135deg,#58a6ff,#f0883e);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.menu-buttons{display:flex;gap:6px;flex-wrap:wrap;}
.menu-buttons button{background:#21262d;border:1px solid #30363d;color:#c9d1d9;padding:4px 12px;border-radius:16px;font-size:12px;cursor:pointer;}
.menu-buttons button:hover{background:#30363d;border-color:#58a6ff;}
.chat{flex:1;overflow-y:auto;padding:16px 20px;display:flex;flex-direction:column;gap:10px;}
.message{max-width:80%;padding:10px 16px;border-radius:12px;line-height:1.5;word-wrap:break-word;white-space:pre-wrap;}
.user{align-self:flex-end;background:#1f6feb;color:#fff;}
.bot{align-self:flex-start;background:#21262d;border:1px solid #30363d;}
.input-area{padding:12px 20px;border-top:1px solid #30363d;display:flex;gap:10px;background:#0a0e17;}
.input-area input{flex:1;padding:10px 16px;border-radius:24px;border:1px solid #30363d;background:#161b22;color:#fff;font-size:14px;outline:none;}
.input-area input:focus{border-color:#58a6ff;}
.input-area button{padding:10px 24px;border-radius:24px;border:none;background:#1f6feb;color:#fff;font-weight:600;font-size:14px;cursor:pointer;}
.input-area button:hover{background:#388bfd;}
.input-area button:disabled{opacity:0.5;cursor:not-allowed;}
.welcome{text-align:center;padding:30px 20px;color:#8b949e;}
.welcome h2{color:#e6edf3;margin-bottom:6px;}
.features{display:flex;gap:12px;justify-content:center;margin-top:12px;flex-wrap:wrap;}
.features span{background:#21262d;padding:4px 14px;border-radius:16px;font-size:12px;border:1px solid #30363d;color:#8b949e;}
.typing{color:#8b949e;font-size:14px;padding:4px 16px;align-self:flex-start;}
.admin-btn{background:#da3633;color:#fff;border-color:#da3633;}
.admin-btn:hover{background:#f85149;border-color:#f85149;}
</style>
</head>
<body>
<div class="header"><span class="logo">🧠 AWESOME AI</span><div class="menu-buttons"><button onclick="sendCommand('/status')">📊</button><button onclick="sendCommand('/premium')">💎</button><button onclick="sendCommand('/test')">🎁</button><button onclick="sendCommand('/profile')">👤</button><button onclick="sendCommand('/help')">❓</button><button onclick="clearChat()">🧹</button><button class="admin-btn" onclick="window.open('/admin?user_id='+userId,'_blank')">👑</button></div></div>
<div class="chat" id="chat"><div class="welcome"><h2>✨ AWESOME AI</h2><p>Спрашивай что угодно — я отвечу, решу, поищу</p><div class="features"><span>📸 Фото</span><span>🌐 Поиск</span><span>💵 Курсы</span><span>🧮 Математика</span></div></div></div>
<div class="input-area"><input id="input" placeholder="Напиши..." onkeydown="if(event.key==='Enter')send()" autofocus><button id="sendBtn" onclick="send()">➤</button></div>
<script>
const chat=document.getElementById('chat');const input=document.getElementById('input');const sendBtn=document.getElementById('sendBtn');let userId=Date.now();
function addMessage(text,isUser){const welcome=chat.querySelector('.welcome');if(welcome)welcome.remove();const div=document.createElement('div');div.className='message '+(isUser?'user':'bot');div.textContent=text;chat.appendChild(div);chat.scrollTop=chat.scrollHeight;}
function setTyping(show){const existing=document.querySelector('.typing');if(existing)existing.remove();if(show){const div=document.createElement('div');div.className='typing';div.textContent='🧠 AWESOME AI печатает...';chat.appendChild(div);chat.scrollTop=chat.scrollHeight;}}
async function send(){const text=input.value.trim();if(!text)return;input.value='';sendBtn.disabled=true;setTyping(true);try{const response=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text,user_id:userId})});const data=await response.json();setTyping(false);if(data.error)addMessage('⚠️ '+data.error,false);else if(data.reply)addMessage(data.reply,false);}catch(e){setTyping(false);addMessage('⚠️ Ошибка соединения',false);}sendBtn.disabled=false;input.focus();}
async function sendCommand(cmd){input.value=cmd;await send();}
function clearChat(){chat.innerHTML='<div class="welcome"><h2>✨ AWESOME AI</h2><p>Спрашивай что угодно — я отвечу, решу, поищу</p><div class="features"><span>📸 Фото</span><span>🌐 Поиск</span><span>💵 Курсы</span><span>🧮 Математика</span></div></div>';}
document.addEventListener('DOMContentLoaded',()=>input.focus());
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
        return jsonify({'reply': f"Ты написал: {message}\n\n🤖 Я — AWESOME AI! Сейчас я работаю в минимальном режиме. Скоро добавлю полноценный ответ от YandexGPT!"})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/admin')
def admin_panel():
    user_id = request.args.get('user_id', type=int)
    if not user_id or user_id != OWNER_ID:
        return "<h1 style='color:#f85149;'>🚫 ДОСТУП ЗАПРЕЩЁН</h1>", 403
    conn = get_db()
    c = conn.cursor()
    action = request.args.get('action')
    target_id = request.args.get('target_id', type=int)
    if action == 'giveprem' and target_id:
        expires = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
        c.execute('UPDATE users SET premium = 1, premium_expires = ? WHERE user_id = ?', (expires, target_id))
        conn.commit()
    if action == 'delprem' and target_id:
        c.execute('UPDATE users SET premium = 0, premium_expires = NULL WHERE user_id = ?', (target_id,))
        conn.commit()
    if action == 'giveadmin' and target_id:
        c.execute('UPDATE users SET is_admin = 1 WHERE user_id = ?', (target_id,))
        conn.commit()
    if action == 'deladmin' and target_id:
        c.execute('UPDATE users SET is_admin = 0 WHERE user_id = ?', (target_id,))
        conn.commit()
    if action == 'ban' and target_id:
        c.execute('INSERT OR IGNORE INTO banned (user_id) VALUES (?)', (target_id,))
        conn.commit()
    if action == 'unban' and target_id:
        c.execute('DELETE FROM banned WHERE user_id = ?', (target_id,))
        conn.commit()
    if action == 'mute' and target_id:
        c.execute('INSERT OR IGNORE INTO muted (user_id) VALUES (?)', (target_id,))
        conn.commit()
    if action == 'unmute' and target_id:
        c.execute('DELETE FROM muted WHERE user_id = ?', (target_id,))
        conn.commit()
    
    c.execute('SELECT user_id, username, premium, premium_expires, is_admin, messages_today FROM users ORDER BY user_id DESC')
    users = c.fetchall()
    c.execute('SELECT COUNT(*) FROM users'); total = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM users WHERE premium = 1'); prem = c.fetchone()[0]
    conn.close()
    
    rows = ""
    for u in users:
        uid, username, premium, expires, is_admin_flag, msgs = u
        status = "👑 ВЛАДЕЛЕЦ" if uid == OWNER_ID else "👑 АДМИН" if is_admin_flag else "💎 PREMIUM" if premium else "🔓 Бесплатный"
        rows += f'<tr><td>{uid}</td><td>@{username}</td><td>{status}</td><td>{msgs}</td><td>{expires or "—"}</td><td><a href="?user_id={OWNER_ID}&action=giveprem&target_id={uid}" style="background:#2ea043;color:#fff;padding:2px 8px;border-radius:3px;text-decoration:none;font-size:11px;">💎+</a> <a href="?user_id={OWNER_ID}&action=delprem&target_id={uid}" style="background:#da3633;color:#fff;padding:2px 8px;border-radius:3px;text-decoration:none;font-size:11px;">💎-</a> <a href="?user_id={OWNER_ID}&action=giveadmin&target_id={uid}" style="background:#f0883e;color:#fff;padding:2px 8px;border-radius:3px;text-decoration:none;font-size:11px;">👑+</a> <a href="?user_id={OWNER_ID}&action=deladmin&target_id={uid}" style="background:#da3633;color:#fff;padding:2px 8px;border-radius:3px;text-decoration:none;font-size:11px;">👑-</a> <a href="?user_id={OWNER_ID}&action=ban&target_id={uid}" style="background:#da3633;color:#fff;padding:2px 8px;border-radius:3px;text-decoration:none;font-size:11px;">🚫</a> <a href="?user_id={OWNER_ID}&action=unban&target_id={uid}" style="background:#2ea043;color:#fff;padding:2px 8px;border-radius:3px;text-decoration:none;font-size:11px;">✅</a> <a href="?user_id={OWNER_ID}&action=mute&target_id={uid}" style="background:#f0883e;color:#fff;padding:2px 8px;border-radius:3px;text-decoration:none;font-size:11px;">🔇</a> <a href="?user_id={OWNER_ID}&action=unmute&target_id={uid}" style="background:#2ea043;color:#fff;padding:2px 8px;border-radius:3px;text-decoration:none;font-size:11px;">🔊</a></td></tr>'
    
    return f'''
    <!DOCTYPE html>
    <html><head><meta charset="UTF-8"><title>👑 Админ-панель</title>
    <style>body{{background:#0a0e17;color:#e6edf3;font-family:sans-serif;padding:20px;}}h1{{color:#58a6ff;}}.stats{{display:flex;gap:20px;margin:15px 0;}} .card{{background:#161b22;padding:10px 20px;border-radius:8px;border:1px solid #30363d;}} .card .num{{font-size:24px;font-weight:700;color:#58a6ff;}} table{{width:100%;border-collapse:collapse;}} th{{background:#1c2128;padding:8px 12px;text-align:left;font-size:12px;}} td{{padding:6px 12px;border-bottom:1px solid #30363d;font-size:13px;}} tr:hover{{background:#1c2128;}} .back{{color:#58a6ff;text-decoration:none;}}
    </style></head>
    <body>
    <h1>👑 Админ-панель</h1>
    <p><a href="/" class="back">← На главную</a></p>
    <div class="stats"><div class="card"><span>👥 Всего</span><div class="num">{total}</div></div><div class="card"><span>💎 Premium</span><div class="num" style="color:#f0883e;">{prem}</div></div></div>
    <h2>👥 Пользователи</h2>
    <table><thead><tr><th>ID</th><th>Username</th><th>Статус</th><th>Сегодня</th><th>Premium до</th><th>Действия</th></tr></thead><tbody>{rows}</tbody></table>
    </body></html>
    '''

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
