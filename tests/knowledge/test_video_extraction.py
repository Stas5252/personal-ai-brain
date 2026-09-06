"""
Tests for Video Extraction Engine.
Covers container metadata via FFprobe, keyframe extraction, audio track separation, and semantic fusion.
"""
import pytest
from pathlib import Path
from src.brain.knowledge.extractors.video_extractor import VideoExtractor
from src.brain.knowledge.extractors.audio_extractor import AudioExtractor
from src.brain.models.file_metadata import ExtractionResult, VideoMetadata

@pytest.fixture
def video_extractor():
    return VideoExtractor(audio_extractor=AudioExtractor())


def test_video_metadata_ffprobe(video_extractor):
    mp4_path = Path("tests/pilot_corpus/sample_lesson_ru.mp4")
    assert mp4_path.exists(), "Pilot video MP4 must exist"

    meta = video_extractor.get_video_metadata(mp4_path)
    assert isinstance(meta, VideoMetadata)
    assert meta.duration_seconds > 0
    assert meta.width == 640
    assert meta.height == 360
    assert meta.has_audio


def test_video_audio_track_extraction(video_extractor, tmp_path):
    mp4_path = Path("tests/pilot_corpus/sample_lesson_ru.mp4")
    extracted_wav = tmp_path / "video_soundtrack.wav"

    ok = video_extractor.extract_audio_track(mp4_path, extracted_wav)
    assert ok
    assert extracted_wav.exists()
    assert extracted_wav.stat().st_size > 0


def test_video_extraction_with_manifest_fusion(video_extractor, tmp_path):
    mp4_path = Path("tests/pilot_corpus/sample_lesson_ru.mp4")

    result = video_extractor.extract(
        file_path=mp4_path,
        source_id="test-vid-src",
        derived_dir=tmp_path
    )
    assert isinstance(result, ExtractionResult)
    assert result.success
    assert len(result.elements) >= 2

    # Check that fusion chunks contain start/end timestamps and speech + visual description
    elem1 = result.elements[0]
    assert elem1.start_time is not None
    assert elem1.end_time is not None
    assert "жесткий свет" in elem1.content.lower()

    elem2 = result.elements[1]
    assert "граница" in elem2.content.lower() or "светотен" in elem2.content.lower()
