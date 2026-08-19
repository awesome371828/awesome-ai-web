import os, re, time, uuid, hashlib, json, threading
from datetime import datetime, timedelta, timezone
from functools import wraps

import requests
import psycopg2
import psycopg2.extras
from flask import Flask, request, jsonify, session, send_file, redirect

# ============ НАСТРОЙКИ ============
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
OWNER_USERNAME = "flidges"

app = Flask(__name__)
app.secret_key = "sourcecraft-awesome-ai-secret"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(seconds=SESSION_TTL)

BOT = "https://api.telegram.org/bot" + TELEGRAM_TOKEN
_http = requests.Session()

# ============ БАЗА ДАННЫХ ============
def get_conn():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        user_id TEXT UNIQUE,
        username TEXT,
        password TEXT,
        role TEXT DEFAULT 'user',
        xp INTEGER DEFAULT 0,
        level INTEGER DEFAULT 1,
        ref_by TEXT DEFAULT NULL,
        created_at TIMESTAMPTZ DEFAULT now())""")
    cur.execute("""CREATE TABLE IF NOT EXISTS chats_web (
        id SERIAL PRIMARY KEY,
        user_id TEXT, chat_id TEXT, title TEXT, pinned INTEGER DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT now())""")
    cur.execute("""CREATE TABLE IF NOT EXISTS messages_web (
        id SERIAL PRIMARY KEY, chat_id TEXT, role TEXT, content TEXT,
        image TEXT, created_at TIMESTAMPTZ DEFAULT now())""")
    cur.execute("""CREATE TABLE IF NOT EXISTS total_stats_web (
        id SERIAL PRIMARY KEY, user_id TEXT, messages INTEGER DEFAULT 0,
        images INTEGER DEFAULT 0, updated_at TIMESTAMPTZ DEFAULT now())""")
    cur.execute("""CREATE TABLE IF NOT EXISTS shared_chats (
        id SERIAL PRIMARY KEY, share_code TEXT UNIQUE, chat_id TEXT, created_at TIMESTAMPTZ DEFAULT now())""")
    cur.execute("""CREATE TABLE IF NOT EXISTS admin_log (
        id SERIAL PRIMARY KEY, admin TEXT, action TEXT, target TEXT,
        created_at TIMESTAMPTZ DEFAULT now())""")
    cur.execute("""ALTER TABLE messages_web ADD COLUMN IF NOT EXISTS image TEXT""")
    conn.commit(); cur.close(); conn.close()
    ensure_owner()

def ensure_owner():
    """Восстанавливает аккаунт владельца при каждом запуске (пароль не сбрасывает)."""
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT password FROM users WHERE user_id=%s", (OWNER_TGID,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT INTO users (user_id, username, password, role) VALUES (%s,%s,%s,%s)",
                    (OWNER_TGID, OWNER_USERNAME, hash_pw(OWNER_PASS), "owner"))
        conn.commit()
    cur.close(); conn.close()

def hash_pw(p):
    return hashlib.sha256(p.encode()).hexdigest()

# ============ SUPABASE (источник истины для Premium/админа/владельца) ============
SB_HDR = {"apikey": SUPABASE_ANON_KEY, "Authorization": "Bearer " + SUPABASE_ANON_KEY}

def sb_get(tgid):
    try:
        r = _http.get(f"{SUPABASE_URL}/rest/v1/users?telegram_id=eq.{tgid}&select=*",
                      headers=SB_HDR, timeout=5)
        if r.status_code == 200 and r.json():
            return r.json()[0]
    except Exception:
        pass
    return None

def eff_status(tgid):
    """Premium/админ/владелец всегда из Supabase (базы бота)."""
    d = sb_get(tgid) or {}
    premium = d.get("premium", False) or d.get("is_premium", False)
    until = d.get("premium_until")
    now = datetime.now(timezone.utc)
    if isinstance(until, str):
        try:
            until = datetime.fromisoformat(until.replace("Z", "+00:00"))
            if until < now:
                premium = False
        except Exception:
            pass
    admin = d.get("admin", False) or d.get("is_admin", False)
    role = "owner" if str(tgid) == OWNER_TGID else ("admin" if admin else ("premium" if premium else "user"))
    return {"premium": bool(premium), "until": str(until or ""), "admin": bool(admin),
            "role": role, "owner": str(tgid) == OWNER_TGID}

def sb_set_premium(tgid, premium, days=0, hours=0, minutes=0):
    """Меняет Premium ПРЯМО в Supabase (база бота) -> /status в ТГ сразу видит."""
    until = None
    if premium:
        until = datetime.now(timezone.utc) + timedelta(days=days, hours=hours, minutes=minutes)
    body = {"premium": premium, "premium_until": until.isoformat() if until else None}
    _http.patch(f"{SUPABASE_URL}/rest/v1/users?telegram_id=eq.{tgid}",
                json=body, headers={**SB_HDR, "Content-Type": "application/json"}, timeout=5)

def sb_set_admin(tgid, admin):
    _http.patch(f"{SUPABASE_URL}/rest/v1/users?telegram_id=eq.{tgid}",
                json={"admin": admin}, headers={**SB_HDR, "Content-Type": "application/json"}, timeout=5)

# ============ ВХОД / РЕГИСТРАЦИЯ ============
def login_required(f):
    @wraps(f)
    def wrap(*a, **k):
        if not session.get("uid"):
            return jsonify({"ok": False, "error": "Войдите в аккаунт"}), 401
        return f(*a, **k)
    return wrap

@app.route("/api/reg", methods=["POST"])
def reg():
    d = request.get_json() or {}
    name = str(d.get("name", "")).strip()
    tgid = str(d.get("telegram_id", "")).strip()
    pwd = str(d.get("password", "")).strip()
    if not name or not tgid or not pwd:
        return jsonify({"ok": False, "error": "Все поля обязательны"})
    if len(pwd) < 4:
        return jsonify({"ok": False, "error": "Пароль минимум 4 символа"})
    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE user_id=%s", (tgid,))
        if cur.fetchone():
            return jsonify({"ok": False, "error": "Аккаунт уже существует — войдите"})
        cur.execute("INSERT INTO users (user_id, username, password, role) VALUES (%s,%s,%s,%s)",
                    (tgid, name, hash_pw(pwd), "user"))
        conn.commit()
    finally:
        cur.close(); conn.close()
    return login_user_core(tgid, name)

@app.route("/api/login", methods=["POST"])
def login():
    d = request.get_json() or {}
    tgid = str(d.get("telegram_id", "")).strip()
    pwd = str(d.get("password", "")).strip()
    return login_user_core(tgid, pwd)

def login_user_core(tgid, pwd):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT username, password, role FROM users WHERE user_id=%s", (tgid,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        return jsonify({"ok": False, "error": "Аккаунт не найден — зарегистрируйтесь"})
    name, db_pw, _role = row
    if hash_pw(pwd) != db_pw:
        return jsonify({"ok": False, "error": "Неверный пароль"})
    session.permanent = True
    session["uid"] = tgid
    session["name"] = name
    return jsonify({"ok": True, "uid": tgid, "name": name})

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})

@app.route("/api/me")
@login_required
def me():
    st = eff_status(session["uid"])
    return jsonify({"ok": True, "uid": session["uid"], "name": session.get("name", ""), "status": st})

@app.route("/api/force_owner", methods=["POST"])
def force_owner():
    """Сброс пароля владельца (для восстановления входа)."""
    d = request.get_json() or {}
    if str(d.get("telegram_id", "")) != OWNER_TGID:
        return jsonify({"ok": False, "error": "Недоступно"})
    pwd = str(d.get("password", "")).strip() or OWNER_PASS
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE user_id=%s", (OWNER_TGID,))
    if cur.fetchone():
        cur.execute("UPDATE users SET password=%s, role=%s WHERE user_id=%s",
                    (hash_pw(pwd), "owner", OWNER_TGID))
    else:
        cur.execute("INSERT INTO users (user_id, username, password, role) VALUES (%s,%s,%s,%s)",
                    (OWNER_TGID, OWNER_USERNAME, hash_pw(pwd), "owner"))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok": True, "message": "Пароль владельца сброшен"})

# ============ ИИ: GigaChat -> YandexGPT -> заготовки (всегда быстрый ответ) ============
def smart_answer(msg):
    text = str(msg).strip().lower()
    # заготовки мгновенно
    quick = quick_answers(text)
    if quick:
        return quick

    # 1) GigaChat
    try:
        r = _http.post("https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
                       data={"scope": "GIGACHAT_API_PERS"},
                       headers={"Authorization": "Basic " + GIGACHAT_AUTH_KEY,
                                "RqUID": str(uuid.uuid4()),
                                "Content-Type": "application/x-www-form-urlencoded"},
                       timeout=6)
        tok = r.json().get("access_token")
        if tok:
            r = _http.post("https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
                           json={"model": "GigaChat", "messages": [{"role": "user", "content": msg}]},
                           headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"},
                           timeout=25)
            ans = r.json()["choices"][0]["message"]["content"]
            if ans and len(ans.strip()) > 1:
                return ans.strip()
    except Exception:
        pass

    # 2) YandexGPT
    try:
        r = _http.post("https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
                       json={"modelUri": f"gpt://{FOLDER_ID}/yandexgpt-lite",
                             "completionOptions": {"temperature": 0.6, "maxTokens": 700},
                             "messages": [{"role": "user", "text": msg}]},
                       headers={"Authorization": "Api-Key " + YANDEX_API_KEY,
                                "Content-Type": "application/json"},
                       timeout=25)
        ans = r.json()["result"]["alternatives"][0]["message"]["text"]
        if ans and len(ans.strip()) > 1:
            return ans.strip()
    except Exception:
        pass

    # 3) универсальный fallback
    return "Я не смог получить ответ от нейросети (возможно, на хостинге нет доступа к внешним API), но вот что могу: " + quick_answers("привет") if "привет" in text else "Не удалось связаться с нейросетью. Попробуйте ещё раз через несколько секунд."

def quick_answers(text):
    t = text
    if any(w in t for w in ["привет", "здравств", "хай", "hello", "ку "]):
        return "Привет! 👋 Я AWESOME AI. Спроси меня что-нибудь, а ещё я умею: погода, курсы валют, криптовалюты, математика, праздники."
    if "погод" in t:
        return "Скажи город, например: «погода в Москве». Я не могу получить реальные данные без ключа погодного API, но вот подсказка: проверь прогноз на Яндекс.Погоде или Gismeteo ☁️"
    if "доллар" in t or "курс" in t or "валю" in t:
        return "Актуальные курсы валют лучше смотреть на ЦБ РФ (cbr.ru) или в вашем банке. Я не имею живого доступа к бирже в этой сборке 💱"
    if "битко" in t or "крипт" in t or "btc" in t:
        return "Цены на криптовалюты смотрите на CoinGecko или Binance. Здесь живой курс недоступен 🪙"
    if re.search(r"[0-9]+\s*[+\-*/]\s*[0-9]+", t):
        try:
            res = eval(re.search(r"[0-9+\-*/().\s]+", t).group().strip())
            return f"Результат: {res} 🧮"
        except Exception:
            return "Не понял выражение. Напишите, например: 2+2*3"
    if "праздник" in t or "какой сегодня день" in t:
        return "Проверьте календарь праздников на сегодня — у меня нет живого доступа к нему в этой сборке 📅"
    return None

# ============ ЧАТ ============
def get_history(chat_id, n=8):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT role, content FROM messages_web WHERE chat_id=%s ORDER BY id DESC LIMIT %s", (chat_id, n))
    rows = cur.fetchall(); cur.close(); conn.close()
    return list(reversed(rows))

@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    d = request.get_json() or {}
    chat_id = str(d.get("chat_id", ""))
    msg = str(d.get("message", "")).strip()
    if not msg:
        return jsonify({"ok": False, "error": "Пустое сообщение"})
    conn = get_conn(); cur = conn.cursor()
    if not chat_id:
        chat_id = uuid.uuid4().hex[:10]
        cur.execute("INSERT INTO chats_web (user_id, chat_id, title) VALUES (%s,%s,%s)",
                    (session["uid"], chat_id, msg[:30]))
    cur.execute("INSERT INTO messages_web (chat_id, role, content) VALUES (%s,%s,%s)", (chat_id, "user", msg))
    cur.execute("UPDATE total_stats_web SET messages=messages+1 WHERE user_id=%s", (session["uid"],))
    conn.commit()
    hist = get_history(chat_id, 20)
    context = "\n".join(f"{'Пользователь' if r=='user' else 'ИИ'}: {c}" for r, c in hist)
    full = context + "\nИИ:"
    answer = smart_answer(msg if True else full)
    cur.execute("INSERT INTO messages_web (chat_id, role, content) VALUES (%s,%s,%s)", (chat_id, "assistant", answer))
    conn.commit(); cur.close(); conn.close()
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
    cur.execute("SELECT role, content, image FROM messages_web WHERE chat_id=%s ORDER BY id ASC", (chat_id,))
    rows = cur.fetchall(); cur.close(); conn.close()
    return jsonify({"ok": True, "messages": [{"role": r[0], "content": r[1], "image": r[2]} for r in rows]})

@app.route("/api/pin", methods=["POST"])
@login_required
def pin():
    d = request.get_json() or {}
    cur = get_conn().cursor()
    cur.execute("UPDATE chats_web SET pinned=%s WHERE chat_id=%s AND user_id=%s",
                (1 if d.get("pin") else 0, d.get("chat_id"), session["uid"]))
    cur.connection.commit(); cur.close()
    return jsonify({"ok": True})

@app.route("/api/image", methods=["POST"])
@login_required
def gen_image():
    prompt = str((request.get_json() or {}).get("prompt", "")).strip() or "abstract art"
    url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(prompt)}"
    return jsonify({"ok": True, "url": url})

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
    cur.execute("SELECT user_id, username, role FROM users ORDER BY id DESC LIMIT 100")
    us = cur.fetchall(); cur.close(); conn.close()
    return jsonify({"ok": True, "users": users, "messages": msgs,
                    "list": [{"id": u[0], "name": u[1], "role": u[2]} for u in us]})

@app.route("/api/admin/set_premium", methods=["POST"])
@owner_required
def admin_set_premium():
    d = request.get_json() or {}
    tgid = str(d.get("telegram_id", "")).strip()
    days = int(d.get("days", 0)); hours = int(d.get("hours", 0)); minutes = int(d.get("minutes", 0))
    if not tgid:
        return jsonify({"ok": False, "error": "Нужен Telegram-ID"})
    sb_set_premium(tgid, True, days, hours, minutes)
    admin_log("выдал Premium", tgid)
    return jsonify({"ok": True})

@app.route("/api/admin/remove_premium", methods=["POST"])
@owner_required
def admin_remove_premium():
    d = request.get_json() or {}
    tgid = str(d.get("telegram_id", "")).strip()
    if not tgid:
        return jsonify({"ok": False, "error": "Нужен Telegram-ID"})
    sb_set_premium(tgid, False)  # пишем прямо в Supabase -> бот сразу видит
    admin_log("снял Premium", tgid)
    return jsonify({"ok": True})

@app.route("/api/admin/set_admin", methods=["POST"])
@owner_required
def admin_set_admin():
    d = request.get_json() or {}
    tgid = str(d.get("telegram_id", "")).strip()
    if not tgid:
        return jsonify({"ok": False, "error": "Нужен Telegram-ID"})
    sb_set_admin(tgid, bool(d.get("admin")))
    admin_log("изменил админа", tgid)
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

@app.route("/api/admin/broadcast", methods=["POST"])
@owner_required
def admin_broadcast():
    d = request.get_json() or {}
    text = str(d.get("text", "")).strip()
    if not text:
        return jsonify({"ok": False, "error": "Пустой текст"})
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    ids = [r[0] for r in cur.fetchall()]; cur.close(); conn.close()
    for tid in ids:
        try:
            _http.post(f"{BOT}/sendMessage", json={"chat_id": tid, "text": text}, timeout=5)
        except Exception:
            pass
    admin_log("рассылка", f"{len(ids)} юзеров")
    return jsonify({"ok": True, "sent": len(ids)})

# ============ ГЛАВНАЯ ============
@app.route("/")
def index():
    return INDEX_HTML

INDEX_HTML = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AWESOME AI</title>
<style>
:root{--bg:#0f172a;--card:#1e293b;--text:#e2e8f0;--ac1:#7b9cff;--ac2:#6fd8c0}
*{box-sizing:border-box;margin:0;padding:0;font-family:'Segoe UI',system-ui,sans-serif}
body{background:linear-gradient(135deg,#0f172a,#1a2a4a);color:var(--text);min-height:100vh}
.container{max-width:900px;margin:0 auto;padding:16px}
@keyframes fadeUp{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
@keyframes bounce{0%,100%{transform:translateY(0)}50%{transform:translateY(-4px)}}
.card{background:var(--card);border-radius:16px;padding:20px;margin-bottom:14px;animation:fadeUp .4s ease}
.btn{background:linear-gradient(90deg,var(--ac1),var(--ac2));color:#fff;border:none;border-radius:12px;
padding:12px 22px;font-size:15px;cursor:pointer;transition:transform .15s,box-shadow .2s}
.btn:hover{transform:translateY(-2px);box-shadow:0 8px 24px rgba(127,156,255,.35)}
input,textarea{width:100%;background:#0f172a;border:1px solid #334155;border-radius:12px;padding:12px;
color:#fff;font-size:15px;outline:none;margin-bottom:10px}
input:focus,textarea:focus{border-color:var(--ac1)}
.hidden{display:none}
.msg{animation:fadeUp .3s ease;padding:12px;border-radius:12px;margin:6px 0;max-width:85%}
.msg.user{background:linear-gradient(90deg,var(--ac1),var(--ac2));margin-left:auto;color:#fff}
.msg.ai{background:#334155;margin-right:auto}
.logo{font-size:26px;font-weight:700;background:linear-gradient(90deg,var(--ac1),var(--ac2));
-webkit-background-clip:text;background-clip:text;color:transparent}
.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;animation:fadeUp .4s ease}
.chip{background:#334155;border-radius:20px;padding:6px 14px;font-size:13px;cursor:pointer;transition:transform .15s}
.chip:hover{transform:scale(1.05)}
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}
.tab{background:#1e293b;border:none;color:var(--text);padding:8px 16px;border-radius:20px;cursor:pointer}
.tab.active{background:linear-gradient(90deg,var(--ac1),var(--ac2));color:#fff}
</style></head><body>
<div class="container">
  <div class="top"><span class="logo">✨ AWESOME AI</span><span id="userInfo"></span></div>

  <!-- ВХОД -->
  <div class="card" id="authCard">
    <h2 id="authTitle">Вход</h2>
    <input id="authName" placeholder="Название (имя)">
    <input id="authTg" placeholder="Telegram ID">
    <input id="authPass" type="password" placeholder="Пароль">
    <button class="btn" id="authBtn" onclick="doAuth()">Войти</button>
    <button class="btn" style="background:#334155;margin-top:8px" onclick="toggleAuth()">Создать аккаунт</button>
    <div id="authErr" style="color:#f87171;margin-top:8px"></div>
  </div>

  <!-- ОСНОВНОЕ -->
  <div class="card hidden" id="mainCard">
    <div class="tabs">
      <button class="tab active" onclick="showTab('chat')">Чат</button>
      <button class="tab" onclick="showTab('chats')">Мои чаты</button>
      <button class="tab" onclick="showTab('admin')" id="adminTab">Админ</button>
      <button class="tab" onclick="logout()">Выйти</button>
    </div>

    <div id="tab-chat">
      <div id="chatBox" style="max-height:50vh;overflow-y:auto;margin-bottom:10px"></div>
      <textarea id="chatInput" placeholder="Напишите сообщение..." rows="2"></textarea>
      <button class="btn" onclick="sendChat()">Отправить ✈</button>
    </div>

    <div id="tab-chats" class="hidden">
      <button class="btn" onclick="newChat()">+ Новый чат</button>
      <div id="chatList"></div>
    </div>

    <div id="tab-admin" class="hidden">
      <h3>Панель владельца</h3>
      <input id="admTg" placeholder="Telegram ID пользователя">
      <input id="admDays" placeholder="Дни" type="number">
      <input id="admHours" placeholder="Часы" type="number">
      <input id="admMin" placeholder="Минуты" type="number">
      <button class="btn" onclick="admPremium()">Выдать Premium</button>
      <button class="btn" style="background:#ef4444" onclick="admRemove()">Снять Premium</button>
      <input id="admPass" placeholder="Новый пароль (для сброса)">
      <button class="btn" onclick="admResetPass()">Сбросить пароль</button>
      <button class="btn" style="background:#ef4444" onclick="admDelete()">Удалить аккаунт</button>
      <div id="adminStats"></div>
    </div>
  </div>
</div>

<script>
let curChat="", isReg=false;
function toggleAuth(){isReg=!isReg;document.getElementById('authTitle').textContent=isReg?'Регистрация':'Вход';
document.getElementById('authName').style.display=isReg?'block':'none';
document.getElementById('authBtn').textContent=isReg?'Создать аккаунт':'Войти';}
async function doAuth(){
 const name=document.getElementById('authName').value.trim();
 const tg=document.getElementById('authTg').value.trim();
 const pw=document.getElementById('authPass').value.trim();
 const url=isReg?'/api/reg':'/api/login';
 const body=isReg?{name,telegram_id:tg,password:pw}:{telegram_id:tg,password:pw};
 const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 const d=await r.json();
 if(!d.ok){document.getElementById('authErr').textContent=d.error;return;}
 sessionStorage.setItem('uid',d.uid);location.reload();
}
async function init(){
 const r=await fetch('/api/me');const d=await r.json();
 if(d.ok){document.getElementById('authCard').classList.add('hidden');
 document.getElementById('mainCard').classList.remove('hidden');
 document.getElementById('userInfo').textContent= d.name+' · '+d.status.role;
 if(d.status.owner)document.getElementById('adminTab').style.display='block';}
}
function showTab(t){
 ['chat','chats','admin'].forEach(x=>{document.getElementById('tab-'+x).classList.toggle('hidden',x!==t);
 document.querySelectorAll('.tab').forEach(b=>b.classList.remove('active'));});
 document.querySelectorAll('.tab')[['chat','chats','admin'].indexOf(t)].classList.add('active');
 if(t==='chats')loadChats(); if(t==='admin')loadAdmin();
}
async function sendChat(){
 const msg=document.getElementById('chatInput').value.trim(); if(!msg)return;
 const box=document.getElementById('chatBox');
 box.innerHTML+='<div class="msg user">'+msg.replace(/</g,'&lt;')+'</div>';
 document.getElementById('chatInput').value='';
 box.innerHTML+='<div class="msg ai">⏳ Думаю...</div>';box.scrollTop=box.scrollHeight;
 const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({chat_id:curChat,message:msg})});
 const d=await r.json();
 box.querySelector('.msg.ai:last-child').textContent=d.answer||'Ошибка';curChat=d.chat_id;box.scrollTop=box.scrollHeight;
}
function newChat(){curChat='';document.getElementById('chatBox').innerHTML='';showTab('chat');}
async function loadChats(){
 const r=await fetch('/api/chats');const d=await r.json();const el=document.getElementById('chatList');el.innerHTML='';
 d.chats.forEach(c=>{const b=document.createElement('button');b.className='chip';b.style.display='block';b.style.margin='4px 0';
 b.textContent=(c.pinned?'📌 ':'')+c.title;b.onclick=()=>{curChat=c.id;showTab('chat');loadMsgs();};el.appendChild(b);});
}
async function loadMsgs(){
 const r=await fetch('/api/messages?chat_id='+curChat);const d=await r.json();const box=document.getElementById('chatBox');
 box.innerHTML='';d.messages.forEach(m=>{box.innerHTML+='<div class="msg '+(m.role==='user'?'user':'ai')+'">'+m.content.replace(/</g,'&lt;')+'</div>';});
 box.scrollTop=box.scrollHeight;
}
async function loadAdmin(){
 const r=await fetch('/api/admin/stats');const d=await r.json();
 document.getElementById('adminStats').innerHTML='<p>Пользователей: '+d.users+' · Сообщений: '+d.messages+'</p>';
}
async function admPremium(){
 const r=await fetch('/api/admin/set_premium',{method:'POST',headers:{'Content-Type':'application/json'},
 body:JSON.stringify({telegram_id:admTg.value.trim(),days:+admDays.value||0,hours:+admHours.value||0,minutes:+admMin.value||0})});
 alert((await r.json()).ok?'Готово':'Ошибка');}
async function admRemove(){
 const r=await fetch('/api/admin/remove_premium',{method:'POST',headers:{'Content-Type':'application/json'},
 body:JSON.stringify({telegram_id:admTg.value.trim()})});alert((await r.json()).ok?'Снято':'Ошибка');}
async function admResetPass(){
 const r=await fetch('/api/admin/reset_password',{method:'POST',headers:{'Content-Type':'application/json'},
 body:JSON.stringify({telegram_id:admTg.value.trim(),password:admPass.value.trim()})});alert((await r.json()).ok?'Готово':'Ошибка');}
async function admDelete(){
 const r=await fetch('/api/admin/delete_user',{method:'POST',headers:{'Content-Type':'application/json'},
 body:JSON.stringify({telegram_id:admTg.value.trim()})});alert((await r.json()).ok?'Удалено':'Ошибка');}
async function logout(){await fetch('/api/logout',{method:'POST'});location.reload();}
init();
</script></body></html>"""

if __name__ == "__main__":
    init_db()
    from waitress import serve
    serve(app, host="0.0.0.0", port=PORT, threads=8)
