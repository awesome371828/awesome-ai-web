# ================= AWESOME AI — АВТОРИЗАЦИЯ ЧЕРЕЗ SUPABASE (надёжно) =================
# Все аккаунты и пароли хранятся в Supabase (таблица users — та же, что у бота).
# Вход НЕ зависит от локального PostgreSQL, поэтому «Временная ошибка» больше не появится.
import os, re, uuid, hashlib, io
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import quote

import requests
import psycopg2
from flask import Flask, request, jsonify, session, send_file

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
app.secret_key = "awesome-ai-supabase-auth-final"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(seconds=SESSION_TTL)
_http = requests.Session()
BOT = "https://api.telegram.org/bot" + TELEGRAM_TOKEN

# ============ SUPABASE (ГЛАВНЫЙ ИСТОЧНИК — все аккаунты и пароли) ============
SB_HDR = {"apikey": SUPABASE_ANON_KEY, "Authorization": "Bearer " + SUPABASE_ANON_KEY}
SB_URL = SUPABASE_URL.rstrip("/")

def hash_pw(p):
    return hashlib.sha256(p.encode()).hexdigest()

def sb_get_user(tgid):
    """Ищет пользователя в Supabase по telegram_id."""
    try:
        r = _http.get(
            f"{SB_URL}/rest/v1/users?telegram_id=eq.{tgid}&select=*",
            headers=SB_HDR, timeout=6)
        if r.status_code == 200 and r.json():
            return r.json()[0]
    except Exception:
        pass
    return None

def sb_get_all_users():
    """Все пользователи из Supabase (для админки)."""
    try:
        r = _http.get(f"{SB_URL}/rest/v1/users?select=*&order=created_at.desc&limit=1000",
                      headers=SB_HDR, timeout=6)
        if r.status_code == 200 and r.json():
            return r.json()
    except Exception:
        pass
    return []

def sb_create_user(tgid, name, pwd_hash):
    """Создаёт нового пользователя в Supabase с паролем."""
    try:
        r = _http.post(f"{SB_URL}/rest/v1/users",
                       json={"telegram_id": str(tgid), "username": name,
                             "password": pwd_hash, "role": "user",
                             "premium": False, "admin": False},
                       headers={**SB_HDR, "Content-Type": "application/json",
                                "Prefer": "return=minimal"}, timeout=6)
        # 201 = создан, 200 = ok (upsert), 409 = конфликт
        return r.status_code in (200, 201, 204)
    except Exception:
        return False

def sb_update_user(tgid, fields):
    try:
        r = _http.patch(f"{SB_URL}/rest/v1/users?telegram_id=eq.{tgid}",
                        json=fields,
                        headers={**SB_HDR, "Content-Type": "application/json"}, timeout=6)
        return r.status_code in (200, 204)
    except Exception:
        return False

def sb_get_status(tgid):
    """Premium/админ/владелец из Supabase (бот = источник истины)."""
    d = sb_get_user(tgid) or {}
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

# ============ АВТОРИЗАЦИЯ (ЛОГИН / РЕГИСТРАЦИЯ ЧЕРЕЗ SUPABASE) ============
def login_required(f):
    @wraps(f)
    def wrap(*a, **k):
        if not session.get("uid"):
            return jsonify({"ok": False, "error": "Войдите в аккаунт"}), 401
        return f(*a, **k)
    return wrap

def owner_required(f):
    @wraps(f)
    def wrap(*a, **k):
        if str(session.get("uid")) != OWNER_TGID:
            return jsonify({"ok": False, "error": "Доступ только владельцу"}), 403
        return f(*a, **k)
    return wrap

@app.route("/api/login", methods=["POST"])
def login():
    try:
        d = request.get_json(silent=True) or {}
        tgid = str(d.get("telegram_id", "")).strip()
        pwd = str(d.get("password", "")).strip()
        if not tgid or not pwd:
            return jsonify({"ok": False, "error": "Заполни оба поля"})
        u = sb_get_user(tgid)
        if not u:
            return jsonify({"ok": False, "error": "Аккаунт не найден — зарегистрируйтесь"})
        db_pw = u.get("password") or u.get("pwd") or ""
        # владелец может войти, даже если в Supabase нет записи его пароля
        if str(tgid) == OWNER_TGID and (not db_pw or db_pw == hash_pw(OWNER_PASS)):
            db_pw = hash_pw(OWNER_PASS)
        if hash_pw(pwd) != db_pw:
            return jsonify({"ok": False, "error": "Неверный пароль"})
        session.permanent = True
        session["uid"] = tgid
        session["name"] = u.get("username") or u.get("name") or tgid
        return jsonify({"ok": True, "uid": tgid, "name": session["name"]})
    except Exception as e:
        return jsonify({"ok": False, "error": "Сервер временно недоступен. Попробуйте ещё раз."})

@app.route("/api/register", methods=["POST"])
def register():
    try:
        d = request.get_json(silent=True) or {}
        name = str(d.get("name", "")).strip()
        tgid = str(d.get("telegram_id", "")).strip()
        pwd = str(d.get("password", "")).strip()
        if not name or not tgid or not pwd:
            return jsonify({"ok": False, "error": "Заполни все поля"})
        if len(pwd) < 4:
            return jsonify({"ok": False, "error": "Пароль минимум 4 символа"})
        if sb_get_user(tgid):
            return jsonify({"ok": False, "error": "Аккаунт с таким Telegram ID уже существует"})
        ok = sb_create_user(tgid, name, hash_pw(pwd))
        if not ok:
            return jsonify({"ok": False, "error": "Не удалось создать аккаунт. Возможно, регистрация ограничена на хостинге."})
        session.permanent = True
        session["uid"] = tgid
        session["name"] = name
        return jsonify({"ok": True, "uid": tgid, "name": name})
    except Exception:
        return jsonify({"ok": False, "error": "Сервер временно недоступен. Попробуйте ещё раз."})

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})

@app.route("/api/me")
@login_required
def me():
    st = sb_get_status(session["uid"])
    return jsonify({"ok": True, "uid": session["uid"],
                    "name": session.get("name", ""), "status": st})

@app.route("/api/force_owner", methods=["POST"])
def force_owner():
    d = request.get_json(silent=True) or {}
    if str(d.get("telegram_id", "")) != OWNER_TGID:
        return jsonify({"ok": False, "error": "Недоступно"})
    u = sb_get_user(OWNER_TGID)
    if u:
        sb_update_user(OWNER_TGID, {"password": hash_pw(OWNER_PASS), "role": "owner",
                                    "username": OWNER_NAME})
    else:
        sb_create_user(OWNER_TGID, OWNER_NAME, hash_pw(OWNER_PASS))
    return jsonify({"ok": True, "message": "Пароль владельца сброшен"})

@app.route("/api/diag")
def diag():
    """Диагностика — показывает, работает ли Supabase (вход зависит от него)."""
    out = {"supabase_users_table": "?"}
    try:
        r = _http.get(f"{SB_URL}/rest/v1/users?select=telegram_id&limit=1",
                      headers=SB_HDR, timeout=6)
        out["supabase"] = f"status {r.status_code}"
        out["sample"] = r.json() if r.status_code == 200 else r.text[:200]
    except Exception as e:
        out["supabase_error"] = str(e)
    # проверим, есть ли колонка password
    try:
        r = _http.get(f"{SB_URL}/rest/v1/users?select=password&limit=1",
                      headers=SB_HDR, timeout=6)
        out["password_column"] = f"status {r.status_code}"
    except Exception as e:
        out["password_column_error"] = str(e)
    return jsonify(out)

# ============ УМНЫЙ ОТВЕТ (быстрый, без ошибок) ============
def quick_answers(text):
    t = text.lower().strip()
    if any(w in t for w in ["привет", "здравств", "хай", "hello", "ку"]):
        return "Привет! 👋 Я AWESOME AI. Спрашивай что угодно — отвечу, посчитаю, помогу!"
    if "погод" in t:
        return "Точный прогноз смотри на Яндекс.Погоде или Gismeteo ☁️"
    if "доллар" in t or "курс" in t or "валю" in t:
        return "Актуальные курсы валют — на ЦБ РФ (cbr.ru) 💱"
    if "битко" in t or "крипт" in t or "btc" in t:
        return "Цены на криптовалюту — на CoinGecko или Binance 🪙"
    if "кто ты" in t or "ты кто" in t:
        return "Я AWESOME AI — умный помощник ✨"
    if "спасибо" in t or "благодар" in t:
        return "Всегда пожалуйста! 😊"
    if "пока" in t or "до свидания" in t:
        return "Пока! Возвращайся 👋"
    if re.search(r"[0-9]+\s*[+\-*/]\s*[0-9]+", t):
        try:
            res = eval(re.search(r"[0-9+\-*/().\s]+", t).group().strip())
            return f"Результат: {res} 🧮"
        except Exception:
            return "Напиши, например: 2+2*3"
    return None

def smart_answer(msg):
    q = quick_answers(msg)
    if q: return q
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
    return "Не удалось получить ответ от нейросети. Но я на связи! Спроси про погоду, курсы, крипту или математику."

# ============ ЧАТ (сохраняется в локальную БД, если доступна; иначе просто отвечает) ============
def get_conn():
    return psycopg2.connect(DATABASE_URL)

@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    d = request.get_json(silent=True) or {}
    chat_id = str(d.get("chat_id", ""))
    msg = str(d.get("message", "")).strip()
    if not msg:
        return jsonify({"ok": False, "error": "Пустое сообщение"})
    answer = smart_answer(msg)
    try:
        conn = get_conn(); cur = conn.cursor()
        if not chat_id:
            chat_id = uuid.uuid4().hex[:10]
            cur.execute("INSERT INTO chats_web (user_id, chat_id, title) VALUES (%s,%s,%s)",
                        (session["uid"], chat_id, msg[:30]))
        cur.execute("INSERT INTO messages_web (chat_id, role, content) VALUES (%s,%s,%s)",
                    (chat_id, "user", msg))
        cur.execute("INSERT INTO messages_web (chat_id, role, content) VALUES (%s,%s,%s)",
                    (chat_id, "assistant", answer))
        conn.commit(); cur.close(); conn.close()
    except Exception:
        pass
    return jsonify({"ok": True, "answer": answer, "chat_id": chat_id or uuid.uuid4().hex[:10]})

@app.route("/api/chats")
@login_required
def list_chats():
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT chat_id, title, pinned FROM chats_web WHERE user_id=%s ORDER BY pinned DESC, id DESC",
                    (session["uid"],))
        rows = cur.fetchall(); cur.close(); conn.close()
        return jsonify({"ok": True, "chats": [{"id": r[0], "title": r[1], "pinned": r[2]} for r in rows]})
    except Exception:
        return jsonify({"ok": True, "chats": []})

@app.route("/api/messages")
@login_required
def get_msgs():
    chat_id = request.args.get("chat_id", "")
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT role, content FROM messages_web WHERE chat_id=%s ORDER BY id ASC", (chat_id,))
        rows = cur.fetchall(); cur.close(); conn.close()
        return jsonify({"ok": True, "messages": [{"role": r[0], "content": r[1]} for r in rows]})
    except Exception:
        return jsonify({"ok": True, "messages": []})

@app.route("/api/image", methods=["POST"])
@login_required
def gen_image():
    d = request.get_json(silent=True) or {}
    prompt = str(d.get("prompt", "")).strip() or "abstract art"
    try:
        return jsonify({"ok": True, "url": f"https://image.pollinations.ai/prompt/{quote(prompt)}"})
    except Exception:
        return jsonify({"ok": False, "error": "Ошибка генерации"})

# ============ АДМИН (только владелец) ============
@app.route("/api/admin/users")
@owner_required
def admin_users():
    users = sb_get_all_users()
    return jsonify({"ok": True,
                    "users": [{"id": u.get("telegram_id"), "name": u.get("username") or u.get("name"),
                               "role": u.get("role") or ("owner" if str(u.get("telegram_id"))==OWNER_TGID else "user"),
                               "premium": u.get("premium", False)} for u in users]})

@app.route("/api/admin/reset_password", methods=["POST"])
@owner_required
def admin_reset_password():
    d = request.get_json(silent=True) or {}
    tgid = str(d.get("telegram_id", "")).strip()
    newp = str(d.get("password", "")).strip()
    if not tgid or not newp:
        return jsonify({"ok": False, "error": "Нужны Telegram-ID и новый пароль"})
    ok = sb_update_user(tgid, {"password": hash_pw(newp)})
    return jsonify({"ok": ok or "Аккаунт не найден"})

@app.route("/api/admin/delete_user", methods=["POST"])
@owner_required
def admin_delete_user():
    d = request.get_json(silent=True) or {}
    tgid = str(d.get("telegram_id", "")).strip()
    if not tgid or tgid == OWNER_TGID:
        return jsonify({"ok": False, "error": "Нельзя удалить"})
    try:
        r = _http.delete(f"{SB_URL}/rest/v1/users?telegram_id=eq.{tgid}",
                         headers=SB_HDR, timeout=6)
        return jsonify({"ok": r.status_code in (200, 204)})
    except Exception:
        return jsonify({"ok": False, "error": "Ошибка удаления"})

@app.route("/api/admin/give_premium", methods=["POST"])
@owner_required
def admin_give_premium():
    d = request.get_json(silent=True) or {}
    tgid = str(d.get("telegram_id", "")).strip()
    if not tgid:
        return jsonify({"ok": False, "error": "Нужен Telegram-ID"})
    until = datetime.now(timezone.utc) + timedelta(
        days=int(d.get("days", 0)), hours=int(d.get("hours", 0)), minutes=int(d.get("minutes", 0)))
    sb_update_user(tgid, {"premium": True, "premium_until": until.isoformat()})
    return jsonify({"ok": True})

@app.route("/api/admin/remove_premium", methods=["POST"])
@owner_required
def admin_remove_premium():
    d = request.get_json(silent=True) or {}
    tgid = str(d.get("telegram_id", "")).strip()
    if not tgid:
        return jsonify({"ok": False, "error": "Нужен Telegram-ID"})
    sb_update_user(tgid, {"premium": False, "premium_until": None})
    return jsonify({"ok": True})

# ============ ГЛАВНАЯ (логин + регистрация, красиво, по центру) ============
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
.btn.ghost{background:#334155;animation:none;margin-top:10px}
.err{color:#f87171;font-size:13px;margin-top:10px;min-height:18px}
.hint{color:#64748b;font-size:12px;margin-top:16px}
.name-field{transition:opacity .25s,height .25s}
</style></head><body>
<div class="wrap"><div class="card">
  <div class="logo">✨ AWESOME AI</div>
  <div class="sub" id="sub">Вход в аккаунт</div>
  <div class="name-field" id="nameWrap">
    <input id="authName" placeholder="Название (имя)">
  </div>
  <input id="authTg" placeholder="Telegram ID">
  <input id="authPass" type="password" placeholder="Пароль">
  <button class="btn" id="authBtn" onclick="doAuth()">Войти</button>
  <button class="btn ghost" onclick="toggleMode()">Нет аккаунта? Зарегистрироваться</button>
  <div class="err" id="err"></div>
  <div class="hint">AWESOME AI · вход по Telegram ID</div>
</div></div>
<script>
let isReg=false;
function toggleMode(){
 isReg=!isReg;
 document.getElementById('nameWrap').style.display=isReg?'block':'none';
 document.getElementById('authBtn').textContent=isReg?'Создать аккаунт':'Войти';
 document.getElementById('sub').textContent=isReg?'Регистрация':'Вход в аккаунт';
 document.querySelector('.ghost').textContent=isReg?'Уже есть аккаунт? Войти':'Нет аккаунта? Зарегистрироваться';
}
async function doAuth(){
 const name=document.getElementById('authName').value.trim();
 const tg=document.getElementById('authTg').value.trim();
 const pw=document.getElementById('authPass').value.trim();
 document.getElementById('err').textContent='';
 if(!tg||!pw){document.getElementById('err').textContent='Заполни Telegram ID и пароль';return;}
 if(isReg&&!name){document.getElementById('err').textContent='Заполни название';return;}
 const b=document.getElementById('authBtn');b.textContent='⏳ Проверка...';b.disabled=true;
 const url=isReg?'/api/register':'/api/login';
 const body=isReg?{name,telegram_id:tg,password:pw}:{telegram_id:tg,password:pw};
 try{
  const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  let d;try{d=await r.json();}catch(e){document.getElementById('err').textContent='Сервер не отвечает. Ещё раз.';reset();return;}
  if(!d.ok){document.getElementById('err').textContent=d.error||'Ошибка';reset();return;}
  document.body.innerHTML='<div style="display:flex;align-items:center;justify-content:center;height:100vh;font-size:22px;color:var(--text)">✅ Вход выполнен! Обновляем...</div>';
  location.reload();
 }catch(e){document.getElementById('err').textContent='Ошибка сети.';reset();}
}
function reset(){const b=document.getElementById('authBtn');b.textContent=isReg?'Создать аккаунт':'Войти';b.disabled=false;}
document.getElementById('nameWrap').style.display='none';
</script></body></html>"""

if __name__ == "__main__":
    try:
        from waitress import serve
        serve(app, host="0.0.0.0", port=PORT, threads=8)
    except ImportError:
        app.run(host="0.0.0.0", port=PORT)
