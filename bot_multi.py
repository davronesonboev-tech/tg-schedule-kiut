# -*- coding: utf-8 -*-
"""
Telegram Bot для автоматической отправки расписания
Версия 3.0 - Multi-user, Multi-group
Автор: Your Team
"""

import os
import json
import logging
import asyncio
from datetime import datetime
from typing import Dict
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from database import Database
from multi_drive_monitor import MultiDriveMonitor
from pdf_converter import PDFConverter
from folder_structure import EDUCATION_TYPES, COURSES, COURSE_DISPLAY, GROUP_PATTERNS, get_friendly_name
from drive_scanner import DriveScanner
from schedule_parser import ScheduleParser
from notification_manager import NotificationManager

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(
    format=log_format,
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Конфигурация
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Состояния для визарда регистрации
(SELECT_EDUCATION, SELECT_COURSE, SELECT_GROUP_LIST, SELECT_GROUP_PAGE,
 SELECT_FORMAT, WAITING_CUSTOM_FILE, CONFIRM_CHOICE) = range(7)


class MultiScheduleBot:
    """Главный класс бота для работы с расписаниями"""
    
    def __init__(self):
        self.app = None
        self.db = Database()
        self.drive = MultiDriveMonitor()
        self.scanner = DriveScanner()  # Сканер для автозагрузки групп
        self.converter = PDFConverter()
        self.parser = ScheduleParser()  # Парсер расписания через Gemini AI
        self.check_jobs = {}  # Храним задачи проверки для каждого файла
        self.file_versions = {}  # Храним версии файлов {filename: modified_time}
        self.GROUPS_PER_PAGE = 5  # Количество групп на странице
        self.failed_checks = {}  # Счетчик неудачных проверок {file_key: count}
        self.max_check_retries = 3  # Максимум попыток проверки файла
        self.groups_cache = {}  # Кеш списка групп {education_course: data}
        self.cache_timestamps = {}  # Временные метки кеша
        self.cache_ttl = 1800  # 30 минут
    
    # ==================== УМНЫЙ ПОИСК ====================
    
    def normalize_group_code(self, input_text: str) -> str:
        """Нормализация ввода: ise74r -> ISE-74R"""
        text = input_text.strip().upper().replace(' ', '').replace('_', '-')
        
        # Если нет дефиса, пытаемся добавить его автоматически
        if '-' not in text:
            # Ищем место для дефиса (после букв, перед цифрами)
            import re
            match = re.match(r'^([A-Z]+)(\d+[A-Z]*)$', text)
            if match:
                text = f"{match.group(1)}-{match.group(2)}"
        
        return text
    
    def calculate_similarity(self, str1: str, str2: str) -> float:
        """Простой расчет схожести строк (Levenshtein distance)"""
        if str1 == str2:
            return 1.0
        
        len1, len2 = len(str1), len(str2)
        if len1 == 0 or len2 == 0:
            return 0.0
        
        # Матрица расстояний
        matrix = [[0] * (len2 + 1) for _ in range(len1 + 1)]
        
        for i in range(len1 + 1):
            matrix[i][0] = i
        for j in range(len2 + 1):
            matrix[0][j] = j
        
        for i in range(1, len1 + 1):
            for j in range(1, len2 + 1):
                cost = 0 if str1[i-1] == str2[j-1] else 1
                matrix[i][j] = min(
                    matrix[i-1][j] + 1,      # deletion
                    matrix[i][j-1] + 1,      # insertion
                    matrix[i-1][j-1] + cost  # substitution
                )
        
        distance = matrix[len1][len2]
        max_len = max(len1, len2)
        return 1.0 - (distance / max_len)
    
    async def get_groups_cached(self, education_type: str, course: str) -> list:
        """Получить список групп с кешированием"""
        import time
        
        cache_key = f"{education_type}_{course}"
        current_time = time.time()
        
        # Проверяем кеш
        if cache_key in self.groups_cache:
            cache_age = current_time - self.cache_timestamps.get(cache_key, 0)
            if cache_age < self.cache_ttl:
                logger.debug(f"🗄️ Используем кеш для {cache_key} (возраст: {cache_age:.0f}с)")
                return self.groups_cache[cache_key]
        
        # Загружаем из Drive
        logger.info(f"🌐 Загружаем список групп для {cache_key}...")
        all_groups = await asyncio.to_thread(
            self.scanner.get_all_groups,
            education_type,
            course
        )
        
        # Сохраняем в кеш
        self.groups_cache[cache_key] = all_groups
        self.cache_timestamps[cache_key] = current_time
        
        return all_groups
    
    async def smart_search_group(self, query_text: str, education_type: str, course: str):
        """
        Умный поиск группы с нормализацией и fuzzy matching
        Возвращает: (exact_match: str|None, similar_matches: list, all_groups: dict)
        """
        normalized_query = self.normalize_group_code(query_text)
        
        # Получаем все группы с кешированием
        all_groups = await self.get_groups_cached(education_type, course)
        
        if not all_groups:
            return None, [], {}
        
        # Ищем точное совпадение
        for filename in all_groups:
            group_code = filename.replace('.pdf', '')
            if group_code == normalized_query:
                return filename, [], self.scanner.group_by_direction(all_groups)
        
        # Ищем похожие группы (fuzzy matching)
        similar = []
        for filename in all_groups:
            group_code = filename.replace('.pdf', '')
            similarity = self.calculate_similarity(normalized_query, group_code)
            
            if similarity >= 0.6:  # Порог схожести 60%
                similar.append((filename, similarity, group_code))
        
        # Сортируем по убыванию схожести
        similar.sort(key=lambda x: x[1], reverse=True)
        
        return None, similar, self.scanner.group_by_direction(all_groups)
    
    # ==================== ГЛАВНОЕ МЕНЮ ====================
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Главное меню бота"""
        user_id = update.effective_user.id
        user_data = self.db.get_user(user_id)
        is_admin = self.db.is_admin(user_id)
        
        keyboard = []
        
        if user_data:
            # Пользователь зарегистрирован
            education = user_data.get('education_type')
            course = user_data.get('course')
            group = user_data.get('group')
            
            keyboard.append([InlineKeyboardButton("📥 Получить расписание", callback_data="get_my_schedule")])
            keyboard.append([InlineKeyboardButton("📋 Моё расписание", callback_data="view_my_schedule")])
            keyboard.append([InlineKeyboardButton("ℹ️ Моя группа", callback_data="show_my_info")])
            
            # Кнопка уведомлений
            notif_settings = self.db.get_notification_settings(user_id)
            if notif_settings and notif_settings['enabled']:
                notif_button = "🔔 Уведомления (вкл)"
            else:
                notif_button = "🔕 Уведомления (выкл)"
            keyboard.append([InlineKeyboardButton(notif_button, callback_data="toggle_notifications")])
            
            keyboard.append([InlineKeyboardButton("⚙️ Изменить настройки", callback_data="start_setup")])
        else:
            # Новый пользователь
            keyboard.append([InlineKeyboardButton("🎓 Начать настройку", callback_data="start_setup")])
        
        keyboard.append([InlineKeyboardButton("❓ Помощь", callback_data="help")])
        
        if is_admin:
            keyboard.append([InlineKeyboardButton("👑 Админ-панель", callback_data="admin_panel")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            "👋 *Привет! Я бот для автоматической отправки расписания*\n\n"
            "🎯 Что я умею:\n"
            "• Автоматически отслеживаю обновления расписания\n"
            "• Отправляю расписание в вашу группу\n"
            "• Работаю со всеми направлениями и курсами\n"
            "• Могу отправлять в PDF или фото\n\n"
        )
        
        if user_data:
            edu_name = EDUCATION_TYPES.get(user_data['education_type'], {}).get('name', 'Неизвестно')
            text += f"📚 Ваша группа: *{user_data['group']}*\n"
            text += f"🏫 Форма обучения: {edu_name}\n"
            text += f"📖 Курс: {user_data['course']}\n"
        else:
            text += "⚠️ _Вы еще не настроили бота. Нажмите 'Начать настройку'_"
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
    
    # ==================== ВИЗАРД НАСТРОЙКИ ====================
    
    async def start_setup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало визарда настройки"""
        query = update.callback_query
        if query:
            await query.answer()
        
        keyboard = []
        for key, info in EDUCATION_TYPES.items():
            keyboard.append([InlineKeyboardButton(
                info['name'],
                callback_data=f"edu_{key}"
            )])
        
        keyboard.append([InlineKeyboardButton("« Отмена", callback_data="cancel_setup")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            "🎓 *ШАГ 1 из 5: Выберите форму обучения*\n\n"
            "Выберите вашу форму обучения:\n"
            "🏫 Очное - дневное обучение\n"
            "🌙 Вечернее - вечерние занятия\n"
            "📮 Заочное - заочное обучение\n"
            "🎓 Магистратура - магистерская программа"
        )
        
        if query:
            await query.edit_message_text(
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        
        return SELECT_EDUCATION
    
    async def select_education(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Выбор формы обучения"""
        query = update.callback_query
        await query.answer()
        
        education_type = query.data.replace('edu_', '')
        context.user_data['education_type'] = education_type
        
        # Выбор курса
        keyboard = []
        for course_num in sorted(COURSES.keys()):
            course_display = COURSE_DISPLAY.get(course_num, f"{course_num} курс")
            keyboard.append([InlineKeyboardButton(
                course_display,
                callback_data=f"course_{course_num}"
            )])
        
        keyboard.append([InlineKeyboardButton("« Назад", callback_data="start_setup")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        edu_name = EDUCATION_TYPES[education_type]['name']
        text = (
            f"✅ Выбрано: *{edu_name}*\n\n"
            f"📚 *ШАГ 2 из 5: Выберите курс*\n\n"
            f"На каком вы курсе?"
        )
        
        await query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        return SELECT_COURSE
    
    async def select_course(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Выбор курса"""
        query = update.callback_query
        await query.answer("⏳ Загружаю список групп...")
        
        course = query.data.replace('course_', '')
        context.user_data['course'] = course
        
        # Загружаем все группы для этого курса
        education_type = context.user_data['education_type']
        
        await query.edit_message_text(
            "⏳ Загружаю список доступных групп с Google Drive...\n"
            "Пожалуйста, подождите..."
        )
        
        try:
            # Получаем все группы с кешированием
            all_groups = await self.get_groups_cached(education_type, course)
            
            if not all_groups:
                await query.edit_message_text(
                    f"❌ К сожалению, для {course} курса пока нет расписаний.\n"
                    f"Попробуйте выбрать другой курс.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("« Назад", callback_data=f"edu_{education_type}")
                    ]])
                )
                return SELECT_COURSE
            
            # Группируем по направлениям
            grouped = self.scanner.group_by_direction(all_groups)
            context.user_data['all_groups'] = grouped
            context.user_data['group_page'] = 0
            
            # Показываем список направлений
            return await self.show_directions_list(query, context, grouped)
            
        except Exception as e:
            logger.error(f"Ошибка загрузки групп: {e}")
            await query.edit_message_text(
                f"❌ Ошибка загрузки групп: {str(e)}\n"
                f"Попробуйте еще раз или введите код группы вручную.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data=f"edu_{education_type}")
                ]])
            )
            return SELECT_COURSE
    
    async def show_directions_list(self, query, context, grouped: Dict):
        """Показать список направлений (компактный вид)"""
        course = context.user_data['course']
        course_display = COURSE_DISPLAY.get(course, f"{course} курс")
        
        # Создаем кнопки по направлениям (по 2 в ряд)
        keyboard = []
        sorted_directions = sorted(grouped.keys())
        
        row = []
        for direction in sorted_directions:
            count = len(grouped[direction])
            # Компактный формат: только код и количество
            row.append(InlineKeyboardButton(
                f"{direction} ({count})",
                callback_data=f"showdir_{direction}"
            ))
            
            if len(row) == 2:
                keyboard.append(row)
                row = []
        
        # Добавляем последний неполный ряд
        if row:
            keyboard.append(row)
        
        # Кнопки управления
        keyboard.append([InlineKeyboardButton("🔍 Поиск по коду группы", callback_data="custom_group")])
        keyboard.append([InlineKeyboardButton("« Назад к курсам", callback_data=f"edu_{context.user_data['education_type']}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        total_groups = sum(len(v) for v in grouped.values())
        
        text = (
            f"📖 *{course_display}*\n\n"
            f"📚 *ШАГ 3 из 4: Выберите направление*\n\n"
            f"🎯 Найдено: *{len(sorted_directions)}* направлений | *{total_groups}* групп\n\n"
            f"💡 Нажмите на код направления или воспользуйтесь поиском:"
        )
        
        await query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        return SELECT_GROUP_LIST
    
    async def select_direction(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать группы выбранного направления"""
        query = update.callback_query
        await query.answer()
        
        direction = query.data.replace('showdir_', '')
        context.user_data['selected_direction'] = direction
        context.user_data['group_page'] = 0
        
        # Показываем группы этого направления
        return await self.show_groups_page(query, context, direction, page=0)
    
    async def show_groups_page(self, query, context, direction: str, page: int = 0):
        """Показать страницу с группами (улучшенный дизайн)"""
        grouped = context.user_data.get('all_groups', {})
        groups = grouped.get(direction, [])
        
        if not groups:
            await query.edit_message_text(
                "❌ Группы не найдены",
                reply_markup=self._main_menu_keyboard()
            )
            return ConversationHandler.END
        
        # Пагинация
        total_groups = len(groups)
        total_pages = (total_groups + self.GROUPS_PER_PAGE - 1) // self.GROUPS_PER_PAGE
        start_idx = page * self.GROUPS_PER_PAGE
        end_idx = min(start_idx + self.GROUPS_PER_PAGE, total_groups)
        
        groups_on_page = groups[start_idx:end_idx]
        
        # Создаем кнопки
        keyboard = []
        
        # Кнопки с группами (по 2 в ряд)
        row = []
        for i, filename in enumerate(groups_on_page):
            group_code = filename.replace('.pdf', '')
            row.append(InlineKeyboardButton(
                f"{group_code}",
                callback_data=f"selgroup_{filename}"
            ))
            if (i + 1) % 2 == 0:
                keyboard.append(row)
                row = []
        
        if row:
            keyboard.append(row)
        
        # Навигация по страницам
        if total_pages > 1:
            nav_row = []
            if page > 0:
                nav_row.append(InlineKeyboardButton(
                    "⬅️",
                    callback_data=f"grouppage_{direction}_{page-1}"
                ))
            
            nav_row.append(InlineKeyboardButton(
                f"• {page+1}/{total_pages} •",
                callback_data="noop"
            ))
            
            if page < total_pages - 1:
                nav_row.append(InlineKeyboardButton(
                    "➡️",
                    callback_data=f"grouppage_{direction}_{page+1}"
                ))
            
            keyboard.append(nav_row)
        
        # Кнопки управления
        keyboard.append([InlineKeyboardButton("🔍 Поиск по коду", callback_data="custom_group")])
        keyboard.append([InlineKeyboardButton("« К направлениям", callback_data=f"course_{context.user_data['course']}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        direction_name = GROUP_PATTERNS.get(direction, direction)
        course_display = COURSE_DISPLAY.get(context.user_data['course'], "")
        
        # Показываем номера групп на текущей странице
        groups_display = ", ".join([g.replace('.pdf', '') for g in groups_on_page])
        
        text = (
            f"📖 *{course_display}*\n"
            f"📚 {direction} - _{direction_name}_\n\n"
            f"👥 *ШАГ 4 из 4: Выберите группу*\n\n"
            f"📊 Страница *{page+1}* из *{total_pages}* | Всего: *{total_groups}* групп\n\n"
            f"Группы на странице:\n"
            f"`{groups_display}`\n\n"
            f"💡 Нажмите на группу или используйте поиск"
        )
        
        await query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        return SELECT_GROUP_PAGE
    
    async def navigate_group_page(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Навигация по страницам групп"""
        query = update.callback_query
        await query.answer()
        
        # Парсим: grouppage_DIRECTION_PAGE
        parts = query.data.split('_')
        direction = parts[1]
        page = int(parts[2])
        
        context.user_data['group_page'] = page
        
        return await self.show_groups_page(query, context, direction, page)
    
    async def select_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Выбор группы из списка"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "custom_group":
            # Пользователь хочет ввести вручную
            await query.edit_message_text(
                "🔍 *УМНЫЙ ПОИСК ГРУППЫ*\n\n"
                "💡 *Просто введите код вашей группы*\n"
                "Я сам найду её, даже если вы:\n"
                "• Забыли дефис (ise74r → ISE-74R)\n"
                "• Ошиблись в букве (ise74ra → ISE-74R 85%)\n"
                "• Написали в другом регистре\n\n"
                "📝 *Примеры:*\n"
                "`ise74r` `ACC71U` `bma-75r`\n\n"
                "✍️ Введите код группы или /cancel для отмены:",
                parse_mode='Markdown'
            )
            return WAITING_CUSTOM_FILE
        
        # Выбрана группа из списка
        filename = query.data.replace('selgroup_', '')
        group_code = filename.replace('.pdf', '')
        
        # Извлекаем direction из кода группы (первая часть до дефиса)
        if '-' in group_code:
            direction = group_code.split('-')[0]
            context.user_data['direction'] = direction
        
        context.user_data['group'] = group_code
        context.user_data['filename'] = filename
        
        # Выбор формата
        return await self.select_format_step(update, context)
    
    async def custom_group_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ввод группы вручную с умным поиском"""
        user_input = update.message.text.strip()
        
        education_type = context.user_data.get('education_type')
        course = context.user_data.get('course')
        
        if not education_type or not course:
            await update.message.reply_text(
                "❌ Ошибка! Пожалуйста, начните настройку заново с помощью /start"
            )
            return ConversationHandler.END
        
        # Показываем загрузку
        loading_msg = await update.message.reply_text("🔍 Ищу вашу группу...")
        
        try:
            # Умный поиск
            exact_match, similar_matches, all_groups = await self.smart_search_group(
                user_input, education_type, course
            )
            
            if exact_match:
                # Найдено точное совпадение!
                group_code = exact_match.replace('.pdf', '')
                normalized = self.normalize_group_code(user_input)
                
                # Извлекаем direction из кода группы
                if '-' in group_code:
                    direction = group_code.split('-')[0]
                    context.user_data['direction'] = direction
                
                context.user_data['group'] = group_code
                context.user_data['filename'] = exact_match
                
                success_text = f"✅ *Группа найдена!*\n\n"
                if normalized != group_code:
                    success_text += f"Вы ввели: `{user_input}`\n"
                    success_text += f"Найдено: *{group_code}*\n\n"
                else:
                    success_text += f"Группа: *{group_code}*\n\n"
                
                success_text += "Переходим к выбору формата..."
                
                await loading_msg.edit_text(success_text, parse_mode='Markdown')
                await asyncio.sleep(1)
                
                # Переход к выбору формата
                return await self.select_format_step(update, context)
            
            elif similar_matches:
                # Найдены похожие группы
                keyboard = []
                
                # Показываем топ-5 похожих
                for filename, similarity, group_code in similar_matches[:5]:
                    percentage = int(similarity * 100)
                    keyboard.append([InlineKeyboardButton(
                        f"📋 {group_code} ({percentage}% схожесть)",
                        callback_data=f"selgroup_{filename}"
                    )])
                
                keyboard.append([InlineKeyboardButton("🔄 Попробовать снова", callback_data="custom_group")])
                keyboard.append([InlineKeyboardButton("« К списку", callback_data=f"course_{course}")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                text = (
                    f"🤔 *Точного совпадения не найдено*\n\n"
                    f"Вы искали: `{user_input}`\n"
                    f"Нормализовано: `{self.normalize_group_code(user_input)}`\n\n"
                    f"💡 *Возможно, вы имели в виду:*"
                )
                
                await loading_msg.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')
                return SELECT_GROUP_PAGE
            
            else:
                # Ничего не найдено
                keyboard = [
                    [InlineKeyboardButton("🔄 Попробовать снова", callback_data="custom_group")],
                    [InlineKeyboardButton("« К списку групп", callback_data=f"course_{course}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                text = (
                    f"❌ *Группа не найдена*\n\n"
                    f"Вы искали: `{user_input}`\n"
                    f"Нормализовано: `{self.normalize_group_code(user_input)}`\n\n"
                    f"К сожалению, такой группы нет в базе.\n"
                    f"Попробуйте:\n"
                    f"• Проверить правильность кода\n"
                    f"• Выбрать из списка всех групп\n"
                    f"• Связаться с администратором"
                )
                
                await loading_msg.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')
                return SELECT_GROUP_PAGE
        
        except Exception as e:
            logger.error(f"Ошибка умного поиска: {e}")
            await loading_msg.edit_text(
                f"❌ Ошибка поиска: {str(e)}\n\n"
                f"Попробуйте снова или выберите из списка.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data=f"course_{course}")
                ]])
            )
            return SELECT_GROUP_PAGE
    
    async def select_format_step(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Выбор формата отправки"""
        # Кнопка "Назад" возвращает к выбору курса
        course = context.user_data.get('course', '1')
        education_type = context.user_data.get('education_type', 'daytime')
        
        keyboard = [
            [
                InlineKeyboardButton("📷 Фото (удобнее)", callback_data="format_photo"),
                InlineKeyboardButton("📄 PDF", callback_data="format_pdf")
            ],
            [InlineKeyboardButton("« Назад к выбору группы", callback_data=f"course_{course}")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        group = context.user_data['group']
        text = (
            f"✅ Группа: *{group}*\n\n"
            f"📤 *ШАГ 5 из 5: Выберите формат отправки*\n\n"
            f"В каком формате отправлять расписание?\n\n"
            f"📷 *Фото* - более удобно смотреть в телефоне\n"
            f"📄 *PDF* - можно сохранить файл"
        )
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        
        return SELECT_FORMAT
    
    async def select_format(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Завершение настройки"""
        query = update.callback_query
        await query.answer()
        
        format_type = query.data.replace('format_', '')
        
        # Сохраняем пользователя
        user_id = update.effective_user.id
        group = context.user_data['group']
        
        self.db.save_user(
            user_id=user_id,
            education_type=context.user_data['education_type'],
            course=context.user_data['course'],
            group=group,
            format_type=format_type
        )
        
        # Логируем регистрацию
        self.db.log_action(user_id, 'registered', f'Группа: {group}, Формат: {format_type}')
        
        # Уведомляем админов о новом пользователе
        await self._notify_admin_new_user(user_id, group)
        
        keyboard = [
            [InlineKeyboardButton("📥 Получить расписание", callback_data="get_my_schedule")],
            [InlineKeyboardButton("« Главное меню", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        edu_name = EDUCATION_TYPES[context.user_data['education_type']]['name']
        format_icon = "📷" if format_type == "photo" else "📄"
        
        text = (
            "✅ *Настройка завершена!*\n\n"
            "📋 *Ваши настройки:*\n"
            f"🏫 Форма: {edu_name}\n"
            f"📖 Курс: {context.user_data['course']}\n"
            f"👥 Группа: *{context.user_data['group']}*\n"
            f"📤 Формат: {format_icon} {format_type.upper()}\n"
            f"📁 Файл: `{context.user_data['filename']}`\n\n"
            "🎉 Теперь вы можете:\n"
            "• Получать расписание по команде\n"
            "• Добавить меня в группу для автоотправки\n\n"
            "💡 *Как добавить в группу:*\n"
            "1. Добавьте меня в вашу учебную группу\n"
            "2. Сделайте меня администратором\n"
            "3. Используйте /setupgroup в группе\n"
            "4. Я буду автоматически отправлять обновления!"
        )
        
        await query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        # Очищаем временные данные
        context.user_data.clear()
        
        return ConversationHandler.END
    
    # ==================== ПОЛУЧЕНИЕ РАСПИСАНИЯ ====================
    
    async def get_my_schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение расписания пользователя"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        user_data = self.db.get_user(user_id)
        
        if not user_data:
            await query.edit_message_text(
                "❌ Вы еще не настроили бота.\n"
                "Используйте /start для настройки.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🎓 Начать настройку", callback_data="start_setup")
                ]])
            )
            return
        
        await query.edit_message_text("⏳ Загружаю ваше расписание...")
        
        try:
            # Формируем имя файла
            filename = f"{user_data['group']}.pdf"
            
            # Загружаем файл
            file_path, file_info = await asyncio.to_thread(
                self.drive.download_file,
                user_data['education_type'],
                filename,
                user_data['course']  # Передаем курс для правильного поиска
            )
            
            if not file_path or not os.path.exists(file_path):
                await query.message.reply_text(
                    f"❌ Файл {filename} не найден на Google Drive.\n"
                    f"Проверьте правильность названия группы.",
                    reply_markup=self._main_menu_keyboard()
                )
                return
            
            # Отправляем в нужном формате
            if user_data['format'] == 'photo':
                await self._send_as_photo(query.message, file_path, user_data, file_info)
            else:
                await self._send_as_pdf(query.message, file_path, user_data, file_info)
            
            # Удаляем временный файл
            os.remove(file_path)
            
            # Логируем получение расписания
            self.db.log_action(user_id, 'get_schedule', f'Группа: {user_data["group"]}')
            
            await query.message.reply_text(
                "✅ Готово!",
                reply_markup=self._main_menu_keyboard()
            )
            
        except Exception as e:
            logger.error(f"Ошибка получения расписания: {e}")
            await query.message.reply_text(
                f"❌ Ошибка: {str(e)}",
                reply_markup=self._main_menu_keyboard()
            )
    
    async def _send_as_photo(self, message, file_path: str, user_data: dict, file_info: dict):
        """Отправка расписания как фото"""
        try:
            # Конвертируем PDF в изображения
            image_paths = await asyncio.to_thread(
                self.converter.pdf_to_images,
                file_path
            )
            
            if not image_paths:
                # Если не удалось конвертировать, отправляем PDF
                await self._send_as_pdf(message, file_path, user_data, file_info)
                return
            
            caption = (
                f"📅 Расписание группы {user_data['group']}\n"
                f"📆 Обновлено: {file_info.get('modified_time', 'Неизвестно')}"
            )
            
            # Отправляем как медиа-группу (альбом)
            if len(image_paths) == 1:
                with open(image_paths[0], 'rb') as photo:
                    await message.reply_photo(
                        photo=photo,
                        caption=caption
                    )
            else:
                media_group = []
                for i, img_path in enumerate(image_paths):
                    with open(img_path, 'rb') as photo:
                        media = InputMediaPhoto(
                            media=photo,
                            caption=caption if i == 0 else None
                        )
                        media_group.append(media)
                
                await message.reply_media_group(media=media_group)
            
            # Удаляем временные изображения
            self.converter.cleanup_images(image_paths)
            
        except Exception as e:
            logger.error(f"Ошибка отправки как фото: {e}")
            # Отправляем PDF в случае ошибки
            await self._send_as_pdf(message, file_path, user_data, file_info)
    
    async def _send_as_pdf(self, message, file_path: str, user_data: dict, file_info: dict):
        """Отправка расписания как PDF"""
        try:
            with open(file_path, 'rb') as pdf:
                caption = (
                    f"📅 Расписание группы {user_data['group']}\n"
                    f"📆 Обновлено: {file_info.get('modified_time', 'Неизвестно')}"
                )
                await message.reply_document(
                    document=pdf,
                    filename=f"{user_data['group']}.pdf",
                    caption=caption
                )
        except Exception as e:
            logger.error(f"Ошибка отправки PDF: {e}")
            raise
    
    # ==================== НАСТРОЙКА ГРУППЫ ====================
    
    async def setup_group_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Настройка группы для автоотправки"""
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        
        # Проверяем что это группа
        if update.effective_chat.type == 'private':
            await update.message.reply_text(
                "❌ Эту команду нужно использовать в группе, а не в личке!\n\n"
                "💡 Добавьте меня в вашу учебную группу и используйте /setupgroup там."
            )
            return
        
        user_data = self.db.get_user(user_id)
        
        if not user_data:
            await update.message.reply_text(
                "❌ Сначала настройте бота в личке!\n"
                "Отправьте мне /start в личных сообщениях."
            )
            return
        
        # Сохраняем настройки группы на основе пользователя
        filename = f"{user_data['group']}.pdf"
        self.db.save_chat(
            chat_id=chat_id,
            education_type=user_data['education_type'],
            course=user_data['course'],
            group=user_data['group'],
            file_name=filename,
            format_type=user_data['format']
        )
        
        edu_name = EDUCATION_TYPES[user_data['education_type']]['name']
        format_icon = "📷" if user_data['format'] == "photo" else "📄"
        
        await update.message.reply_text(
            "✅ *Группа настроена!*\n\n"
            "📋 *Настройки группы:*\n"
            f"🏫 {edu_name}\n"
            f"📖 Курс: {user_data['course']}\n"
            f"👥 Группа: *{user_data['group']}*\n"
            f"📤 Формат: {format_icon}\n"
            f"📁 Файл: `{filename}`\n\n"
            "🤖 Теперь я буду автоматически присылать обновления расписания в эту группу!",
            parse_mode='Markdown'
        )
    
    # ==================== ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ ====================
    
    async def show_my_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать информацию о настройках пользователя"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        user_data = self.db.get_user(user_id)
        
        if not user_data:
            await query.edit_message_text(
                "❌ Данные не найдены",
                reply_markup=self._main_menu_keyboard()
            )
            return
        
        edu_name = EDUCATION_TYPES[user_data['education_type']]['name']
        format_icon = "📷" if user_data['format'] == "photo" else "📄"
        filename = f"{user_data['group']}.pdf"
        
        keyboard = [
            [InlineKeyboardButton("📥 Получить расписание", callback_data="get_my_schedule")],
            [InlineKeyboardButton("⚙️ Изменить настройки", callback_data="start_setup")],
            [InlineKeyboardButton("« Главное меню", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            "ℹ️ *Ваши настройки*\n\n"
            f"🏫 Форма обучения: {edu_name}\n"
            f"📖 Курс: {user_data['course']}\n"
            f"👥 Группа: *{user_data['group']}*\n"
            f"📤 Формат: {format_icon} {user_data['format'].upper()}\n"
            f"📁 Файл: `{filename}`\n\n"
            "💡 Чтобы добавить в группу:\n"
            "1. Добавьте меня в группу\n"
            "2. Сделайте администратором\n"
            "3. Используйте /setupgroup"
        )
        
        await query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    # ==================== РАСПИСАНИЕ И УВЕДОМЛЕНИЯ ====================
    
    async def view_my_schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Просмотр распознанного расписания"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        user_data = self.db.get_user(user_id)
        
        if not user_data:
            await query.edit_message_text(
                "❌ Сначала настройте бота через /start",
                reply_markup=self._main_menu_keyboard()
            )
            return
        
        group = user_data['group']
        
        # Проверяем есть ли расписание
        schedule_json = self.db.get_schedule(group)
        
        if not schedule_json:
            # Расписания нет, предлагаем распознать
            keyboard = [
                [InlineKeyboardButton("🤖 Распознать расписание", callback_data="parse_schedule")],
                [InlineKeyboardButton("« Главное меню", callback_data="back_to_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"📋 *Расписание для группы {group}*\n\n"
                f"Расписание еще не распознано.\n\n"
                f"Нажмите кнопку ниже, чтобы я распознал ваше расписание через AI!",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return
        
        # Расписание есть, показываем
        schedule_age = self.db.get_schedule_age(group)
        schedule_text = self.parser.format_schedule_text(json.loads(schedule_json))
        
        keyboard = [
            [InlineKeyboardButton("🔄 Обновить расписание", callback_data="parse_schedule")],
            [InlineKeyboardButton("« Главное меню", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"📋 *Расписание группы {group}*\n"
            f"🕐 Обновлено {schedule_age}ч назад\n\n"
            f"{schedule_text}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def parse_schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Распознать расписание через Gemini AI"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        user_data = self.db.get_user(user_id)
        
        if not user_data:
            return
        
        group = user_data['group']
        filename = f"{group}.pdf"
        
        await query.edit_message_text(
            f"🤖 Распознаю расписание для группы {group}...\n\n"
            f"Это может занять 10-20 секунд...",
            parse_mode='Markdown'
        )
        
        try:
            # Скачиваем файл
            file_path, file_info = await asyncio.to_thread(
                self.drive.download_file,
                user_data['education_type'],
                filename,
                user_data['course']
            )
            
            if not file_path:
                await query.message.reply_text(
                    f"❌ Не удалось скачать файл расписания.\n"
                    f"Проверьте что файл {filename} существует на Drive.",
                    reply_markup=self._main_menu_keyboard()
                )
                return
            
            # Распознаем через Gemini AI
            schedule = await asyncio.to_thread(
                self.parser.parse_schedule_from_pdf,
                file_path
            )
            
            # Удаляем временный файл
            os.remove(file_path)
            
            if not schedule:
                await query.message.reply_text(
                    f"❌ Не удалось распознать расписание.\n"
                    f"Попробуйте еще раз позже или обратитесь к админу.",
                    reply_markup=self._main_menu_keyboard()
                )
                return
            
            # Сохраняем в БД
            schedule_json = json.dumps(schedule, ensure_ascii=False)
            self.db.save_schedule(group, schedule_json)
            
            # Логируем
            self.db.log_action(user_id, 'parse_schedule', f'Группа: {group}')
            
            # Показываем результат
            schedule_text = self.parser.format_schedule_text(schedule)
            
            keyboard = [[InlineKeyboardButton("« Главное меню", callback_data="back_to_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.reply_text(
                f"✅ *Расписание успешно распознано!*\n\n"
                f"{schedule_text[:1000]}...",  # Ограничиваем длину
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Ошибка распознавания расписания: {e}")
            await query.message.reply_text(
                f"❌ Ошибка: {str(e)}",
                reply_markup=self._main_menu_keyboard()
            )
    
    async def toggle_notifications(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Переключить уведомления о парах"""
        query = update.callback_query
        user_id = update.effective_user.id
        
        # Переключаем
        new_state = self.db.toggle_notifications(user_id)
        
        if new_state:
            text = (
                "🔔 *Уведомления включены!*\n\n"
                "Я буду напоминать о предстоящих парах за 10 минут до начала.\n\n"
                "💡 Убедитесь что ваше расписание распознано (кнопка \"Моё расписание\")."
            )
            await query.answer("✅ Уведомления включены!", show_alert=False)
        else:
            text = (
                "🔕 *Уведомления выключены*\n\n"
                "Я больше не буду напоминать о парах.\n"
                "Вы можете включить их снова в любой момент."
            )
            await query.answer("✅ Уведомления выключены", show_alert=False)
        
        keyboard = [[InlineKeyboardButton("« Главное меню", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    # ==================== ПОМОЩЬ ====================
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Помощь"""
        query = update.callback_query
        if query:
            await query.answer()
        
        text = (
            "❓ *ПОМОЩЬ*\n\n"
            "*Что умеет бот:*\n"
            "• Автоматически следит за обновлениями расписания\n"
            "• Отправляет расписание в группу при обновлении\n"
            "• Распознаёт расписание через AI (Gemini)\n"
            "• Напоминает о предстоящих парах\n"
            "• Работает со всеми направлениями и курсами\n"
            "• Может отправлять PDF или фото\n\n"
            "*Первая настройка:*\n"
            "1. /start → Начать настройку\n"
            "2. Выберите форму обучения\n"
            "3. Выберите курс\n"
            "4. Выберите направление\n"
            "5. Выберите группу\n"
            "6. Выберите формат (PDF/фото)\n\n"
            "*Уведомления о парах:*\n"
            "1. Нажмите \"📋 Моё расписание\"\n"
            "2. Распознайте расписание через AI\n"
            "3. Включите уведомления в главном меню\n"
            "4. Бот пришлёт напоминание за 10 минут до пары\n\n"
            "*Добавление в группу:*\n"
            "1. Добавьте бота в вашу учебную группу\n"
            "2. Сделайте его администратором\n"
            "3. В группе: /setupgroup\n"
            "4. Готово! Бот будет присылать обновления\n\n"
            "*Команды:*\n"
            "/start - Главное меню\n"
            "/setupgroup - Настроить группу (в группе)\n"
            "/getchatid - Узнать ID чата\n\n"
            "*Проблемы?*\n"
            "Попробуйте заново настроить через /start"
        )
        
        keyboard = [[InlineKeyboardButton("« Главное меню", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if query:
            await query.edit_message_text(
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
    
    # ==================== АДМИН-ПАНЕЛЬ ====================
    
    async def admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Админ-панель"""
        query = update.callback_query
        user_id = update.effective_user.id
        
        if not self.db.is_admin(user_id):
            await query.answer("❌ Нет прав", show_alert=True)
            return
        
        await query.answer()
        
        all_chats = self.db.get_all_chats()
        stats = self.db.get_stats()
        users_count = stats['users']
        chats_count = len(all_chats)
        
        keyboard = [
            [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton("👥 Список групп", callback_data="admin_chats")],
            [InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")],
            [InlineKeyboardButton("⏰ Интервал проверки", callback_data="admin_interval")],
            [InlineKeyboardButton("🔄 Проверить все", callback_data="admin_check_all")],
            [InlineKeyboardButton("🗑️ Очистить кеш", callback_data="admin_clear_cache")],
            [InlineKeyboardButton("« Главное меню", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            "👑 *АДМИН-ПАНЕЛЬ*\n\n"
            f"👤 Пользователей: {users_count}\n"
            f"💬 Активных групп: {chats_count}\n"
            f"⏰ Интервал: {self.db.get_check_interval()} мин\n"
        )
        
        await query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def admin_clear_cache(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Очистка кеша"""
        query = update.callback_query
        user_id = update.effective_user.id
        
        if not self.db.is_admin(user_id):
            await query.answer("❌ Нет прав", show_alert=True)
            return
        
        await query.answer("🗑️ Очистка кеша...")
        
        # Очищаем кеш бота
        bot_cache_size = len(self.groups_cache)
        self.groups_cache.clear()
        self.cache_timestamps.clear()
        
        # Очищаем кеш сканера
        self.scanner.clear_cache()
        
        text = (
            "✅ *Кеш очищен!*\n\n"
            f"🗑️ Удалено записей: {bot_cache_size}\n"
            "📝 Следующий запрос загрузит свежие данные из Drive"
        )
        
        keyboard = [[InlineKeyboardButton("« Назад", callback_data="admin_panel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def admin_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Рассылка всем пользователям"""
        query = update.callback_query
        user_id = update.effective_user.id
        
        if not self.db.is_admin(user_id):
            await query.answer("❌ Нет прав", show_alert=True)
            return
        
        await query.answer()
        
        text = (
            "📢 *РАССЫЛКА СООБЩЕНИЙ*\n\n"
            "Отправьте текст сообщения, которое будет разослано ВСЕМ пользователям бота.\n\n"
            "⚠️ *Внимание:* Используйте эту функцию ответственно!\n\n"
            "Поддерживается Markdown форматирование.\n\n"
            "Отправьте /cancel для отмены."
        )
        
        keyboard = [[InlineKeyboardButton("« Отмена", callback_data="admin_panel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def broadcast_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка сообщения для рассылки"""
        user_id = update.effective_user.id
        
        if not self.db.is_admin(user_id):
            return
        
        message_text = update.message.text
        
        # Подтверждение
        keyboard = [
            [
                InlineKeyboardButton("✅ Да, отправить", callback_data=f"confirm_broadcast"),
                InlineKeyboardButton("❌ Отмена", callback_data="admin_panel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Сохраняем текст в контексте
        context.user_data['broadcast_text'] = message_text
        
        all_users = self.db.get_all_users()
        
        await update.message.reply_text(
            f"📢 *Предпросмотр рассылки:*\n\n"
            f"{message_text}\n\n"
            f"👥 Будет отправлено *{len(all_users)}* пользователям\n\n"
            f"Подтвердите отправку:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def confirm_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Подтверждение и выполнение рассылки"""
        query = update.callback_query
        user_id = update.effective_user.id
        
        if not self.db.is_admin(user_id):
            await query.answer("❌ Нет прав", show_alert=True)
            return
        
        await query.answer()
        
        broadcast_text = context.user_data.get('broadcast_text')
        if not broadcast_text:
            await query.edit_message_text(
                "❌ Ошибка: текст сообщения не найден",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Назад", callback_data="admin_panel")
                ]])
            )
            return
        
        await query.edit_message_text(
            "📤 *Начинаю рассылку...*\n\n"
            "Это может занять некоторое время.",
            parse_mode='Markdown'
        )
        
        # Получаем всех пользователей
        all_users = self.db.get_all_users()
        
        success_count = 0
        failed_count = 0
        blocked_count = 0
        
        for user_data in all_users:
            try:
                await self.app.bot.send_message(
                    chat_id=user_data['user_id'],
                    text=broadcast_text,
                    parse_mode='Markdown'
                )
                success_count += 1
                await asyncio.sleep(0.05)  # Задержка чтобы не словить rate limit
            except Exception as e:
                if "blocked" in str(e).lower():
                    blocked_count += 1
                else:
                    failed_count += 1
        
        # Логируем рассылку
        self.db.log_action(user_id, 'broadcast', f'Успешно: {success_count}, Ошибок: {failed_count}')
        
        result_text = (
            "✅ *Рассылка завершена!*\n\n"
            f"📤 Отправлено: *{success_count}*\n"
            f"🚫 Заблокировали бота: {blocked_count}\n"
            f"❌ Ошибок: {failed_count}\n"
            f"👥 Всего пользователей: {len(all_users)}"
        )
        
        keyboard = [[InlineKeyboardButton("« Админ-панель", callback_data="admin_panel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.reply_text(
            result_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def admin_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Расширенная статистика для админа"""
        query = update.callback_query
        await query.answer()
        
        # Получаем расширенную статистику
        basic_stats = self.db.get_stats()
        extended_stats = self.db.get_extended_stats()
        
        text = "📊 *РАСШИРЕННАЯ СТАТИСТИКА*\n\n"
        
        # Основные цифры
        text += f"👤 Всего пользователей: *{basic_stats['users']}*\n"
        text += f"💬 Активных групп: *{basic_stats['chats']}*\n"
        text += f"👑 Администраторов: *{basic_stats['admins']}*\n\n"
        
        # По формам обучения
        text += "*📚 По формам обучения:*\n"
        for edu_key, count in extended_stats.get('users_by_education', {}).items():
            edu_name = EDUCATION_TYPES.get(edu_key, {}).get('name', edu_key)
            text += f"  • {edu_name}: {count}\n"
        
        # По курсам
        text += "\n*📖 По курсам:*\n"
        for course, count in extended_stats.get('users_by_course', {}).items():
            text += f"  • {course} курс: {count}\n"
        
        # Популярные группы (топ-5)
        top_groups = extended_stats.get('top_groups', [])[:5]
        if top_groups:
            text += "\n*🏆 Топ групп:*\n"
            for idx, (group_name, count) in enumerate(top_groups, 1):
                text += f"  {idx}. {group_name}: {count}\n"
        
        # Форматы
        formats = extended_stats.get('formats', {})
        text += f"\n*📤 Форматы:*\n"
        text += f"  📷 Фото: {formats.get('photo', 0)}\n"
        text += f"  📄 PDF: {formats.get('pdf', 0)}\n"
        
        # Активность за последние дни
        recent = extended_stats.get('recent_activity', [])
        if recent:
            text += f"\n*📈 Активность (7 дней):*\n"
            for date, count in recent[:3]:
                text += f"  • {date}: +{count}\n"
        
        keyboard = [[InlineKeyboardButton("« Назад", callback_data="admin_panel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    # ==================== АВТОПРОВЕРКА ОБНОВЛЕНИЙ ====================
    
    async def check_class_notifications(self, context: ContextTypes.DEFAULT_TYPE = None):
        """
        УЛУЧШЕННАЯ ЛОГИКА:
        1. Закрепленное расписание на день (обновляется, всегда наверху)
        2. Push-уведомления за 10 минут (НОВОЕ сообщение - приходит push!)
        3. Автоудаление уведомлений через 5 минут (не засоряет чат)
        """
        try:
            from datetime import datetime, timedelta
            
            # Получаем всех пользователей с включенными уведомлениями
            users = self.db.get_users_with_notifications_enabled()
            
            if not users:
                return
            
            current_hour = datetime.now().hour
            current_minute = datetime.now().minute
            current_date = datetime.now().strftime("%Y-%m-%d")
            
            for user in users:
                try:
                    user_id = user['user_id']
                    group = user['group']
                    daily_message_id = user.get('daily_message_id')
                    minutes_before = user.get('minutes_before', 10)
                    timezone = user.get('timezone', 'Asia/Tashkent')
                    
                    # Получаем расписание группы
                    schedule_json = self.db.get_schedule(group)
                    
                    if not schedule_json:
                        continue
                    
                    # ============================================
                    # 1. ЕЖЕДНЕВНОЕ РАСПИСАНИЕ (закрепленное)
                    # ============================================
                    
                    # Формируем сообщение с расписанием на день
                    message_text = NotificationManager.format_daily_schedule(
                        schedule_json, 
                        group, 
                        highlight_next=True
                    )
                    
                    # Утром (7:00) или если нет сообщения - отправляем новое
                    if (current_hour == 7 and current_minute < 5 and daily_message_id is None) or (daily_message_id is None and 7 <= current_hour <= 21):
                        try:
                            sent_message = await self.app.bot.send_message(
                                chat_id=user_id,
                                text=message_text,
                                parse_mode='Markdown',
                                disable_notification=True  # БЕЗ звука (фоновое)
                            )
                            
                            # Закрепляем сообщение
                            try:
                                await self.app.bot.pin_chat_message(
                                    chat_id=user_id,
                                    message_id=sent_message.message_id,
                                    disable_notification=True
                                )
                            except:
                                pass
                            
                            # Сохраняем ID сообщения
                            self.db.save_daily_message_id(user_id, sent_message.message_id)
                            
                            logger.info(f"📅 Отправлено ежедневное расписание для {user_id} (группа {group})")
                            
                        except Exception as e:
                            logger.error(f"Ошибка отправки ежедневного расписания {user_id}: {e}")
                    
                    # В течение дня - обновляем существующее сообщение
                    elif daily_message_id and 8 <= current_hour <= 21:
                        next_class = NotificationManager.get_next_class(schedule_json, timezone)
                        
                        # Обновляем каждые 5 минут или если до пары < 15 минут
                        should_update = False
                        
                        if next_class and next_class.get('minutes_until', 999) < 15:
                            should_update = True
                        elif current_minute % 5 == 0:  # Каждые 5 минут
                            should_update = True
                        
                        if should_update:
                            try:
                                await self.app.bot.edit_message_text(
                                    chat_id=user_id,
                                    message_id=daily_message_id,
                                    text=message_text,
                                    parse_mode='Markdown'
                                )
                                logger.debug(f"🔄 Обновлено расписание для {user_id}")
                            except Exception as e:
                                if "message to edit not found" in str(e).lower():
                                    self.db.save_daily_message_id(user_id, None)
                    
                    # ============================================
                    # 2. PUSH-УВЕДОМЛЕНИЯ ЗА 10 МИНУТ
                    # ============================================
                    
                    next_class = NotificationManager.get_next_class(schedule_json, timezone)
                    
                    if next_class:
                        minutes_until = next_class.get('minutes_until', 999)
                        class_time = next_class.get('time_start', '')
                        
                        # Проверяем: пора ли отправлять уведомление?
                        if minutes_before <= minutes_until <= minutes_before + 1:
                            # Проверяем не отправляли ли уже сегодня для этой пары
                            if not self.db.was_notification_sent(user_id, class_time, current_date):
                                try:
                                    # Формируем КОРОТКОЕ уведомление для push
                                    subject = next_class['subject']
                                    room = next_class.get('room', '')
                                    time_range = f"{next_class['time_start']}-{next_class['time_end']}"
                                    
                                    # ВАЖНО: Первые 2 строки видны в push-уведомлении!
                                    push_message = (
                                        f"🔔 *{subject}*\n"
                                        f"🚪 {room} • ⏰ {next_class['time_start']} (через {minutes_until} мин)\n\n"
                                        f"📅 Группа: {group}\n"
                                        f"⏱ {time_range}\n\n"
                                        f"💨 Не опаздывай!"
                                    )
                                    
                                    # Отправляем с ЗВУКОМ (disable_notification=False)
                                    sent_notif = await self.app.bot.send_message(
                                        chat_id=user_id,
                                        text=push_message,
                                        parse_mode='Markdown',
                                        disable_notification=False  # СО ЗВУКОМ! Push придет!
                                    )
                                    
                                    logger.info(f"🔔 Push-уведомление отправлено {user_id} о паре {subject}")
                                    
                                    # Отмечаем что отправили
                                    self.db.mark_notification_sent(user_id, class_time, current_date)
                                    
                                    # Планируем УДАЛЕНИЕ через 5 минут ПОСЛЕ НАЧАЛА пары
                                    # minutes_until (10 мин до пары) + 5 мин после начала = 15 минут
                                    delete_after = minutes_until + 5
                                    
                                    self.app.job_queue.run_once(
                                        callback=lambda ctx: self._delete_notification(user_id, sent_notif.message_id),
                                        when=timedelta(minutes=delete_after),
                                        name=f'delete_notif_{user_id}_{sent_notif.message_id}'
                                    )
                                    
                                    logger.debug(f"🗑️ Уведомление будет удалено через {delete_after} мин (в {next_class['time_start']} + 5 мин)")
                                    
                                except Exception as e:
                                    logger.error(f"Ошибка отправки push-уведомления {user_id}: {e}")
                    
                    # В конце дня - сбрасываем
                    if current_hour >= 22 and daily_message_id:
                        self.db.save_daily_message_id(user_id, None)
                        logger.debug(f"🌙 Сброшено ежедневное сообщение для {user_id}")
                    
                except Exception as e:
                    logger.error(f"Ошибка обработки пользователя {user.get('user_id')}: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Ошибка check_class_notifications: {e}")
    
    async def _delete_notification(self, chat_id: int, message_id: int):
        """Удалить уведомление (вызывается через 5 минут)"""
        try:
            await self.app.bot.delete_message(chat_id=chat_id, message_id=message_id)
            logger.debug(f"🗑️ Удалено уведомление {message_id} для {chat_id}")
        except Exception as e:
            logger.debug(f"Не удалось удалить уведомление: {e}")
    
    async def cleanup_old_logs(self, context: ContextTypes.DEFAULT_TYPE = None):
        """Автоматическая очистка старых логов и уведомлений"""
        try:
            logger.info("🗑️ Начало очистки старых данных...")
            
            # Очищаем логи
            deleted_logs = self.db.cleanup_old_logs(days=30)
            logger.info(f"✅ Удалено старых логов: {deleted_logs}")
            
            # Очищаем старые записи об уведомлениях
            deleted_notif = self.db.cleanup_old_notifications(days=7)
            logger.info(f"✅ Удалено старых уведомлений: {deleted_notif}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка очистки: {e}")
    
    async def check_all_schedules(self, context: ContextTypes.DEFAULT_TYPE = None):
        """Улучшенная проверка обновлений для всех групп"""
        try:
            logger.info("=" * 50)
            logger.info("🔍 Начало проверки обновлений...")
            start_time = datetime.now()
            
            all_chats = self.db.get_all_chats()
            
            if not all_chats:
                logger.info("ℹ️ Нет активных групп для проверки")
                return
            
            # Группируем чаты по файлам (чтобы не проверять один файл дважды)
            files_to_check = {}
            for chat_id_str, chat_data in all_chats.items():
                file_key = f"{chat_data['education_type']}_{chat_data.get('course')}_{chat_data['file_name']}"
                if file_key not in files_to_check:
                    files_to_check[file_key] = chat_data
            
            logger.info(f"📋 Групп для проверки: {len(all_chats)}")
            logger.info(f"📁 Уникальных файлов: {len(files_to_check)}")
            
            # Счетчики
            checked_count = 0
            updated_count = 0
            failed_count = 0
            
            for file_key, chat_data in files_to_check.items():
                try:
                    filename = chat_data['file_name']
                    education_type = chat_data['education_type']
                    course = chat_data.get('course')
                    
                    # Получаем информацию о файле
                    file_info = await asyncio.to_thread(
                        self.drive.get_file_info,
                        education_type,
                        filename,
                        course
                    )
                    
                    if not file_info:
                        logger.warning(f"⚠️ Файл {filename} не найден")
                        failed_count += 1
                        self.failed_checks[file_key] = self.failed_checks.get(file_key, 0) + 1
                        continue
                    
                    current_version = file_info.get('modified_time_raw')
                    last_version = self.file_versions.get(file_key)
                    
                    # Инициализация
                    if last_version is None:
                        self.file_versions[file_key] = current_version
                        logger.info(f"📝 Инициализация: {filename}")
                        checked_count += 1
                        continue
                    
                    # Проверка обновления
                    if current_version != last_version:
                        logger.info(f"🆕 Обновление: {filename}")
                        
                        # Загружаем файл
                        file_path, file_info = await asyncio.to_thread(
                            self.drive.download_file,
                            education_type,
                            filename,
                            course
                        )
                        
                        if file_path and os.path.exists(file_path):
                            # Отправляем во все группы с этим файлом
                            sent_count = await self._send_to_subscribed_chats(
                                file_path,
                                filename,
                                education_type,
                                file_info
                            )
                            
                            # Автоматически перераспознаем расписание через AI
                            try:
                                group_name = os.path.splitext(filename)[0]
                                logger.info(f"🤖 Перераспознаю расписание для {group_name}...")
                                schedule_data = await asyncio.to_thread(
                                    self.schedule_parser.parse_schedule_from_pdf,
                                    file_path
                                )
                                
                                if schedule_data:
                                    # Сохраняем в БД
                                    schedule_json = json.dumps(schedule_data, ensure_ascii=False)
                                    self.db.save_schedule(group_name, schedule_json)
                                    logger.info(f"✅ Расписание {group_name} обновлено автоматически")
                                else:
                                    logger.warning(f"⚠️ Не удалось распознать расписание {group_name}")
                            except Exception as e:
                                logger.error(f"❌ Ошибка перераспознавания {filename}: {e}")
                            
                            # Обновляем версию
                            self.file_versions[file_key] = current_version
                            
                            # Удаляем файл
                            os.remove(file_path)
                            
                            updated_count += 1
                            logger.info(f"   ✅ Отправлено в {sent_count} групп")
                            
                            # Сбрасываем счетчик ошибок
                            self.failed_checks.pop(file_key, None)
                        else:
                            failed_count += 1
                            self.failed_checks[file_key] = self.failed_checks.get(file_key, 0) + 1
                    else:
                        checked_count += 1
                        # Сбрасываем счетчик ошибок при успешной проверке
                        self.failed_checks.pop(file_key, None)
                        
                except Exception as e:
                    logger.error(f"❌ Ошибка проверки {file_key}: {e}")
                    failed_count += 1
                    self.failed_checks[file_key] = self.failed_checks.get(file_key, 0) + 1
                    continue
            
            # Статистика
            duration = (datetime.now() - start_time).total_seconds()
            logger.info("=" * 50)
            logger.info(f"✅ Проверка завершена за {duration:.1f}с")
            logger.info(f"📊 Проверено: {checked_count} | Обновлено: {updated_count} | Ошибок: {failed_count}")
            
            # Проверяем критические ошибки
            critical_failures = [
                key for key, count in self.failed_checks.items()
                if count >= self.max_check_retries
            ]
            
            if critical_failures:
                logger.warning(f"⚠️ Критические ошибки для {len(critical_failures)} файлов")
                await self._notify_admin_about_failures(critical_failures)
            
            logger.info("=" * 50)
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка глобальной проверки: {e}")
            import traceback
            traceback.print_exc()
    
    async def _send_to_subscribed_chats(self, file_path: str, filename: str, 
                                       education_type: str, file_info: dict) -> int:
        """
        Отправка файла во все подписанные чаты И ПОЛЬЗОВАТЕЛЯМ  
        Возвращает количество успешных отправок
        """
        sent_count = 0
        group_name_from_file = os.path.splitext(filename)[0]  # ISE-74R.pdf -> ISE-74R
        
        # 1. ОТПРАВЛЯЕМ В ГРУППЫ/КАНАЛЫ
        all_chats = self.db.get_all_chats()
        
        for chat_id_str, chat_data in all_chats.items():
            try:
                # Проверяем что это нужный файл
                if (chat_data['file_name'] != filename or 
                    chat_data['education_type'] != education_type):
                    continue
                
                chat_id = int(chat_id_str)
                group_name = chat_data['group']
                format_type = chat_data.get('format', 'photo')
                
                caption = (
                    f"🆕 *Обновлено расписание!*\n\n"
                    f"👥 Группа: *{group_name}*\n"
                    f"📆 Дата обновления: {file_info.get('modified_time', 'Неизвестно')}\n"
                    f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}"
                )
                
                # Отправляем в нужном формате
                if format_type == 'photo':
                    await self._send_schedule_as_photo(
                        chat_id,
                        file_path,
                        caption
                    )
                else:
                    await self._send_schedule_as_pdf(
                        chat_id,
                        file_path,
                        filename,
                        caption
                    )
                
                sent_count += 1
                logger.info(f"   📤 Отправлено в чат {chat_id}")
                
            except Exception as e:
                logger.error(f"   ❌ Ошибка отправки в чат {chat_id_str}: {e}")
        
        # 2. ОТПРАВЛЯЕМ ПОЛЬЗОВАТЕЛЯМ с этой группой
        all_users = self.db.get_all_users()
        
        for user_data in all_users:
            # Проверяем что это нужная группа
            if user_data.get('group') != group_name_from_file:
                continue
            
            try:
                user_id = user_data['user_id']
                format_type = user_data.get('format', 'photo')
                
                caption = (
                    f"🆕 *Обновлено расписание!*\n\n"
                    f"📅 Ваша группа: *{group_name_from_file}*\n"
                    f"📆 Обновлено: {file_info.get('modified_time', 'Сейчас')}\n\n"
                    f"💡 _Расписание автоматически обновлено в Google Drive_"
                )
                
                # Отправляем в нужном формате
                if format_type == 'photo':
                    await self._send_schedule_as_photo(
                        user_id,
                        file_path,
                        caption
                    )
                else:
                    await self._send_schedule_as_pdf(
                        user_id,
                        file_path,
                        filename,
                        caption
                    )
                
                sent_count += 1
                logger.info(f"   📤 Отправлено пользователю {user_id} (группа {group_name_from_file})")
                
                # Небольшая задержка против rate limit
                await asyncio.sleep(0.05)
                
            except Exception as e:
                logger.error(f"   ❌ Ошибка отправки пользователю {user_data['user_id']}: {e}")
        
        return sent_count
    
    async def _send_schedule_as_photo(self, chat_id: int, file_path: str, caption: str):
        """Отправка расписания как фото в чат"""
        try:
            image_paths = await asyncio.to_thread(
                self.converter.pdf_to_images,
                file_path
            )
            
            if not image_paths:
                await self._send_schedule_as_pdf(
                    chat_id,
                    file_path,
                    os.path.basename(file_path),
                    caption
                )
                return
            
            if len(image_paths) == 1:
                with open(image_paths[0], 'rb') as photo:
                    await self.app.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        caption=caption,
                        parse_mode='Markdown'
                    )
            else:
                media_group = []
                for i, img_path in enumerate(image_paths):
                    with open(img_path, 'rb') as photo:
                        media = InputMediaPhoto(
                            media=photo,
                            caption=caption if i == 0 else None,
                            parse_mode='Markdown' if i == 0 else None
                        )
                        media_group.append(media)
                
                await self.app.bot.send_media_group(
                    chat_id=chat_id,
                    media=media_group
                )
            
            self.converter.cleanup_images(image_paths)
            
        except Exception as e:
            logger.error(f"Ошибка отправки фото в {chat_id}: {e}")
            await self._send_schedule_as_pdf(
                chat_id,
                file_path,
                os.path.basename(file_path),
                caption
            )
    
    async def _send_schedule_as_pdf(self, chat_id: int, file_path: str, 
                                   filename: str, caption: str):
        """Отправка расписания как PDF в чат"""
        try:
            with open(file_path, 'rb') as pdf:
                await self.app.bot.send_document(
                    chat_id=chat_id,
                    document=pdf,
                    filename=filename,
                    caption=caption,
                    parse_mode='Markdown'
                )
        except Exception as e:
            logger.error(f"Ошибка отправки PDF в {chat_id}: {e}")
    
    async def _notify_admin_about_failures(self, failed_files: list):
        """Уведомление админа о критических проблемах"""
        try:
            admins = self.db.get_all_admins()
            if not admins:
                return
            
            message = (
                "⚠️ *ВНИМАНИЕ: Проблемы с проверкой файлов*\n\n"
                f"Не удалось проверить {len(failed_files)} файлов после {self.max_check_retries} попыток:\n\n"
            )
            
            for file_key in failed_files[:10]:  # Максимум 10
                message += f"• `{file_key}`\n"
            
            if len(failed_files) > 10:
                message += f"\n...и еще {len(failed_files) - 10} файлов"
            
            message += "\n\n💡 Проверьте подключение к Google Drive и правильность путей к файлам"
            
            for admin_id in admins:
                try:
                    await self.app.bot.send_message(
                        chat_id=admin_id,
                        text=message,
                        parse_mode='Markdown'
                    )
                    logger.info(f"📨 Уведомление отправлено админу {admin_id}")
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления админу {admin_id}: {e}")
        except Exception as e:
            logger.error(f"Ошибка уведомления админов: {e}")
    
    async def _notify_admin_new_user(self, user_id: int, group: str):
        """Уведомление админа о новом пользователе"""
        try:
            admins = self.db.get_all_admins()
            if not admins:
                return
            
            stats = self.db.get_stats()
            
            message = (
                "🆕 *Новый пользователь!*\n\n"
                f"👤 ID: `{user_id}`\n"
                f"👥 Группа: *{group}*\n\n"
                f"📊 Всего пользователей: {stats['users']}"
            )
            
            for admin_id in admins:
                try:
                    await self.app.bot.send_message(
                        chat_id=admin_id,
                        text=message,
                        parse_mode='Markdown'
                    )
                except:
                    pass  # Админ может заблокировать бота
        except Exception as e:
            logger.error(f"Ошибка уведомления о новом пользователе: {e}")
    
    # ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
    
    async def get_chat_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получить ID чата"""
        chat_id = update.effective_chat.id
        chat_type = update.effective_chat.type
        chat_title = update.effective_chat.title or "Личный чат"
        
        await update.message.reply_text(
            f"ℹ️ *Информация о чате*\n\n"
            f"🆔 Chat ID: `{chat_id}`\n"
            f"📱 Тип: {chat_type}\n"
            f"💬 Название: {chat_title}",
            parse_mode='Markdown'
        )
    
    async def cancel_setup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена настройки"""
        query = update.callback_query
        if query:
            await query.answer()
            await self.start_command(update, context)
        
        context.user_data.clear()
        return ConversationHandler.END
    
    def _main_menu_keyboard(self):
        """Клавиатура главного меню"""
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("« Главное меню", callback_data="back_to_menu")
        ]])
    
    # ==================== НАСТРОЙКА И ЗАПУСК ====================
    
    async def post_init(self, application: Application):
        """Инициализация после запуска"""
        logger.info("✅ Бот инициализирован")
    
    def setup(self):
        """Настройка бота"""
        self.app = (
            Application.builder()
            .token(TELEGRAM_BOT_TOKEN)
            .post_init(self.post_init)
            .build()
        )
        
        # Основные команды
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("setupgroup", self.setup_group_command))
        self.app.add_handler(CommandHandler("getchatid", self.get_chat_id))
        self.app.add_handler(CommandHandler("help", self.help_command))
        
        # Callback handlers
        self.app.add_handler(CallbackQueryHandler(self.start_command, pattern="^back_to_menu$"))
        self.app.add_handler(CallbackQueryHandler(self.get_my_schedule, pattern="^get_my_schedule$"))
        self.app.add_handler(CallbackQueryHandler(self.show_my_info, pattern="^show_my_info$"))
        self.app.add_handler(CallbackQueryHandler(self.help_command, pattern="^help$"))
        
        # Расписание и уведомления
        self.app.add_handler(CallbackQueryHandler(self.view_my_schedule, pattern="^view_my_schedule$"))
        self.app.add_handler(CallbackQueryHandler(self.parse_schedule, pattern="^parse_schedule$"))
        self.app.add_handler(CallbackQueryHandler(self.toggle_notifications, pattern="^toggle_notifications$"))
        
        self.app.add_handler(CallbackQueryHandler(self.admin_panel, pattern="^admin_panel$"))
        self.app.add_handler(CallbackQueryHandler(self.admin_stats, pattern="^admin_stats$"))
        self.app.add_handler(CallbackQueryHandler(self.admin_clear_cache, pattern="^admin_clear_cache$"))
        self.app.add_handler(CallbackQueryHandler(self.admin_broadcast, pattern="^admin_broadcast$"))
        self.app.add_handler(CallbackQueryHandler(self.confirm_broadcast, pattern="^confirm_broadcast$"))
        
        # ConversationHandler для настройки
        setup_handler = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(self.start_setup, pattern="^start_setup$")
            ],
            states={
                SELECT_EDUCATION: [
                    CallbackQueryHandler(self.select_education, pattern="^edu_"),
                ],
                SELECT_COURSE: [
                    CallbackQueryHandler(self.select_course, pattern="^course_"),
                    CallbackQueryHandler(self.start_setup, pattern="^start_setup$"),
                ],
                SELECT_GROUP_LIST: [
                    CallbackQueryHandler(self.select_direction, pattern="^showdir_"),
                    CallbackQueryHandler(self.select_group, pattern="^custom_group$"),
                    CallbackQueryHandler(self.select_education, pattern="^edu_"),
                    CallbackQueryHandler(self.select_course, pattern="^course_"),
                ],
                SELECT_GROUP_PAGE: [
                    CallbackQueryHandler(self.navigate_group_page, pattern="^grouppage_"),
                    CallbackQueryHandler(self.select_group, pattern="^selgroup_"),
                    CallbackQueryHandler(self.select_group, pattern="^custom_group$"),
                    CallbackQueryHandler(self.select_course, pattern="^course_"),
                ],
                WAITING_CUSTOM_FILE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.custom_group_input),
                ],
                SELECT_FORMAT: [
                    CallbackQueryHandler(self.select_format, pattern="^format_"),
                    CallbackQueryHandler(self.select_course, pattern="^course_"),
                ],
            },
            fallbacks=[
                CallbackQueryHandler(self.cancel_setup, pattern="^cancel_setup$"),
                CommandHandler("cancel", self.cancel_setup),
            ],
        )
        self.app.add_handler(setup_handler)
        
        # Обработчик для "noop" (пустое действие для индикатора страницы)
        self.app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.answer(), pattern="^noop$"))
        
        # JobQueue для автопроверки
        interval = self.db.get_check_interval()
        self.app.job_queue.run_repeating(
            self.check_all_schedules,
            interval=interval * 60,
            first=30,  # Первая проверка через 30 сек
            name='check_schedules'
        )
        
        # Автоматическая очистка старых логов (каждые 24 часа)
        self.app.job_queue.run_repeating(
            self.cleanup_old_logs,
            interval=24 * 3600,  # 24 часа
            first=3600,  # Первая очистка через 1 час
            name='cleanup_logs'
        )
        
        # Проверка времени пар каждую минуту
        self.app.job_queue.run_repeating(
            self.check_class_notifications,
            interval=60,  # 1 минута
            first=10,  # Первая проверка через 10 секунд
            name='check_notifications'
        )
        
        logger.info(f"✅ Автопроверка настроена: каждые {interval} минут")
        logger.info(f"✅ Автоочистка логов: каждые 24 часа")
        logger.info(f"✅ Проверка уведомлений: каждую минуту")
    
    def run(self):
        """Запуск бота"""
        self.setup()
        logger.info("🚀 Бот запущен и готов к работе!")
        logger.info("="*50)
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)


def main():
    """Главная функция"""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN не установлен в .env файле!")
        return
    
    logger.info("="*50)
    logger.info("🤖 MULTI-SCHEDULE BOT v3.0")
    logger.info("="*50)
    
    bot = MultiScheduleBot()
    bot.run()


if __name__ == '__main__':
    main()

