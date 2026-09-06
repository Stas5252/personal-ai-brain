"""
Structure-Aware Chunker for Knowledge Ingestion Factory.
Preserves document hierarchy, tables, lists, slide boundaries, and video timestamps.
"""
import re
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from src.brain.config import CHUNK_TARGET_CHARS, CHUNK_OVERLAP_CHARS
from src.brain.models.knowledge import (
    KnowledgeChunk, KnowledgeLayer, KnowledgeMetadata, ContentType
)
from src.brain.models.file_metadata import ExtractionResult, ExtractedElement

class StructureChunker:
    def __init__(self, target_chars: int = CHUNK_TARGET_CHARS, overlap_chars: int = CHUNK_OVERLAP_CHARS):
        self.target_chars = target_chars
        self.overlap_chars = overlap_chars

    def chunk(
        self,
        extraction: ExtractionResult,
        layer: KnowledgeLayer,
        source_title: str,
        base_metadata: Optional[Dict[str, Any]] = None
    ) -> List[KnowledgeChunk]:
        """Converts extracted structural elements into self-contained, traceable chunks."""
        chunks: List[KnowledgeChunk] = []
        source_id = extraction.source_id
        now_str = datetime.now(timezone.utc).isoformat()
        chunk_idx = 1

        elements = extraction.elements
        if not elements and extraction.raw_text:
            # Fallback for plain raw text
            return self._chunk_plain_text(extraction.raw_text, source_id, layer, source_title, now_str)

        current_text_buffer: List[str] = []
        current_len = 0
        current_heading_path = None
        current_page = None

        for elem in elements:
            # 1. Independent atomic elements: tables, slides, video/audio fusion segments
            if elem.element_type in ["table", "slide", "fusion", "transcript_segment", "ocr", "vision_description"]:
                # Flush any accumulated paragraph buffer
                if current_text_buffer:
                    chunk_text = "\n\n".join(current_text_buffer).strip()
                    if chunk_text:
                        chunks.append(self._create_chunk(
                            chunk_id=f"{source_id}-chk-{chunk_idx}",
                            source_id=source_id,
                            layer=layer,
                            content=chunk_text,
                            content_type=ContentType.TEXT,
                            page_number=current_page,
                            heading_path=current_heading_path,
                            source_title=source_title,
                            created_at=now_str
                        ))
                        chunk_idx += 1
                    current_text_buffer = []
                    current_len = 0

                # Determine content type
                c_type = ContentType.TEXT
                if elem.element_type == "table":
                    c_type = ContentType.TABLE
                elif elem.element_type == "ocr":
                    c_type = ContentType.OCR
                elif elem.element_type == "vision_description":
                    c_type = ContentType.VISION_DESCRIPTION
                elif elem.element_type == "transcript_segment":
                    c_type = ContentType.TRANSCRIPT
                elif elem.element_type == "fusion":
                    c_type = ContentType.FUSION

                chunks.append(self._create_chunk(
                    chunk_id=f"{source_id}-chk-{chunk_idx}",
                    source_id=source_id,
                    layer=layer,
                    content=elem.content.strip(),
                    content_type=c_type,
                    page_number=elem.page_number,
                    slide_number=elem.slide_number,
                    sheet_name=elem.sheet_name,
                    start_time=elem.start_time,
                    end_time=elem.end_time,
                    heading_path=elem.heading_path,
                    extra_meta=elem.metadata,
                    source_title=source_title,
                    created_at=now_str
                ))
                chunk_idx += 1
                continue

            # 2. Text elements: headings and paragraphs
            if elem.element_type == "heading":
                current_heading_path = elem.content
                current_page = elem.page_number
                current_text_buffer.append(f"## {elem.content}")
                current_len += len(elem.content) + 5
            else:
                p_text = elem.content.strip()
                if not p_text:
                    continue
                current_page = elem.page_number or current_page

                # Check if buffer exceeded target
                if current_len + len(p_text) > self.target_chars and current_text_buffer:
                    chunk_text = "\n\n".join(current_text_buffer).strip()
                    chunks.append(self._create_chunk(
                        chunk_id=f"{source_id}-chk-{chunk_idx}",
                        source_id=source_id,
                        layer=layer,
                        content=chunk_text,
                        content_type=ContentType.TEXT,
                        page_number=current_page,
                        heading_path=current_heading_path,
                        source_title=source_title,
                        created_at=now_str
                    ))
                    chunk_idx += 1

                    # Keep heading context in next chunk if heading path is set
                    current_text_buffer = [f"## {current_heading_path}"] if current_heading_path else []
                    current_len = len(current_text_buffer[0]) if current_text_buffer else 0

                current_text_buffer.append(p_text)
                current_len += len(p_text)

        # Flush trailing buffer
        if current_text_buffer:
            chunk_text = "\n\n".join(current_text_buffer).strip()
            if chunk_text:
                chunks.append(self._create_chunk(
                    chunk_id=f"{source_id}-chk-{chunk_idx}",
                    source_id=source_id,
                    layer=layer,
                    content=chunk_text,
                    content_type=ContentType.TEXT,
                    page_number=current_page,
                    heading_path=current_heading_path,
                    source_title=source_title,
                    created_at=now_str
                ))

        return chunks

    def _create_chunk(
        self,
        chunk_id: str,
        source_id: str,
        layer: KnowledgeLayer,
        content: str,
        content_type: ContentType,
        source_title: str,
        created_at: str,
        page_number: Optional[int] = None,
        slide_number: Optional[int] = None,
        sheet_name: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        heading_path: Optional[str] = None,
        extra_meta: Optional[Dict[str, Any]] = None
    ) -> KnowledgeChunk:
        meta = KnowledgeMetadata(
            source_id=source_id,
            title=source_title,
            category=layer,
            page_number=page_number,
            slide_number=slide_number,
            sheet_name=sheet_name,
            start_time=start_time,
            end_time=end_time,
            heading_path=heading_path,
            confidence=1.0,
            tags=extra_meta.get("tags", []) if extra_meta else []
        )
        # Approximate tokens (Russian/English ~4 chars per token)
        token_count = max(1, len(content) // 4)

        return KnowledgeChunk(
            id=chunk_id,
            source_id=source_id,
            layer=layer,
            content=content,
            content_type=content_type,
            page_number=page_number,
            slide_number=slide_number,
            sheet_name=sheet_name,
            start_time=start_time,
            end_time=end_time,
            heading_path=heading_path,
            token_count=token_count,
            metadata=meta,
            created_at=created_at
        )

    def _chunk_plain_text(
        self, text: str, source_id: str, layer: KnowledgeLayer, title: str, now_str: str
    ) -> List[KnowledgeChunk]:
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks = []
        for idx, p in enumerate(paragraphs):
            chunks.append(self._create_chunk(
                chunk_id=f"{source_id}-chk-{idx+1}",
                source_id=source_id,
                layer=layer,
                content=p,
                content_type=ContentType.TEXT,
                source_title=title,
                created_at=now_str
            ))
        return chunks
