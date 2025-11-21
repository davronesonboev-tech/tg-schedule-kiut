#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для распознавания расписания из PDF через Gemini AI
"""

import os
import json
import logging
from typing import Dict, List, Optional
import google.generativeai as genai
from PIL import Image

logger = logging.getLogger(__name__)


class ScheduleParser:
    """Парсер расписания с использованием Gemini AI"""
    
    def __init__(self):
        self.api_key = os.getenv('GEMINI_API_KEY')
        self.model = None
        self.is_available = False
        
        if self.api_key:
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel('gemini-2.5-flash')
                self.is_available = True
                logger.info("✅ Gemini AI подключен и готов к работе")
            except Exception as e:
                logger.error(f"❌ Ошибка инициализации Gemini API: {e}")
                self.is_available = False
        else:
            logger.info("ℹ️ GEMINI_API_KEY не настроен. AI-распознавание недоступно.")
    
    def parse_schedule_from_image(self, image_path: str) -> Optional[Dict]:
        """
        Распознать расписание из изображения
        
        Возвращает:
        {
            "monday": [
                {"time_start": "9:00", "time_end": "9:50", "subject": "E-GOVERNMENT LAW", "room": "D-609"},
                ...
            ],
            "tuesday": [...],
            ...
        }
        """
        if not self.is_available or not self.model:
            logger.warning("⚠️ Gemini API недоступен. AI-распознавание отключено.")
            return None
        
        try:
            logger.info(f"Распознаю расписание из {image_path}")
            
            # Открываем изображение
            image = Image.open(image_path)
            
            # Промпт для Gemini
            prompt = """
Проанализируй это расписание занятий университета и верни данные в JSON формате.

СТРУКТУРА РАСПИСАНИЯ:
- Вверху: номера пар (1, 2, 3...) и их время (9:00-9:50, 10:00-10:50, 11:00-11:50, 12:00-12:50...)
- Слева: дни недели (Пн, Вт, Ср, Чт, Пт, Сб, Вс)
- В ячейках: название предмета, под ним - аудитория (например: B-609, D-702, C-LAB 601)

ИНСТРУКЦИИ:
1. Для КАЖДОЙ пары (даже если предмет занимает 2-3 пары подряд) - создай ОТДЕЛЬНУЮ запись
2. Время бери из ШАПКИ таблицы (столбец 1 = 9:00-9:50, столбец 2 = 10:00-10:50 и т.д.)
3. ОБЯЗАТЕЛЬНО указывай аудиторию (она написана ПОД названием предмета)
4. Если предмет занимает несколько пар подряд - разбей на отдельные временные слоты
5. Если в ячейке ничего нет - пропускай эту пару

ФОРМАТ ОТВЕТА (ТОЛЬКО JSON):
```json
{
  "monday": [
    {
      "time_start": "9:00",
      "time_end": "9:50",
      "subject": "E-GOVERNMENT & IT LAW",
      "room": "B-609"
    },
    {
      "time_start": "10:00",
      "time_end": "10:50",
      "subject": "E-GOVERNMENT & IT LAW",
      "room": "B-609"
    }
  ],
  "tuesday": [...],
  "wednesday": [...],
  "thursday": [...],
  "friday": [...],
  "saturday": [],
  "sunday": []
}
```

ВАЖНО:
- Каждая 50-минутная пара = отдельный объект
- Аудитория ОБЯЗАТЕЛЬНА (ищи под названием предмета)
- Время из шапки таблицы (не придумывай сам!)
- Если пары нет - не добавляй в массив
"""
            
            # Отправляем запрос к Gemini
            response = self.model.generate_content([prompt, image])
            
            # Парсим JSON из ответа
            response_text = response.text.strip()
            
            # Убираем markdown если есть
            if response_text.startswith('```json'):
                response_text = response_text.replace('```json', '').replace('```', '').strip()
            elif response_text.startswith('```'):
                response_text = response_text.replace('```', '').strip()
            
            schedule = json.loads(response_text)
            
            logger.info(f"✅ Расписание распознано успешно!")
            logger.debug(f"Распознано занятий: {sum(len(v) for v in schedule.values())}")
            
            return schedule
            
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON: {e}")
            logger.error(f"Ответ Gemini: {response_text[:500]}")
            return None
        except Exception as e:
            logger.error(f"Ошибка распознавания расписания: {e}")
            return None
    
    def parse_schedule_from_pdf(self, pdf_path: str) -> Optional[Dict]:
        """
        Распознать расписание из PDF
        Конвертирует первую страницу в изображение и распознает
        """
        try:
            from pdf_converter import PDFConverter
            
            logger.info(f"Конвертирую PDF в изображение: {pdf_path}")
            
            # Конвертируем PDF в изображения
            converter = PDFConverter()
            images = converter.pdf_to_images(pdf_path)
            
            if not images:
                logger.error("Не удалось конвертировать PDF")
                return None
            
            # Распознаем первую страницу (обычно там основное расписание)
            schedule = self.parse_schedule_from_image(images[0])
            
            # Удаляем временные изображения
            converter.cleanup_images(images)
            
            return schedule
            
        except Exception as e:
            logger.error(f"Ошибка обработки PDF: {e}")
            return None
    
    @staticmethod
    def get_day_name_russian(day_key: str) -> str:
        """Получить русское название дня"""
        days_map = {
            'monday': 'Понедельник',
            'tuesday': 'Вторник',
            'wednesday': 'Среда',
            'thursday': 'Четверг',
            'friday': 'Пятница',
            'saturday': 'Суббота',
            'sunday': 'Воскресенье'
        }
        return days_map.get(day_key, day_key)
    
    @staticmethod
    def get_day_key_from_weekday(weekday: int) -> str:
        """
        Получить ключ дня из номера дня недели
        weekday: 0 = Monday, 6 = Sunday
        """
        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        return days[weekday] if 0 <= weekday < 7 else 'monday'
    
    @staticmethod
    def format_schedule_text(schedule: Dict, day_key: str = None) -> str:
        """
        Отформатировать расписание для отображения
        Если day_key указан - только этот день, иначе все дни
        """
        if not schedule:
            return "Расписание не найдено"
        
        text = ""
        
        if day_key:
            # Только один день
            day_name = ScheduleParser.get_day_name_russian(day_key)
            classes = schedule.get(day_key, [])
            
            if not classes:
                return f"{day_name}: выходной 🎉"
            
            text = f"📅 {day_name}:\n\n"
            for cls in classes:
                time = f"{cls['time_start']}-{cls['time_end']}"
                subject = cls['subject']
                room = cls.get('room', '')
                room_text = f" (ауд. {room})" if room else ""
                text += f"🕐 {time}\n📚 {subject}{room_text}\n\n"
        else:
            # Все дни
            for day_key in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
                day_name = ScheduleParser.get_day_name_russian(day_key)
                classes = schedule.get(day_key, [])
                
                if classes:
                    text += f"\n📅 {day_name}:\n"
                    for cls in classes:
                        time = f"{cls['time_start']}-{cls['time_end']}"
                        subject = cls['subject']
                        room = cls.get('room', '')
                        room_text = f" ({room})" if room else ""
                        text += f"  • {time} - {subject}{room_text}\n"
        
        return text.strip()
