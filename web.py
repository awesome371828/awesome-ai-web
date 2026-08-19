#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AWESOME AI WEB — вход по Telegram-ID+пароль, связка бот+сайт+Supabase, много функций"""

import os, re, io, time, json, base64, urllib.parse, hashlib, random, html
from datetime import datetime, timedelta, timezone
import requests, urllib3
import psycopg2, psycopg2.extras
from flask import Flask, request, jsonify, render_template_string, session
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
from supabase import create_client

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY","awesome-ai-super-secret-key-2026")
app.permanent_session_lifetime = timedelta(days=30)

# Ключи
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY","AQVNyfn82epL9dy8C_kftzeypq6eF9lFd6SZnFzV")
FOLDER_ID = os.getenv("FOLDER_ID","b1g4aq87c7j61c6g3i5l")
GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY","MDFhMDBkNmEtMmExNC03M2JkLWFlZmMtOTQ0OWVlOTc5M2U1OmE1ZWJhM2NlLTQwYjAtNDZlYi1iMmY2LTE3OTFmYzhhYTQ2MA==")
SUPABASE_URL = os.getenv("SUPABASE_URL","https://lprxbmshmuucymkgaqwk.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY","eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxwcnhibXNobXV1Y3lta2dhcXdrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY3NDk0MjgsImV4cCI6MjEwMjMyNTQyOH0.Ie9jSH5RMxeOq8aU-Dv6MXlojWMUTOLE723Hdg6heZU")
DATABASE_URL = os.getenv("DATABASE_URL","postgresql://u_cmsu43cr30:3sdZICdPDoR1DUrRRKsJ8yW1BqrH2PvZ@db-team-cmsu3ykqi0295mo01tsv8m15p:5432/db_awesome_ai_web")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN","8336209662:AAHdhYXhqWA-LtthwgydDSRU7A6A0ceC-HY")
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
def is_owner(uid=None, tg=None, username=None):
    if uid and str(uid)==str(OWNER_ID): return True
    if tg and str(tg)==str(OWNER_ID): return True
    if username and str(username).lower()==OWNER_USERNAME: return True
    return False

# ===== БАЗА (user_id = telegram_id для связки с ботом) =====
def init_db():
    conn=get_db(); cur=conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users(
        user_id TEXT PRIMARY KEY, name TEXT, password TEXT, telegram_id TEXT,
        premium INTEGER DEFAULT 0, messages_today INTEGER DEFAULT 0, last_reset TEXT,
        premium_expires TEXT, is_admin INTEGER DEFAULT 0, is_owner INTEGER DEFAULT 0,
        theme TEXT DEFAULT 'dark', joined_at TEXT, xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1,
        avatar TEXT DEFAULT '', ref_code TEXT, ref_count INTEGER DEFAULT 0, fav_ai TEXT DEFAULT 'gigachat')""")
    cur.execute("""CREATE TABLE IF NOT EXISTS chats_web(id BIGSERIAL PRIMARY KEY, user_id TEXT,
        title TEXT DEFAULT 'Новый чат', created_at TEXT, pinned INTEGER DEFAULT 0)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS messages_web(id BIGSERIAL PRIMARY KEY, chat_id BIGINT,
        role TEXT, content TEXT, image TEXT, created_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS total_stats_web(user_id TEXT PRIMARY KEY, total_messages INTEGER DEFAULT 0)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS shared_chats(id TEXT PRIMARY KEY, chat_id BIGINT, created_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS admin_log(id BIGSERIAL PRIMARY KEY, admin_id TEXT, action TEXT, created_at TEXT)""")
    for col in ['xp','level','avatar','ref_code','ref_count','fav_ai']:
        try: cur.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} TEXT DEFAULT ''")
        except: pass
    try: cur.execute("ALTER TABLE chats_web ADD COLUMN IF NOT EXISTS pinned INTEGER DEFAULT 0")
    except: pass
    try: cur.execute("ALTER TABLE messages_web ADD COLUMN IF NOT EXISTS image TEXT")
    except: pass
    conn.commit(); cur.close(); conn.close()
    print("✅ База данных готова (аккаунт = Telegram-ID)")
init_db()
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ===== СТАТУС ИЗ БАЗЫ БОТА (Supabase) =====
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
    cur.execute("SELECT premium,premium_expires,is_admin,is_owner,telegram_id,level,xp,ref_count,fav_ai FROM users WHERE user_id=%s",(uid,))
    row=cur.fetchone(); cur.close(); conn.close()
    u=dict(row) if row else {'premium':0,'premium_expires':None,'is_admin':0,'is_owner':0,'telegram_id':None,'level':1,'xp':0,'ref_count':0,'fav_ai':'gigachat'}
    tg=tg or u.get('telegram_id')
    owner=1 if is_owner(uid,tg) else 0
    bot=bot_status(tg)
    if bot:
        if bot.get('is_owner')==1: owner=1
        # SYNC: премиум из Supabase всегда синхронизируется
        if bot.get('premium')==1:
            u['premium']=1; u['premium_expires']=bot.get('premium_expires')
        elif bot.get('premium')==0 and not u.get('premium'):
            u['premium']=0
        if bot.get('is_admin')==1: u['is_admin']=1
    if u.get('premium')==1 and u.get('premium_expires'):
        try:
            if gm()>datetime.strptime(u['premium_expires'],'%Y-%m-%d %H:%M:%S').replace(tzinfo=MOSCOW_TZ):
                u['premium']=0; u['premium_expires']=None
        except: pass
    return {'premium':1 if(owner or u.get('premium')) else 0,'premium_expires':u.get('premium_expires'),
            'is_admin':1 if(owner or u.get('is_admin')) else 0,'is_owner':owner,'telegram_id':tg,
            'level':u.get('level',1),'xp':u.get('xp',0),'ref_count':u.get('ref_count',0),'fav_ai':u.get('fav_ai','gigachat')}

# ===== АККАУНТЫ (имя + telegram_id + пароль) =====
def reg_user(telegram_id,name,pw):
    if not telegram_id or not telegram_id.isdigit(): return False,"Введи корректный Telegram-ID"
    if not name or len(name)<1: return False,"Имя обязательно"
    if not pw or len(pw)<3: return False,"Пароль мин. 3 символа"
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id=%s",(str(telegram_id),))
    if cur.fetchone(): cur.close(); conn.close(); return False,"Этот Telegram-ID уже зарегистрирован"
    ref_code=hashlib.md5((str(telegram_id)+str(random.random())).encode()).hexdigest()[:8]
    owner=1 if str(telegram_id)==str(OWNER_ID) else 0
    cur.execute("INSERT INTO users(user_id,name,password,telegram_id,messages_today,last_reset,is_admin,is_owner,theme,joined_at,ref_code) VALUES(%s,%s,%s,%s,0,%s,%s,%s,'dark',%s,%s)",
                (str(telegram_id),name,hash_pw(pw),str(telegram_id),gm().strftime('%Y-%m-%d'),owner,owner,now_iso(),ref_code))
    cur.execute("INSERT INTO total_stats_web(user_id,total_messages) VALUES(%s,0) ON CONFLICT DO NOTHING",(str(telegram_id),))
    conn.commit(); cur.close(); conn.close(); return True,"OK"

def login_user(telegram_id,pw):
    if not telegram_id: return False,"Введи Telegram-ID"
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM users WHERE user_id=%s",(str(telegram_id),))
    row=cur.fetchone(); cur.close(); conn.close()
    if not row: return False,"Аккаунт не найден"
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
    if s['is_owner'] or s['is_admin']: add_xp(uid,5); return
    conn=get_db(); cur=conn.cursor()
    cur.execute("UPDATE users SET messages_today=messages_today+1 WHERE user_id=%s",(str(uid),))
    cur.execute("INSERT INTO total_stats_web(user_id,total_messages) VALUES(%s,1) ON CONFLICT(user_id) DO UPDATE SET total_messages=total_stats_web.total_messages+1",(str(uid),))
    conn.commit(); cur.close(); conn.close(); add_xp(uid,10)

def add_xp(uid,amt):
    conn=get_db(); cur=conn.cursor()
    cur.execute("UPDATE users SET xp=xp+%s WHERE user_id=%s",(amt,str(uid)))
    cur.execute("UPDATE users SET level=1+floor(xp/100) WHERE user_id=%s",(str(uid),))
    conn.commit(); cur.close(); conn.close()

def upd_settings(uid,**kw):
    conn=get_db(); cur=conn.cursor()
    for k,v in kw.items():
        if v is not None: cur.execute(f"UPDATE users SET {k}=%s WHERE user_id=%s",(v,str(uid)))
    conn.commit(); cur.close(); conn.close()

def log_admin(admin_id,action):
    conn=get_db(); cur=conn.cursor()
    cur.execute("INSERT INTO admin_log(admin_id,action,created_at) VALUES(%s,%s,%s)",(str(admin_id),action,now_iso()))
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
    m=get_msgs(cid); return m[-MAX_HISTORY:] if m else []
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
        c=giga(hist+[{"role":"assistant","content":first},{"role":"user","content":"Продолжи с того места, где остановился, закончи мысль полностью."}],sysp,2000)
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
ПРАВИЛА: полный развёрнутый ответ, раскрывай тему целиком. Разделяй на РАЗДЕЛЫ с подзаголовками **1. Утро**. Важное **жирным**. Без "возможно/наверное/извини". Примеры, цифры, эмодзи (🔥🧠💡⚡🚀). Ответ такой полный, чтобы не осталось вопросов.
💎 PREMIUM — максимальная глубина. Ты живая нейросеть!"""

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
        return "".join(page.get_text() for page in doc)[:6000] or "PDF без текста"
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
                    'level':s['level'],'xp':s['xp'],'ref_count':s['ref_count'],'fav_ai':s['fav_ai']})

@app.route('/api/chat',methods=['POST'])
def api_chat():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False,'error':'Авторизуйся'})
    u=get_user(uid); tg=u.get('telegram_id') if u else uid
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
    return render_template_string("""<html><head><title>Поделиться</title><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{background:#12141c;color:#eceaf5;font-family:Segoe UI;padding:20px;max-width:760px;margin:auto}.m{background:#1f2230;border-radius:12px;padding:12px;margin:10px 0;white-space:pre-wrap}.user{background:#ff8a3d;color:#fff}</style></head><body><h2>💬 Общий чат</h2>{{h|safe}}</body></html>""",
        h="".join(f'<div class="m {"user" if m["role"]=="user" else ""}">{"Вы" if m["role"]=="user" else "🤖 AWESOME AI"}:<br>'+html.escape(m.get("content") or "")+"</div>" for m in msgs))

@app.route('/api/export',methods=['POST'])
def api_export():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False})
    msgs=get_msgs(request.json.get('chat_id'))
    txt="".join(("Вы: " if m['role']=='user' else "AWESOME AI: ")+str(m.get('content') or "")+"\n\n" for m in msgs)
    f=io.BytesIO(txt.encode('utf-8'))
    from flask import send_file as sf
    return sf(f,as_attachment=True,download_name="chat.txt",mimetype="text/plain")

@app.route('/api/translate',methods=['POST'])
def api_translate():
    d=request.json; return jsonify({'ok':True,'translated':translate(d.get('text',''),d.get('target','ru'))})

@app.route('/api/draw',methods=['POST'])
def api_draw():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False,'error':'Авторизуйся'})
    u=get_user(uid); tg=u.get('telegram_id') if u else uid
    if not can_send(uid,tg): return jsonify({'ok':False,'error':'Лимит!'})
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
                    'is_admin':bool(s['is_admin']),'is_owner':bool(s['is_owner']),'level':s['level'],'xp':s['xp'],'ref_count':s['ref_count'],
                    'premium_expires':fmt_date(s['premium_expires']) if s['premium'] else None,
                    'messages_today':row[0] if row else 0,'total_messages':tot[0] if tot else 0,'joined_at':u.get('joined_at')})

@app.route('/api/settings',methods=['POST'])
def api_settings():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False})
    d=request.json
    upd_settings(uid,name=d.get('name'),theme=d.get('theme'),avatar=d.get('avatar'),fav_ai=d.get('fav_ai'))
    if d.get('name'): session['name']=d['name']
    return jsonify({'ok':True})

@app.route('/api/search',methods=['POST'])
def api_search():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False})
    q=request.json.get('q','').lower()
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id,title FROM chats_web WHERE user_id=%s",(str(uid),))
    chats=cur.fetchall(); cur.close(); conn.close()
    res=[]
    for c in chats:
        for m in get_msgs(c['id']):
            if q in str(m.get('content') or '').lower():
                res.append({'chat_id':c['id'],'title':c.get('title','Чат'),'snippet':str(m.get('content') or '')[:80]}); break
    return jsonify({'ok':True,'results':res[:20]})

# ===== АДМИН =====
@app.route('/api/admin/stats')
def admin_stats():
    uid=session.get('user_id'); u=get_user(uid)
    if not is_owner(uid,u.get('telegram_id') if u else None): return jsonify({'ok':False,'error':'Нет доступа'})
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
    uid=session.get('user_id'); u=get_user(uid)
    if not is_owner(uid,u.get('telegram_id') if u else None): return jsonify({'ok':False,'error':'Нет доступа'})
    d=request.json; target=str(d.get('user_id','')).strip(); field=d.get('field'); val=d.get('value')
    if not target or not field: return jsonify({'ok':False,'error':'Данные'})
    # синхронизация в Supabase: если даём premium — записываем и в бота
    if field in ('premium','is_admin'):
        try:
            botrow=supabase.table('users').select('premium,premium_expires,is_admin').eq('user_id',int(target)).execute()
            if botrow.data:
                if field=='premium':
                    exp=gm()+timedelta(days=30)
                    supabase.table('users').update({'premium':int(val),'premium_expires':exp.strftime('%Y-%m-%d %H:%M:%S')}).eq('user_id',int(target)).execute()
                if field=='is_admin':
                    supabase.table('users').update({'is_admin':int(val)}).eq('user_id',int(target)).execute()
        except: pass
    upd_settings(target,**{field:val})
    log_admin(uid,f"Выдал {field}={val} для {target}")
    return jsonify({'ok':True})

@app.route('/api/admin/broadcast',methods=['POST'])
def admin_broadcast():
    uid=session.get('user_id'); u=get_user(uid)
    if not is_owner(uid,u.get('telegram_id') if u else None): return jsonify({'ok':False,'error':'Нет доступа'})
    text=request.json.get('text','')
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT user_id FROM users"); ids=[r[0] for r in cur.fetchall()]; cur.close(); conn.close()
    sent=0
    for uid2 in ids:
        try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",json={"chat_id":uid2,"text":text}); sent+=1
        except: pass
    log_admin(uid,f"Рассылка: {text[:50]} ({sent}/{len(ids)})")
    return jsonify({'ok':True,'sent':sent,'total':len(ids)})

@app.route('/api/admin/logs')
def admin_logs():
    uid=session.get('user_id'); u=get_user(uid)
    if not is_owner(uid,u.get('telegram_id') if u else None): return jsonify({'ok':False})
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM admin_log ORDER BY id DESC LIMIT 50")
    rows=cur.fetchall(); cur.close(); conn.close()
    return jsonify({'ok':True,'logs':[dict(r) for r in rows]})

# ===== HTML (оптимизированный) =====
INDEX_HTML = r"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no"><title>AWESOME AI</title>
<style>
:root{--bg:#12141c;--bg2:#191c26;--panel:#1f2230;--border:#2c3040;--accent:#ff8a3d;--accent2:#ff6b1a;--text:#eceaf5;--muted:#9a96ab;--danger:#ff5b6e;--success:#3ddc84}
[data-theme="light"]{--bg:#f6f5f9;--bg2:#fff;--panel:#fff;--border:#e4e1ec;--accent:#f07800;--accent2:#ff6b1a;--text:#23202e;--muted:#6d6a80}
*{margin:0;padding:0;box-sizing:border-box;font-family:'Segoe UI',system-ui,sans-serif}
body{background:var(--bg);color:var(--text);height:100vh;overflow:hidden;transition:background .3s,color .3s;-webkit-font-smoothing:antialiased}
.app{display:flex;height:100vh}
.sidebar{width:280px;background:var(--panel);border-right:1px solid var(--border);display:flex;flex-direction:column;transition:transform .25s;z-index:50}
.sidebar-header{padding:16px;display:flex;align-items:center;gap:10px;border-bottom:1px solid var(--border)}
.logo{width:42px;height:42px;border-radius:14px;background:linear-gradient(135deg,var(--accent),var(--accent2));display:flex;align-items:center;justify-content:center;font-size:21px;flex-shrink:0}
.brand{font-weight:800;font-size:17px;background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.new-chat{margin:14px;padding:13px;background:linear-gradient(135deg,var(--accent),var(--accent2));border:none;border-radius:14px;color:#fff;font-weight:700;cursor:pointer;font-size:14px}
.new-chat:active{transform:scale(.98)}
.chat-list{flex:1;overflow-y:auto;padding:0 10px}
.chat-item{padding:11px 12px;border-radius:12px;cursor:pointer;margin-bottom:4px;font-size:13px;display:flex;align-items:center;gap:8px}
.chat-item:hover,.chat-item.active{background:var(--bg2)}
.chat-item .t{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.chat-item .del{opacity:0;background:none;border:none;color:var(--danger);cursor:pointer;font-size:14px}
.chat-item:hover .del{opacity:1}
.sidebar-footer{padding:12px;border-top:1px solid var(--border)}
.user-box{display:flex;align-items:center;gap:10px;padding:10px;background:var(--bg2);border-radius:14px}
.avatar{width:38px;height:38px;border-radius:50%;background:linear-gradient(135deg,var(--accent),var(--accent2));display:flex;align-items:center;justify-content:center;font-weight:700;font-size:16px;flex-shrink:0;color:#fff}
.user-info{flex:1;min-width:0}
.user-name{font-weight:600;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.user-status{font-size:11px;color:var(--accent)}
.user-actions{display:flex;gap:2px}
.mini-btn{background:none;border:none;color:var(--muted);cursor:pointer;font-size:16px;padding:4px}
.mini-btn:hover{color:var(--accent)}
.main{flex:1;display:flex;flex-direction:column;min-width:0}
.main-header{height:56px;display:flex;align-items:center;justify-content:center;border-bottom:1px solid var(--border);position:relative}
.mobile-toggle{display:none;position:absolute;left:14px;background:none;border:none;color:var(--text);font-size:22px;cursor:pointer}
.messages{flex:1;overflow-y:auto;padding:20px;scroll-behavior:smooth}
.welcome{max-width:720px;margin:0 auto;text-align:center;padding-top:6vh}
.welcome h1{font-size:clamp(28px,5vw,46px);margin-bottom:12px;background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.welcome p{color:var(--muted);margin-bottom:28px;font-size:16px}
.suggestion-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;max-width:640px;margin:0 auto}
.sugg{background:var(--panel);border:1px solid var(--border);border-radius:16px;padding:18px;cursor:pointer;transition:transform .15s,border-color .15s;font-size:13px;text-align:left}
.sugg:hover{transform:translateY(-3px);border-color:var(--accent)}
.sugg:active{transform:scale(.97)}
.sugg .ic{font-size:26px;margin-bottom:10px;display:block}
.msg{max-width:760px;margin:0 auto 18px;display:flex;gap:12px;position:relative}
.msg.user{flex-direction:row-reverse}
.msg .bubble{padding:14px 18px;border-radius:18px;font-size:15px;line-height:1.65;max-width:82%;white-space:pre-wrap;word-break:break-word}
.msg.user .bubble{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;border-top-right-radius:6px}
.msg.ai .bubble{background:var(--panel);border:1px solid var(--border);border-top-left-radius:6px}
.msg .bubble b{color:var(--accent)}
.msg .bubble .h{display:block;font-weight:800;color:var(--accent);font-size:16px;margin:12px 0 6px;padding-top:10px;border-top:1px solid var(--border)}
.msg .bubble .h:first-child{border:none;margin-top:0;padding-top:0}
.msg .bubble img.a{max-width:240px;border-radius:12px;margin-top:8px;display:block}
.msg .bubble img.g{max-width:100%;border-radius:12px;margin-top:8px}
.msg-actions{position:absolute;top:8px;right:8px;display:flex;gap:4px;opacity:0;transition:.2s}
.msg:hover .msg-actions{opacity:1}
.msg-actions button{background:var(--bg2);border:1px solid var(--border);color:var(--muted);border-radius:8px;cursor:pointer;font-size:12px;padding:4px 8px}
.msg-actions button:hover{color:var(--accent)}
.typing-dots{display:inline-flex;gap:5px;padding:8px 2px}
.typing-dots span{width:9px;height:9px;border-radius:50%;background:var(--accent);animation:bounce 1.2s infinite}
.typing-dots span:nth-child(2){animation-delay:.2s}.typing-dots span:nth-child(3){animation-delay:.4s}
@keyframes bounce{0%,100%{transform:translateY(0);opacity:.4}50%{transform:translateY(-7px);opacity:1}}
.input-area{padding:14px;border-top:1px solid var(--border);background:var(--bg)}
.attach-preview{max-width:760px;margin:0 auto 8px;display:none;gap:8px;align-items:center;background:var(--bg2);border:1px solid var(--border);border-radius:14px;padding:8px}
.attach-preview img{width:52px;height:52px;object-fit:cover;border-radius:8px}
.attach-preview .an{flex:1;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.attach-preview .rm{background:none;border:none;color:var(--danger);cursor:pointer;font-size:18px}
.input-wrap{max-width:760px;margin:0 auto;display:flex;align-items:flex-end;gap:6px;background:var(--bg2);border:1px solid var(--border);border-radius:20px;padding:8px}
.input-wrap:focus-within{border-color:var(--accent)}
textarea{flex:1;background:none;border:none;outline:none;color:var(--text);font-size:15px;resize:none;max-height:130px;padding:8px 4px}
.icon-btn{width:38px;height:38px;border-radius:12px;background:none;border:none;color:var(--muted);font-size:17px;cursor:pointer;flex-shrink:0}
.icon-btn:hover{color:var(--accent)}
.send-btn{width:44px;height:44px;border-radius:14px;background:linear-gradient(135deg,var(--accent),var(--accent2));border:none;color:#fff;font-size:18px;cursor:pointer;flex-shrink:0}
.send-btn:disabled{opacity:.4;cursor:not-allowed}
.toolbar{max-width:760px;margin:10px auto 0;display:flex;gap:8px;flex-wrap:wrap}
.tool-btn{background:var(--panel);border:1px solid var(--border);color:var(--muted);border-radius:10px;padding:7px 13px;font-size:12px;cursor:pointer}
.tool-btn:hover{color:var(--text);border-color:var(--accent)}
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:100;display:flex;align-items:center;justify-content:center;padding:16px}
.modal{background:var(--panel);border:1px solid var(--border);border-radius:22px;padding:30px;width:100%;max-width:420px;text-align:center;max-height:92vh;overflow-y:auto}
.modal .tabs{display:flex;gap:8px;margin-bottom:16px}
.modal .tab{flex:1;padding:11px;border-radius:12px;background:var(--bg2);border:1px solid var(--border);color:var(--muted);cursor:pointer;font-weight:700;font-size:14px}
.modal .tab.active{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;border:none}
.modal h2{margin-bottom:8px}.modal p{color:var(--muted);font-size:14px;margin-bottom:16px}
.modal input,.modal select{width:100%;padding:13px;background:var(--bg2);border:1px solid var(--border);border-radius:12px;color:var(--text);font-size:15px;margin-bottom:10px;outline:none}
.modal input:focus{border-color:var(--accent)}
.modal .btn{width:100%;padding:14px;border:none;border-radius:12px;background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;font-weight:700;font-size:15px;cursor:pointer;margin-bottom:8px}
.modal .btn.ghost{background:var(--bg2);color:var(--muted);border:1px solid var(--border)}
.hint{font-size:12px;color:var(--muted);margin-top:10px;line-height:1.5}
.toast{position:fixed;top:20px;right:20px;background:var(--panel);border:1px solid var(--border);border-radius:14px;padding:14px 20px;z-index:300;box-shadow:0 8px 30px rgba(0,0,0,.4);max-width:320px}
.toast.error{border-color:var(--danger)}.toast.success{border-color:var(--success)}
.scrollbar::-webkit-scrollbar{width:6px}.scrollbar::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
.stat-card{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:12px;margin-bottom:18px}
.scard{background:var(--bg2);border:1px solid var(--border);border-radius:14px;padding:14px;text-align:center}
.scard .n{font-size:26px;font-weight:800;color:var(--accent)}
.scard .l{font-size:12px;color:var(--muted)}
.adm-user{display:flex;align-items:center;gap:8px;padding:8px;background:var(--bg2);border-radius:10px;margin-bottom:6px;font-size:13px}
.adm-user select{width:90px;padding:5px;background:var(--panel);border:1px solid var(--border);border-radius:6px;color:var(--text)}
@media(max-width:768px){
.sidebar{position:fixed;left:0;top:0;bottom:0;transform:translateX(-100%)}
.sidebar.open{transform:translateX(0);box-shadow:0 0 40px rgba(0,0,0,.5)}
.mobile-toggle{display:block}
.msg .bubble{max-width:90%}
.msg .bubble img.a{max-width:170px}
}
</style></head>
<body data-theme="dark"><div class="app">
<aside class="sidebar" id="sidebar">
<div class="sidebar-header"><div class="logo">🤖</div><div class="brand">AWESOME AI</div></div>
<button class="new-chat" onclick="newChat()">＋ Новый чат</button>
<div class="chat-list scrollbar" id="chatList"></div>
<div class="sidebar-footer">
<div class="user-box">
<div class="avatar" id="userAvatar">?</div>
<div class="user-info"><div class="user-name" id="userName">Пользователь</div><div class="user-status" id="userStatus">...</div></div>
<div class="user-actions">
<button class="mini-btn" onclick="openSettings()" title="Настройки">⚙️</button>
<button class="mini-btn" onclick="openAdmin()" id="adminBtn" style="display:none">🛡️</button>
<button class="mini-btn" onclick="toggleTheme()">🌓</button>
<button class="mini-btn" onclick="logout()">⏻</button>
</div></div></div></aside>
<div class="main">
<div class="main-header"><button class="mobile-toggle" onclick="toggleSidebar()">☰</button><div class="title" id="currentChatTitle">Новый чат</div></div>
<div class="messages scrollbar" id="messages">
<div class="welcome" id="welcome">
<h1>Чем могу помочь?</h1><p>AWESOME AI — живая нейросеть, память диалога, 35+ функций</p>
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
<button class="icon-btn" onclick="document.getElementById('fileInput').click()">📎</button>
<button class="icon-btn" onclick="startVoice()">🎤</button>
<button class="icon-btn" onclick="ttsLast()">🔊</button>
<button class="icon-btn" onclick="translateLast()">🌐</button>
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
<h2 id="authTitle">Вход</h2><p id="authSub">Войди по Telegram-ID</p>
<div id="regFields" style="display:none"><input type="text" id="regName" placeholder="Имя (обязательно)"></div>
<input type="text" id="regId" placeholder="Telegram-ID (обязательно)" inputmode="numeric">
<input type="password" id="regPass" placeholder="Пароль (обязательно)">
<button class="btn" id="authBtn" onclick="submitAuth()">Войти</button>
<div class="hint">Premium/админ/владелец из бота @awesomeneiro_bot автоматически применится по твоему Telegram-ID</div>
</div></div>

<!-- Настройки -->
<div class="overlay" id="settingsOverlay" style="display:none">
<div class="modal"><h2>⚙️ Настройки</h2><p>Твой профиль</p>
<input type="text" id="setName" placeholder="Имя">
<input type="text" id="setAvatar" placeholder="URL аватарки">
<select id="setTheme"><option value="dark">🌙 Тёмная</option><option value="light">☀️ Светлая</option></select>
<button class="btn" onclick="saveSettings()">Сохранить</button>
<button class="btn ghost" onclick="document.getElementById('settingsOverlay').style.display='none'">Закрыть</button></div></div>

<!-- Админ -->
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
function switchTab(m){authMode=m;document.getElementById('tabLogin').className='tab'+(m==='login'?' active':'');document.getElementById('tabReg').className='tab'+(m==='reg'?' active':'');document.getElementById('regFields').style.display=m==='reg'?'block':'none';document.getElementById('authTitle').textContent=m==='reg'?'Регистрация':'Вход';document.getElementById('authBtn').textContent=m==='reg'?'Создать аккаунт':'Войти';}
async function submitAuth(){const id=document.getElementById('regId').value.trim(),pw=document.getElementById('regPass').value;if(!id||!pw){toast('Заполни Telegram-ID и пароль','error');return;}let body={telegram_id:id,password:pw};if(authMode==='reg'){const name=document.getElementById('regName').value.trim();if(!name){toast('Имя обязательно','error');return;}body.name=name;}const r=await api(authMode==='reg'?'/api/register':'/api/login','POST',body);if(r.ok){currentUserId=r.user_id;document.getElementById('authOverlay').style.display='none';toast('Добро пожаловать!','success');init();}else toast(r.error||'Ошибка','error');}
async function logout(){await api('/api/logout','POST');location.reload();}
function openSettings(){api('/api/profile').then(r=>{if(r.ok){document.getElementById('setName').value=r.name||'';document.getElementById('setAvatar').value=r.avatar||'';document.getElementById('setTheme').value=r.theme||'dark';}}).catch(()=>{});document.getElementById('settingsOverlay').style.display='flex';}
async function saveSettings(){const body={};body.name=document.getElementById('setName').value.trim()||undefined;body.avatar=document.getElementById('setAvatar').value.trim()||undefined;body.theme=document.getElementById('setTheme').value;const r=await api('/api/settings','POST',body);if(r.ok){setTheme(body.theme);toast('Сохранено','success');document.getElementById('settingsOverlay').style.display='none';init();}else toast('Ошибка','error');}
async function openAdmin(){const r=await api('/api/admin/stats');if(!r.ok){toast('Нет доступа','error');return;}let h='<div class="stat-card">';
h+='<div class="scard"><div class="n">'+r.total+'</div><div class="l">Пользователей</div></div>';
h+='<div class="scard"><div class="n">'+r.premium+'</div><div class="l">Premium</div></div>';
h+='<div class="scard"><div class="n">'+r.admins+'</div><div class="l">Админов</div></div>';
h+='<div class="scard"><div class="n">'+r.chats+'</div><div class="l">Чатов</div></div>';
h+='<div class="scard"><div class="n">'+r.messages+'</div><div class="l">Сообщений</div></div>';
h+='</div><h3 style="margin:10px 0">Пользователи</h3>';
(r.users||[]).forEach(u=>{h+='<div class="adm-user"><b>'+esc(u.name||u.id)+'</b> (#'+esc(u.id)+') Lv'+u.level+' <select onchange="adminSet(\''+esc(u.id)+'\',\'premium\',this.value)"><option value="0"'+(u.premium?'':' selected')+'>Free</option><option value="1"'+(u.premium?' selected':'')+'>Premium</option></select><button class="tool-btn" onclick="adminSet(\''+esc(u.id)+'\',\'is_admin\','+(u.is_admin?'0':'1')+')">'+(u.is_admin?'⬇️ Снять':'👑 Дать админа')+'</button></div>';});
h+='<h3 style="margin:10px 0">Рассылка</h3><textarea id="bcastText" style="width:100%;padding:10px;background:var(--bg2);border:1px solid var(--border);border-radius:10px;color:var(--text);resize:none" rows="2"></textarea><button class="tool-btn" style="margin-top:6px" onclick="adminBroadcast()">📢 Отправить всем</button>';
document.getElementById('adminContent').innerHTML=h;document.getElementById('adminOverlay').style.display='flex';}
async function adminSet(id,field,val){const r=await api('/api/admin/give','POST',{user_id:id,field:field,value:val});if(r.ok){toast('OK — синхронизировано с ботом','success');openAdmin();}else toast('Ошибка','error');}
async function adminBroadcast(){const t=document.getElementById('bcastText').value;if(!t)return;const r=await api('/api/admin/broadcast','POST',{text:t});if(r.ok){toast('Отправлено: '+r.sent+'/'+r.total,'success');openAdmin();}}
function esc(s){return String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function handleFile(inp){const f=inp.files[0];if(!f)return;attachedType=f.type.includes('pdf')?'pdf':'image';const reader=new FileReader();reader.onload=e=>{attachedImage=e.target.result;document.getElementById('attachImg').src=attachedType==='image'?attachedImage:'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg"><text y="30" font-size="20">📄</text></svg>';document.getElementById('attachName').textContent=f.name;document.getElementById('attachPreview').style.display='flex';};reader.readAsDataURL(f);inp.value='';}
function removeAttach(){attachedImage=null;document.getElementById('attachPreview').style.display='none';}
function formatAI(t){if(!t)return '';const lines=t.split('\n');let out='';for(const line of lines){const h=line.match(/^\*\*(.+?)\*\*$/);if(h){out+='<div class="h">'+esc(h[1])+'</div>';continue;}const parts=line.split(/(\*\*.*?\*\*)/g);let p='';for(const part of parts){if(part.startsWith('**')&&part.endsWith('**')&&part.length>4)p+='<b>'+esc(part.slice(2,-2))+'</b>';else p+=esc(part);}out+='<div style="margin:3px 0">'+p+'</div>';}return out;}
function addMsg(role,text,img,isGen){const box=document.getElementById('messages');if(document.getElementById('welcome'))document.getElementById('welcome').style.display='none';const m=document.createElement('div');m.className='msg '+role;let b='';if(img){b+=isGen?'<img class="g" src="'+img+'">':'<img class="a" src="'+img+'">';}let content='';if(role==='ai'&&text)content=formatAI(text);else if(text)content=esc(text);const acts=role==='ai'?'<div class="msg-actions"><button onclick="copyMsg(this)">📋</button><button onclick="regen()">🔄</button><button onclick="ttsMsg(this)">🔊</button></div>':'';m.innerHTML='<div class="avatar">'+(role==='ai'?'🤖':String(currentUserId||'?').slice(0,1).toUpperCase())+'</div><div class="bubble">'+b+content+'</div>'+acts;box.appendChild(m);box.scrollTop=box.scrollHeight;}
function copyMsg(btn){const b=btn.closest('.msg').querySelector('.bubble');const t=document.createElement('textarea');t.value=b.innerText;document.body.appendChild(t);t.select();document.execCommand('copy');t.remove();toast('Скопировано 📋','success');}
function regen(){if(sending)return;const box=document.getElementById('messages');const ms=box.querySelectorAll('.msg');if(ms.length<2)return;const last=ms[ms.length-1];if(last.classList.contains('ai')){last.remove();const us=box.querySelectorAll('.msg.user');if(us.length)sendMessage(us[us.length-1].querySelector('.bubble').innerText,true);}}
function ttsMsg(btn){const b=btn.closest('.msg').querySelector('.bubble').innerText;if('speechSynthesis'in window){speechSynthesis.speak(new SpeechSynthesisUtterance(b));toast('🔊 Озвучиваю...','success');}}
function ttsLast(){const box=document.getElementById('messages');const ms=box.querySelectorAll('.msg.ai');if(ms.length){const b=ms[ms.length-1].querySelector('.bubble').innerText;if('speechSynthesis'in window){speechSynthesis.speak(new SpeechSynthesisUtterance(b));toast('🔊','success');}}}
async function translateLast(){const box=document.getElementById('messages');const ms=box.querySelectorAll('.msg.ai');if(!ms.length)return;const r=await api('/api/translate','POST',{text:ms[ms.length-1].querySelector('.bubble').innerText,target:'ru'});if(r.ok)toast('🌐 '+r.translated.slice(0,250),'success');}
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
async function checkStatus(){const r=await api('/api/status');if(!r.ok){toast('Авторизуйся','error');return;}document.getElementById('userStatus').textContent=r.status_text+' · '+r.limit_text+' · Ур.'+r.level;if(r.is_owner)document.getElementById('adminBtn').style.display='';else document.getElementById('adminBtn').style.display='none';}
async function draw(){const input=document.getElementById('input');const p=prompt('🎨 Опиши что нарисовать:',input.value||'');if(!p||!p.trim())return;addMsg('user','🎨 '+p,null,false);setSending(true);addTyping();const r=await api('/api/draw','POST',{prompt:p});removeTyping();if(r.ok&&r.image){addMsg('ai','Готово!',r.image,true);}else addMsg('ai','⚠️ '+(r.error||'Не удалось'));setSending(false);checkStatus();}
function startVoice(){if(!('webkitSpeechRecognition'in window)){toast('Голос не поддерживается','error');return;}const rec=new webkitSpeechRecognition();rec.lang='ru-RU';rec.onresult=e=>{document.getElementById('input').value+=e.results[0][0].transcript;};rec.start();toast('Говори... 🎤','success');}
async function init(){const me=await api('/api/me');if(me.ok){currentUserId=me.user_id;document.getElementById('authOverlay').style.display='none';document.getElementById('userAvatar').textContent=String(me.name||me.user_id).slice(0,1).toUpperCase();document.getElementById('userName').textContent=me.name||me.user_id;document.getElementById('userStatus').textContent='...';if(me.theme)setTheme(me.theme);await loadChats();await checkStatus();}else{document.getElementById('authOverlay').style.display='flex';try{const t=localStorage.getItem('awesome_theme');if(t)setTheme(t);}catch(e){}}}
document.addEventListener('DOMContentLoaded',init);
</script></body></html>"""

@app.route('/api/owner_reset', methods=['POST'])
def api_owner_reset():
    """Сброс пароля ТОЛЬКО для владельца (без входа)"""
    d = request.json
    tg = str(d.get('telegram_id', '')).strip()
    new_pw = str(d.get('password', ''))
    # Только владелец может сбросить
    if str(tg) != str(OWNER_ID):
        return jsonify({'ok': False, 'error': 'Доступ запрещён'})
    if len(new_pw) < 3:
        return jsonify({'ok': False, 'error': 'Пароль мин. 3 символа'})
    conn = get_db(); cur = conn.cursor()
    # Обновляем пароль и создаём аккаунт, если его нет
    cur.execute("""INSERT INTO users (user_id, name, password, telegram_id, messages_today, last_reset, is_owner, theme, joined_at)
                   VALUES (%s, 'AWESOME', %s, %s, 0, %s, 1, 'dark', %s)
                   ON CONFLICT (user_id) DO UPDATE SET password = EXCLUDED.password""",
                (str(OWNER_ID), hash_pw(new_pw), str(OWNER_ID), gm().strftime('%Y-%m-%d'), now_iso()))
    cur.execute("INSERT INTO total_stats_web (user_id, total_messages) VALUES (%s, 0) ON CONFLICT DO NOTHING", (str(OWNER_ID),))
    conn.commit(); cur.close(); conn.close()
    return jsonify({'ok': True, 'error': None})


if __name__ == '__main__':
    print("="*60)
    print("🧠 AWESOME AI WEB — вход по Telegram-ID, связка бот+сайт+Supabase")
    print("="*60)
    print("✅ Вход: Telegram-ID + пароль")
    print("✅ Регистрация: имя + Telegram-ID + пароль")
    print("✅ Premium/админ/владелец синхронизируется из Supabase")
    print("✅ Админ-панель (владелец 6652898792 / @flidges)")
    print("✅ Много функций + оптимизация FPS")
    print("="*60)
    port=int(os.getenv("PORT",8080))
    app.run(host='0.0.0.0',port=port,debug=False,threaded=True)
