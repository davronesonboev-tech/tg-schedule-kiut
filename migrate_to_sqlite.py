#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт миграции данных из JSON в SQLite
Использование: python migrate_to_sqlite.py
"""

import json
import os
import shutil
import sqlite3
from datetime import datetime
from database import Database

JSON_FILE = 'bot_database.json'
BACKUP_FOLDER = 'backups'


class MigrationError(Exception):
    """Ошибка миграции"""
    pass


def create_backup():
    """Создать бэкап перед миграцией"""
    os.makedirs(BACKUP_FOLDER, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    backups = []
    
    # Бэкап JSON если существует
    if os.path.exists(JSON_FILE):
        backup_json = os.path.join(BACKUP_FOLDER, f'{JSON_FILE}.{timestamp}.bak')
        shutil.copy2(JSON_FILE, backup_json)
        backups.append(backup_json)
        print(f"[✓] JSON backup: {backup_json}")
    
    # Бэкап старой БД если существует
    if os.path.exists('bot_database.db'):
        backup_db = os.path.join(BACKUP_FOLDER, f'bot_database.db.{timestamp}.bak')
        shutil.copy2('bot_database.db', backup_db)
        backups.append(backup_db)
        print(f"[✓] DB backup: {backup_db}")
    
    return backups


def validate_json_data(data: dict):
    """Валидация данных JSON"""
    errors = []
    warnings = []
    
    # Проверка структуры
    required_keys = ['users', 'chats', 'admin_ids', 'settings']
    for key in required_keys:
        if key not in data:
            errors.append(f"Отсутствует ключ: {key}")
    
    # Валидация пользователей
    users = data.get('users', {})
    for user_id, user_data in users.items():
        if not isinstance(user_data, dict):
            errors.append(f"User {user_id}: неверный формат")
            continue
        
        required_fields = ['education_type', 'course', 'group']
        for field in required_fields:
            if field not in user_data:
                warnings.append(f"User {user_id}: отсутствует {field}")
    
    # Валидация чатов
    chats = data.get('chats', {})
    for chat_id, chat_data in chats.items():
        if not isinstance(chat_data, dict):
            errors.append(f"Chat {chat_id}: неверный формат")
            continue
        
        required_fields = ['education_type', 'course', 'group', 'file_name']
        for field in required_fields:
            if field not in chat_data:
                warnings.append(f"Chat {chat_id}: отсутствует {field}")
    
    return errors, warnings


def migrate():
    """Улучшенная миграция с валидацией и rollback"""
    
    print("=" * 60)
    print("🔄 МИГРАЦИЯ ДАННЫХ: JSON → SQLite v2.0")
    print("=" * 60)
    
    # Проверка файла
    if not os.path.exists(JSON_FILE):
        print("\n[!] Файл bot_database.json не найден.")
        print("[+] Создаем новую SQLite базу данных...")
        db = Database()
        print("[✓] База данных создана!")
        return
    
    print(f"\n[1/6] 📂 Найден файл: {JSON_FILE}")
    
    # Создаем бэкапы
    print("\n[2/6] 💾 Создание резервных копий...")
    try:
        backups = create_backup()
    except Exception as e:
        print(f"❌ Ошибка создания бэкапа: {e}")
        return
    
    # Загружаем и валидируем JSON
    print("\n[3/6] 📖 Чтение и валидация JSON...")
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Ошибка чтения JSON: {e}")
        return
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return
    
    errors, warnings = validate_json_data(data)
    
    if errors:
        print("\n❌ КРИТИЧЕСКИЕ ОШИБКИ:")
        for error in errors[:5]:
            print(f"  • {error}")
        print("\n[!] Миграция отменена из-за критических ошибок")
        return
    
    if warnings:
        print("\n⚠️ ПРЕДУПРЕЖДЕНИЯ:")
        for warning in warnings[:5]:
            print(f"  • {warning}")
        if len(warnings) > 5:
            print(f"  ...и еще {len(warnings) - 5} предупреждений")
    
    print("[✓] Валидация пройдена")
    
    # Миграция с транзакцией
    print("\n[4/6] 🔄 Начало миграции...")
    
    db_file = 'bot_database.db'
    conn = sqlite3.connect(db_file)
    
    try:
        conn.execute('BEGIN TRANSACTION')
        
        db = Database()
        
        # Мигрируем пользователей
        users = data.get('users', {})
        print(f"\n   👤 Миграция пользователей: {len(users)}")
        migrated_users = 0
        for user_id, user_data in users.items():
            try:
                db.save_user(
                    int(user_id),
                    user_data.get('education_type', ''),
                    user_data.get('course', ''),
                    user_data.get('group', ''),
                    user_data.get('format', 'photo')
                )
                migrated_users += 1
            except Exception as e:
                print(f"   ⚠️ Ошибка user {user_id}: {e}")
        
        print(f"   [✓] Мигрировано: {migrated_users}/{len(users)}")
        
        # Мигрируем чаты
        chats = data.get('chats', {})
        print(f"\n   💬 Миграция чатов: {len(chats)}")
        migrated_chats = 0
        for chat_id, chat_data in chats.items():
            try:
                db.save_chat(
                    int(chat_id),
                    chat_data.get('education_type', ''),
                    chat_data.get('course', ''),
                    chat_data.get('group', ''),
                    chat_data.get('file_name', ''),
                    chat_data.get('format', 'photo')
                )
                migrated_chats += 1
            except Exception as e:
                print(f"   ⚠️ Ошибка chat {chat_id}: {e}")
        
        print(f"   [✓] Мигрировано: {migrated_chats}/{len(chats)}")
        
        # Мигрируем админов
        admin_ids = data.get('admin_ids', [])
        print(f"\n   👑 Миграция админов: {len(admin_ids)}")
        for admin_id in admin_ids:
            db.add_admin(admin_id)
        print(f"   [✓] Мигрировано: {len(admin_ids)}")
        
        # Мигрируем настройки
        settings = data.get('settings', {})
        print(f"\n   ⚙️ Миграция настроек: {len(settings)}")
        for key, value in settings.items():
            db.set_setting(key, value)
        print(f"   [✓] Мигрировано: {len(settings)}")
        
        conn.commit()
        print("\n[✓] Транзакция успешно завершена")
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ ОШИБКА! Откат изменений...")
        print(f"Ошибка: {e}")
        return
    
    finally:
        conn.close()
    
    # Проверка результата
    print("\n[5/6] ✅ Проверка результата...")
    stats = db.get_stats()
    
    print(f"\n   📊 Статистика:")
    print(f"   • Пользователей: {stats['users']}")
    print(f"   • Чатов: {stats['chats']}")
    print(f"   • Админов: {stats['admins']}")
    
    # Итог
    print("\n[6/6] 🎉 МИГРАЦИЯ ЗАВЕРШЕНА!")
    print("=" * 60)
    print(f"✅ Новая БД: bot_database.db")
    print(f"💾 Резервные копии:")
    for backup in backups:
        print(f"   • {backup}")
    print(f"\n💡 Старый файл {JSON_FILE} можно удалить или оставить как бэкап")
    print("=" * 60)

if __name__ == '__main__':
    try:
        migrate()
    except Exception as e:
        print(f"\n❌ Ошибка миграции: {e}")
        import traceback
        traceback.print_exc()

