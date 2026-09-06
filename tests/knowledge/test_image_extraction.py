"""
Tests for Image Extraction Engine.
Verifies EXIF parsing, strict separation of factual OCR from AI vision descriptions, and sidecar support.
"""
import pytest
from pathlib import Path
from PIL import Image

from src.brain.knowledge.extractors.image_extractor import ImageExtractor
from src.brain.models.file_metadata import ExtractionResult

@pytest.fixture
def img_extractor():
    return ImageExtractor()


def test_image_extraction_with_sidecar(img_extractor):
    img_path = Path("tests/pilot_corpus/sample_moodboard.jpg")
    assert img_path.exists(), "Pilot moodboard image must exist"

    result = img_extractor.extract(img_path)
    assert isinstance(result, ExtractionResult)
    assert len(result.elements) > 0

    # Verify strict separation of OCR and Vision description
    ocr_elements = [e for e in result.elements if e.element_type == "ocr_text"]
    vision_elements = [e for e in result.elements if e.element_type == "visual_description"]

    assert len(ocr_elements) >= 1
    assert "MOODBOARD" in ocr_elements[0].content
    assert "Warm Ochre" in ocr_elements[0].content

    assert len(vision_elements) >= 1
    assert "Мудборд осенней фотосессии" in vision_elements[0].content

    # Check that metadata properly records both separately
    assert result.metadata.get("visual_description") is not None
    assert result.metadata.get("ocr_text") is not None


def test_clean_image_without_sidecar(img_extractor, tmp_path):
    img_path = tmp_path / "simple_test.png"
    img = Image.new("RGB", (200, 200), color=(100, 150, 200))
    img.save(img_path)

    result = img_extractor.extract(img_path)
    assert len(result.elements) >= 1
    assert result.elements[0].content_type.value == "image"
    assert result.metadata["width"] == 200
    assert result.metadata["height"] == 200
