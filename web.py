import os, re, uuid, hashlib, io
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import quote
import requests, psycopg2
from flask import Flask, request, jsonify, session, send_file

PORT = int(os.environ.get("PORT", "8080"))
SESSION_TTL = 30 * 24 * 3600
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
app.secret_key = "diag-mode"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(seconds=SESSION_TTL)
_http = requests.Session()
BOT = "https://api.telegram.org/bot" + TELEGRAM_TOKEN
SB_HDR = {"apikey": SUPABASE_ANON_KEY, "Authorization": "Bearer " + SUPABASE_ANON_KEY}
SB_URL = SUPABASE_URL.rstrip("/")

def hash_pw(p): return hashlib.sha256(p.encode()).hexdigest()
def get_conn(): return psycopg2.connect(DATABASE_URL)

def sb_get_user(tgid):
    try:
        r = _http.get(f"{SB_URL}/rest/v1/users?telegram_id=eq.{tgid}&select=*",
                      headers=SB_HDR, timeout=6)
        if r.status_code == 200 and r.json(): return r.json()[0]
    except Exception: pass
    return None

# ======== ЛОГИН С ДИАГНОСТИКОЙ: покажет НАСТОЯЩУЮ ошибку ========
@app.route("/api/login", methods=["POST"])
def login():
    try:
        d = request.get_json(silent=True) or {}
        tgid = str(d.get("telegram_id", "")).strip()
        pwd = str(d.get("password", "")).strip()
        if not tgid or not pwd:
            return jsonify({"ok": False, "error": "Заполни оба поля"})
        # пробуем Supabase
        u = sb_get_user(tgid)
        if not u:
            # пробуем локальную БД
            try:
                conn = get_conn(); cur = conn.cursor()
                cur.execute("SELECT username,password,role FROM users WHERE user_id=%s",(tgid,))
                row = cur.fetchone(); cur.close(); conn.close()
                if not row: return jsonify({"ok": False, "error": "Аккаунт не найден"})
                if hash_pw(pwd) != row[1]:
                    return jsonify({"ok": False, "error": "Неверный пароль"})
            except Exception as e:
                return jsonify({"ok": False, "REAL_ERROR_LOCAL_DB": str(e),
                                "hint": "проблема с локальным PostgreSQL"})
        else:
            db_pw = u.get("password") or u.get("pwd") or ""
            if str(tgid) == OWNER_TGID and (not db_pw or db_pw == hash_pw(OWNER_PASS)):
                db_pw = hash_pw(OWNER_PASS)
            if hash_pw(pwd) != db_pw:
                return jsonify({"ok": False, "error": "Неверный пароль"})
        session.permanent = True
        session["uid"] = tgid
        session["name"] = u.get("username") or u.get("name") if u else tgid
        return jsonify({"ok": True, "uid": tgid, "name": session["name"]})
    except Exception as e:
        # ВАЖНО: показываем реальную ошибку вместо «Временной»
        return jsonify({"ok": False, "REAL_ERROR": str(e),
                        "type": type(e).__name__})

@app.route("/api/diag")
def diag():
    out = {}
    try:
        conn = get_conn(); cur = conn.cursor(); cur.execute("SELECT 1"); cur.fetchone()
        cur.close(); conn.close()
        out["local_db"] = "OK"
    except Exception as e:
        out["local_db"] = "FAIL: " + str(e)
    try:
        r = _http.get(f"{SB_URL}/rest/v1/users?select=telegram_id&limit=1",
                      headers=SB_HDR, timeout=6)
        out["supabase"] = f"status {r.status_code}"
    except Exception as e:
        out["supabase"] = "FAIL: " + str(e)
    return jsonify(out)

@app.route("/")
def index():
    return "AWESOME AI. Войди через /api/login (POST) или открой /api/diag для диагностики."

if __name__ == "__main__":
    try:
        from waitress import serve
        serve(app, host="0.0.0.0", port=PORT, threads=8)
    except ImportError:
        app.run(host="0.0.0.0", port=PORT)
