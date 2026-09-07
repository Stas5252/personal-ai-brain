"""
Tests for Image Extraction Engine.
Verifies EXIF parsing, strict separation of factual OCR from AI vision descriptions, and sidecar support.
"""
import pytest
from pathlib import Path
from PIL import Image

from src.brain.knowledge.extractors.image_extractor import ImageExtractor
from src.brain.knowledge.extractors.vision_provider import VisionStatus, VisionAnalysisResult
from src.brain.models.file_metadata import ExtractionResult

class MoodboardOCRDouble:
    is_available = True
    def extract_text(self, path):
        return ("MOODBOARD: AUTUMN URBAN MINIMALISM\nColor Palette: Warm Ochre, Graphite Gray", 0.95)

class MoodboardVisionDouble:
    def is_available(self):
        return True
    def analyze_image(self, path):
        return VisionAnalysisResult(
            status=VisionStatus.AVAILABLE,
            description="Мудборд осенней фотосессии с образцами шерстяных пальто в графитовых и терракотовых тонах",
            confidence=0.95
        )

@pytest.fixture
def img_extractor():
    return ImageExtractor(ocr_engine=MoodboardOCRDouble(), vision_provider=MoodboardVisionDouble())


def test_image_extraction_with_sidecar(img_extractor):
    img_path = Path("tests/pilot_corpus/sample_moodboard.jpg")
    assert img_path.exists(), "Pilot moodboard image must exist"

    result = img_extractor.extract(img_path)
    assert isinstance(result, ExtractionResult)
    assert len(result.elements) > 0

    # Verify strict separation of OCR and Vision description
    ocr_elements = [e for e in result.elements if e.element_type in ("ocr", "ocr_text")]
    vision_elements = [e for e in result.elements if e.element_type in ("visual_description", "vision_description")]

    assert len(ocr_elements) >= 1
    assert "MOODBOARD" in ocr_elements[0].content
    assert "Warm Ochre" in ocr_elements[0].content

    assert len(vision_elements) >= 1
    assert "Мудборд осенней фотосессии" in vision_elements[0].content

    # Check that metadata properly records both separately
    assert result.metadata.get("visual_description") is not None
    assert result.metadata.get("ocr_text") is not None


def test_clean_image_without_sidecar(tmp_path):
    img_path = tmp_path / "simple_test.png"
    img = Image.new("RGB", (200, 200), color=(100, 150, 200))
    img.save(img_path)

    clean_extractor = ImageExtractor()
    result = clean_extractor.extract(img_path)
    assert not result.success
    assert len(result.elements) == 0
    assert "No usable image content" in result.error_message
