#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AWESOME AI WEB — 35+ функций, админ-панель владельца, красивый дизайн"""

import os, re, io, time, json, base64, urllib.parse, hashlib, random, html
from datetime import datetime, timedelta, timezone
import requests, urllib3
import psycopg2, psycopg2.extras
from flask import Flask, request, jsonify, render_template_string, session, send_file
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
from supabase import create_client

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "awesome-ai-super-secret-key-2026")
app.permanent_session_lifetime = timedelta(days=30)

# Конфиг
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY","AQVNyfn82epL9dy8C_kftzeypq6eF9lFd6SZnFzV")
FOLDER_ID = os.getenv("FOLDER_ID","b1g4aq87c7j61c6g3i5l")
GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY","MDFhMDBkNmEtMmExNC03M2JkLWFlZmMtOTQ0OWVlOTc5M2U1OmE1ZWJhM2NlLTQwYjAtNDZlYi1iMmY2LTE3OTFmYzhhYTQ2MA==")
SUPABASE_URL = os.getenv("SUPABASE_URL","https://lprxbmshmuucymkgaqwk.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY","eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxwcnhibXNobXV1Y3lta2dhcXdrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY3NDk0MjgsImV4cCI6MjEwMjMyNTQyOH0.Ie9jSH5RMxeOq8aU-Dv6MXlojWMUTOLE723Hdg6heZU")
DATABASE_URL = os.getenv("DATABASE_URL","postgresql://u_cmsu43cr30:3sdZICdPDoR1DUrRRKsJ8yW1BqrH2PvZ@db-team-cmsu3ykqi0295mo01tsv8m15p:5432/db_awesome_ai_web")

# ВЛАДЕЛЕЦ (только ты)
OWNER_ID = 6652898792
OWNER_USERNAME = "flidges"

FREE_LIMIT = 20
MAX_HISTORY = 30
MOSCOW_TZ = timezone(timedelta(hours=3))
CACHE = {}; CACHE_TTL = 60

def gm(): return datetime.now(MOSCOW_TZ)
def gdate(): return gm().strftime('%d.%m.%Y')
def now_iso(): return gm().strftime('%Y-%m-%d %H:%M:%S')
def fmt_date(s):
    if not s: return "неизвестно"
    try: return datetime.strptime(s,'%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')+" МСК"
    except: return s
def hash_pw(p): return hashlib.sha256(p.encode()).hexdigest()
def get_db(): return psycopg2.connect(DATABASE_URL)

def is_owner(uid=None, username=None):
    if uid and int(uid)==OWNER_ID: return True
    if username and str(username).lower()==OWNER_USERNAME.lower(): return True
    return False

# ===== БАЗА =====
def init_db():
    conn=get_db(); cur=conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users(
        user_id TEXT PRIMARY KEY,name TEXT,password TEXT,telegram_id TEXT,
        premium INTEGER DEFAULT 0,messages_today INTEGER DEFAULT 0,last_reset TEXT,
        premium_expires TEXT,is_admin INTEGER DEFAULT 0,is_owner INTEGER DEFAULT 0,
        theme TEXT DEFAULT 'dark',joined_at TEXT,xp INTEGER DEFAULT 0,level INTEGER DEFAULT 1,
        avatar TEXT DEFAULT '',ref_code TEXT,ref_count INTEGER DEFAULT 0)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS chats_web(id BIGSERIAL PRIMARY KEY,user_id TEXT,
        title TEXT DEFAULT 'Новый чат',created_at TEXT,pinned INTEGER DEFAULT 0)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS messages_web(id BIGSERIAL PRIMARY KEY,chat_id BIGINT,
        role TEXT,content TEXT,image TEXT,created_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS total_stats_web(user_id TEXT PRIMARY KEY,total_messages INTEGER DEFAULT 0)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS shared_chats(id TEXT PRIMARY KEY,chat_id BIGINT,created_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS admin_log(id BIGSERIAL PRIMARY KEY,admin_id TEXT,action TEXT,created_at TEXT)""")
    for col in ['xp','level','avatar','ref_code','ref_count']:
        try: cur.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} TEXT DEFAULT ''")
        except: pass
    try: cur.execute("ALTER TABLE chats_web ADD COLUMN IF NOT EXISTS pinned INTEGER DEFAULT 0")
    except: pass
    try: cur.execute("ALTER TABLE messages_web ADD COLUMN IF NOT EXISTS image TEXT")
    except: pass
    conn.commit(); cur.close(); conn.close()
    print("✅ База данных готова")

init_db()
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ===== СТАТУС ИЗ TG =====
def bot_status(tg):
    if not tg: return None
    try:
        r=supabase.table('users').select('premium,premium_expires,is_admin,is_owner').eq('user_id',int(tg)).execute()
        if r.data:
            d=r.data[0]
            if d.get('premium')==1 and d.get('premium_expires'):
                try:
                    if gm()>datetime.strptime(d['premium_expires'],'%Y-%m-%d %H:%M:%S').replace(tzinfo=MOSCOW_TZ):
                        return {'premium':0,'premium_expires':None,'is_admin':d.get('is_admin',0),'is_owner':d.get('is_owner',0)}
                except: return d
            return d
    except: pass
    return None

def eff_status(uid, tg=None):
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT premium,premium_expires,is_admin,is_owner,telegram_id,level,xp,ref_count FROM users WHERE user_id=%s",(uid,))
    row=cur.fetchone(); cur.close(); conn.close()
    u=dict(row) if row else {'premium':0,'premium_expires':None,'is_admin':0,'is_owner':0,'telegram_id':None,'level':1,'xp':0,'ref_count':0}
    tg=tg or u.get('telegram_id')
    owner=1 if(tg and str(tg)==str(OWNER_ID)) else 0
    if is_owner(uid): owner=1
    bot=bot_status(tg)
    if bot:
        if bot.get('is_owner')==1: owner=1
        if bot.get('premium')==1 and not u.get('premium'): u['premium']=1; u['premium_expires']=bot.get('premium_expires')
        if bot.get('is_admin')==1: u['is_admin']=1
    if u.get('premium')==1 and u.get('premium_expires'):
        try:
            if gm()>datetime.strptime(u['premium_expires'],'%Y-%m-%d %H:%M:%S').replace(tzinfo=MOSCOW_TZ):
                u['premium']=0; u['premium_expires']=None
        except: pass
    return {'premium':1 if(owner or u.get('premium')) else 0,'premium_expires':u.get('premium_expires'),
            'is_admin':1 if(owner or u.get('is_admin')) else 0,'is_owner':owner,'telegram_id':tg,
            'level':u.get('level',1),'xp':u.get('xp',0),'ref_count':u.get('ref_count',0)}

def reg_user(uid,name,pw,tg=None):
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id=%s",(uid,))
    if cur.fetchone(): cur.close(); conn.close(); return False,"Такой профиль существует"
    ref_code=hashlib.md5((uid+str(random.random())).encode()).hexdigest()[:8]
    cur.execute("INSERT INTO users(user_id,name,password,telegram_id,messages_today,last_reset,is_owner,theme,joined_at,ref_code) VALUES(%s,%s,%s,%s,0,%s,%s,'dark',%s,%s)",
                (uid,name,hash_pw(pw),tg,gm().strftime('%Y-%m-%d'),1 if tg and str(tg)==str(OWNER_ID) else 0,now_iso(),ref_code))
    cur.execute("INSERT INTO total_stats_web(user_id,total_messages) VALUES(%s,0) ON CONFLICT DO NOTHING",(uid,))
    conn.commit(); cur.close(); conn.close(); return True,"OK"

def login_user(uid,pw):
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM users WHERE user_id=%s",(uid,))
    row=cur.fetchone(); cur.close(); conn.close()
    if not row: return False,"Профиль не найден"
    if row['password']!=hash_pw(pw): return False,"Неверный пароль"
    return True,"OK"

def get_user(uid):
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM users WHERE user_id=%s",(uid,))
    row=cur.fetchone(); cur.close(); conn.close()
    return dict(row) if row else None

def can_send(uid,tg=None):
    s=eff_status(uid,tg)
    if s['is_owner'] or s['is_admin'] or s['premium']: return True
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT messages_today FROM users WHERE user_id=%s",(uid,))
    row=cur.fetchone(); cur.close(); conn.close()
    return (row[0] if row else 0)<FREE_LIMIT

def incr(uid,tg=None):
    s=eff_status(uid,tg)
    if s['is_owner'] or s['is_admin']: 
        add_xp(uid,5); return
    conn=get_db(); cur=conn.cursor()
    cur.execute("UPDATE users SET messages_today=messages_today+1 WHERE user_id=%s",(uid,))
    cur.execute("INSERT INTO total_stats_web(user_id,total_messages) VALUES(%s,1) ON CONFLICT(user_id) DO UPDATE SET total_messages=total_stats_web.total_messages+1",(uid,))
    conn.commit(); cur.close(); conn.close(); add_xp(uid,10)

def add_xp(uid,amt):
    conn=get_db(); cur=conn.cursor()
    cur.execute("UPDATE users SET xp=xp+%s WHERE user_id=%s",(amt,uid))
    cur.execute("UPDATE users SET level=1+floor(xp/100) WHERE user_id=%s",(uid,))
    conn.commit(); cur.close(); conn.close()

def upd_settings(uid,**kw):
    conn=get_db(); cur=conn.cursor()
    for k,v in kw.items():
        if v is not None: cur.execute(f"UPDATE users SET {k}=%s WHERE user_id=%s",(v,uid))
    conn.commit(); cur.close(); conn.close()

def log_admin(admin_id,action):
    conn=get_db(); cur=conn.cursor()
    cur.execute("INSERT INTO admin_log(admin_id,action,created_at) VALUES(%s,%s,%s)",(admin_id,action,now_iso()))
    conn.commit(); cur.close(); conn.close()

# ===== ЧАТЫ =====
def create_chat(uid,title="Новый чат"):
    conn=get_db(); cur=conn.cursor()
    cur.execute("INSERT INTO chats_web(user_id,title,created_at) VALUES(%s,%s,%s) RETURNING id",(uid,title,now_iso()))
    cid=cur.fetchone()[0]; conn.commit(); cur.close(); conn.close(); return cid
def get_chats(uid):
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM chats_web WHERE user_id=%s ORDER BY pinned DESC,created_at DESC",(uid,))
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
    m=get_msgs(cid); return m[-MAX_HISTORY:] if m else []
def set_title(cid,t):
    conn=get_db(); cur=conn.cursor()
    cur.execute("UPDATE chats_web SET title=%s WHERE id=%s",(t[:50],int(cid)))
    conn.commit(); cur.close(); conn.close()
def del_chat(uid,cid):
    conn=get_db(); cur=conn.cursor()
    cur.execute("DELETE FROM messages_web WHERE chat_id=%s",(int(cid),))
    cur.execute("DELETE FROM chats_web WHERE id=%s AND user_id=%s",(int(cid),uid))
    conn.commit(); cur.close(); conn.close()
def pin_chat(cid):
    conn=get_db(); cur=conn.cursor()
    cur.execute("UPDATE chats_web SET pinned = CASE WHEN pinned=1 THEN 0 ELSE 1 END WHERE id=%s",(int(cid),))
    conn.commit(); cur.close(); conn.close()

# ===== GIGACHAT =====
tok=None; tok_t=0
def get_tok():
    global tok,tok_t
    if tok and time.time()-tok_t<300: return tok
    for _ in range(3):
        try:
            r=requests.post("https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
                headers={"Content-Type":"application/x-www-form-urlencoded","Accept":"application/json","RqUID":"00000000-0000-0000-0000-000000000000","Authorization":f"Basic {GIGACHAT_AUTH_KEY}"},
                data={"scope":"GIGACHAT_API_PERS","grant_type":"client_credentials"},timeout=8,verify=False)
            if r.status_code==200: tok=r.json().get("access_token"); tok_t=time.time(); return tok
        except: pass
        time.sleep(1)
    return None

def giga(hist,sysp,max_tok=3000):
    try:
        t=get_tok()
        if not t: return None
        msgs=[{"role":"system","content":sysp[:2000]}]+[{"role":h["role"],"content":(h.get("content") or "")[:800]} for h in hist if h.get("role") in("user","assistant")]
        r=requests.post("https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
            headers={"Authorization":f"Bearer {t}","Content-Type":"application/json","Accept":"application/json"},
            json={"model":"GigaChat-Pro","messages":msgs,"temperature":0.85,"max_tokens":max_tok},
            timeout=30,verify=False)
        if r.status_code==200: return r.json()["choices"][0]["message"]["content"]
    except: pass
    return None

def full_ans(hist,sysp):
    first=giga(hist,sysp)
    if not first or len(first)<5: return None
    if len(first)>2500 and not first.rstrip().endswith(('.','!','?','»','"')):
        c=giga(hist+[{"role":"assistant","content":first},{"role":"user","content":"Продолжи с того места, где остановился. Закончи мысль полностью."}],sysp,2000)
        if c and len(c)>5: return first+"\n"+c
    return first

def ygpt(text,sysp):
    try:
        r=requests.post("https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
            headers={"Authorization":f"Api-Key {YANDEX_API_KEY}","Content-Type":"application/json"},
            json={"modelUri":f"gpt://{FOLDER_ID}/yandexgpt/latest","completionOptions":{"temperature":0.3,"maxTokens":300},
                  "messages":[{"role":"system","text":sysp},{"role":"user","text":text}]},timeout=15)
        if r.status_code==200: return r.json()["result"]["alternatives"][0]["message"]["text"]
    except: pass
    return None

SUPER="""ТЫ — AWESOME AI 2026, живая нейросеть на базе GigaChat, копия DeepSeek. НЕ шаблон.
📍 Москва (UTC+3). Сегодня: {d}, время: {t}.
Ты помнишь весь диалог.
ПРАВИЛА: полный развёрнутый ответ, раскрывай тему целиком. Разделяй ответ на РАЗДЕЛЫ с подзаголовками **1. Утро** (две звёздочки). Важное выделяй **жирным**. Без "возможно/наверное/извини". Примеры, цифры, эмодзи (🔥🧠💡⚡🚀). Ответ такой полный, чтобы не осталось вопросов.
💎 PREMIUM — максимальная глубина. Ты живая нейросеть, докажи это!"""

def describe_img(b64):
    try:
        t=get_tok()
        if not t: return "📸 Изображение"
        r=requests.post("https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
            headers={"Authorization":f"Bearer {t}","Content-Type":"application/json","Accept":"application/json"},
            json={"model":"GigaChat-Pro","messages":[{"role":"system","content":"Ты видишь изображения. Опиши подробно объекты, действия, текст, цвета. На русском."},
                {"role":"user","content":[{"type":"text","text":"Что на изображении?"},{"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}"}}]}],"temperature":0.5,"max_tokens":700},timeout=30,verify=False)
        if r.status_code==200: return r.json()["choices"][0]["message"]["content"]
    except: pass
    return "📸 Изображение"

def gen_img(prompt):
    try:
        c=prompt
        for w in ['нарисуй','сгенерируй','покажи','картинку','изображение']: c=c.replace(w,'').strip()
        if not c: c=prompt
        r=requests.get(f"https://image.pollinations.ai/prompt/{urllib.parse.quote(c)}?width=1024&height=1024&nologo=true",headers={"User-Agent":"Mozilla/5.0"},timeout=25)
        if r.status_code==200 and len(r.content)>1000: return base64.b64encode(r.content).decode()
    except: pass
    return None

def translate(text,target='ru'):
    try:
        r=requests.post("https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl="+target+"&dt=t&q="+urllib.parse.quote(text[:5000]),timeout=10)
        if r.status_code==200: return "".join(x[0] for x in r.json()[0] if x[0])
    except: pass
    return text

def read_pdf(b64):
    try:
        import fitz
        raw=base64.b64decode(b64.split(',')[-1]); doc=fitz.open(stream=raw,filetype="pdf")
        txt="".join(page.get_text() for page in doc)[:6000]
        return txt or "PDF не содержит текста"
    except: return "PDF загружен"

def solve_math(text):
    tl=text.lower().strip()
    if not re.search(r'\d',tl): return None
    if any(k in tl for k in ['кто','что','где','когда','почему','зачем','праздник','погода','курс']): return None
    c=tl
    for w in ['сколько будет','сколько','будет','посчитай','реши','пример','скок','равно']: c=c.replace(w,'').strip()
    c=c.replace(' ','').replace('плюс','+').replace('минус','-').replace('умножить','*').replace('разделить','/').replace('х','*').replace('×','*').replace('÷','/')
    if not re.search(r'[+\-*/]',c): return None
    e=re.sub(r'[^0-9+\-*/()=.]','',c)
    if e and len(e)>1:
        try:
            if any(op in e for op in ['__','import','eval','exec']): return None
            r=eval(e); return str(int(r)) if r==int(r) else str(round(r,2))
        except: pass
    return None

def weather(city):
    try:
        r=requests.get(f"https://api.openweathermap.org/data/2.5/weather?q={urllib.parse.quote(city)}&appid=4c8f5c0b8a9f2c5d6e7f8g9h0i1j2k3l&units=metric&lang=ru",timeout=3)
        if r.status_code==200:
            d=r.json(); return f"🌤 {city}: {round(d['main']['temp'])}°C, {d['weather'][0]['description']}\n💨 Ветер: {d['wind']['speed']} м/с"
    except: pass
    return None

def currency():
    try:
        r=requests.get("https://api.exchangerate-api.com/v4/latest/USD",timeout=4)
        rates=r.json().get('rates',{}); usd=rates.get('RUB','?'); eur=usd/rates.get('EUR',1) if rates.get('EUR') else '?'
        return f"💵 USD: {round(usd,2)}₽\nEUR: {round(eur,2)}₽"
    except: return None

def crypto():
    try:
        r=requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd",timeout=4)
        d=r.json(); return f"🪙 BTC: ${d.get('bitcoin',{}).get('usd','?')}\nETH: ${d.get('ethereum',{}).get('usd','?')}"
    except: return None

def process(uid,text,history,img=None,tg=None,doc_text=None):
    tl=text.lower().strip()
    if img or doc_text:
        sp=SUPER.format(d=gdate(),t=gm().strftime('%H:%M'))
        if img: sp+=f"\n📸 Изображение: {img}"
        if doc_text: sp+=f"\n📄 Документ:\n{doc_text[:4000]}"
        sp+="\nОтветь развёрнуто."
        if eff_status(uid,tg)['premium']: sp+="\n💎 PREMIUM."
        a=full_ans(history+[{"role":"user","content":text or "Опиши"}],sp); return a or "Готово"
    m=solve_math(text)
    if m is not None: return m
    if any(k in tl for k in ['праздник','какой сегодня праздник']):
        md=gdate()[3:5]+'.'+gdate()[0:2]
        h={'01.01':'Новый год','07.01':'Рождество','23.02':'День защитника Отечества','08.03':'Женский день','09.05':'День Победы','12.06':'День России','04.11':'День народного единства','14.02':'День влюбленных','01.04':'День смеха','12.04':'День космонавтики','01.09':'День знаний','31.10':'Хэллоуин','12.12':'День Конституции РФ'}
        return f"📅 *{gdate()} (МСК)*\n\n{h.get(md,'Праздников не найдено')}"
    if any(k in tl for k in ['погода','weather']):
        mm=re.search(r'(в|в городе)\s+([а-яА-Яa-zA-Z\- ]+)',tl)
        if mm:
            w=weather(mm.group(2).strip()); return w if w else "🌤 Не удалось"
        return "🌤 Напиши: погода в [город]"
    if any(k in tl for k in ['курс','доллар','евро','валюта']):
        c=currency(); return c if c else "💵 Не удалось"
    if any(k in tl for k in ['биткоин','btc','эфириум','eth','крипта']):
        c=crypto(); return c if c else "🪙 Не удалось"
    sp=SUPER.format(d=gdate(),t=gm().strftime('%H:%M'))
    if eff_status(uid,tg)['premium']: sp+="\n💎 PREMIUM — максимальная проработка."
    a=full_ans(history+[{"role":"user","content":text}],sp)
    if a and len(a)>5:
        ch=ygpt(a[:400],"Если всё верно, ответь ровно 'ПОДТВЕРЖДАЮ'. Иначе кратко перечисли ошибки.")
        if ch and "ПОДТВЕРЖДАЮ" not in ch.upper():
            f=full_ans(history+[{"role":"user","content":f"Исправь: {ch}\nОтвет:\n{a}"}],"Исправь ответ. Полный ответ.")
            if f and len(f)>5: return f
        return a
    return "🤖 Обрабатываю... Повтори чуть позже."

# ===== API =====
@app.route('/')
def index(): return render_template_string(INDEX_HTML)

@app.route('/api/register',methods=['POST'])
def api_register():
    d=request.json; uid=str(d.get('user_id','')).strip(); name=str(d.get('name','')).strip() or uid
    pw=str(d.get('password','')); tg=d.get('telegram_id') or None
    ref=d.get('ref') or None
    if not uid or len(pw)<3: return jsonify({'ok':False,'error':'Заполни ID и пароль (мин 3)'})
    try: tg=str(int(tg)) if tg else None
    except: tg=None
    ok,msg=reg_user(uid,name,pw,tg)
    if not ok: return jsonify({'ok':False,'error':msg})
    if ref: add_xp(ref,20)
    session.permanent=True; session['user_id']=uid; session['name']=name
    return jsonify({'ok':True,'user_id':uid,'name':name})

@app.route('/api/login',methods=['POST'])
def api_login():
    d=request.json; uid=str(d.get('user_id','')).strip(); pw=str(d.get('password',''))
    ok,msg=login_user(uid,pw)
    if not ok: return jsonify({'ok':False,'error':msg})
    u=get_user(uid); session.permanent=True; session['user_id']=uid; session['name']=u.get('name') if u else uid
    return jsonify({'ok':True,'user_id':uid,'name':session['name']})

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
    u=get_user(uid); tg=u.get('telegram_id') if u else None
    s=eff_status(uid,tg)
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT messages_today FROM users WHERE user_id=%s",(uid,)); row=cur.fetchone(); cur.close(); conn.close()
    if s['is_owner']: st="👑 Владелец"; lim="♾️"
    elif s['is_admin']: st="👑 Админ"; lim="♾️"
    elif s['premium']: st="💎 Premium"; lim="♾️"
    else: st="🔓 Бесплатный"; lim=f"{max(0,FREE_LIMIT-(row[0] if row else 0))}/{FREE_LIMIT}"
    return jsonify({'ok':True,'premium':bool(s['premium']),'is_admin':bool(s['is_admin']),'is_owner':bool(s['is_owner']),
                    'premium_expires':fmt_date(s['premium_expires']) if s['premium'] else None,
                    'status_text':st,'limit_text':lim,'messages_today':row[0] if row else 0,'free_limit':FREE_LIMIT,
                    'level':s['level'],'xp':s['xp'],'ref_count':s['ref_count']})

@app.route('/api/chat',methods=['POST'])
def api_chat():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False,'error':'Авторизуйся'})
    u=get_user(uid); tg=u.get('telegram_id') if u else None
    if not can_send(uid,tg): return jsonify({'ok':False,'error':'Лимит! Купи Premium.'})
    d=request.json; msg=d.get('message','').strip(); cid=d.get('chat_id'); img=d.get('image'); doc=d.get('document')
    if not msg and not img and not doc: return jsonify({'ok':False,'error':'Пустое'})
    if not cid: cid=create_chat(uid)
    h=hist(cid)
    idesc=None; dtext=None
    if img:
        try:
            raw=base64.b64decode(img.split(',')[-1]); im=Image.open(io.BytesIO(raw)).convert('RGB'); im.thumbnail((800,800))
            b=io.BytesIO(); im.save(b,'JPEG',quality=85); idesc=describe_img(base64.b64encode(b.getvalue()).decode())
        except: idesc="📸"
    if doc:
        if doc.get('type')=='pdf': dtext=read_pdf(doc.get('data',''))
        else: dtext="Документ: "+doc.get('name','')
    add_msg(cid,'user',msg,img)
    response=process(uid,msg,h,idesc,tg,dtext)
    incr(uid,tg); add_msg(cid,'assistant',response)
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
    return render_template_string("""<html><head><title>Поделиться</title><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{background:#16151c;color:#eceaf5;font-family:Segoe UI;padding:20px;max-width:760px;margin:auto}.m{background:#262430;border-radius:12px;padding:12px;margin:10px 0;white-space:pre-wrap}.user{background:#ff8a3d;color:#fff}.a{background:#262430}</style></head><body><h2>💬 Общий чат</h2>{{msgs_html|safe}}</body></html>""",
        msgs_html="".join(f'<div class="m {"user" if m["role"]=="user" else "a"}">{"Вы" if m["role"]=="user" else "🤖 AWESOME AI"}:<br>'+html.escape(m.get("content") or "")+"</div>" for m in msgs))

@app.route('/api/export',methods=['POST'])
def api_export():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False})
    cid=request.json.get('chat_id'); msgs=get_msgs(cid)
    txt="".join(("Вы: " if m['role']=='user' else "AWESOME AI: ")+str(m.get('content') or "")+"\n\n" for m in msgs)
    f=io.BytesIO(txt.encode('utf-8'))
    from flask import send_file as sf
    return sf(f,as_attachment=True,download_name="chat.txt",mimetype="text/plain")

@app.route('/api/translate',methods=['POST'])
def api_translate():
    d=request.json; t=translate(d.get('text',''),d.get('target','ru')); return jsonify({'ok':True,'translated':t})

@app.route('/api/draw',methods=['POST'])
def api_draw():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False,'error':'Авторизуйся'})
    u=get_user(uid); tg=u.get('telegram_id') if u else None
    if not can_send(uid,tg): return jsonify({'ok':False,'error':'Лимит!'})
    img=gen_img(request.json.get('prompt',''))
    if img: incr(uid,tg); return jsonify({'ok':True,'image':img})
    return jsonify({'ok':False,'error':'Не удалось'})

@app.route('/api/profile')
def api_profile():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False})
    u=get_user(uid); tg=u.get('telegram_id') if u else None
    s=eff_status(uid,tg)
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT messages_today FROM users WHERE user_id=%s",(uid,)); row=cur.fetchone()
    cur.execute("SELECT total_messages FROM total_stats_web WHERE user_id=%s",(uid,)); tot=cur.fetchone()
    cur.close(); conn.close()
    return jsonify({'ok':True,'user_id':uid,'name':u.get('name'),'telegram_id':tg,'theme':u.get('theme','dark'),
                    'avatar':u.get('avatar',''),'ref_code':u.get('ref_code'),'premium':bool(s['premium']),
                    'is_admin':bool(s['is_admin']),'is_owner':bool(s['is_owner']),'level':s['level'],'xp':s['xp'],'ref_count':s['ref_count'],
                    'premium_expires':fmt_date(s['premium_expires']) if s['premium'] else None,
                    'messages_today':row[0] if row else 0,'total_messages':tot[0] if tot else 0,'joined_at':u.get('joined_at')})

@app.route('/api/settings',methods=['POST'])
def api_settings():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False})
    d=request.json
    upd_settings(uid,name=d.get('name'),theme=d.get('theme'),telegram_id=d.get('telegram_id'),avatar=d.get('avatar'))
    if d.get('name'): session['name']=d['name']
    return jsonify({'ok':True})

@app.route('/api/search',methods=['POST'])
def api_search():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False})
    q=request.json.get('q','').lower()
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id,title FROM chats_web WHERE user_id=%s",(uid,))
    chats=cur.fetchall(); cur.close(); conn.close()
    res=[]
    for c in chats:
        ms=get_msgs(c['id'])
        for m in ms:
            if q in str(m.get('content') or '').lower():
                res.append({'chat_id':c['id'],'title':c.get('title','Чат'),'snippet':str(m.get('content') or '')[:80]}); break
    return jsonify({'ok':True,'results':res[:20]})

# ===== АДМИН-ПАНЕЛЬ (только владелец) =====
@app.route('/api/admin/stats')
def admin_stats():
    uid=session.get('user_id')
    u=get_user(uid)
    if not is_owner(uid,u.get('telegram_id') if u else None):
        return jsonify({'ok':False,'error':'Нет доступа'})
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users"); total=cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users WHERE premium=1"); prem=cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users WHERE is_admin=1"); admins=cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM chats_web"); chats=cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM messages_web"); msgs=cur.fetchone()[0]
    cur.execute("SELECT user_id,name,premium,is_admin,level,xp FROM users ORDER BY joined_at DESC LIMIT 50")
    users=cur.fetchall(); cur.close(); conn.close()
    return jsonify({'ok':True,'total':total,'premium':prem,'admins':admins,'chats':chats,'messages':msgs,
                    'users':[{'id':r[0],'name':r[1],'premium':r[2],'is_admin':r[3],'level':r[4],'xp':r[5]} for r in users]})

@app.route('/api/admin/give',methods=['POST'])
def admin_give():
    uid=session.get('user_id')
    u=get_user(uid)
    if not is_owner(uid,u.get('telegram_id') if u else None): return jsonify({'ok':False,'error':'Нет доступа'})
    d=request.json; target=d.get('user_id','').strip(); field=d.get('field'); val=d.get('value')
    if not target or not field: return jsonify({'ok':False,'error':'Данные'})
    upd_settings(target,**{field:val})
    log_admin(uid,f"Выдал {field}={val} для {target}")
    return jsonify({'ok':True})

@app.route('/api/admin/broadcast',methods=['POST'])
def admin_broadcast():
    uid=session.get('user_id')
    u=get_user(uid)
    if not is_owner(uid,u.get('telegram_id') if u else None): return jsonify({'ok':False,'error':'Нет доступа'})
    text=request.json.get('text','')
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT user_id FROM users"); ids=[r[0] for r in cur.fetchall()]; cur.close(); conn.close()
    sent=0
    for uid2 in ids:
        try: requests.post(f"https://api.telegram.org/bot8336209662:AAHdhYXhqWA-LtthwgydDSRU7A6A0ceC-HY/sendMessage",json={"chat_id":uid2,"text":text}); sent+=1
        except: pass
    log_admin(uid,f"Рассылка: {text[:50]} ({sent}/{len(ids)})")
    return jsonify({'ok':True,'sent':sent,'total':len(ids)})

@app.route('/api/admin/logs')
def admin_logs():
    uid=session.get('user_id')
    u=get_user(uid)
    if not is_owner(uid,u.get('telegram_id') if u else None): return jsonify({'ok':False})
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM admin_log ORDER BY id DESC LIMIT 50")
    rows=cur.fetchall(); cur.close(); conn.close()
    return jsonify({'ok':True,'logs':[dict(r) for r in rows]})

# ===== HTML =====
INDEX_HTML = r"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no"><title>AWESOME AI</title>
<style>
:root{--bg:#12141c;--bg2:#191c26;--panel:#1f2230;--border:#2c3040;--accent:#ff8a3d;--accent2:#ff6b1a;--text:#eceaf5;--muted:#9a96ab;--danger:#ff5b6e;--success:#3ddc84;--glow:rgba(255,138,61,.25)}
[data-theme="light"]{--bg:#f6f5f9;--bg2:#fff;--panel:#fff;--border:#e4e1ec;--accent:#f07800;--accent2:#ff6b1a;--text:#23202e;--muted:#6d6a80;--danger:#e0404f;--success:#1fa860;--glow:rgba(240,120,0,.15)}
*{margin:0;padding:0;box-sizing:border-box;font-family:'Segoe UI',system-ui,sans-serif}
body{background:var(--bg);color:var(--text);height:100vh;overflow:hidden;transition:background .4s,color .4s;-webkit-font-smoothing:antialiased}
.bg{position:fixed;inset:0;z-index:-2;background:radial-gradient(circle at 15% 15%,var(--glow),transparent 45%),radial-gradient(circle at 85% 85%,rgba(124,108,255,.1),transparent 45%),var(--bg)}
.app{display:flex;height:100vh}
.sidebar{width:280px;background:var(--panel);border-right:1px solid var(--border);display:flex;flex-direction:column;transition:transform .25s,background .4s;z-index:50}
.sidebar-header{padding:16px;display:flex;align-items:center;gap:10px;border-bottom:1px solid var(--border)}
.logo{width:42px;height:42px;border-radius:14px;background:linear-gradient(135deg,var(--accent),var(--accent2));display:flex;align-items:center;justify-content:center;font-size:21px;flex-shrink:0;box-shadow:0 4px 20px var(--glow);animation:glow 3s ease-in-out infinite}
@keyframes glow{0%,100%{box-shadow:0 0 0 0 var(--glow)}50%{box-shadow:0 0 25px var(--glow)}}
.brand{font-weight:800;font-size:17px;background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.new-chat{margin:14px;padding:13px;background:linear-gradient(135deg,var(--accent),var(--accent2));border:none;border-radius:14px;color:#fff;font-weight:700;cursor:pointer;font-size:14px;transition:.2s;box-shadow:0 4px 18px var(--glow)}
.new-chat:hover{transform:translateY(-2px)}
.new-chat:active{transform:scale(.97)}
.search-box{margin:0 14px 10px;padding:10px 12px;background:var(--bg2);border:1px solid var(--border);border-radius:10px;color:var(--muted);font-size:13px;outline:none;width:calc(100% - 28px)}
.search-box:focus{border-color:var(--accent)}
.chat-list{flex:1;overflow-y:auto;padding:0 10px}
.chat-item{padding:11px 12px;border-radius:12px;cursor:pointer;margin-bottom:4px;font-size:13px;display:flex;align-items:center;gap:8px;transition:.15s;animation:fadeIn .3s}
.chat-item:hover,.chat-item.active{background:var(--bg2)}
.chat-item .t{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.chat-item .star{opacity:0;background:none;border:none;color:#ffd700;cursor:pointer;font-size:14px}
.chat-item:hover .star{opacity:1}
.chat-item .del{opacity:0;background:none;border:none;color:var(--danger);cursor:pointer;font-size:14px}
.chat-item:hover .del{opacity:1}
@keyframes fadeIn{from{opacity:0;transform:translateY(-5px)}to{opacity:1;transform:translateY(0)}}
.sidebar-footer{padding:12px;border-top:1px solid var(--border)}
.user-box{display:flex;align-items:center;gap:10px;padding:10px;background:var(--bg2);border-radius:14px}
.avatar{width:38px;height:38px;border-radius:50%;background:linear-gradient(135deg,var(--accent),var(--accent2));display:flex;align-items:center;justify-content:center;font-weight:700;font-size:16px;flex-shrink:0;color:#fff}
.user-info{flex:1;min-width:0}
.user-name{font-weight:600;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.user-status{font-size:11px;color:var(--accent)}
.user-level{font-size:10px;color:var(--muted)}
.user-actions{display:flex;gap:2px}
.mini-btn{background:none;border:none;color:var(--muted);cursor:pointer;font-size:16px;padding:4px;transition:.2s}
.mini-btn:hover{color:var(--accent);transform:scale(1.1)}
.main{flex:1;display:flex;flex-direction:column;min-width:0}
.main-header{height:56px;display:flex;align-items:center;justify-content:center;border-bottom:1px solid var(--border);position:relative}
.mobile-toggle{display:none;position:absolute;left:14px;background:none;border:none;color:var(--text);font-size:22px;cursor:pointer}
.messages{flex:1;overflow-y:auto;padding:20px;scroll-behavior:smooth;overscroll-behavior:contain}
.welcome{max-width:720px;margin:0 auto;text-align:center;padding-top:6vh;animation:fadeUp .6s ease}
@keyframes fadeUp{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}
.welcome h1{font-size:clamp(28px,5vw,46px);margin-bottom:12px;background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.welcome p{color:var(--muted);margin-bottom:30px;font-size:16px}
.suggestion-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;max-width:640px;margin:0 auto}
.sugg{background:var(--panel);border:1px solid var(--border);border-radius:16px;padding:18px;cursor:pointer;transition:.25s;font-size:13px;text-align:left}
.sugg:hover{transform:translateY(-4px);border-color:var(--accent);box-shadow:0 10px 30px var(--glow)}
.sugg:active{transform:scale(.97)}
.sugg .ic{font-size:26px;margin-bottom:10px;display:block}
.msg{max-width:760px;margin:0 auto 18px;display:flex;gap:12px;animation:fadeUp .35s ease;position:relative}
.msg.user{flex-direction:row-reverse}
.msg .bubble{padding:14px 18px;border-radius:18px;font-size:15px;line-height:1.65;max-width:82%;white-space:pre-wrap;word-break:break-word}
.msg.user .bubble{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;border-top-right-radius:6px}
.msg.ai .bubble{background:var(--panel);border:1px solid var(--border);border-top-left-radius:6px}
.msg .bubble b{color:var(--accent)}
.msg .bubble .h{display:block;font-weight:800;color:var(--accent);font-size:16px;margin:14px 0 6px;padding-top:12px;border-top:1px solid var(--border)}
.msg .bubble .h:first-child{border:none;margin-top:0;padding-top:0}
.msg .bubble img.a{max-width:240px;border-radius:12px;margin-top:8px;display:block}
.msg .bubble img.g{max-width:100%;border-radius:12px;margin-top:8px}
.msg-actions{position:absolute;top:8px;right:8px;display:flex;gap:4px;opacity:0;transition:.2s}
.msg:hover .msg-actions{opacity:1}
.msg-actions button{background:var(--bg2);border:1px solid var(--border);color:var(--muted);border-radius:8px;cursor:pointer;font-size:12px;padding:4px 8px}
.msg-actions button:hover{color:var(--accent);border-color:var(--accent)}
.typing-dots{display:inline-flex;gap:5px;padding:8px 2px}
.typing-dots span{width:9px;height:9px;border-radius:50%;background:var(--accent);animation:bounce 1.2s infinite}
.typing-dots span:nth-child(2){animation-delay:.2s}.typing-dots span:nth-child(3){animation-delay:.4s}
@keyframes bounce{0%,100%{transform:translateY(0);opacity:.4}50%{transform:translateY(-7px);opacity:1}}
.input-area{padding:14px;border-top:1px solid var(--border);background:var(--bg)}
.attach-preview{max-width:760px;margin:0 auto 8px;display:none;gap:8px;align-items:center;background:var(--bg2);border:1px solid var(--border);border-radius:14px;padding:8px;animation:fadeIn .3s}
.attach-preview img{width:52px;height:52px;object-fit:cover;border-radius:8px}
.attach-preview .an{flex:1;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.attach-preview .rm{background:none;border:none;color:var(--danger);cursor:pointer;font-size:18px}
.input-wrap{max-width:760px;margin:0 auto;display:flex;align-items:flex-end;gap:6px;background:var(--bg2);border:1px solid var(--border);border-radius:20px;padding:8px;transition:.2s}
.input-wrap:focus-within{border-color:var(--accent);box-shadow:0 0 0 4px var(--glow)}
textarea{flex:1;background:none;border:none;outline:none;color:var(--text);font-size:15px;resize:none;max-height:130px;padding:8px 4px}
.icon-btn{width:38px;height:38px;border-radius:12px;background:none;border:none;color:var(--muted);font-size:17px;cursor:pointer;flex-shrink:0;transition:.2s}
.icon-btn:hover{color:var(--accent);transform:scale(1.1)}
.send-btn{width:44px;height:44px;border-radius:14px;background:linear-gradient(135deg,var(--accent),var(--accent2));border:none;color:#fff;font-size:18px;cursor:pointer;flex-shrink:0;box-shadow:0 4px 16px var(--glow);transition:.2s}
.send-btn:hover{transform:scale(1.05)}
.send-btn:disabled{opacity:.4;cursor:not-allowed;transform:none}
.toolbar{max-width:760px;margin:10px auto 0;display:flex;gap:8px;flex-wrap:wrap}
.tool-btn{background:var(--panel);border:1px solid var(--border);color:var(--muted);border-radius:10px;padding:7px 13px;font-size:12px;cursor:pointer;transition:.2s}
.tool-btn:hover{color:var(--text);border-color:var(--accent);transform:translateY(-1px)}
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.6);backdrop-filter:blur(6px);z-index:100;display:flex;align-items:center;justify-content:center;padding:16px;animation:fadeIn .3s}
.modal{background:var(--panel);border:1px solid var(--border);border-radius:22px;padding:30px;width:100%;max-width:420px;text-align:center;max-height:92vh;overflow-y:auto;animation:pop .4s ease}
@keyframes pop{from{transform:scale(.9);opacity:0}to{transform:scale(1);opacity:1}}
.modal .tabs{display:flex;gap:8px;margin-bottom:16px}
.modal .tab{flex:1;padding:11px;border-radius:12px;background:var(--bg2);border:1px solid var(--border);color:var(--muted);cursor:pointer;font-weight:700;font-size:14px;transition:.2s}
.modal .tab.active{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;border:none}
.modal h2{margin-bottom:8px}.modal p{color:var(--muted);font-size:14px;margin-bottom:16px}
.modal input,.modal select,.modal textarea{width:100%;padding:13px;background:var(--bg2);border:1px solid var(--border);border-radius:12px;color:var(--text);font-size:15px;margin-bottom:10px;outline:none}
.modal input:focus,.modal select:focus{border-color:var(--accent)}
.modal .btn{width:100%;padding:14px;border:none;border-radius:12px;background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;font-weight:700;font-size:15px;cursor:pointer;transition:.2s;margin-bottom:8px}
.modal .btn:hover{transform:translateY(-2px)}
.modal .btn.ghost{background:var(--bg2);color:var(--muted);border:1px solid var(--border)}
.hint{font-size:12px;color:var(--muted);margin-top:10px;line-height:1.5}
.toast{position:fixed;top:20px;right:20px;background:var(--panel);border:1px solid var(--border);border-radius:14px;padding:14px 20px;z-index:300;box-shadow:0 8px 30px rgba(0,0,0,.4);max-width:320px;animation:slideR .3s}
.toast.error{border-color:var(--danger)}.toast.success{border-color:var(--success)}
@keyframes slideR{from{transform:translateX(120%);opacity:0}to{transform:translateX(0);opacity:1}}
.scrollbar::-webkit-scrollbar{width:6px}.scrollbar::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
.stat-card{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;margin-bottom:18px}
.scard{background:var(--bg2);border:1px solid var(--border);border-radius:14px;padding:14px;text-align:center}
.scard .n{font-size:26px;font-weight:800;color:var(--accent)}
.scard .l{font-size:12px;color:var(--muted)}
.adm-user{display:flex;align-items:center;gap:8px;padding:8px;background:var(--bg2);border-radius:10px;margin-bottom:6px;font-size:13px}
.adm-user input{width:60px;padding:5px;background:var(--panel);border:1px solid var(--border);border-radius:6px;color:var(--text);text-align:center}
@media(max-width:768px){
.sidebar{position:fixed;left:0;top:0;bottom:0;transform:translateX(-100%)}
.sidebar.open{transform:translateX(0);box-shadow:0 0 40px rgba(0,0,0,.5)}
.mobile-toggle{display:block}
.msg .bubble{max-width:90%}
.msg .bubble img.a{max-width:170px}
}
</style></head>
<body data-theme="dark"><div class="bg"></div>
<div class="app">
<aside class="sidebar" id="sidebar">
<div class="sidebar-header"><div class="logo">🤖</div><div class="brand">AWESOME AI</div></div>
<button class="new-chat" onclick="newChat()">＋ Новый чат</button>
<input class="search-box" id="chatSearch" placeholder="🔍 Поиск по чатам..." oninput="searchChats(this.value)">
<div class="chat-list scrollbar" id="chatList"></div>
<div class="sidebar-footer">
<div class="user-box">
<div class="avatar" id="userAvatar">?</div>
<div class="user-info"><div class="user-name" id="userName">Пользователь</div><div class="user-status" id="userStatus">...</div><div class="user-level" id="userLevel"></div></div>
<div class="user-actions">
<button class="mini-btn" onclick="openSettings()" title="Настройки">⚙️</button>
<button class="mini-btn" onclick="openAdmin()" id="adminBtn" style="display:none" title="Админ">🛡️</button>
<button class="mini-btn" onclick="toggleTheme()" title="Тема">🌓</button>
<button class="mini-btn" onclick="logout()" title="Выйти">⏻</button>
</div></div></div></aside>
<div class="main">
<div class="main-header"><button class="mobile-toggle" onclick="toggleSidebar()">☰</button><div class="title" id="currentChatTitle">Новый чат</div></div>
<div class="messages scrollbar" id="messages">
<div class="welcome" id="welcome">
<h1>Чем могу помочь?</h1><p>AWESOME AI — 35+ функций, память диалога, DeepSeek-стиль</p>
<div class="suggestion-grid">
<div class="sugg" onclick="sendSuggestion('Расскажи подробно про распорядок дня')"><span class="ic">⏰</span>Распорядок дня</div>
<div class="sugg" onclick="sendSuggestion('Напиши код на Python для парсинга сайта')"><span class="ic">💻</span>Напиши код</div>
<div class="sugg" onclick="sendSuggestion('погода в Москве')"><span class="ic">🌤</span>Погода</div>
<div class="sugg" onclick="sendSuggestion('нарисуй кота в космосе')"><span class="ic">🎨</span>Нарисуй</div>
<div class="sugg" onclick="sendSuggestion('курс доллара')"><span class="ic">💵</span>Курс валют</div>
<div class="sugg" onclick="sendSuggestion('сколько будет 256*144+18?')"><span class="ic">🧮</span>Математика</div>
</div></div></div>
<div class="input-area">
<div class="attach-preview" id="attachPreview"><img id="attachImg" src=""><span class="an" id="attachName"></span><button class="rm" onclick="removeAttach()">✕</button></div>
<div class="input-wrap">
<input type="file" id="fileInput" accept="image/*,.pdf" style="display:none" onchange="handleFile(this)">
<button class="icon-btn" onclick="document.getElementById('fileInput').click()" title="Прикрепить файл">📎</button>
<button class="icon-btn" onclick="startVoice()" title="Голос">🎤</button>
<button class="icon-btn" onclick="tts()" title="Озвучить">🔊</button>
<button class="icon-btn" onclick="translateLast()" title="Перевести">🌐</button>
<textarea id="input" rows="1" placeholder="Спроси что-нибудь..." onkeydown="onKey(event)"></textarea>
<button class="send-btn" id="sendBtn" onclick="sendMessage()">➤</button>
</div>
<div class="toolbar">
<button class="tool-btn" onclick="draw()">🎨 Сгенерировать</button>
<button class="tool-btn" onclick="checkStatus()">💎 Статус</button>
<button class="tool-btn" onclick="clearHistory()">🧹 Очистить</button>
</div></div></div></div>

<!-- Вход/Регистрация -->
<div class="overlay" id="authOverlay">
<div class="modal">
<div class="logo" style="width:56px;height:56px;font-size:28px;margin:0 auto 14px;display:flex;align-items:center;justify-content:center;border-radius:14px;background:linear-gradient(135deg,var(--accent),var(--accent2))">🤖</div>
<div class="tabs"><button class="tab active" id="tabLogin" onclick="switchTab('login')">Вход</button><button class="tab" id="tabReg" onclick="switchTab('reg')">Регистрация</button></div>
<h2 id="authTitle">Вход</h2><p id="authSub">Войди в аккаунт</p>
<div id="regFields" style="display:none"><input type="text" id="regName" placeholder="Имя"></div>
<input type="text" id="regId" placeholder="Профиль-ID">
<input type="password" id="regPass" placeholder="Пароль">
<div id="tgField"><input type="text" id="regTg" placeholder="Telegram-ID (для Premium из бота)"></div>
<input type="text" id="regRef" placeholder="Реферальный код (если есть)" style="display:none">
<button class="btn" id="authBtn" onclick="submitAuth()">Войти</button>
<div class="hint">Укажи Telegram-ID — статус (Premium/админ/владелец) из @awesomeneiro_bot применится автоматически</div></div></div>

<!-- Настройки -->
<div class="overlay" id="settingsOverlay" style="display:none">
<div class="modal"><h2>⚙️ Настройки</h2><p>Твой профиль</p>
<input type="text" id="setName" placeholder="Имя">
<input type="text" id="setTg" placeholder="Telegram-ID">
<input type="text" id="setAvatar" placeholder="URL аватарки">
<select id="setTheme"><option value="dark">🌙 Тёмная</option><option value="light">☀️ Светлая</option></select>
<div id="refInfo" style="font-size:13px;color:var(--muted);margin-bottom:10px;background:var(--bg2);padding:10px;border-radius:10px"></div>
<button class="btn" onclick="saveSettings()">Сохранить</button>
<button class="btn ghost" onclick="document.getElementById('settingsOverlay').style.display='none'">Закрыть</button></div></div>

<!-- Админ-панель -->
<div class="overlay" id="adminOverlay" style="display:none">
<div class="modal" style="max-width:600px"><h2>🛡️ Админ-панель</h2><p>Только для владельца</p>
<div id="adminContent" style="text-align:left">Загрузка...</div>
<button class="btn ghost" onclick="document.getElementById('adminOverlay').style.display='none'">Закрыть</button></div></div>

<script>
let currentUserId=null,currentChatId=null,sending=false,attachedImage=null,attachedType='image',authMode='login',currentTheme='dark';
function toast(t,ty){const el=document.createElement('div');el.className='toast '+(ty||'');el.textContent=t;document.body.appendChild(el);setTimeout(()=>el.remove(),3000);}
function toggleSidebar(){document.getElementById('sidebar').classList.toggle('open');}
async function api(url,method,body){try{const o={method:method||'GET',headers:{'Content-Type':'application/json'}};if(body)o.body=JSON.stringify(body);const r=await fetch(url,o);return await r.json();}catch(e){return{ok:false,error:'Соединение'};}}
function setTheme(t){currentTheme=t;document.body.setAttribute('data-theme',t);try{localStorage.setItem('awesome_theme',t);}catch(e){}}
function toggleTheme(){setTheme(currentTheme==='dark'?'light':'dark');api('/api/settings','POST',{theme:currentTheme});}
function switchTab(m){authMode=m;document.getElementById('tabLogin').className='tab'+(m==='login'?' active':'');document.getElementById('tabReg').className='tab'+(m==='reg'?' active':'');document.getElementById('regFields').style.display=m==='reg'?'block':'none';document.getElementById('tgField').style.display=m==='reg'?'block':'none';document.getElementById('regRef').style.display=m==='reg'?'block':'none';document.getElementById('authTitle').textContent=m==='reg'?'Регистрация':'Вход';document.getElementById('authBtn').textContent=m==='reg'?'Создать аккаунт':'Войти';}
async function submitAuth(){const id=document.getElementById('regId').value.trim(),pw=document.getElementById('regPass').value;if(!id||!pw){toast('Заполни ID и пароль','error');return;}let body={user_id:id,password:pw};if(authMode==='reg'){body.name=document.getElementById('regName').value.trim()||id;body.telegram_id=document.getElementById('regTg').value.trim()||null;body.ref=document.getElementById('regRef').value.trim()||null;}const r=await api(authMode==='reg'?'/api/register':'/api/login','POST',body);if(r.ok){currentUserId=r.user_id;document.getElementById('authOverlay').style.display='none';toast('Добро пожаловать!','success');init();}else toast(r.error||'Ошибка','error');}
async function logout(){await api('/api/logout','POST');location.reload();}
function openSettings(){api('/api/profile').then(r=>{if(r.ok){document.getElementById('setName').value=r.name||'';document.getElementById('setTg').value=r.telegram_id||'';document.getElementById('setAvatar').value=r.avatar||'';document.getElementById('setTheme').value=r.theme||'dark';document.getElementById('refInfo').innerHTML='🔗 Реферальный код: <b>'+r.ref_code+'</b><br>Приглашено: '+r.ref_count+' чел.';}}).catch(()=>{});document.getElementById('settingsOverlay').style.display='flex';}
async function saveSettings(){const body={};body.name=document.getElementById('setName').value.trim()||undefined;body.telegram_id=document.getElementById('setTg').value.trim()||null;body.avatar=document.getElementById('setAvatar').value.trim()||undefined;body.theme=document.getElementById('setTheme').value;const r=await api('/api/settings','POST',body);if(r.ok){setTheme(body.theme);toast('Сохранено','success');document.getElementById('settingsOverlay').style.display='none';init();}else toast('Ошибка','error');}
// Админ
async function openAdmin(){const r=await api('/api/admin/stats');if(!r.ok){toast('Нет доступа','error');return;}let h='<div class="stat-card">';
h+='<div class="scard"><div class="n">'+r.total+'</div><div class="l">Пользователей</div></div>';
h+='<div class="scard"><div class="n">'+r.premium+'</div><div class="l">Premium</div></div>';
h+='<div class="scard"><div class="n">'+r.admins+'</div><div class="l">Админов</div></div>';
h+='<div class="scard"><div class="n">'+r.chats+'</div><div class="l">Чатов</div></div>';
h+='<div class="scard"><div class="n">'+r.messages+'</div><div class="l">Сообщений</div></div>';
h+='</div><h3 style="margin:10px 0">Пользователи</h3>';
(r.users||[]).forEach(u=>{h+='<div class="adm-user"><b>'+esc(u.name||u.id)+'</b> (#'+esc(u.id)+') Lv'+u.level+' | XP:'+u.xp+' <select onchange="adminSet(\''+esc(u.id)+'\',\'premium\',this.value)"><option value="0"'+(u.premium?'':' selected')+'>Free</option><option value="1"'+(u.premium?' selected':'')+'>Premium</option></select> <button class="tool-btn" onclick="adminSet(\''+esc(u.id)+'\',\'is_admin\','+(u.is_admin?'0':'1')+')">'+(u.is_admin?'⬇️ Снять админа':'👑 Дать админа')+'</button></div>';});
h+='<h3 style="margin:10px 0">Рассылка</h3><textarea id="bcastText" style="width:100%;padding:10px;background:var(--bg2);border:1px solid var(--border);border-radius:10px;color:var(--text);resize:none" rows="2"></textarea><button class="tool-btn" style="margin-top:6px" onclick="adminBroadcast()">📢 Отправить всем</button>';
document.getElementById('adminContent').innerHTML=h;document.getElementById('adminOverlay').style.display='flex';}
async function adminSet(id,field,val){const r=await api('/api/admin/give','POST',{user_id:id,field:field,value:val});if(r.ok){toast('OK','success');openAdmin();}else toast('Ошибка','error');}
async function adminBroadcast(){const t=document.getElementById('bcastText').value;if(!t)return;const r=await api('/api/admin/broadcast','POST',{text:t});if(r.ok){toast('Отправлено: '+r.sent+'/'+r.total,'success');openAdmin();}}
function esc(s){return String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function handleFile(inp){const f=inp.files[0];if(!f)return;attachedType=f.type.includes('pdf')?'pdf':'image';const reader=new FileReader();reader.onload=e=>{if(attachedType==='image'){attachedImage=e.target.result;document.getElementById('attachImg').src=attachedImage;document.getElementById('attachImg').style.display='';}else{attachedImage=e.target.result;document.getElementById('attachImg').src='data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg"><text y="30" font-size="20">📄</text></svg>';document.getElementById('attachImg').style.display='';}document.getElementById('attachName').textContent=f.name+' ('+attachedType+')';document.getElementById('attachPreview').style.display='flex';};reader.readAsDataURL(f);inp.value='';}
function removeAttach(){attachedImage=null;document.getElementById('attachPreview').style.display='none';}
function formatAI(t){if(!t)return '';const lines=t.split('\n');let out='';for(const line of lines){const h=line.match(/^\*\*(.+?)\*\*$/);if(h){out+='<div class="h">'+esc(h[1])+'</div>';continue;}const parts=line.split(/(\*\*.*?\*\*)/g);let p='';for(const part of parts){if(part.startsWith('**')&&part.endsWith('**')&&part.length>4)p+='<b>'+esc(part.slice(2,-2))+'</b>';else p+=esc(part);}out+='<div style="margin:3px 0">'+p+'</div>';}return out;}
function addMsg(role,text,img,isGen){const box=document.getElementById('messages');if(document.getElementById('welcome'))document.getElementById('welcome').style.display='none';const m=document.createElement('div');m.className='msg '+role;let b='';if(img){b+=isGen?'<img class="g" src="'+img+'">':'<img class="a" src="'+img+'">';}let content='';if(role==='ai'&&text)content=formatAI(text);else if(text)content=esc(text);const acts=role==='ai'?'<div class="msg-actions"><button onclick="copyMsg(this)">📋</button><button onclick="regen()">🔄</button><button onclick="tts(this)">🔊</button><button onclick="translateMsg(this)">🌐</button></div>':'';m.innerHTML='<div class="avatar">'+(role==='ai'?'🤖':String(currentUserId||'?').slice(0,1).toUpperCase())+'</div><div class="bubble">'+b+content+'</div>'+acts;box.appendChild(m);box.scrollTop=box.scrollHeight;return m;}
function copyMsg(btn){const b=btn.closest('.msg').querySelector('.bubble');const t=document.createElement('textarea');t.value=b.innerText;document.body.appendChild(t);t.select();document.execCommand('copy');t.remove();toast('Скопировано 📋','success');}
function regen(){if(sending)return;const box=document.getElementById('messages');const ms=box.querySelectorAll('.msg');if(ms.length<2)return;const last=ms[ms.length-1];if(last.classList.contains('ai')){last.remove();const us=box.querySelectorAll('.msg.user');if(us.length){const u=us[us.length-1];sendMessage(u.querySelector('.bubble').innerText,true);}}}
async function translateMsg(btn){const b=btn.closest('.msg').querySelector('.bubble').innerText;const r=await api('/api/translate','POST',{text:b,target:'ru'});if(r.ok)toast('🌐 '+r.translated.slice(0,200),'success');}
async function translateLast(){const box=document.getElementById('messages');const ms=box.querySelectorAll('.msg.ai');if(!ms.length)return;const b=ms[ms.length-1].querySelector('.bubble').innerText;const r=await api('/api/translate','POST',{text:b,target:'ru'});if(r.ok){toast('🌐 Перевод:\n'+r.translated.slice(0,300),'success');}}
function tts(btn){const b=btn?btn.closest('.msg').querySelector('.bubble').innerText:document.getElementById('lastAI');if(!b)return;if('speechSynthesis'in window){const u=new SpeechSynthesisUtterance(b);u.lang='ru-RU';speechSynthesis.speak(u);toast('🔊 Озвучиваю...','success');}else toast('Не поддерживается','error');}
function addTyping(){const box=document.getElementById('messages');const m=document.createElement('div');m.className='msg ai';m.id='typing';m.innerHTML='<div class="avatar">🤖</div><div class="bubble"><div class="typing-dots"><span></span><span></span><span></span></div></div>';box.appendChild(m);box.scrollTop=box.scrollHeight;}
function removeTyping(){const t=document.getElementById('typing');if(t)t.remove();}
async function sendMessage(text,regenMode){if(sending&&!regenMode)return;const input=document.getElementById('input');const msg=(text!==undefined&&text!==null)?text:input.value.trim();if(!msg&&!attachedImage)return;if(!regenMode){input.value='';addMsg('user',msg,attachedType==='image'?attachedImage:null,false);}setSending(true);addTyping();try{const body={message:msg,chat_id:currentChatId};if(attachedImage){if(attachedType==='pdf')body.document={type:'pdf',name:document.getElementById('attachName').textContent,data:attachedImage};else body.image=attachedImage;}const r=await api('/api/chat','POST',body);removeTyping();if(r.ok){currentChatId=r.chat_id;const ai=addMsg('ai',r.response,null,false);document.getElementById('lastAI'=ai;);document.getElementById('currentChatTitle').textContent='Чат';loadChats();}else{addMsg('ai','⚠️ '+r.error);toast(r.error,'error');}}catch(e){removeTyping();addMsg('ai','⚠️ Ошибка');}attachedImage=null;document.getElementById('attachPreview').style.display='none';setSending(false);checkStatus();}
function setSending(v){sending=v;document.getElementById('sendBtn').disabled=v;document.getElementById('input').disabled=v;}
function onKey(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMessage();}}
function sendSuggestion(t){sendMessage(t);}
async function newChat(){const r=await api('/api/chat/new','POST');if(r.ok){currentChatId=r.chat_id;document.getElementById('messages').innerHTML='';document.getElementById('welcome').style.display='';document.getElementById('currentChatTitle').textContent='Новый чат';document.getElementById('sidebar').classList.remove('open');}}
async function loadChats(){const r=await api('/api/chats');if(!r.ok)return;const list=document.getElementById('chatList');list.innerHTML='';r.chats.forEach(c=>{const it=document.createElement('div');it.className='chat-item'+(c.id===currentChatId?' active':'');it.innerHTML=(c.pinned?'⭐ ':'💬')+'<span class="t">'+esc(c.title||'Новый чат')+'</span><button class="star" onclick="pinChat('+c.id+',event)">⭐</button><button class="del" onclick="delChat('+c.id+',event)">✕</button>';it.onclick=()=>openChat(c);list.appendChild(it);});}
function openChat(c){currentChatId=c.id;const box=document.getElementById('messages');box.innerHTML='';document.getElementById('currentChatTitle').textContent=c.title||'Чат';(c.messages||[]).forEach(m=>addMsg(m.role,m.content,m.image,false));document.getElementById('sidebar').classList.remove('open');}
async function delChat(id,e){e.stopPropagation();if(!confirm('Удалить чат?'))return;await api('/api/chat/delete','POST',{chat_id:id});if(id===currentChatId){currentChatId=null;boxReset();}loadChats();}
async function pinChat(id,e){e.stopPropagation();await api('/api/chat/pin','POST',{chat_id:id});loadChats();}
async function searchChats(q){if(!q){loadChats();return;}const r=await api('/api/search','POST',{q});if(!r.ok)return;const list=document.getElementById('chatList');list.innerHTML='';r.results.forEach(c=>{const it=document.createElement('div');it.className='chat-item';it.innerHTML='🔍 <span class="t">'+esc(c.title)+'</span>';it.onclick=()=>openChat({id:c.chat_id,title:c.title,messages:[]});list.appendChild(it);});}
function boxReset(){document.getElementById('messages').innerHTML='';document.getElementById('welcome').style.display='';document.getElementById('currentChatTitle').textContent='Новый чат';}
function clearHistory(){if(!confirm('Очистить историю?'))return;document.getElementById('messages').innerHTML='';document.getElementById('welcome').style.display='';toast('Очищено','success');}
async function checkStatus(){const r=await api('/api/status');if(!r.ok){toast('Авторизуйся','error');return;}document.getElementById('userStatus').textContent=r.status_text+' · '+r.limit_text;document.getElementById('userLevel').textContent='Уровень '+r.level+' · XP '+r.xp;if(r.is_owner)document.getElementById('adminBtn').style.display='';else document.getElementById('adminBtn').style.display='none';}
async function draw(){const input=document.getElementById('input');const p=prompt('🎨 Опиши что нарисовать:',input.value||'');if(!p||!p.trim())return;addMsg('user','🎨 '+p,null,false);setSending(true);addTyping();const r=await api('/api/draw','POST',{prompt:p});removeTyping();if(r.ok&&r.image){addMsg('ai','Готово!',r.image,true);}else addMsg('ai','⚠️ '+(r.error||'Не удалось'));setSending(false);checkStatus();}
function startVoice(){if(!('webkitSpeechRecognition'in window)){toast('Голос не поддерживается','error');return;}const SR=window.webkitSpeechRecognition;const rec=new SR();rec.lang='ru-RU';rec.onresult=e=>{document.getElementById('input').value+=e.results[0][0].transcript;};rec.start();toast('Говори... 🎤','success');}
async function init(){const me=await api('/api/me');if(me.ok){currentUserId=me.user_id;document.getElementById('authOverlay').style.display='none';document.getElementById('userAvatar').textContent=String(me.name||me.user_id).slice(0,1).toUpperCase();document.getElementById('userName').textContent=me.name||me.user_id;document.getElementById('userStatus').textContent='...';if(me.theme)setTheme(me.theme);await loadChats();await checkStatus();}else{document.getElementById('authOverlay').style.display='flex';try{const t=localStorage.getItem('awesome_theme');if(t)setTheme(t);}catch(e){}}}
document.addEventListener('DOMContentLoaded',init);
</script></body></html>"""

if __name__ == '__main__':
    print("="*60)
    print("🧠 AWESOME AI WEB — 35+ функций")
    print("="*60)
    print("✅ Админ-панель (только владелец 6652898792 / @flidges)")
    print("✅ Красивый дизайн + анимации")
    print("✅ 35+ функций DeepSeek")
    print("="*60)
    port=int(os.getenv("PORT",8080))
    app.run(host='0.0.0.0',port=port,debug=False,threaded=True)
