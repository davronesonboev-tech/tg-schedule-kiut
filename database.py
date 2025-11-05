import sqlite3
import os
from typing import Dict, List, Optional, Any
import json

DB_FILE = 'bot_database.db'

class Database:
    def __init__(self):
        self.db_file = DB_FILE
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных SQLite"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                education_type TEXT NOT NULL,
                course TEXT NOT NULL,
                group_name TEXT NOT NULL,
                format_type TEXT DEFAULT 'photo',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица чатов (групп)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chats (
                chat_id INTEGER PRIMARY KEY,
                education_type TEXT NOT NULL,
                course TEXT NOT NULL,
                group_name TEXT NOT NULL,
                file_name TEXT NOT NULL,
                format_type TEXT DEFAULT 'photo',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица админов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица настроек
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица логов действий пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Индекс для логов
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_logs_user ON user_logs(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON user_logs(timestamp)')
        
        # Таблица расписаний групп
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_name TEXT NOT NULL UNIQUE,
                schedule_json TEXT NOT NULL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица настроек уведомлений пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notification_settings (
                user_id INTEGER PRIMARY KEY,
                enabled BOOLEAN DEFAULT 1,
                minutes_before INTEGER DEFAULT 10,
                timezone TEXT DEFAULT 'Asia/Tashkent',
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        
        # Добавляем дефолтного админа если БД пустая
        cursor.execute('SELECT COUNT(*) FROM admins')
        if cursor.fetchone()[0] == 0:
            cursor.execute('INSERT INTO admins (user_id) VALUES (?)', (1395804259,))
        
        # Создаем индексы для ускорения запросов
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_education ON users(education_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_course ON users(course)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chats_education ON chats(education_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chats_course ON chats(course)')
        
        # Добавляем дефолтные настройки если их нет
        default_settings = {
            'check_interval': '30',
            'default_format': 'photo',
            'main_folder_id': '1Ud2rCjM099mjmKI6Hi1Okw08ZzD5_9U_'
        }
        
        for key, value in default_settings.items():
            cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
            if not cursor.fetchone():
                cursor.execute('INSERT INTO settings (key, value) VALUES (?, ?)', (key, value))
        
        conn.commit()
        conn.close()
    
    def _get_connection(self):
        """Получить подключение к БД"""
        return sqlite3.connect(self.db_file)
    
    # ==================== ПОЛЬЗОВАТЕЛИ ====================
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        """Получить данные пользователя"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT education_type, course, group_name, format_type 
            FROM users WHERE user_id = ?
        ''', (user_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'education_type': row[0],
                'course': row[1],
                'group': row[2],
                'format': row[3]
            }
        return None
    
    def save_user(self, user_id: int, education_type: str, course: str, group: str, format_type: str = "photo"):
        """Сохранить выбор пользователя"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (user_id, education_type, course, group_name, format_type, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (user_id, education_type, course, group, format_type))
        
        conn.commit()
        conn.close()
    
    def delete_user(self, user_id: int):
        """Удалить пользователя"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
        
        conn.commit()
        conn.close()
    
    def get_all_users(self) -> List[Dict]:
        """Получить всех пользователей"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT user_id, education_type, course, group_name, format_type FROM users')
        
        users = []
        for row in cursor.fetchall():
            users.append({
                'user_id': row[0],
                'education_type': row[1],
                'course': row[2],
                'group': row[3],
                'format': row[4]
            })
        
        conn.close()
        return users
    
    # ==================== ЧАТЫ ====================
    
    def get_chat(self, chat_id: int) -> Optional[Dict]:
        """Получить данные чата"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT education_type, course, group_name, file_name, format_type 
            FROM chats WHERE chat_id = ?
        ''', (chat_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'education_type': row[0],
                'course': row[1],
                'group': row[2],
                'file_name': row[3],
                'format': row[4]
            }
        return None
    
    def save_chat(self, chat_id: int, education_type: str, course: str, group: str, 
                  file_name: str, format_type: str = "photo"):
        """Сохранить настройки чата"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO chats 
            (chat_id, education_type, course, group_name, file_name, format_type, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (chat_id, education_type, course, group, file_name, format_type))
        
        conn.commit()
        conn.close()
    
    def get_all_chats(self) -> Dict[str, Dict]:
        """Получить все чаты (в формате совместимом со старым кодом)"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT chat_id, education_type, course, group_name, file_name, format_type FROM chats')
        
        chats = {}
        for row in cursor.fetchall():
            chats[str(row[0])] = {
                'education_type': row[1],
                'course': row[2],
                'group': row[3],
                'file_name': row[4],
                'format': row[5]
            }
        
        conn.close()
        return chats
    
    def delete_chat(self, chat_id: int):
        """Удалить чат"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM chats WHERE chat_id = ?', (chat_id,))
        
        conn.commit()
        conn.close()
    
    # ==================== АДМИНЫ ====================
    
    def is_admin(self, user_id: int) -> bool:
        """Проверка админа"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT user_id FROM admins WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        conn.close()
        return result is not None
    
    def add_admin(self, user_id: int):
        """Добавить админа"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (user_id,))
        
        conn.commit()
        conn.close()
    
    def remove_admin(self, user_id: int):
        """Удалить админа"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Проверяем что не последний админ
        cursor.execute('SELECT COUNT(*) FROM admins')
        if cursor.fetchone()[0] > 1:
            cursor.execute('DELETE FROM admins WHERE user_id = ?', (user_id,))
            conn.commit()
        
        conn.close()
    
    def get_all_admins(self) -> List[int]:
        """Получить всех админов"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT user_id FROM admins')
        admins = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        return admins
    
    # ==================== НАСТРОЙКИ ====================
    
    def get_setting(self, key: str) -> Any:
        """Получить настройку"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        row = cursor.fetchone()
        
        conn.close()
        
        if row:
            value = row[0]
            # Пытаемся распарсить JSON если это не простая строка
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        return None
    
    def set_setting(self, key: str, value: Any):
        """Установить настройку"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Конвертируем в JSON если не строка
        if not isinstance(value, str):
            value = json.dumps(value)
        
        cursor.execute('''
            INSERT OR REPLACE INTO settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        ''', (key, value))
        
        conn.commit()
        conn.close()
    
    def get_check_interval(self) -> int:
        """Получить интервал проверки"""
        value = self.get_setting('check_interval')
        return int(value) if value else 30
    
    def set_check_interval(self, interval: int):
        """Установить интервал проверки"""
        self.set_setting('check_interval', str(interval))
    
    # ==================== СТАТИСТИКА ====================
    
    def get_stats(self) -> Dict:
        """Получить статистику"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM users')
        users_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM chats')
        chats_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM admins')
        admins_count = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'users': users_count,
            'chats': chats_count,
            'admins': admins_count
        }
    
    def get_extended_stats(self) -> Dict:
        """Расширенная статистика"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        stats = {}
        
        # Пользователи по формам обучения
        cursor.execute('''
            SELECT education_type, COUNT(*) 
            FROM users 
            GROUP BY education_type
        ''')
        stats['users_by_education'] = dict(cursor.fetchall())
        
        # Пользователи по курсам
        cursor.execute('''
            SELECT course, COUNT(*) 
            FROM users 
            GROUP BY course 
            ORDER BY course
        ''')
        stats['users_by_course'] = dict(cursor.fetchall())
        
        # Популярные группы
        cursor.execute('''
            SELECT group_name, COUNT(*) as cnt 
            FROM users 
            GROUP BY group_name 
            ORDER BY cnt DESC 
            LIMIT 10
        ''')
        stats['top_groups'] = cursor.fetchall()
        
        # Форматы
        cursor.execute('''
            SELECT format_type, COUNT(*) 
            FROM users 
            GROUP BY format_type
        ''')
        stats['formats'] = dict(cursor.fetchall())
        
        # Активность (последние 7 дней)
        cursor.execute('''
            SELECT DATE(created_at) as date, COUNT(*) 
            FROM users 
            WHERE created_at >= datetime('now', '-7 days') 
            GROUP BY date 
            ORDER BY date DESC
        ''')
        stats['recent_activity'] = cursor.fetchall()
        
        conn.close()
        return stats
    
    # ==================== ЛОГИРОВАНИЕ ====================
    
    def log_action(self, user_id: int, action: str, details: str = None):
        """Логировать действие пользователя"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO user_logs (user_id, action, details)
                VALUES (?, ?, ?)
            ''', (user_id, action, details))
            
            conn.commit()
            conn.close()
        except Exception as e:
            import logging
            logging.error(f"Ошибка логирования: {e}")
    
    def get_user_activity(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Получить историю действий пользователя"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT action, details, timestamp 
            FROM user_logs 
            WHERE user_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (user_id, limit))
        
        logs = []
        for row in cursor.fetchall():
            logs.append({
                'action': row[0],
                'details': row[1],
                'timestamp': row[2]
            })
        
        conn.close()
        return logs
    
    def get_recent_logs(self, hours: int = 24, limit: int = 100) -> List[Dict]:
        """Получить последние логи за N часов"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id, action, details, timestamp 
            FROM user_logs 
            WHERE timestamp >= datetime('now', '-' || ? || ' hours')
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (hours, limit))
        
        logs = []
        for row in cursor.fetchall():
            logs.append({
                'user_id': row[0],
                'action': row[1],
                'details': row[2],
                'timestamp': row[3]
            })
        
        conn.close()
        return logs
    
    def cleanup_old_logs(self, days: int = 30):
        """Удалить старые логи"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            DELETE FROM user_logs 
            WHERE timestamp < datetime('now', '-' || ? || ' days')
        ''', (days,))
        
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        return deleted
    
    # ==================== РАСПИСАНИЯ ====================
    
    def save_schedule(self, group_name: str, schedule_json: str):
        """Сохранить расписание группы"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO schedules (group_name, schedule_json, last_updated)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        ''', (group_name, schedule_json))
        
        conn.commit()
        conn.close()
    
    def get_schedule(self, group_name: str) -> Optional[str]:
        """Получить расписание группы"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT schedule_json FROM schedules WHERE group_name = ?
        ''', (group_name,))
        
        row = cursor.fetchone()
        conn.close()
        
        return row[0] if row else None
    
    def get_schedule_age(self, group_name: str) -> Optional[int]:
        """Получить возраст расписания в часах"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                CAST((julianday('now') - julianday(last_updated)) * 24 AS INTEGER) as hours_old
            FROM schedules 
            WHERE group_name = ?
        ''', (group_name,))
        
        row = cursor.fetchone()
        conn.close()
        
        return row[0] if row else None
    
    # ==================== НАСТРОЙКИ УВЕДОМЛЕНИЙ ====================
    
    def get_notification_settings(self, user_id: int) -> Optional[Dict]:
        """Получить настройки уведомлений пользователя"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT enabled, minutes_before, timezone 
            FROM notification_settings 
            WHERE user_id = ?
        ''', (user_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'enabled': bool(row[0]),
                'minutes_before': row[1],
                'timezone': row[2]
            }
        return None
    
    def set_notification_settings(self, user_id: int, enabled: bool = True, 
                                  minutes_before: int = 10, timezone: str = 'Asia/Tashkent'):
        """Установить настройки уведомлений"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO notification_settings 
            (user_id, enabled, minutes_before, timezone)
            VALUES (?, ?, ?, ?)
        ''', (user_id, enabled, minutes_before, timezone))
        
        conn.commit()
        conn.close()
    
    def toggle_notifications(self, user_id: int) -> bool:
        """Переключить уведомления вкл/выкл. Возвращает новое состояние"""
        settings = self.get_notification_settings(user_id)
        
        if settings is None:
            # Создаем настройки (включены по умолчанию)
            self.set_notification_settings(user_id, enabled=True)
            return True
        else:
            # Переключаем
            new_state = not settings['enabled']
            self.set_notification_settings(
                user_id, 
                enabled=new_state,
                minutes_before=settings['minutes_before'],
                timezone=settings['timezone']
            )
            return new_state
    
    def get_users_with_notifications_enabled(self) -> List[Dict]:
        """Получить всех пользователей с включенными уведомлениями"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT u.user_id, u.group_name, ns.minutes_before, ns.timezone
            FROM users u
            JOIN notification_settings ns ON u.user_id = ns.user_id
            WHERE ns.enabled = 1
        ''')
        
        users = []
        for row in cursor.fetchall():
            users.append({
                'user_id': row[0],
                'group': row[1],
                'minutes_before': row[2],
                'timezone': row[3]
            })
        
        conn.close()
        return users
