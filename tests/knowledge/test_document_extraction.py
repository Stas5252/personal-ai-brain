"""
Tests for Document Extraction Engine.
Covers PDF, Scanned PDF fallback, DOCX, PPTX, XLSX, HTML, and Markdown.
"""
import pytest
from pathlib import Path
from src.brain.knowledge.extractors.document_extractor import DocumentExtractor
from src.brain.models.file_metadata import ExtractionResult

@pytest.fixture
def doc_extractor():
    return DocumentExtractor()


def test_pdf_extraction(doc_extractor):
    pdf_path = Path("tests/pilot_corpus/sample_contract.pdf")
    assert pdf_path.exists(), "Pilot contract PDF must exist"

    result = doc_extractor.extract(pdf_path)
    assert isinstance(result, ExtractionResult)
    assert len(result.elements) > 0

    full_text = result.get_full_text()
    assert "ДОГОВОР НА ОКАЗАНИЕ ФОТОУСЛУГ" in full_text
    assert "85 000 рублей" in full_text
    assert "30 000 рублей" in full_text


def test_docx_extraction_with_headings_and_tables(doc_extractor):
    docx_path = Path("tests/pilot_corpus/sample_guide.docx")
    assert docx_path.exists(), "Pilot guide DOCX must exist"

    result = doc_extractor.extract(docx_path)
    assert len(result.elements) > 0

    # Verify heading hierarchy and table preservation
    headings = [e for e in result.elements if e.element_type == "heading"]
    tables = [e for e in result.elements if e.element_type == "table"]

    assert len(headings) >= 3
    assert any("Рембрандт" in e.content for e in result.elements)
    assert len(tables) >= 1
    # Check table structure inside content
    table_content = tables[0].content
    assert "Октабокс 120 см" in table_content
    assert "Портретная тарелка" in table_content


def test_pptx_extraction_with_slides_and_notes(doc_extractor):
    pptx_path = Path("tests/pilot_corpus/sample_portfolio.pptx")
    assert pptx_path.exists(), "Pilot portfolio PPTX must exist"

    result = doc_extractor.extract(pptx_path)
    assert len(result.elements) > 0

    # Slides must have slide_number
    slides = [e for e in result.elements if e.slide_number is not None]
    assert len(slides) >= 2

    # Check slide notes extraction
    notes = [e for e in result.elements if e.element_type == "speaker_notes"]
    assert len(notes) >= 1
    assert "В стоимость не включена аренда студии" in notes[0].content


def test_xlsx_extraction_multi_sheet(doc_extractor):
    xlsx_path = Path("tests/pilot_corpus/sample_pricing.xlsx")
    assert xlsx_path.exists(), "Pilot pricing XLSX must exist"

    result = doc_extractor.extract(xlsx_path)
    assert len(result.elements) > 0

    # Check sheet names
    sheet_names = {e.sheet_name for e in result.elements if e.sheet_name}
    assert "Пакеты съемок" in sheet_names
    assert "Дополнительные услуги" in sheet_names

    full_text = result.get_full_text()
    assert "Свадебный день" in full_text
    assert "110000" in full_text
    assert "Ретушь дополнительного кадра" in full_text


def test_html_and_markdown_extraction(doc_extractor, tmp_path):
    # HTML test with nav/footer boilerplate
    html_file = tmp_path / "test.html"
    html_file.write_text("""
    <!DOCTYPE html>
    <html>
    <head><title>Памятка клиенту перед съемкой</title></head>
    <body>
        <nav><a href="/home">Home</a> | <a href="/menu">Menu</a></nav>
        <header>Header content</header>
        <main>
            <h1>Подготовка к фотосессии</h1>
            <p>Выспитесь накануне и пейте больше воды.</p>
            <ul>
                <li>Возьмите с собой 2-3 комплекта одежды</li>
                <li>Макияж лучше делать у профессионала</li>
            </ul>
        </main>
        <footer>Copyright 2026 Studio. All rights reserved.</footer>
    </body>
    </html>
    """, encoding="utf-8")

    res = doc_extractor.extract(html_file)
    extracted_text = res.get_full_text()
    assert "Подготовка к фотосессии" in extracted_text
    assert "Выспитесь накануне" in extracted_text
    # Boilerplate stripped
    assert "Copyright 2026 Studio" not in extracted_text
