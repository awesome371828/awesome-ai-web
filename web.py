# ================= AWESOME AI — ПОЛНАЯ РАБОЧАЯ ВЕРСИЯ =================
# Все данные в Supabase. Код сам определяет структуру таблицы users.
import os, re, uuid, hashlib, io, base64, json
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import quote
import requests
from flask import Flask, request, jsonify, session, send_file, redirect

# ============ КЛЮЧИ И НАСТРОЙКИ ============
PORT = int(os.environ.get("PORT", "8080"))
SESSION_TTL = 30 * 24 * 3600  # автовход 30 дней

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
app.secret_key = "awesome-ai-self-healing-v1"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(seconds=SESSION_TTL)
_http = requests.Session()
BOT = "https://api.telegram.org/bot" + TELEGRAM_TOKEN

SB_URL = SUPABASE_URL.rstrip("/")
SB_HDR = {"apikey": SUPABASE_ANON_KEY, "Authorization": "Bearer " + SUPABASE_ANON_KEY,
          "Content-Type": "application/json"}

def hash_pw(p):
    return hashlib.sha256(p.encode()).hexdigest()

# ============ SUPABASE: САМО-ОПРЕДЕЛЕНИЕ СТРУКТУРЫ users ============
_ID_COLS = ["telegram_id", "user_id", "tg_id", "tgid", "chat_id"]

def _guess_id_col(cols):
    """Находит колонку с Telegram ID в списке колонок таблицы."""
    for c in _ID_COLS:
        if c in cols:
            return c
    return None

def get_users_columns():
    """Определяет реальные колонки таблицы users."""
    try:
        r = _http.get(f"{SB_URL}/rest/v1/users?select=*&limit=1", headers=SB_HDR, timeout=6)
        if r.status_code == 200 and r.json():
            return list(r.json()[0].keys())
    except Exception:
        pass
    return []

def find_user_by_tgid(tgid):
    """Ищет пользователя, пробуя все возможные колонки ID."""
    cols = get_users_columns()
    for col in _ID_COLS:
        if col in cols:
            try:
                r = _http.get(f"{SB_URL}/rest/v1/users?{col}=eq.{tgid}&select=*",
                              headers=SB_HDR, timeout=6)
                if r.status_code == 200 and r.json():
                    return r.json()[0], col
            except Exception:
                pass
    return None, None

def get_user_col(tgid):
    """Возвращает (пользователь, колонка_id)."""
    return find_user_by_tgid(tgid)

# ============ РЕГИСТРАЦИЯ / ВХОД (само-адаптация под таблицу) ============
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
        u, idcol = get_user_col(tgid)
        if u:
            return jsonify({"ok": False, "error": "Аккаунт с таким Telegram ID уже существует"})
        cols = get_users_columns()
        if not cols:
            return jsonify({"ok": False, "error": "Не удалось получить таблицу users. Проверь RLS-политики."})
        idcol = _guess_id_col(cols) or "user_id"
        payload = {idcol: str(tgid), "username": name, "password": hash_pw(pwd),
                   "role": "user"}
        if "premium" in cols: payload["premium"] = False
        if "admin" in cols: payload["admin"] = False
        r = _http.post(f"{SB_URL}/rest/v1/users", json=payload,
                       headers={**SB_HDR, "Prefer": "return=minimal"}, timeout=6)
        if r.status_code not in (200, 201, 204):
            return jsonify({"ok": False, "error": f"Регистрация не удалась (статус {r.status_code}). Проверь RLS: {r.text[:150]}"})
        session.permanent = True; session["uid"] = tgid; session["name"] = name
        return jsonify({"ok": True, "uid": tgid, "name": name})
    except Exception as e:
        return jsonify({"ok": False, "error": "Ошибка сервера: " + str(e)})

@app.route("/api/login", methods=["POST"])
def login():
    try:
        d = request.get_json(silent=True) or {}
        tgid = str(d.get("telegram_id", "")).strip()
        pwd = str(d.get("password", "")).strip()
        if not tgid or not pwd:
            return jsonify({"ok": False, "error": "Заполни оба поля"})
        u, idcol = get_user_col(tgid)
        if not u:
            return jsonify({"ok": False, "error": "Аккаунт не найден — зарегистрируйтесь"})
        db_pw = u.get("password") or u.get("pwd") or ""
        if str(tgid) == OWNER_TGID and (not db_pw or db_pw == hash_pw(OWNER_PASS)):
            db_pw = hash_pw(OWNER_PASS)
        if hash_pw(pwd) != db_pw:
            return jsonify({"ok": False, "error": "Неверный пароль"})
        session.permanent = True
        session["uid"] = tgid
        session["name"] = u.get("username") or u.get("name") or tgid
        return jsonify({"ok": True, "uid": tgid, "name": session["name"]})
    except Exception as e:
        return jsonify({"ok": False, "error": "Ошибка сервера: " + str(e)})

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})

@app.route("/api/me")
@login_required
def me():
    u, _ = get_user_col(session["uid"])
    u = u or {}
    premium = bool(u.get("premium", False) or u.get("is_premium", False))
    until = u.get("premium_until")
    if isinstance(until, str):
        try:
            if datetime.fromisoformat(until.replace("Z", "+00:00")) < datetime.now(timezone.utc):
                premium = False
        except Exception: pass
    admin = bool(u.get("admin", False) or u.get("is_admin", False))
    role = "owner" if str(session["uid"]) == OWNER_TGID else ("admin" if admin else ("premium" if premium else "user"))
    return jsonify({"ok": True, "uid": session["uid"], "name": session.get("name", ""),
                    "status": {"premium": premium, "admin": admin, "role": role,
                               "owner": str(session["uid"]) == OWNER_TGID, "until": str(until or "")}})

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

@app.route("/api/force_owner", methods=["POST"])
def force_owner():
    d = request.get_json(silent=True) or {}
    if str(d.get("telegram_id", "")) != OWNER_TGID:
        return jsonify({"ok": False, "error": "Недоступно"})
    u, idcol = get_user_col(OWNER_TGID)
    if u:
        r = _http.patch(f"{SB_URL}/rest/v1/users?{idcol}=eq.{OWNER_TGID}",
                        json={"password": hash_pw(OWNER_PASS), "role": "owner", "username": OWNER_NAME},
                        headers=SB_HDR, timeout=6)
    else:
        cols = get_users_columns()
        idcol = _guess_id_col(cols) or "user_id"
        r = _http.post(f"{SB_URL}/rest/v1/users",
                       json={idcol: OWNER_TGID, "username": OWNER_NAME,
                             "password": hash_pw(OWNER_PASS), "role": "owner",
                             "premium": True, "admin": True},
                       headers={**SB_HDR, "Prefer": "return=minimal"}, timeout=6)
    return jsonify({"ok": True, "message": "Пароль владельца сброшен"})

# ============ ДИАГНОСТИКА (встроена прямо в сайт) ============
@app.route("/api/diag")
def diag():
    out = {}
    try:
        r = _http.get(f"{SB_URL}/rest/v1/users?select=*&limit=1", headers=SB_HDR, timeout=6)
        out["users_status"] = r.status_code
        out["users_body"] = r.text[:600]
    except Exception as e:
        out["users_error"] = str(e)
    return jsonify(out)

# ============ ЧАТ (в Supabase) ============
def _insert(table, data):
    try:
        r = _http.post(f"{SB_URL}/rest/v1/{table}", json=data,
                       headers={**SB_HDR, "Prefer": "return=minimal"}, timeout=6)
        return r.status_code in (200, 201, 204)
    except Exception:
        return False

def _select(table, query):
    try:
        r = _http.get(f"{SB_URL}/rest/v1/{table}?{query}", headers=SB_HDR, timeout=6)
        if r.status_code == 200 and r.json():
            return r.json()
    except Exception:
        pass
    return None

@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    d = request.get_json(silent=True) or {}
    chat_id = str(d.get("chat_id", ""))
    msg = str(d.get("message", "")).strip()
    if not msg:
        return jsonify({"ok": False, "error": "Пустое сообщение"})
    answer = smart_answer(msg)
    if not chat_id:
        chat_id = uuid.uuid4().hex[:10]
        _insert("chats_web", {"user_id": session["uid"], "chat_id": chat_id, "title": msg[:30]})
    _insert("messages_web", {"chat_id": chat_id, "role": "user", "content": msg})
    _insert("messages_web", {"chat_id": chat_id, "role": "assistant", "content": answer})
    return jsonify({"ok": True, "answer": answer, "chat_id": chat_id})

@app.route("/api/chats")
@login_required
def list_chats():
    rows = _select("chats_web", f"user_id=eq.{session['uid']}&select=*&order=id.desc") or []
    return jsonify({"ok": True, "chats": [{"id": r.get("chat_id"), "title": r.get("title"),
                                           "pinned": r.get("pinned", 0)} for r in rows]})

@app.route("/api/messages")
@login_required
def get_msgs():
    chat_id = request.args.get("chat_id", "")
    rows = _select("messages_web", f"chat_id=eq.{chat_id}&select=*&order=id.asc") or []
    return jsonify({"ok": True, "messages": [{"role": r.get("role"), "content": r.get("content"),
                                              "image": r.get("image")} for r in rows]})

@app.route("/api/image", methods=["POST"])
@login_required
def gen_image():
    prompt = str((request.get_json(silent=True) or {}).get("prompt", "")).strip() or "abstract art"
    try:
        return jsonify({"ok": True, "url": f"https://image.pollinations.ai/prompt/{quote(prompt)}"})
    except Exception:
        return jsonify({"ok": False, "error": "Ошибка"})

@app.route("/api/export")
@login_required
def export_chat():
    chat_id = request.args.get("chat_id", "")
    rows = _select("messages_web", f"chat_id=eq.{chat_id}&select=*&order=id.asc") or []
    text = "\n\n".join(f"{'Вы' if r.get('role')=='user' else 'AI'}:\n{r.get('content')}" for r in rows)
    buf = io.BytesIO(text.encode("utf-8"))
    return send_file(buf, as_attachment=True, download_name="chat.txt", mimetype="text/plain")

# ============ АДМИН (владелец) ============
@app.route("/api/admin/users")
@owner_required
def admin_users():
    rows = _select("users", "select=*&order=created_at.desc&limit=1000") or []
    return jsonify({"ok": True, "users": [{"id": r.get(rcol) if (rcol := _guess_id_col(list(r.keys()))) else r.get("user_id"),
                                           "name": r.get("username") or r.get("name"),
                                           "role": r.get("role", "user"),
                                           "premium": r.get("premium", False)} for r in rows]})

@app.route("/api/admin/reset_password", methods=["POST"])
@owner_required
def admin_reset_password():
    d = request.get_json(silent=True) or {}
    tgid = str(d.get("telegram_id", "")).strip()
    newp = str(d.get("password", "")).strip()
    if not tgid or not newp:
        return jsonify({"ok": False, "error": "Нужны ID и пароль"})
    u, idcol = get_user_col(tgid)
    if not u:
        return jsonify({"ok": False, "error": "Аккаунт не найден"})
    r = _http.patch(f"{SB_URL}/rest/v1/users?{idcol}=eq.{tgid}",
                    json={"password": hash_pw(newp)}, headers=SB_HDR, timeout=6)
    return jsonify({"ok": r.status_code in (200, 204)})

@app.route("/api/admin/delete_user", methods=["POST"])
@owner_required
def admin_delete_user():
    d = request.get_json(silent=True) or {}
    tgid = str(d.get("telegram_id", "")).strip()
    if not tgid or tgid == OWNER_TGID:
        return jsonify({"ok": False, "error": "Нельзя удалить"})
    u, idcol = get_user_col(tgid)
    if not u:
        return jsonify({"ok": False, "error": "Аккаунт не найден"})
    r = _http.delete(f"{SB_URL}/rest/v1/users?{idcol}=eq.{tgid}", headers=SB_HDR, timeout=6)
    return jsonify({"ok": r.status_code in (200, 204)})

@app.route("/api/admin/give_premium", methods=["POST"])
@owner_required
def admin_give_premium():
    d = request.get_json(silent=True) or {}
    tgid = str(d.get("telegram_id", "")).strip()
    if not tgid:
        return jsonify({"ok": False, "error": "Нужен Telegram-ID"})
    u, idcol = get_user_col(tgid)
    if not u:
        return jsonify({"ok": False, "error": "Аккаунт не найден"})
    until = datetime.now(timezone.utc) + timedelta(days=int(d.get("days", 0)),
                                                   hours=int(d.get("hours", 0)),
                                                   minutes=int(d.get("minutes", 0)))
    r = _http.patch(f"{SB_URL}/rest/v1/users?{idcol}=eq.{tgid}",
                    json={"premium": True, "premium_until": until.isoformat()},
                    headers=SB_HDR, timeout=6)
    return jsonify({"ok": r.status_code in (200, 204)})

@app.route("/api/admin/remove_premium", methods=["POST"])
@owner_required
def admin_remove_premium():
    d = request.get_json(silent=True) or {}
    tgid = str(d.get("telegram_id", "")).strip()
    if not tgid:
        return jsonify({"ok": False, "error": "Нужен Telegram-ID"})
    u, idcol = get_user_col(tgid)
    if not u:
        return jsonify({"ok": False, "error": "Аккаунт не найден"})
    r = _http.patch(f"{SB_URL}/rest/v1/users?{idcol}=eq.{tgid}",
                    json={"premium": False, "premium_until": None}, headers=SB_HDR, timeout=6)
    return jsonify({"ok": r.status_code in (200, 204)})

@app.route("/api/admin/set_admin", methods=["POST"])
@owner_required
def admin_set_admin():
    d = request.get_json(silent=True) or {}
    tgid = str(d.get("telegram_id", "")).strip()
    if not tgid:
        return jsonify({"ok": False, "error": "Нужен Telegram-ID"})
    u, idcol = get_user_col(tgid)
    if not u:
        return jsonify({"ok": False, "error": "Аккаунт не найден"})
    r = _http.patch(f"{SB_URL}/rest/v1/users?{idcol}=eq.{tgid}",
                    json={"admin": bool(d.get("admin"))}, headers=SB_HDR, timeout=6)
    return jsonify({"ok": r.status_code in (200, 204)})

@app.route("/api/admin/broadcast", methods=["POST"])
@owner_required
def admin_broadcast():
    d = request.get_json(silent=True) or {}
    text = str(d.get("text", "")).strip()
    if not text:
        return jsonify({"ok": False, "error": "Пустой текст"})
    rows = _select("users", "select=*") or []
    sent = 0
    idcol = _guess_id_col(list(rows[0].keys())) if rows else "user_id"
    for u in rows:
        tid = u.get(idcol) or u.get("telegram_id")
        if not tid: continue
        try:
            _http.post(f"{BOT}/sendMessage", json={"chat_id": tid, "text": text}, timeout=5)
            sent += 1
        except Exception: pass
    return jsonify({"ok": True, "sent": sent})

# ============ УМНЫЙ ОТВЕТ ============
def quick_answers(text):
    t = text.lower().strip()
    if any(w in t for w in ["привет", "здравств", "хай", "hello", "ку"]):
        return "Привет! 👋 Я AWESOME AI. Умею: отвечать, считать, генерировать картинки, погоду, курсы валют, криптовалюты. Спрашивай!"
    if "погод" in t: return "Точный прогноз смотри на Яндекс.Погоде или Gismeteo ☁️"
    if "доллар" in t or "курс" in t or "валю" in t: return "Актуальные курсы валют — на ЦБ РФ (cbr.ru) 💱"
    if "битко" in t or "крипт" in t or "btc" in t: return "Цены на криптовалюту — на CoinGecko или Binance 🪙"
    if "кто ты" in t or "ты кто" in t: return "Я AWESOME AI — умный помощник ✨"
    if "спасибо" in t or "благодар" in t: return "Всегда пожалуйста! 😊"
    if "пока" in t or "до свидания" in t: return "Пока! Возвращайся 👋"
    if "праздник" in t or "какой сегодня день" in t: return "Проверь календарь праздников на сегодня 📅"
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
.btn.ghost{background:#334155;animation:none;margin-top:10px}
.err{color:#f87171;font-size:13px;margin-top:10px;min-height:18px}
.hint{color:#64748b;font-size:12px;margin-top:16px}
.diag{color:#6fd8c0;font-size:11px;margin-top:8px;cursor:pointer;text-decoration:underline}
.name-field{display:none}
</style></head><body>
<div class="wrap"><div class="card">
  <div class="logo">✨ AWESOME AI</div>
  <div class="sub" id="sub">Вход в аккаунт</div>
  <div class="name-field" id="nameWrap"><input id="authName" placeholder="Название (имя)"></div>
  <input id="authTg" placeholder="Telegram ID">
  <input id="authPass" type="password" placeholder="Пароль">
  <button class="btn" id="authBtn" onclick="doAuth()">Войти</button>
  <button class="btn ghost" onclick="toggleMode()">Нет аккаунта? Зарегистрироваться</button>
  <div class="err" id="err"></div>
  <div class="hint">AWESOME AI · вход по Telegram ID</div>
  <div class="diag" onclick="showDiag()">🔍 Диагностика</div>
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
async function showDiag(){
 try{
  const r=await fetch('/api/diag');const d=await r.json();
  document.getElementById('err').innerHTML='<b>Диагностика:</b><br>'+JSON.stringify(d);
 }catch(e){document.getElementById('err').textContent='Не удалось получить диагностику';}
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
</script></body></html>"""

if __name__ == "__main__":
    # создаём владельца при старте, если таблица и RLS позволяют
    try:
        u, idcol = get_user_col(OWNER_TGID)
        if not u:
            cols = get_users_columns()
            idcol = _guess_id_col(cols) or "user_id"
            payload = {idcol: OWNER_TGID, "username": OWNER_NAME,
                       "password": hash_pw(OWNER_PASS), "role": "owner"}
            if "premium" in cols: payload["premium"] = True
            if "admin" in cols: payload["admin"] = True
            _http.post(f"{SB_URL}/rest/v1/users", json=payload,
                       headers={**SB_HDR, "Prefer": "return=minimal"}, timeout=6)
    except Exception:
        pass
    try:
        from waitress import serve
        serve(app, host="0.0.0.0", port=PORT, threads=8)
    except ImportError:
        app.run(host="0.0.0.0", port=PORT)
