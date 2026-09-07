"""Extract actual image content, never neighboring benchmark answers.

Technical metadata alone is not a successful knowledge import. OCR and model
interpretation are separate observations, not guaranteed facts.
"""
import math
import tempfile
import warnings
from pathlib import Path
from typing import Optional
from PIL import Image, ImageOps
from src.brain.knowledge.extractors.base import BaseExtractor
from src.brain.knowledge.extractors.ocr_engine import OCREngine
from src.brain.knowledge.extractors.vision_provider import get_vision_provider, VisionStatus
from src.brain.models.file_metadata import ExtractionResult, ExtractedElement


class ImageExtractor(BaseExtractor):
    SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif"}

    def __init__(self, ocr_engine=None, vision_provider=None,
                 max_pixels: int = 40_000_000, min_ocr_confidence: float = 0.5):
        if max_pixels <= 0:
            raise ValueError("max_pixels must be positive")
        if not 0 <= min_ocr_confidence <= 1:
            raise ValueError("min_ocr_confidence must be between 0 and 1")
        self._ocr = ocr_engine
        self._vision = vision_provider
        self.max_pixels = max_pixels
        self.min_ocr_confidence = min_ocr_confidence

    def can_handle(self, extension: str, mime_type: str) -> bool:
        return extension.lower() in self.SUPPORTED_EXTS

    def extract(self, file_path: Path, source_id: str = "default_source",
                derived_dir: Optional[Path] = None) -> ExtractionResult:
        p = Path(file_path)
        info = {"format": p.suffix.lstrip(".").upper(), "ocr_status": "NOT_RUN",
                "vision_status": "NOT_RUN", "warnings": [], "content_coverage": "NONE"}
        try:
            if not self.can_handle(p.suffix, ""):
                raise ValueError("Unsupported image extension")
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(p) as image:
                    if image.width * image.height > self.max_pixels:
                        raise ValueError("Image exceeds configured pixel limit")
                    if getattr(image, "n_frames", 1) != 1:
                        raise ValueError("Multi-frame images are not supported; export each frame/page separately")
                    image.verify()
                with Image.open(p) as image:
                    normalized = ImageOps.exif_transpose(image).convert("RGB")
                    normalized.load()
                    info.update(width=normalized.width, height=normalized.height,
                                exif_transposed=True, exif_forwarded=False)
                    # Pillow may carry EXIF/ICC through convert(); strip all
                    # embedded metadata before forwarding to a provider.
                    normalized.info.clear()
            try:
                dest = Path(derived_dir) if derived_dir else p.parent / ".derived"
                dest.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(prefix="image-", dir=dest) as scratch:
                    image_path = Path(scratch) / "normalized.png"
                    normalized.save(image_path, format="PNG")
                    elements, ocr_text, description = [], "", ""
                    try:
                        engine = self._ocr if self._ocr is not None else OCREngine.get_instance()
                        if not engine.is_available:
                            info["ocr_status"] = "UNAVAILABLE"
                        else:
                            text, confidence = engine.extract_text(image_path)
                            if not isinstance(text, str):
                                raise ValueError("OCR returned non-text content")
                            confidence = float(confidence)
                            if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                                raise ValueError("Invalid OCR confidence")
                            info["ocr_confidence"] = confidence
                            ocr_text = text.strip()
                            if not ocr_text:
                                # Existing engine conflates no text and failure.
                                info["ocr_status"] = "EMPTY_OR_FAILED"
                            elif confidence < self.min_ocr_confidence:
                                info["ocr_status"] = "LOW_CONFIDENCE"
                                info["warnings"].append("OCR text withheld due to low confidence")
                                ocr_text = ""
                            else:
                                info["ocr_status"] = "EXTRACTED"
                                elements.append(ExtractedElement(
                                    element_type="ocr",
                                    content="РАСПОЗНАННЫЙ ТЕКСТ (OCR, возможны ошибки):\n" + ocr_text,
                                    metadata={"provenance": "ocr", "ocr_text": ocr_text,
                                              "confidence": confidence, "needs_review": True}))
                    except Exception as exc:
                        info["ocr_status"] = "ERROR"
                        info["warnings"].append("OCR failed: " + type(exc).__name__)
                    try:
                        provider = self._vision if self._vision is not None else get_vision_provider()
                        if not provider.is_available():
                            info["vision_status"] = "UNAVAILABLE"
                        else:
                            result = provider.analyze_image(image_path)
                            info["vision_status"] = result.status.value
                            info["vision_model"] = result.model_name
                            if result.status == VisionStatus.AVAILABLE:
                                if not isinstance(result.description, str) or not result.description.strip():
                                    info["vision_status"] = "EMPTY"
                                else:
                                    description = result.description.strip()
                                    elements.append(ExtractedElement(
                                        element_type="vision_description",
                                        content="ИНТЕРПРЕТАЦИЯ ИЗОБРАЖЕНИЯ МОДЕЛЬЮ (не установленный факт):\n" + description,
                                        metadata={"provenance": "model_interpretation",
                                                  "model": result.model_name, "needs_review": True}))
                    except Exception as exc:
                        info["vision_status"] = "ERROR"
                        info["warnings"].append("Vision failed: " + type(exc).__name__)
            finally:
                normalized.close()
            info.update(ocr_text=ocr_text, visual_description=description,
                        vision_description=description, detected_objects=[], visual_tags=[])
            # Provider's existing hardcoded object labels are not observations.
            if not elements:
                return ExtractionResult(source_id=source_id, success=False, media_info=info,
                                        error_message="No usable image content extracted. Check OCR/vision availability and image quality.")
            info["content_coverage"] = "OCR_AND_VISION" if ocr_text and description else (
                "OCR_ONLY" if ocr_text else "VISION_ONLY")
            if not description:
                info["warnings"].append("Visual content was not analyzed")
            if not ocr_text:
                info["warnings"].append("No reliable OCR text extracted")
            return ExtractionResult(source_id=source_id, success=True, elements=elements,
                                    raw_text="\n\n".join(e.content for e in elements), media_info=info)
        except Exception as exc:
            return ExtractionResult(source_id=source_id, success=False, media_info=info,
                                    error_message="Image extraction failed: " + str(exc))
