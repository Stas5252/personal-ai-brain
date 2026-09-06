"""
Tests for Audio Extraction Engine.
Covers audio normalization via FFmpeg, timestamps, segments, language detection, and sidecar loading.
"""
import pytest
from pathlib import Path
from src.brain.knowledge.extractors.audio_extractor import AudioExtractor
from src.brain.models.file_metadata import ExtractionResult

@pytest.fixture
def audio_extractor():
    return AudioExtractor()


def test_audio_normalization_ffmpeg(audio_extractor, tmp_path):
    wav_path = Path("tests/pilot_corpus/sample_speech_ru.wav")
    assert wav_path.exists(), "Pilot speech WAV must exist"

    normalized_wav = tmp_path / "normalized.wav"
    ok = audio_extractor.normalize_audio(wav_path, normalized_wav)
    assert ok, "Audio normalization must succeed"
    assert normalized_wav.exists()
    assert normalized_wav.stat().st_size > 0


def test_audio_extraction_with_sidecar(audio_extractor, tmp_path):
    wav_path = Path("tests/pilot_corpus/sample_speech_ru.wav")
    assert wav_path.exists()

    result = audio_extractor.extract(
        file_path=wav_path,
        source_id="test-audio-src",
        derived_dir=tmp_path
    )
    assert isinstance(result, ExtractionResult)
    assert result.success
    assert len(result.elements) >= 2

    # Check timestamps and Russian speech content
    first_seg = result.elements[0]
    assert first_seg.start_time is not None
    assert first_seg.end_time is not None
    assert "тайминг на пятницу" in first_seg.content.lower()

    second_seg = result.elements[1]
    assert "циклорама" in second_seg.content.lower()
    assert result.media_info.get("language") == "ru"
