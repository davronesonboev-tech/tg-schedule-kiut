#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Система локализации для бота
Поддерживаемые языки: русский (ru), узбекский (uz), английский (en)
"""

import logging
from typing import Dict

logger = logging.getLogger(__name__)

# Словарь переводов
TRANSLATIONS = {
    # ==================== ОСНОВНЫЕ КОМАНДЫ ====================
    'start': {
        'ru': '👋 Привет! Я бот для расписания занятий.\n\nВыбери язык / Tilni tanlang / Choose language:',
        'uz': '👋 Salom! Men dars jadvalini ko\'rsatuvchi botman.\n\nTilni tanlang / Выбери язык / Choose language:',
        'en': '👋 Hello! I\'m a schedule bot.\n\nChoose language / Выбери язык / Tilni tanlang:'
    },
    
    'language_changed': {
        'ru': '✅ Язык изменен на русский',
        'uz': '✅ Til o\'zbekchaga o\'zgartirildi',
        'en': '✅ Language changed to English'
    },
    
    'choose_education_type': {
        'ru': '📚 Выбери тип обучения:',
        'uz': '📚 Ta\'lim turini tanlang:',
        'en': '📚 Choose education type:'
    },
    
    'choose_course': {
        'ru': '🎓 Выбери курс:',
        'uz': '🎓 Kursni tanlang:',
        'en': '🎓 Choose course:'
    },
    
    'loading_groups': {
        'ru': '🌐 Загружаем список групп...',
        'uz': '🌐 Guruhlar ro\'yxatini yuklamoqda...',
        'en': '🌐 Loading groups list...'
    },
    
    'choose_group': {
        'ru': '👥 Выбери свою группу:',
        'uz': '👥 Guruhingizni tanlang:',
        'en': '👥 Choose your group:'
    },
    
    'choose_format': {
        'ru': '📄 В каком формате отправлять расписание?',
        'uz': '📄 Jadvalni qanday formatda yuborish kerak?',
        'en': '📄 In what format should I send the schedule?'
    },
    
    'format_photo': {
        'ru': '📷 Картинкой',
        'uz': '📷 Rasm sifatida',
        'en': '📷 As image'
    },
    
    'format_pdf': {
        'ru': '📎 PDF файлом',
        'uz': '📎 PDF fayl sifatida',
        'en': '📎 As PDF file'
    },
    
    'setup_complete': {
        'ru': '✅ Отлично! Настройка завершена.\n\n📋 Твоё расписание сохранено.\n\n💡 Используй команды:\n/schedule - Посмотреть расписание\n/settings - Изменить настройки\n/notifications - Настроить уведомления\n/language - Сменить язык',
        'uz': '✅ Ajoyib! Sozlash tugallandi.\n\n📋 Jadvalingiz saqlandi.\n\n💡 Buyruqlardan foydalaning:\n/schedule - Jadvalni ko\'rish\n/settings - Sozlamalarni o\'zgartirish\n/notifications - Bildirishnomalarni sozlash\n/language - Tilni o\'zgartirish',
        'en': '✅ Great! Setup complete.\n\n📋 Your schedule has been saved.\n\n💡 Use commands:\n/schedule - View schedule\n/settings - Change settings\n/notifications - Configure notifications\n/language - Change language'
    },
    
    # ==================== РАСПИСАНИЕ ====================
    'schedule_title': {
        'ru': '📅 Расписание группы',
        'uz': '📅 Guruh jadvali',
        'en': '📅 Group schedule'
    },
    
    'updated': {
        'ru': 'Обновлено',
        'uz': 'Yangilandi',
        'en': 'Updated'
    },
    
    'not_configured': {
        'ru': '❌ Вы ещё не настроили расписание.\nИспользуйте /start для настройки.',
        'uz': '❌ Siz hali jadvalni sozlamadingiz.\nSozlash uchun /start buyrug\'idan foydalaning.',
        'en': '❌ You haven\'t configured your schedule yet.\nUse /start to set it up.'
    },
    
    'file_not_found': {
        'ru': 'Файл {filename} не найден на Google Drive.\nПроверьте правильность названия группы.',
        'uz': '{filename} fayli Google Drive\'da topilmadi.\nGuruh nomining to\'g\'riligini tekshiring.',
        'en': 'File {filename} not found on Google Drive.\nCheck if the group name is correct.'
    },
    
    'schedule_updated': {
        'ru': '📅 Расписание обновлено!',
        'uz': '📅 Jadval yangilandi!',
        'en': '📅 Schedule updated!'
    },
    
    'no_classes_today': {
        'ru': '🎉 Сегодня пар нет! Отдыхай!',
        'uz': '🎉 Bugun darslar yo\'q! Dam oling!',
        'en': '🎉 No classes today! Relax!'
    },
    
    'schedule_for_today': {
        'ru': '📅 *Расписание на {weekday}*',
        'uz': '📅 *{weekday} kuni jadvali*',
        'en': '📅 *Schedule for {weekday}*'
    },
    
    'group': {
        'ru': 'Группа',
        'uz': 'Guruh',
        'en': 'Group'
    },
    
    'room': {
        'ru': 'Аудитория',
        'uz': 'Xona',
        'en': 'Room'
    },
    
    'all_classes_done': {
        'ru': '✅ _Все пары на сегодня завершены!_',
        'uz': '✅ _Bugun barcha darslar tugadi!_',
        'en': '✅ _All classes for today are done!_'
    },
    
    'auto_updates': {
        'ru': '💡 _Сообщение обновляется автоматически_',
        'uz': '💡 _Xabar avtomatik yangilanadi_',
        'en': '💡 _Message updates automatically_'
    },
    
    # ==================== УВЕДОМЛЕНИЯ ====================
    'notifications_settings': {
        'ru': '🔔 Настройки уведомлений',
        'uz': '🔔 Bildirishnomalar sozlamalari',
        'en': '🔔 Notification settings'
    },
    
    'notifications_enabled': {
        'ru': '✅ Уведомления включены',
        'uz': '✅ Bildirishnomalar yoqilgan',
        'en': '✅ Notifications enabled'
    },
    
    'notifications_disabled': {
        'ru': '🔕 Уведомления выключены',
        'uz': '🔕 Bildirishnomalar o\'chirilgan',
        'en': '🔕 Notifications disabled'
    },
    
    'notify_before': {
        'ru': '⏰ Напоминать за {minutes} мин до пары',
        'uz': '⏰ Darsdan {minutes} daqiqa oldin eslatma',
        'en': '⏰ Remind {minutes} min before class'
    },
    
    'class_reminder': {
        'ru': '🔔 *Напоминание о паре!*\n\n⏰ Начало через *{minutes} мин* ({time})\n📚 *{subject}*\n{room}💨 Не опаздывай!',
        'uz': '🔔 *Dars haqida eslatma!*\n\n⏰ *{minutes} daqiqadan* ({time}) keyin boshlanadi\n📚 *{subject}*\n{room}💨 Kechikma!',
        'en': '🔔 *Class reminder!*\n\n⏰ Starts in *{minutes} min* ({time})\n📚 *{subject}*\n{room}💨 Don\'t be late!'
    },
    
    'toggle_notifications': {
        'ru': '🔄 Вкл/Выкл уведомления',
        'uz': '🔄 Bildirishnomalarni yoq/o\'chir',
        'en': '🔄 Toggle notifications'
    },
    
    'change_time': {
        'ru': '⏰ Изменить время',
        'uz': '⏰ Vaqtni o\'zgartirish',
        'en': '⏰ Change time'
    },
    
    'notification_time_changed': {
        'ru': '✅ Время уведомления изменено на {minutes} минут до пары',
        'uz': '✅ Bildirishnoma vaqti darsdan {minutes} daqiqa oldin o\'zgartirildi',
        'en': '✅ Notification time changed to {minutes} minutes before class'
    },
    
    # ==================== НАСТРОЙКИ ====================
    'settings': {
        'ru': '⚙️ Настройки',
        'uz': '⚙️ Sozlamalar',
        'en': '⚙️ Settings'
    },
    
    'your_settings': {
        'ru': '⚙️ *Твои настройки:*\n\n🎓 Тип: {education_type}\n📚 Курс: {course}\n👥 Группа: {group}\n📄 Формат: {format}\n🌐 Язык: {language}',
        'uz': '⚙️ *Sizning sozlamalaringiz:*\n\n🎓 Tur: {education_type}\n📚 Kurs: {course}\n👥 Guruh: {group}\n📄 Format: {format}\n🌐 Til: {language}',
        'en': '⚙️ *Your settings:*\n\n🎓 Type: {education_type}\n📚 Course: {course}\n👥 Group: {group}\n📄 Format: {format}\n🌐 Language: {language}'
    },
    
    'change_group': {
        'ru': '👥 Сменить группу',
        'uz': '👥 Guruhni o\'zgartirish',
        'en': '👥 Change group'
    },
    
    'change_format': {
        'ru': '📄 Сменить формат',
        'uz': '📄 Formatni o\'zgartirish',
        'en': '📄 Change format'
    },
    
    'change_language': {
        'ru': '🌐 Сменить язык',
        'uz': '🌐 Tilni o\'zgartirish',
        'en': '🌐 Change language'
    },
    
    'back': {
        'ru': '◀️ Назад',
        'uz': '◀️ Orqaga',
        'en': '◀️ Back'
    },
    
    'cancel': {
        'ru': '❌ Отмена',
        'uz': '❌ Bekor qilish',
        'en': '❌ Cancel'
    },
    
    # ==================== АДМИНКА ====================
    'admin_menu': {
        'ru': '👑 *Панель администратора*',
        'uz': '👑 *Administrator paneli*',
        'en': '👑 *Admin panel*'
    },
    
    'total_users': {
        'ru': '👥 Всего пользователей',
        'uz': '👥 Jami foydalanuvchilar',
        'en': '👥 Total users'
    },
    
    'active_groups': {
        'ru': '📚 Активных групп',
        'uz': '📚 Faol guruhlar',
        'en': '📚 Active groups'
    },
    
    'subscribed_chats': {
        'ru': '💬 Подписанных чатов',
        'uz': '💬 Obuna bo\'lgan chatlar',
        'en': '💬 Subscribed chats'
    },
    
    'with_notifications': {
        'ru': '🔔 С уведомлениями',
        'uz': '🔔 Bildirishnomalar bilan',
        'en': '🔔 With notifications'
    },
    
    'popular_groups': {
        'ru': '📊 *Популярные группы:*',
        'uz': '📊 *Mashhur guruhlar:*',
        'en': '📊 *Popular groups:*'
    },
    
    'analytics': {
        'ru': '📊 Расширенная аналитика',
        'uz': '📊 Kengaytirilgan tahlil',
        'en': '📊 Advanced analytics'
    },
    
    'user_activity': {
        'ru': '📈 *Активность пользователей* (последние 7 дней)',
        'uz': '📈 *Foydalanuvchilar faolligi* (so\'nggi 7 kun)',
        'en': '📈 *User activity* (last 7 days)'
    },
    
    'peak_hours': {
        'ru': '🕐 *Пиковые часы использования:*',
        'uz': '🕐 *Eng faol vaqt:*',
        'en': '🕐 *Peak usage hours:*'
    },
    
    'conversion_stats': {
        'ru': '📉 *Статистика конверсии:*',
        'uz': '📉 *Konversiya statistikasi:*',
        'en': '📉 *Conversion statistics:*'
    },
    
    'registered': {
        'ru': 'Зарегистрировано',
        'uz': 'Ro\'yxatdan o\'tgan',
        'en': 'Registered'
    },
    
    'active_7_days': {
        'ru': 'Активны за 7 дней',
        'uz': '7 kun ichida faol',
        'en': 'Active in 7 days'
    },
    
    'active_30_days': {
        'ru': 'Активны за 30 дней',
        'uz': '30 kun ichida faol',
        'en': 'Active in 30 days'
    },
    
    'conversion_rate': {
        'ru': 'Конверсия',
        'uz': 'Konversiya',
        'en': 'Conversion rate'
    },
    
    'language_distribution': {
        'ru': '🌐 *Распределение по языкам:*',
        'uz': '🌐 *Tillar bo\'yicha taqsimot:*',
        'en': '🌐 *Language distribution:*'
    },
    
    'no_access': {
        'ru': '❌ У вас нет доступа к админ-панели',
        'uz': '❌ Sizda admin-panelga kirish huquqi yo\'q',
        'en': '❌ You don\'t have access to the admin panel'
    },
    
    # ==================== ОШИБКИ ====================
    'error_occurred': {
        'ru': '❌ Произошла ошибка. Попробуйте позже.',
        'uz': '❌ Xatolik yuz berdi. Keyinroq urinib ko\'ring.',
        'en': '❌ An error occurred. Please try again later.'
    },
    
    'download_error': {
        'ru': '❌ Ошибка загрузки файла',
        'uz': '❌ Faylni yuklashda xatolik',
        'en': '❌ File download error'
    },
    
    # ==================== ДНИ НЕДЕЛИ ====================
    'monday': {
        'ru': 'Понедельник',
        'uz': 'Dushanba',
        'en': 'Monday'
    },
    'tuesday': {
        'ru': 'Вторник',
        'uz': 'Seshanba',
        'en': 'Tuesday'
    },
    'wednesday': {
        'ru': 'Среда',
        'uz': 'Chorshanba',
        'en': 'Wednesday'
    },
    'thursday': {
        'ru': 'Четверг',
        'uz': 'Payshanba',
        'en': 'Thursday'
    },
    'friday': {
        'ru': 'Пятница',
        'uz': 'Juma',
        'en': 'Friday'
    },
    'saturday': {
        'ru': 'Суббота',
        'uz': 'Shanba',
        'en': 'Saturday'
    },
    'sunday': {
        'ru': 'Воскресенье',
        'uz': 'Yakshanba',
        'en': 'Sunday'
    },
    
    # ==================== ТИПЫ ОБУЧЕНИЯ ====================
    'daytime': {
        'ru': 'Дневное',
        'uz': 'Kunduzgi',
        'en': 'Daytime'
    },
    'evening': {
        'ru': 'Вечернее',
        'uz': 'Kechki',
        'en': 'Evening'
    },
    'distance': {
        'ru': 'Заочное',
        'uz': 'Sirtqi',
        'en': 'Distance'
    },
}


class Localization:
    """Класс для работы с локализацией"""
    
    @staticmethod
    def get(key: str, language: str = 'ru', **kwargs) -> str:
        """
        Получить перевод по ключу
        
        Args:
            key: Ключ перевода
            language: Код языка (ru, uz, en)
            **kwargs: Параметры для форматирования строки
        
        Returns:
            Переведенная строка
        """
        try:
            if key not in TRANSLATIONS:
                logger.warning(f"Отсутствует перевод для ключа: {key}")
                return key
            
            if language not in TRANSLATIONS[key]:
                logger.warning(f"Отсутствует перевод для языка {language} и ключа {key}, используем 'ru'")
                language = 'ru'
            
            text = TRANSLATIONS[key][language]
            
            # Форматируем строку если есть параметры
            if kwargs:
                text = text.format(**kwargs)
            
            return text
            
        except Exception as e:
            logger.error(f"Ошибка получения перевода для {key}: {e}")
            return key
    
    @staticmethod
    def detect_language(telegram_user) -> str:
        """
        Определить язык пользователя по настройкам Telegram
        
        Args:
            telegram_user: Объект User из Telegram
        
        Returns:
            Код языка (ru, uz, en)
        """
        try:
            if hasattr(telegram_user, 'language_code') and telegram_user.language_code:
                lang_code = telegram_user.language_code.lower()
                
                # Маппинг языковых кодов
                if lang_code.startswith('ru'):
                    return 'ru'
                elif lang_code.startswith('uz'):
                    return 'uz'
                elif lang_code.startswith('en'):
                    return 'en'
            
            # По умолчанию русский
            return 'ru'
            
        except Exception as e:
            logger.error(f"Ошибка определения языка: {e}")
            return 'ru'
    
    @staticmethod
    def get_available_languages() -> Dict[str, str]:
        """Получить список доступных языков"""
        return {
            'ru': '🇷🇺 Русский',
            'uz': '🇺🇿 O\'zbekcha',
            'en': '🇬🇧 English'
        }
    
    @staticmethod
    def get_weekday(weekday_index: int, language: str = 'ru') -> str:
        """
        Получить название дня недели
        
        Args:
            weekday_index: Индекс дня недели (0 = Monday)
            language: Код языка
        
        Returns:
            Название дня недели
        """
        weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        if 0 <= weekday_index < len(weekdays):
            return Localization.get(weekdays[weekday_index], language)
        return ''


# Удобная функция для быстрого доступа
def _(key: str, language: str = 'ru', **kwargs) -> str:
    """Короткий алиас для Localization.get()"""
    return Localization.get(key, language, **kwargs)

