"""
Knowledge Ingestion Factory — Central Orchestrator for Multimodal Knowledge Pipeline.
Source File -> Validation -> Deduplication -> Extraction -> Normalization ->
Classification -> Chunking -> Embeddings -> Vector & FTS Indexing -> Searchable Knowledge.
"""
import os
import re
import uuid
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any

from src.brain.db import get_connection
from src.brain.models.knowledge import (
    KnowledgeSource, KnowledgeChunk, KnowledgeLayer, KnowledgeMetadata,
    IngestionStatus, ClassificationMethod, ContentType, SourceTrace
)
from src.brain.knowledge.storage import StorageManager
from src.brain.knowledge.state_machine import IngestionStateMachine
from src.brain.knowledge.extractors.document_extractor import DocumentExtractor
from src.brain.knowledge.extractors.image_extractor import ImageExtractor
from src.brain.knowledge.extractors.audio_extractor import AudioExtractor
from src.brain.knowledge.extractors.video_extractor import VideoExtractor
from src.brain.knowledge.classifiers.layer_classifier import LayerClassifier
from src.brain.knowledge.chunkers.structure_chunker import StructureChunker
from src.brain.knowledge.indexing.vector_index import ChromaVectorIndex
from src.brain.knowledge.indexing.hybrid_search import HybridSearchEngine
from src.brain.knowledge.embeddings.implementations import get_embedding_provider

class KnowledgeIngestionFactory:
    def __init__(
        self,
        storage_manager: Optional[StorageManager] = None,
        vector_index: Optional[ChromaVectorIndex] = None
    ):
        self.storage = storage_manager or StorageManager()
        self.embedding_provider = get_embedding_provider()
        self.vector_index = vector_index or ChromaVectorIndex(embedding_provider=self.embedding_provider)
        self.hybrid_search = HybridSearchEngine(vector_index=self.vector_index)

        # Register modular extractors
        self.document_extractor = DocumentExtractor()
        self.image_extractor = ImageExtractor()
        self.audio_extractor = AudioExtractor()
        self.video_extractor = VideoExtractor(audio_extractor=self.audio_extractor)

        self.classifier = LayerClassifier()
        self.chunker = StructureChunker()

    def _get_extractor(self, ext: str, mime: str):
        if self.document_extractor.can_handle(ext, mime):
            return self.document_extractor
        if self.image_extractor.can_handle(ext, mime):
            return self.image_extractor
        if self.audio_extractor.can_handle(ext, mime):
            return self.audio_extractor
        if self.video_extractor.can_handle(ext, mime):
            return self.video_extractor
        raise ValueError(f"No extractor registered for file extension '{ext}' (MIME: {mime})")

    def ingest_file(
        self,
        file_path: Path,
        title: Optional[str] = None,
        layer: Optional[KnowledgeLayer] = None,
        override_layer: Optional[KnowledgeLayer] = None,
        metadata: Optional[Dict[str, Any]] = None,
        author: Optional[str] = None,
        subcategory: Optional[str] = None,
        tags: Optional[List[str]] = None,
        project: Optional[str] = None,
        client: Optional[str] = None,
        job_id: Optional[str] = None,
        force: bool = False,
        source_id: Optional[str] = None
    ) -> Tuple[KnowledgeSource, List[KnowledgeChunk]]:
        """
        Executes complete, idempotent ingestion pipeline for a single source file.
        Returns Tuple[KnowledgeSource, List[KnowledgeChunk]].
        """
        p = Path(file_path)
        effective_layer = override_layer or layer
        meta = dict(metadata or {})
        if author:
            meta["author"] = author
        if subcategory:
            meta["subcategory"] = subcategory
        if tags:
            meta["tags"] = tags
        if project:
            meta["project"] = project
        if client:
            meta["client"] = client
        if effective_layer:
            meta["layer"] = effective_layer.value

        # Step 1: Validation
        val = self.storage.validate_file(p)
        if not val.is_valid:
            raise ValueError(f"File validation failed: {val.error_message}")

        # Step 2: SHA-256 Deduplication Check
        existing = self.storage.check_duplicate(val.sha256, exclude_source_id=source_id)
        if existing and not force:
            dup_source_id = existing["source_id"]
            self.storage.record_duplicate_encounter(dup_source_id)
            conn = get_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM knowledge_chunks WHERE source_id = ?", (dup_source_id,))
            rows = c.fetchall()
            conn.close()
            existing_chunks = []
            for cr in rows:
                c_meta = json.loads(cr["metadata_json"] or "{}")
                existing_chunks.append(KnowledgeChunk(
                    id=cr["id"],
                    source_id=cr["source_id"],
                    layer=KnowledgeLayer(cr["layer"]),
                    content=cr["content"],
                    content_type=ContentType(cr["content_type"]) if cr["content_type"] else ContentType.TEXT,
                    page_number=cr["page_number"],
                    slide_number=cr["slide_number"],
                    sheet_name=cr["sheet_name"],
                    start_time=cr["start_time"],
                    end_time=cr["end_time"],
                    heading_path=cr["heading_path"],
                    metadata=KnowledgeMetadata(**c_meta),
                    created_at=cr["created_at"]
                ))
            src_obj = KnowledgeSource(
                source_id=dup_source_id,
                original_filename=existing.get("original_filename") or "unknown_file",
                mime_type=existing.get("mime_type") or "text/plain",
                file_size=existing.get("file_size") or 0,
                sha256=existing.get("sha256") or "",
                storage_path=existing.get("storage_path"),
                derived_dir=existing["derived_dir"],
                created_at=existing["timestamp"],
                ingestion_status=IngestionStatus.DUPLICATE,
                source_type=existing["type"] or "document",
                layer=KnowledgeLayer(existing["category"]),
                seen_count=existing["seen_count"] + 1
            )
            return src_obj, existing_chunks
        elif existing and force:
            self.delete_source(existing["source_id"], delete_original=False)

        # Step 3: Registration & Storage of Original
        source_id = source_id or str(uuid.uuid4())
        sm = IngestionStateMachine(source_id=source_id, job_id=job_id)
        now_str = datetime.now(timezone.utc).isoformat()
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        source_title = title or p.stem.replace("_", " ").title()
        orig_dest = self.storage.store_original(p, val.sha256, val.safe_filename)
        derived_dir = self.storage.get_derived_dir(source_id)

        # Detect source type category
        ext = val.extension.lower()
        if ext in [".mp4", ".mov", ".mkv", ".webm"]:
            source_type = "video"
        elif ext in [".mp3", ".wav", ".m4a", ".ogg", ".flac"]:
            source_type = "audio"
        elif ext in [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif"]:
            source_type = "image"
        else:
            source_type = "document"

        # Insert or update initial DISCOVERED record
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
        INSERT INTO knowledge_sources (
            source_id, title, author, date, type, category, subcategory,
            tags_json, project, client, language, source_path, timestamp,
            confidence, original_filename, mime_type, file_size, sha256,
            p_hash, storage_path, derived_dir, ingestion_status,
            processing_version, classification_method, seen_count,
            checkpoint_stage, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_id) DO UPDATE SET
            title = excluded.title,
            storage_path = excluded.storage_path,
            source_path = excluded.source_path,
            derived_dir = excluded.derived_dir,
            ingestion_status = excluded.ingestion_status,
            checkpoint_stage = excluded.checkpoint_stage,
            timestamp = excluded.timestamp
        """, (
            source_id, source_title, meta.get("author", "Owner"), date_str, source_type,
            (layer.value if layer else KnowledgeLayer.GLOBAL.value), meta.get("subcategory"),
            json.dumps(meta.get("tags", [])), meta.get("project"), meta.get("client"),
            meta.get("language", "ru"), str(orig_dest), now_str, 1.0,
            val.safe_filename, val.mime_type, val.file_size, val.sha256,
            val.p_hash, str(orig_dest), str(derived_dir), IngestionStatus.DISCOVERED.value,
            "v1.0", "rules", 1, "DISCOVERED", json.dumps(meta)
        ))
        conn.commit()
        conn.close()

        # Step 4: Extraction
        sm.transition(IngestionStatus.VALIDATING, progress=0.1)
        sm.transition(IngestionStatus.EXTRACTING, progress=0.2)
        extractor = self._get_extractor(val.extension, val.mime_type)
        extraction = extractor.extract(orig_dest, source_id, derived_dir)
        if not extraction.success:
            sm.transition(IngestionStatus.FAILED, error_message=extraction.error_message)
            raise RuntimeError(f"Extraction failed: {extraction.error_message}")

        # Step 5: Normalization
        sm.transition(IngestionStatus.NORMALIZING, progress=0.4)
        # Text normalization (clean extraneous whitespace, control characters, non-breaking spaces)
        for elem in extraction.elements:
            elem.content = re.sub(r"\r\n|\r", "\n", elem.content)
            elem.content = re.sub(r"[\xa0\u200b\u202f\xad]+", " ", elem.content)
            elem.content = re.sub(r"[ \t]+", " ", elem.content).strip()

        extraction.raw_text = re.sub(r"[\xa0\u200b\u202f\xad]+", " ", extraction.raw_text)

        # Step 6: Classification into 6 Layers
        sm.transition(IngestionStatus.CLASSIFYING, progress=0.5)
        if effective_layer:
            assigned_layer = effective_layer
            conf = 1.0
            method = ClassificationMethod.MANUAL
        else:
            assigned_layer, conf, method, reasoning = self.classifier.classify(
                title=source_title,
                text_snippet=extraction.raw_text,
                metadata=meta
            )

        conn = get_connection()
        c = conn.cursor()
        c.execute("""
        UPDATE knowledge_sources
        SET category = ?, confidence = ?, classification_method = ?
        WHERE source_id = ?
        """, (assigned_layer.value, conf, method.value, source_id))
        conn.commit()
        conn.close()

        # Step 7: Structure-Aware Chunking
        sm.transition(IngestionStatus.CHUNKING, progress=0.6)
        chunks = self.chunker.chunk(
            extraction=extraction,
            layer=assigned_layer,
            source_title=source_title,
            base_metadata=meta
        )

        # Step 8: Vector Embedding Generation
        sm.transition(IngestionStatus.EMBEDDING, progress=0.8)
        chunk_texts = [c.content for c in chunks]
        embeddings = self.embedding_provider.embed_documents(chunk_texts)

        # Step 9: Indexing into SQLite & ChromaDB
        sm.transition(IngestionStatus.INDEXING, progress=0.9)
        conn = get_connection()
        c = conn.cursor()

        for chunk in chunks:
            c.execute("""
            INSERT OR REPLACE INTO knowledge_chunks (
                id, source_id, layer, content, metadata_json, created_at,
                content_type, page_number, slide_number, sheet_name,
                start_time, end_time, heading_path, language, token_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                chunk.id, chunk.source_id, chunk.layer.value, chunk.content,
                chunk.metadata.model_dump_json(), chunk.created_at,
                chunk.content_type.value, chunk.page_number, chunk.slide_number,
                chunk.sheet_name, chunk.start_time, chunk.end_time,
                chunk.heading_path, chunk.language, chunk.token_count
            ))

            # Synchronize FTS5 virtual table
            c.execute("""
            INSERT INTO knowledge_chunks_fts (chunk_id, source_id, content, heading_path, sheet_name, layer)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (
                chunk.id, chunk.source_id, chunk.content,
                chunk.heading_path or "", chunk.sheet_name or "", chunk.layer.value
            ))

        conn.commit()
        conn.close()

        # Upsert into ChromaDB
        self.vector_index.upsert_chunks(chunks, embeddings=embeddings)

        # Step 10: Verification & Completion
        sm.transition(IngestionStatus.VERIFYING, progress=0.95)
        sm.transition(IngestionStatus.COMPLETED, progress=1.0)

        source_obj = KnowledgeSource(
            source_id=source_id,
            original_filename=val.safe_filename,
            mime_type=val.mime_type,
            file_size=val.file_size,
            sha256=val.sha256,
            p_hash=val.p_hash,
            storage_path=str(orig_dest),
            derived_dir=str(derived_dir),
            created_at=now_str,
            ingestion_status=IngestionStatus.COMPLETED,
            source_type=source_type,
            layer=assigned_layer,
            confidence=conf,
            classification_method=method,
            metadata=meta
        )
        return source_obj, chunks

    def reprocess(self, source_id: str) -> KnowledgeSource:
        """Reprocesses an existing source file from scratch using the stored original."""
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM knowledge_sources WHERE source_id = ?", (source_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            raise ValueError(f"Source '{source_id}' not found")

        storage_path = Path(row["storage_path"])
        if not storage_path.exists():
            conn.close()
            raise FileNotFoundError(f"Original file missing at {storage_path}")

        # Delete existing chunks and vector entries
        self.delete_source(source_id, delete_original=False)
        conn.close()

        # Re-ingest
        src, _ = self.ingest_file(
            file_path=storage_path,
            title=row["title"],
            layer=KnowledgeLayer(row["category"]) if row["category"] else None,
            metadata=json.loads(row["metadata_json"] or "{}"),
            force=True
        )
        return src

    def delete_source(self, source_id: str, delete_original: bool = True):
        """Deletes chunks, vector entries, FTS entries, and optionally original file."""
        # 1. Delete from ChromaDB
        self.vector_index.delete_by_source(source_id)

        # 2. Delete from SQLite
        conn = get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM knowledge_chunks_fts WHERE source_id = ?", (source_id,))
        c.execute("DELETE FROM knowledge_chunks WHERE source_id = ?", (source_id,))
        c.execute("DELETE FROM ingestion_jobs WHERE source_id = ?", (source_id,))
        
        if delete_original:
            c.execute("SELECT storage_path FROM knowledge_sources WHERE source_id = ?", (source_id,))
            r = c.fetchone()
            if r and r["storage_path"] and Path(r["storage_path"]).exists():
                try:
                    os.remove(r["storage_path"])
                except Exception:
                    pass
        c.execute("DELETE FROM knowledge_sources WHERE source_id = ?", (source_id,))

        conn.commit()
        conn.close()

        # 3. Clean up derived files
        self.storage.delete_source_files(source_id)

    def scan_directory(
        self,
        dir_path: Path,
        recursive: bool = True,
        default_layer: Optional[KnowledgeLayer] = None
    ) -> List[KnowledgeSource]:
        """Scans directory for supported files and ingests them."""
        p = Path(dir_path)
        if not p.exists() or not p.is_dir():
            raise ValueError(f"Directory not found: {dir_path}")

        pattern = "**/*" if recursive else "*"
        sources = []
        for item in p.glob(pattern):
            if item.is_file() and not item.name.startswith("."):
                ext = item.suffix.lower()
                from src.brain.config import ALLOWED_EXTENSIONS
                if ext in ALLOWED_EXTENSIONS:
                    try:
                        src, _ = self.ingest_file(item, layer=default_layer)
                        sources.append(src)
                    except Exception as e:
                        pass
        return sources

    def search(
        self,
        query: str,
        layer: Optional[KnowledgeLayer] = None,
        project_id: Optional[str] = None,
        client_id: Optional[str] = None,
        top_k: int = 5
    ) -> List[Tuple[KnowledgeChunk, float, SourceTrace]]:
        """Searches multimodal knowledge base via Hybrid Search Engine."""
        return self.hybrid_search.search(
            query=query,
            layer=layer,
            project_id=project_id,
            client_id=client_id,
            top_k=top_k
        )
