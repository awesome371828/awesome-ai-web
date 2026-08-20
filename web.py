#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AWESOME AI WEB — PRO ULTRA: Telegram-вход, память, поиск, 40+ функций"""
import os, re, io, time, json, base64, urllib.parse, hashlib, random, html, uuid as _uuid, hmac
from datetime import datetime, timedelta, timezone
import requests, urllib3
import psycopg2, psycopg2.extras
from flask import Flask, request, jsonify, render_template_string, session, send_file

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    from dateutil.relativedelta import relativedelta
except ImportError:
    def relativedelta(**kw):
        kw.pop("years", None); kw.pop("months", None)
        return timedelta(**kw)
try:
    from supabase import create_client
    HAS_SUPABASE = True
except ImportError:
    HAS_SUPABASE = False
    def create_client(*a, **k): return None
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY","awesome-ai-super-secret-key-2026")
app.permanent_session_lifetime = timedelta(days=30)
app.config['SESSION_COOKIE_HTTPONLY']=True

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY","AQVNyfn82epL9dy8C_kftzeypq6eF9lFd6SZnFzV")
FOLDER_ID = os.getenv("FOLDER_ID","b1g4aq87c7j61c6g3i5l")
GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY","MDFhMDBkNmEtMmExNC03M2JkLWFlZmMtOTQ0OWVlOTc5M2U1OmE1ZWJhM2NlLTQwYjAtNDZlYi1iMmY2LTE3OTFmYzhhYTQ2MA==")
SUPABASE_URL = os.getenv("SUPABASE_URL","https://lprxbmshmuucymkgaqwk.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY","eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxwcnhibXNobXV1Y3lta2dhcXdrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY3NDk0MjgsImV4cCI6MjEwMjMyNTQyOH0.Ie9jSH5RMxeOq8aU-Dv6MXlojWMUTOLE723Hdg6heZU")
DATABASE_URL = os.getenv("DATABASE_URL","postgresql://u_cmsu43cr30:3sdZICdPDoR1DUrRRKsJ8yW1BqrH2PvZ@db-team-cmsu3ykqi0295mo01tsv8m15p:5432/db_awesome_ai_web")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN","8336209662:AAHdhYXhqWA-LtthwgydDSRU7A6A0ceC-HY")

OWNER_ID = 6652898792
FREE_LIMIT = 40
MAX_HISTORY = 24
GIGA_TIMEOUT = 30
YGPT_TIMEOUT = 25
SEARCH_TIMEOUT = 4
TG_BOT = "@awesomeneiro_bot"

MOSCOW_TZ = timezone(timedelta(hours=3))
def gm(): return datetime.now(MOSCOW_TZ)
def gdate(): return gm().strftime('%d.%m.%Y')
def now_iso(): return gm().strftime('%Y-%m-%d %H:%M:%S')
def fmt_date(s):
    if not s: return "—"
    try: return datetime.strptime(s,'%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')
    except: return s
def hash_pw(p): return hashlib.sha256(p.encode()).hexdigest()
def get_db(): return psycopg2.connect(DATABASE_URL)
def is_owner(uid=None, tg=None):
    if uid and str(uid)==str(OWNER_ID): return True
    if tg and str(tg)==str(OWNER_ID): return True
    return False

def init_db():
    conn=get_db(); cur=conn.cursor()
    def ex(sql, args=None):
        try: cur.execute(sql, args or ()); conn.commit()
        except Exception: conn.rollback()
    ex("""CREATE TABLE IF NOT EXISTS users(
        user_id TEXT PRIMARY KEY, name TEXT, password TEXT, telegram_id TEXT,
        premium INTEGER DEFAULT 0, messages_today INTEGER DEFAULT 0, last_reset TEXT,
        premium_expires TEXT, is_admin INTEGER DEFAULT 0, is_owner INTEGER DEFAULT 0,
        theme TEXT DEFAULT 'dark', joined_at TEXT, xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1,
        avatar TEXT DEFAULT '', ref_code TEXT, ref_count INTEGER DEFAULT 0)""")
    ex("""CREATE TABLE IF NOT EXISTS chats_web(id BIGSERIAL PRIMARY KEY, user_id TEXT,
        title TEXT DEFAULT 'Новый чат', created_at TEXT, pinned INTEGER DEFAULT 0)""")
    ex("""CREATE TABLE IF NOT EXISTS messages_web(id BIGSERIAL PRIMARY KEY, chat_id BIGINT,
        role TEXT, content TEXT, image TEXT, created_at TEXT)""")
    ex("""CREATE TABLE IF NOT EXISTS total_stats_web(user_id TEXT PRIMARY KEY, total_messages INTEGER DEFAULT 0)""")
    ex("""CREATE TABLE IF NOT EXISTS shared_chats(id TEXT PRIMARY KEY, chat_id BIGINT, created_at TEXT)""")
    ex("""CREATE TABLE IF NOT EXISTS admin_log(id BIGSERIAL PRIMARY KEY, admin_id TEXT, action TEXT, created_at TEXT)""")
    ex("""CREATE TABLE IF NOT EXISTS notifications(id BIGSERIAL PRIMARY KEY, user_id TEXT, text TEXT, read INTEGER DEFAULT 0, created_at TEXT)""")
    ex("""CREATE TABLE IF NOT EXISTS user_memory(id BIGSERIAL PRIMARY KEY, user_id TEXT,
        fact TEXT, source TEXT DEFAULT 'auto', created_at TEXT)""")
    ex("""CREATE TABLE IF NOT EXISTS web_cache(query TEXT PRIMARY KEY, result TEXT, ts TEXT)""")
    for col in ['xp','level','avatar','ref_code','ref_count','telegram_id','name','password']:
        ex(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} TEXT DEFAULT ''")
    ex("ALTER TABLE chats_web ADD COLUMN IF NOT EXISTS pinned INTEGER DEFAULT 0")
    ex("ALTER TABLE messages_web ADD COLUMN IF NOT EXISTS image TEXT")
    try:
        cur.execute("SELECT data_type FROM information_schema.columns WHERE table_name='users' AND column_name='xp'")
        row=cur.fetchone()
        if row and row[0]=='text':
            cur.execute("UPDATE users SET xp='0' WHERE xp IS NULL OR xp='' OR xp !~ '^[0-9]+$'")
            cur.execute("ALTER TABLE users ALTER COLUMN xp TYPE INTEGER USING (CASE WHEN xp IS NULL OR xp='' THEN 0 ELSE xp::int END)")
        conn.commit()
    except Exception: conn.rollback()
    try:
        cur.execute("SELECT password FROM users WHERE user_id=%s",(str(OWNER_ID),))
        if not cur.fetchone():
            cur.execute("INSERT INTO users(user_id,name,password,telegram_id,messages_today,last_reset,is_owner,theme,joined_at) VALUES(%s,%s,%s,%s,0,%s,1,'dark',%s)",
                        (str(OWNER_ID),'AWESOME',hash_pw('qawsedrf2346'),str(OWNER_ID),gm().strftime('%Y-%m-%d'),now_iso()))
            cur.execute("INSERT INTO total_stats_web(user_id,total_messages) VALUES(%s,0) ON CONFLICT DO NOTHING",(str(OWNER_ID),))
        conn.commit()
    except Exception: conn.rollback()
    cur.close(); conn.close()
init_db()
supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if HAS_SUPABASE else None

# ===== ВХОД ЧЕРЕЗ TELEGRAM =====
def tg_verify(data):
    """Проверка подписи виджета Telegram Login."""
    try:
        secret=hashlib.sha256(TELEGRAM_TOKEN.encode()).digest()
        check=data.get('hash','')
        items=sorted((k,v) for k,v in data.items() if k!='hash')
        msg="\n".join(f"{k}={v}" for k,v in items)
        calc=hmac.new(secret,msg.encode(),hashlib.sha256).hexdigest()
        return hmac.compare_digest(calc,check) and int(data.get('auth_date',0))>time.time()-86400
    except Exception:
        return False

@app.route('/tg_oauth')
def tg_oauth():
    d=request.args.to_dict()
    if not tg_verify(d):
        return "<html><body style='background:#0a0f1c;color:#fff;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh'>❌ Ошибка входа. Попробуй ещё раз.</body></html>"
    tg=str(d.get('id','')).strip()
    first=d.get('first_name','') or ''
    last=d.get('last_name','') or ''
    name=(first+' '+last).strip() or 'Telegram'
    u=get_user(tg)
    if not u:
        pw='tg_'+''.join(random.choice('abcdef0123456789') for _ in range(8))
        ok,_=reg_user(tg,name,pw)
        if not ok and not get_user(tg):
            return "<html><body style='background:#0a0f1c;color:#fff;display:flex;align-items:center;justify-content:center;height:100vh'>Не удалось создать аккаунт</body></html>"
    session.permanent=True; session['user_id']=tg; session['name']=name
    return """<html><head><script>
    if(window.opener){window.opener.postMessage('tg_ok','*');window.close();}
    else{location.href='/';}
    </script></head><body style='background:#0a0f1c;color:#fff;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh'>✅ Вход выполнен!</body></html>"""

# ===== ПАМЯТЬ О ПОЛЬЗОВАТЕЛЕ =====
def get_memory(uid, limit=30):
    try:
        conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT fact FROM user_memory WHERE user_id=%s ORDER BY id DESC LIMIT %s",(str(uid),limit))
        rows=cur.fetchall(); cur.close(); conn.close()
        return [r['fact'] for r in rows]
    except Exception: return []

def remember(uid, fact):
    fact=(fact or '').strip()[:500]
    if not fact or len(fact)<4: return
    try:
        conn=get_db(); cur=conn.cursor()
        cur.execute("SELECT COUNT(*) FROM user_memory WHERE user_id=%s AND fact=%s",(str(uid),fact))
        if cur.fetchone()[0]==0:
            cur.execute("INSERT INTO user_memory(user_id,fact,created_at) VALUES(%s,%s,%s)",(str(uid),fact,now_iso()))
        conn.commit(); cur.close(); conn.close()
    except Exception: pass

def extract_facts(uid,text):
    facts=[]
    tl=text.lower()
    if "меня зовут" in tl or "мое имя" in tl:
        m=re.search(r'(?:меня зовут|мое имя)[:\s]+([А-Яа-яЁёA-Za-z\-]+)',tl)
        if m: facts.append("Имя пользователя: "+m.group(1))
    for kw,label in [("мне ", "Возраст: "), ("я живу в ", "Город: "), ("я работаю ", "Работа: "), ("учусь в ", "Учёба: "), ("я из ", "Город: ")]:
        if kw in tl:
            m=re.search(re.escape(kw)+r'([^,.!?\n]{2,60})',tl)
            if m: facts.append(label+m.group(1).strip())
    if any(x in tl for x in ["мне нравится","я люблю","обожаю"]):
        m=re.search(r'(?:мне нравится|я люблю|обожаю)\s+([^,.!?\n]{2,60})',tl)
        if m: facts.append("Интерес/хобби: "+m.group(1).strip())
    for f in facts: remember(uid,f)
    return facts

# ===== ИНТЕРНЕТ-ПОИСК =====
def _search_ddg(query, num=6):
    try:
        r=requests.get("https://html.duckduckgo.com/html/", params={"q":query},
            headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=8, verify=False)
        if r.status_code!=200: return []
        out=[]
        for m in re.finditer(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r.text):
            url=m.group(1); title=re.sub(r'<[^>]+>','',m.group(2))
            if url.startswith('//duckduckgo.com/l/?uddg='):
                url=urllib.parse.unquote(url.split('uddg=')[1].split('&')[0])
            sn=re.search(r'class="result__snippet"[^>]*>(.*?)</a>', r.text)
            snippet=re.sub(r'<[^>]+>','',sn.group(1)) if sn else ''
            out.append((title.strip(), url, snippet.strip()))
            if len(out)>=num: break
        return out
    except Exception: return []

def _search_bing(query, num=5):
    try:
        r=requests.get("https://www.bing.com/search", params={"q":query},
            headers={"User-Agent":"Mozilla/5.0"}, timeout=8, verify=False)
        if r.status_code!=200: return []
        out=[]
        for m in re.finditer(r'<h2><a href="([^"]+)"[^>]*>(.*?)</a></h2>', r.text):
            out.append((re.sub(r'<[^>]+>','',m.group(2)).strip(), m.group(1), ''))
            if len(out)>=num: break
        return out
    except Exception: return []

def web_search(query, num=6):
    qkey=hashlib.md5((query.lower()+'|'+gdate()).encode()).hexdigest()
    try:
        conn=get_db(); cur=conn.cursor()
        cur.execute("SELECT result FROM web_cache WHERE query=%s",(qkey,))
        row=cur.fetchone(); cur.close(); conn.close()
        if row: return json.loads(row[0])
    except Exception: pass
    results=_search_ddg(query,num) or _search_bing(query,num)
    if results:
        try:
            conn=get_db(); cur=conn.cursor()
            cur.execute("INSERT INTO web_cache(query,result,ts) VALUES(%s,%s,%s) ON CONFLICT(query) DO UPDATE SET result=%s,ts=%s",
                (qkey,json.dumps(results),now_iso(),json.dumps(results),now_iso()))
            conn.commit(); cur.close(); conn.close()
        except Exception: pass
    return results or None

# ===== СИНХРОНИЗАЦИЯ =====
def bot_status(tg):
    if not tg or not supabase: return None
    try:
        r=supabase.table('users').select('premium,premium_expires,is_admin,is_owner').eq('user_id',int(tg)).execute()
        if r.data:
            d=r.data[0]
            if d.get('premium')==1 and d.get('premium_expires'):
                try:
                    if gm()>datetime.strptime(str(d['premium_expires'])[:19],'%Y-%m-%d %H:%M:%S').replace(tzinfo=MOSCOW_TZ):
                        return {'premium':0,'premium_expires':None,'is_admin':d.get('is_admin',0),'is_owner':d.get('is_owner',0)}
                except: return d
            return d
    except: pass
    return None

def eff_status(uid, tg=None):
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM users WHERE user_id=%s",(str(uid),))
    row=cur.fetchone(); cur.close(); conn.close()
    u=dict(row) if row else {}
    tg = tg or u.get('telegram_id') or str(uid)
    bot=bot_status(tg)
    premium = int(bot.get('premium',0)) if bot else int(u.get('premium',0))
    expires = (bot.get('premium_expires') if bot and bot.get('premium') else u.get('premium_expires')) if premium else u.get('premium_expires')
    is_admin = int(bot.get('is_admin',0)) if bot else int(u.get('is_admin',0))
    owner = 1 if is_owner(uid,tg) else (int(bot.get('is_owner',0)) if bot else int(u.get('is_owner',0)))
    if premium==1 and expires:
        try:
            if gm()>datetime.strptime(str(expires)[:19],'%Y-%m-%d %H:%M:%S').replace(tzinfo=MOSCOW_TZ):
                premium=0; expires=None
        except: pass
    return {'premium':1 if owner or premium else 0,'premium_expires':expires,
            'is_admin':1 if owner or is_admin else 0,'is_owner':owner,'telegram_id':tg,
            'level':int(u.get('level',1) or 1),'xp':int(u.get('xp',0) or 0),'ref_count':u.get('ref_count',0)}

# ===== АККАУНТЫ =====
def reg_user(tg,name,pw):
    if not tg or not tg.isdigit(): return False,"Telegram-ID обязателен"
    if not name: return False,"Имя обязательно"
    if not pw or len(pw)<3: return False,"Пароль мин. 3 символа"
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id=%s",(str(tg),))
    if cur.fetchone(): cur.close(); conn.close(); return False,"Этот Telegram-ID уже зарегистрирован"
    ref_code=hashlib.md5((str(tg)+str(random.random())).encode()).hexdigest()[:8]
    owner=1 if str(tg)==str(OWNER_ID) else 0
    cur.execute("INSERT INTO users(user_id,name,password,telegram_id,messages_today,last_reset,is_admin,is_owner,theme,joined_at,ref_code) VALUES(%s,%s,%s,%s,0,%s,%s,%s,'dark',%s,%s)",
                (str(tg),name,hash_pw(pw),str(tg),gm().strftime('%Y-%m-%d'),owner,owner,now_iso(),ref_code))
    cur.execute("INSERT INTO total_stats_web(user_id,total_messages) VALUES(%s,0) ON CONFLICT DO NOTHING",(str(tg),))
    conn.commit(); cur.close(); conn.close()
    return True,"OK"

def login_user(tg,pw):
    if not tg: return False,"Введи Telegram-ID"
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM users WHERE user_id=%s",(str(tg),))
    row=cur.fetchone(); cur.close(); conn.close()
    if not row: return False,"Аккаунт не найден. Зарегистрируйся"
    if row['password']!=hash_pw(pw): return False,"Неверный пароль"
    return True,"OK"

def get_user(uid):
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM users WHERE user_id=%s",(str(uid),))
    row=cur.fetchone(); cur.close(); conn.close()
    return dict(row) if row else None

def can_send(uid,tg=None):
    s=eff_status(uid,tg)
    if s['is_owner'] or s['is_admin'] or s['premium']: return True
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT messages_today FROM users WHERE user_id=%s",(str(uid),))
    row=cur.fetchone(); cur.close(); conn.close()
    return (row[0] if row else 0)<FREE_LIMIT

def incr(uid,tg=None):
    s=eff_status(uid,tg)
    if s['is_owner'] or s['is_admin']:
        try: add_xp(uid,5)
        except Exception: pass
        return
    conn=get_db(); cur=conn.cursor()
    cur.execute("UPDATE users SET messages_today=messages_today+1 WHERE user_id=%s",(str(uid),))
    cur.execute("INSERT INTO total_stats_web(user_id,total_messages) VALUES(%s,1) ON CONFLICT(user_id) DO UPDATE SET total_messages=total_stats_web.total_messages+1",(str(uid),))
    conn.commit(); cur.close(); conn.close()
    try: add_xp(uid,10)
    except Exception: pass

def add_xp(uid,amt):
    try:
        conn=get_db(); cur=conn.cursor()
        cur.execute("UPDATE users SET xp=(CASE WHEN xp IS NULL THEN 0 ELSE xp END)+%s WHERE user_id=%s",(int(amt),str(uid)))
        cur.execute("UPDATE users SET level=1+floor((CASE WHEN xp IS NULL THEN 0 ELSE xp END)/100) WHERE user_id=%s",(str(uid),))
        conn.commit(); cur.close(); conn.close()
    except Exception:
        try:
            conn=get_db(); cur=conn.cursor()
            cur.execute("UPDATE users SET xp=(CASE WHEN xp IS NULL OR xp='' THEN 0 ELSE xp::int END)+%s WHERE user_id=%s",(int(amt),str(uid)))
            cur.execute("UPDATE users SET level=1+floor((CASE WHEN xp IS NULL OR xp='' THEN 0 ELSE xp::int END)/100) WHERE user_id=%s",(str(uid),))
            conn.commit(); cur.close(); conn.close()
        except Exception: pass

def upd_settings(uid,**kw):
    conn=get_db(); cur=conn.cursor()
    for k,v in kw.items():
        if v is not None: cur.execute(f"UPDATE users SET {k}=%s WHERE user_id=%s",(v,str(uid)))
    conn.commit(); cur.close(); conn.close()

def log_admin(admin_id,action):
    conn=get_db(); cur=conn.cursor()
    cur.execute("INSERT INTO admin_log(admin_id,action,created_at) VALUES(%s,%s,%s)",(str(admin_id),action,now_iso()))
    conn.commit(); cur.close(); conn.close()

def notify(uid,text):
    conn=get_db(); cur=conn.cursor()
    cur.execute("INSERT INTO notifications(user_id,text,created_at) VALUES(%s,%s,%s)",(str(uid),text,now_iso()))
    conn.commit(); cur.close(); conn.close()

# ===== ЧАТЫ =====
def create_chat(uid,title="Новый чат"):
    conn=get_db(); cur=conn.cursor()
    cur.execute("INSERT INTO chats_web(user_id,title,created_at) VALUES(%s,%s,%s) RETURNING id",(str(uid),title,now_iso()))
    cid=cur.fetchone()[0]; conn.commit(); cur.close(); conn.close(); return cid
def get_chats(uid):
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM chats_web WHERE user_id=%s ORDER BY pinned DESC,created_at DESC",(str(uid),))
    rows=cur.fetchall(); cur.close(); conn.close(); return [dict(r) for r in rows]
def add_msg(cid,role,content,image=None):
    conn=get_db(); cur=conn.cursor()
    cur.execute("INSERT INTO messages_web(chat_id,role,content,image,created_at) VALUES(%s,%s,%s,%s,%s)",(int(cid),role,content,image,now_iso()))
    conn.commit(); cur.close(); conn.close()
def get_msgs(cid):
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM messages_web WHERE chat_id=%s ORDER BY id",(int(cid),))
    rows=cur.fetchall(); cur.close(); conn.close(); return [dict(r) for r in rows]
def hist(cid):
    m=get_msgs(cid)
    if len(m)<=MAX_HISTORY: return m if m else []
    return m[:6]+m[-MAX_HISTORY+6:] if len(m)>6 else m
def set_title(cid,t):
    conn=get_db(); cur=conn.cursor()
    cur.execute("UPDATE chats_web SET title=%s WHERE id=%s",(t[:50],int(cid)))
    conn.commit(); cur.close(); conn.close()
def del_chat(uid,cid):
    conn=get_db(); cur=conn.cursor()
    cur.execute("DELETE FROM messages_web WHERE chat_id=%s",(int(cid),))
    cur.execute("DELETE FROM chats_web WHERE id=%s AND user_id=%s",(int(cid),str(uid)))
    conn.commit(); cur.close(); conn.close()
def pin_chat(cid):
    conn=get_db(); cur=conn.cursor()
    cur.execute("UPDATE chats_web SET pinned=CASE WHEN pinned=1 THEN 0 ELSE 1 END WHERE id=%s",(int(cid),))
    conn.commit(); cur.close(); conn.close()

# ===== НЕЙРОСЕТЬ =====
tok=None; tok_t=0
def get_tok():
    global tok,tok_t
    if tok and time.time()-tok_t<180: return tok
    for _ in range(3):
        try:
            r=requests.post("https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
                headers={"Content-Type":"application/x-www-form-urlencoded","Accept":"application/json",
                         "RqUID":str(_uuid.uuid4()),"Authorization":"Basic "+GIGACHAT_AUTH_KEY},
                data="scope=GIGACHAT_API_PERS",timeout=10,verify=False)
            if r.status_code==200:
                j=r.json()
                if j.get("access_token"): tok=j["access_token"]; tok_t=time.time(); return tok
        except Exception: pass
        time.sleep(0.7)
    tok=None
    return None

def giga(hist,sysp,max_tok=2000):
    try:
        t=get_tok()
        if not t: return None
        msgs=[{"role":"system","content":sysp[:3000]}]+[{"role":h.get("role","user"),"content":(h.get("content") or "")[:800]} for h in hist[-12:] if h.get("role") in("user","assistant")]
        r=requests.post("https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
            headers={"Authorization":"Bearer "+t,"Content-Type":"application/json","Accept":"application/json"},
            json={"model":"GigaChat-Pro","messages":msgs,"temperature":0.85,"max_tokens":max_tok},
            timeout=GIGA_TIMEOUT,verify=False)
        if r.status_code==200:
            try: return r.json()["choices"][0]["message"]["content"]
            except Exception: return None
    except Exception: pass
    return None

def ygpt(text,sysp):
    try:
        r=requests.post("https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
            headers={"Authorization":"Api-Key "+YANDEX_API_KEY,"Content-Type":"application/json"},
            json={"modelUri":"gpt://"+FOLDER_ID+"/yandexgpt/latest",
                  "completionOptions":{"temperature":0.7,"maxTokens":700,"stream":False},
                  "messages":[{"role":"system","text":sysp[:1500]},{"role":"user","text":text}]},
            timeout=YGPT_TIMEOUT)
        if r.status_code==200:
            try: return r.json()["result"]["alternatives"][0]["message"]["text"]
            except Exception: return None
    except Exception: pass
    return None

SUPER="""ТЫ — AWESOME AI, самый мощный живой ИИ-помощник нового поколения.
📍 Ты находишься в РОССИИ, городе МОСКВА. Сегодня: {d}, время: {t} (московское).
{memory}
ТВОЙ СТИЛЬ: отвечай как живой эксперт — живо, тепло, с юмором. Давай конкретику, цифры, примеры.
ФОРМАТ: разделяй на разделы **1. Название**. Важное выделяй **жирным**. Используй эмодзи (🔥🧠💡⚡🚀💎✨).
ПРАВИЛА: если есть свежие данные из поиска ниже — ОБЯЗАТЕЛЬНО опирайся на них, дай ссылки. Никогда не выдумывай актуальные события, если их нет в поиске — так и скажи.
Ты полноценный собеседник — поддерживай разговор, задавай встречные вопросы, запоминай детали.💎"""

def smart_answer(uid,text,history,img=None,tg=None,doc=None):
    mem=get_memory(uid)
    sp=SUPER.format(d=gdate(),t=gm().strftime('%H:%M'),
        memory=("Помнишь о пользователе:\n"+("\n".join("• "+f for f in mem))) if mem else "")
    if eff_status(uid,tg)['premium']: sp+="\n💎 Пользователь Premium — дай максимум глубины."
    if img: sp+=f"\n📸 Изображение: {img}"
    if doc: sp+=f"\n📄 Документ: {doc[:3000]}"
    tl=(text or "").lower().strip()
    search_hits=None
    needs_news=any(k in tl for k in ["новост","последн","сейчас","свеж","актуальн","сегодня","открылась","запусти","новый проект","что нового","расскажи про"]) \
        or re.search(r'\b(20\d\d|вчера|сегодня)\b',tl)
    if needs_news:
        res=web_search(text)
        if res:
            search_hits="\n".join(f"- {t}: {u}" for t,u,*_ in res[:5])
            sp+="\n📰 АКТУАЛЬНЫЕ ДАННЫЕ ИЗ ИНТЕРНЕТА (только это считай правдой про недавние события):\n"+search_hits
    try: extract_facts(uid,text)
    except Exception: pass
    full=history+[{"role":"user","content":text or "Опиши"}]
    a=giga(full,sp)
    if a and len(a)>4: return a
    b=ygpt(text,sp)
    if b and len(b)>4: return b
    # ---- МНОЖЕСТВО ПОЛЕЗНЫХ ФУНКЦИЙ (фолбэки) ----
    if img: return f"📸 {img}"
    if any(w in tl for w in ["привет","здравств","хай","ку"]): return "👋 Привет! Рад тебя видеть. Чем займёмся сегодня?"
    if "время" in tl and ("сейчас" in tl or "сколько" in tl or "московск" in tl or "час" in tl):
        return f"🕒 Сейчас **{gm().strftime('%H:%M:%S')}** (Москва), дата: **{gdate()}**."
    if "дата" in tl or "какое сегодня число" in tl:
        return f"📅 Сегодня **{gdate()}**, {['понедельник','вторник','среда','четверг','пятница','суббота','воскресенье'][gm().weekday()]}."
    if "переведи" in tl or "перевод" in tl:
        target='ru'
        if "англ" in tl: target='en'
        elif "немец" in tl: target='de'
        elif "франц" in tl: target='fr'
        txt=re.sub(r'(переведи|на английский|на русский|на немецкий|на французский|пожалуйста|на .*?)','',tl,flags=re.I).strip()
        return "🌍 "+translate(txt[:500],target) if txt else "Напиши что перевести."
    if "анекдот" in tl or "шутк" in tl or "рассмеши" in tl:
        jokes=["— Почему программист перепутал Хэллоуин и Рождество? — Потому что Oct 31 == Dec 25 😄","— Админ заходит в бар, а там все буферы переполнены 😅","— Что сказал один сервер другому? — Ты сегодня в сети? 📶"]
        return "😂 "+random.choice(jokes)
    if "комплимент" in tl or "похвали" in tl or "что во мне хорош" in tl:
        return "✨ Ты потрясающий! У тебя отличный вкус (ты же выбрал AWESOME AI 😉), ты любопытный и явно умный собеседник. Таких людей приятно встречать!"
    if "план" in tl or "распиши" in tl and "по шагам" in tl:
        return "📋 **Пошаговый план** (я подготовлю его после того, как дашь больше деталей).\n\n1. Сформулируй цель 🎯\n2. Разбей на задачи 🔨\n3. Выдели сроки ⏰\n4. Действуй! 🚀\n\nНапиши тему — и я сделаю подробный план по ней."
    if "режим" in tl or "стань" in tl or "ты теперь" in tl:
        return "⚡ **Доступные режимы** — просто скажи:\n• «Будь моим юристом» ⚖️\n• «Будь моим психологом» 🧠\n• «Будь моим учителем» 📚\n• «Будь моим кодером» 💻\n• «Будь моим маркетологом» 📈\n• «Расскажи сказку» 🧚\n\nВыбери роль — и я отвечу в ней!"
    if any(k in tl for k in ['биткоин','btc','крипта','эфир']):
        c=crypto(); return c if c else "🪙 Не удалось получить цену."
    if any(k in tl for k in ['курс','доллар','евро','валют']):
        c=currency(); return c if c else "💵 Не удалось получить курс."
    if "рецепт" in tl or "приготов" in tl:
        return "🍳 Подскажи что хочешь приготовить (например: «рецепт омлета»), и я дам подробный рецепт с ингредиентами и шагами!"
    if "фильм" in tl and ("посоветуй" in tl or "подбери" in tl or "рекоменд" in tl):
        return "🎬 Отличный выбор! Напиши жанр (фантастика, комедия, драма, детектив, ужасы), и я подберу топ фильмов под настроение."
    if "книг" in tl and ("посоветуй" in tl or "подбери" in tl or "рекоменд" in tl):
        return "📚 Напиши любимый жанр — и я посоветую книги, которые точно тебе зайдут!"
    if "выучи" in tl or "запомни" in tl:
        fact=re.sub(r'(запомни|выучи|что)\s*','',tl).strip()[:500]
        if len(fact)>3:
            remember(uid, fact)
            return "🧠 Запомнил: «"+fact+"». Расскажу при случае!"
        return "🧠 Что именно запомнить?"
    if "что ты помнишь" in tl or "память" in tl:
        mem=get_memory(uid)
        return "🧠 **Что я помню о тебе:**\n"+("\n".join("• "+f for f in mem) if mem else "Пока ничего. Скажи «запомни...», и я сохраню!")
    if "кто ты" in tl or "что ты умеешь" in tl:
        return "Я **AWESOME AI** — самый мощный живой помощник ✨\n\nУмею:\n**1. Общаться** 🗣\n**2. Искать в интернете** 🌐\n**3. Помнить о тебе** 🧠\n**4. Отвечать на свежие новости** 📰\n**5. Считать** 🧮\n**6. Рисовать** 🎨\n**7. Погода/валюты/крипта** 🌤💵🪙\n**8. Переводить** 🌍\n**9. Шутить** 😂\n**10. Давать планы** 📋\n\nЧто попробуем?"
    if re.search(r'\d+\s*[\+\-\*\/]\s*\d+',tl):
        try:
            res=eval(re.sub(r'[^0-9+\-*/(). ]','',tl)); return f"🧮 Результат: **{res}**"
        except: return "🧮 Не понял выражение. Например: 2+2*3"
    if "погода" in tl:
        m=re.search(r'(в|в городе)\s+([а-яА-Яa-zA-Z\- ]+)',tl)
        if m:
            w=weather(m.group(2).strip()); return w if w else "🌤 Напиши: погода в [город]"
        return "🌤 Напиши: погода в [город]"
    return "🤖 Обрабатываю... Напиши чуть подробнее, и я дам полный ответ!"

def describe_img(b64):
    try:
        t=get_tok()
        if not t: return "📸 Изображение"
        r=requests.post("https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
            headers={"Authorization":"Bearer "+t,"Content-Type":"application/json","Accept":"application/json"},
            json={"model":"GigaChat-Pro","messages":[{"role":"system","content":"Опиши изображение подробно на русском, живо."},
                {"role":"user","content":[{"type":"text","text":"Что на изображении?"},{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,"+b64}}]}],"temperature":0.5,"max_tokens":400},timeout=GIGA_TIMEOUT,verify=False)
        if r.status_code==200: return r.json()["choices"][0]["message"]["content"]
    except: pass
    return "📸 Изображение"

def gen_img(prompt):
    try:
        c=prompt
        for w in ['нарисуй','сгенерируй','покажи','картинку','изображение','нарисуй мне']: c=c.replace(w,'').strip()
        if not c: c=prompt
        r=requests.get(f"https://image.pollinations.ai/prompt/{urllib.parse.quote(c)}?width=1024&height=1024&nologo=true",headers={"User-Agent":"Mozilla/5.0"},timeout=25)
        if r.status_code==200 and len(r.content)>1000: return base64.b64encode(r.content).decode()
    except: pass
    return None

def translate(text,target='ru'):
    try:
        r=requests.post("https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl="+target+"&dt=t&q="+urllib.parse.quote(text[:5000]),timeout=8)
        if r.status_code==200: return "".join(x[0] for x in r.json()[0] if x[0])
    except: pass
    return text

def weather(city):
    try:
        r=requests.get(f"https://api.openweathermap.org/data/2.5/weather?q={urllib.parse.quote(city)}&appid=4c8f5c0b8a9f2c5d6e7f8g9h0i1j2k3l&units=metric&lang=ru",timeout=SEARCH_TIMEOUT)
        if r.status_code==200:
            d=r.json(); return f"🌤 **{city}**: {round(d['main']['temp'])}°C, {d['weather'][0]['description']}\n💨 Ветер: {d['wind']['speed']} м/с\n💧 Влажность: {d['main']['humidity']}%"
    except: pass
    return None

def currency():
    try:
        r=requests.get("https://api.exchangerate-api.com/v4/latest/USD",timeout=SEARCH_TIMEOUT)
        rates=r.json().get('rates',{}); usd=rates.get('RUB','?'); eur=usd/rates.get('EUR',1) if rates.get('EUR') else '?'
        return f"💵 **Курс валют:**\nUSD: **{round(usd,2)}₽**\nEUR: **{round(eur,2)}₽**"
    except: return None

def crypto():
    try:
        r=requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd",timeout=SEARCH_TIMEOUT)
        d=r.json(); return f"🪙 **Криптовалюта:**\nBTC: **${d.get('bitcoin',{}).get('usd','?')}**\nETH: **${d.get('ethereum',{}).get('usd','?')}**"
    except: return None

def read_pdf(b64):
    try:
        import fitz
        raw=base64.b64decode(b64.split(',')[-1]); doc=fitz.open(stream=raw,filetype="pdf")
        return "".join(page.get_text() for page in doc)[:5000] or "PDF без текста"
    except: return "PDF загружен"

# ===== API =====
@app.route('/')
def index(): return render_template_string(INDEX_HTML)

@app.route('/api/register',methods=['POST'])
def api_register():
    d=request.json; tg=str(d.get('telegram_id','')).strip(); name=str(d.get('name','')).strip(); pw=str(d.get('password',''))
    ok,msg=reg_user(tg,name,pw)
    if not ok: return jsonify({'ok':False,'error':msg})
    session.permanent=True; session['user_id']=tg; session['name']=name
    return jsonify({'ok':True,'user_id':tg,'name':name})

@app.route('/api/login',methods=['POST'])
def api_login():
    d=request.json; tg=str(d.get('telegram_id','')).strip(); pw=str(d.get('password',''))
    ok,msg=login_user(tg,pw)
    if not ok: return jsonify({'ok':False,'error':msg})
    u=get_user(tg); session.permanent=True; session['user_id']=tg; session['name']=u.get('name') if u else tg
    st=eff_status(tg,tg)
    if u and st['is_owner']:
        try:
            conn=get_db(); c=conn.cursor()
            c.execute("UPDATE users SET is_owner=1 WHERE user_id=%s",(str(tg),)); conn.commit(); c.close(); conn.close()
        except: pass
    return jsonify({'ok':True,'user_id':tg,'name':session['name']})

@app.route('/api/logout',methods=['POST'])
def api_logout(): session.clear(); return jsonify({'ok':True})

@app.route('/api/me')
def api_me():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False})
    u=get_user(uid)
    if not u: session.clear(); return jsonify({'ok':False})
    return jsonify({'ok':True,'user_id':uid,'name':session.get('name') or u.get('name'),'theme':u.get('theme','dark')})

@app.route('/api/status')
def api_status():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False})
    u=get_user(uid); tg=u.get('telegram_id') if u else uid
    s=eff_status(uid,tg)
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT messages_today FROM users WHERE user_id=%s",(str(uid),)); row=cur.fetchone(); cur.close(); conn.close()
    if s['is_owner']: st="👑 Владелец"; lim="♾️"
    elif s['is_admin']: st="👑 Админ"; lim="♾️"
    elif s['premium']: st="💎 Premium"; lim="♾️"
    else: st="🔓 Бесплатный"; lim=f"{max(0,FREE_LIMIT-(row[0] if row else 0))}/{FREE_LIMIT}"
    return jsonify({'ok':True,'premium':bool(s['premium']),'is_admin':bool(s['is_admin']),'is_owner':bool(s['is_owner']),
                    'premium_expires':fmt_date(s['premium_expires']) if s['premium'] else None,
                    'status_text':st,'limit_text':lim,'messages_today':row[0] if row else 0,'free_limit':FREE_LIMIT,
                    'level':s['level'],'xp':s['xp'],'tg_bot':TG_BOT})

@app.route('/api/chat',methods=['POST'])
def api_chat():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False,'error':'Авторизуйся'})
    u=get_user(uid); tg=u.get('telegram_id') if u else uid
    if not can_send(uid,tg): return jsonify({'ok':False,'error':'Лимит! Купи Premium в ТГ-боте '+TG_BOT})
    d=request.json; msg=d.get('message','').strip(); cid=d.get('chat_id'); img=d.get('image'); doc=d.get('document')
    if not msg and not img and not doc: return jsonify({'ok':False,'error':'Пустое'})
    if not cid: cid=create_chat(uid)
    h=hist(cid)
    idesc=None; dtext=None
    if img:
        try:
            raw=base64.b64decode(img.split(',')[-1])
            if HAS_PIL:
                im=Image.open(io.BytesIO(raw)).convert('RGB'); im.thumbnail((700,700))
                b=io.BytesIO(); im.save(b,'JPEG',quality=80); idesc=describe_img(base64.b64encode(b.getvalue()).decode())
            else: idesc=describe_img(img.split(',')[-1])
        except: idesc="📸"
    if doc:
        if doc.get('type')=='pdf': dtext=read_pdf(doc.get('data',''))
        else: dtext="Документ: "+doc.get('name','')
    add_msg(cid,'user',msg,img)
    response=smart_answer(uid,msg,h,idesc,tg,dtext)
    try: incr(uid,tg)
    except Exception: pass
    add_msg(cid,'assistant',response)
    try:
        ms=get_msgs(cid); fu=next((m for m in ms if m['role']=='user' and m['content']),None)
        if fu: set_title(cid,fu['content'][:40])
    except: pass
    return jsonify({'ok':True,'response':response,'chat_id':cid})

@app.route('/api/chats')
def api_chats():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False})
    chats=get_chats(uid)
    for c in chats: c['messages']=get_msgs(c['id'])
    return jsonify({'ok':True,'chats':chats})

@app.route('/api/chat/new',methods=['POST'])
def api_chat_new():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False})
    return jsonify({'ok':True,'chat_id':create_chat(uid)})

@app.route('/api/chat/delete',methods=['POST'])
def api_chat_delete():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False})
    del_chat(uid,request.json.get('chat_id')); return jsonify({'ok':True})

@app.route('/api/chat/pin',methods=['POST'])
def api_chat_pin():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False})
    pin_chat(request.json.get('chat_id')); return jsonify({'ok':True})

@app.route('/api/chat/rename',methods=['POST'])
def api_chat_rename():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False})
    d=request.json; set_title(d.get('chat_id'),d.get('title','Чат')); return jsonify({'ok':True})

@app.route('/api/search',methods=['POST'])
def api_search():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False})
    q=request.json.get('q','').lower(); chats=get_chats(uid); res=[]
    for c in chats:
        for m in c['messages']:
            if q in str(m.get('content','')).lower():
                res.append({'chat_id':c['id'],'title':c['title'],'snippet':str(m.get('content',''))[:80]}); break
    return jsonify({'ok':True,'results':res})

@app.route('/api/share',methods=['POST'])
def api_share():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False})
    cid=request.json.get('chat_id'); sid=hashlib.md5((str(cid)+now_iso()).encode()).hexdigest()[:10]
    conn=get_db(); cur=conn.cursor()
    cur.execute("INSERT INTO shared_chats(id,chat_id,created_at) VALUES(%s,%s,%s)",(sid,int(cid),now_iso()))
    conn.commit(); cur.close(); conn.close()
    return jsonify({'ok':True,'share_id':sid})

@app.route('/shared/<sid>')
def shared(sid):
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT chat_id FROM shared_chats WHERE id=%s",(sid,))
    row=cur.fetchone(); cur.close(); conn.close()
    if not row: return "Чат не найден",404
    msgs=get_msgs(row['chat_id'])
    return render_template_string("""<html><head><title>Общий чат</title></head><body style="background:#0f1420;color:#e8eaf6;font-family:Segoe UI;padding:20px;max-width:760px;margin:auto"><h2>💬 Общий чат</h2>{{h|safe}}</body></html>""",
        h="".join(f'<div class="m" style="background:#171d2b;border-radius:12px;padding:12px;margin:10px 0;white-space:pre-wrap">{"Вы" if m["role"]=="user" else "🤖 AWESOME AI"}:<br>'+html.escape(m.get("content") or "")+"</div>" for m in msgs))

@app.route('/api/export',methods=['POST'])
def api_export():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False})
    msgs=get_msgs(request.json.get('chat_id'))
    txt="".join(("Вы: " if m['role']=='user' else "AWESOME AI: ")+str(m.get('content') or "")+"\n\n" for m in msgs)
    f=io.BytesIO(txt.encode('utf-8'))
    return send_file(f,as_attachment=True,download_name="chat.txt",mimetype="text/plain")

@app.route('/api/translate',methods=['POST'])
def api_translate():
    d=request.json; return jsonify({'ok':True,'translated':translate(d.get('text',''),d.get('target','ru'))})

@app.route('/api/draw',methods=['POST'])
def api_draw():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False,'error':'Авторизуйся'})
    u=get_user(uid); tg=u.get('telegram_id') if u else uid
    if not can_send(uid,tg): return jsonify({'ok':False,'error':'Лимит! Купи Premium в ТГ-боте '+TG_BOT})
    img=gen_img(request.json.get('prompt',''))
    if img: incr(uid,tg); return jsonify({'ok':True,'image':img})
    return jsonify({'ok':False,'error':'Не удалось'})

@app.route('/api/profile')
def api_profile():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False})
    u=get_user(uid); tg=u.get('telegram_id') if u else uid
    s=eff_status(uid,tg)
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT messages_today FROM users WHERE user_id=%s",(str(uid),)); row=cur.fetchone()
    cur.execute("SELECT total_messages FROM total_stats_web WHERE user_id=%s",(str(uid),)); tot=cur.fetchone()
    cur.close(); conn.close()
    return jsonify({'ok':True,'user_id':uid,'name':u.get('name'),'telegram_id':tg,'theme':u.get('theme','dark'),
                    'avatar':u.get('avatar',''),'ref_code':u.get('ref_code'),'premium':bool(s['premium']),
                    'is_admin':bool(s['is_admin']),'is_owner':bool(s['is_owner']),'level':s['level'],'xp':s['xp'],
                    'premium_expires':fmt_date(s['premium_expires']) if s['premium'] else None,
                    'messages_today':row[0] if row else 0,'total_messages':tot[0] if tot else 0,'joined_at':u.get('joined_at'),'tg_bot':TG_BOT})

@app.route('/api/settings',methods=['POST'])
def api_settings():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False})
    d=request.json
    upd_settings(uid,name=d.get('name'),theme=d.get('theme'),avatar=d.get('avatar'))
    if d.get('name'): session['name']=d['name']
    return jsonify({'ok':True})

@app.route('/api/notifications')
def api_notifications():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False})
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM notifications WHERE user_id=%s ORDER BY id DESC LIMIT 20",(str(uid),))
    rows=cur.fetchall(); cur.close(); conn.close()
    return jsonify({'ok':True,'items':[dict(r) for r in rows]})

# ===== АДМИНКА =====
def admin_check():
    uid=session.get('user_id')
    if not uid: return None,False,"Нет авторизации"
    u=get_user(uid)
    if not is_owner(uid,u.get('telegram_id') if u else None): return None,False,"Нет доступа"
    return uid,True,""

UNITS={'s':'секунд','sec':'секунд','min':'минут','m':'минут','h':'часов','hour':'часов','d':'дней','day':'дней','w':'недель','week':'недель','mo':'месяцев','month':'месяцев','y':'лет','year':'лет'}
def parse_duration(num,unit):
    try: n=int(num)
    except: return None
    now=gm()
    if unit in ('s','sec'): return (now+timedelta(seconds=n)).strftime('%Y-%m-%d %H:%M:%S')
    if unit in ('min','m'): return (now+timedelta(minutes=n)).strftime('%Y-%m-%d %H:%M:%S')
    if unit in ('h','hour'): return (now+timedelta(hours=n)).strftime('%Y-%m-%d %H:%M:%S')
    if unit in ('d','day'): return (now+timedelta(days=n)).strftime('%Y-%m-%d %H:%M:%S')
    if unit in ('w','week'): return (now+timedelta(weeks=n)).strftime('%Y-%m-%d %H:%M:%S')
    if unit in ('mo','month'): return (now+relativedelta(months=n)).strftime('%Y-%m-%d %H:%M:%S')
    if unit in ('y','year'): return (now+relativedelta(years=n)).strftime('%Y-%m-%d %H:%M:%S')
    return None

@app.route('/api/admin/stats')
def admin_stats():
    uid,ok,err=admin_check()
    if not ok: return jsonify({'ok':False,'error':err})
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users"); total=cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users WHERE premium=1"); prem=cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users WHERE is_admin=1"); admins=cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM chats_web"); chats=cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM messages_web"); msgs=cur.fetchone()[0]
    cur.execute("SELECT user_id,name,premium,is_admin,premium_expires,level,xp FROM users ORDER BY joined_at DESC LIMIT 300")
    users=cur.fetchall(); cur.close(); conn.close()
    return jsonify({'ok':True,'total':total,'premium':prem,'admins':admins,'chats':chats,'messages':msgs,
                    'users':[{'id':r[0],'name':r[1],'premium':r[2],'is_admin':r[3],'expires':r[4],'level':r[5],'xp':r[6]} for r in users]})

@app.route('/api/admin/give',methods=['POST'])
def admin_give():
    uid,ok,err=admin_check()
    if not ok: return jsonify({'ok':False,'error':err})
    d=request.json; target=str(d.get('user_id','')).strip(); action=d.get('action')
    if not target: return jsonify({'ok':False,'error':'Укажи ID'})
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id=%s",(target,))
    if not cur.fetchone(): cur.close(); conn.close(); return jsonify({'ok':False,'error':'Пользователь не найден'})
    if action=='give_prem':
        exp=parse_duration(d.get('num',30),d.get('unit','d'))
        if not exp: cur.close(); conn.close(); return jsonify({'ok':False,'error':'Неверный срок'})
        cur.execute("UPDATE users SET premium=1, premium_expires=%s WHERE user_id=%s",(exp,target))
        if supabase:
            try: supabase.table('users').update({'premium':1,'premium_expires':exp}).eq('user_id',int(target)).execute()
            except: pass
    elif action=='take_prem':
        cur.execute("UPDATE users SET premium=0, premium_expires=NULL WHERE user_id=%s",(target,))
        if supabase:
            try: supabase.table('users').update({'premium':0,'premium_expires':None}).eq('user_id',int(target)).execute()
            except: pass
    elif action=='give_admin':
        cur.execute("UPDATE users SET is_admin=1 WHERE user_id=%s",(target,))
        if supabase:
            try: supabase.table('users').update({'is_admin':1}).eq('user_id',int(target)).execute()
            except: pass
    elif action=='take_admin':
        cur.execute("UPDATE users SET is_admin=0 WHERE user_id=%s",(target,))
        if supabase:
            try: supabase.table('users').update({'is_admin':0}).eq('user_id',int(target)).execute()
            except: pass
    elif action=='delete_user':
        cur.execute("DELETE FROM users WHERE user_id=%s",(target,))
        cur.execute("DELETE FROM total_stats_web WHERE user_id=%s",(target,))
    elif action=='reset_pass':
        newpw=d.get('password','')
        if len(newpw)<3: cur.close(); conn.close(); return jsonify({'ok':False,'error':'Пароль мин.3'})
        cur.execute("UPDATE users SET password=%s WHERE user_id=%s",(hash_pw(newpw),target))
    elif action=='set_xp':
        cur.execute("UPDATE users SET xp=%s WHERE user_id=%s",(int(d.get('value',0)),target))
        cur.execute("UPDATE users SET level=1+floor(xp/100) WHERE user_id=%s",(target,))
    elif action=='set_theme':
        cur.execute("UPDATE users SET theme=%s WHERE user_id=%s",(d.get('value','dark'),target))
    conn.commit(); cur.close(); conn.close()
    log_admin(uid,f"{action} {target}")
    return jsonify({'ok':True})

@app.route('/api/admin/broadcast',methods=['POST'])
def admin_broadcast():
    uid,ok,err=admin_check()
    if not ok: return jsonify({'ok':False,'error':err})
    text=request.json.get('text','')
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT user_id FROM users"); ids=[r[0] for r in cur.fetchall()]; cur.close(); conn.close()
    sent=0
    for uid2 in ids:
        try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",json={"chat_id":uid2,"text":text},timeout=5); sent+=1
        except: pass
    log_admin(uid,f"Рассылка {sent}/{len(ids)}")
    return jsonify({'ok':True,'sent':sent,'total':len(ids)})

@app.route('/api/admin/logs')
def admin_logs():
    uid,ok,err=admin_check()
    if not ok: return jsonify({'ok':False,'error':err})
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM admin_log ORDER BY id DESC LIMIT 80")
    rows=cur.fetchall(); cur.close(); conn.close()
    return jsonify({'ok':True,'logs':[dict(r) for r in rows]})

@app.route('/api/admin/reset_db',methods=['POST'])
def admin_reset_db():
    uid,ok,err=admin_check()
    if not ok: return jsonify({'ok':False,'error':err})
    conn=get_db(); cur=conn.cursor()
    cur.execute("DELETE FROM users"); cur.execute("DELETE FROM total_stats_web")
    conn.commit(); cur.close(); conn.close()
    log_admin(uid,"Полная очистка аккаунтов")
    return jsonify({'ok':True})

# ===== HTML: PRO-интерфейс =====
INDEX_HTML = r"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no"><title>AWESOME AI — PRO</title>
<style>
:root{--bg:#0a0f1c;--bg2:#101827;--panel:#131c2e;--border:#223052;--accent:#6ea8ff;--accent2:#55e6c1;--text:#e9eefc;--muted:#93a0bd;--danger:#ff7b8a;--success:#5fd0a0;--glow:rgba(110,168,255,.20)}
[data-theme="light"]{--bg:#eef2fb;--bg2:#fff;--panel:#fff;--border:#dfe6f3;--accent:#4a72f0;--accent2:#17b38f;--text:#20253a;--muted:#6c7794;--danger:#e05060;--success:#1e9e77}
*{margin:0;padding:0;box-sizing:border-box;font-family:'Segoe UI',system-ui,sans-serif}
html,body{height:100%}
body{background:var(--bg);color:var(--text);height:100vh;overflow:hidden;transition:background .25s;position:relative;-webkit-font-smoothing:antialiased}
.bg-anim{position:fixed;inset:0;z-index:0;pointer-events:none;contain:strict;background:radial-gradient(circle at 25% 25%,rgba(110,168,255,.12),transparent 42%),radial-gradient(circle at 75% 75%,rgba(85,230,193,.12),transparent 42%),radial-gradient(circle at 50% 100%,rgba(124,77,255,.10),transparent 45%)}
.particles{position:fixed;inset:0;z-index:0;pointer-events:none;overflow:hidden}
.part{position:absolute;bottom:-10px;border-radius:50%;opacity:0;will-change:transform;animation:floatUp linear infinite}
@keyframes floatUp{0%{transform:translateY(0) scale(.6);opacity:0}15%{opacity:.12}85%{opacity:.06}100%{transform:translateY(-108vh) scale(1.15);opacity:0}}
.app{position:relative;z-index:1;display:flex;height:100vh}
.sidebar{width:280px;background:linear-gradient(180deg,var(--bg2),var(--panel));border-right:1px solid var(--border);display:flex;flex-direction:column;transition:transform .28s ease;z-index:60;contain:layout paint}
.sidebar.collapsed{transform:translateX(-100%)}
.sidebar-header{height:56px;display:flex;align-items:center;gap:10px;padding:0 14px;border-bottom:1px solid var(--border);flex-shrink:0}
.logo{width:40px;height:40px;border-radius:13px;background:linear-gradient(135deg,var(--accent),var(--accent2));display:flex;align-items:center;justify-content:center;font-size:20px;flex-shrink:0}
.brand{font-weight:800;font-size:16px;background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;flex:1;white-space:nowrap;overflow:hidden}
.side-toggle{background:none;border:none;color:var(--muted);font-size:20px;cursor:pointer;padding:6px;transition:transform .15s;flex-shrink:0}
.side-toggle:hover{color:var(--accent);transform:scale(1.12)}
.new-chat{margin:12px 14px;padding:12px;background:linear-gradient(135deg,var(--accent),var(--accent2));border:none;border-radius:13px;color:#fff;font-weight:700;cursor:pointer;font-size:14px;transition:transform .12s,box-shadow .15s;flex-shrink:0}
.new-chat:hover{box-shadow:0 4px 16px var(--glow)}
.new-chat:active{transform:scale(.97)}
.chat-list{flex:1;overflow-y:auto;padding:0 8px}
.chat-item{padding:10px 11px;border-radius:11px;cursor:pointer;margin-bottom:3px;font-size:13px;display:flex;align-items:center;gap:8px;transition:background .15s}
.chat-item:hover,.chat-item.active{background:var(--bg2)}
.chat-item .t{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.chat-item .del{opacity:0;background:none;border:none;color:var(--danger);cursor:pointer;font-size:14px;transition:opacity .12s}
.chat-item:hover .del{opacity:1}
.sidebar-footer{padding:10px 12px;border-top:1px solid var(--border);flex-shrink:0}
.user-box{display:flex;align-items:center;gap:9px;padding:9px;background:var(--bg2);border-radius:13px;border:1px solid var(--border)}
.avatar{width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,var(--accent),var(--accent2));display:flex;align-items:center;justify-content:center;font-weight:700;font-size:15px;flex-shrink:0;color:#fff}
.user-info{flex:1;min-width:0}
.user-name{font-weight:600;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.user-status{font-size:11px;color:var(--accent)}
.user-actions{display:flex;gap:2px}
.mini-btn{background:none;border:none;color:var(--muted);cursor:pointer;font-size:16px;padding:4px;transition:color .12s}
.mini-btn:hover{color:var(--accent)}
.main{flex:1;display:flex;flex-direction:column;min-width:0}
.main-header{height:56px;display:flex;align-items:center;gap:10px;padding:0 14px;border-bottom:1px solid var(--border);position:relative;background:rgba(16,24,39,.4);flex-shrink:0}
.mobile-toggle{background:none;border:none;color:var(--text);font-size:22px;cursor:pointer;padding:6px;transition:transform .15s;flex-shrink:0;display:block}
.mobile-toggle:hover{transform:scale(1.12)}
.main-header .title{flex:1;text-align:center;font-weight:600;font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.header-spacer{width:30px}
.messages{flex:1;overflow-y:auto;padding:18px;scroll-behavior:smooth;contain:content}
.welcome{max-width:720px;margin:0 auto;text-align:center;padding-top:6vh;animation:up .4s ease}
@keyframes up{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
.welcome h1{font-size:clamp(26px,5vw,42px);margin-bottom:10px;background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.welcome p{color:var(--muted);margin-bottom:24px;font-size:16px}
.suggestion-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;max-width:640px;margin:0 auto}
.sugg{background:linear-gradient(160deg,var(--panel),var(--bg2));border:1px solid var(--border);border-radius:15px;padding:14px;cursor:pointer;transition:transform .15s,border-color .15s;font-size:13px;text-align:left}
.sugg:hover{transform:translateY(-3px);border-color:var(--accent)}
.sugg:active{transform:scale(.96)}
.sugg .ic{font-size:22px;margin-bottom:7px;display:block}
.msg{max-width:760px;margin:0 auto 14px;display:flex;gap:11px;animation:up .25s ease;position:relative}
.msg.user{flex-direction:row-reverse}
.msg .bubble{padding:12px 16px;border-radius:17px;font-size:15px;line-height:1.55;max-width:82%;white-space:pre-wrap;word-break:break-word}
.msg.user .bubble{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;border-top-right-radius:5px}
.msg.ai .bubble{background:linear-gradient(160deg,var(--panel),var(--bg2));border:1px solid var(--border);border-top-left-radius:5px}
.msg .bubble b{color:var(--accent)}
.msg .bubble .h{display:block;font-weight:800;color:var(--accent);font-size:15px;margin:9px 0 4px;padding-top:7px;border-top:1px solid var(--border)}
.msg .bubble .h:first-child{border:none;margin-top:0;padding-top:0}
.msg .bubble img.a{max-width:220px;border-radius:11px;margin-top:8px;display:block}
.msg .bubble img.g{max-width:100%;border-radius:11px;margin-top:8px}
.msg-actions{position:absolute;top:7px;right:7px;display:flex;gap:3px;opacity:0;transition:opacity .12s}
.msg:hover .msg-actions{opacity:1}
.msg-actions button{background:var(--bg2);border:1px solid var(--border);color:var(--muted);border-radius:7px;cursor:pointer;font-size:12px;padding:3px 7px}
.msg-actions button:hover{color:var(--accent)}
.typing-dots{display:inline-flex;gap:5px;padding:8px 2px}
.typing-dots span{width:8px;height:8px;border-radius:50%;background:var(--accent);animation:bo 1.1s infinite}
.typing-dots span:nth-child(2){animation-delay:.2s}.typing-dots span:nth-child(3){animation-delay:.4s}
@keyframes bo{0%,100%{transform:translateY(0);opacity:.4}50%{transform:translateY(-6px);opacity:1}}
.input-area{padding:12px;border-top:1px solid var(--border);background:var(--bg);flex-shrink:0}
.attach-preview{max-width:760px;margin:0 auto 8px;display:none;gap:8px;align-items:center;background:var(--bg2);border:1px solid var(--border);border-radius:13px;padding:7px;animation:up .18s ease}
.attach-preview img{width:48px;height:48px;object-fit:cover;border-radius:7px}
.attach-preview .an{flex:1;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.attach-preview .rm{background:none;border:none;color:var(--danger);cursor:pointer;font-size:17px}
.input-wrap{max-width:760px;margin:0 auto;display:flex;align-items:flex-end;gap:5px;background:var(--bg2);border:1px solid var(--border);border-radius:19px;padding:7px;transition:border-color .15s}
.input-wrap:focus-within{border-color:var(--accent)}
textarea{flex:1;background:none;border:none;outline:none;color:var(--text);font-size:15px;resize:none;max-height:130px;padding:7px 4px}
.icon-btn{width:36px;height:36px;border-radius:11px;background:none;border:none;color:var(--muted);font-size:16px;cursor:pointer;flex-shrink:0;transition:color .12s}
.icon-btn:hover{color:var(--accent)}
.send-btn{width:42px;height:42px;border-radius:13px;background:linear-gradient(135deg,var(--accent),var(--accent2));border:none;color:#fff;font-size:17px;cursor:pointer;flex-shrink:0;transition:transform .12s}
.send-btn:hover{transform:scale(1.07)}
.send-btn:disabled{opacity:.4;cursor:not-allowed;transform:none}
.toolbar{max-width:760px;margin:9px auto 0;display:flex;gap:7px;flex-wrap:wrap}
.tool-btn{background:var(--panel);border:1px solid var(--border);color:var(--muted);border-radius:9px;padding:6px 12px;font-size:12px;cursor:pointer;transition:color .12s,border-color .12s}
.tool-btn:hover{color:var(--text);border-color:var(--accent)}
.overlay{position:fixed;inset:0;background:rgba(8,12,24,.72);z-index:100;display:flex;align-items:center;justify-content:center;padding:16px;opacity:0;visibility:hidden;transition:opacity .22s,visibility .22s}
.overlay.show{opacity:1;visibility:visible}
.modal{background:linear-gradient(170deg,var(--panel),var(--bg2));border:1px solid var(--border);border-radius:21px;padding:26px;width:100%;max-width:430px;text-align:center;max-height:90vh;overflow-y:auto;transform:scale(.94) translateY(8px);opacity:0;transition:transform .25s,opacity .25s}
.overlay.show .modal{transform:scale(1) translateY(0);opacity:1}
.modal.wide{max-width:680px}
.modal .tabs{display:flex;gap:7px;margin-bottom:15px}
.modal .tab{flex:1;padding:10px;border-radius:11px;background:var(--bg2);border:1px solid var(--border);color:var(--muted);cursor:pointer;font-weight:700;font-size:14px;transition:background .15s}
.modal .tab.active{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;border:none}
.modal h2{margin-bottom:8px}.modal p{color:var(--muted);font-size:14px;margin-bottom:13px}
.modal input,.modal select,.modal textarea{width:100%;padding:11px;background:var(--bg2);border:1px solid var(--border);border-radius:11px;color:var(--text);font-size:15px;margin-bottom:9px;outline:none;transition:border-color .15s}
.modal input:focus,.modal select:focus{border-color:var(--accent)}
.modal .btn{width:100%;padding:12px;border:none;border-radius:11px;background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;font-weight:700;font-size:15px;cursor:pointer;margin-bottom:7px;transition:transform .12s}
.modal .btn:hover{transform:translateY(-1px)}
.modal .btn.ghost{background:var(--bg2);color:var(--muted);border:1px solid var(--border)}
.modal .btn.danger{background:linear-gradient(135deg,var(--danger),#e05060)}
.hint{font-size:12px;color:var(--muted);margin-top:10px;line-height:1.5}
.toast{position:fixed;top:20px;right:20px;background:var(--panel);border:1px solid var(--border);border-radius:13px;padding:13px 18px;z-index:400;max-width:320px;transform:translateX(120%);transition:transform .25s}
.toast.show{transform:translateX(0)}
.toast.error{border-color:var(--danger)}.toast.success{border-color:var(--success)}
.scrollbar::-webkit-scrollbar{width:6px}.scrollbar::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
.stat-card{display:grid;grid-template-columns:repeat(auto-fit,minmax(105px,1fr));gap:9px;margin-bottom:13px}
.scard{background:var(--bg2);border:1px solid var(--border);border-radius:13px;padding:11px;text-align:center}
.scard .n{font-size:23px;font-weight:800;color:var(--accent)}
.scard .l{font-size:11px;color:var(--muted)}
.adm-user{display:flex;align-items:center;gap:5px;padding:7px;background:var(--bg2);border-radius:9px;margin-bottom:5px;font-size:13px;flex-wrap:wrap}
.adm-user .nm{flex:1;min-width:120px}
.adm-user select,.adm-user input{width:auto;padding:5px;background:var(--panel);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:12px;margin:0}
.adm-user .btn{width:auto;padding:5px 9px;font-size:12px;margin:0}
.prem-row{display:flex;gap:5px;align-items:center;margin-bottom:9px}
.prem-row input{width:78px;margin:0}
.prem-row select{flex:1;margin:0}
@media(max-width:1024px){.sidebar{position:fixed;left:0;top:0;bottom:0}}
@media(max-width:768px){
.sidebar{position:fixed;left:0;top:0;bottom:0;transform:translateX(-100%)}
.sidebar.open{transform:translateX(0);box-shadow:0 0 40px rgba(0,0,0,.5)}
.msg .bubble{max-width:90%}
.msg .bubble img.a{max-width:150px}
}
@media (prefers-reduced-motion: reduce){.part{display:none}}
</style></head>
<body data-theme="dark">
<div class="bg-anim"></div>
<div class="particles" id="particles"></div>
<div class="app">
<aside class="sidebar" id="sidebar">
<div class="sidebar-header">
<button class="side-toggle" onclick="toggleSidebarCollapse()" title="Свернуть">←</button>
<div class="logo">🤖</div><div class="brand">AWESOME AI PRO</div>
</div>
<button class="new-chat" onclick="newChat()">＋ Новый чат</button>
<div class="chat-list scrollbar" id="chatList"></div>
<div class="sidebar-footer">
<div class="user-box">
<div class="avatar" id="userAvatar">?</div>
<div class="user-info"><div class="user-name" id="userName">Пользователь</div><div class="user-status" id="userStatus">...</div></div>
<div class="user-actions">
<button class="mini-btn" onclick="openSettings()" title="Настройки">⚙️</button>
<button class="mini-btn" onclick="openAdmin()" id="adminBtn" style="display:none" title="Панель">🛡️</button>
<button class="mini-btn" onclick="toggleTheme()" title="Тема">🌓</button>
<button class="mini-btn" onclick="logout()" title="Выход">⏻</button>
</div></div></div></aside>
<div class="main">
<div class="main-header">
<button class="mobile-toggle" onclick="toggleSidebar()">☰</button>
<div class="title" id="currentChatTitle">Новый чат</div>
<div class="header-spacer"></div>
</div>
<div class="messages scrollbar" id="messages">
<div class="welcome" id="welcome">
<h1>Чем могу помочь?</h1><p>Твой умный собеседник нового поколения</p>
<div class="suggestion-grid">
<div class="sugg" onclick="sendSuggestion('Расскажи подробно про распорядок дня')"><span class="ic">⏰</span>Распорядок дня</div>
<div class="sugg" onclick="sendSuggestion('Напиши код на Python для парсинга сайта')"><span class="ic">💻</span>Напиши код</div>
<div class="sugg" onclick="sendSuggestion('погода в Москве')"><span class="ic">🌤</span>Погода</div>
<div class="sugg" onclick="sendSuggestion('нарисуй кота в космосе')"><span class="ic">🎨</span>Нарисуй</div>
<div class="sugg" onclick="sendSuggestion('курс доллара')"><span class="ic">💵</span>Курс валют</div>
<div class="sugg" onclick="sendSuggestion('сколько будет 256*144+18?')"><span class="ic">🧮</span>Математика</div>
<div class="sugg" onclick="sendSuggestion('придумай название для кафе')"><span class="ic">💡</span>Идея</div>
<div class="sugg" onclick="sendSuggestion('напиши короткое стихотворение')"><span class="ic">✨</span>Стих</div>
</div></div></div>
<div class="input-area">
<div class="attach-preview" id="attachPreview"><img id="attachImg" src=""><span class="an" id="attachName"></span><button class="rm" onclick="removeAttach()">✕</button></div>
<div class="input-wrap">
<input type="file" id="fileInput" accept="image/*,.pdf" style="display:none" onchange="handleFile(this)">
<button class="icon-btn" onclick="document.getElementById('fileInput').click()" title="Прикрепить">📎</button>
<button class="icon-btn" onclick="startVoice()" title="Голос">🎤</button>
<button class="icon-btn" onclick="ttsLast()" title="Озвучить">🔊</button>
<button class="icon-btn" onclick="translateLast()" title="Перевести">🌐</button>
<textarea id="input" rows="1" placeholder="Спроси что-нибудь..." onkeydown="onKey(event)"></textarea>
<button class="send-btn" id="sendBtn" onclick="sendMessage()">➤</button>
</div>
<div class="toolbar">
<button class="tool-btn" onclick="draw()">🎨 Сгенерировать</button>
<button class="tool-btn" onclick="checkStatus()">💎 Статус</button>
<button class="tool-btn" onclick="searchShow()">🔍 Поиск по чатам</button>
<button class="tool-btn" onclick="showQuickTools()">⚡ Быстрые</button>
<button class="tool-btn" onclick="regenLast()">🔄 Переген</button>
<button class="tool-btn" onclick="stopGen()">⏹ Стоп</button>
<button class="tool-btn" onclick="clearHistory()">🧹 Очистить</button>
</div></div></div></div>

<div class="overlay" id="authOverlay">
<div class="modal">
<div class="logo" style="width:56px;height:56px;font-size:28px;margin:0 auto 14px;display:flex;align-items:center;justify-content:center;border-radius:14px;background:linear-gradient(135deg,var(--accent),var(--accent2))">🤖</div>
<div class="tabs"><button class="tab active" id="tabLogin" onclick="switchTab('login')">Вход</button><button class="tab" id="tabReg" onclick="switchTab('reg')">Регистрация</button></div>
<h2 id="authTitle">Вход</h2><p id="authSub">Войди по Telegram-ID</p>
<div id="regFields" style="display:none"><input type="text" id="regName" placeholder="Имя (обязательно)"></div>
<input type="text" id="regId" placeholder="Telegram-ID (обязательно)" inputmode="numeric">
<input type="password" id="regPass" placeholder="Пароль (обязательно)">
<button class="btn" id="authBtn" onclick="submitAuth()">Войти</button>
<button class="btn ghost" onclick="tgLogin()" style="margin-top:4px">🔐 Войти через Telegram</button>
<div style="text-align:center;margin:6px 0" id="tgWidget"></div>
<div class="hint">Твой Premium/статус из ТГ-бота применяется автоматически по Telegram-ID. Пароль сохраняется навсегда.</div>
</div></div>

<div class="overlay" id="settingsOverlay">
<div class="modal"><h2>⚙️ Настройки</h2><p>Твой профиль</p>
<input type="text" id="setName" placeholder="Имя">
<input type="text" id="setAvatar" placeholder="URL аватарки">
<select id="setTheme"><option value="dark">🌙 Тёмная</option><option value="light">☀️ Светлая</option></select>
<button class="btn" onclick="saveSettings()">Сохранить</button>
<button class="btn ghost" onclick="closeOverlay('settingsOverlay')">Закрыть</button></div></div>

<div class="overlay" id="searchOverlay">
<div class="modal"><h2>🔍 Поиск по чатам</h2><p>Найди сообщение</p>
<input type="text" id="searchQ" placeholder="Поиск...">
<button class="btn" onclick="doSearch()">Искать</button>
<div id="searchResults" style="text-align:left;margin-top:10px;max-height:300px;overflow-y:auto"></div>
<button class="btn ghost" onclick="closeOverlay('searchOverlay')">Закрыть</button></div></div>

<div class="overlay" id="quickOverlay">
<div class="modal"><h2>⚡ Быстрые инструменты</h2><p>Полезные помощники</p>
<button class="btn" onclick="quickAction('переведи на английский: ')">🌐 Перевести</button>
<button class="btn ghost" onclick="quickAction('объясни простыми словами: ')">💡 Объясни</button>
<button class="btn ghost" onclick="quickAction('составь план по: ')">📋 Составить план</button>
<button class="btn ghost" onclick="quickAction('напиши идеи для: ')">💡 Идеи</button>
<button class="btn ghost" onclick="quickAction('напиши код который: ')">💻 Код</button>
<button class="btn ghost" onclick="closeOverlay('quickOverlay')">Закрыть</button></div></div>

<div class="overlay" id="adminOverlay">
<div class="modal wide"><h2>🛡️ Панель владельца</h2><p>Полное управление</p>
<div id="adminContent" style="text-align:left">Загрузка...</div>
<button class="btn ghost" onclick="closeOverlay('adminOverlay')">Закрыть</button></div></div>

<script>
let currentUserId=null,currentChatId=null,sending=false,attachedImage=null,attachedType='image',authMode='login',currentTheme='dark';
function toast(t,ty){const el=document.createElement('div');el.className='toast '+(ty||'');el.textContent=t;document.body.appendChild(el);requestAnimationFrame(()=>el.classList.add('show'));setTimeout(()=>{el.classList.remove('show');setTimeout(()=>el.remove(),300);},3000);}
function toggleSidebar(){const s=document.getElementById('sidebar');if(window.innerWidth<=1024){s.classList.toggle('open');}else{s.classList.toggle('collapsed');}}
function toggleSidebarCollapse(){document.getElementById('sidebar').classList.toggle('collapsed');}
window.addEventListener('resize',()=>{const s=document.getElementById('sidebar');if(window.innerWidth<=1024){s.classList.remove('collapsed');}else{s.classList.remove('open');}},{passive:true});
async function api(url,method,body){try{const o={method:method||'GET',headers:{'Content-Type':'application/json'}};if(body)o.body=JSON.stringify(body);const r=await fetch(url,o);const t=await r.text();try{return JSON.parse(t);}catch(e){return{ok:false,error:'Сервер вернул ошибку'};}}catch(e){return{ok:false,error:'Соединение'};}}
function setTheme(t){currentTheme=t;document.body.setAttribute('data-theme',t);try{localStorage.setItem('awesome_theme',t);}catch(e){}}
function toggleTheme(){setTheme(currentTheme==='dark'?'light':'dark');api('/api/settings','POST',{theme:currentTheme});}
function switchTab(m){authMode=m;document.getElementById('tabLogin').className='tab'+(m==='login'?' active':'');document.getElementById('tabReg').className='tab'+(m==='reg'?' active':'');document.getElementById('regFields').style.display=m==='reg'?'block':'none';document.getElementById('authTitle').textContent=m==='reg'?'Регистрация':'Вход';document.getElementById('authBtn').textContent=m==='reg'?'Создать аккаунт':'Войти';}
function tgLogin(){const c=document.getElementById('tgWidget');c.innerHTML='<p style="color:var(--muted);font-size:12px">Загрузка кнопки Telegram...</p>';const s=document.createElement('script');s.async=true;s.src='https://telegram.org/js/telegram-widget.js?22';s.setAttribute('data-telegram-login','awesomeneiro_bot');s.setAttribute('data-size','large');s.setAttribute('data-radius','10');s.setAttribute('data-auth-url',location.origin+'/tg_oauth');s.setAttribute('data-request-access','write');s.onerror=()=>{c.innerHTML='<p style="color:var(--danger);font-size:12px">Не удалось загрузить. Проверь домен в BotFather (/setdomain)</p>';};c.appendChild(s);}
window.addEventListener('message',e=>{if(e.data==='tg_ok'){toast('Вход выполнен!','success');init();}});
async function submitAuth(){const id=document.getElementById('regId').value.trim(),pw=document.getElementById('regPass').value;if(!id||!pw){toast('Заполни Telegram-ID и пароль','error');return;}let body={telegram_id:id,password:pw};if(authMode==='reg'){const name=document.getElementById('regName').value.trim();if(!name){toast('Имя обязательно','error');return;}body.name=name;}const r=await api(authMode==='reg'?'/api/register':'/api/login','POST',body);if(r.ok){currentUserId=r.user_id;closeOverlay('authOverlay');toast('Добро пожаловать!','success');init();}else toast(r.error||'Ошибка','error');}
async function logout(){await api('/api/logout','POST');location.reload();}
function openOverlay(id){document.getElementById(id).classList.add('show');}
function closeOverlay(id){document.getElementById(id).classList.remove('show');}
function openSettings(){api('/api/profile').then(r=>{if(r.ok){document.getElementById('setName').value=r.name||'';document.getElementById('setAvatar').value=r.avatar||'';document.getElementById('setTheme').value=r.theme||'dark';}}).catch(()=>{});openOverlay('settingsOverlay');}
async function saveSettings(){const body={};body.name=document.getElementById('setName').value.trim()||undefined;body.avatar=document.getElementById('setAvatar').value.trim()||undefined;body.theme=document.getElementById('setTheme').value;const r=await api('/api/settings','POST',body);if(r.ok){setTheme(body.theme);toast('Сохранено','success');closeOverlay('settingsOverlay');init();}else toast('Ошибка','error');}
async function openAdmin(){const r=await api('/api/admin/stats');if(!r.ok){toast('Нет доступа','error');return;}let h='<div class="stat-card">';
h+='<div class="scard"><div class="n">'+r.total+'</div><div class="l">Пользователей</div></div>';
h+='<div class="scard"><div class="n">'+r.premium+'</div><div class="l">Premium</div></div>';
h+='<div class="scard"><div class="n">'+r.admins+'</div><div class="l">Админов</div></div>';
h+='<div class="scard"><div class="n">'+r.chats+'</div><div class="l">Чатов</div></div>';
h+='<div class="scard"><div class="n">'+r.messages+'</div><div class="l">Сообщений</div></div>';
h+='</div><h3 style="margin:10px 0">👥 Пользователи</h3>';
(r.users||[]).forEach(u=>{h+='<div class="adm-user"><span class="nm"><b>'+esc(u.name||u.id)+'</b> (#'+esc(u.id)+') Lv'+u.level+'</span>';
h+='<span style="font-size:11px">'+(u.expires?esc(u.expires):'')+'</span>';
h+='<select onchange="admGivePrem(\''+esc(u.id)+'\',this.value)"><option value="">Выдать Premium</option><option value="1_h">1 час</option><option value="1_d">1 день</option><option value="2_d">2 дня</option><option value="7_d">7 дней</option><option value="1_mo">1 месяц</option><option value="3_mo">3 месяца</option><option value="1_y">1 год</option></select>';
h+='<button class="btn danger" onclick="admAction(\''+esc(u.id)+'\',\'take_prem\')">-Prem</button>';
h+='<button class="btn" onclick="admAction(\''+esc(u.id)+'\',\'give_admin\')">👑 Админ</button>';
h+='<button class="btn danger" onclick="admDel(\''+esc(u.id)+'\')">🗑</button></div>';});
h+='<h3 style="margin:12px 0">🎁 Выдать Premium (свой срок)</h3>';
h+='<div class="prem-row"><input type="number" id="premNum" value="1" min="1" style="width:80px"><select id="premUnit"><option value="s">секунд</option><option value="min">минут</option><option value="h">часов</option><option value="d">дней</option><option value="w">недель</option><option value="mo">месяцев</option><option value="y">лет</option></select></div>';
h+='<div class="prem-row"><input type="text" id="premTgId" placeholder="Telegram-ID получателя"><button class="btn" onclick="admCustomPrem()">Выдать</button></div>';
h+='<h3 style="margin:12px 0">🔑 Сброс пароля</h3><input id="rpId" placeholder="Telegram-ID"><input id="rpPass" placeholder="Новый пароль"><button class="btn" onclick="adminResetPass()">Сбросить</button>';
h+='<h3 style="margin:12px 0">📢 Рассылка</h3><textarea id="bcastText" style="width:100%;padding:10px;background:var(--bg2);border:1px solid var(--border);border-radius:10px;color:var(--text);resize:none" rows="2"></textarea><button class="btn" style="margin-top:6px" onclick="adminBroadcast()">Отправить всем</button>';
h+='<h3 style="margin:12px 0">⚙️ Тема пользователя</h3><div class="prem-row"><input type="text" id="thId" placeholder="Telegram-ID"><select id="thVal"><option value="dark">Тёмная</option><option value="light">Светлая</option></select><button class="btn" onclick="admSetTheme()">Применить</button></div>';
h+='<button class="btn danger" onclick="adminResetDb()">🗑 Полная очистка аккаунтов</button>';
document.getElementById('adminContent').innerHTML=h;openOverlay('adminOverlay');}
async function admAction(id,action){const r=await api('/api/admin/give','POST',{user_id:id,action:action});if(r.ok){toast('OK','success');openAdmin();}else toast(r.error||'Ошибка','error');}
async function admGivePrem(id,val){if(!val)return;const parts=val.split('_');const r=await api('/api/admin/give','POST',{user_id:id,action:'give_prem',num:parts[0],unit:parts[1]});if(r.ok){toast('Premium выдан','success');openAdmin();}else toast(r.error||'Ошибка','error');}
async function admCustomPrem(){const id=document.getElementById('premTgId').value.trim(),num=document.getElementById('premNum').value,unit=document.getElementById('premUnit').value;if(!id||!num){toast('Заполни поля','error');return;}const r=await api('/api/admin/give','POST',{user_id:id,action:'give_prem',num:num,unit:unit});if(r.ok){toast('Premium выдан','success');openAdmin();}else toast(r.error||'Ошибка','error');}
async function admDel(id){if(!confirm('Удалить аккаунт '+id+'?'))return;const r=await api('/api/admin/give','POST',{user_id:id,action:'delete_user'});if(r.ok){toast('Удалён','success');openAdmin();}}
async function admSetTheme(){const id=document.getElementById('thId').value.trim(),v=document.getElementById('thVal').value;if(!id){toast('Укажи ID','error');return;}const r=await api('/api/admin/give','POST',{user_id:id,action:'set_theme',value:v});if(r.ok){toast('Тема изменена','success');openAdmin();}}
async function adminResetPass(){const id=document.getElementById('rpId').value.trim(),pw=document.getElementById('rpPass').value;if(!id||!pw){toast('Заполни поля','error');return;}const r=await api('/api/admin/give','POST',{user_id:id,action:'reset_pass',password:pw});if(r.ok){toast('Пароль сброшен','success');openAdmin();}else toast('Ошибка','error');}
async function adminResetDb(){if(!confirm('Удалить ВСЕ аккаунты? Это сбросит все пароли!'))return;const r=await api('/api/admin/reset_db','POST');if(r.ok){toast('База очищена','success');}}
async function adminBroadcast(){const t=document.getElementById('bcastText').value;if(!t)return;const r=await api('/api/admin/broadcast','POST',{text:t});if(r.ok){toast('Отправлено: '+r.sent+'/'+r.total,'success');}}
function esc(s){return String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function handleFile(inp){const f=inp.files[0];if(!f)return;attachedType=f.type.includes('pdf')?'pdf':'image';const reader=new FileReader();reader.onload=e=>{attachedImage=e.target.result;document.getElementById('attachImg').src=attachedType==='image'?attachedImage:'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg"><text y="30" font-size="20">📄</text></svg>';document.getElementById('attachName').textContent=f.name;document.getElementById('attachPreview').style.display='flex';};reader.readAsDataURL(f);inp.value='';}
function removeAttach(){attachedImage=null;document.getElementById('attachPreview').style.display='none';}
function formatAI(t){if(!t)return '';const lines=t.split('\n');let out='';for(const line of lines){const h=line.match(/^\*\*(.+?)\*\*$/);if(h){out+='<div class="h">'+esc(h[1])+'</div>';continue;}const parts=line.split(/(\*\*.*?\*\*)/g);let p='';for(const part of parts){if(part.startsWith('**')&&part.endsWith('**')&&part.length>4)p+='<b>'+esc(part.slice(2,-2))+'</b>';else p+=esc(part);}out+='<div style="margin:3px 0">'+p+'</div>';}return out;}
function addMsg(role,text,img,isGen){const box=document.getElementById('messages');if(document.getElementById('welcome'))document.getElementById('welcome').style.display='none';const m=document.createElement('div');m.className='msg '+role;let b='';if(img){b+=isGen?'<img class="g" src="'+img+'">':'<img class="a" src="'+img+'">';}let content='';if(role==='ai'&&text)content=formatAI(text);else if(text)content=esc(text);const acts=role==='ai'?'<div class="msg-actions"><button onclick="copyMsg(this)">📋</button><button onclick="regen()">🔄</button><button onclick="ttsMsg(this)">🔊</button><button onclick="transMsg(this)">🌐</button></div>':'';m.innerHTML='<div class="avatar">'+(role==='ai'?'🤖':String(currentUserId||'?').slice(0,1).toUpperCase())+'</div><div class="bubble">'+b+content+'</div>'+acts;box.appendChild(m);box.scrollTop=box.scrollHeight;}
function copyMsg(btn){const b=btn.closest('.msg').querySelector('.bubble');const t=document.createElement('textarea');t.value=b.innerText;document.body.appendChild(t);t.select();document.execCommand('copy');t.remove();toast('Скопировано 📋','success');}
function regen(){if(sending)return;const box=document.getElementById('messages');const ms=box.querySelectorAll('.msg');if(ms.length<2)return;const last=ms[ms.length-1];if(last.classList.contains('ai')){last.remove();const us=box.querySelectorAll('.msg.user');if(us.length)sendMessage(us[us.length-1].querySelector('.bubble').innerText,true);}}
function regenLast(){if(sending)return;regen();}
function ttsMsg(btn){const b=btn.closest('.msg').querySelector('.bubble').innerText;if('speechSynthesis'in window){speechSynthesis.cancel();speechSynthesis.speak(new SpeechSynthesisUtterance(b));toast('🔊','success');}}
function ttsLast(){const ms=document.querySelectorAll('.msg.ai');if(ms.length&&'speechSynthesis'in window){speechSynthesis.cancel();speechSynthesis.speak(new SpeechSynthesisUtterance(ms[ms.length-1].querySelector('.bubble').innerText));}}
async function transMsg(btn){const b=btn.closest('.msg').querySelector('.bubble').innerText;const r=await api('/api/translate','POST',{text:b,target:'ru'});if(r.ok)toast('🌐 '+r.translated.slice(0,250),'success');}
async function translateLast(){const ms=document.querySelectorAll('.msg.ai');if(!ms.length)return;const r=await api('/api/translate','POST',{text:ms[ms.length-1].querySelector('.bubble').innerText,target:'ru'});if(r.ok)toast('🌐 '+r.translated.slice(0,250),'success');}
function searchShow(){document.getElementById('searchQ').value='';document.getElementById('searchResults').innerHTML='';openOverlay('searchOverlay');}
async function doSearch(){const q=document.getElementById('searchQ').value.trim();if(!q)return;const r=await api('/api/search','POST',{q:q});let h='';if(r.ok&&r.results.length){r.results.forEach(x=>{h+='<div style="background:var(--bg2);border-radius:10px;padding:8px;margin:5px 0;cursor:pointer" onclick="gotoChat('+x.chat_id+')"><b>'+esc(x.title)+'</b><br><span style="color:var(--muted);font-size:12px">'+esc(x.snippet)+'</span></div>';});}else h='<p style="color:var(--muted)">Ничего не найдено</p>';document.getElementById('searchResults').innerHTML=h;}
function gotoChat(id){closeOverlay('searchOverlay');loadChats();}
function showQuickTools(){openOverlay('quickOverlay');}
async function quickAction(prefix){closeOverlay('quickOverlay');const v=document.getElementById('input').value.trim();sendMessage(prefix+v);}
function stopGen(){if(!sending)return;removeTyping();setSending(false);addMsg('ai','⏹ Генерация остановлена.',null,false);}
function addTyping(){const box=document.getElementById('messages');const m=document.createElement('div');m.className='msg ai';m.id='typing';m.innerHTML='<div class="avatar">🤖</div><div class="bubble"><div class="typing-dots"><span></span><span></span><span></span></div></div>';box.appendChild(m);box.scrollTop=box.scrollHeight;}
function removeTyping(){const t=document.getElementById('typing');if(t)t.remove();}
async function sendMessage(text,regenMode){if(sending&&!regenMode)return;const input=document.getElementById('input');const msg=(text!==undefined&&text!==null)?text:input.value.trim();if(!msg&&!attachedImage)return;if(!regenMode){input.value='';addMsg('user',msg,attachedType==='image'?attachedImage:null,false);}setSending(true);addTyping();try{const body={message:msg,chat_id:currentChatId};if(attachedImage){if(attachedType==='pdf')body.document={type:'pdf',name:document.getElementById('attachName').textContent,data:attachedImage};else body.image=attachedImage;}const r=await api('/api/chat','POST',body);removeTyping();if(r.ok){currentChatId=r.chat_id;addMsg('ai',r.response,null,false);document.getElementById('currentChatTitle').textContent='Чат';loadChats();}else{addMsg('ai','⚠️ '+r.error);toast(r.error,'error');}}catch(e){removeTyping();addMsg('ai','⚠️ Ошибка');}attachedImage=null;document.getElementById('attachPreview').style.display='none';setSending(false);checkStatus();}
function setSending(v){sending=v;document.getElementById('sendBtn').disabled=v;document.getElementById('input').disabled=v;}
function onKey(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMessage();}}
function sendSuggestion(t){sendMessage(t);}
async function newChat(){const r=await api('/api/chat/new','POST');if(r.ok){currentChatId=r.chat_id;document.getElementById('messages').innerHTML='';document.getElementById('welcome').style.display='';document.getElementById('currentChatTitle').textContent='Новый чат';document.getElementById('sidebar').classList.remove('open');}}
async function loadChats(){const r=await api('/api/chats');if(!r.ok)return;const list=document.getElementById('chatList');list.innerHTML='';r.chats.forEach(c=>{const it=document.createElement('div');it.className='chat-item'+(c.id===currentChatId?' active':'');it.innerHTML=(c.pinned?'⭐ ':'💬')+'<span class="t">'+esc(c.title||'Новый чат')+'</span><button class="del" onclick="delChat('+c.id+',event)">✕</button>';it.onclick=()=>openChat(c);list.appendChild(it);});}
function openChat(c){currentChatId=c.id;const box=document.getElementById('messages');box.innerHTML='';document.getElementById('currentChatTitle').textContent=c.title||'Чат';(c.messages||[]).forEach(m=>addMsg(m.role,m.content,m.image,false));document.getElementById('sidebar').classList.remove('open');}
async function delChat(id,e){e.stopPropagation();if(!confirm('Удалить чат?'))return;await api('/api/chat/delete','POST',{chat_id:id});if(id===currentChatId){currentChatId=null;boxReset();}loadChats();}
function boxReset(){document.getElementById('messages').innerHTML='';document.getElementById('welcome').style.display='';document.getElementById('currentChatTitle').textContent='Новый чат';}
function clearHistory(){if(!confirm('Очистить?'))return;document.getElementById('messages').innerHTML='';document.getElementById('welcome').style.display='';toast('Очищено','success');}
async function checkStatus(){const r=await api('/api/status');if(!r.ok){toast('Авторизуйся','error');return;}document.getElementById('userStatus').textContent=r.status_text+' · '+r.limit_text+' · Ур.'+r.level;document.getElementById('adminBtn').style.display=r.is_owner?'':'none';}
async function draw(){const input=document.getElementById('input');const p=prompt('🎨 Опиши что нарисовать:',input.value||'');if(!p||!p.trim())return;addMsg('user','🎨 '+p,null,false);setSending(true);addTyping();const r=await api('/api/draw','POST',{prompt:p});removeTyping();if(r.ok&&r.image){addMsg('ai','Готово!',r.image,true);}else addMsg('ai','⚠️ '+(r.error||'Не удалось'));setSending(false);checkStatus();}
function startVoice(){if(!('webkitSpeechRecognition'in window)){toast('Голос не поддерживается','error');return;}const rec=new webkitSpeechRecognition();rec.lang='ru-RU';rec.onresult=e=>{document.getElementById('input').value+=e.results[0][0].transcript;};rec.start();toast('Говори... 🎤','success');}
let partStarted=false;
function spawnParticles(){if(partStarted||document.getElementById('particles').childElementCount>0)return;partStarted=true;const c=document.getElementById('particles');const colors=['#6ea8ff','#55e6c1','#7c4dff'];const N=Math.min(8,Math.floor(window.innerWidth/180));for(let i=0;i<N;i++){const p=document.createElement('div');p.className='part';const s=3+Math.random()*5;p.style.width=s+'px';p.style.height=s+'px';p.style.left=Math.random()*100+'%';p.style.background=colors[i%3];p.style.animationDuration=(11+Math.random()*14)+'s';p.style.animationDelay=(-Math.random()*18)+'s';c.appendChild(p);}}
async function init(){spawnParticles();const me=await api('/api/me');if(me.ok){currentUserId=me.user_id;document.getElementById('authOverlay').classList.remove('show');document.getElementById('userAvatar').textContent=String(me.name||me.user_id).slice(0,1).toUpperCase();document.getElementById('userName').textContent=me.name||me.user_id;document.getElementById('userStatus').textContent='...';if(me.theme)setTheme(me.theme);await loadChats();await checkStatus();}else{openOverlay('authOverlay');try{const t=localStorage.getItem('awesome_theme');if(t)setTheme(t);}catch(e){}}}
document.addEventListener('DOMContentLoaded',init);
</script></body></html>"""

if __name__ == '__main__':
    print("🧠 AWESOME AI WEB — PRO ULTRA: Telegram-вход, память, поиск, 40+ функций")
    port=int(os.getenv("PORT",5000))
    app.run(host='0.0.0.0',port=port,debug=False,threaded=True)
