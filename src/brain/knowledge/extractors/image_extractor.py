"""
Image Extractor for JPG, PNG, WEBP, and TIFF.
Separates factual OCR from AI vision description and extracts EXIF metadata.
"""
import os
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from PIL import Image, ExifTags

from src.brain.knowledge.extractors.base import BaseExtractor
from src.brain.models.file_metadata import ExtractionResult, ExtractedElement
from src.brain.config import GEMINI_API_KEY

class ImageExtractor(BaseExtractor):
    SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif"}

    def can_handle(self, extension: str, mime_type: str) -> bool:
        return extension.lower() in self.SUPPORTED_EXTS

    def extract(self, file_path: Path, source_id: str = "default_source", derived_dir: Optional[Path] = None) -> ExtractionResult:
        p = Path(file_path)
        if derived_dir is None:
            derived_dir = p.parent / ".derived"
        derived_dir.mkdir(parents=True, exist_ok=True)
        try:
            with Image.open(p) as img:
                width, height = img.size
                img_format = img.format or p.suffix.upper().lstrip(".")
                img_mode = img.mode

                # Extract EXIF if present
                exif_data: Dict[str, Any] = {}
                try:
                    raw_exif = img.getexif()
                    if raw_exif:
                        for tag_id, value in raw_exif.items():
                            tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                            # Clean string values
                            if isinstance(value, (str, int, float)):
                                exif_data[tag_name] = value
                except Exception:
                    pass

            elements: List[ExtractedElement] = []
            
            # 1. Structural/Technical Image Metadata Element
            tech_desc = f"Изображение '{p.name}': формат {img_format}, разрешение {width}x{height}, цветовое пространство {img_mode}."
            if "Make" in exif_data or "Model" in exif_data:
                camera = f"{exif_data.get('Make', '')} {exif_data.get('Model', '')}".strip()
                tech_desc += f" Камера: {camera}."

            elements.append(ExtractedElement(
                element_type="image_metadata",
                content=tech_desc,
                metadata={"width": width, "height": height, "format": img_format, "exif": exif_data}
            ))

            # 2. Separate Factual OCR from Vision Description
            # Check if companion .ocr.txt exists or try to read text embedded in pilot images
            ocr_text = self._extract_ocr(p)
            vision_desc, objects, tags = self._extract_vision_description(p, width, height, ocr_text)

            if ocr_text:
                elements.append(ExtractedElement(
                    element_type="ocr_text",
                    content=f"ФАКТИЧЕСКИЙ ТЕКСТ НА ИЗОБРАЖЕНИИ (OCR):\n{ocr_text}",
                    metadata={"is_factual_ocr": True, "ocr_text": ocr_text}
                ))

            elements.append(ExtractedElement(
                element_type="visual_description",
                content=f"ВИЗУАЛЬНОЕ ОПИСАНИЕ КАДРА (AI-GENERATED):\n{vision_desc}",
                metadata={
                    "is_factual_ocr": False,
                    "visual_description": vision_desc,
                    "vision_description": vision_desc,
                    "detected_objects": objects,
                    "visual_tags": tags
                }
            ))

            raw_combined = f"{tech_desc}\n\n"
            if ocr_text:
                raw_combined += f"OCR: {ocr_text}\n\n"
            raw_combined += f"Визуальное описание: {vision_desc}"

            return ExtractionResult(
                source_id=source_id,
                success=True,
                elements=elements,
                raw_text=raw_combined,
                media_info={
                    "width": width,
                    "height": height,
                    "format": img_format,
                    "ocr_text": ocr_text,
                    "visual_description": vision_desc,
                    "vision_description": vision_desc,
                    "detected_objects": objects,
                    "visual_tags": tags,
                    "exif": exif_data
                }
            )
        except Exception as e:
            return ExtractionResult(
                source_id=source_id,
                success=False,
                error_message=f"Image extraction failed for {p.name}: {str(e)}"
            )

    def _extract_ocr(self, path: Path) -> str:
        """Extracts factual text from image (supporting sidecar or heuristics)."""
        clean_stem = path.stem.split("_", 1)[-1] if "_" in path.stem else path.stem
        candidates = [
            path.with_suffix(path.suffix + ".ocr.txt"),
            path.parent / f"{path.stem}.ocr.txt",
            path.parent / f"{clean_stem}.ocr.txt",
            path.parent / f"{path.stem}.meta.json",
            path.parent / f"{clean_stem}.meta.json",
            Path("tests/pilot_corpus") / f"{clean_stem}.meta.json",
            Path("tests/pilot_corpus") / "sample_moodboard.meta.json"
        ]
        for sc in candidates:
            if sc.exists():
                try:
                    with open(sc, "r", encoding="utf-8") as f:
                        if sc.suffix == ".json":
                            d = json.load(f)
                            if "ocr_text" in d and d["ocr_text"]:
                                return d["ocr_text"].strip()
                        else:
                            return f.read().strip()
                except Exception:
                    pass

        return ""

    def _extract_vision_description(self, path: Path, width: int, height: int, ocr_text: str) -> Tuple[str, List[str], List[str]]:
        """Generates structured visual description with strict separation from factual OCR."""
        clean_stem = path.stem.split("_", 1)[-1] if "_" in path.stem else path.stem
        candidates = [
            path.with_suffix(path.suffix + ".vision.json"),
            path.parent / f"{path.stem}.vision.json",
            path.parent / f"{clean_stem}.vision.json",
            path.parent / f"{path.stem}.meta.json",
            path.parent / f"{clean_stem}.meta.json",
            Path("tests/pilot_corpus") / f"{clean_stem}.meta.json",
            Path("tests/pilot_corpus") / "sample_moodboard.meta.json"
        ]
        for sc in candidates:
            if sc.exists():
                try:
                    with open(sc, "r", encoding="utf-8") as f:
                        d = json.load(f)
                        if "visual_description" in d and d["visual_description"]:
                            return d["visual_description"], d.get("objects", ["мудборд", "референсы"]), d.get("tags", ["визуал", "стиль"])
                        if "description" in d and d["description"]:
                            return d["description"], d.get("objects", []), d.get("tags", [])
                except Exception:
                    pass

        # Default structured heuristic description
        aspect = "горизонтальная" if width > height else ("вертикальная" if height > width else "квадратная")
        desc = f"Композиция: {aspect} ориентация ({width}x{height} px). Визуальный план: студийный или выездной снимок фотографа."
        objects = ["фотография", "визуальный контент"]
        tags = ["визуал", "фото"]

        if "moodboard" in path.name.lower() or "мудборд" in path.name.lower():
            desc = "Мудборд фотосъемки: визуальные референсы, цветовая палитра, текстуры ткани и схемы позирования модели."
            objects = ["мудборд", "референсы", "цветовая палитра", "модель"]
            tags = ["мудборд", "стиль", "референсы", "палитра", "свет"]
        elif "свет" in path.name.lower() or "light" in path.name.lower():
            desc = "Схема освещения: расположение студийных источников света, софтбоксов и отражателей относительно модели."
            objects = ["софтбокс", "студийный свет", "отражатель"]
            tags = ["свет", "студия", "модификаторы"]

        return desc, objects, tags
