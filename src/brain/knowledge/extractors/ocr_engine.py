"""
Local On-Device OCR Engine for Knowledge Ingestion Factory.
Uses RapidOCR (ONNX Runtime) for high-performance Russian and English text recognition.
Does not depend on external Tesseract binaries or cloud API keys.
"""
from pathlib import Path
from typing import Tuple, Optional, List

class OCREngine:
    _instance: Optional["OCREngine"] = None
    _engine = None

    def __init__(self):
        if OCREngine._engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
                OCREngine._engine = RapidOCR()
            except Exception:
                OCREngine._engine = None

    @classmethod
    def get_instance(cls) -> "OCREngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def is_available(self) -> bool:
        return self._engine is not None

    def extract_text(self, image_path: Path) -> Tuple[str, float]:
        """
        Runs OCR on given image path.
        Returns Tuple[extracted_text, average_confidence].
        """
        p = Path(image_path)
        if not p.exists() or not self.is_available:
            return "", 0.0

        try:
            result, _ = self._engine(str(p))
            if not result:
                return "", 0.0

            # result format: [[box_coords, text, confidence], ...]
            lines: List[str] = []
            confidences: List[float] = []

            for item in result:
                if len(item) >= 3:
                    txt = str(item[1]).strip()
                    conf = float(item[2])
                    if txt:
                        lines.append(txt)
                        confidences.append(conf)

            full_text = "\n".join(lines).strip()
            avg_conf = (sum(confidences) / len(confidences)) if confidences else 0.0
            return full_text, round(avg_conf, 3)
        except Exception:
            return "", 0.0

def get_ocr_engine() -> OCREngine:
    return OCREngine.get_instance()
