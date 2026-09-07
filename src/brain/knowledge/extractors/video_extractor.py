"""Honest video ingestion with timestamped speech and optional frame analysis.

A video filename is not visual knowledge. This extractor indexes only real
transcript segments or results from an explicitly supplied frame analyzer.
Metadata failures are errors, never a fabricated 60-second 1080p video.
"""
import json
import re
import subprocess
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple, Callable

from src.brain.config import (
    VIDEO_FRAME_INTERVAL_SECONDS, VIDEO_MAX_FRAMES_PER_MINUTE,
    VIDEO_SCENE_DETECTION_THRESHOLD,
)
from src.brain.knowledge.extractors.base import BaseExtractor
from src.brain.knowledge.extractors.audio_extractor import AudioExtractor
from src.brain.models.file_metadata import ExtractionResult, ExtractedElement, VideoMetadata, SceneInfo


class SceneDetector:
    def __init__(self, threshold: float = VIDEO_SCENE_DETECTION_THRESHOLD):
        if not 0 <= threshold <= 1:
            raise ValueError("scene threshold must be between 0 and 1")
        self.threshold = threshold

    def detect_scenes(self, video_path: Path, duration: float) -> List[SceneInfo]:
        if duration <= 0:
            return []
        try:
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-i", str(video_path), "-filter:v",
                 f"select='gt(scene,{self.threshold})',showinfo", "-f", "null", "-"],
                capture_output=True, text=True, timeout=60, check=False)
            points = [0.0] + [float(x) for x in re.findall(r"pts_time:([0-9.]+)", result.stderr)] + [duration]
            points = sorted({max(0.0, min(duration, x)) for x in points})
            return [SceneInfo(scene_index=i + 1, start_time=a, end_time=b)
                    for i, (a, b) in enumerate(zip(points, points[1:])) if b > a]
        except (OSError, subprocess.SubprocessError, ValueError):
            return [SceneInfo(scene_index=1, start_time=0.0, end_time=duration)]


class VideoExtractor(BaseExtractor):
    SUPPORTED_EXTS = {".mp4", ".mov", ".mkv", ".webm"}

    def __init__(self, frame_interval_seconds: float = VIDEO_FRAME_INTERVAL_SECONDS,
                 scene_threshold: float = VIDEO_SCENE_DETECTION_THRESHOLD,
                 audio_extractor: Optional[AudioExtractor] = None,
                 scene_detector: Optional[SceneDetector] = None,
                 frame_analyzer: Optional[Callable[[Path], Any]] = None,
                 max_duration_seconds: float = 12 * 60 * 60):
        if frame_interval_seconds <= 0 or max_duration_seconds <= 0:
            raise ValueError("video limits must be positive")
        self.frame_interval_seconds = frame_interval_seconds
        self.max_duration_seconds = max_duration_seconds
        self.audio_extractor = audio_extractor or AudioExtractor()
        self.scene_detector = scene_detector or SceneDetector(scene_threshold)
        self.frame_analyzer = frame_analyzer

    def can_handle(self, extension: str, mime_type: str) -> bool:
        return extension.lower() in self.SUPPORTED_EXTS

    def get_video_metadata(self, video_path: Path) -> VideoMetadata:
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(video_path)],
                capture_output=True, text=True, timeout=60, check=False)
            if result.returncode != 0:
                raise ValueError(result.stderr.strip()[:300] or "ffprobe failed")
            data = json.loads(result.stdout)
            streams = data.get("streams", [])
            video = next((s for s in streams if s.get("codec_type") == "video"), None)
            if not video:
                raise ValueError("video stream not found")
            fmt = data.get("format", {})
            duration = float(fmt.get("duration") or video.get("duration") or 0)
            if not 0 < duration <= self.max_duration_seconds:
                raise ValueError("video duration is missing or exceeds configured limit")
            rate = video.get("r_frame_rate", "0/1").split("/")
            fps = float(rate[0]) / float(rate[1]) if len(rate) == 2 and float(rate[1]) else 0.0
            if not video.get("width") or not video.get("height"):
                raise ValueError("video dimensions are missing")
            audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
            bitrate = fmt.get("bit_rate")
            return VideoMetadata(duration_seconds=duration, fps=fps,
                                 width=int(video["width"]), height=int(video["height"]),
                                 codec=video.get("codec_name", "unknown"),
                                 audio_codec=audio.get("codec_name") if audio else None,
                                 has_audio=audio is not None,
                                 bitrate=int(bitrate) if bitrate else None)
        except (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise RuntimeError("Video metadata unavailable: " + str(exc)) from exc

    def extract_audio_track(self, video_path: Path, output_wav: Path) -> bool:
        try:
            result = subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-i", str(video_path), "-vn", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(output_wav)],
                capture_output=True, text=True, timeout=300, check=False)
            return result.returncode == 0 and output_wav.is_file() and output_wav.stat().st_size > 0
        except (OSError, subprocess.SubprocessError):
            return False

    def sample_keyframes(self, video_path: Path, keyframes_dir: Path, duration: float) -> List[Tuple[float, Path]]:
        keyframes_dir.mkdir(parents=True, exist_ok=True)
        interval = max(1.0, self.frame_interval_seconds)
        max_frames = max(1, int((duration / 60.0) * VIDEO_MAX_FRAMES_PER_MINUTE))
        count = min(max_frames, max(1, int(duration / interval) + 1))
        if count == 1:
            timestamps = [0.0]
        else:
            timestamps = [round(i * duration / (count - 1), 3) for i in range(count)]
        sampled = []
        for index, timestamp in enumerate(timestamps):
            output = keyframes_dir / f"frame_{index:04d}.jpg"
            try:
                result = subprocess.run(
                    ["ffmpeg", "-y", "-hide_banner", "-ss", str(timestamp), "-i", str(video_path),
                     "-frames:v", "1", "-q:v", "2", str(output)],
                    capture_output=True, text=True, timeout=90, check=False)
                if result.returncode == 0 and output.is_file() and output.stat().st_size > 0:
                    sampled.append((timestamp, output))
            except (OSError, subprocess.SubprocessError):
                continue
        return sampled

    def _format_time(self, seconds: float) -> str:
        minutes, remainder = divmod(max(0.0, seconds), 60)
        return f"{int(minutes):02d}:{int(remainder):02d}"

    def _analyze_frame(self, path: Path) -> Optional[Dict[str, Any]]:
        if self.frame_analyzer is None:
            return None
        try:
            result = self.frame_analyzer(path)
            if isinstance(result, str) and result.strip():
                return {"description": result.strip(), "provenance": "frame_analyzer"}
            if isinstance(result, dict) and isinstance(result.get("description"), str) and result["description"].strip():
                return {"description": result["description"].strip(), "provenance": "frame_analyzer",
                        "ocr_text": result.get("ocr_text", "")}
        except Exception:
            return None
        return None

    def extract(self, file_path: Path, source_id: str, derived_dir: Path) -> ExtractionResult:
        path = Path(file_path)
        info = {"format": path.suffix.lstrip(".").upper(), "content_coverage": "NONE",
                "warnings": [], "sidecar_used": False}
        audio_wav = Path(derived_dir) / "extracted_audio.wav"
        keyframes_dir = Path(derived_dir) / "keyframes"
        try:
            if not path.is_file() or not self.can_handle(path.suffix, ""):
                raise ValueError("video file does not exist or extension is unsupported")
            meta = self.get_video_metadata(path)
            info.update(duration_seconds=meta.duration_seconds, fps=meta.fps,
                        resolution=f"{meta.width}x{meta.height}", has_audio=meta.has_audio)
            samples = self.sample_keyframes(path, keyframes_dir, meta.duration_seconds)
            audio_result = None
            if meta.has_audio and self.extract_audio_track(path, audio_wav):
                audio_result = self.audio_extractor.extract(audio_wav, source_id, Path(derived_dir))
            elif meta.has_audio:
                info["warnings"].append("Audio extraction failed")
            elements: List[ExtractedElement] = []
            analyzed_frames: Dict[float, Dict[str, Any]] = {}
            for timestamp, frame in samples:
                analysis = self._analyze_frame(frame)
                if analysis:
                    analyzed_frames[timestamp] = analysis
            if audio_result and audio_result.success and audio_result.elements:
                for segment in audio_result.elements:
                    start = float(segment.start_time or 0.0)
                    end = float(segment.end_time or start)
                    nearest = min(samples, key=lambda item: abs(item[0] - start), default=None)
                    content = f"Видео [{self._format_time(start)} - {self._format_time(end)}] Речь: {segment.content.strip()}"
                    metadata = {"timestamp_range": f"{self._format_time(start)} - {self._format_time(end)}",
                                "has_speech": True, "provenance": "transcript"}
                    if nearest and nearest[0] in analyzed_frames:
                        analysis = analyzed_frames[nearest[0]]
                        content += "\nВизуальный анализ кадра (интерпретация): " + analysis["description"]
                        if analysis.get("ocr_text"):
                            content += "\nOCR кадра: " + str(analysis["ocr_text"])
                        metadata["frame_timestamp"] = nearest[0]
                    elements.append(ExtractedElement(element_type="fusion", content=content,
                                                     start_time=start, end_time=end,
                                                     heading_path=metadata["timestamp_range"], metadata=metadata))
            else:
                for timestamp, analysis in analyzed_frames.items():
                    end = min(meta.duration_seconds, timestamp + self.frame_interval_seconds)
                    elements.append(ExtractedElement(
                        element_type="fusion", content=f"Видео [{self._format_time(timestamp)} - {self._format_time(end)}] Визуальный анализ (интерпретация): {analysis['description']}",
                        start_time=timestamp, end_time=end,
                        heading_path=self._format_time(timestamp),
                        metadata={"timestamp_range": f"{self._format_time(timestamp)} - {self._format_time(end)}",
                                  "provenance": "frame_analyzer", "frame_timestamp": timestamp,
                                  "ocr_text": analysis.get("ocr_text", "")}))
            info.update(keyframes_count=len(samples), analyzed_frames=len(analyzed_frames),
                        transcript_segments=len(audio_result.elements) if audio_result and audio_result.elements else 0)
            if not elements:
                info["warnings"].append("No transcript or frame analysis was available")
                return ExtractionResult(source_id=source_id, success=False, elements=[], raw_text="",
                                        duration_seconds=meta.duration_seconds, media_info=info,
                                        error_message="Video has no usable transcript or visual analysis")
            info["content_coverage"] = "TRANSCRIPT_AND_FRAMES" if analyzed_frames and audio_result and audio_result.elements else ("TRANSCRIPT" if audio_result and audio_result.elements else "FRAMES")
            return ExtractionResult(source_id=source_id, success=True, elements=elements,
                                    raw_text="\n\n".join(e.content for e in elements),
                                    duration_seconds=meta.duration_seconds, media_info=info)
        except Exception as exc:
            return ExtractionResult(source_id=source_id, success=False, media_info=info,
                                    error_message="Video extraction failed: " + str(exc))
        finally:
            try:
                if audio_wav.exists():
                    audio_wav.unlink()
            except OSError:
                pass
