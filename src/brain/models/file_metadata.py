"""
File Metadata and Extraction Models for Knowledge Ingestion Factory.
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class FileValidationResult(BaseModel):
    is_valid: bool
    mime_type: str = ""
    extension: str = ""
    file_size: int = 0
    sha256: str = ""
    p_hash: Optional[str] = None
    safe_filename: str = ""
    error_message: Optional[str] = None

class ExtractedElement(BaseModel):
    element_type: str # heading, paragraph, table, list_item, slide, speaker_note, frame, transcript_segment
    content: str
    page_number: Optional[int] = None
    slide_number: Optional[int] = None
    sheet_name: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    heading_path: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def content_type(self):
        class _CT:
            def __init__(self, val):
                self.value = val
        if "image" in self.element_type or "ocr" in self.element_type or "visual" in self.element_type:
            return _CT("image")
        elif "audio" in self.element_type or "transcript" in self.element_type:
            return _CT("audio")
        elif "video" in self.element_type or "frame" in self.element_type:
            return _CT("video")
        elif "table" in self.element_type:
            return _CT("table")
        else:
            return _CT("text")

class ExtractionResult(BaseModel):
    source_id: str
    success: bool
    elements: List[ExtractedElement] = Field(default_factory=list)
    raw_text: str = ""
    page_count: Optional[int] = None
    duration_seconds: Optional[float] = None
    media_info: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None

    @property
    def metadata(self) -> Dict[str, Any]:
        return self.media_info

    def get_full_text(self) -> str:
        text = self.raw_text if self.raw_text else "\n\n".join(e.content for e in self.elements if e.content)
        return text.replace("\xa0", " ").replace("\xad", "")

class VideoMetadata(BaseModel):
    duration_seconds: float = 0.0
    fps: float = 0.0
    width: int = 0
    height: int = 0
    codec: str = ""
    audio_codec: Optional[str] = None
    has_audio: bool = False
    bitrate: Optional[int] = None

class SceneInfo(BaseModel):
    scene_index: int
    start_time: float
    end_time: float
    keyframe_path: Optional[str] = None
    ocr_text: Optional[str] = None
    visual_summary: Optional[str] = None

class AudioSegment(BaseModel):
    start_time: float
    end_time: float
    text: str
    confidence: float = 1.0
    speaker: Optional[str] = None
