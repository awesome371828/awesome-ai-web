# ================= AWESOME AI — НАДЁЖНАЯ ВЕРСИЯ (рабочие кнопки) =================
import os, re, uuid, hashlib, io, base64, json
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import quote
import requests
from flask import Flask, request, jsonify, session, send_file

# ============ КЛЮЧИ ============
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
app.secret_key = "awesome-ai-robust-buttons"
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
        if not session.get("uid"):
            return jsonify({"ok": False, "error": "Войдите"}), 401
        return f(*a, **k)
    return wrap

def owner_required(f):
    @wraps(f)
    def wrap(*a, **k):
        if str(session.get("uid")) != OWNER_TGID:
            return jsonify({"ok": False, "error": "Только владелец"}), 403
        return f(*a, **k)
    return wrap

# ---- Supabase helpers ----
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
            if datetime.fromisoformat(str(until).replace("Z", "+00:00")) < datetime.now(timezone.utc):
                premium = False
        except Exception: pass
    role = "owner" if owner else ("admin" if admin else ("premium" if premium else "user"))
    return {"premium": premium, "until": str(until or ""), "admin": admin, "role": role, "owner": owner}

def _insert(t, d):
    try:
        r = _http.post(f"{SB_URL}/rest/v1/{t}", json=d, headers={**SB_HDR, "Prefer": "return=minimal"}, timeout=6)
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

def reset_all():
    try:
        rows = _select("users", "select=user_id") or []
        for u in rows:
            if u.get("user_id") is not None:
                _delete("users", f"user_id=eq.{u.get('user_id')}")
    except Exception: pass

# ============ АВТОРИЗАЦИЯ ============
@app.route("/api/register", methods=["POST"])
def register():
    try:
        d = request.get_json(silent=True) or {}
        name = str(d.get("name", "")).strip(); tgid = str(d.get("telegram_id", "")).strip(); pwd = str(d.get("password", "")).strip()
        if not name or not tgid or not pwd: return jsonify({"ok": False, "error": "Заполни все поля"})
        if len(pwd) < 4: return jsonify({"ok": False, "error": "Пароль минимум 4 символа"})
        if get_user(tgid): return jsonify({"ok": False, "error": "Такой аккаунт уже есть"})
        cols = get_users_columns()
        payload = {"user_id": int(tgid) if str(tgid).isdigit() else tgid, "username": name, "password": hash_pw(pwd)}
        if "premium" in cols: payload["premium"] = 0
        if "is_admin" in cols: payload["is_admin"] = 0
        if "is_owner" in cols: payload["is_owner"] = 1 if str(tgid) == OWNER_TGID else 0
        if not _insert("users", payload): return jsonify({"ok": False, "error": "Регистрация не удалась. Проверь RLS"})
        session.permanent = True; session["uid"] = tgid; session["name"] = name
        return jsonify({"ok": True, "uid": tgid, "name": name})
    except Exception as e:
        return jsonify({"ok": False, "error": "Ошибка: " + str(e)})

@app.route("/api/login", methods=["POST"])
def login():
    try:
        d = request.get_json(silent=True) or {}
        tgid = str(d.get("telegram_id", "")).strip(); pwd = str(d.get("password", "")).strip()
        if not tgid or not pwd: return jsonify({"ok": False, "error": "Заполни оба поля"})
        u = get_user(tgid)
        if not u: return jsonify({"ok": False, "error": "Аккаунт не найден — зарегистрируйся"})
        db_pw = u.get("password") or u.get("pwd") or ""
        if str(tgid) == OWNER_TGID and (not db_pw or db_pw == hash_pw(OWNER_PASS)): db_pw = hash_pw(OWNER_PASS)
        if hash_pw(pwd) != db_pw: return jsonify({"ok": False, "error": "Неверный пароль"})
        session.permanent = True; session["uid"] = tgid; session["name"] = u.get("username") or tgid
        return jsonify({"ok": True, "uid": tgid, "name": session["name"]})
    except Exception as e:
        return jsonify({"ok": False, "error": "Ошибка: " + str(e)})

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear(); return jsonify({"ok": True})

@app.route("/api/me")
@login_required
def me():
    u = get_user(session["uid"])
    st = parse_status(u) if u else {"premium": False, "until": "", "admin": False, "role": "user", "owner": False}
    return jsonify({"ok": True, "uid": session["uid"], "name": session.get("name", ""), "status": st})

@app.route("/api/diag")
def diag():
    out = {}
    try:
        r = _http.get(f"{SB_URL}/rest/v1/users?select=*&limit=1", headers=SB_HDR, timeout=6)
        out["users_status"] = r.status_code; out["users_body"] = r.text[:600]
    except Exception as e:
        out["users_error"] = str(e)
    return jsonify(out)

# ============ ИИ ============
def quick_answers(text):
    t = text.lower().strip()
    if any(w in t for w in ["привет", "здравств", "хай", "hello", "ку"]):
        return "Привет! 👋 Я AWESOME AI. Умею: отвечать, считать, генерировать картинки, погоду, курсы валют, криптовалюты. Спрашивай!"
    if "погод" in t: return "Прогноз смотри на Яндекс.Погоде или Gismeteo ☁️"
    if "доллар" in t or "курс" in t or "валю" in t: return "Курсы валют — на ЦБ РФ (cbr.ru) 💱"
    if "битко" in t or "крипт" in t or "btc" in t: return "Цены на крипту — на CoinGecko или Binance 🪙"
    if "кто ты" in t or "ты кто" in t: return "Я AWESOME AI — умный помощник ✨"
    if "спасибо" in t: return "Всегда пожалуйста! 😊"
    if "пока" in t: return "Пока! Возвращайся 👋"
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
        r = _http.post("https://ngw.devices.sberbank.ru:9443/api/v2/oauth", data={"scope": "GIGACHAT_API_PERS"},
                       headers={"Authorization": "Basic " + GIGACHAT_AUTH_KEY, "RqUID": str(uuid.uuid4()),
                                "Content-Type": "application/x-www-form-urlencoded"}, timeout=6)
        tok = r.json().get("access_token")
        if tok:
            r = _http.post("https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
                           json={"model": "GigaChat", "messages": [{"role": "user", "content": msg}]},
                           headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"}, timeout=25)
            ans = r.json()["choices"][0]["message"]["content"]
            if ans and len(ans.strip()) > 1: return ans.strip()
    except Exception: pass
    try:
        r = _http.post("https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
                       json={"modelUri": f"gpt://{FOLDER_ID}/yandexgpt-lite",
                             "completionOptions": {"temperature": 0.6, "maxTokens": 500},
                             "messages": [{"role": "user", "text": msg}]},
                       headers={"Authorization": "Api-Key " + YANDEX_API_KEY, "Content-Type": "application/json"}, timeout=25)
        ans = r.json()["result"]["alternatives"][0]["message"]["text"]
        if ans and len(ans.strip()) > 1: return ans.strip()
    except Exception: pass
    return "Не удалось получить ответ от нейросети. Но я на связи! Спроси про погоду, курсы, крипту или математику."

# ============ ЧАТ ============
@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    d = request.get_json(silent=True) or {}
    chat_id = str(d.get("chat_id", "")); msg = str(d.get("message", "")).strip()
    if not msg: return jsonify({"ok": False, "error": "Пустое сообщение"})
    if not chat_id:
        chat_id = uuid.uuid4().hex[:10]
        _insert("chats_web", {"user_id": session["uid"], "chat_id": chat_id, "title": msg[:30]})
    _insert("messages_web", {"chat_id": chat_id, "role": "user", "content": msg})
    answer = smart_answer(msg)
    _insert("messages_web", {"chat_id": chat_id, "role": "assistant", "content": answer})
    return jsonify({"ok": True, "answer": answer, "chat_id": chat_id})

@app.route("/api/chats")
@login_required
def list_chats():
    rows = _select("chats_web", f"user_id=eq.{session['uid']}&select=*&order=id.desc") or []
    return jsonify({"ok": True, "chats": [{"id": r.get("chat_id"), "title": r.get("title"), "pinned": r.get("pinned", 0)} for r in rows]})

@app.route("/api/messages")
@login_required
def get_msgs():
    chat_id = request.args.get("chat_id", "")
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
    prompt = str((request.get_json(silent=True) or {}).get("prompt", "")).strip() or "abstract art"
    return jsonify({"ok": True, "url": f"https://image.pollinations.ai/prompt/{quote(prompt)}"})

@app.route("/api/share", methods=["POST"])
@login_required
def share():
    d = request.get_json(silent=True) or {}
    code = uuid.uuid4().hex[:8]
    _insert("shared_chats", {"share_code": code, "chat_id": str(d.get("chat_id", ""))})
    return jsonify({"ok": True, "url": "/s/" + code})

@app.route("/s/<code>")
def shared(code):
    rows = _select("shared_chats", f"share_code=eq.{code}&select=chat_id") or []
    if not rows: return "Чат не найден", 404
    msgs = _select("messages_web", f"chat_id=eq.{rows[0].get('chat_id')}&select=*&order=id.asc") or []
    html = "<html><body style='font-family:sans-serif;padding:20px;background:#0f172a;color:#e2e8f0'><h2>💬 Публичный чат</h2>"
    for r in msgs:
        color = "#6fd8c0" if r.get("role") == "user" else "#7b9cff"
        label = "Вы" if r.get("role") == "user" else "AI"
        html += f"<div style='margin:8px 0;padding:10px;border-radius:10px;background:#1e293b;border-left:4px solid {color}'><b>{label}:</b> {r.get('content')}</div>"
    html += "</body></html>"
    return html

@app.route("/api/export")
@login_required
def export_chat():
    chat_id = request.args.get("chat_id", "")
    rows = _select("messages_web", f"chat_id=eq.{chat_id}&select=*&order=id.asc") or []
    text = "\n\n".join(f"{'Вы' if r.get('role')=='user' else 'AI'}:\n{r.get('content')}" for r in rows)
    return send_file(io.BytesIO(text.encode("utf-8")), as_attachment=True, download_name="chat.txt", mimetype="text/plain")

@app.route("/api/profile")
@login_required
def profile():
    u = get_user(session["uid"]) or {}
    st = parse_status(u)
    return jsonify({"ok": True, "name": u.get("username", ""), "role": st["role"], "xp": u.get("xp", 0), "level": u.get("level", 1)})

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
    tgid = str(d.get("telegram_id", "")).strip(); newp = str(d.get("password", "")).strip()
    if not tgid or not newp: return jsonify({"ok": False, "error": "Нужны ID и пароль"})
    ok = _patch("users", f"user_id=eq.{tgid}", {"password": hash_pw(newp)})
    return jsonify({"ok": ok})

@app.route("/api/admin/delete_user", methods=["POST"])
@owner_required
def admin_delete_user():
    d = request.get_json(silent=True) or {}
    tgid = str(d.get("telegram_id", "")).strip()
    if not tgid or tgid == OWNER_TGID: return jsonify({"ok": False, "error": "Нельзя"})
    return jsonify({"ok": _delete("users", f"user_id=eq.{tgid}")})

@app.route("/api/admin/give_premium", methods=["POST"])
@owner_required
def admin_give_premium():
    d = request.get_json(silent=True) or {}
    tgid = str(d.get("telegram_id", "")).strip()
    if not tgid: return jsonify({"ok": False, "error": "Нужен ID"})
    until = datetime.now(timezone.utc) + timedelta(days=int(d.get("days", 0)), hours=int(d.get("hours", 0)), minutes=int(d.get("minutes", 0)))
    return jsonify({"ok": _patch("users", f"user_id=eq.{tgid}", {"premium": 1, "premium_expires": until.isoformat()})})

@app.route("/api/admin/remove_premium", methods=["POST"])
@owner_required
def admin_remove_premium():
    d = request.get_json(silent=True) or {}
    tgid = str(d.get("telegram_id", "")).strip()
    if not tgid: return jsonify({"ok": False, "error": "Нужен ID"})
    return jsonify({"ok": _patch("users", f"user_id=eq.{tgid}", {"premium": 0, "premium_expires": None})})

@app.route("/api/admin/set_admin", methods=["POST"])
@owner_required
def admin_set_admin():
    d = request.get_json(silent=True) or {}
    tgid = str(d.get("telegram_id", "")).strip()
    if not tgid: return jsonify({"ok": False, "error": "Нужен ID"})
    return jsonify({"ok": _patch("users", f"user_id=eq.{tgid}", {"is_admin": 1 if d.get("admin") else 0})})

@app.route("/api/admin/broadcast", methods=["POST"])
@owner_required
def admin_broadcast():
    d = request.get_json(silent=True) or {}
    text = str(d.get("text", "")).strip()
    if not text: return jsonify({"ok": False, "error": "Пустой текст"})
    rows = _select("users", "select=user_id") or []
    sent = 0
    for u in rows:
        tid = u.get("user_id")
        if not tid: continue
        try:
            _http.post(f"{BOT}/sendMessage", json={"chat_id": tid, "text": text}, timeout=5); sent += 1
        except Exception: pass
    return jsonify({"ok": True, "sent": sent})

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
.card{background:var(--card);border-radius:22px;padding:30px;width:100%;max-width:420px;box-shadow:0 20px 60px rgba(0,0,0,.5);text-align:center;margin:auto}
.wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.logo{font-size:32px;font-weight:800;background:linear-gradient(90deg,var(--ac1),var(--ac2));-webkit-background-clip:text;background-clip:text;color:transparent}
.sub{color:var(--muted);font-size:14px;margin:8px 0 20px}
input{width:100%;background:var(--bg);border:1.5px solid #334155;border-radius:14px;padding:13px 16px;color:#fff;font-size:15px;outline:none;margin-bottom:12px}
input:focus{border-color:var(--ac1)}
.btn{width:100%;background:linear-gradient(90deg,var(--ac1),var(--ac2));color:#fff;border:none;border-radius:14px;padding:13px;font-size:15px;font-weight:600;cursor:pointer;margin-top:6px}
.btn.ghost{background:#334155}
.err{color:#f87171;font-size:13px;margin-top:10px;min-height:18px}
.hint{color:#64748b;font-size:12px;margin-top:14px}
.diag{color:#6fd8c0;font-size:11px;margin-top:8px;cursor:pointer;text-decoration:underline}
#nameWrap{display:none}
</style></head><body>
<div class="wrap"><div class="card">
  <div class="logo">✨ AWESOME AI</div>
  <div class="sub" id="sub">Вход в аккаунт</div>
  <div id="nameWrap"><input id="authName" placeholder="Название (имя)"></div>
  <input id="authTg" placeholder="Telegram ID">
  <input id="authPass" type="password" placeholder="Пароль">
  <button class="btn" id="authBtn">Войти</button>
  <button class="btn ghost" id="toggleBtn">Нет аккаунта? Зарегистрироваться</button>
  <div class="err" id="err"></div>
  <div class="hint">AWESOME AI · вход по Telegram ID</div>
  <div class="diag" id="diagLink">🔍 Диагностика</div>
</div></div>

<script>
(function(){
  var isReg=false;
  var nameWrap=document.getElementById('nameWrap');
  var authBtn=document.getElementById('authBtn');
  var toggleBtn=document.getElementById('toggleBtn');
  var err=document.getElementById('err');
  var sub=document.getElementById('sub');

  function resetBtn(){ authBtn.textContent = isReg ? 'Создать аккаунт' : 'Войти'; authBtn.disabled=false; }

  toggleBtn.addEventListener('click', function(){
    isReg=!isReg;
    nameWrap.style.display = isReg ? 'block' : 'none';
    authBtn.textContent = isReg ? 'Создать аккаунт' : 'Войти';
    sub.textContent = isReg ? 'Регистрация' : 'Вход в аккаунт';
    toggleBtn.textContent = isReg ? 'Уже есть аккаунт? Войти' : 'Нет аккаунта? Зарегистрироваться';
  });

  document.getElementById('diagLink').addEventListener('click', async function(){
    err.textContent='⏳ Загрузка диагностики...';
    try{
      var r=await fetch('/api/diag'); var d=await r.json();
      err.innerHTML='<b>Диагностика:</b><br>'+JSON.stringify(d);
    }catch(e){ err.textContent='Ошибка диагностики'; }
  });

  authBtn.addEventListener('click', async function(){
    var name=document.getElementById('authName').value.trim();
    var tg=document.getElementById('authTg').value.trim();
    var pw=document.getElementById('authPass').value.trim();
    err.textContent='';
    if(!tg||!pw){ err.textContent='Заполни Telegram ID и пароль'; return; }
    if(isReg&&!name){ err.textContent='Заполни название'; return; }
    authBtn.textContent='⏳ Проверка...'; authBtn.disabled=true;
    try{
      var url=isReg?'/api/register':'/api/login';
      var body=isReg?{name:name,telegram_id:tg,password:pw}:{telegram_id:tg,password:pw};
      var r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      var d=await r.json();
      if(!d.ok){ err.textContent=d.error||'Ошибка'; resetBtn(); return; }
      err.textContent='✅ Вход выполнен! Перезагружаю...';
      setTimeout(function(){ location.href='/'; }, 600);
    }catch(e){
      err.textContent='Ошибка сети: '+e.message; resetBtn();
    }
  });

  // проверка сессии при загрузке
  fetch('/api/me').then(function(r){ return r.json(); }).then(function(d){
    if(d.ok){ window.location.href='/'; }
  }).catch(function(){});
})();
</script></body></html>"""

if __name__ == "__main__":
    reset_all()  # сброс аккаунтов при старте
    try:
        from waitress import serve
        serve(app, host="0.0.0.0", port=PORT, threads=8)
    except ImportError:
        app.run(host="0.0.0.0", port=PORT)
