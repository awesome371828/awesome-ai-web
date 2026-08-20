# ================= AWESOME AI — МАКСИМАЛЬНАЯ ПОЛНАЯ ВЕРСИЯ =================
# Полный ассистент-копия DeepSeek/ChatGPT/Grok/Gemini/Claude (все функции)
# Нейросети: GigaChat + YandexGPT + быстрые заготовки (fallback)
# При старте: ПОЛНЫЙ СБРОС аккаунтов (все удаляются) — зарегистрируйся заново
import os, re, uuid, hashlib, io, base64, json, time, threading
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import quote
import requests
from flask import Flask, request, jsonify, session, send_file

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
app.secret_key = "awesome-ai-mega-final"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(seconds=SESSION_TTL)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True
_http = requests.Session()
BOT = "https://api.telegram.org/bot" + TELEGRAM_TOKEN

SB_URL = SUPABASE_URL.rstrip("/")
SB_HDR = {"apikey": SUPABASE_ANON_KEY, "Authorization": "Bearer " + SUPABASE_ANON_KEY,
          "Content-Type": "application/json"}

def hash_pw(p):
    return hashlib.sha256(p.encode()).hexdigest()

# ============ ДЕКОРАТОРЫ ============
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

# ============ SUPABASE (адаптация под твою таблицу users) ============
def get_users_columns():
    try:
        r = _http.get(f"{SB_URL}/rest/v1/users?select=*&limit=1", headers=SB_HDR, timeout=6)
        if r.status_code == 200 and r.json():
            return list(r.json()[0].keys())
    except Exception:
        pass
    return []

def get_user_col(tgid):
    try:
        r = _http.get(f"{SB_URL}/rest/v1/users?user_id=eq.{tgid}&select=*",
                      headers=SB_HDR, timeout=6)
        if r.status_code == 200 and r.json():
            return r.json()[0], "user_id"
    except Exception:
        pass
    return None, None

def parse_status(u):
    owner = bool(u.get("is_owner")) or str(u.get("user_id")) == OWNER_TGID
    admin = bool(u.get("is_admin")) or bool(u.get("admin"))
    premium = bool(u.get("premium")) or bool(u.get("is_premium"))
    until = u.get("premium_expires") or u.get("premium_until")
    if until:
        try:
            s = str(until)
            if datetime.fromisoformat(s.replace("Z", "+00:00")) < datetime.now(timezone.utc):
                premium = False
        except Exception:
            pass
    role = "owner" if owner else ("admin" if admin else ("premium" if premium else "user"))
    return {"premium": premium, "until": str(until or ""), "admin": admin,
            "role": role, "owner": owner}

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

def _patch(table, filter_q, data):
    try:
        r = _http.patch(f"{SB_URL}/rest/v1/{table}?{filter_q}", json=data,
                        headers=SB_HDR, timeout=6)
        return r.status_code in (200, 204)
    except Exception:
        return False

def _delete(table, filter_q):
    try:
        r = _http.delete(f"{SB_URL}/rest/v1/{table}?{filter_q}", headers=SB_HDR, timeout=6)
        return r.status_code in (200, 204)
    except Exception:
        return False

def reset_all_accounts():
    """ПОЛНЫЙ СБРОС: удаляет ВСЕ аккаунты (включая владельца). Вызывается при старте."""
    try:
        rows = _select("users", "select=user_id") or []
        for u in rows:
            tid = u.get("user_id")
            if tid is not None:
                _delete("users", f"user_id=eq.{tid}")
        # очищаем чаты и сообщения
        try:
            rows2 = _select("chats_web", "select=chat_id") or []
            for c in rows2:
                cid = c.get("chat_id")
                if cid: _delete("chats_web", f"chat_id=eq.{cid}")
        except Exception: pass
        print("=== ПОЛНЫЙ СБРОС АККАУНТОВ ВЫПОЛНЕН ===")
    except Exception as e:
        print("reset warning:", e)

# ============ АВТОРИЗАЦИЯ ============
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
        u, _ = get_user_col(tgid)
        if u:
            return jsonify({"ok": False, "error": "Аккаунт с таким Telegram ID уже существует"})
        cols = get_users_columns()
        payload = {"user_id": int(tgid) if str(tgid).isdigit() else tgid,
                   "username": name, "password": hash_pw(pwd)}
        if "premium" in cols: payload["premium"] = 0
        if "is_admin" in cols: payload["is_admin"] = 0
        if "is_owner" in cols: payload["is_owner"] = 1 if str(tgid) == OWNER_TGID else 0
        if "xp" in cols: payload["xp"] = 0
        if "level" in cols: payload["level"] = 1
        r = _http.post(f"{SB_URL}/rest/v1/users", json=payload,
                       headers={**SB_HDR, "Prefer": "return=minimal"}, timeout=6)
        if r.status_code not in (200, 201, 204):
            return jsonify({"ok": False, "error": f"Регистрация не удалась (статус {r.status_code}): {r.text[:150]}"})
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
    st = parse_status(u) if u else {"premium": False, "until": "", "admin": False,
                                    "role": "user", "owner": False}
    return jsonify({"ok": True, "uid": session["uid"], "name": session.get("name", ""), "status": st})

@app.route("/api/force_owner", methods=["POST"])
def force_owner():
    d = request.get_json(silent=True) or {}
    if str(d.get("telegram_id", "")) != OWNER_TGID:
        return jsonify({"ok": False, "error": "Недоступно"})
    u, _ = get_user_col(OWNER_TGID)
    if u:
        _patch("users", f"user_id=eq.{OWNER_TGID}",
               {"password": hash_pw(OWNER_PASS), "username": OWNER_NAME,
                "is_owner": 1, "is_admin": 1, "premium": 1})
    else:
        cols = get_users_columns()
        payload = {"user_id": int(OWNER_TGID), "username": OWNER_NAME,
                   "password": hash_pw(OWNER_PASS)}
        if "is_owner" in cols: payload["is_owner"] = 1
        if "is_admin" in cols: payload["is_admin"] = 1
        if "premium" in cols: payload["premium"] = 1
        _insert("users", payload)
    return jsonify({"ok": True, "message": "Пароль владельца сброшен"})

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

# ============ УМНЫЙ ОТВЕТ (GigaChat + YandexGPT + заготовки) ============
def quick_answers(text):
    t = text.lower().strip()
    if any(w in t for w in ["привет", "здравств", "хай", "hello", "ку", "здарова"]):
        return "Привет! 👋 Я AWESOME AI — ассистент нового поколения, как DeepSeek/ChatGPT/Grok. Умею: общаться, считать, генерировать картинки, погоду, курсы валют, криптовалюты, праздники, придумывать идеи. Спрашивай!"
    if "погод" in t:
        m = re.search(r"в\s+([а-яё]+)", t)
        city = m.group(1) if m else ""
        return f"Прогноз погоды смотри на Яндекс.Погоде или Gismeteo ☁️{(' для '+city.capitalize()) if city else ''} (в этой сборке нет живого API погоды)"
    if "доллар" in t or "курс" in t or "валю" in t:
        return "Актуальные курсы валют — на ЦБ РФ (cbr.ru) или в твоём банке 💱"
    if "битко" in t or "крипт" in t or "btc" in t or "эфир" in t:
        return "Цены на криптовалюту — на CoinGecko или Binance 🪙"
    if "кто ты" in t or "ты кто" in t or "что умеешь" in t:
        return "Я AWESOME AI ✨ — аналог DeepSeek/ChatGPT/Grok/Gemini. Отвечаю на вопросы, считаю, генерирую картинки, помогаю с идеями и задачами."
    if "спасибо" in t or "благодар" in t:
        return "Всегда пожалуйста! 😊 Обращайся ещё!"
    if "пока" in t or "до свидания" in t or "прощай" in t:
        return "Пока! Возвращайся 👋"
    if "праздник" in t or "какой сегодня день" in t:
        return "Проверь календарь праздников на сегодня 📅"
    if "придумай" in t and ("имя" in t or "название" in t or "иде" in t):
        return "Вот несколько идей: ✨ 1) «Свет», 2) «Импульс», 3) «Волна», 4) «Горизонт», 5) «Энергия». Скажи тему — придумаю ещё!"
    if "перевод" in t or "переведи" in t:
        return "Напиши текст и язык, например: «переведи привет на английский» — я помогу с переводом! 🌍"
    if "стих" in t or "стихотворение" in t:
        return "Вот тебе короткое: ✨\nВ мире тёплых слов и света,\nЯ всегда с тобой в ответе.\nСпросишь — отвечу, помогу,\nСкучать точно не дам никому! 💫"
    if re.search(r"[0-9]+\s*[+\-*/]\s*[0-9]+", t):
        try:
            res = eval(re.search(r"[0-9+\-*/().\s]+", t).group().strip())
            return f"Результат: {res} 🧮"
        except Exception:
            return "Напиши, например: 2+2*3"
    return None

def smart_answer(msg, history=None):
    q = quick_answers(msg)
    if q: return q
    # 1) GigaChat
    try:
        r = _http.post("https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
                       data={"scope": "GIGACHAT_API_PERS"},
                       headers={"Authorization": "Basic " + GIGACHAT_AUTH_KEY,
                                "RqUID": str(uuid.uuid4()),
                                "Content-Type": "application/x-www-form-urlencoded"}, timeout=6)
        tok = r.json().get("access_token")
        if tok:
            msgs = []
            if history:
                for h in history:
                    role = "user" if h[0] == "user" else "assistant"
                    msgs.append({"role": role, "content": h[1]})
            msgs.append({"role": "user", "content": msg})
            r = _http.post("https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
                           json={"model": "GigaChat", "messages": msgs},
                           headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"}, timeout=25)
            ans = r.json()["choices"][0]["message"]["content"]
            if ans and len(ans.strip()) > 1: return ans.strip()
    except Exception: pass
    # 2) YandexGPT
    try:
        r = _http.post("https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
                       json={"modelUri": f"gpt://{FOLDER_ID}/yandexgpt-lite",
                             "completionOptions": {"temperature": 0.6, "maxTokens": 700},
                             "messages": [{"role": "user", "text": msg}]},
                       headers={"Authorization": "Api-Key " + YANDEX_API_KEY,
                                "Content-Type": "application/json"}, timeout=25)
        ans = r.json()["result"]["alternatives"][0]["message"]["text"]
        if ans and len(ans.strip()) > 1: return ans.strip()
    except Exception: pass
    # 3) Универсальный fallback — всегда отвечаем
    return ("Я не смог связаться с нейросетью прямо сейчас (возможно, на хостинге нет "
            "доступа к внешним API), но я на связи! Я могу посчитать (например, 2+2*3), "
            "рассказать про погоду, курсы валют, криптовалюты, придумать идеи или имя. "
            "Спроси меня что-нибудь из этого!")

# ============ ЧАТ ============
def get_history(chat_id, n=30):
    rows = _select("messages_web", f"chat_id=eq.{chat_id}&select=*&order=id.desc&limit={n}") or []
    hist = [{"role": r.get("role"), "content": r.get("content")} for r in reversed(rows)]
    return [(h["role"], h["content"]) for h in hist]

@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    d = request.get_json(silent=True) or {}
    chat_id = str(d.get("chat_id", ""))
    msg = str(d.get("message", "")).strip()
    if not msg:
        return jsonify({"ok": False, "error": "Пустое сообщение"})
    if not chat_id:
        chat_id = uuid.uuid4().hex[:10]
        _insert("chats_web", {"user_id": session["uid"], "chat_id": chat_id, "title": msg[:30]})
    _insert("messages_web", {"chat_id": chat_id, "role": "user", "content": msg})
    history = get_history(chat_id)
    answer = smart_answer(msg, history)
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

@app.route("/api/rename", methods=["POST"])
@login_required
def rename():
    d = request.get_json(silent=True) or {}
    _patch("chats_web", f"chat_id=eq.{d.get('chat_id')}", {"title": str(d.get("title",""))[:40]})
    return jsonify({"ok": True})

@app.route("/api/pin", methods=["POST"])
@login_required
def pin():
    d = request.get_json(silent=True) or {}
    _patch("chats_web", f"chat_id=eq.{d.get('chat_id')}", {"pinned": 1 if d.get("pin") else 0})
    return jsonify({"ok": True})

@app.route("/api/delete_chat", methods=["POST"])
@login_required
def delete_chat():
    d = request.get_json(silent=True) or {}
    _delete("chats_web", f"chat_id=eq.{d.get('chat_id')}")
    _delete("messages_web", f"chat_id=eq.{d.get('chat_id')}")
    return jsonify({"ok": True})

@app.route("/api/search")
@login_required
def search():
    q = request.args.get("q", "").strip()
    rows = _select("chats_web", f"user_id=eq.{session['uid']}&select=*") or []
    res = [{"id": r.get("chat_id"), "title": r.get("title")} for r in rows if q.lower() in str(r.get("title","")).lower()]
    return jsonify({"ok": True, "results": res})

@app.route("/api/image", methods=["POST"])
@login_required
def gen_image():
    prompt = str((request.get_json(silent=True) or {}).get("prompt", "")).strip() or "abstract art"
    try:
        url = f"https://image.pollinations.ai/prompt/{quote(prompt)}"
        return jsonify({"ok": True, "url": url})
    except Exception:
        return jsonify({"ok": False, "error": "Ошибка"})

@app.route("/api/upload", methods=["POST"])
@login_required
def upload():
    chat_id = request.form.get("chat_id", "")
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "error": "Нет файла"})
    try:
        data = base64.b64encode(f.read()).decode()
        fname = f.filename or "file"
        _insert("messages_web", {"chat_id": chat_id, "role": "user",
                                 "content": "📎 Файл: " + fname, "file": data})
        return jsonify({"ok": True, "name": fname})
    except Exception:
        return jsonify({"ok": False, "error": "Ошибка"})

@app.route("/api/share", methods=["POST"])
@login_required
def share():
    d = request.get_json(silent=True) or {}
    chat_id = str(d.get("chat_id", ""))
    code = uuid.uuid4().hex[:8]
    _insert("shared_chats", {"share_code": code, "chat_id": chat_id})
    return jsonify({"ok": True, "url": "/s/" + code})

@app.route("/s/<code>")
def shared(code):
    rows = _select("shared_chats", f"share_code=eq.{code}&select=chat_id") or []
    if not rows: return "Чат не найден", 404
    cid = rows[0].get("chat_id")
    msgs = _select("messages_web", f"chat_id=eq.{cid}&select=*&order=id.asc") or []
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
    buf = io.BytesIO(text.encode("utf-8"))
    return send_file(buf, as_attachment=True, download_name="chat.txt", mimetype="text/plain")

# ============ ПРОФИЛЬ / XP / УРОВНИ ============
@app.route("/api/profile")
@login_required
def profile():
    u, _ = get_user_col(session["uid"])
    u = u or {}
    return jsonify({"ok": True, "name": u.get("username", ""),
                    "role": parse_status(u)["role"], "xp": u.get("xp", 0),
                    "level": u.get("level", 1)})

@app.route("/api/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        d = request.get_json(silent=True) or {}
        # тема храним в data (JSON) твоей таблицы, если есть колонка data
        cols = get_users_columns()
        if "data" in cols:
            u, _ = get_user_col(session["uid"])
            data = u.get("data") or {} if u else {}
            if isinstance(data, str):
                try: data = json.loads(data)
                except: data = {}
            data["theme"] = d.get("theme", "dark")
            _patch("users", f"user_id=eq.{session['uid']}", {"data": data})
        return jsonify({"ok": True})
    u, _ = get_user_col(session["uid"])
    theme = "dark"
    if u:
        data = u.get("data")
        if isinstance(data, dict) and data.get("theme"): theme = data["theme"]
        elif isinstance(data, str):
            try:
                dd = json.loads(data)
                if dd.get("theme"): theme = dd["theme"]
            except: pass
    return jsonify({"ok": True, "theme": theme})

# ============ АДМИН (только владелец) ============
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
    rows = _select("users", "select=user_id") or []
    msgs = _select("messages_web", "select=id") or []
    return jsonify({"ok": True, "users": len(rows), "messages": len(msgs)})

@app.route("/api/admin/reset_password", methods=["POST"])
@owner_required
def admin_reset_password():
    d = request.get_json(silent=True) or {}
    tgid = str(d.get("telegram_id", "")).strip()
    newp = str(d.get("password", "")).strip()
    if not tgid or not newp: return jsonify({"ok": False, "error": "Нужны ID и пароль"})
    u, _ = get_user_col(tgid)
    if not u: return jsonify({"ok": False, "error": "Аккаунт не найден"})
    ok = _patch("users", f"user_id=eq.{tgid}", {"password": hash_pw(newp)})
    return jsonify({"ok": ok})

@app.route("/api/admin/delete_user", methods=["POST"])
@owner_required
def admin_delete_user():
    d = request.get_json(silent=True) or {}
    tgid = str(d.get("telegram_id", "")).strip()
    if not tgid or tgid == OWNER_TGID: return jsonify({"ok": False, "error": "Нельзя удалить"})
    ok = _delete("users", f"user_id=eq.{tgid}")
    return jsonify({"ok": ok})

@app.route("/api/admin/give_premium", methods=["POST"])
@owner_required
def admin_give_premium():
    d = request.get_json(silent=True) or {}
    tgid = str(d.get("telegram_id", "")).strip()
    if not tgid: return jsonify({"ok": False, "error": "Нужен Telegram-ID"})
    u, _ = get_user_col(tgid)
    if not u: return jsonify({"ok": False, "error": "Аккаунт не найден"})
    until = datetime.now(timezone.utc) + timedelta(days=int(d.get("days", 0)),
                                                   hours=int(d.get("hours", 0)),
                                                   minutes=int(d.get("minutes", 0)))
    ok = _patch("users", f"user_id=eq.{tgid}",
                {"premium": 1, "premium_expires": until.isoformat()})
    return jsonify({"ok": ok})

@app.route("/api/admin/remove_premium", methods=["POST"])
@owner_required
def admin_remove_premium():
    d = request.get_json(silent=True) or {}
    tgid = str(d.get("telegram_id", "")).strip()
    if not tgid: return jsonify({"ok": False, "error": "Нужен Telegram-ID"})
    u, _ = get_user_col(tgid)
    if not u: return jsonify({"ok": False, "error": "Аккаунт не найден"})
    ok = _patch("users", f"user_id=eq.{tgid}", {"premium": 0, "premium_expires": None})
    return jsonify({"ok": ok})

@app.route("/api/admin/set_admin", methods=["POST"])
@owner_required
def admin_set_admin():
    d = request.get_json(silent=True) or {}
    tgid = str(d.get("telegram_id", "")).strip()
    if not tgid: return jsonify({"ok": False, "error": "Нужен Telegram-ID"})
    u, _ = get_user_col(tgid)
    if not u: return jsonify({"ok": False, "error": "Аккаунт не найден"})
    ok = _patch("users", f"user_id=eq.{tgid}", {"is_admin": 1 if d.get("admin") else 0})
    return jsonify({"ok": ok})

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
            _http.post(f"{BOT}/sendMessage", json={"chat_id": tid, "text": text}, timeout=5)
            sent += 1
        except Exception: pass
    return jsonify({"ok": True, "sent": sent})

@app.route("/api/admin/clear_all", methods=["POST"])
@owner_required
def admin_clear_all():
    d = request.get_json(silent=True) or {}
    if not d.get("confirm"): return jsonify({"ok": False, "error": "Нужно подтверждение"})
    reset_all_accounts()
    return jsonify({"ok": True})

# ============ ГЛАВНАЯ ============
@app.route("/")
def index():
    return INDEX_HTML

INDEX_HTML = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AWESOME AI — Про</title>
<style>
:root{--ac1:#7b9cff;--ac2:#6fd8c0;--text:#e2e8f0;--card:#1e293b;--bg:#0f172a;--muted:#94a3b8}
*{box-sizing:border-box;margin:0;padding:0;font-family:'Segoe UI',system-ui,sans-serif}
body{background:linear-gradient(135deg,#0f172a 0%,#1a2a4a 50%,#123a3a 100%);min-height:100vh;color:var(--text)}
@keyframes fadeUp{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:translateY(0)}}
@keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}
@keyframes glow{0%,100%{box-shadow:0 0 0 rgba(127,156,255,0)}50%{box-shadow:0 0 30px rgba(127,156,255,.25)}}
.card{background:var(--card);border-radius:22px;padding:32px;width:100%;max-width:420px;
box-shadow:0 20px 60px rgba(0,0,0,.5);animation:fadeUp .5s ease;text-align:center;margin:auto}
.wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.logo{font-size:32px;font-weight:800;background:linear-gradient(90deg,var(--ac1),var(--ac2));
-webkit-background-clip:text;background-clip:text;color:transparent;animation:float 3s ease-in-out infinite}
.sub{color:var(--muted);font-size:14px;margin:8px 0 24px}
input,textarea{width:100%;background:var(--bg);border:1.5px solid #334155;border-radius:14px;padding:13px 16px;
color:#fff;font-size:15px;outline:none;margin-bottom:12px;transition:border-color .2s}
input:focus,textarea:focus{border-color:var(--ac1)}
textarea{resize:vertical;min-height:70px}
.btn{width:100%;background:linear-gradient(90deg,var(--ac1),var(--ac2));color:#fff;border:none;border-radius:14px;
padding:13px;font-size:15px;font-weight:600;cursor:pointer;transition:transform .15s,box-shadow .2s}
.btn:hover{transform:translateY(-2px);box-shadow:0 8px 24px rgba(127,156,255,.3)}
.btn.ghost{background:#334155}
.btn.small{width:auto;padding:8px 14px;font-size:13px;display:inline-block;margin:4px}
.btn.danger{background:#ef4444}
.err{color:#f87171;font-size:13px;margin-top:8px;min-height:18px}
.hint{color:#64748b;font-size:12px;margin-top:16px}
.name-field{display:none}
.app{display:none;max-width:950px;margin:0 auto;padding:14px}
.topbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.tab{background:#1e293b;border:none;color:var(--text);padding:8px 16px;border-radius:20px;cursor:pointer}
.tab.active{background:linear-gradient(90deg,var(--ac1),var(--ac2));color:#fff}
.chatbox{max-height:55vh;overflow-y:auto;margin-bottom:10px;padding:10px;border:1px solid #334155;border-radius:16px;background:rgba(15,23,42,.5)}
.msg{animation:fadeUp .3s ease;padding:12px;border-radius:12px;margin:6px 0;max-width:85%;white-space:pre-wrap}
.msg.user{background:linear-gradient(90deg,var(--ac1),var(--ac2));margin-left:auto;color:#fff}
.msg.ai{background:#334155;margin-right:auto}
.msg .tools{margin-top:8px;display:flex;gap:6px;flex-wrap:wrap}
.chat-item{background:#1e293b;border-radius:12px;padding:12px;margin:8px 0;cursor:pointer;transition:transform .15s}
.chat-item:hover{transform:translateX(4px)}
.admin-row{display:flex;gap:8px;align-items:center;margin:6px 0;flex-wrap:wrap;background:#0f172a;border-radius:10px;padding:8px}
.admin-row span{flex:1;font-size:13px}
#adminTab{display:none}
.diag{color:#6fd8c0;font-size:11px;margin-top:8px;cursor:pointer;text-decoration:underline}
.toolbar{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
</style></head><body>

<!-- ВХОД -->
<div class="wrap" id="authScreen">
  <div class="card">
    <div class="logo">✨ AWESOME AI</div>
    <div class="sub" id="sub">Вход в аккаунт</div>
    <div class="name-field" id="nameWrap"><input id="authName" placeholder="Название (имя)"></div>
    <input id="authTg" placeholder="Telegram ID">
    <input id="authPass" type="password" placeholder="Пароль">
    <button class="btn" id="authBtn" onclick="doAuth()">Войти</button>
    <button class="btn ghost" style="margin-top:10px" onclick="toggleMode()">Нет аккаунта? Зарегистрироваться</button>
    <div class="err" id="err"></div>
    <div class="hint">AWESOME AI · вход по Telegram ID</div>
    <div class="diag" onclick="showDiag()">🔍 Диагностика</div>
  </div>
</div>

<!-- ПРИЛОЖЕНИЕ -->
<div class="app" id="app">
  <div class="topbar">
    <span class="logo" style="font-size:22px">✨ AWESOME AI</span>
    <span class="user" id="userInfo"></span>
  </div>
  <div class="tabs">
    <button class="tab active" onclick="showTab('chat')">💬 Чат</button>
    <button class="tab" onclick="showTab('chats')">📁 Мои чаты</button>
    <button class="tab" onclick="showTab('image')">🎨 Картинки</button>
    <button class="tab" id="adminTab" onclick="showTab('admin')">⚙️ Админ</button>
    <button class="tab" onclick="showTab('settings')">🛠 Настройки</button>
    <button class="tab" onclick="logout()">🚪 Выйти</button>
  </div>

  <div id="tab-chat">
    <div class="chatbox" id="chatBox"><div class="msg ai">Привет! 👋 Я AWESOME AI. Напиши мне что-нибудь — отвечу как DeepSeek/ChatGPT/Grok!</div></div>
    <textarea id="chatInput" placeholder="Напишите сообщение..." onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendChat();}"></textarea>
    <div class="toolbar">
      <button class="btn" style="width:auto" onclick="sendChat()">✈ Отправить</button>
      <button class="btn ghost small" onclick="newChat()">🆕 Новый чат</button>
      <button class="btn ghost small" onclick="genImageFromChat()">🎨 Картинка</button>
      <button class="btn ghost small" onclick="shareChat()">🔗 Поделиться</button>
      <button class="btn ghost small" onclick="exportChat()">📥 Экспорт</button>
    </div>
  </div>

  <div id="tab-chats" style="display:none">
    <input id="searchInput" placeholder="🔍 Поиск по чатам..." oninput="loadChats()">
    <div id="chatList"></div>
  </div>

  <div id="tab-image" style="display:none">
    <h3>🎨 Генерация изображений</h3>
    <input id="imgPrompt" placeholder="Опишите картинку, например: кот в космосе">
    <button class="btn" onclick="genImage()">Сгенерировать</button>
    <div id="imgResult" style="margin-top:12px;text-align:center"></div>
  </div>

  <div id="tab-settings" style="display:none">
    <h3>🛠 Настройки</h3>
    <div style="margin:8px 0"><b>Тема:</b>
      <button class="btn small" onclick="setTheme('dark')">🌙 Тёмная</button>
      <button class="btn small" onclick="setTheme('light')">☀️ Светлая</button>
    </div>
    <div id="profileInfo" style="margin:12px 0;color:var(--muted)"></div>
  </div>

  <div id="tab-admin" style="display:none">
    <h3>⚙️ Панель владельца</h3>
    <div id="adminStats" style="margin:8px 0;color:var(--muted)"></div>
    <input id="admTg" placeholder="Telegram ID пользователя">
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <input id="admDays" placeholder="Дни" type="number" style="width:70px">
      <input id="admHours" placeholder="Часы" type="number" style="width:70px">
      <input id="admMin" placeholder="Минуты" type="number" style="width:70px">
    </div>
    <button class="btn small" onclick="admGive()">💎 Выдать Premium</button>
    <button class="btn small danger" onclick="admRemove()">Снять Premium</button>
    <input id="admPass" placeholder="Новый пароль (сброс)">
    <button class="btn small" onclick="admResetPass()">🔑 Сбросить пароль</button>
    <button class="btn small danger" onclick="admDelete()">🗑 Удалить аккаунт</button>
    <div id="adminList"></div>
  </div>
</div>

<script>
let isReg=false, curChat="", me=null;
function toggleMode(){
 isReg=!isReg;
 document.getElementById('nameWrap').style.display=isReg?'block':'none';
 document.getElementById('authBtn').textContent=isReg?'Создать аккаунт':'Войти';
 document.getElementById('sub').textContent=isReg?'Регистрация':'Вход в аккаунт';
 document.querySelector('.ghost').textContent=isReg?'Уже есть аккаунт? Войти':'Нет аккаунта? Зарегистрироваться';
}
async function showDiag(){
 try{const r=await fetch('/api/diag');const d=await r.json();
 document.getElementById('err').innerHTML='<b>Диагностика:</b><br>'+JSON.stringify(d);
 }catch(e){document.getElementById('err').textContent='Ошибка диагностики';}
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
  let d;try{d=await r.json();}catch(e){document.getElementById('err').textContent='Сервер не отвечает';reset();return;}
  if(!d.ok){document.getElementById('err').textContent=d.error||'Ошибка';reset();return;}
  enterApp({uid:d.uid,name:d.name});
 }catch(e){document.getElementById('err').textContent='Ошибка сети';reset();}
}
function reset(){const b=document.getElementById('authBtn');b.textContent=isReg?'Создать аккаунт':'Войти';b.disabled=false;}
async function enterApp(d){
 me={uid:d.uid,name:d.name};
 document.getElementById('authScreen').style.display='none';
 document.getElementById('app').style.display='block';
 document.getElementById('userInfo').textContent=me.name;
 const m=await fetch('/api/me');const md=await m.json();
 if(md.ok){
   me=md;
   document.getElementById('userInfo').textContent=me.name+' · '+me.status.role+(me.status.premium?' 💎':'');
   if(me.status.owner)document.getElementById('adminTab').style.display='block';
 }
 loadProfile(); showTab('chat');
}
async function init(){
 try{
  const r=await fetch('/api/me');
  if(r.ok){const d=await r.json(); if(d.ok){enterApp({uid:d.uid,name:d.name}); return;}}
 }catch(e){}
 document.getElementById('authScreen').style.display='flex';
}
function showTab(t){
 document.getElementById('tab-chat').style.display=t==='chat'?'block':'none';
 document.getElementById('tab-chats').style.display=t==='chats'?'block':'none';
 document.getElementById('tab-image').style.display=t==='image'?'block':'none';
 document.getElementById('tab-settings').style.display=t==='settings'?'block':'none';
 document.getElementById('tab-admin').style.display=t==='admin'?'block':'none';
 document.querySelectorAll('.tab').forEach(b=>b.classList.remove('active'));
 if(t==='chats')loadChats(); if(t==='admin')loadAdmin();
}
async function sendChat(){
 const msg=document.getElementById('chatInput').value.trim(); if(!msg)return;
 const box=document.getElementById('chatBox');
 box.innerHTML+='<div class="msg user">'+esc(msg)+'</div>';
 document.getElementById('chatInput').value='';
 const typingId='typing'+Date.now();
 box.innerHTML+='<div class="msg ai" id="'+typingId+'">⏳ Думаю...</div>';box.scrollTop=box.scrollHeight;
 const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({chat_id:curChat,message:msg})});
 const d=await r.json();
 const el=document.getElementById(typingId);
 if(el){el.innerHTML=esc(d.answer||'Ошибка')+toolsHTML(typingId);}
 curChat=d.chat_id;box.scrollTop=box.scrollHeight;
}
function toolsHTML(id){
 return '<div class="tools">'+
  '<button class="btn small" onclick="copyMsg(this)">📋 Копировать</button>'+
  '<button class="btn small" onclick="speakMsg(this)">🔊 Озвучить</button>'+
  '</div>';
}
function esc(s){return (s||'').replace(/</g,'&lt;').replace(/\n/g,'<br>');}
function copyMsg(btn){const t=btn.parentElement.parentElement.innerText.replace('📋 Копировать','').replace('🔊 Озвучить','').trim();navigator.clipboard.writeText(t);btn.textContent='✅ Скопировано';setTimeout(()=>btn.textContent='📋 Копировать',1500);}
function speakMsg(btn){const t=btn.parentElement.parentElement.innerText.replace('📋 Копировать','').replace('🔊 Озвучить','').trim();const u=new SpeechSynthesisUtterance(t);u.lang='ru-RU';speechSynthesis.cancel();speechSynthesis.speak(u);}
function newChat(){curChat='';document.getElementById('chatBox').innerHTML='<div class="msg ai">Привет! 👋 Напиши мне что-нибудь.</div>';}
async function loadChats(){
 const r=await fetch('/api/chats');const d=await r.json();const el=document.getElementById('chatList');el.innerHTML='';
 let list=d.chats||[];
 const q=(document.getElementById('searchInput').value||'').toLowerCase();
 if(q)list=list.filter(c=>(c.title||'').toLowerCase().includes(q));
 if(!list.length){el.innerHTML='<p style="color:var(--muted)">Чатов пока нет. Начни диалог в «Чат».</p>';return;}
 list.forEach(c=>{const div=document.createElement('div');div.className='chat-item';
 div.innerHTML=(c.pinned?'📌 ':'')+esc(c.title)+' <button class="btn small danger" style="float:right" onclick="event.stopPropagation();delChat(\''+c.id+'\')">🗑</button>';
 div.onclick=()=>{curChat=c.id;showTab('chat');loadMsgs();};el.appendChild(div);});
}
async function loadMsgs(){
 const r=await fetch('/api/messages?chat_id='+curChat);const d=await r.json();const box=document.getElementById('chatBox');
 box.innerHTML='';d.messages.forEach(m=>{box.innerHTML+='<div class="msg '+(m.role==='user'?'user':'ai')+'">'+esc(m.content)+'</div>';});
 box.scrollTop=box.scrollHeight;
}
async function delChat(id){if(!confirm('Удалить чат?'))return;await fetch('/api/delete_chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({chat_id:id})});loadChats();}
async function genImageFromChat(){const p=prompt('Опишите картинку:');if(!p)return;const d=await (await fetch('/api/image',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:p})})).json();if(d.ok)window.open(d.url,'_blank');}
async function genImage(){const p=document.getElementById('imgPrompt').value.trim();if(!p)return;const d=await (await fetch('/api/image',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:p})})).json();document.getElementById('imgResult').innerHTML=d.ok?'<img src="'+d.url+'" style="max-width:100%;border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,.5)">':'Ошибка';}
async function shareChat(){if(!curChat){alert('Сначала начни чат');return;}const d=await (await fetch('/api/share',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({chat_id:curChat})})).json();if(d.ok){navigator.clipboard.writeText(location.origin+d.url);alert('Ссылка скопирована: '+location.origin+d.url);}}
function exportChat(){if(!curChat){alert('Сначала начни чат');return;}window.location='/api/export?chat_id='+curChat;}
async function setTheme(t){await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({theme:t})});location.reload();}
async function loadProfile(){const d=await (await fetch('/api/profile')).json();if(d.ok)document.getElementById('profileInfo').textContent='👤 '+d.name+' · Уровень '+d.level+' · XP '+d.xp;}
async function loadAdmin(){
 const s=await (await fetch('/api/admin/stats')).json();
 document.getElementById('adminStats').textContent='Пользователей: '+s.users+' · Сообщений: '+s.messages;
 const r=await fetch('/api/admin/users');const d=await r.json();const el=document.getElementById('adminList');el.innerHTML='';
 if(!d.ok){el.innerHTML='<p style="color:var(--muted)">'+d.error+'</p>';return;}
 d.users.forEach(u=>{const row=document.createElement('div');row.className='admin-row';
 row.innerHTML='<span>'+esc(u.name)+' (ID: '+u.id+') — '+u.role+(u.premium?' 💎':'')+'</span>';
 el.appendChild(row);});
}
async function admGive(){const r=await fetch('/api/admin/give_premium',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:admTg.value.trim(),days:+admDays.value||0,hours:+admHours.value||0,minutes:+admMin.value||0})});alert((await r.json()).ok?'Premium выдан':'Ошибка');}
async function admRemove(){const r=await fetch('/api/admin/remove_premium',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:admTg.value.trim()})});alert((await r.json()).ok?'Premium снят':'Ошибка');}
async function admResetPass(){const r=await fetch('/api/admin/reset_password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:admTg.value.trim(),password:admPass.value.trim()})});alert((await r.json()).ok?'Пароль сброшен':'Ошибка');}
async function admDelete(){if(!confirm('Удалить аккаунт?'))return;const r=await fetch('/api/admin/delete_user',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:admTg.value.trim()})});alert((await r.json()).ok?'Удалено':'Ошибка');}
async function logout(){await fetch('/api/logout',{method:'POST'});location.reload();}
init();
</script></body></html>"""

if __name__ == "__main__":
    # ПОЛНЫЙ СБРОС АККАУНТОВ ПРИ СТАРТЕ
    reset_all_accounts()
    try:
        from waitress import serve
        serve(app, host="0.0.0.0", port=PORT, threads=8)
    except ImportError:
        app.run(host="0.0.0.0", port=PORT)
