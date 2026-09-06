"""
Generator for Stage 4 Pilot Corpus.
Creates high-fidelity multi-format test files for documents, images, audio, and video.
"""
import os
import json
import wave
import struct
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import fitz  # PyMuPDF
from docx import Document
from pptx import Presentation
from pptx.util import Inches, Pt
from openpyxl import Workbook

CORPUS_DIR = Path(__file__).parent.resolve()

def generate_pdf_contract():
    doc = fitz.open()
    page = doc.new_page()
    text = (
        "ДОГОВОР НА ОКАЗАНИЕ ФОТОУСЛУГ № 104-Ф\n\n"
        "г. Москва, 15 января 2026 года\n\n"
        "1. ПРЕДМЕТ ДОГОВОРА\n"
        "Исполнитель обязуется оказать Заказчику услуги по фотосъемке "
        "мероприятия 'Fashion Lookbook Autumn 2026', а Заказчик обязуется оплатить услуги.\n\n"
        "2. СТОИМОСТЬ И ПОРЯДОК ОПЛАТЫ\n"
        "Полная стоимость услуг составляет 85 000 рублей.\n"
        "Предоплата в размере 30 000 рублей вносится не позднее 20 января 2026 года.\n"
        "Остаток в размере 55 000 рублей оплачивается в день передачи готовых материалов.\n\n"
        "3. СРОКИ И ПЕРЕДАЧА МАТЕРИАЛОВ\n"
        "Срок передачи исходных файлов: 3 календарных дня.\n"
        "Срок передачи финальных ретушированных фотографий: 14 календарных дней.\n\n"
        "4. ОТМЕНА И ПЕРЕНОС СЪЕМКИ\n"
        "При отмене съемки менее чем за 48 часов задаток в размере 30 000 рублей не возвращается.\n"
    )
    rect = fitz.Rect(50, 50, 550, 750)
    page.insert_font(fontname="F0", fontfile="C:/Windows/Fonts/arial.ttf")
    page.insert_textbox(rect, text, fontsize=11, fontname="F0")
    doc.save(str(CORPUS_DIR / "sample_contract.pdf"))
    doc.close()
    print("Created sample_contract.pdf")

def generate_scanned_receipt():
    # Create image of receipt
    img = Image.new("RGB", (600, 400), color=(245, 245, 240))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 16)
    lines = [
        "КАССОВЫЙ ЧЕК № 8841",
        "ООО 'ФОТОПРОКАТ МОСКВА'",
        "Аренда объектива Sony 85mm f/1.4 GM: 3 500 руб.",
        "Аренда источника Profoto B10X: 4 200 руб.",
        "ИТОГО К ОПЛАТЕ: 7 700 руб.",
        "ОПЛАЧЕНО КАРТОЙ: ОДОБРЕНО",
        "ДАТА: 02.02.2026 11:30"
    ]
    y = 30
    for line in lines:
        draw.text((40, y), line, font=font, fill=(20, 20, 20))
        y += 40
    
    img_path = CORPUS_DIR / "temp_receipt.png"
    img.save(img_path)

    # Insert into PDF as full page image (scanned PDF)
    doc = fitz.open()
    page = doc.new_page(width=600, height=400)
    page.insert_image(fitz.Rect(0, 0, 600, 400), filename=str(img_path))
    doc.save(str(CORPUS_DIR / "sample_scanned_receipt.pdf"))
    doc.close()
    img_path.unlink()

    # Save sidecar OCR metadata
    sidecar_path = CORPUS_DIR / "sample_scanned_receipt.meta.json"
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump({"ocr_text": "\n".join(lines)}, f, ensure_ascii=False, indent=2)
    print("Created sample_scanned_receipt.pdf + sidecar OCR")

def generate_docx_guide():
    doc = Document()
    doc.add_heading("Руководство по студийному свету для портретной съемки", level=1)
    
    doc.add_heading("1. Базовые световые схемы", level=2)
    doc.add_paragraph(
        "Классическая портретная схема 'Рембрандт' характеризуется треугольником света "
        "на теневой стороне лица модели. Ключевой источник света устанавливается под углом 45 градусов "
        "относительно оси камеры и немного выше уровня глаз."
    )
    
    doc.add_heading("2. Сравнение светоформирующих насадок", level=2)
    table = doc.add_table(rows=1, cols=3)
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = "Насадка"
    hdr_cells[1].text = "Характер света"
    hdr_cells[2].text = "Рекомендация"
    
    data = [
        ("Октабокс 120 см", "Мягкий рассеянный свет с плавными тенями", "Женский бьюти-портрет"),
        ("Портретная тарелка (Beauty Dish)", "Контрастный свет с акцентом на фактуру кожи", "Fashion и фешн-макияж"),
        ("Стрипбокс с сотами", "Узкий направленный световой пучок", "Контровой свет и силуэты")
    ]
    for n, char, rec in data:
        row_cells = table.add_row().cells
        row_cells[0].text = n
        row_cells[1].text = char
        row_cells[2].text = rec

    doc.add_heading("3. Оборудование и чек-лист", level=2)
    p = doc.add_paragraph()
    p.add_run("• Синхронизатор Profoto Air Remote TTL\\n")
    p.add_run("• Светоотражатель 5-в-1 серебро/белый 80 см\\n")
    p.add_run("• Флаги черные пенокартонные 200x100 см")
    
    doc.save(str(CORPUS_DIR / "sample_guide.docx"))
    print("Created sample_guide.docx")

def generate_pptx_portfolio():
    prs = Presentation()
    
    # Slide 1: Title
    slide_layout = prs.slide_layouts[0]
    slide1 = prs.slides.add_slide(slide_layout)
    slide1.shapes.title.text = "Презентация Портфолио 2026"
    slide1.placeholders[1].text = "Автор: Анна Яровая\\nКоммерческая и портретная фотография"

    # Slide 2: Commercial Packages
    bullet_layout = prs.slide_layouts[1]
    slide2 = prs.slides.add_slide(bullet_layout)
    slide2.shapes.title.text = "Коммерческие пакеты для брендов"
    tf = slide2.placeholders[1].text_frame
    tf.text = "Съемка лукбуков и кампейнов:"
    p = tf.add_paragraph()
    p.text = "• Полный съемочный день (8 часов): 120 000 руб."
    p = tf.add_paragraph()
    p.text = "• Экспресс-лукбук (4 часа): 70 000 руб."
    p = tf.add_paragraph()
    p.text = "• Продюсирование и кастинг моделей под ключ"
    
    # Notes for Slide 2
    notes_slide = slide2.notes_slide
    text_frame = notes_slide.notes_text_frame
    text_frame.text = "В стоимость не включена аренда студии и оплата визажиста."

    prs.save(str(CORPUS_DIR / "sample_portfolio.pptx"))
    print("Created sample_portfolio.pptx")

def generate_xlsx_pricing():
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "Пакеты съемок"
    
    headers1 = ["Пакет", "Длительность (часы)", "Количество фото с ретушью", "Цена (руб.)", "Предоплата (руб.)"]
    ws1.append(headers1)
    ws1.append(["Индивидуальный базовый", 1, 15, 15000, 5000])
    ws1.append(["Индивидуальный премиум", 2, 35, 28000, 10000])
    ws1.append(["Свадебный день", 10, 120, 110000, 30000])
    ws1.append(["Контент для экспертов", 3, 50, 42000, 15000])
    
    ws2 = wb.create_sheet(title="Дополнительные услуги")
    headers2 = ["Услуга", "Единица измерения", "Стоимость (руб.)"]
    ws2.append(headers2)
    ws2.append(["Срочная отдача за 48 часов", "За заказ", 8000])
    ws2.append(["Дополнительный час съемки", "За 1 час", 7000])
    ws2.append(["Ретушь дополнительного кадра", "За 1 фото", 500])
    ws2.append(["Аренда пленочной камеры Leica", "За съемочный день", 6000])
    
    wb.save(str(CORPUS_DIR / "sample_pricing.xlsx"))
    print("Created sample_pricing.xlsx")

def generate_image_moodboard():
    img = Image.new("RGB", (800, 600), color=(230, 220, 205))
    draw = ImageDraw.Draw(img)
    draw.rectangle([50, 50, 750, 550], outline=(80, 70, 60), width=3)
    
    lines = [
        "MOODBOARD: AUTUMN URBAN MINIMALISM",
        "Color Palette: Warm Ochre, Graphite Gray, Off-White, Rust",
        "Lighting: Soft diffused natural window light, subtle negative fill",
        "Styling: Wool coats, oversized knitwear, clean architectural geometry",
        "Key Reference: Peter Lindbergh studio portraits"
    ]
    y = 80
    for line in lines:
        draw.text((70, y), line, fill=(40, 35, 30))
        y += 60

    img_path = CORPUS_DIR / "sample_moodboard.jpg"
    img.save(img_path, "JPEG")
    
    # Also save a sidecar visual description metadata to simulate multi-modal vision tagging
    sidecar_path = CORPUS_DIR / "sample_moodboard.meta.json"
    sidecar_data = {
        "visual_description": "Мудборд осенней фотосессии с образцами шерстяных пальто в графитовых и терракотовых тонах, минималистичная композиция с мягким студийным светом.",
        "ocr_text": "MOODBOARD: AUTUMN URBAN MINIMALISM\\nColor Palette: Warm Ochre, Graphite Gray, Off-White, Rust\\nLighting: Soft diffused natural window light\\nStyling: Wool coats, oversized knitwear\\nKey Reference: Peter Lindbergh studio portraits"
    }
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(sidecar_data, f, ensure_ascii=False, indent=2)
    print("Created sample_moodboard.jpg + sidecar")

def generate_audio_speech():
    wav_path = CORPUS_DIR / "sample_speech_ru.wav"
    sample_rate = 16000
    duration_s = 4
    n_samples = int(sample_rate * duration_s)
    
    with wave.open(str(wav_path), "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        # Generate clean audio sine wave
        for i in range(n_samples):
            val = int(32767.0 * 0.4 * math.sin(2.0 * math.pi * 440.0 * (i / sample_rate)))
            data = struct.pack("<h", val)
            wav_file.writeframesraw(data)

    # Also save sidecar transcript for deterministic testing without external speech models
    sidecar_path = CORPUS_DIR / "sample_speech_ru.transcript.json"
    sidecar_data = {
        "text": "Здравствуйте! Мы согласовали тайминг на пятницу, съемка начнется ровно в одиннадцать часов утра в зале Циклорама.",
        "language": "ru",
        "segments": [
            {
                "start": 0.0,
                "end": 2.2,
                "text": "Здравствуйте! Мы согласовали тайминг на пятницу,"
            },
            {
                "start": 2.2,
                "end": 4.0,
                "text": "съемка начнется ровно в одиннадцать часов утра в зале Циклорама."
            }
        ]
    }
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(sidecar_data, f, ensure_ascii=False, indent=2)
    print("Created sample_speech_ru.wav + sidecar transcript")

def generate_video_sidecar():
    # Sidecar for sample_lesson_ru.mp4
    sidecar_path = CORPUS_DIR / "sample_lesson_ru.video_meta.json"
    sidecar_data = {
        "audio_transcript": {
            "text": "Привет всем! Сегодня мы разберем жесткий свет и использование рефлектора с сотами. Обратите внимание на четкую границу светотени.",
            "language": "ru",
            "segments": [
                {
                    "start": 0.0,
                    "end": 3.0,
                    "text": "Привет всем! Сегодня мы разберем жесткий свет и использование рефлектора с сотами."
                },
                {
                    "start": 3.0,
                    "end": 6.0,
                    "text": "Обратите внимание на четкую границу светотени на модели."
                }
            ]
        },
        "scenes": [
            {
                "start_time": 0.0,
                "end_time": 3.0,
                "description": "Спикер у доски со схемой жесткого рефлектора.",
                "ocr_text": "УРОК 3: ЖЕСТКИЙ СВЕТ И СОТЫ"
            },
            {
                "start_time": 3.0,
                "end_time": 6.0,
                "description": "Демонстрация светотеневого рисунка на лице модели.",
                "ocr_text": "ГРАНИЦА ТЕНИ: ПРИМЕР СЪЕМКИ"
            }
        ]
    }
    for sc_name in ["sample_lesson_ru.video_meta.json", "sample_lesson_ru.manifest.json"]:
        with open(CORPUS_DIR / sc_name, "w", encoding="utf-8") as f:
            json.dump(sidecar_data, f, ensure_ascii=False, indent=2)
    print("Created sample_lesson_ru video sidecars")

if __name__ == "__main__":
    generate_pdf_contract()
    generate_scanned_receipt()
    generate_docx_guide()
    generate_pptx_portfolio()
    generate_xlsx_pricing()
    generate_image_moodboard()
    generate_audio_speech()
    generate_video_sidecar()
    print("All pilot corpus files generated successfully!")
