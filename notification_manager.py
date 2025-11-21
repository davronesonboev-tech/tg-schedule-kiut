#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Менеджер уведомлений о предстоящих парах
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pytz

logger = logging.getLogger(__name__)


class NotificationManager:
    """Менеджер для проверки времени пар и отправки уведомлений"""
    
    @staticmethod
    def get_current_weekday_key() -> str:
        """Получить ключ текущего дня недели"""
        from schedule_parser import ScheduleParser
        weekday = datetime.now().weekday()  # 0 = Monday
        return ScheduleParser.get_day_key_from_weekday(weekday)
    
    @staticmethod
    def parse_time(time_str: str) -> Optional[datetime]:
        """
        Парсить время из строки "9:00" в datetime объект сегодня
        """
        try:
            hour, minute = map(int, time_str.split(':'))
            now = datetime.now()
            return now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except Exception as e:
            logger.error(f"Ошибка парсинга времени '{time_str}': {e}")
            return None
    
    @staticmethod
    def get_next_class(schedule_json: str, timezone_str: str = 'Asia/Tashkent') -> Optional[Dict]:
        """
        Получить следующую пару из расписания
        
        Возвращает:
        {
            "time_start": "9:00",
            "time_end": "9:50",
            "subject": "E-GOVERNMENT LAW",
            "room": "D-609",
            "minutes_until": 45
        }
        или None если пар сегодня больше нет
        """
        try:
            schedule = json.loads(schedule_json)
            
            # Текущее время в нужном часовом поясе
            tz = pytz.timezone(timezone_str)
            now = datetime.now(tz).replace(tzinfo=None)  # Убираем tzinfo для сравнения
            
            # Получаем расписание на сегодня
            day_key = NotificationManager.get_current_weekday_key()
            today_classes = schedule.get(day_key, [])
            
            if not today_classes:
                return None  # Сегодня пар нет
            
            # Ищем ближайшую пару
            for cls in today_classes:
                class_time = NotificationManager.parse_time(cls['time_start'])
                if not class_time:
                    continue
                
                # Если пара еще не началась
                if class_time > now:
                    minutes_until = int((class_time - now).total_seconds() / 60)
                    return {
                        **cls,
                        'minutes_until': minutes_until,
                        'class_time': class_time
                    }
            
            return None  # Все пары на сегодня уже прошли
            
        except Exception as e:
            logger.error(f"Ошибка получения следующей пары: {e}")
            return None
    
    @staticmethod
    def should_send_notification(next_class: Dict, minutes_before: int) -> bool:
        """
        Проверить, нужно ли отправлять уведомление
        
        Отправляем если:
        - До пары осталось ровно N минут (±1 минута)
        """
        if not next_class:
            return False
        
        minutes_until = next_class.get('minutes_until', 0)
        
        # Проверяем диапазон: от (minutes_before) до (minutes_before + 1)
        # Это нужно чтобы не пропустить уведомление между проверками
        return minutes_before <= minutes_until <= minutes_before + 1
    
    @staticmethod
    def format_notification_message(next_class: Dict) -> str:
        """
        Сформировать текст уведомления
        """
        time = f"{next_class['time_start']}-{next_class['time_end']}"
        subject = next_class['subject']
        room = next_class.get('room', '')
        minutes = next_class['minutes_until']
        
        message = (
            f"🔔 *Напоминание о паре!*\n\n"
            f"⏰ Начало через *{minutes} мин* ({next_class['time_start']})\n"
            f"📚 *{subject}*\n"
        )
        
        if room:
            message += f"🚪 Аудитория: *{room}*\n"
        
        message += f"\n💨 Не опаздывай!"
        
        return message
    
    @staticmethod
    def format_daily_schedule(schedule_json: str, group_name: str, highlight_next: bool = True) -> str:
        """
        Форматировать расписание на день (ОДНО сообщение)
        
        Args:
            schedule_json: JSON с расписанием
            group_name: Название группы
            highlight_next: Выделить следующую пару
        
        Returns:
            Форматированное сообщение
        """
        try:
            schedule = json.loads(schedule_json)
            
            # Текущее время
            now = datetime.now()
            
            # Получаем расписание на сегодня
            day_key = NotificationManager.get_current_weekday_key()
            today_classes = schedule.get(day_key, [])
            
            if not today_classes:
                return (
                    f"📅 *Расписание на сегодня*\n"
                    f"👥 Группа: *{group_name}*\n\n"
                    f"🎉 Сегодня пар нет! Отдыхай!"
                )
            
            # Заголовок
            from datetime import datetime
            today_str = now.strftime("%d.%m.%Y")
            weekday_names = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
            weekday = weekday_names[now.weekday()]
            
            message = (
                f"📅 *Расписание на {weekday}*\n"
                f"📆 {today_str}\n"
                f"👥 Группа: *{group_name}*\n\n"
            )
            
            # Ищем следующую пару
            next_class_index = None
            if highlight_next:
                for idx, cls in enumerate(today_classes):
                    class_time = NotificationManager.parse_time(cls['time_start'])
                    if class_time and class_time > now:
                        next_class_index = idx
                        break
            
            # Форматируем каждую пару
            for idx, cls in enumerate(today_classes):
                time = f"{cls['time_start']}-{cls['time_end']}"
                subject = cls['subject']
                room = cls.get('room', '')
                
                # Проверяем прошла ли пара
                class_time = NotificationManager.parse_time(cls['time_start'])
                is_past = class_time and class_time < now
                is_next = idx == next_class_index
                
                if is_past:
                    # Зачеркнутая пройденная пара
                    message += f"~~{time}~~ ✅\n"
                    message += f"~~{subject}~~\n"
                    if room:
                        message += f"~~{room}~~\n"
                elif is_next:
                    # Следующая пара (выделено)
                    minutes_until = int((class_time - now).total_seconds() / 60)
                    message += f"🔔 *{time}* (через {minutes_until} мин)\n"
                    message += f"📚 *{subject}*\n"
                    if room:
                        message += f"🚪 {room}\n"
                else:
                    # Будущие пары
                    message += f"{time}\n"
                    message += f"📖 {subject}\n"
                    if room:
                        message += f"🚪 {room}\n"
                
                message += "\n"
            
            # Футер
            if next_class_index is not None:
                message += "💡 _Сообщение обновляется автоматически_"
            else:
                message += "✅ _Все пары на сегодня завершены!_"
            
            return message
            
        except Exception as e:
            logger.error(f"Ошибка форматирования ежедневного расписания: {e}")
            return f"❌ Ошибка отображения расписания"

