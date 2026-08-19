#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AWESOME AI WEB — DeepSeek-подобный: профиль, статус из TG-бота, темы, настройки"""

import os, re, io, time, json, base64, urllib.parse, hashlib
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
app.secret_key = os.getenv("SECRET_KEY", "awesome-ai-super-secret-key-2026")
app.permanent_session_lifetime = timedelta(days=30)

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY", "AQVNyfn82epL9dy8C_kftzeypq6eF9lFd6SZnFzV")
FOLDER_ID = os.getenv("FOLDER_ID", "b1g4aq87c7j61c6g3i5l")
GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY", "MDFhMDBkNmEtMmExNC03M2JkLWFlZmMtOTQ0OWVlOTc5M2U1OmE1ZWJhM2NlLTQwYjAtNDZlYi1iMmY2LTE3OTFmYzhhYTQ2MA==")
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://lprxbmshmuucymkgaqwk.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxwcnhibXNobXV1Y3lta2dhcXdrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY3NDk0MjgsImV4cCI6MjEwMjMyNTQyOH0.Ie9jSH5RMxeOq8aU-Dv6MXlojWMUTOLE723Hdg6heZU")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://u_cmsu43cr30:3sdZICdPDoR1DUrRRKsJ8yW1BqrH2PvZ@db-team-cmsu3ykqi0295mo01tsv8m15p:5432/db_awesome_ai_web")

OWNER_ID = 6652898792
FREE_LIMIT = 20
GIGACHAT_TIMEOUT = 30
YANDEXGPT_TIMEOUT = 15
SEARCH_TIMEOUT = 4
WEATHER_TIMEOUT = 3
MAX_HISTORY = 30

MOSCOW_TZ = timezone(timedelta(hours=3))
CACHE = {}; CACHE_TTL = 60

def get_moscow_time(): return datetime.now(MOSCOW_TZ)
def get_current_date(): return get_moscow_time().strftime('%d.%m.%Y')
def now_iso(): return get_moscow_time().strftime('%Y-%m-%d %H:%M:%S')

def format_date(s):
    if not s: return "неизвестно"
    try: return datetime.strptime(s,'%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')+" МСК"
    except Exception: return s

def get_cache(k):
    if k in CACHE:
        d,t=CACHE[k]
        if time.time()-t<CACHE_TTL: return d
        del CACHE[k]
    return None
def set_cache(k,d): CACHE[k]=(d,time.time())
def hash_pw(p): return hashlib.sha256(p.encode()).hexdigest()

def get_db(): return psycopg2.connect(DATABASE_URL)

def init_db():
    conn=get_db(); cur=conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY, name TEXT, password TEXT, telegram_id TEXT,
        premium INTEGER DEFAULT 0, messages_today INTEGER DEFAULT 0, last_reset TEXT,
        premium_expires TEXT, is_admin INTEGER DEFAULT 0, is_owner INTEGER DEFAULT 0,
        theme TEXT DEFAULT 'dark', joined_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS chats_web (
        id BIGSERIAL PRIMARY KEY, user_id TEXT, title TEXT DEFAULT 'Новый чат', created_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS messages_web (
        id BIGSERIAL PRIMARY KEY, chat_id BIGINT, role TEXT, content TEXT, image TEXT, created_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS total_stats_web (
        user_id TEXT PRIMARY KEY, total_messages INTEGER DEFAULT 0)""")
    try:
        cur.execute("ALTER TABLE messages_web ADD COLUMN IF NOT EXISTS image TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_id TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS name TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS theme TEXT DEFAULT 'dark'")
        conn.commit()
    except Exception: conn.rollback()
    conn.commit(); cur.close(); conn.close()
    print("✅ База данных готова")

init_db()
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ===== СТАТУС ИЗ ТГ-БОТА (по telegram_id) =====
def get_bot_user_status(telegram_id):
    if not telegram_id: return None
    try:
        r = supabase.table('users').select('premium,premium_expires,is_admin,is_owner').eq('user_id', int(telegram_id)).execute()
        if r.data:
            d = r.data[0]
            if d.get('premium')==1 and d.get('premium_expires'):
                try:
                    if get_moscow_time() > datetime.strptime(d['premium_expires'],'%Y-%m-%d %H:%M:%S').replace(tzinfo=MOSCOW_TZ):
                        return {'premium':0,'premium_expires':None,'is_admin':d.get('is_admin',0),'is_owner':d.get('is_owner',0)}
                except Exception: return d
            return d
        return None
    except Exception: return None

def get_effective_status(user_id, telegram_id=None):
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT premium,premium_expires,is_admin,is_owner,telegram_id FROM users WHERE user_id=%s",(user_id,))
    row=cur.fetchone(); cur.close(); conn.close()
    local=dict(row) if row else {'premium':0,'premium_expires':None,'is_admin':0,'is_owner':0,'telegram_id':None}
    tg = telegram_id or local.get('telegram_id')
    is_owner = 1 if (tg and str(tg).strip()==str(OWNER_ID)) else 0
    bot = get_bot_user_status(tg)
    if bot:
        if bot.get('is_owner')==1: is_owner=1
        if bot.get('premium')==1 and not local.get('premium'):
            local['premium']=1; local['premium_expires']=bot.get('premium_expires')
        if bot.get('is_admin')==1: local['is_admin']=1
    if local.get('premium')==1 and local.get('premium_expires'):
        try:
            if get_moscow_time()>datetime.strptime(local['premium_expires'],'%Y-%m-%d %H:%M:%S').replace(tzinfo=MOSCOW_TZ):
                local['premium']=0; local['premium_expires']=None
        except Exception: pass
    return {'premium':1 if (is_owner or local.get('premium')) else 0,
            'premium_expires':local.get('premium_expires'),
            'is_admin':1 if (is_owner or local.get('is_admin')) else 0,
            'is_owner':is_owner, 'telegram_id':tg}

def get_premium_status(uid,tg=None): return get_effective_status(uid,tg)['premium']
def get_premium_expires(uid,tg=None): return get_effective_status(uid,tg)['premium_expires']
def is_admin(uid,tg=None): return get_effective_status(uid,tg)['is_admin']

def register_user(user_id,name,password,telegram_id=None):
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id=%s",(user_id,))
    if cur.fetchone(): cur.close(); conn.close(); return False,"Такой профиль уже существует"
    cur.execute("INSERT INTO users (user_id,name,password,telegram_id,premium,messages_today,last_reset,is_admin,is_owner,theme,joined_at) VALUES (%s,%s,%s,%s,0,0,%s,0,0,'dark',%s)",
                (user_id,name,hash_pw(password),telegram_id,get_moscow_time().strftime('%Y-%m-%d'),now_iso()))
    cur.execute("INSERT INTO total_stats_web (user_id,total_messages) VALUES (%s,0) ON CONFLICT DO NOTHING",(user_id,))
    conn.commit(); cur.close(); conn.close(); return True,"OK"

def login_user(user_id,password):
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM users WHERE user_id=%s",(user_id,))
    row=cur.fetchone(); cur.close(); conn.close()
    if not row: return False,"Профиль не найден"
    if row['password']!=hash_pw(password): return False,"Неверный пароль"
    return True,"OK"

def get_user(user_id):
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM users WHERE user_id=%s",(user_id,))
    row=cur.fetchone(); cur.close(); conn.close()
    return dict(row) if row else None

def can_send_message(uid,tg=None):
    s=get_effective_status(uid,tg)
    if s['is_owner'] or s['is_admin'] or s['premium']: return True
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT messages_today FROM users WHERE user_id=%s",(uid,))
    row=cur.fetchone(); cur.close(); conn.close()
    return (row[0] if row else 0)<FREE_LIMIT

def increment_messages(uid,tg=None):
    s=get_effective_status(uid,tg)
    if s['is_owner'] or s['is_admin']: return
    conn=get_db(); cur=conn.cursor()
    cur.execute("UPDATE users SET messages_today=messages_today+1 WHERE user_id=%s",(uid,))
    cur.execute("INSERT INTO total_stats_web (user_id,total_messages) VALUES (%s,1) ON CONFLICT (user_id) DO UPDATE SET total_messages=total_stats_web.total_messages+1",(uid,))
    conn.commit(); cur.close(); conn.close()

def update_settings(user_id,name=None,theme=None,telegram_id=None):
    conn=get_db(); cur=conn.cursor()
    if name: cur.execute("UPDATE users SET name=%s WHERE user_id=%s",(name,user_id))
    if theme: cur.execute("UPDATE users SET theme=%s WHERE user_id=%s",(theme,user_id))
    if telegram_id is not None: cur.execute("UPDATE users SET telegram_id=%s WHERE user_id=%s",(telegram_id or None,user_id))
    conn.commit(); cur.close(); conn.close()

# ===== ЧАТЫ =====
def create_chat(user_id,title="Новый чат"):
    conn=get_db(); cur=conn.cursor()
    cur.execute("INSERT INTO chats_web (user_id,title,created_at) VALUES (%s,%s,%s) RETURNING id",(user_id,title,now_iso()))
    cid=cur.fetchone()[0]; conn.commit(); cur.close(); conn.close(); return cid
def get_chats(user_id):
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM chats_web WHERE user_id=%s ORDER BY created_at DESC",(user_id,))
    rows=cur.fetchall(); cur.close(); conn.close(); return [dict(r) for r in rows]
def add_message(chat_id,role,content,image=None):
    conn=get_db(); cur=conn.cursor()
    cur.execute("INSERT INTO messages_web (chat_id,role,content,image,created_at) VALUES (%s,%s,%s,%s,%s)",(int(chat_id),role,content,image,now_iso()))
    conn.commit(); cur.close(); conn.close()
def get_chat_messages(chat_id):
    conn=get_db(); cur=conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM messages_web WHERE chat_id=%s ORDER BY id",(int(chat_id),))
    rows=cur.fetchall(); cur.close(); conn.close(); return [dict(r) for r in rows]
def get_chat_history(chat_id):
    msgs=get_chat_messages(chat_id); return msgs[-MAX_HISTORY:] if msgs else []
def update_chat_title(chat_id,title):
    conn=get_db(); cur=conn.cursor()
    cur.execute("UPDATE chats_web SET title=%s WHERE id=%s",(title[:50],int(chat_id)))
    conn.commit(); cur.close(); conn.close()
def delete_chat(user_id,chat_id):
    conn=get_db(); cur=conn.cursor()
    cur.execute("DELETE FROM messages_web WHERE chat_id=%s",(int(chat_id),))
    cur.execute("DELETE FROM chats_web WHERE id=%s AND user_id=%s",(int(chat_id),user_id))
    conn.commit(); cur.close(); conn.close()

# ===== GIGACHAT =====
gigachat_token=None; gigachat_token_time=0
def get_gigachat_token():
    global gigachat_token,gigachat_token_time
    if gigachat_token and time.time()-gigachat_token_time<300: return gigachat_token
    for _ in range(3):
        try:
            r=requests.post("https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
                headers={"Content-Type":"application/x-www-form-urlencoded","Accept":"application/json","RqUID":"00000000-0000-0000-0000-000000000000","Authorization":f"Basic {GIGACHAT_AUTH_KEY}"},
                data={"scope":"GIGACHAT_API_PERS","grant_type":"client_credentials"},timeout=8,verify=False)
            if r.status_code==200:
                gigachat_token=r.json().get("access_token"); gigachat_token_time=time.time(); return gigachat_token
        except Exception: pass
        time.sleep(1)
    return None

def generate_with_gigachat(history,system_prompt,max_tokens=3000):
    try:
        token=get_gigachat_token()
        if not token: return None
        messages=[{"role":"system","content":system_prompt[:2000]}]
        messages+=[{"role":h["role"],"content":(h.get("content") or "")[:800]} for h in history if h.get("role") in ("user","assistant")]
        r=requests.post("https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
            headers={"Authorization":f"Bearer {token}","Content-Type":"application/json","Accept":"application/json"},
            json={"model":"GigaChat-Pro","messages":messages,"temperature":0.85,"max_tokens":max_tokens},
            timeout=GIGACHAT_TIMEOUT,verify=False)
        if r.status_code==200: return r.json()["choices"][0]["message"]["content"]
        return None
    except Exception: return None

def generate_full_answer(history,system_prompt):
    first=generate_with_gigachat(history,system_prompt,3000)
    if not first or len(first)<5: return None
    if len(first)>2500 and not first.rstrip().endswith(('.','!','?','»','"')):
        cont=generate_with_gigachat(history+[{"role":"assistant","content":first},{"role":"user","content":"Продолжи с того места, где остановился. Закончи мысль полностью."}],system_prompt,2000)
        if cont and len(cont)>5: return first+"\n"+cont
    return first

def generate_with_yandexgpt(user_text,system_prompt):
    try:
        r=requests.post("https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
            headers={"Authorization":f"Api-Key {YANDEX_API_KEY}","Content-Type":"application/json"},
            json={"modelUri":f"gpt://{FOLDER_ID}/yandexgpt/latest","completionOptions":{"temperature":0.3,"maxTokens":300},
                  "messages":[{"role":"system","text":system_prompt},{"role":"user","text":user_text}]},timeout=YANDEXGPT_TIMEOUT)
        if r.status_code==200: return r.json()["result"]["alternatives"][0]["message"]["text"]
        return None
    except Exception: return None

SUPER_SYSTEM_PROMPT="""ТЫ — AWESOME AI 2026, живая нейросеть на базе GigaChat, копия DeepSeek. НЕ шаблон.
📍 ТЫ В МОСКВЕ (UTC+3). Сегодня: {current_date}, время: {current_time}.
Ты помнишь весь диалог и отвечаешь с его учётом.

ПРАВИЛА ОТВЕТА:
1. ВСЕГДА полный развёрнутый ответ, раскрывай тему целиком (например распорядок дня: утро, день, вечер, ночь).
2. Разделяй ответ на РАЗДЕЛЫ с подзаголовками. Подзаголовки ОБЯЗАТЕЛЬНО оформляй так: **1. Утро** (две звёздочки с двух сторон).
3. После каждого подзаголовка — содержимое раздела, можно списками.
4. Важное внутри текста выделяй **жирным**.
5. Никаких "возможно/наверное/извини". Уверенно и конкретно.
6. Примеры, цифры, советы. Эмодзи (🔥🧠💡⚡🚀).
7. Ответ такой полный, чтобы не осталось вопросов.
💎 PREMIUM — максимальная глубина.
🎯 Ты живая нейросеть, докажи это!"""

# ===== ИЗОБРАЖЕНИЯ =====
def describe_image(image_b64):
    try:
        token=get_gigachat_token()
        if not token: return "📸 Изображение получено"
        r=requests.post("https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
            headers={"Authorization":f"Bearer {token}","Content-Type":"application/json","Accept":"application/json"},
            json={"model":"GigaChat-Pro",
                  "messages":[{"role":"system","content":"Ты — ИИ, видишь изображения. Подробно опиши объекты, действия, текст, цвета. На русском, развёрнуто."},
                              {"role":"user","content":[{"type":"text","text":"Что на изображении? Опиши подробно."},
                                {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{image_b64}"}}]}],
                  "temperature":0.5,"max_tokens":700},timeout=GIGACHAT_TIMEOUT,verify=False)
        if r.status_code==200: return r.json()["choices"][0]["message"]["content"]
        return "📸 Изображение получено"
    except Exception: return "📸 Изображение получено"

def generate_image(prompt):
    try:
        clean=prompt
        for w in ['нарисуй','сгенерируй','покажи','картинку','изображение']: clean=clean.replace(w,'').strip()
        if not clean: clean=prompt
        r=requests.get(f"https://image.pollinations.ai/prompt/{urllib.parse.quote(clean)}?width=1024&height=1024&nologo=true",headers={"User-Agent":"Mozilla/5.0"},timeout=25)
        if r.status_code==200 and len(r.content)>1000: return base64.b64encode(r.content).decode()
    except Exception: pass
    return None

# ===== ПРОЧЕЕ =====
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
        except Exception: pass
    return None

def get_weather(city):
    ck=f"w_{city}"; c=get_cache(ck)
    if c: return c
    try:
        r=requests.get(f"https://api.openweathermap.org/data/2.5/weather?q={urllib.parse.quote(city)}&appid=4c8f5c0b8a9f2c5d6e7f8g9h0i1j2k3l&units=metric&lang=ru",timeout=WEATHER_TIMEOUT)
        if r.status_code==200:
            d=r.json(); out=f"🌤 {city}: {round(d['main']['temp'])}°C, {d['weather'][0]['description']}\n💨 Ветер: {d['wind']['speed']} м/с"
            set_cache(ck,out); return out
    except Exception: pass
    return None

def get_currency():
    c=get_cache("cur")
    if c: return c
    try:
        r=requests.get("https://api.exchangerate-api.com/v4/latest/USD",timeout=SEARCH_TIMEOUT)
        rates=r.json().get('rates',{}); usd=rates.get('RUB','?'); eur=usd/rates.get('EUR',1) if rates.get('EUR') else '?'
        out=f"💵 USD: {round(usd,2)}₽\nEUR: {round(eur,2)}₽"; set_cache("cur",out); return out
    except Exception: return None

def get_crypto():
    c=get_cache("cry")
    if c: return c
    try:
        r=requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd",timeout=SEARCH_TIMEOUT)
        d=r.json(); out=f"🪙 BTC: ${d.get('bitcoin',{}).get('usd','?')}\nETH: ${d.get('ethereum',{}).get('usd','?')}"
        set_cache("cry",out); return out
    except Exception: return None

def search_google(q):
    try:
        r=requests.get(f"https://www.google.com/search?q={urllib.parse.quote(q)}&hl=ru",headers={"User-Agent":"Mozilla/5.0"},timeout=SEARCH_TIMEOUT)
        if r.status_code==200:
            soup=BeautifulSoup(r.text,'html.parser'); out=[]
            for res in soup.select('div.g')[:2]:
                t=res.select_one('h3'); s=res.select_one('div.VwiC3b')
                if t: out.append(f"🔹 {t.get_text(strip=True)}\n📝 {(s.get_text(strip=True) if s else '')[:100]}")
            return "\n".join(out) if out else None
    except Exception: pass
    return None

def search_wikipedia(q):
    try:
        r=requests.get(f"https://ru.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(q)}&format=json&utf8=1",timeout=SEARCH_TIMEOUT)
        data=r.json(); res=data.get('query',{}).get('search',[])
        if res:
            out=""
            for it in res[:2]: out+=f"📚 {it.get('title','')}\n{re.sub(r'<[^>]+>','',it.get('snippet',''))[:100]}\n\n"
            return out
    except Exception: pass
    return None

def search_all_internet(query):
    cache_key=f"s_{hash(query)}_{int(time.time()/60)}"
    c=get_cache(cache_key)
    if c: return c
    results=[]
    with ThreadPoolExecutor(max_workers=2) as ex:
        futs=[ex.submit(f,query) for f in [search_google,search_wikipedia]]
        for f in as_completed(futs):
            try:
                r=f.result(timeout=SEARCH_TIMEOUT+0.5)
                if r: results.append(r)
            except Exception: pass
    if results:
        final="\n\n".join(results[:2]); set_cache(cache_key,final); return final
    return None

def process_message(user_id,user_text,history,image_desc=None,telegram_id=None):
    tl=user_text.lower().strip()
    if image_desc:
        sp=SUPER_SYSTEM_PROMPT.format(current_date=get_current_date(),current_time=get_moscow_time().strftime('%H:%M'))
        sp+=f"\n\n📸 Пользователь прислал изображение. Описание: {image_desc}"
        sp+="\n\nОтветь развёрнуто, учитывая изображение и запрос."
        if get_premium_status(user_id,telegram_id): sp+="\n\n💎 PREMIUM режим."
        hist=history+[{"role":"user","content":user_text or "Опиши изображение подробно"}]
        a=generate_full_answer(hist,sp); return a if a else f"📸 {image_desc}"
    m=solve_math(user_text)
    if m is not None: return m
    if any(k in tl for k in ['праздник','какой сегодня праздник','сегодня праздник']):
        md=get_current_date()[3:5]+'.'+get_current_date()[0:2]
        h={'01.01':'Новый год','07.01':'Рождество','23.02':'День защитника Отечества','08.03':'Женский день','09.05':'День Победы','12.06':'День России','04.11':'День народного единства','14.02':'День влюбленных','01.04':'День смеха','12.04':'День космонавтики','01.09':'День знаний','31.10':'Хэллоуин','12.12':'День Конституции РФ'}
        return f"📅 *{get_current_date()} (МСК)*\n\n{h.get(md,'Праздников не найдено')}"
    if any(k in tl for k in ['погода','weather']):
        mm=re.search(r'(в|в городе)\s+([а-яА-Яa-zA-Z\- ]+)',tl)
        if mm:
            w=get_weather(mm.group(2).strip()); return w if w else "🌤 Не удалось получить погоду"
        return "🌤 Напиши: погода в [город]"
    if any(k in tl for k in ['курс','доллар','евро','валюта']):
        c=get_currency(); return c if c else "💵 Не удалось получить курс"
    if any(k in tl for k in ['биткоин','btc','эфириум','eth','крипта']):
        c=get_crypto(); return c if c else "🪙 Не удалось получить курс крипты"
    search=search_all_internet(user_text) if len(user_text)>2 else None
    sp=SUPER_SYSTEM_PROMPT.format(current_date=get_current_date(),current_time=get_moscow_time().strftime('%H:%M'))
    if get_premium_status(user_id,telegram_id): sp+="\n\n💎 Пользователь PREMIUM — режим максимальной проработки."
    if search: sp+=f"\n\n🔍 Данные из интернета:\n{search[:600]}"
    a=generate_full_answer(history+[{"role":"user","content":user_text}],sp)
    if a and len(a)>5:
        check=generate_with_yandexgpt(a[:400],"Ты — ИИ-проверщик фактов. Если всё верно, ответь ровно 'ПОДТВЕРЖДАЮ'. Если есть ошибки, кратко перечисли.")
        if check and "ПОДТВЕРЖДАЮ" not in check.upper():
            fixed=generate_full_answer(history+[{"role":"user","content":f"Исправь ошибки: {check}\nМой ответ:\n{a}"}],"Исправь ответ с учётом замечаний. Полный ответ.")
            if fixed and len(fixed)>5: return fixed
        return a
    if search: return f"🔍 *{user_text}*\n\n{search[:700]}"
    return "🤖 Обрабатываю... Повтори чуть позже."

# ===== API =====
@app.route('/')
def index(): return render_template_string(INDEX_HTML)

@app.route('/api/register', methods=['POST'])
def api_register():
    d=request.json
    uid=str(d.get('user_id','')).strip(); name=str(d.get('name','')).strip(); pw=str(d.get('password','')); tg=d.get('telegram_id') or None
    if not uid or not pw or len(pw)<3: return jsonify({'ok':False,'error':'Заполни ID и пароль (мин. 3 символа)'})
    if not name: name=uid
    ok,msg=register_user(uid,name,pw,tg)
    if not ok: return jsonify({'ok':False,'error':msg})
    session.permanent=True; session['user_id']=uid; session['name']=name
    return jsonify({'ok':True,'user_id':uid,'name':name})

@app.route('/api/login', methods=['POST'])
def api_login():
    d=request.json
    uid=str(d.get('user_id','')).strip(); pw=str(d.get('password',''))
    ok,msg=login_user(uid,pw)
    if not ok: return jsonify({'ok':False,'error':msg})
    u=get_user(uid); session.permanent=True; session['user_id']=uid; session['name']=u.get('name') if u else uid
    return jsonify({'ok':True,'user_id':uid,'name':session['name']})

@app.route('/api/logout', methods=['POST'])
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
    s=get_effective_status(uid,tg)
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT messages_today FROM users WHERE user_id=%s",(uid,))
    row=cur.fetchone(); cur.close(); conn.close()
    if s['is_owner']: st="👑 Владелец"; lim="♾️ Безлимит"
    elif s['is_admin']: st="👑 Админ"; lim="♾️ Безлимит"
    elif s['premium']: st="💎 Premium"; lim="♾️ Безлимит"
    else: st="🔓 Бесплатный"; lim=f"{max(0,FREE_LIMIT-(row[0] if row else 0))}/{FREE_LIMIT}"
    return jsonify({'ok':True,'premium':bool(s['premium']),'is_admin':bool(s['is_admin']),'is_owner':bool(s['is_owner']),
                    'premium_expires':format_date(s['premium_expires']) if s['premium'] else None,
                    'status_text':st,'limit_text':lim,'messages_today':row[0] if row else 0,'free_limit':FREE_LIMIT})

@app.route('/api/chat', methods=['POST'])
def api_chat():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False,'error':'Авторизуйтесь'})
    u=get_user(uid); tg=u.get('telegram_id') if u else None
    if not can_send_message(uid,tg): return jsonify({'ok':False,'error':'Лимит исчерпан! Купите Premium.'})
    d=request.json; msg=d.get('message','').strip(); chat_id=d.get('chat_id'); image_b64=d.get('image')
    if not msg and not image_b64: return jsonify({'ok':False,'error':'Пустое сообщение'})
    if not chat_id: chat_id=create_chat(uid)
    history=get_chat_history(chat_id)
    image_desc=None
    if image_b64:
        try:
            raw=base64.b64decode(image_b64.split(',')[-1]); img=Image.open(io.BytesIO(raw)).convert('RGB'); img.thumbnail((800,800))
            buf=io.BytesIO(); img.save(buf,'JPEG',quality=85); image_desc=describe_image(base64.b64encode(buf.getvalue()).decode())
        except Exception: image_desc="📸 Изображение прикреплено"
    add_message(chat_id,'user',msg,image_b64)
    response=process_message(uid,msg,history,image_desc,tg)
    increment_messages(uid,tg)
    add_message(chat_id,'assistant',response)
    try:
        msgs=get_chat_messages(chat_id)
        fu=next((m for m in msgs if m['role']=='user' and m['content']),None)
        if fu: update_chat_title(chat_id,fu['content'][:40])
    except Exception: pass
    return jsonify({'ok':True,'response':response,'chat_id':chat_id})

@app.route('/api/chats')
def api_chats():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False})
    chats=get_chats(uid)
    for c in chats: c['messages']=get_chat_messages(c['id'])
    return jsonify({'ok':True,'chats':chats})

@app.route('/api/chat/new', methods=['POST'])
def api_chat_new():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False,'error':'Авторизуйтесь'})
    return jsonify({'ok':True,'chat_id':create_chat(uid)})

@app.route('/api/chat/delete', methods=['POST'])
def api_chat_delete():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False})
    delete_chat(uid,request.json.get('chat_id')); return jsonify({'ok':True})

@app.route('/api/draw', methods=['POST'])
def api_draw():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False,'error':'Авторизуйтесь'})
    u=get_user(uid); tg=u.get('telegram_id') if u else None
    if not can_send_message(uid,tg): return jsonify({'ok':False,'error':'Лимит! Купите Premium.'})
    img=generate_image(request.json.get('prompt',''))
    if img:
        increment_messages(uid,tg); return jsonify({'ok':True,'image':img})
    return jsonify({'ok':False,'error':'Не удалось сгенерировать'})

@app.route('/api/profile')
def api_profile():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False})
    u=get_user(uid); tg=u.get('telegram_id') if u else None
    s=get_effective_status(uid,tg)
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT messages_today FROM users WHERE user_id=%s",(uid,))
    row=cur.fetchone()
    cur.execute("SELECT total_messages FROM total_stats_web WHERE user_id=%s",(uid,))
    tot=cur.fetchone(); cur.close(); conn.close()
    return jsonify({'ok':True,'user_id':uid,'name':u.get('name') if u else session.get('name'),'telegram_id':tg,
                    'theme':u.get('theme','dark') if u else 'dark','premium':bool(s['premium']),
                    'is_admin':bool(s['is_admin']),'is_owner':bool(s['is_owner']),
                    'premium_expires':format_date(s['premium_expires']) if s['premium'] else None,
                    'messages_today':row[0] if row else 0,'total_messages':tot[0] if tot else 0,'joined_at':u.get('joined_at') if u else None})

@app.route('/api/settings', methods=['POST'])
def api_settings():
    uid=session.get('user_id')
    if not uid: return jsonify({'ok':False,'error':'Авторизуйтесь'})
    d=request.json
    update_settings(uid, name=d.get('name'), theme=d.get('theme'), telegram_id=d.get('telegram_id'))
    if d.get('name'): session['name']=d['name']
    return jsonify({'ok':True})

# ===== HTML =====
INDEX_HTML = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>AWESOME AI</title>
<style>
:root{
--bg:#16151c;--bg2:#201e28;--panel:#262430;--border:#373441;
--accent:#ff8a3d;--accent2:#ff6b1a;--text:#eceaf5;--muted:#9a96ab;--danger:#ff5b6e;--success:#3ddc84;
}
[data-theme="light"]{
--bg:#f5f4f8;--bg2:#ffffff;--panel:#ffffff;--border:#e3e0ec;
--accent:#f07800;--accent2:#ff6b1a;--text:#22202e;--muted:#6b6880;--danger:#e0404f;--success:#1fa860;
}
*{margin:0;padding:0;box-sizing:border-box;font-family:'Segoe UI',system-ui,sans-serif}
html,body{height:100%}
body{background:var(--bg);color:var(--text);min-height:100vh;overflow-x:hidden;transition:background .4s,color .4s;-webkit-font-smoothing:antialiased}
.bg{position:fixed;inset:0;z-index:-2;background:radial-gradient(circle at 20% 20%,rgba(255,138,61,.07),transparent 45%),var(--bg)}
.app{display:flex;height:100vh}
.sidebar{width:270px;background:var(--panel);border-right:1px solid var(--border);display:flex;flex-direction:column;transition:transform .25s,background .4s;z-index:50}
.sidebar-header{padding:16px;display:flex;align-items:center;gap:10px;border-bottom:1px solid var(--border)}
.logo{width:40px;height:40px;border-radius:12px;background:linear-gradient(135deg,var(--accent),var(--accent2));display:flex;align-items:center;justify-content:center;font-size:20px;flex-shrink:0}
.brand{font-weight:700;font-size:16px;background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.new-chat{margin:14px;padding:12px;background:linear-gradient(135deg,var(--accent),var(--accent2));border:none;border-radius:12px;color:#fff;font-weight:600;cursor:pointer;font-size:14px;transition:transform .15s,opacity .15s}
.new-chat:active{transform:scale(.97)}
.chat-list{flex:1;overflow-y:auto;padding:0 10px}
.chat-item{padding:11px 12px;border-radius:10px;cursor:pointer;margin-bottom:4px;font-size:13px;display:flex;align-items:center;gap:8px}
.chat-item:hover,.chat-item.active{background:var(--bg2)}
.chat-item .t{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.chat-item .del{opacity:0;background:none;border:none;color:var(--danger);cursor:pointer;font-size:14px;transition:opacity .15s;padding:4px}
.chat-item:hover .del{opacity:1}
.sidebar-footer{padding:12px;border-top:1px solid var(--border)}
.user-box{display:flex;align-items:center;gap:10px;padding:10px;background:var(--bg2);border-radius:12px}
.avatar{width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,var(--accent),var(--accent2));display:flex;align-items:center;justify-content:center;font-weight:700;font-size:15px;flex-shrink:0;color:#fff}
.user-info{flex:1;min-width:0}
.user-name{font-weight:600;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.user-status{font-size:11px;color:var(--accent)}
.user-actions{display:flex;gap:4px}
.mini-btn{background:none;border:none;color:var(--muted);cursor:pointer;font-size:16px;padding:4px}
.mini-btn:hover{color:var(--accent)}
.main{flex:1;display:flex;flex-direction:column;min-width:0}
.main-header{height:56px;display:flex;align-items:center;justify-content:center;border-bottom:1px solid var(--border);position:relative}
.mobile-toggle{display:none;position:absolute;left:14px;background:none;border:none;color:var(--text);font-size:22px;cursor:pointer}
.messages{flex:1;overflow-y:auto;padding:20px;scroll-behavior:smooth;overscroll-behavior:contain}
.welcome{max-width:720px;margin:0 auto;text-align:center;padding-top:7vh;animation:fadeUp .5s ease}
@keyframes fadeUp{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
.welcome h1{font-size:clamp(26px,5vw,42px);margin-bottom:10px;background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.welcome p{color:var(--muted);margin-bottom:28px;font-size:16px}
.suggestion-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;max-width:600px;margin:0 auto}
.sugg{background:var(--panel);border:1px solid var(--border);border-radius:14px;padding:16px;cursor:pointer;transition:transform .15s,border-color .15s;font-size:13px}
.sugg:active{transform:scale(.98)}
.sugg:hover{border-color:var(--accent)}
.sugg .ic{font-size:22px;margin-bottom:8px;display:block}
.msg{max-width:760px;margin:0 auto 18px;display:flex;gap:12px;animation:fadeUp .3s ease;position:relative}
.msg.user{flex-direction:row-reverse}
.msg .bubble{padding:13px 16px;border-radius:16px;font-size:15px;line-height:1.6;max-width:80%;white-space:pre-wrap;word-break:break-word}
.msg.user .bubble{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;border-top-right-radius:4px}
.msg.ai .bubble{background:var(--panel);border:1px solid var(--border);border-top-left-radius:4px}
/* Оранжевые заголовки ответов ИИ (**текст**) */
.msg .bubble b{color:var(--accent)}
.msg .bubble .ai-head{display:block;font-weight:700;color:var(--accent);font-size:16px;margin:12px 0 6px;padding-top:10px;border-top:1px solid var(--border)}
.msg .bubble .ai-head:first-child{border-top:none;margin-top:0;padding-top:0}
.msg .bubble img.attach{max-width:240px;border-radius:10px;margin-top:8px;display:block}
.msg .bubble img.gen{max-width:100%;border-radius:12px;margin-top:8px;display:block}
.msg-actions{position:absolute;top:8px;right:8px;display:flex;gap:4px;opacity:0;transition:opacity .2s}
.msg:hover .msg-actions{opacity:1}
.msg-actions button{background:var(--bg2);border:1px solid var(--border);color:var(--muted);border-radius:6px;cursor:pointer;font-size:12px;padding:4px 7px}
.msg-actions button:hover{color:var(--accent)}
.typing-dots{display:inline-flex;gap:4px;padding:6px 2px}
.typing-dots span{width:8px;height:8px;border-radius:50%;background:var(--accent);animation:bounce 1.2s infinite}
.typing-dots span:nth-child(2){animation-delay:.2s}.typing-dots span:nth-child(3){animation-delay:.4s}
@keyframes bounce{0%,100%{transform:translateY(0);opacity:.4}50%{transform:translateY(-6px);opacity:1}}
.input-area{padding:14px;border-top:1px solid var(--border);background:var(--bg)}
.attach-preview{max-width:760px;margin:0 auto 8px;display:none;gap:8px;align-items:center;background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:8px}
.attach-preview img{width:52px;height:52px;object-fit:cover;border-radius:8px}
.attach-preview .aname{flex:1;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.attach-preview .rm{background:none;border:none;color:var(--danger);cursor:pointer;font-size:18px}
.input-wrap{max-width:760px;margin:0 auto;display:flex;align-items:flex-end;gap:8px;background:var(--bg2);border:1px solid var(--border);border-radius:18px;padding:8px}
.input-wrap:focus-within{border-color:var(--accent);box-shadow:0 0 0 3px rgba(255,138,61,.15)}
textarea{flex:1;background:none;border:none;outline:none;color:var(--text);font-size:15px;resize:none;max-height:120px;padding:8px 4px}
.icon-btn{width:38px;height:38px;border-radius:12px;background:none;border:none;color:var(--muted);font-size:17px;cursor:pointer;flex-shrink:0}
.icon-btn:hover{color:var(--accent)}
.send-btn{width:42px;height:42px;border-radius:12px;background:linear-gradient(135deg,var(--accent),var(--accent2));border:none;color:#fff;font-size:18px;cursor:pointer;flex-shrink:0}
.send-btn:disabled{opacity:.4;cursor:not-allowed}
.toolbar{max-width:760px;margin:10px auto 0;display:flex;gap:8px;flex-wrap:wrap}
.tool-btn{background:var(--panel);border:1px solid var(--border);color:var(--muted);border-radius:8px;padding:6px 12px;font-size:12px;cursor:pointer}
.tool-btn:hover{color:var(--text);border-color:var(--accent)}
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.6);backdrop-filter:blur(4px);z-index:100;display:flex;align-items:center;justify-content:center;padding:16px}
.modal{background:var(--panel);border:1px solid var(--border);border-radius:20px;padding:28px;width:100%;max-width:400px;text-align:center;max-height:90vh;overflow-y:auto}
.modal .tabs{display:flex;gap:8px;margin-bottom:16px}
.modal .tab{flex:1;padding:10px;border-radius:10px;background:var(--bg2);border:1px solid var(--border);color:var(--muted);cursor:pointer;font-weight:600;font-size:14px}
.modal .tab.active{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;border:none}
.modal h2{margin-bottom:8px}.modal p{color:var(--muted);font-size:14px;margin-bottom:16px}
.modal input,.modal select{width:100%;padding:12px;background:var(--bg2);border:1px solid var(--border);border-radius:10px;color:var(--text);font-size:15px;margin-bottom:10px;outline:none;text-align:center}
.modal input:focus,.modal select:focus{border-color:var(--accent)}
.modal .btn{width:100%;padding:13px;border:none;border-radius:10px;background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;font-weight:600;font-size:15px;cursor:pointer}
.hint{font-size:12px;color:var(--muted);margin-top:10px;line-height:1.5}
.toast{position:fixed;top:20px;right:20px;background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:14px 20px;z-index:300;box-shadow:0 8px 30px rgba(0,0,0,.4);max-width:320px;animation:fadeUp .3s ease}
.toast.error{border-color:var(--danger)}.toast.success{border-color:var(--success)}
.scrollbar::-webkit-scrollbar{width:6px}.scrollbar::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
@media(max-width:768px){
.sidebar{position:fixed;left:0;top:0;bottom:0;transform:translateX(-100%)}
.sidebar.open{transform:translateX(0);box-shadow:0 0 40px rgba(0,0,0,.5)}
.mobile-toggle{display:block}
.msg .bubble{max-width:88%}
.msg .bubble img.attach{max-width:180px}
}
</style>
</head>
<body data-theme="dark">
<div class="bg"></div>
<div class="app">
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
<button class="mini-btn" onclick="toggleTheme()" title="Тема">🌓</button>
<button class="mini-btn" onclick="logout()" title="Выйти">⏻</button>
</div>
</div>
</div>
</aside>
<div class="main">
<div class="main-header"><button class="mobile-toggle" onclick="toggleSidebar()">☰</button><div class="title" id="currentChatTitle">Новый чат</div></div>
<div class="messages scrollbar" id="messages">
<div class="welcome" id="welcome">
<h1>Чем могу помочь?</h1>
<p>AWESOME AI — живая нейросеть с памятью диалога</p>
<div class="suggestion-grid">
<div class="sugg" onclick="sendSuggestion('Расскажи подробно про распорядок дня')"><span class="ic">⏰</span>Распорядок дня</div>
<div class="sugg" onclick="sendSuggestion('Напиши код на Python для парсинга сайта')"><span class="ic">💻</span>Напиши код</div>
<div class="sugg" onclick="sendSuggestion('погода в Москве')"><span class="ic">🌤</span>Погода</div>
<div class="sugg" onclick="sendSuggestion('нарисуй кота в космосе')"><span class="ic">🎨</span>Нарисуй</div>
<div class="sugg" onclick="sendSuggestion('курс доллара')"><span class="ic">💵</span>Курс валют</div>
<div class="sugg" onclick="sendSuggestion('сколько будет 256 * 144 + 18?')"><span class="ic">🧮</span>Математика</div>
</div>
</div>
</div>
<div class="input-area">
<div class="attach-preview" id="attachPreview">
<img id="attachImg" src=""><span class="aname" id="attachName"></span>
<button class="rm" onclick="removeAttach()">✕</button>
</div>
<div class="input-wrap">
<input type="file" id="fileInput" accept="image/*" style="display:none" onchange="handleFile(this)">
<button class="icon-btn" onclick="document.getElementById('fileInput').click()" title="Прикрепить файл">📎</button>
<button class="icon-btn" onclick="startVoice()" title="Голосовой ввод">🎤</button>
<textarea id="input" rows="1" placeholder="Спроси что-нибудь..." onkeydown="onKey(event)"></textarea>
<button class="send-btn" id="sendBtn" onclick="sendMessage()">➤</button>
</div>
<div class="toolbar">
<button class="tool-btn" onclick="draw()">🎨 Сгенерировать</button>
<button class="tool-btn" onclick="checkStatus()">💎 Статус</button>
<button class="tool-btn" onclick="clearHistory()">🧹 Очистить</button>
</div>
</div>
</div>
</div>

<!-- Вход / Регистрация -->
<div class="overlay" id="authOverlay">
<div class="modal">
<div class="logo" style="width:56px;height:56px;font-size:28px;margin:0 auto 14px;display:flex;align-items:center;justify-content:center;border-radius:14px;background:linear-gradient(135deg,var(--accent),var(--accent2))">🤖</div>
<div class="tabs"><button class="tab active" id="tabLogin" onclick="switchTab('login')">Вход</button><button class="tab" id="tabReg" onclick="switchTab('reg')">Регистрация</button></div>
<h2 id="authTitle">Вход</h2>
<p id="authSub">Войди в свой аккаунт</p>
<div id="regFields" style="display:none"><input type="text" id="regName" placeholder="Имя"></div>
<input type="text" id="regId" placeholder="Профиль-ID (например: mama123)">
<input type="password" id="regPass" placeholder="Пароль">
<input type="text" id="regTg" placeholder="Telegram-ID (для Premium из бота)" style="display:none">
<button class="btn" id="authBtn" onclick="submitAuth()">Войти</button>
<div class="hint">Совет: укажи Telegram-ID — тогда Premium/админ/владелец из бота @awesomeneiro_bot автоматически применится на сайте.<br>Тебя запомнят — при следующем визите вход автоматический.</div>
</div>
</div>

<!-- Настройки -->
<div class="overlay" id="settingsOverlay" style="display:none">
<div class="modal">
<h2>⚙️ Настройки</h2>
<p>Настрой свой профиль</p>
<input type="text" id="setName" placeholder="Имя">
<input type="text" id="setTg" placeholder="Telegram-ID (для статуса из бота)">
<label style="display:block;text-align:left;color:var(--muted);font-size:13px;margin-bottom:6px">Тема</label>
<select id="setTheme"><option value="dark">🌙 Тёмная</option><option value="light">☀️ Светлая</option></select>
<button class="btn" onclick="saveSettings()">Сохранить</button>
<button class="btn" style="margin-top:8px;background:var(--bg2);color:var(--muted);border:1px solid var(--border)" onclick="document.getElementById('settingsOverlay').style.display='none'">Закрыть</button>
</div>
</div>

<script>
let currentUserId=null,currentChatId=null,sending=false,attachedImage=null,authMode='login',currentTheme='dark';
function toast(t,ty){const el=document.createElement('div');el.className='toast '+(ty||'');el.textContent=t;document.body.appendChild(el);setTimeout(()=>el.remove(),3000);}
function toggleSidebar(){document.getElementById('sidebar').classList.toggle('open');}
async function api(url,method,body){try{const o={method:method||'GET',headers:{'Content-Type':'application/json'}};if(body)o.body=JSON.stringify(body);const r=await fetch(url,o);return await r.json();}catch(e){return {ok:false,error:'Соединение'};}}
function setTheme(t){currentTheme=t;document.body.setAttribute('data-theme',t);try{localStorage.setItem('awesome_theme',t);}catch(e){}}
function toggleTheme(){setTheme(currentTheme==='dark'?'light':'dark');api('/api/settings','POST',{theme:currentTheme});}
function switchTab(m){authMode=m;document.getElementById('tabLogin').className='tab'+(m==='login'?' active':'');document.getElementById('tabReg').className='tab'+(m==='reg'?' active':'');document.getElementById('regFields').style.display=m==='reg'?'block':'none';document.getElementById('regTg').style.display=m==='reg'?'block':'none';document.getElementById('authTitle').textContent=m==='reg'?'Регистрация':'Вход';document.getElementById('authBtn').textContent=m==='reg'?'Создать аккаунт':'Войти';}
async function submitAuth(){
  const id=document.getElementById('regId').value.trim(),pw=document.getElementById('regPass').value;
  if(!id||!pw){toast('Заполни ID и пароль','error');return;}
  let body={user_id:id,password:pw};
  if(authMode==='reg'){body.name=document.getElementById('regName').value.trim()||id;body.telegram_id=document.getElementById('regTg').value.trim()||null;}
  const r=await api(authMode==='reg'?'/api/register':'/api/login','POST',body);
  if(r.ok){currentUserId=r.user_id;document.getElementById('authOverlay').style.display='none';toast('Добро пожаловать!','success');init();}
  else{toast(r.error||'Ошибка','error');}
}
async function logout(){await api('/api/logout','POST');location.reload();}
function openSettings(){const p=document.getElementById('profile');(async()=>{const r=await api('/api/profile');if(r.ok){document.getElementById('setName').value=r.name||'';document.getElementById('setTg').value=r.telegram_id||'';document.getElementById('setTheme').value=r.theme||'dark';}})().catch(()=>{});document.getElementById('settingsOverlay').style.display='flex';}
async function saveSettings(){const name=document.getElementById('setName').value.trim(),tg=document.getElementById('setTg').value.trim(),theme=document.getElementById('setTheme').value;const r=await api('/api/settings','POST',{name:name||undefined,telegram_id:tg||null,theme:theme});if(r.ok){setTheme(theme);toast('Настройки сохранены','success');document.getElementById('settingsOverlay').style.display='none';init();}else toast('Ошибка','error');}
function handleFile(inp){const f=inp.files[0];if(!f)return;const reader=new FileReader();reader.onload=e=>{attachedImage=e.target.result;document.getElementById('attachImg').src=attachedImage;document.getElementById('attachName').textContent=f.name;document.getElementById('attachPreview').style.display='flex';};reader.readAsDataURL(f);inp.value='';}
function removeAttach(){attachedImage=null;document.getElementById('attachPreview').style.display='none';}
function startVoice(){if(!('webkitSpeechRecognition'in window)&&!('SpeechRecognition'in window)){toast('Голосовой ввод не поддерживается','error');return;}const SR=window.SpeechRecognition||window.webkitSpeechRecognition;const rec=new SR();rec.lang='ru-RU';rec.onresult=e=>{document.getElementById('input').value+=e.results[0][0].transcript;};rec.start();toast('Говори... 🎤');}
function formatAI(text){
  // Обрабатываем **Заголовок** в оранжевые заголовки
  const lines=text.split('\n');let out='';let open=false;
  for(let line of lines){
    let m=line.match(/^\*\*(.+?)\*\*$/);
    if(m){out+='<div class="ai-head">'+esc(m[1])+'</div>';continue;}
    // инлайн **жирный** внутри строки
    let parts=line.split(/(\*\*.*?\*\*)/g);
    let processed='';
    for(let p of parts){
      if(p.startsWith('**')&&p.endsWith('**')&&p.length>4){processed+='<b>'+esc(p.slice(2,-2))+'</b>';}
      else{processed+=esc(p);}
    }
    out+='<div style="margin:3px 0">'+processed+'</div>';
  }
  return out;
}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function addMsg(role,text,img,isGen){const box=document.getElementById('messages');if(document.getElementById('welcome'))document.getElementById('welcome').style.display='none';const m=document.createElement('div');m.className='msg '+role;let b='';if(img){b+=isGen?'<img class="gen" src="'+img+'">':'<img class="attach" src="'+img+'">';}
let content='';if(role==='ai'&&text){content=formatAI(text);}else if(text){content=esc(text);}
const actions=role==='ai'?'<div class="msg-actions"><button onclick="copyMsg(this)">📋</button><button onclick="regen()">🔄</button></div>':'';
m.innerHTML='<div class="avatar">'+(role==='ai'?'🤖':String(currentUserId||'?').slice(0,1).toUpperCase())+'</div><div class="bubble">'+b+content+'</div>'+actions;box.appendChild(m);box.scrollTop=box.scrollHeight;return m;}
function copyMsg(btn){const bubble=btn.closest('.msg').querySelector('.bubble');const t=document.createElement('textarea');t.value=bubble.innerText;document.body.appendChild(t);t.select();document.execCommand('copy');t.remove();toast('Скопировано 📋','success');}
function regen(){if(sending)return;const box=document.getElementById('messages');const msgs=box.querySelectorAll('.msg');if(msgs.length<2)return;const lastAI=msgs[msgs.length-1];if(lastAI&&lastAI.classList.contains('ai')){lastAI.remove();const lastUser=box.querySelectorAll('.msg.user');if(lastUser.length){const u=lastUser[lastUser.length-1];const txt=u.querySelector('.bubble').innerText;sendMessage(txt,true);}}}
function addTyping(){const box=document.getElementById('messages');const m=document.createElement('div');m.className='msg ai';m.id='typing';m.innerHTML='<div class="avatar">🤖</div><div class="bubble"><div class="typing-dots"><span></span><span></span><span></span></div></div>';box.appendChild(m);box.scrollTop=box.scrollHeight;}
function removeTyping(){const t=document.getElementById('typing');if(t)t.remove();}
async function sendMessage(text,regenMode){if(sending&&!regenMode)return;const input=document.getElementById('input');const msg=(text!==undefined&&text!==null)?text:input.value.trim();if(!msg&&!attachedImage)return;if(!regenMode){input.value='';addMsg('user',msg,attachedImage,false);}setSending(true);addTyping();try{const r=await api('/api/chat','POST',{message:msg,chat_id:currentChatId,image:attachedImage});removeTyping();if(r.ok){currentChatId=r.chat_id;addMsg('ai',r.response,null,false);document.getElementById('currentChatTitle').textContent='Чат';loadChats();}else{addMsg('ai','⚠️ '+r.error);toast(r.error,'error');}}catch(e){removeTyping();addMsg('ai','⚠️ Ошибка соединения');}attachedImage=null;document.getElementById('attachPreview').style.display='none';setSending(false);checkStatus();}
function setSending(v){sending=v;document.getElementById('sendBtn').disabled=v;document.getElementById('input').disabled=v;}
function onKey(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMessage();}}
function sendSuggestion(t){sendMessage(t);}
async function newChat(){const r=await api('/api/chat/new','POST');if(r.ok){currentChatId=r.chat_id;document.getElementById('messages').innerHTML='';document.getElementById('welcome').style.display='';document.getElementById('currentChatTitle').textContent='Новый чат';document.getElementById('sidebar').classList.remove('open');}}
async function loadChats(){const r=await api('/api/chats');if(!r.ok)return;const list=document.getElementById('chatList');list.innerHTML='';r.chats.forEach(c=>{const it=document.createElement('div');it.className='chat-item'+(c.id===currentChatId?' active':'');it.innerHTML='<span>💬</span><span class="t">'+esc(c.title||'Новый чат')+'</span><button class="del" onclick="delChat('+c.id+',event)">✕</button>';it.onclick=()=>openChat(c);list.appendChild(it);});}
function openChat(c){currentChatId=c.id;const box=document.getElementById('messages');box.innerHTML='';document.getElementById('currentChatTitle').textContent=c.title||'Чат';(c.messages||[]).forEach(m=>addMsg(m.role,m.content,m.image,false));document.getElementById('sidebar').classList.remove('open');}
async function delChat(id,e){e.stopPropagation();if(!confirm('Удалить чат?'))return;await api('/api/chat/delete','POST',{chat_id:id});if(id===currentChatId){currentChatId=null;boxReset();}loadChats();}
function boxReset(){document.getElementById('messages').innerHTML='';document.getElementById('welcome').style.display='';document.getElementById('currentChatTitle').textContent='Новый чат';}
function clearHistory(){document.getElementById('messages').innerHTML='';document.getElementById('welcome').style.display='';toast('История очищена','success');}
async function checkStatus(){const r=await api('/api/status');if(!r.ok){toast('Авторизуйся','error');return;}const st=document.getElementById('userStatus');st.textContent=r.status_text+' · '+r.limit_text;}
async function draw(){const input=document.getElementById('input');const p=prompt('🎨 Опиши что нарисовать:',input.value||'');if(!p||!p.trim())return;addMsg('user','🎨 '+p,null,false);setSending(true);addTyping();const r=await api('/api/draw','POST',{prompt:p});removeTyping();if(r.ok&&r.image){addMsg('ai','Готово!',r.image,true);}else addMsg('ai','⚠️ '+(r.error||'Не удалось'));setSending(false);checkStatus();}
async function init(){const me=await api('/api/me');if(me.ok){currentUserId=me.user_id;document.getElementById('authOverlay').style.display='none';document.getElementById('userAvatar').textContent=String(me.name||me.user_id).slice(0,1).toUpperCase();document.getElementById('userName').textContent=me.name||me.user_id;document.getElementById('userStatus').textContent='Загрузка...';if(me.theme)setTheme(me.theme);await loadChats();await checkStatus();}else{document.getElementById('authOverlay').style.display='flex';try{const t=localStorage.getItem('awesome_theme');if(t)setTheme(t);}catch(e){}}}
document.addEventListener('DOMContentLoaded',init);
</script>
</body>
</html>"""

if __name__ == '__main__':
    print("=" * 60)
    print("🧠 AWESOME AI WEB — DeepSeek-подобный")
    print("=" * 60)
    print("✅ Вход/Регистрация, автовход")
    print("✅ Статус (Premium/админ/владелец) из TG-бота по Telegram-ID")
    print("✅ Тёмная/светлая тема, настройки")
    print("✅ Оранжевые заголовки ответов ИИ")
    print("✅ Память диалога, полные ответы")
    print("=" * 60)
    port = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
