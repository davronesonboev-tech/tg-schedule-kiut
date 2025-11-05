import os
import logging
import requests
import time
from datetime import datetime
from typing import Optional, Tuple, Dict, List
from folder_structure import MAIN_FOLDER_ID, EDUCATION_TYPES

logger = logging.getLogger(__name__)


class MultiDriveMonitor:
    """Монитор для работы с несколькими папками Google Drive"""
    
    def __init__(self, max_retries: int = 3, retry_delay: int = 2):
        self.api_key = os.getenv('GOOGLE_API_KEY')
        self.main_folder_id = MAIN_FOLDER_ID
        self.max_retries = max_retries
        self.retry_delay = retry_delay
    
    def _request_with_retry(self, url: str, params: dict, timeout: int = 10) -> Optional[dict]:
        """Выполнить запрос с повторными попытками"""
        for attempt in range(self.max_retries):
            try:
                response = requests.get(url, params=params, timeout=timeout)
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:  # Rate limit
                    wait_time = self.retry_delay * (attempt + 1)
                    logger.warning(f"⚠️ Rate limit, ожидание {wait_time}с...")
                    time.sleep(wait_time)
                else:
                    logger.warning(f"⚠️ Статус {response.status_code}, попытка {attempt + 1}/{self.max_retries}")
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay)
            except requests.Timeout:
                logger.warning(f"⏱️ Timeout, попытка {attempt + 1}/{self.max_retries}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
            except Exception as e:
                logger.error(f"❌ Ошибка запроса: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
        
        return None
    
    def get_subfolders(self, folder_id: str) -> List[Dict]:
        """
        Получение списка подпапок в папке
        """
        try:
            api_url = "https://www.googleapis.com/drive/v3/files"
            params = {
                'q': f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
                'fields': 'files(id, name)',
                'supportsAllDrives': 'true',
                'includeItemsFromAllDrives': 'true'
            }
            
            if self.api_key:
                params['key'] = self.api_key
            
            data = self._request_with_retry(api_url, params, timeout=10)
            if data:
                return data.get('files', [])
        except Exception as e:
            logger.error(f"Ошибка получения подпапок: {e}")
        
        return []
    
    def find_education_folder(self, education_type: str) -> Optional[str]:
        """
        Поиск папки по типу образования
        """
        try:
            education_info = EDUCATION_TYPES.get(education_type)
            if not education_info:
                return None
            
            subfolders = self.get_subfolders(self.main_folder_id)
            subfolder_name = education_info['subfolder_name']
            
            for folder in subfolders:
                if subfolder_name in folder['name']:
                    return folder['id']
            
            # Если не нашли, возвращаем главную папку
            return self.main_folder_id
            
        except Exception as e:
            logger.error(f"Ошибка поиска папки образования: {e}")
            return self.main_folder_id
    
    def find_file_in_folder(self, folder_id: str, filename: str) -> Optional[Dict]:
        """
        Поиск файла в папке по имени
        """
        try:
            api_url = "https://www.googleapis.com/drive/v3/files"
            params = {
                'q': f"'{folder_id}' in parents and name='{filename}' and trashed=false",
                'fields': 'files(id, name, modifiedTime, size, webViewLink, webContentLink)',
                'supportsAllDrives': 'true',
                'includeItemsFromAllDrives': 'true'
            }
            
            if self.api_key:
                params['key'] = self.api_key
            
            data = self._request_with_retry(api_url, params, timeout=10)
            
            if data:
                files = data.get('files', [])
                
                if files:
                    file_data = files[0]
                    
                    # Форматируем дату
                    modified_time = file_data.get('modifiedTime', '')
                    if modified_time:
                        dt = datetime.fromisoformat(modified_time.replace('Z', '+00:00'))
                        formatted_time = dt.strftime('%d.%m.%Y %H:%M')
                    else:
                        formatted_time = 'Неизвестно'
                    
                    # Форматируем размер
                    size = int(file_data.get('size', 0))
                    size_kb = size / 1024
                    formatted_size = f"{size_kb:.1f} KB"
                    
                    return {
                        'id': file_data.get('id'),
                        'name': file_data.get('name'),
                        'modified_time': formatted_time,
                        'modified_time_raw': modified_time,
                        'size': formatted_size,
                        'web_link': file_data.get('webViewLink'),
                        'download_link': file_data.get('webContentLink')
                    }
        except Exception as e:
            logger.error(f"Ошибка поиска файла: {e}")
        
        return None
    
    def find_course_folder(self, education_folder_id: str, course: str) -> Optional[str]:
        """
        Поиск папки курса (например, 4-LEVEL)
        """
        try:
            from folder_structure import COURSES
            course_folder_name = COURSES.get(course, f"{course}-LEVEL")
            
            subfolders = self.get_subfolders(education_folder_id)
            
            for folder in subfolders:
                if course_folder_name in folder['name']:
                    return folder['id']
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка поиска папки курса: {e}")
            return None
    
    def get_file_info(self, education_type: str, filename: str, course: str = None) -> Optional[Dict]:
        """
        Получение информации о файле расписания
        """
        try:
            # Находим папку образования
            education_folder_id = self.find_education_folder(education_type)
            if not education_folder_id:
                logger.warning(f"Папка для {education_type} не найдена")
                return None
            
            # Если указан курс, ищем в папке курса
            if course:
                course_folder_id = self.find_course_folder(education_folder_id, course)
                if course_folder_id:
                    file_info = self.find_file_in_folder(course_folder_id, filename)
                    if file_info:
                        return file_info
                    else:
                        logger.warning(f"Файл {filename} не найден в папке курса {course}")
            
            # Иначе ищем в папке образования (обратная совместимость)
            file_info = self.find_file_in_folder(education_folder_id, filename)
            return file_info
            
        except Exception as e:
            logger.error(f"Ошибка получения информации о файле: {e}")
            return None
    
    def download_file(self, education_type: str, filename: str, course: str = None) -> Tuple[Optional[str], Optional[Dict]]:
        """
        Загрузка файла с Google Drive
        """
        try:
            file_info = self.get_file_info(education_type, filename, course)
            
            if not file_info:
                logger.error(f"Файл {filename} не найден")
                return None, None
            
            file_id = file_info.get('id')
            
            if file_id:
                download_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
                params = {}
                
                if self.api_key:
                    params['key'] = self.api_key
                
                # Пытаемся скачать с retry
                for attempt in range(self.max_retries):
                    try:
                        response = requests.get(download_url, params=params, timeout=30)
                        
                        if response.status_code == 200:
                            temp_file_path = f"temp_{filename}"
                            
                            with open(temp_file_path, 'wb') as f:
                                f.write(response.content)
                            
                            file_size = len(response.content) / 1024
                            logger.info(f"✅ Файл {filename} загружен ({file_size:.1f} KB)")
                            return temp_file_path, file_info
                        else:
                            logger.warning(f"⚠️ Статус загрузки {response.status_code}, попытка {attempt + 1}/{self.max_retries}")
                            if attempt < self.max_retries - 1:
                                time.sleep(self.retry_delay)
                    except Exception as e:
                        logger.error(f"❌ Ошибка загрузки (попытка {attempt + 1}): {e}")
                        if attempt < self.max_retries - 1:
                            time.sleep(self.retry_delay)
            
        except Exception as e:
            logger.error(f"Ошибка загрузки файла: {e}")
        
        return None, None
    
    def list_all_files_in_folder(self, folder_id: str) -> List[Dict]:
        """
        Получение списка всех PDF файлов в папке
        """
        try:
            api_url = "https://www.googleapis.com/drive/v3/files"
            params = {
                'q': f"'{folder_id}' in parents and mimeType='application/pdf' and trashed=false",
                'fields': 'files(id, name, modifiedTime)',
                'supportsAllDrives': 'true',
                'includeItemsFromAllDrives': 'true',
                'orderBy': 'name'
            }
            
            if self.api_key:
                params['key'] = self.api_key
            
            data = self._request_with_retry(api_url, params, timeout=10)
            if data:
                return data.get('files', [])
        except Exception as e:
            logger.error(f"Ошибка получения списка файлов: {e}")
        
        return []

