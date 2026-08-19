#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import os
import sys
from datetime import datetime, timedelta

DB_PATH = 'users_web.db'

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def print_separator():
    print("=" * 70)

# ============================================================
# 1. ПРОСМОТР ПОЛЬЗОВАТЕЛЕЙ
# ============================================================
def list_users():
    """Показать всех пользователей"""
    try:
        conn = get_conn()
        users = conn.execute('''
            SELECT 
                user_id, 
                username, 
                premium,
                messages_today,
                premium_expires,
                is_admin,
                test_used,
                joined_at
            FROM users_web 
            ORDER BY user_id DESC
        ''').fetchall()
        conn.close()
        
        print_separator()
        print(f"👥 ВСЕ ПОЛЬЗОВАТЕЛИ ({len(users)})")
        print_separator()
        
        if users:
            print(f"{'ID':<15} {'ЮЗЕР':<20} {'PREMIUM':<10} {'СООБЩ':<10} {'АДМИН':<8} {'ДО':<20}")
            print("-" * 83)
            for u in users:
                expires = u['premium_expires'][:16] if u['premium_expires'] else "нет"
                username = u['username'] or 'unknown'
                print(f"{u['user_id']:<15} @{username:<18} {u['premium']:<10} {u['messages_today']:<10} {u['is_admin']:<8} {expires:<20}")
        else:
            print("❌ Пользователей нет")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

def get_user(user_id):
    """Информация о конкретном пользователе"""
    try:
        conn = get_conn()
        user = conn.execute('SELECT * FROM users_web WHERE user_id = ?', (user_id,)).fetchone()
        conn.close()
        
        if not user:
            print(f"❌ Пользователь {user_id} не найден")
            return
        
        print_separator()
        print(f"👤 ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ {user_id}")
        print_separator()
        for key in user.keys():
            print(f"{key}: {user[key]}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

# ============================================================
# 2. УПРАВЛЕНИЕ PREMIUM
# ============================================================
def give_premium(user_id, days):
    """Выдать Premium пользователю"""
    try:
        conn = get_conn()
        c = conn.cursor()
        
        user = c.execute('SELECT * FROM users_web WHERE user_id = ?', (user_id,)).fetchone()
        if not user:
            print(f"❌ Пользователь {user_id} не найден")
            conn.close()
            return
        
        now = datetime.now()
        expires = (now + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        
        c.execute('''
            UPDATE users_web 
            SET premium = 1, premium_expires = ? 
            WHERE user_id = ?
        ''', (expires, user_id))
        conn.commit()
        conn.close()
        
        print(f"✅ Premium выдан пользователю {user_id} до {expires}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

def remove_premium(user_id):
    """Забрать Premium у пользователя"""
    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute('''
            UPDATE users_web 
            SET premium = 0, premium_expires = NULL 
            WHERE user_id = ?
        ''', (user_id,))
        conn.commit()
        conn.close()
        print(f"✅ Premium забран у пользователя {user_id}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

# ============================================================
# 3. УПРАВЛЕНИЕ АДМИНАМИ
# ============================================================
def make_admin(user_id):
    """Сделать пользователя админом"""
    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute('UPDATE users_web SET is_admin = 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        print(f"✅ Пользователь {user_id} стал админом")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

def remove_admin(user_id):
    """Забрать админку"""
    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute('UPDATE users_web SET is_admin = 0 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        print(f"✅ У пользователя {user_id} забрали админку")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

# ============================================================
# 4. ПРОСМОТР ИСТОРИИ ЧАТОВ
# ============================================================
def show_history(user_id, limit=20):
    """Показать историю чатов пользователя"""
    try:
        conn = get_conn()
        history = conn.execute('''
            SELECT id, chat_id, role, content, timestamp 
            FROM chat_history_web 
            WHERE user_id = ?
            ORDER BY id DESC LIMIT ?
        ''', (user_id, limit)).fetchall()
        conn.close()
        
        if not history:
            print(f"❌ Нет истории для пользователя {user_id}")
            return
        
        print_separator()
        print(f"📜 ИСТОРИЯ ПОЛЬЗОВАТЕЛЯ {user_id} (последние {len(history)})")
        print_separator()
        
        for msg in reversed(history):
            role = "👤 ВЫ" if msg['role'] == 'user' else "🤖 AWESOME AI"
            content = msg['content'][:100] + "..." if len(msg['content']) > 100 else msg['content']
            print(f"{role}: {content}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

def show_all_history(limit=50):
    """Показать последние сообщения всех пользователей"""
    try:
        conn = get_conn()
        history = conn.execute('''
            SELECT id, user_id, chat_id, role, content, timestamp 
            FROM chat_history_web 
            ORDER BY id DESC LIMIT ?
        ''', (limit,)).fetchall()
        conn.close()
        
        if not history:
            print("❌ Нет сообщений")
            return
        
        print_separator()
        print(f"📜 ПОСЛЕДНИЕ {len(history)} СООБЩЕНИЙ")
        print_separator()
        
        for msg in reversed(history):
            role = "👤" if msg['role'] == 'user' else "🤖"
            content = msg['content'][:80] + "..." if len(msg['content']) > 80 else msg['content']
            print(f"[{msg['user_id']}] {role}: {content}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

# ============================================================
# 5. СТАТИСТИКА
# ============================================================
def show_stats():
    """Показать статистику"""
    try:
        conn = get_conn()
        c = conn.cursor()
        
        total_users = c.execute('SELECT COUNT(*) FROM users_web').fetchone()[0]
        premium_users = c.execute('SELECT COUNT(*) FROM users_web WHERE premium = 1').fetchone()[0]
        admin_users = c.execute('SELECT COUNT(*) FROM users_web WHERE is_admin = 1').fetchone()[0]
        total_messages = c.execute('SELECT COUNT(*) FROM chat_history_web').fetchone()[0]
        
        top_users = c.execute('''
            SELECT user_id, COUNT(*) as cnt 
            FROM chat_history_web 
            GROUP BY user_id 
            ORDER BY cnt DESC 
            LIMIT 5
        ''').fetchall()
        
        conn.close()
        
        print_separator()
        print("📊 СТАТИСТИКА")
        print_separator()
        print(f"👥 Всего пользователей: {total_users}")
        print(f"💎 Premium: {premium_users}")
        print(f"👑 Админов: {admin_users}")
        print(f"📨 Всего сообщений: {total_messages}")
        print()
        print("🏆 ТОП ПО СООБЩЕНИЯМ:")
        for u in top_users:
            print(f"  {u['user_id']}: {u['cnt']} сообщений")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

# ============================================================
# 6. ОЧИСТКА
# ============================================================
def clear_user_history(user_id):
    """Очистить историю пользователя"""
    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute('DELETE FROM chat_history_web WHERE user_id = ?', (user_id,))
        deleted = c.rowcount
        conn.commit()
        conn.close()
        print(f"✅ Удалено {deleted} сообщений пользователя {user_id}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

def clear_all_history():
    """Очистить ВСЮ историю"""
    try:
        if input("⚠️ УДАЛИТЬ ВСЮ ИСТОРИЮ? (yes/no): ") != "yes":
            print("❌ Отменено")
            return
        conn = get_conn()
        c = conn.cursor()
        c.execute('DELETE FROM chat_history_web')
        conn.commit()
        conn.close()
        print("✅ Вся история удалена")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

def reset_messages(user_id):
    """Сбросить счётчик сообщений за сегодня"""
    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute('UPDATE users_web SET messages_today = 0 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        print(f"✅ Счётчик сообщений пользователя {user_id} сброшен")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

# ============================================================
# 7. БАН И МУТ
# ============================================================
def ban_user(user_id):
    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO banned_web (user_id) VALUES (?)', (user_id,))
        conn.commit()
        conn.close()
        print(f"✅ Пользователь {user_id} забанен")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

def unban_user(user_id):
    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute('DELETE FROM banned_web WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        print(f"✅ Пользователь {user_id} разбанен")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

def mute_user(user_id):
    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO muted_web (user_id) VALUES (?)', (user_id,))
        conn.commit()
        conn.close()
        print(f"✅ Пользователь {user_id} замучен")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

def unmute_user(user_id):
    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute('DELETE FROM muted_web WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        print(f"✅ Пользователь {user_id} размучен")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

# ============================================================
# 8. ПАМЯТЬ
# ============================================================
def show_memory(user_id):
    """Показать что бот запомнил о пользователе"""
    try:
        conn = get_conn()
        memory = conn.execute('''
            SELECT topic, fact, timestamp 
            FROM user_memory_web 
            WHERE user_id = ?
            ORDER BY id DESC
        ''', (user_id,)).fetchall()
        conn.close()
        
        if not memory:
            print(f"❌ Нет сохранённой памяти для {user_id}")
            return
        
        print_separator()
        print(f"🧠 ПАМЯТЬ О ПОЛЬЗОВАТЕЛЕ {user_id}")
        print_separator()
        for m in memory:
            print(f"📌 {m['topic']}: {m['fact']}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

# ============================================================
# ГЛАВНОЕ МЕНЮ
# ============================================================
def main():
    while True:
        print()
        print_separator()
        print("🧠 УПРАВЛЕНИЕ SQLite БАЗОЙ AWESOME AI")
        print_separator()
        print("1. 👥 Список всех пользователей")
        print("2. 👤 Информация о пользователе")
        print("3. 💎 Выдать Premium (по дням)")
        print("4. 💎 Забрать Premium")
        print("5. 👑 Сделать админом")
        print("6. 👑 Забрать админку")
        print("7. 📜 История чатов пользователя")
        print("8. 📜 Все последние сообщения")
        print("9. 📊 Статистика")
        print("10. 🗑️ Очистить историю пользователя")
        print("11. 🗑️ Очистить ВСЮ историю")
        print("12. 🔄 Сбросить счётчик сообщений")
        print("13. 🚫 Забанить")
        print("14. ✅ Разбанить")
        print("15. 🔇 Замутить")
        print("16. 🔊 Размутить")
        print("17. 🧠 Память о пользователе")
        print("0. ❌ Выйти")
        print_separator()
        
        choice = input("Выбери действие: ").strip()
        
        if choice == "0":
            print("👋 Пока!")
            break
        
        elif choice == "1":
            list_users()
        
        elif choice == "2":
            try:
                uid = int(input("ID пользователя: "))
                get_user(uid)
            except:
                print("❌ Введи число")
        
        elif choice == "3":
            try:
                uid = int(input("ID пользователя: "))
                days = int(input("Количество дней: "))
                give_premium(uid, days)
            except:
                print("❌ Введи число")
        
        elif choice == "4":
            try:
                uid = int(input("ID пользователя: "))
                remove_premium(uid)
            except:
                print("❌ Введи число")
        
        elif choice == "5":
            try:
                uid = int(input("ID пользователя: "))
                make_admin(uid)
            except:
                print("❌ Введи число")
        
        elif choice == "6":
            try:
                uid = int(input("ID пользователя: "))
                remove_admin(uid)
            except:
                print("❌ Введи число")
        
        elif choice == "7":
            try:
                uid = int(input("ID пользователя: "))
                limit = input("Сколько сообщений (по умолчанию 20): ").strip()
                limit = int(limit) if limit else 20
                show_history(uid, limit)
            except:
                print("❌ Введи число")
        
        elif choice == "8":
            try:
                limit = input("Сколько сообщений (по умолчанию 50): ").strip()
                limit = int(limit) if limit else 50
                show_all_history(limit)
            except:
                print("❌ Введи число")
        
        elif choice == "9":
            show_stats()
        
        elif choice == "10":
            try:
                uid = int(input("ID пользователя: "))
                clear_user_history(uid)
            except:
                print("❌ Введи число")
        
        elif choice == "11":
            clear_all_history()
        
        elif choice == "12":
            try:
                uid = int(input("ID пользователя: "))
                reset_messages(uid)
            except:
                print("❌ Введи число")
        
        elif choice == "13":
            try:
                uid = int(input("ID пользователя: "))
                ban_user(uid)
            except:
                print("❌ Введи число")
        
        elif choice == "14":
            try:
                uid = int(input("ID пользователя: "))
                unban_user(uid)
            except:
                print("❌ Введи число")
        
        elif choice == "15":
            try:
                uid = int(input("ID пользователя: "))
                mute_user(uid)
            except:
                print("❌ Введи число")
        
        elif choice == "16":
            try:
                uid = int(input("ID пользователя: "))
                unmute_user(uid)
            except:
                print("❌ Введи число")
        
        elif choice == "17":
            try:
                uid = int(input("ID пользователя: "))
                show_memory(uid)
            except:
                print("❌ Введи число")
        
        else:
            print("❌ Неизвестная команда")

if __name__ == "__main__":
    print("🧠 AWESOME AI - УПРАВЛЕНИЕ БАЗОЙ ДАННЫХ")
    print(f"📁 База: {DB_PATH}")
    print(f"📂 Путь: {os.path.abspath(DB_PATH)}")
    
    if not os.path.exists(DB_PATH):
        print(f"❌ База данных {DB_PATH} не найдена!")
        print("📌 Создай базу через web.py")
        sys.exit(1)
    
    main()
