"""
Tests for Structure-Aware Chunker.
Verifies heading hierarchy, table atomicity, slide preservation, and video timestamp metadata.
"""
import pytest
from src.brain.knowledge.chunkers.structure_chunker import StructureChunker
from src.brain.models.file_metadata import ExtractionResult, ExtractedElement
from src.brain.models.knowledge import KnowledgeLayer, ContentType

@pytest.fixture
def chunker():
    return StructureChunker(target_chars=300, overlap_chars=50)


def test_table_atomicity_preserved(chunker):
    # Tables must be preserved as single chunks and not split randomly
    table_content = "Таблица цен: Пакет А - 10000 руб, Пакет Б - 20000 руб, Пакет В - 30000 руб"
    extraction = ExtractionResult(
        source_id="src-table-test",
        success=True,
        elements=[
            ExtractedElement(element_type="table", content=table_content, sheet_name="Прайс")
        ]
    )

    chunks = chunker.chunk(extraction, KnowledgeLayer.BUSINESS, "Таблица Цен")
    assert len(chunks) == 1
    assert chunks[0].content_type == ContentType.TABLE
    assert chunks[0].content == table_content
    assert chunks[0].sheet_name == "Прайс"


def test_slide_and_notes_preservation(chunker):
    extraction = ExtractionResult(
        source_id="src-pptx-test",
        success=True,
        elements=[
            ExtractedElement(
                element_type="slide",
                content="Слайд 2: Коммерческие пакеты\n• День: 120 000 руб",
                slide_number=2
            ),
            ExtractedElement(
                element_type="speaker_notes",
                content="В стоимость не входит аренда студии",
                slide_number=2
            )
        ]
    )

    chunks = chunker.chunk(extraction, KnowledgeLayer.PROFESSIONAL, "Презентация")
    assert len(chunks) >= 1
    slide_chunk = next(c for c in chunks if c.slide_number == 2)
    assert "120 000 руб" in slide_chunk.content


def test_heading_path_propagation(chunker):
    extraction = ExtractionResult(
        source_id="src-heading-test",
        success=True,
        elements=[
            ExtractedElement(element_type="heading", content="1. Осветительные приборы"),
            ExtractedElement(element_type="paragraph", content="Моноблоки Profoto обеспечивают цветовую стабильность."),
            ExtractedElement(element_type="paragraph", content="Генераторы высокой мощности используются для уличных съемок.")
        ]
    )

    chunks = chunker.chunk(extraction, KnowledgeLayer.GLOBAL, "Гайд по свету")
    assert len(chunks) >= 1
    assert chunks[0].heading_path == "1. Осветительные приборы"
    assert "Profoto" in chunks[0].content


def test_timestamp_range_in_chunks(chunker):
    extraction = ExtractionResult(
        source_id="src-video-test",
        success=True,
        elements=[
            ExtractedElement(
                element_type="fusion",
                content="Видео [01:15 – 01:45] Спикер объясняет световую схему",
                start_time=75.0,
                end_time=105.0,
                heading_path="01:15 – 01:45"
            )
        ]
    )

    chunks = chunker.chunk(extraction, KnowledgeLayer.GLOBAL, "Видеоурок")
    assert len(chunks) == 1
    assert chunks[0].start_time == 75.0
    assert chunks[0].end_time == 105.0
    assert chunks[0].heading_path == "01:15 – 01:45"
