import os
import logging
import io
from typing import List, Optional
from PIL import Image

logger = logging.getLogger(__name__)

class PDFConverter:
    """Конвертер PDF в изображения"""
    
    def __init__(self, dpi: int = 200, quality: int = 85, max_dimension: int = 2000):
        """
        dpi: разрешение для конвертации (200 = хорошее качество, меньше размер)
        quality: качество JPEG (85 = оптимальный баланс)
        max_dimension: максимальная ширина/высота в пикселях
        """
        self.dpi = dpi
        self.quality = quality
        self.max_dimension = max_dimension
    
    def pdf_to_images(self, pdf_path: str, output_folder: str = "temp_images") -> List[str]:
        """
        Конвертация PDF в изображения
        Возвращает список путей к изображениям
        """
        try:
            # Попытка использовать pdf2image
            try:
                from pdf2image import convert_from_path
                
                # Создаем папку для изображений
                os.makedirs(output_folder, exist_ok=True)
                
                # Конвертируем PDF
                images = convert_from_path(
                    pdf_path,
                    dpi=300,  # Качество изображения
                    fmt='jpeg',
                    jpegopt={'quality': 95, 'optimize': True}
                )
                
                image_paths = []
                base_name = os.path.splitext(os.path.basename(pdf_path))[0]
                
                for i, image in enumerate(images):
                    img_path = os.path.join(output_folder, f"{base_name}_page_{i+1}.jpg")
                    image.save(img_path, 'JPEG', quality=95, optimize=True)
                    image_paths.append(img_path)
                    logger.info(f"Страница {i+1} сохранена: {img_path}")
                
                return image_paths
                
            except ImportError:
                logger.warning("pdf2image не установлен, используем альтернативный метод")
                return self._alternative_convert(pdf_path, output_folder)
                
        except Exception as e:
            logger.error(f"Ошибка конвертации PDF: {e}")
            return []
    
    def _alternative_convert(self, pdf_path: str, output_folder: str) -> List[str]:
        """
        Альтернативный метод конвертации через PyMuPDF (fitz)
        """
        try:
            import fitz  # PyMuPDF
            
            os.makedirs(output_folder, exist_ok=True)
            
            doc = fitz.open(pdf_path)
            image_paths = []
            base_name = os.path.splitext(os.path.basename(pdf_path))[0]
            
            # Определяем коэффициент масштабирования
            zoom = self.dpi / 72  # 72 DPI - стандарт PDF
            mat = fitz.Matrix(zoom, zoom)
            
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                
                # Конвертируем в изображение
                pix = page.get_pixmap(matrix=mat, alpha=False)
                
                # Конвертируем в PIL Image для оптимизации
                img_data = pix.tobytes("jpeg")  # quality задается при сохранении через PIL
                img = Image.open(io.BytesIO(img_data))
                
                # Уменьшаем если слишком большое
                width, height = img.size
                if width > self.max_dimension or height > self.max_dimension:
                    ratio = min(self.max_dimension/width, self.max_dimension/height)
                    new_size = (int(width*ratio), int(height*ratio))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                    logger.info(f"Уменьшено: {width}x{height} → {new_size[0]}x{new_size[1]}")
                
                # Сохраняем оптимизированное изображение
                img_path = os.path.join(output_folder, f"{base_name}_page_{page_num+1}.jpg")
                img.save(
                    img_path,
                    'JPEG',
                    quality=self.quality,
                    optimize=True,
                    progressive=True
                )
                
                # Логируем размер файла
                file_size = os.path.getsize(img_path) / 1024  # KB
                logger.info(f"Страница {page_num+1}: {img_path} ({file_size:.1f} KB)")
                
                image_paths.append(img_path)
            
            doc.close()
            
            # Общий размер
            total_size = sum(os.path.getsize(p) for p in image_paths) / 1024
            logger.info(f"✅ Всего страниц: {len(image_paths)}, общий размер: {total_size:.1f} KB")
            
            return image_paths
            
        except ImportError:
            logger.error("PyMuPDF не установлен. Установите: pip install PyMuPDF")
            return []
        except Exception as e:
            logger.error(f"Ошибка альтернативной конвертации: {e}")
            return []
    
    @staticmethod
    def cleanup_images(image_paths: List[str]):
        """Удаление временных изображений"""
        deleted = 0
        for img_path in image_paths:
            try:
                if os.path.exists(img_path):
                    os.remove(img_path)
                    deleted += 1
            except Exception as e:
                logger.error(f"Ошибка удаления {img_path}: {e}")
        
        if deleted > 0:
            logger.debug(f"🗑️ Удалено {deleted} временных файлов")
        
        # Удаляем папку если пустая
        try:
            if image_paths:
                folder = os.path.dirname(image_paths[0])
                if os.path.exists(folder) and not os.listdir(folder):
                    os.rmdir(folder)
                    logger.debug(f"🗑️ Удалена пустая папка: {folder}")
        except:
            pass

