"""Lease-fenced worker-only knowledge ingestion pipeline."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.brain.knowledge.queue.fencing import LeaseFence, fenced_write, run_fenced_effect, transition
from src.brain.models.knowledge import ClassificationMethod, IngestionStatus, KnowledgeChunk, KnowledgeLayer


def _replace_sqlite(connection, source_id: str, chunks: List[KnowledgeChunk]) -> None:
    connection.execute("DELETE FROM knowledge_chunks_fts WHERE source_id = ?", (source_id,))
    connection.execute("DELETE FROM knowledge_chunks WHERE source_id = ?", (source_id,))
    for chunk in chunks:
        connection.execute(
            """INSERT INTO knowledge_chunks (
                id, source_id, layer, content, metadata_json, created_at,
                content_type, page_number, slide_number, sheet_name,
                start_time, end_time, heading_path, language, token_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                chunk.id, chunk.source_id, chunk.layer.value, chunk.content,
                chunk.metadata.model_dump_json(), chunk.created_at,
                chunk.content_type.value, chunk.page_number, chunk.slide_number,
                chunk.sheet_name, chunk.start_time, chunk.end_time,
                chunk.heading_path, chunk.language, chunk.token_count,
            ),
        )
        connection.execute(
            """INSERT INTO knowledge_chunks_fts
                (chunk_id, source_id, content, heading_path, sheet_name, layer)
                VALUES (?, ?, ?, ?, ?, ?)""",
            (
                chunk.id, chunk.source_id, chunk.content,
                chunk.heading_path or "", chunk.sheet_name or "", chunk.layer.value,
            ),
        )


def replace_source(vector_index, source_id: str, chunks, embeddings) -> None:
    """Upsert the exact vector snapshot, then delete obsolete tail IDs."""
    chunk_list = list(chunks)
    if any(chunk.source_id != source_id for chunk in chunk_list):
        raise ValueError("all chunks must belong to source_id")
    response = vector_index.collection.get(where={"source_id": source_id})
    existing = set((response or {}).get("ids") or [])
    expected = {chunk.id for chunk in chunk_list}
    if chunk_list:
        vector_index.upsert_chunks(chunk_list, embeddings=list(embeddings))
    obsolete = sorted(existing - expected)
    if obsolete:
        vector_index.delete_chunks(obsolete)


def ingest_file_fenced(
    factory,
    *,
    queue,
    fence: LeaseFence,
    file_path: Path,
    title: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    layer: Optional[KnowledgeLayer] = None,
    lease_seconds: int = 60,
) -> List[KnowledgeChunk]:
    """Run every persistent source/chunk/FTS/vector mutation under ``fence``."""
    path = Path(file_path)
    meta = dict(metadata or {})
    validation = factory.storage.validate_file(path)
    if not validation.is_valid:
        raise ValueError(f"File validation failed: {validation.error_message}")
    original = factory.storage.store_original(path, validation.sha256, validation.safe_filename)
    derived_dir = factory.storage.get_derived_dir(fence.source_id)
    source_title = title or path.stem.replace("_", " ").title()

    with fenced_write(queue, fence) as connection:
        updated = connection.execute(
            """UPDATE knowledge_sources SET title = ?, source_path = ?, storage_path = ?,
                derived_dir = ?, original_filename = ?, mime_type = ?, file_size = ?,
                sha256 = ?, p_hash = ?, ingestion_status = 'DISCOVERED',
                checkpoint_stage = 'DISCOVERED', error_message = NULL, metadata_json = ?
                WHERE source_id = ?""",
            (
                source_title, str(original), str(original), str(derived_dir),
                validation.safe_filename, validation.mime_type, validation.file_size,
                validation.sha256, validation.p_hash, json.dumps(meta), fence.source_id,
            ),
        )
        if updated.rowcount != 1:
            raise ValueError(f"Source {fence.source_id!r} not found")

    transition(queue, fence, IngestionStatus.VALIDATING, 0.1)
    transition(queue, fence, IngestionStatus.EXTRACTING, 0.2)
    extractor = factory._get_extractor(validation.extension, validation.mime_type)
    extraction = extractor.extract(original, fence.source_id, derived_dir)
    if not extraction.success:
        raise RuntimeError(f"Extraction failed: {extraction.error_message}")

    transition(queue, fence, IngestionStatus.NORMALIZING, 0.4)
    for element in extraction.elements:
        element.content = re.sub(r"\r\n|\r", "\n", element.content)
        element.content = re.sub(r"[\xa0\u200b\u202f\xad]+", " ", element.content)
        element.content = re.sub(r"[ \t]+", " ", element.content).strip()
    extraction.raw_text = re.sub(r"[\xa0\u200b\u202f\xad]+", " ", extraction.raw_text)

    transition(queue, fence, IngestionStatus.CLASSIFYING, 0.5)
    if layer is not None:
        assigned_layer, confidence, method = layer, 1.0, ClassificationMethod.MANUAL
    else:
        assigned_layer, confidence, method, _ = factory.classifier.classify(
            title=source_title, text_snippet=extraction.raw_text, metadata=meta
        )
    with fenced_write(queue, fence) as connection:
        connection.execute(
            """UPDATE knowledge_sources SET category = ?, confidence = ?,
                classification_method = ? WHERE source_id = ?""",
            (assigned_layer.value, confidence, method.value, fence.source_id),
        )

    transition(queue, fence, IngestionStatus.CHUNKING, 0.6)
    chunks = factory.chunker.chunk(
        extraction=extraction,
        layer=assigned_layer,
        source_title=source_title,
        base_metadata=meta,
    )
    transition(queue, fence, IngestionStatus.EMBEDDING, 0.8)
    embeddings = factory.embedding_provider.embed_documents([chunk.content for chunk in chunks])
    transition(queue, fence, IngestionStatus.INDEXING, 0.9)
    with fenced_write(queue, fence) as connection:
        _replace_sqlite(connection, fence.source_id, chunks)
    run_fenced_effect(
        queue,
        fence,
        lambda: replace_source(factory.vector_index, fence.source_id, chunks, embeddings),
        renew_for_seconds=lease_seconds,
    )
    transition(queue, fence, IngestionStatus.VERIFYING, 0.95)
    return chunks
