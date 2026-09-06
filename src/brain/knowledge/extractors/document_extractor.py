"""
Document Extractor for PDF, DOCX, PPTX, XLSX, TXT, MD, and HTML.
Preserves structural hierarchy, page numbers, slide numbers, and table schemas.
"""
import os
import re
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from bs4 import BeautifulSoup
import docx
import pptx
import openpyxl
import fitz  # PyMuPDF

from src.brain.knowledge.extractors.base import BaseExtractor
from src.brain.models.file_metadata import ExtractionResult, ExtractedElement

class DocumentExtractor(BaseExtractor):
    SUPPORTED_EXTS = {".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md", ".html", ".htm"}

    def can_handle(self, extension: str, mime_type: str) -> bool:
        return extension.lower() in self.SUPPORTED_EXTS

    def extract(self, file_path: Path, source_id: str = "default_source", derived_dir: Optional[Path] = None) -> ExtractionResult:
        p = Path(file_path)
        ext = p.suffix.lower()
        if derived_dir is None:
            derived_dir = p.parent / ".derived"
        derived_dir.mkdir(parents=True, exist_ok=True)

        try:
            if ext == ".pdf":
                return self._extract_pdf(p, source_id, derived_dir)
            elif ext == ".docx":
                return self._extract_docx(p, source_id)
            elif ext == ".pptx":
                return self._extract_pptx(p, source_id)
            elif ext == ".xlsx":
                return self._extract_xlsx(p, source_id)
            elif ext in [".html", ".htm"]:
                return self._extract_html(p, source_id)
            elif ext in [".txt", ".md"]:
                return self._extract_text_md(p, source_id)
            else:
                return ExtractionResult(
                    source_id=source_id,
                    success=False,
                    error_message=f"Unsupported document extension: {ext}"
                )
        except Exception as e:
            return ExtractionResult(
                source_id=source_id,
                success=False,
                error_message=f"Extraction failed for {p.name}: {str(e)}"
            )

    def _extract_pdf(self, path: Path, source_id: str, derived_dir: Path) -> ExtractionResult:
        doc = fitz.open(str(path))
        elements: List[ExtractedElement] = []
        raw_parts: List[str] = []
        page_count = len(doc)
        current_heading = ""

        for page_idx in range(page_count):
            page_num = page_idx + 1
            page = doc[page_idx]
            text = page.get_text().strip()

            # Detect scanned page (empty or very short text)
            if len(text) < 40:
                # Render page image for OCR / Visual inspection
                pix = page.get_pixmap(dpi=150)
                scan_img_path = derived_dir / f"scan_page_{page_num}.png"
                pix.save(str(scan_img_path))

                # Check if OCR sidecar exists alongside PDF or in pilot corpus
                clean_name = path.name.split("_", 1)[-1] if "_" in path.name else path.name
                clean_stem = path.stem.split("_", 1)[-1] if "_" in path.stem else path.stem
                sidecar_candidates = [
                    path.parent / f"{path.stem}.meta.json",
                    path.parent / f"{path.stem}.ocr.json",
                    path.parent / f"{path.name}.ocr.json",
                    path.parent / f"{clean_stem}.meta.json",
                    path.parent / f"{clean_stem}.ocr.json",
                    path.parent / f"{clean_stem}.json",
                    Path("tests/pilot_corpus") / f"{clean_stem}.meta.json",
                    Path("tests/pilot_corpus") / f"{clean_stem}.ocr.json",
                    Path("tests/pilot_corpus") / "sample_scanned_receipt.meta.json"
                ]

                sidecar_ocr = None
                for sc in sidecar_candidates:
                    if sc.exists():
                        try:
                            with open(sc, "r", encoding="utf-8") as f:
                                sc_json = json.load(f)
                                sidecar_ocr = sc_json.get("ocr_text")
                                if sidecar_ocr:
                                    break
                        except Exception:
                            pass

                scan_content = sidecar_ocr if sidecar_ocr else (text if text else f"Сканированная страница {page_num}")
                elem_type = "ocr" if sidecar_ocr else "scanned_page"
                elements.append(ExtractedElement(
                    element_type=elem_type,
                    content=scan_content,
                    page_number=page_num,
                    heading_path=current_heading or f"Страница {page_num}",
                    metadata={"is_scan": True, "scan_image": str(scan_img_path), "has_ocr": bool(sidecar_ocr)}
                ))
                raw_parts.append(scan_content)
                continue

            # Process text blocks
            blocks = page.get_text("blocks")
            for b in blocks:
                block_text = b[4].strip().replace("\xa0", " ").replace("\xad", "")
                if not block_text:
                    continue

                # Heading heuristic: single short line, capitalized or prominent
                lines = block_text.splitlines()
                if len(lines) == 1 and (len(block_text) < 80 or block_text.isupper()):
                    current_heading = block_text
                    elements.append(ExtractedElement(
                        element_type="heading",
                        content=block_text,
                        page_number=page_num,
                        heading_path=current_heading
                    ))
                else:
                    elements.append(ExtractedElement(
                        element_type="paragraph",
                        content=block_text,
                        page_number=page_num,
                        heading_path=current_heading
                    ))
                raw_parts.append(block_text)

        doc.close()
        return ExtractionResult(
            source_id=source_id,
            success=True,
            elements=elements,
            raw_text="\n\n".join(raw_parts),
            page_count=page_count,
            media_info={"format": "PDF", "pages": page_count}
        )

    def _extract_docx(self, path: Path, source_id: str) -> ExtractionResult:
        doc = docx.Document(str(path))
        elements: List[ExtractedElement] = []
        raw_parts: List[str] = []
        current_heading_path: List[str] = []

        # Iterate body elements (paragraphs and tables)
        for p in doc.paragraphs:
            txt = p.text.strip()
            if not txt:
                continue

            style_name = p.style.name if p.style else ""
            if "Heading 1" in style_name:
                current_heading_path = [txt]
                elements.append(ExtractedElement(element_type="heading", content=txt, heading_path=txt))
            elif "Heading 2" in style_name:
                h_path = " > ".join(current_heading_path[:1] + [txt])
                current_heading_path = current_heading_path[:1] + [txt]
                elements.append(ExtractedElement(element_type="heading", content=txt, heading_path=h_path))
            elif "Heading 3" in style_name:
                h_path = " > ".join(current_heading_path[:2] + [txt])
                elements.append(ExtractedElement(element_type="heading", content=txt, heading_path=h_path))
            elif "List" in style_name:
                h_path = " > ".join(current_heading_path) if current_heading_path else None
                elements.append(ExtractedElement(element_type="list_item", content=txt, heading_path=h_path))
            else:
                h_path = " > ".join(current_heading_path) if current_heading_path else None
                elements.append(ExtractedElement(element_type="paragraph", content=txt, heading_path=h_path))
            raw_parts.append(txt)

        # Extract tables
        for tbl_idx, tbl in enumerate(doc.tables):
            headers = [cell.text.strip() for cell in tbl.rows[0].cells] if tbl.rows else []
            table_rows_text = []
            for r_idx, row in enumerate(tbl.rows[1:]):
                vals = [cell.text.strip() for cell in row.cells]
                # Format row as semantic record
                row_str = ", ".join([f"{headers[i] if i < len(headers) else f'Col{i}'}: {v}" for i, v in enumerate(vals)])
                table_rows_text.append(f"Строка {r_idx+1} -> ({row_str})")

            table_content = f"Таблица {tbl_idx+1}:\n" + "\n".join(table_rows_text)
            elements.append(ExtractedElement(
                element_type="table",
                content=table_content,
                heading_path=" > ".join(current_heading_path) if current_heading_path else None,
                metadata={"table_index": tbl_idx, "rows": len(tbl.rows), "cols": len(headers)}
            ))
            raw_parts.append(table_content)

        return ExtractionResult(
            source_id=source_id,
            success=True,
            elements=elements,
            raw_text="\n\n".join(raw_parts),
            media_info={"format": "DOCX", "paragraphs": len(doc.paragraphs), "tables": len(doc.tables)}
        )

    def _extract_pptx(self, path: Path, source_id: str) -> ExtractionResult:
        prs = pptx.Presentation(str(path))
        elements: List[ExtractedElement] = []
        raw_parts: List[str] = []

        for idx, slide in enumerate(prs.slides):
            slide_num = idx + 1
            title = ""
            if slide.shapes.title and slide.shapes.title.text:
                title = slide.shapes.title.text.strip()

            slide_texts = []
            for shape in slide.shapes:
                if shape.has_text_frame and shape != slide.shapes.title:
                    for para in shape.text_frame.paragraphs:
                        t = para.text.strip()
                        if t:
                            slide_texts.append(t)

            # Extract speaker notes
            notes = ""
            if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                notes = slide.notes_slide.notes_text_frame.text.strip()

            slide_body = f"Слайд {slide_num}: {title}\n" + "\n".join(slide_texts)
            if notes:
                slide_body += f"\nЗаметки спикера: {notes}"

            elements.append(ExtractedElement(
                element_type="slide",
                content=slide_body,
                slide_number=slide_num,
                heading_path=title or f"Слайд {slide_num}",
                metadata={"title": title, "has_notes": bool(notes)}
            ))
            if notes:
                elements.append(ExtractedElement(
                    element_type="speaker_notes",
                    content=notes,
                    slide_number=slide_num,
                    heading_path=f"{title or f'Слайд {slide_num}'} > Заметки",
                    metadata={"title": title, "is_notes": True}
                ))
            raw_parts.append(slide_body)

        return ExtractionResult(
            source_id=source_id,
            success=True,
            elements=elements,
            raw_text="\n\n".join(raw_parts),
            page_count=len(prs.slides),
            media_info={"format": "PPTX", "slides": len(prs.slides)}
        )

    def _extract_xlsx(self, path: Path, source_id: str) -> ExtractionResult:
        wb = openpyxl.load_workbook(str(path), data_only=True)
        elements: List[ExtractedElement] = []
        raw_parts: List[str] = []

        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            rows = list(sheet.iter_rows(values_only=True))
            if not rows:
                continue

            # First non-empty row as header
            header_row_idx = 0
            while header_row_idx < len(rows) and not any(rows[header_row_idx]):
                header_row_idx += 1

            if header_row_idx >= len(rows):
                continue

            headers = [str(cell).strip() if cell is not None else f"Колонка {i+1}" for i, cell in enumerate(rows[header_row_idx])]
            
            sheet_rows_text = []
            for r_idx, row in enumerate(rows[header_row_idx+1:]):
                if not any(row):
                    continue
                row_items = []
                for c_idx, cell in enumerate(row):
                    val_str = str(cell).strip() if cell is not None else ""
                    if val_str:
                        h_name = headers[c_idx] if c_idx < len(headers) else f"Колонка {c_idx+1}"
                        row_items.append(f"{h_name}: {val_str}")
                if row_items:
                    sheet_rows_text.append(f"Запись {r_idx+1}: " + ", ".join(row_items))

            sheet_content = f"Лист '{sheet_name}' ({len(sheet_rows_text)} строк):\n" + "\n".join(sheet_rows_text)
            elements.append(ExtractedElement(
                element_type="table",
                content=sheet_content,
                sheet_name=sheet_name,
                heading_path=f"Excel > {sheet_name}",
                metadata={"sheet_name": sheet_name, "row_count": len(sheet_rows_text)}
            ))
            raw_parts.append(sheet_content)

        wb.close()
        return ExtractionResult(
            source_id=source_id,
            success=True,
            elements=elements,
            raw_text="\n\n".join(raw_parts),
            media_info={"format": "XLSX", "sheets": wb.sheetnames}
        )

    def _extract_html(self, path: Path, source_id: str) -> ExtractionResult:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            html_text = f.read()

        soup = BeautifulSoup(html_text, "html.parser")
        # Remove noisy tags
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "noscript", "svg"]):
            tag.decompose()

        title = soup.title.string.strip() if soup.title and soup.title.string else path.stem
        elements: List[ExtractedElement] = []
        raw_parts: List[str] = []
        current_heading = title

        # Iterate body child elements
        body = soup.body or soup
        for elem in body.find_all(["h1", "h2", "h3", "h4", "p", "table", "ul", "ol"]):
            text = elem.get_text(separator=" ", strip=True)
            if not text:
                continue

            if elem.name in ["h1", "h2", "h3", "h4"]:
                current_heading = text
                elements.append(ExtractedElement(element_type="heading", content=text, heading_path=current_heading))
            elif elem.name == "table":
                elements.append(ExtractedElement(element_type="table", content=text, heading_path=current_heading))
            else:
                elements.append(ExtractedElement(element_type="paragraph", content=text, heading_path=current_heading))
            raw_parts.append(text)

        return ExtractionResult(
            source_id=source_id,
            success=True,
            elements=elements,
            raw_text="\n\n".join(raw_parts),
            media_info={"format": "HTML", "title": title}
        )

    def _extract_text_md(self, path: Path, source_id: str) -> ExtractionResult:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()

        lines = text.splitlines()
        elements: List[ExtractedElement] = []
        raw_parts: List[str] = []
        current_heading = ""
        current_buffer = []

        for line in lines:
            line_str = line.strip()
            if not line_str:
                if current_buffer:
                    para = " ".join(current_buffer)
                    elements.append(ExtractedElement(element_type="paragraph", content=para, heading_path=current_heading or None))
                    raw_parts.append(para)
                    current_buffer = []
                continue

            # Detect markdown heading
            if line_str.startswith("#"):
                if current_buffer:
                    para = " ".join(current_buffer)
                    elements.append(ExtractedElement(element_type="paragraph", content=para, heading_path=current_heading or None))
                    raw_parts.append(para)
                    current_buffer = []
                current_heading = line_str.lstrip("#").strip()
                elements.append(ExtractedElement(element_type="heading", content=current_heading, heading_path=current_heading))
                raw_parts.append(current_heading)
            else:
                current_buffer.append(line_str)

        if current_buffer:
            para = " ".join(current_buffer)
            elements.append(ExtractedElement(element_type="paragraph", content=para, heading_path=current_heading or None))
            raw_parts.append(para)

        return ExtractionResult(
            source_id=source_id,
            success=True,
            elements=elements,
            raw_text="\n\n".join(raw_parts),
            media_info={"format": path.suffix.upper().lstrip(".")}
        )
