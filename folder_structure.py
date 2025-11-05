"""
Структура папок Google Drive для расписаний
Настраивается в зависимости от структуры вашего Drive
"""

# Главная папка
MAIN_FOLDER_ID = "1Ud2rCjM099mjmKI6Hi1Okw08ZzD5_9U_"

# Структура образования
EDUCATION_TYPES = {
    "daytime": {
        "name": "🏫 Очное (Кундузги)",
        "folder_id": "1Ud2rCjM099mjmKI6Hi1Okw08ZzD5_9U_",
        "subfolder_name": "1. Кундузги таълим (Очное образование)"
    },
    "evening": {
        "name": "🌙 Вечернее (Кечки)",
        "folder_id": "1Ud2rCjM099mjmKI6Hi1Okw08ZzD5_9U_",
        "subfolder_name": "2. Кечки таълим (Вечернее образование)"
    },
    "correspondence": {
        "name": "📮 Заочное (Сиртқи)",
        "folder_id": "1Ud2rCjM099mjmKI6Hi1Okw08ZzD5_9U_",
        "subfolder_name": "3. Сиртқи таълим (Заочное образование)"
    },
    "masters": {
        "name": "🎓 Магистратура",
        "folder_id": "1Ud2rCjM099mjmKI6Hi1Okw08ZzD5_9U_",
        "subfolder_name": "4. Магистратура"
    }
}

# Курсы (LEVEL)
COURSES = {
    "1": "1-LEVEL",
    "2": "2-LEVEL",
    "3": "3-LEVEL",
    "4": "4-LEVEL",
    "5": "5-LEVEL"
}

# Маппинг для отображения
COURSE_DISPLAY = {
    "1": "📖 1 курс (1-LEVEL)",
    "2": "📖 2 курс (2-LEVEL)",
    "3": "📖 3 курс (3-LEVEL)",
    "4": "📖 4 курс (4-LEVEL)",
    "5": "📖 5 курс (5-LEVEL)"
}

# Шаблоны названий групп (для автоматического поиска файлов)
# Формат: {направление}-{курс}{группа}.pdf
# Например: ISE-74R.pdf, BMA-71U.pdf
GROUP_PATTERNS = {
    "ISE": "Информационная безопасность",
    "BMA": "Бизнес менеджмент",
    "ACC": "Бухгалтерский учет",
    "AUD": "Аудит",
    "BAN": "Банковское дело",
    "BAT": "Бизнес администрирование",
    "CEN": "Ценообразование",
    "DNT": "Стоматология",
    "ELE": "Электроника",
    "ENG": "Английский язык",
    "FAD": "Финансовый анализ"
}

def generate_group_code(direction: str, course: str, group_letter: str) -> str:
    """
    Генерация кода группы
    Например: ISE + 7 + 4 + R = ISE-74R
    """
    return f"{direction}-{course}{group_letter}"

def parse_group_code(filename: str) -> dict:
    """
    Парсинг имени файла расписания
    Например: ISE-74R.pdf -> {direction: ISE, course: 7, semester: 4, group: R}
    """
    try:
        name = filename.replace('.pdf', '')
        parts = name.split('-')
        if len(parts) == 2:
            direction = parts[0]
            code = parts[1]
            
            # Примерный формат: 74R (7 - курс, 4 - семестр, R - группа)
            if len(code) >= 3:
                course = code[0]
                semester = code[1]
                group = code[2:]
                
                return {
                    'direction': direction,
                    'course': course,
                    'semester': semester,
                    'group': group,
                    'full_code': name
                }
    except:
        pass
    
    return None

def get_friendly_name(direction_code: str) -> str:
    """Получить читаемое название направления"""
    return GROUP_PATTERNS.get(direction_code, direction_code)

