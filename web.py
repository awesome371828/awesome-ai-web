# ================= AWESOME AI — ПОЛНАЯ ВЕРСИЯ =================
import os, re, time, uuid, hashlib, json, csv, io
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import quote

import requests
import psycopg2
from flask import Flask, request, jsonify, session, send_file, make_response

# ============ КЛЮЧИ И НАСТРОЙКИ ============
PORT = int(os.environ.get("PORT", "8080"))
SESSION_TTL = 30 * 24 * 3600  # автовход 30 дней

YANDEX_API_KEY = "AQVNyfn82epL9dy8C_kftzeypq6eF9lFd6SZnFzV"
FOLDER_ID = "b1g4aq87c7j61c6g3i5l"
GIGACHAT_AUTH_KEY = "MDFhMDBkNmEtMmExNC03M2JkLWFlZmMtOTQ0OWVlOTc5M2U1OmE1ZWJhM2NlLTQwYjAtNDZlYi1iMmY2LTE3OTFmYzhhYTQ2MA=="
SUPABASE_URL = "https://lprxbmshmuucymkgaqwk.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoiYW5vbiIsImlhdCI6MTczODAwMDAwMCwiZXhwIjoyMDUzNTk2MDAwfQ"
DATABASE_URL = "postgresql://u_cmsu43cr30:3sdZICdPDoR1DUrRRKsJ8yW1BqrH2PvZ@db-team-cmsu3ykqi0295mo01tsv8m15p:5432/db_awesome_ai_web"
TELEGRAM_TOKEN = "8336209662:AAHdhYXhqWA-LtthwgydDSRU7A6A0ceC-HY"

OWNER_TGID = "6652898792"
OWNER_PASS = "qawsedrf2346"
OWNER_NAME = "Сергей (владелец)"

app = Flask(__name__)
app.secret_key = "sourcecraft-awesome-ai-secret-2024"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(seconds=SESSION_TTL)

BOT = "https://api.telegram.org/bot" + TELEGRAM_TOKEN
_http = requests.Session()

# ============ БАЗА ДАННЫХ ============
def get_conn():
    return psycopg2.connect(DATABASE_URL)

def hash_pw(p):
    return hashlib.sha256(p.encode()).hexdigest()

def init_db():
    """ПОЛНЫЙ СБРОС + создание таблиц + только владелец."""
    conn = get_conn(); conn.autocommit = True; cur = conn.cursor()
    for t in ["users", "chats_web", "messages_web", "total_stats_web", "shared_chats", "admin_log"]:
        cur.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    cur.execute("""CREATE TABLE users (
        id SERIAL PRIMARY KEY, user_id TEXT UNIQUE, username TEXT,
        password TEXT, role TEXT DEFAULT 'user', xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1,
        ref_code TEXT, ref_by TEXT, created_at TIMESTAMPTZ DEFAULT now())""")
    cur.execute("""CREATE TABLE chats_web (
        id SERIAL PRIMARY KEY, user_id TEXT, chat_id TEXT, title TEXT,
        pinned INTEGER DEFAULT 0, created_at TIMESTAMPTZ DEFAULT now())""")
    cur.execute("""CREATE TABLE messages_web (
        id SERIAL PRIMARY KEY, chat_id TEXT, role TEXT, content TEXT,
        image TEXT, file TEXT, created_at TIMESTAMPTZ DEFAULT now())""")
    cur.execute("""CREATE TABLE total_stats_web (
        id SERIAL PRIMARY KEY, user_id TEXT, messages INTEGER DEFAULT 0,
        images INTEGER DEFAULT 0, updated_at TIMESTAMPTZ DEFAULT now())""")
    cur.execute("""CREATE TABLE shared_chats (
        id SERIAL PRIMARY KEY, share_code TEXT UNIQUE, chat_id TEXT,
        created_at TIMESTAMPTZ DEFAULT now())""")
    cur.execute("""CREATE TABLE admin_log (
        id SERIAL PRIMARY KEY, admin TEXT, action TEXT, target TEXT,
        created_at TIMESTAMPTZ DEFAULT now())""")
    cur.execute("INSERT INTO users (user_id, username, password, role, ref_code) VALUES (%s,%s,%s,%s,%s)",
                (OWNER_TGID, OWNER_NAME, hash_pw(OWNER_PASS), "owner", "owner"))
    cur.close(); conn.close()
    print("=== ПОЛНЫЙ СБРОС ВЫПОЛНЕН, СОЗДАН ТОЛЬКО ВЛАДЕЛЕЦ ===")

# ============ SUPABASE (Premium/админ/владелец из бота) ============
SB_HDR = {"apikey": SUPABASE_ANON_KEY, "Authorization": "Bearer " + SUPABASE_ANON_KEY}

def sb_get(tgid):
    try:
        r = _http.get(f"{SUPABASE_URL}/rest/v1/users?telegram_id=eq.{tgid}&select=*", headers=SB_HDR, timeout=5)
        if r.status_code == 200 and r.json():
            return r.json()[0]
    except Exception:
        pass
    return None

def eff_status(tgid):
    d = sb_get(tgid) or {}
    premium = d.get("premium", False) or d.get("is_premium", False)
    until = d.get("premium_until")
    now = datetime.now(timezone.utc)
    if isinstance(until, str):
        try:
            u = datetime.fromisoformat(until.replace("Z", "+00:00"))
            if u < now: premium = False
        except Exception: pass
    admin = d.get("admin", False) or d.get("is_admin", False)
    role = "owner" if str(tgid) == OWNER_TGID else ("admin" if admin else ("premium" if premium else "user"))
    return {"premium": bool(premium), "until": str(until or ""), "admin": bool(admin),
            "role": role, "owner": str(tgid) == OWNER_TGID}

# ============ АВТОРИЗАЦИЯ ============
def login_required(f):
    @wraps(f)
    def wrap(*a, **k):
        if not session.get("uid"):
            return jsonify({"ok": False, "error": "Войдите в аккаунт"}), 401
        return f(*a, **k)
    return wrap

@app.route("/api/login", methods=["POST"])
def login():
    d = request.get_json() or {}
    tgid = str(d.get("telegram_id", "")).strip()
    pwd = str(d.get("password", "")).strip()
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT username, password, role, xp, level, ref_code FROM users WHERE user_id=%s", (tgid,))
    row = cur.fetchone(); cur.close(); conn.close()
    if not row:
        return jsonify({"ok": False, "error": "Аккаунт не найден"})
    name, db_pw, role, xp, level, ref_code = row
    if hash_pw(pwd) != db_pw:
        return jsonify({"ok": False, "error": "Неверный пароль"})
    session.permanent = True
    session["uid"] = tgid; session["name"] = name; session["role"] = role
    return jsonify({"ok": True, "uid": tgid, "name": name, "role": role, "xp": xp, "level": level, "ref": ref_code})

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})

@app.route("/api/me")
@login_required
def me():
    st = eff_status(session["uid"])
    return jsonify({"ok": True, "uid": session["uid"], "name": session.get("name", ""), "status": st})

# ============ ИИ (быстрый ответ, без «соединение») ============
def quick_answers(text):
    t = text.lower()
    if any(w in t for w in ["привет", "здравств", "хай", "hello", "ку"]):
        return "Привет! 👋 Я AWESOME AI. Умею: отвечать на вопросы, считать, генерировать картинки, погоду, курсы валют, криптовалюты, праздники. Спрашивай!"
    if "погод" in t:
        return "Точный прогноз смотри на Яндекс.Погоде или Gismeteo ☁️ (в этой сборке нет живого доступа к метеоданным)"
    if "доллар" in t or "курс" in t or "валю" in t:
        return "Актуальные курсы валют — на ЦБ РФ (cbr.ru) или в твоём банке 💱"
    if "битко" in t or "крипт" in t or "btc" in t:
        return "Цены на крипту — на CoinGecko или Binance 🪙"
    if "праздник" in t or "какой сегодня день" in t:
        return "Проверь календарь праздников на сегодня 📅"
    if re.search(r"[0-9]+\s*[+\-*/]\s*[0-9]+", t):
        try:
            res = eval(re.search(r"[0-9+\-*/().\s]+", t).group().strip())
            return f"Результат: {res} 🧮"
        except Exception:
            return "Напиши, например: 2+2*3"
    if "кто ты" in t or "ты кто" in t:
        return "Я AWESOME AI — умный помощник нового поколения. Делаю анализ, отвечаю на вопросы, помогаю с задачами ✨"
    if "спасибо" in t or "благодар" in t:
        return "Всегда пожалуйста! 😊 Обращайся ещё!"
    if "пока" in t or "до свидания" in t:
        return "Пока! Было приятно пообщаться 👋"
    return None

def smart_answer(msg):
    q = quick_answers(msg)
    if q: return q
    # GigaChat
    try:
        r = _http.post("https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
                       data={"scope": "GIGACHAT_API_PERS"},
                       headers={"Authorization": "Basic " + GIGACHAT_AUTH_KEY,
                                "RqUID": str(uuid.uuid4()),
                                "Content-Type": "application/x-www-form-urlencoded"}, timeout=6)
        tok = r.json().get("access_token")
        if tok:
            r = _http.post("https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
                           json={"model": "GigaChat", "messages": [{"role": "user", "content": msg}]},
                           headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"}, timeout=25)
            ans = r.json()["choices"][0]["message"]["content"]
            if ans and len(ans.strip()) > 1: return ans.strip()
    except Exception: pass
    # YandexGPT
    try:
        r = _http.post("https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
                       json={"modelUri": f"gpt://{FOLDER_ID}/yandexgpt-lite",
                             "completionOptions": {"temperature": 0.6, "maxTokens": 500},
                             "messages": [{"role": "user", "text": msg}]},
                       headers={"Authorization": "Api-Key " + YANDEX_API_KEY,
                                "Content-Type": "application/json"}, timeout=25)
        ans = r.json()["result"]["alternatives"][0]["message"]["text"]
        if ans and len(ans.strip()) > 1: return ans.strip()
    except Exception: pass
    return "Не удалось связаться с нейросетью (возможно, на хостинге нет доступа к внешним API). Но я на связи! Попробуй написать ещё раз — или спроси про погоду, курсы, крипту, математику."

# ============ ЧАТ ============
def get_history(chat_id, n=30):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT role, content FROM messages_web WHERE chat_id=%s ORDER BY id DESC LIMIT %s", (chat_id, n))
    rows = cur.fetchall(); cur.close(); conn.close()
    return list(reversed(rows))

def add_xp(tgid, amount=5):
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("UPDATE users SET xp=xp+%s, level=1+(xp+%s)/100 WHERE user_id=%s", (amount, amount, tgid))
        conn.commit(); cur.close(); conn.close()
    except Exception: pass

@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    d = request.get_json() or {}
    chat_id = str(d.get("chat_id", ""))
    msg = str(d.get("message", "")).strip()
    if not msg: return jsonify({"ok": False, "error": "Пустое сообщение"})
    conn = get_conn(); cur = conn.cursor()
    if not chat_id:
        chat_id = uuid.uuid4().hex[:10]
        cur.execute("INSERT INTO chats_web (user_id, chat_id, title) VALUES (%s,%s,%s)",
                    (session["uid"], chat_id, msg[:30]))
    cur.execute("INSERT INTO messages_web (chat_id, role, content) VALUES (%s,%s,%s)", (chat_id, "user", msg))
    cur.execute("UPDATE total_stats_web SET messages=messages+1 WHERE user_id=%s", (session["uid"],))
    conn.commit()
    hist = get_history(chat_id, 30)
    context = "\n".join(f"{'Пользователь' if r=='user' else 'ИИ'}: {c}" for r, c in hist)
    answer = smart_answer(msg)
    cur.execute("INSERT INTO messages_web (chat_id, role, content) VALUES (%s,%s,%s)", (chat_id, "assistant", answer))
    conn.commit(); cur.close(); conn.close()
    add_xp(session["uid"])
    return jsonify({"ok": True, "answer": answer, "chat_id": chat_id})

@app.route("/api/chats")
@login_required
def list_chats():
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT chat_id, title, pinned FROM chats_web WHERE user_id=%s ORDER BY pinned DESC, id DESC", (session["uid"],))
    rows = cur.fetchall(); cur.close(); conn.close()
    return jsonify({"ok": True, "chats": [{"id": r[0], "title": r[1], "pinned": r[2]} for r in rows]})

@app.route("/api/messages")
@login_required
def get_msgs():
    chat_id = request.args.get("chat_id", "")
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT role, content, image, file FROM messages_web WHERE chat_id=%s ORDER BY id ASC", (chat_id,))
    rows = cur.fetchall(); cur.close(); conn.close()
    return jsonify({"ok": True, "messages": [{"role": r[0], "content": r[1], "image": r[2], "file": r[3]} for r in rows]})

@app.route("/api/pin", methods=["POST"])
@login_required
def pin():
    d = request.get_json() or {}
    cur = get_conn().cursor()
    cur.execute("UPDATE chats_web SET pinned=%s WHERE chat_id=%s AND user_id=%s",
                (1 if d.get("pin") else 0, d.get("chat_id"), session["uid"]))
    cur.connection.commit(); cur.close()
    return jsonify({"ok": True})

@app.route("/api/rename", methods=["POST"])
@login_required
def rename():
    d = request.get_json() or {}
    cur = get_conn().cursor()
    cur.execute("UPDATE chats_web SET title=%s WHERE chat_id=%s AND user_id=%s",
                (str(d.get("title", ""))[:30], d.get("chat_id"), session["uid"]))
    cur.connection.commit(); cur.close()
    return jsonify({"ok": True})

@app.route("/api/delete_chat", methods=["POST"])
@login_required
def delete_chat():
    d = request.get_json() or {}
    conn = get_conn(); cur = conn.cursor()
    cur.execute("DELETE FROM chats_web WHERE chat_id=%s AND user_id=%s", (d.get("chat_id"), session["uid"]))
    cur.execute("DELETE FROM messages_web WHERE chat_id=%s", (d.get("chat_id"),))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok": True})

@app.route("/api/image", methods=["POST"])
@login_required
def gen_image():
    prompt = str((request.get_json() or {}).get("prompt", "")).strip() or "abstract art"
    url = f"https://image.pollinations.ai/prompt/{quote(prompt)}"
    return jsonify({"ok": True, "url": url})

@app.route("/api/share", methods=["POST"])
@login_required
def share():
    d = request.get_json() or {}
    chat_id = str(d.get("chat_id", ""))
    code = uuid.uuid4().hex[:8]
    conn = get_conn(); cur = conn.cursor()
    cur.execute("INSERT INTO shared_chats (share_code, chat_id) VALUES (%s,%s)", (code, chat_id))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok": True, "url": "/s/" + code})

@app.route("/s/<code>")
def shared(code):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT chat_id FROM shared_chats WHERE share_code=%s", (code,))
    row = cur.fetchone(); cur.close(); conn.close()
    if not row: return "Чат не найден", 404
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT role, content FROM messages_web WHERE chat_id=%s ORDER BY id ASC", (row[0],))
    msgs = cur.fetchall(); cur.close(); conn.close()
    html = "<html><body style='font-family:sans-serif;padding:20px;background:#0f172a;color:#e2e8f0'><h2>💬 Публичный чат</h2>"
    for r, c in msgs:
        cls = "user" if r == "user" else "ai"
        color = "#6fd8c0" if r == "user" else "#7b9cff"
        html += f"<div style='margin:8px 0;padding:10px;border-radius:10px;background:#1e293b;border-left:4px solid {color}'><b>{'Вы' if r=='user' else 'AI'}:</b> {c}</div>"
    html += "</body></html>"
    return html

@app.route("/api/export")
@login_required
def export_chat():
    chat_id = request.args.get("chat_id", "")
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT role, content FROM messages_web WHERE chat_id=%s ORDER BY id ASC", (chat_id,))
    rows = cur.fetchall(); cur.close(); conn.close()
    text = "\n\n".join(f"{'Вы' if r=='user' else 'AI'}:\n{c}" for r, c in rows)
    buf = io.BytesIO(text.encode("utf-8"))
    return send_file(buf, as_attachment=True, download_name="chat.txt", mimetype="text/plain")

# ============ АДМИН (только владелец) ============
def owner_required(f):
    @wraps(f)
    def wrap(*a, **k):
        if str(session.get("uid")) != OWNER_TGID:
            return jsonify({"ok": False, "error": "Доступ только владельцу"}), 403
        return f(*a, **k)
    return wrap

def admin_log(action, target):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("INSERT INTO admin_log (admin, action, target) VALUES (%s,%s,%s)",
                (session.get("uid", ""), action, target))
    conn.commit(); cur.close(); conn.close()

@app.route("/api/admin/stats")
@owner_required
def admin_stats():
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users"); users = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(SUM(messages),0) FROM total_stats_web"); msgs = cur.fetchone()[0]
    cur.execute("SELECT user_id, username, role, xp, level FROM users ORDER BY id DESC LIMIT 200")
    us = cur.fetchall(); cur.close(); conn.close()
    return jsonify({"ok": True, "users": users, "messages": msgs,
                    "list": [{"id": u[0], "name": u[1], "role": u[2], "xp": u[3], "level": u[4]} for u in us]})

@app.route("/api/admin/delete_user", methods=["POST"])
@owner_required
def admin_delete_user():
    d = request.get_json() or {}
    tgid = str(d.get("telegram_id", "")).strip()
    if not tgid or tgid == OWNER_TGID:
        return jsonify({"ok": False, "error": "Нельзя удалить"})
    conn = get_conn(); cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE user_id=%s", (tgid,))
    conn.commit(); cur.close(); conn.close()
    admin_log("удалил аккаунт", tgid)
    return jsonify({"ok": True})

@app.route("/api/admin/reset_password", methods=["POST"])
@owner_required
def admin_reset_password():
    d = request.get_json() or {}
    tgid = str(d.get("telegram_id", "")).strip()
    newp = str(d.get("password", "")).strip()
    if not tgid or not newp:
        return jsonify({"ok": False, "error": "Нужны Telegram-ID и новый пароль"})
    conn = get_conn(); cur = conn.cursor()
    cur.execute("UPDATE users SET password=%s WHERE user_id=%s", (hash_pw(newp), tgid))
    conn.commit(); cur.close(); conn.close()
    admin_log("сбросил пароль", tgid)
    return jsonify({"ok": True})

@app.route("/api/admin/broadcast", methods=["POST"])
@owner_required
def admin_broadcast():
    d = request.get_json() or {}
    text = str(d.get("text", "")).strip()
    if not text: return jsonify({"ok": False, "error": "Пустой текст"})
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    ids = [r[0] for r in cur.fetchall()]; cur.close(); conn.close()
    for tid in ids:
        try:
            _http.post(f"{BOT}/sendMessage", json={"chat_id": tid, "text": text}, timeout=5)
        except Exception: pass
    admin_log("рассылка", f"{len(ids)} юзеров")
    return jsonify({"ok": True, "sent": len(ids)})

@app.route("/api/force_owner", methods=["POST"])
def force_owner():
    d = request.get_json() or {}
    if str(d.get("telegram_id", "")) != OWNER_TGID:
        return jsonify({"ok": False, "error": "Недоступно"})
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE user_id=%s", (OWNER_TGID,))
    if cur.fetchone():
        cur.execute("UPDATE users SET password=%s, role=%s, username=%s WHERE user_id=%s",
                    (hash_pw(OWNER_PASS), "owner", OWNER_NAME, OWNER_TGID))
    else:
        cur.execute("INSERT INTO users (user_id, username, password, role) VALUES (%s,%s,%s,%s)",
                    (OWNER_TGID, OWNER_NAME, hash_pw(OWNER_PASS), "owner"))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok": True, "message": "Пароль владельца сброшен"})

# ============ ГЛАВНАЯ ============
@app.route("/")
def index():
    return INDEX_HTML

INDEX_HTML = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AWESOME AI</title>
<style>
:root{--ac1:#7b9cff;--ac2:#6fd8c0;--text:#e2e8f0;--card:#1e293b;--bg:#0f172a;--muted:#94a3b8}
*{box-sizing:border-box;margin:0;padding:0;font-family:'Segoe UI',system-ui,sans-serif}
body{background:linear-gradient(135deg,#0f172a 0%,#1a2a4a 50%,#123a3a 100%);min-height:100vh;color:var(--text)}
@keyframes fadeUp{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:translateY(0)}}
@keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}
@keyframes glow{0%,100%{box-shadow:0 0 0 rgba(127,156,255,0)}50%{box-shadow:0 0 30px rgba(127,156,255,.25)}}
.card{background:var(--card);border-radius:22px;padding:36px 32px;width:100%;max-width:420px;
box-shadow:0 20px 60px rgba(0,0,0,.5);animation:fadeUp .5s ease;text-align:center;margin:auto}
.wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.logo{font-size:34px;font-weight:800;background:linear-gradient(90deg,var(--ac1),var(--ac2));
-webkit-background-clip:text;background-clip:text;color:transparent;animation:float 3s ease-in-out infinite}
.sub{color:var(--muted);font-size:14px;margin:8px 0 24px}
input{width:100%;background:var(--bg);border:1.5px solid #334155;border-radius:14px;padding:14px 16px;
color:#fff;font-size:15px;outline:none;margin-bottom:12px;transition:border-color .2s}
input:focus{border-color:var(--ac1)}
.btn{width:100%;background:linear-gradient(90deg,var(--ac1),var(--ac2));color:#fff;border:none;border-radius:14px;
padding:14px;font-size:16px;font-weight:600;cursor:pointer;transition:transform .15s,box-shadow .2s;animation:glow 3s ease-in-out infinite}
.btn:hover{transform:translateY(-2px)}
.err{color:#f87171;font-size:13px;margin-top:10px;min-height:18px}
.hint{color:#64748b;font-size:12px;margin-top:16px}
</style></head><body>
<div class="wrap"><div class="card">
  <div class="logo">✨ AWESOME AI</div>
  <div class="sub">Умный помощник нового поколения</div>
  <input id="authTg" placeholder="Telegram ID">
  <input id="authPass" type="password" placeholder="Пароль">
  <button class="btn" onclick="doLogin()">Войти</button>
  <div class="err" id="err"></div>
  <div class="hint">AWESOME AI · вход по Telegram ID</div>
</div></div>
<script>
async function doLogin(){
 const tg=document.getElementById('authTg').value.trim();
 const pw=document.getElementById('authPass').value.trim();
 document.getElementById('err').textContent='';
 if(!tg||!pw){document.getElementById('err').textContent='Заполни оба поля';return;}
 try{
  const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:tg,password:pw})});
  const d=await r.json();
  if(!d.ok){document.getElementById('err').textContent=d.error;return;}
  document.body.innerHTML='<div style="display:flex;align-items:center;justify-content:center;height:100vh;font-size:22px;color:var(--text)">✅ Вход выполнен! Обновляем...</div>';
  location.reload();
 }catch(e){document.getElementById('err').textContent='Ошибка сети';}
}
</script></body></html>"""

if __name__ == "__main__":
    init_db()
    try:
        from waitress import serve
        serve(app, host="0.0.0.0", port=PORT, threads=8)
    except ImportError:
        app.run(host="0.0.0.0", port=PORT)
