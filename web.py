# ============ AWESOME AI — ПОЛНАЯ КОПИЯ DeepSeek ============
import os, re, uuid, hashlib, io, json
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import quote
import requests
from flask import Flask, request, jsonify, session, send_file

PORT = int(os.environ.get("PORT", "8080"))
SESSION_TTL = 30 * 24 * 3600

YANDEX_API_KEY = "AQVNyfn82epL9dy8C_kftzeypq6eF9lFd6SZnFzV"
FOLDER_ID = "b1g4aq87c7j61c6g3i5l"
GIGACHAT_AUTH_KEY = "MDFhMDBkNmEtMmExNC03M2JkLWFlZmMtOTQ0OWVlOTc5M2U1OmE1ZWJhM2NlLTQwYjAtNDZlYi1iMmY2LTE3OTFmYzhhYTQ2MA=="
SUPABASE_URL = "https://lprxbmshmuucymkgaqwk.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxwcnhibXNobXV1Y3lta2dhcXdrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY3NDk0MjgsImV4cCI6MjEwMjMyNTQyOH0.Ie9jSH5RMxeOq8aU-Dv6MXlojWMUTOLE723Hdg6heZU"
TELEGRAM_TOKEN = "8336209662:AAHdhYXhqWA-LtthwgydDSRU7A6A0ceC-HY"
OWNER_TGID = "6652898792"
OWNER_PASS = "qawsedrf2346"
OWNER_NAME = "Сергей (владелец)"

app = Flask(__name__)
app.secret_key = "awesome-ai-full-deepseek"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(seconds=SESSION_TTL)
_http = requests.Session()
BOT = "https://api.telegram.org/bot" + TELEGRAM_TOKEN
SB_URL = SUPABASE_URL.rstrip("/")
SB_HDR = {"apikey": SUPABASE_ANON_KEY, "Authorization": "Bearer " + SUPABASE_ANON_KEY,
          "Content-Type": "application/json"}

def hash_pw(p): return hashlib.sha256(p.encode()).hexdigest()

def login_required(f):
    @wraps(f)
    def wrap(*a, **k):
        if not session.get("uid"): return jsonify({"ok": False, "error": "Войдите"}), 401
        return f(*a, **k)
    return wrap

def owner_required(f):
    @wraps(f)
    def wrap(*a, **k):
        if str(session.get("uid")) != OWNER_TGID: return jsonify({"ok": False, "error": "Только владелец"}), 403
        return f(*a, **k)
    return wrap

# --- Supabase helpers ---
def get_users_columns():
    try:
        r = _http.get(f"{SB_URL}/rest/v1/users?select=*&limit=1", headers=SB_HDR, timeout=6)
        if r.status_code == 200 and r.json(): return list(r.json()[0].keys())
    except Exception: pass
    return []

def get_user(tgid):
    try:
        r = _http.get(f"{SB_URL}/rest/v1/users?user_id=eq.{tgid}&select=*", headers=SB_HDR, timeout=6)
        if r.status_code == 200 and r.json(): return r.json()[0]
    except Exception: pass
    return None

def parse_status(u):
    owner = bool(u.get("is_owner")) or str(u.get("user_id")) == OWNER_TGID
    admin = bool(u.get("is_admin")) or bool(u.get("admin"))
    premium = bool(u.get("premium")) or bool(u.get("is_premium"))
    until = u.get("premium_expires") or u.get("premium_until")
    if until:
        try:
            if datetime.fromisoformat(str(until).replace("Z","+00:00")) < datetime.now(timezone.utc): premium = False
        except Exception: pass
    role = "owner" if owner else ("admin" if admin else ("premium" if premium else "user"))
    return {"premium": premium, "until": str(until or ""), "admin": admin, "role": role, "owner": owner}

def _insert(t, d):
    try:
        r = _http.post(f"{SB_URL}/rest/v1/{t}", json=d, headers={**SB_HDR, "Prefer":"return=minimal"}, timeout=6)
        return r.status_code in (200, 201, 204)
    except Exception: return False

def _select(t, q):
    try:
        r = _http.get(f"{SB_URL}/rest/v1/{t}?{q}", headers=SB_HDR, timeout=6)
        if r.status_code == 200 and r.json(): return r.json()
    except Exception: pass
    return None

def _patch(t, fq, d):
    try:
        r = _http.patch(f"{SB_URL}/rest/v1/{t}?{fq}", json=d, headers=SB_HDR, timeout=6)
        return r.status_code in (200, 204)
    except Exception: return False

def _delete(t, fq):
    try:
        r = _http.delete(f"{SB_URL}/rest/v1/{t}?{fq}", headers=SB_HDR, timeout=6)
        return r.status_code in (200, 204)
    except Exception: return False

# ============ АВТОРИЗАЦИЯ ============
@app.route("/api/register", methods=["POST"])
def register():
    try:
        d = request.get_json(silent=True) or {}
        name = str(d.get("name","")).strip(); tgid = str(d.get("telegram_id","")).strip(); pwd = str(d.get("password","")).strip()
        if not name or not tgid or not pwd: return jsonify({"ok": False, "error": "Заполни все поля"})
        if len(pwd) < 4: return jsonify({"ok": False, "error": "Пароль минимум 4 символа"})
        if get_user(tgid): return jsonify({"ok": False, "error": "Такой аккаунт уже есть"})
        cols = get_users_columns()
        payload = {"user_id": int(tgid) if str(tgid).isdigit() else tgid, "username": name, "password": hash_pw(pwd)}
        if "premium" in cols: payload["premium"] = 0
        if "is_admin" in cols: payload["is_admin"] = 0
        if "is_owner" in cols: payload["is_owner"] = 1 if str(tgid)==OWNER_TGID else 0
        if not _insert("users", payload): return jsonify({"ok": False, "error": "Регистрация не удалась (RLS?)"})
        session.permanent=True; session["uid"]=tgid; session["name"]=name
        return jsonify({"ok": True, "uid": tgid, "name": name})
    except Exception as e:
        return jsonify({"ok": False, "error": "Ошибка: "+str(e)})

@app.route("/api/login", methods=["POST"])
def login():
    try:
        d = request.get_json(silent=True) or {}
        tgid = str(d.get("telegram_id","")).strip(); pwd = str(d.get("password","")).strip()
        if not tgid or not pwd: return jsonify({"ok": False, "error": "Заполни оба поля"})
        u = get_user(tgid)
        if not u: return jsonify({"ok": False, "error": "Аккаунт не найден"})
        db_pw = u.get("password") or u.get("pwd") or ""
        if str(tgid)==OWNER_TGID and (not db_pw or db_pw==hash_pw(OWNER_PASS)): db_pw = hash_pw(OWNER_PASS)
        if hash_pw(pwd) != db_pw: return jsonify({"ok": False, "error": "Неверный пароль"})
        session.permanent=True; session["uid"]=tgid; session["name"]=u.get("username") or tgid
        return jsonify({"ok": True, "uid": tgid, "name": session["name"]})
    except Exception as e:
        return jsonify({"ok": False, "error": "Ошибка: "+str(e)})

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear(); return jsonify({"ok": True})

@app.route("/api/me")
@login_required
def me():
    u = get_user(session["uid"])
    st = parse_status(u) if u else {"premium":False,"until":"","admin":False,"role":"user","owner":False}
    return jsonify({"ok": True, "uid": session["uid"], "name": session.get("name",""), "status": st})

@app.route("/api/diag")
def diag():
    out = {}
    try:
        r = _http.get(f"{SB_URL}/rest/v1/users?select=*&limit=1", headers=SB_HDR, timeout=6)
        out["users_status"] = r.status_code; out["users_body"] = r.text[:400]
    except Exception as e: out["users_error"] = str(e)
    # проверим таблицы чата
    try:
        r = _http.get(f"{SB_URL}/rest/v1/chats_web?select=*&limit=1", headers=SB_HDR, timeout=6)
        out["chats_status"] = r.status_code
    except Exception as e: out["chats_error"] = str(e)
    try:
        r = _http.get(f"{SB_URL}/rest/v1/messages_web?select=*&limit=1", headers=SB_HDR, timeout=6)
        out["messages_status"] = r.status_code
    except Exception as e: out["messages_error"] = str(e)
    return jsonify(out)

# ============ ИИ (DeepSeek-стиль, быстрый) ============
def quick_answers(text):
    t = text.lower().strip()
    if any(w in t for w in ["привет","здравств","хай","hello","ку"]):
        return "Привет! 👋 Я AWESOME AI. Умею: отвечать, считать, генерировать картинки, погоду, курсы валют, криптовалюты, стихи, идеи. Спрашивай!"
    if "погод" in t: return "Прогноз смотри на Яндекс.Погоде или Gismeteo ☁️"
    if "доллар" in t or "курс" in t or "валю" in t: return "Курсы валют — на ЦБ РФ (cbr.ru) 💱"
    if "битко" in t or "крипт" in t or "btc" in t: return "Цены на крипту — на CoinGecko или Binance 🪙"
    if "кто ты" in t or "ты кто" in t or "что умеешь" in t: return "Я AWESOME AI ✨ — аналог DeepSeek/ChatGPT/Grok. Отвечаю, считаю, рисую, помогаю с идеями."
    if "спасибо" in t: return "Всегда пожалуйста! 😊"
    if "пока" in t: return "Пока! Возвращайся 👋"
    if "стих" in t: return "Вот тебе: ✨\nВ мире тёплых слов и света,\nЯ всегда с тобой в ответе. 💫"
    if re.search(r"[0-9]+\s*[+\-*/]\s*[0-9]+", t):
        try:
            res = eval(re.search(r"[0-9+\-*/().\s]+", t).group().strip())
            return f"Результат: {res} 🧮"
        except Exception: return "Напиши, например: 2+2*3"
    return None

def smart_answer(msg):
    q = quick_answers(msg)
    if q: return q
    try:
        r = _http.post("https://ngw.devices.sberbank.ru:9443/api/v2/oauth", data={"scope":"GIGACHAT_API_PERS"},
                       headers={"Authorization":"Basic "+GIGACHAT_AUTH_KEY,"RqUID":str(uuid.uuid4()),
                                "Content-Type":"application/x-www-form-urlencoded"}, timeout=6)
        tok = r.json().get("access_token")
        if tok:
            r = _http.post("https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
                           json={"model":"GigaChat","messages":[{"role":"user","content":msg}]},
                           headers={"Authorization":"Bearer "+tok,"Content-Type":"application/json"}, timeout=25)
            ans = r.json()["choices"][0]["message"]["content"]
            if ans and len(ans.strip())>1: return ans.strip()
    except Exception: pass
    try:
        r = _http.post("https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
                       json={"modelUri":f"gpt://{FOLDER_ID}/yandexgpt-lite",
                             "completionOptions":{"temperature":0.6,"maxTokens":700},
                             "messages":[{"role":"user","text":msg}]},
                       headers={"Authorization":"Api-Key "+YANDEX_API_KEY,"Content-Type":"application/json"}, timeout=25)
        ans = r.json()["result"]["alternatives"][0]["message"]["text"]
        if ans and len(ans.strip())>1: return ans.strip()
    except Exception: pass
    return "Не удалось получить ответ от нейросети. Но я на связи! Спроси про погоду, курсы, математику или попроси стих."

# ============ ЧАТ ============
@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    d = request.get_json(silent=True) or {}
    chat_id = str(d.get("chat_id","")); msg = str(d.get("message","")).strip()
    if not msg: return jsonify({"ok": False, "error": "Пустое сообщение"})
    try:
        if not chat_id:
            chat_id = uuid.uuid4().hex[:10]
            _insert("chats_web", {"user_id": session["uid"], "chat_id": chat_id, "title": msg[:30]})
        _insert("messages_web", {"chat_id": chat_id, "role":"user", "content": msg})
        ans = smart_answer(msg)
        _insert("messages_web", {"chat_id": chat_id, "role":"assistant", "content": ans})
        return jsonify({"ok": True, "answer": ans, "chat_id": chat_id})
    except Exception as e:
        # если таблицы чата нет — всё равно отвечаем (без сохранения)
        return jsonify({"ok": True, "answer": smart_answer(msg), "chat_id": chat_id or uuid.uuid4().hex[:10], "warn": str(e)})

@app.route("/api/chats")
@login_required
def list_chats():
    rows = _select("chats_web", f"user_id=eq.{session['uid']}&select=*&order=id.desc") or []
    return jsonify({"ok": True, "chats": [{"id": r.get("chat_id"), "title": r.get("title"), "pinned": r.get("pinned",0)} for r in rows]})

@app.route("/api/messages")
@login_required
def get_msgs():
    chat_id = request.args.get("chat_id","")
    rows = _select("messages_web", f"chat_id=eq.{chat_id}&select=*&order=id.asc") or []
    return jsonify({"ok": True, "messages": [{"role": r.get("role"), "content": r.get("content"), "image": r.get("image")} for r in rows]})

@app.route("/api/delete_chat", methods=["POST"])
@login_required
def delete_chat():
    d = request.get_json(silent=True) or {}
    _delete("chats_web", f"chat_id=eq.{d.get('chat_id')}")
    _delete("messages_web", f"chat_id=eq.{d.get('chat_id')}")
    return jsonify({"ok": True})

@app.route("/api/image", methods=["POST"])
@login_required
def gen_image():
    prompt = str((request.get_json(silent=True) or {}).get("prompt","")).strip() or "abstract art"
    return jsonify({"ok": True, "url": f"https://image.pollinations.ai/prompt/{quote(prompt)}"})

@app.route("/api/export")
@login_required
def export_chat():
    chat_id = request.args.get("chat_id","")
    rows = _select("messages_web", f"chat_id=eq.{chat_id}&select=*&order=id.asc") or []
    text = "\n\n".join(f"{'Вы' if r.get('role')=='user' else 'AI'}:\n{r.get('content')}" for r in rows)
    return send_file(io.BytesIO(text.encode("utf-8")), as_attachment=True, download_name="chat.txt", mimetype="text/plain")

@app.route("/api/profile")
@login_required
def profile():
    u = get_user(session["uid"]) or {}
    st = parse_status(u)
    return jsonify({"ok": True, "name": u.get("username",""), "role": st["role"], "xp": u.get("xp",0), "level": u.get("level",1)})

# ============ АДМИН ============
@app.route("/api/admin/users")
@owner_required
def admin_users():
    rows = _select("users", "select=*&order=joined_at.desc&limit=1000") or []
    res = []
    for r in rows:
        res.append({"id": r.get("user_id"), "name": r.get("username"),
                    "role": "owner" if r.get("is_owner") else ("admin" if r.get("is_admin") else "user"),
                    "premium": bool(r.get("premium"))})
    return jsonify({"ok": True, "users": res})

@app.route("/api/admin/stats")
@owner_required
def admin_stats():
    users = _select("users", "select=user_id") or []
    msgs = _select("messages_web", "select=id") or []
    return jsonify({"ok": True, "users": len(users), "messages": len(msgs)})

@app.route("/api/admin/reset_password", methods=["POST"])
@owner_required
def admin_reset_password():
    d = request.get_json(silent=True) or {}
    tgid = str(d.get("telegram_id","")).strip(); newp = str(d.get("password","")).strip()
    if not tgid or not newp: return jsonify({"ok": False, "error": "Нужны ID и пароль"})
    return jsonify({"ok": _patch("users", f"user_id=eq.{tgid}", {"password": hash_pw(newp)})})

@app.route("/api/admin/delete_user", methods=["POST"])
@owner_required
def admin_delete_user():
    d = request.get_json(silent=True) or {}
    tgid = str(d.get("telegram_id","")).strip()
    if not tgid or tgid==OWNER_TGID: return jsonify({"ok": False, "error": "Нельзя"})
    return jsonify({"ok": _delete("users", f"user_id=eq.{tgid}")})

@app.route("/api/admin/give_premium", methods=["POST"])
@owner_required
def admin_give_premium():
    d = request.get_json(silent=True) or {}
    tgid = str(d.get("telegram_id","")).strip()
    if not tgid: return jsonify({"ok": False, "error": "Нужен ID"})
    until = datetime.now(timezone.utc) + timedelta(days=int(d.get("days",0)), hours=int(d.get("hours",0)), minutes=int(d.get("minutes",0)))
    return jsonify({"ok": _patch("users", f"user_id=eq.{tgid}", {"premium":1, "premium_expires": until.isoformat()})})

@app.route("/api/admin/remove_premium", methods=["POST"])
@owner_required
def admin_remove_premium():
    d = request.get_json(silent=True) or {}
    tgid = str(d.get("telegram_id","")).strip()
    if not tgid: return jsonify({"ok": False, "error": "Нужен ID"})
    return jsonify({"ok": _patch("users", f"user_id=eq.{tgid}", {"premium":0, "premium_expires": None})})

@app.route("/api/admin/set_admin", methods=["POST"])
@owner_required
def admin_set_admin():
    d = request.get_json(silent=True) or {}
    tgid = str(d.get("telegram_id","")).strip()
    if not tgid: return jsonify({"ok": False, "error": "Нужен ID"})
    return jsonify({"ok": _patch("users", f"user_id=eq.{tgid}", {"is_admin": 1 if d.get("admin") else 0})})

@app.route("/api/admin/broadcast", methods=["POST"])
@owner_required
def admin_broadcast():
    d = request.get_json(silent=True) or {}
    text = str(d.get("text","")).strip()
    if not text: return jsonify({"ok": False, "error": "Пустой текст"})
    rows = _select("users", "select=user_id") or []
    sent = 0
    for u in rows:
        tid = u.get("user_id")
        if tid:
            try:
                _http.post(f"{BOT}/sendMessage", json={"chat_id": tid, "text": text}, timeout=5); sent += 1
            except Exception: pass
    return jsonify({"ok": True, "sent": sent})

# ============ ГЛАВНАЯ (всё на одной странице, надёжные onclick) ============
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
@keyframes glow{0%,100%{box-shadow:0 0 0 rgba(127,156,255,0)}50%{box-shadow:0 0 26px rgba(127,156,255,.25)}}
.card{background:var(--card);border-radius:22px;padding:34px 30px;width:100%;max-width:420px;box-shadow:0 20px 60px rgba(0,0,0,.5);text-align:center;margin:auto;animation:fadeUp .5s ease}
.wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.logo{font-size:34px;font-weight:800;background:linear-gradient(90deg,var(--ac1),var(--ac2));-webkit-background-clip:text;background-clip:text;color:transparent;animation:float 3s ease-in-out infinite}
.sub{color:var(--muted);font-size:14px;margin:8px 0 20px}
input,textarea{width:100%;background:var(--bg);border:1.5px solid #334155;border-radius:14px;padding:13px 16px;color:#fff;font-size:15px;outline:none;margin-bottom:12px}
input:focus,textarea:focus{border-color:var(--ac1)}
textarea{resize:vertical;min-height:70px}
.btn{width:100%;background:linear-gradient(90deg,var(--ac1),var(--ac2));color:#fff;border:none;border-radius:14px;padding:13px;font-size:15px;font-weight:600;cursor:pointer;margin-top:6px;animation:glow 3s ease-in-out infinite}
.btn:hover{transform:translateY(-2px)}
.btn.ghost{background:#334155;animation:none}
.btn.small{width:auto;padding:9px 16px;font-size:13px;display:inline-block;margin:4px}
.btn.danger{background:#ef4444}
.err{color:#f87171;font-size:13px;margin-top:10px;min-height:18px;word-break:break-word;text-align:left}
.hint{color:#64748b;font-size:12px;margin-top:14px}
.diag{color:#6fd8c0;font-size:11px;margin-top:8px;cursor:pointer;text-decoration:underline}
#nameWrap{display:none}
#app{display:none;max-width:950px;margin:0 auto;padding:14px}
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.tab{background:#1e293b;border:none;color:var(--text);padding:8px 16px;border-radius:20px;cursor:pointer}
.tab.active{background:linear-gradient(90deg,var(--ac1),var(--ac2));color:#fff}
.chatbox{max-height:50vh;overflow-y:auto;margin-bottom:10px;padding:10px;border:1px solid #334155;border-radius:16px;background:rgba(15,23,42,.5)}
.msg{animation:fadeUp .3s ease;padding:12px;border-radius:12px;margin:6px 0;max-width:85%;white-space:pre-wrap}
.msg.user{background:linear-gradient(90deg,var(--ac1),var(--ac2));margin-left:auto;color:#fff}
.msg.ai{background:#334155;margin-right:auto}
.msg .tools{margin-top:8px;display:flex;gap:6px;flex-wrap:wrap}
.chat-item{background:#1e293b;border-radius:12px;padding:12px;margin:8px 0;cursor:pointer}
.admin-row{display:flex;gap:8px;align-items:center;margin:6px 0;flex-wrap:wrap;background:#0f172a;border-radius:10px;padding:8px}
.admin-row span{flex:1;font-size:13px}
#adminTab{display:none}
#topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
</style></head><body>

<!-- ВХОД -->
<div class="wrap" id="authScreen">
  <div class="card">
    <div class="logo">✨ AWESOME AI</div>
    <div class="sub" id="sub">Вход в аккаунт</div>
    <div id="nameWrap"><input id="authName" placeholder="Название (имя)"></div>
    <input id="authTg" placeholder="Telegram ID">
    <input id="authPass" type="password" placeholder="Пароль">
    <button class="btn" id="authBtn" onclick="doAuth()">Войти</button>
    <button class="btn ghost" onclick="toggleMode()">Нет аккаунта? Зарегистрироваться</button>
    <div class="err" id="err"></div>
    <div class="hint">AWESOME AI · вход по Telegram ID</div>
    <div class="diag" onclick="doDiag()">🔍 Диагностика</div>
  </div>
</div>

<!-- ПРИЛОЖЕНИЕ -->
<div id="app">
  <div id="topbar"><span class="logo" style="font-size:22px">✨ AWESOME AI</span><span id="userInfo"></span></div>
  <div class="tabs">
    <button class="tab active" id="tabChat" onclick="showTab('chat')">💬 Чат</button>
    <button class="tab" onclick="showTab('chats')">📁 Чаты</button>
    <button class="tab" onclick="showTab('img')">🎨 Картинки</button>
    <button class="tab" id="adminTab" onclick="showTab('admin')">⚙️ Админ</button>
    <button class="tab" onclick="doLogout()">🚪 Выйти</button>
  </div>
  <div id="view-chat">
    <div class="chatbox" id="chatBox"><div class="msg ai">Привет! 👋 Напиши мне что-нибудь.</div></div>
    <textarea id="chatInput" placeholder="Сообщение..." onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendChat();}"></textarea>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button class="btn" style="width:auto" onclick="sendChat()">✈ Отправить</button>
      <button class="btn ghost small" onclick="newChat()">🆕 Новый</button>
      <button class="btn ghost small" onclick="shareChat()">🔗 Поделиться</button>
      <button class="btn ghost small" onclick="exportChat()">📥 Экспорт</button>
    </div>
  </div>
  <div id="view-chats" style="display:none"><div id="chatList"></div></div>
  <div id="view-img" style="display:none">
    <input id="imgPrompt" placeholder="Опишите картинку">
    <button class="btn" onclick="genImg()">🎨 Сгенерировать</button>
    <div id="imgResult" style="margin-top:12px;text-align:center"></div>
  </div>
  <div id="view-admin" style="display:none">
    <h3>⚙️ Панель владельца</h3>
    <div id="adminStats" style="margin:8px 0;color:var(--muted)"></div>
    <div id="adminList"></div>
  </div>
</div>

<script>
var isReg=false, curChat='';
function esc(s){return (s||'').replace(/</g,'&lt;').replace(/\n/g,'<br>');}
function showErr(m){document.getElementById('err').innerHTML=m;}
function toggleMode(){
  isReg=!isReg;
  document.getElementById('nameWrap').style.display=isReg?'block':'none';
  document.getElementById('authBtn').textContent=isReg?'Создать аккаунт':'Войти';
  document.getElementById('sub').textContent=isReg?'Регистрация':'Вход в аккаунт';
}
async function doDiag(){
  showErr('⏳ Загрузка диагностики...');
  try{var r=await fetch('/api/diag');var d=await r.json();showErr('<b>Диагностика:</b><br>'+JSON.stringify(d));}
  catch(e){showErr('Ошибка: '+e.message);}
}
async function doAuth(){
  var name=document.getElementById('authName').value.trim();
  var tg=document.getElementById('authTg').value.trim();
  var pw=document.getElementById('authPass').value.trim();
  showErr('');
  if(!tg||!pw){showErr('Заполни Telegram ID и пароль');return;}
  if(isReg&&!name){showErr('Заполни название');return;}
  var b=document.getElementById('authBtn');b.textContent='⏳...';b.disabled=true;
  try{
    var url=isReg?'/api/register':'/api/login';
    var body=isReg?{name:name,telegram_id:tg,password:pw}:{telegram_id:tg,password:pw};
    var r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    var d=await r.json();
    if(!d.ok){showErr(d.error||'Ошибка');b.textContent=isReg?'Создать аккаунт':'Войти';b.disabled=false;return;}
    loadSession();
  }catch(e){showErr('Ошибка сети: '+e.message);b.textContent=isReg?'Создать аккаунт':'Войти';b.disabled=false;}
}
function showTab(n){
  document.getElementById('view-chat').style.display=n==='chat'?'block':'none';
  document.getElementById('view-chats').style.display=n==='chats'?'block':'none';
  document.getElementById('view-img').style.display=n==='img'?'block':'none';
  document.getElementById('view-admin').style.display=n==='admin'?'block':'none';
  if(n==='chats')loadChats();
  if(n==='admin')loadAdmin();
}
async function sendChat(){
  var msg=document.getElementById('chatInput').value.trim(); if(!msg)return;
  var box=document.getElementById('chatBox');
  box.innerHTML+='<div class="msg user">'+esc(msg)+'</div>';
  document.getElementById('chatInput').value='';
  var tid='t'+Date.now();
  box.innerHTML+='<div class="msg ai" id="'+tid+'">⏳ Думаю...</div>'; box.scrollTop=box.scrollHeight;
  try{
    var r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({chat_id:curChat,message:msg})});
    var d=await r.json();
    var el=document.getElementById(tid);
    if(el)el.innerHTML=esc(d.answer||'Ошибка')+'<div class="tools"><button class="btn small" onclick="copyMsg(this)">📋</button><button class="btn small" onclick="speakMsg(this)">🔊</button></div>';
    curChat=d.chat_id;
  }catch(e){var el2=document.getElementById(tid);if(el2)el2.textContent='Ошибка сети: '+e.message;}
}
function copyMsg(b){var t=b.parentElement.parentElement.innerText.replace('📋','').replace('🔊','').trim();navigator.clipboard.writeText(t);b.textContent='✅';setTimeout(function(){b.textContent='📋';},1200);}
function speakMsg(b){var t=b.parentElement.parentElement.innerText.replace('📋','').replace('🔊','').trim();var u=new SpeechSynthesisUtterance(t);u.lang='ru-RU';speechSynthesis.cancel();speechSynthesis.speak(u);}
function newChat(){curChat='';document.getElementById('chatBox').innerHTML='<div class="msg ai">Привет! 👋</div>';}
async function loadChats(){
  try{
    var r=await fetch('/api/chats');var d=await r.json();var el=document.getElementById('chatList');el.innerHTML='';
    var list=d.chats||[];
    if(!list.length){el.innerHTML='<p style="color:var(--muted)">Чатов нет.</p>';return;}
    list.forEach(function(c){var div=document.createElement('div');div.className='chat-item';
      div.textContent=(c.pinned?'📌 ':'')+c.title;
      div.onclick=function(){curChat=c.id;showTab('chat');loadMsgs();};el.appendChild(div);});
  }catch(e){}
}
async function loadMsgs(){
  try{
    var r=await fetch('/api/messages?chat_id='+curChat);var d=await r.json();var box=document.getElementById('chatBox');
    box.innerHTML='';d.messages.forEach(function(m){box.innerHTML+='<div class="msg '+(m.role==='user'?'user':'ai')+'">'+esc(m.content)+'</div>';});
  }catch(e){}
}
async function genImg(){
  var p=document.getElementById('imgPrompt').value.trim();if(!p)return;
  var r=await fetch('/api/image',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:p})});
  var d=await r.json();
  document.getElementById('imgResult').innerHTML=d.ok?'<img src="'+d.url+'" style="max-width:100%;border-radius:12px">':'Ошибка';
}
async function shareChat(){
  if(!curChat){alert('Сначала напиши сообщение');return;}
  var code=curChat.slice(0,8);
  navigator.clipboard.writeText(location.origin+'/s/'+code);
  alert('Ссылка скопирована');
}
function exportChat(){if(!curChat){alert('Сначала напиши сообщение');return;}window.location='/api/export?chat_id='+curChat;}
async function loadAdmin(){
  try{
    var s=await (await fetch('/api/admin/stats')).json();
    document.getElementById('adminStats').textContent='Пользователей: '+s.users+' · Сообщений: '+s.messages;
    var r=await fetch('/api/admin/users');var d=await r.json();var el=document.getElementById('adminList');el.innerHTML='';
    (d.users||[]).forEach(function(u){var row=document.createElement('div');row.className='admin-row';
      row.innerHTML='<span>'+esc(u.name)+' (ID: '+u.id+') — '+u.role+(u.premium?' 💎':'')+'</span>';el.appendChild(row);});
  }catch(e){}
}
async function doLogout(){await fetch('/api/logout',{method:'POST'});location.reload();}
async function loadSession(){
  try{
    var r=await fetch('/api/me');var d=await r.json();
    if(d.ok){
      document.getElementById('authScreen').style.display='none';
      document.getElementById('app').style.display='block';
      document.getElementById('userInfo').textContent=d.name+' · '+d.status.role+(d.status.premium?' 💎':'');
      if(d.status.owner)document.getElementById('adminTab').style.display='block';
      return;
    }
  }catch(e){}
  document.getElementById('authScreen').style.display='flex';
}
loadSession();
</script></body></html>"""

if __name__ == "__main__":
    try:
        from waitress import serve
        serve(app, host="0.0.0.0", port=PORT, threads=8)
    except ImportError:
        app.run(host="0.0.0.0", port=PORT)
