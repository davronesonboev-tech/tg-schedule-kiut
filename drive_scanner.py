"""
Сканер Google Drive для автоматического получения списка групп
"""

import os
import logging
import requests
import time
from typing import List, Dict, Optional
from folder_structure import MAIN_FOLDER_ID, EDUCATION_TYPES, COURSES

logger = logging.getLogger(__name__)


class DriveScanner:
    """Сканер для автоматического обнаружения групп"""
    
    def __init__(self, cache_ttl: int = 3600):
        self.api_key = os.getenv('GOOGLE_API_KEY')
        self.cache = {}  # Кеш для списков файлов
        self.cache_timestamps = {}  # Время кеширования
        self.cache_ttl = cache_ttl  # Время жизни кеша в секундах (по умолчанию 1 час)
    
    def get_subfolders(self, folder_id: str) -> List[Dict]:
        """Получить подпапки"""
        try:
            api_url = "https://www.googleapis.com/drive/v3/files"
            params = {
                'q': f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
                'fields': 'files(id, name)',
                'supportsAllDrives': 'true',
                'includeItemsFromAllDrives': 'true',
                'orderBy': 'name'
            }
            
            if self.api_key:
                params['key'] = self.api_key
            
            response = requests.get(api_url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('files', [])
        except Exception as e:
            logger.error(f"Ошибка получения подпапок: {e}")
        
        return []
    
    def get_pdf_files(self, folder_id: str) -> List[Dict]:
        """Получить все PDF файлы в папке"""
        try:
            # Проверяем кеш
            if folder_id in self.cache:
                cache_age = time.time() - self.cache_timestamps.get(folder_id, 0)
                if cache_age < self.cache_ttl:
                    logger.debug(f"🗄️ Кеш для {folder_id[:20]}... (возраст: {cache_age:.0f}с)")
                    return self.cache[folder_id]
                else:
                    logger.debug(f"⏰ Кеш устарел для {folder_id[:20]}... (возраст: {cache_age:.0f}с)")
                    del self.cache[folder_id]
                    del self.cache_timestamps[folder_id]
            
            api_url = "https://www.googleapis.com/drive/v3/files"
            params = {
                'q': f"'{folder_id}' in parents and mimeType='application/pdf' and trashed=false",
                'fields': 'files(id, name)',
                'supportsAllDrives': 'true',
                'includeItemsFromAllDrives': 'true',
                'orderBy': 'name',
                'pageSize': 1000  # Максимум файлов
            }
            
            if self.api_key:
                params['key'] = self.api_key
            
            response = requests.get(api_url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                files = data.get('files', [])
                
                # Сохраняем в кеш с временной меткой
                self.cache[folder_id] = files
                self.cache_timestamps[folder_id] = time.time()
                logger.debug(f"💾 Сохранено в кеш: {len(files)} файлов для {folder_id[:20]}...")
                
                return files
        except Exception as e:
            logger.error(f"Ошибка получения файлов: {e}")
        
        return []
    
    def find_education_folder(self, education_type: str) -> Optional[str]:
        """Найти папку формы обучения"""
        try:
            education_info = EDUCATION_TYPES.get(education_type)
            if not education_info:
                return None
            
            subfolders = self.get_subfolders(MAIN_FOLDER_ID)
            subfolder_name = education_info['subfolder_name']
            
            for folder in subfolders:
                if subfolder_name in folder['name']:
                    return folder['id']
            
            return MAIN_FOLDER_ID
            
        except Exception as e:
            logger.error(f"Ошибка поиска папки образования: {e}")
            return MAIN_FOLDER_ID
    
    def find_course_folder(self, education_folder_id: str, course: str) -> Optional[str]:
        """Найти папку курса (LEVEL)"""
        try:
            course_name = COURSES.get(course)
            if not course_name:
                return None
            
            subfolders = self.get_subfolders(education_folder_id)
            
            for folder in subfolders:
                if course_name in folder['name']:
                    return folder['id']
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка поиска папки курса: {e}")
            return None
    
    def get_all_groups(self, education_type: str, course: str) -> List[str]:
        """
        Получить все группы для курса
        Возвращает список имен файлов (например: ACC-71U.pdf)
        """
        try:
            # Находим папку образования
            edu_folder_id = self.find_education_folder(education_type)
            if not edu_folder_id:
                logger.warning(f"Папка образования {education_type} не найдена")
                return []
            
            # Находим папку курса
            course_folder_id = self.find_course_folder(edu_folder_id, course)
            if not course_folder_id:
                logger.warning(f"Папка курса {course} не найдена")
                return []
            
            # Получаем все PDF файлы
            files = self.get_pdf_files(course_folder_id)
            
            # Извлекаем имена файлов
            group_names = [f['name'] for f in files if f['name'].endswith('.pdf')]
            
            logger.info(f"Найдено {len(group_names)} групп для {education_type}/{course}")
            
            return sorted(group_names)
            
        except Exception as e:
            logger.error(f"Ошибка получения групп: {e}")
            return []
    
    def parse_group_code(self, filename: str) -> Optional[Dict]:
        """
        Парсинг кода группы из имени файла
        Например: ACC-71U.pdf -> {direction: ACC, code: 71U, full: ACC-71U}
        """
        try:
            name = filename.replace('.pdf', '')
            parts = name.split('-')
            
            if len(parts) == 2:
                direction = parts[0]
                code = parts[1]
                
                return {
                    'direction': direction,
                    'code': code,
                    'full': name,
                    'filename': filename
                }
        except:
            pass
        
        return None
    
    def group_by_direction(self, group_names: List[str]) -> Dict[str, List[str]]:
        """
        Группировка файлов по направлениям
        Возвращает: {direction: [files]}
        """
        grouped = {}
        
        for filename in group_names:
            parsed = self.parse_group_code(filename)
            if parsed:
                direction = parsed['direction']
                if direction not in grouped:
                    grouped[direction] = []
                grouped[direction].append(filename)
        
        return grouped
    
    def clear_cache(self):
        """Очистить кеш"""
        cache_size = len(self.cache)
        self.cache.clear()
        self.cache_timestamps.clear()
        logger.info(f"🗑️ Кеш очищен ({cache_size} записей)")

