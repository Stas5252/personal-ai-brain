"""Regression checks for video truthfulness and content evidence policy."""
import ast
import inspect
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from src.brain.engines.content_engine import ContentEngine
from src.brain.knowledge.extractors.video_extractor import VideoExtractor


class VideoHonestyTests(unittest.TestCase):
    def test_metadata_probe_failure_is_not_fake_60_second_video(self):
        extractor = VideoExtractor()
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "ffprobe")):
            with self.assertRaises(RuntimeError):
                extractor.get_video_metadata(Path("missing.mp4"))

    def test_production_code_has_no_benchmark_sidecar_path(self):
        source = inspect.getsource(VideoExtractor)
        self.assertNotIn("pilot_corpus", source)
        self.assertNotIn("manifest.json", source)
        self.assertNotIn("duration_seconds=60.0", source)
        self.assertNotIn("Визуальный ключевой кадр: {f_path.name}", source)

    def test_filename_is_not_indexed_as_visual_knowledge(self):
        source = inspect.getsource(VideoExtractor)
        self.assertNotIn("Кадр: {closest_frame.name}", source)


class ContentHonestyTests(unittest.TestCase):
    def test_fallback_has_no_unverified_slots_or_statistics(self):
        result = ContentEngine().emergency_content_recovery(
            recent_projects=[], memories=[], use_llm=False
        )
        text = " ".join(str(item) for item in result)
        self.assertNotIn("8 из 10", text)
        self.assertNotIn("Осталось всего 3", text)
        self.assertIn("провер", text.lower())

    def test_content_engine_has_no_unconditional_slot_claim(self):
        source = inspect.getsource(ContentEngine)
        self.assertNotIn("Осталось всего 3 свободных слота", source)
        self.assertNotIn("8 из 10 моих съемок", source)
        ast.parse(source)


if __name__ == "__main__":
    unittest.main()
