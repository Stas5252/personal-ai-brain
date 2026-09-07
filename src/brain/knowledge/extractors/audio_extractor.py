"""Real transcription. Production never reads test transcripts or invents speech."""
import json
import math
import subprocess
from pathlib import Path
from typing import List, Tuple
from src.brain.knowledge.extractors.base import BaseExtractor
from src.brain.models.file_metadata import ExtractionResult, ExtractedElement, AudioSegment


class AudioExtractor(BaseExtractor):
    SUPPORTED_EXTS = {'.mp3', '.wav', '.m4a', '.ogg', '.flac'}

    def __init__(self, whisper_model_size='base', allow_sidecar=False):
        self.whisper_model_size = whisper_model_size
        self.allow_sidecar = allow_sidecar
        self._model = None

    def can_handle(self, extension, mime_type):
        return extension.lower() in self.SUPPORTED_EXTS

    def normalize_audio(self, input_path, output_wav_path):
        try:
            result = subprocess.run(
                ['ffmpeg', '-nostdin', '-y', '-i', str(input_path), '-ar', '16000',
                 '-ac', '1', '-c:a', 'pcm_s16le', str(output_wav_path)],
                capture_output=True, timeout=120,
            )
            return result.returncode == 0 and output_wav_path.is_file()
        except (OSError, subprocess.TimeoutExpired):
            return False

    def extract(self, file_path: Path, source_id: str, derived_dir: Path) -> ExtractionResult:
        path = Path(file_path)
        try:
            if not path.is_file() or not path.stat().st_size:
                raise ValueError('Audio file is missing or empty.')
            derived_dir = Path(derived_dir)
            derived_dir.mkdir(parents=True, exist_ok=True)
            sidecar = path.with_suffix(path.suffix + '.transcript.json')
            if self.allow_sidecar and sidecar.is_file():
                segments, language = self._load_sidecar_transcript(sidecar)
            else:
                normalized = derived_dir / 'normalized_audio.wav'
                target = normalized if self.normalize_audio(path, normalized) else path
                segments, language = self._transcribe_with_whisper(target)
            segments = [s for s in segments if s.text.strip()]
            if not segments:
                raise ValueError('No intelligible speech detected.')
            elements = [ExtractedElement(
                element_type='transcript_segment', content=s.text,
                start_time=s.start_time, end_time=s.end_time,
                metadata={'language': language, 'confidence': s.confidence},
            ) for s in segments]
            return ExtractionResult(
                source_id=source_id, success=True, elements=elements,
                raw_text='\n'.join(s.text for s in segments), duration_seconds=segments[-1].end_time,
                media_info={'language': language, 'segments_count': len(segments),
                            'source': 'sidecar' if self.allow_sidecar and sidecar.is_file() else 'whisper'},
            )
        except Exception as exc:
            return ExtractionResult(source_id=source_id, success=False,
                                    error_message=f'Transcription failed ({type(exc).__name__}).')

    def _load_sidecar_transcript(self, path: Path) -> Tuple[List[AudioSegment], str]:
        data = json.loads(path.read_text(encoding='utf-8'))
        segments = [AudioSegment(start_time=float(s['start']), end_time=float(s['end']),
                                 text=s['text'], confidence=float(s.get('confidence', 0.95)))
                    for s in data.get('segments', [])]
        return segments, data.get('language', 'ru')

    def _transcribe_with_whisper(self, audio_path: Path) -> Tuple[List[AudioSegment], str]:
        from faster_whisper import WhisperModel
        if self._model is None:
            self._model = WhisperModel(self.whisper_model_size, device='cpu', compute_type='int8')
        stream, info = self._model.transcribe(str(audio_path), beam_size=5, vad_filter=True)
        segments = [AudioSegment(start_time=round(s.start, 2), end_time=round(s.end, 2),
                                 text=s.text.strip(), confidence=min(1.0, max(0.0, math.exp(s.avg_logprob))))
                    for s in stream]
        return segments, info.language
