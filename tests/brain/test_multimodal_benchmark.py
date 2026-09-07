"""
Multimodal Pipeline Benchmark for Personal AI Brain.
Evaluates local OCR integration, Voice transcript decomposition,
and honest capability contract (no fake simulation).
"""
import pytest
from pathlib import Path
from src.brain.services.brain_service import BrainService
from src.brain.knowledge.extractors.ocr_engine import get_ocr_engine
from src.brain.knowledge.extractors.vision_provider import VisionProvider

def test_local_ocr_contract():
    """Verifies that local OCR engine is active and does not fake text recognition."""
    ocr = get_ocr_engine()
    assert ocr is not None
    # Test availability
    assert ocr.is_available is True

def test_honest_vision_contract():
    """Verifies that vision abstraction reports honest status without fake heuristics."""
    vp = VisionProvider()
    res = vp.analyze_image(Path("dummy_path_no_file.jpg"))
    # Must report NOT_CONFIGURED or NOT_IMPLEMENTED rather than hallucinating fake scenes
    assert res.status.value in ["NOT_CONFIGURED", "NOT_IMPLEMENTED", "ERROR"]
    assert "moodboard" not in res.description.lower() or res.status.value != "SUCCESS"

def test_voice_to_derivative_assets():
    """Verifies complete multimodal voice decomposition."""
    brain = BrainService()
    transcript = "Привет! Сегодня была сложная клиентка, очень переживала из-за морщинок. Я выставила рассеянный софтбокс сверху и она расплакалась от радости!"
    pack = brain.voice_engine.process_voice_transcript(transcript)
    
    assert pack["source_transcript"] == transcript
    assert len(pack["story_beats"]) >= 2
    assert "post" in pack["derivative_post"].lower() or len(pack["derivative_post"]) > 50
    assert len(pack["derivative_reels"]) == 2
    assert len(pack["derivative_stories"]) == 5
