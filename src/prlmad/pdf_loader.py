from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class PageText:
    page_number: int
    text: str


OcrMode = Literal["off", "auto", "on"]


def load_pdf_pages(
    path: str | Path,
    ocr_mode: OcrMode = "off",
    ocr_max_pages: int | None = None,
    ocr_dpi: int = 180,
) -> list[PageText]:
    pdf_path = Path(path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    pages: list[PageText] = []
    page_count = 0
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        if ocr_mode == "off":
            raise RuntimeError(
                "PDF ingestion needs pypdf. Install it with: python -m pip install pypdf"
            ) from exc
    else:
        reader = PdfReader(str(pdf_path))
        page_count = len(reader.pages)
        for index, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            if text.strip():
                pages.append(PageText(page_number=index, text=text))

    if _should_ocr(ocr_mode, pages, page_count):
        return load_pdf_pages_with_ocr(pdf_path, max_pages=ocr_max_pages, dpi=ocr_dpi)
    return pages


def load_text_pages(path: str | Path, page_chars: int = 4000) -> list[PageText]:
    text_path = Path(path)
    if not text_path.exists():
        raise FileNotFoundError(f"Text file not found: {text_path}")

    text = text_path.read_text(encoding="utf-8")
    pages: list[PageText] = []
    for index, start in enumerate(range(0, len(text), page_chars), start=1):
        pages.append(PageText(page_number=index, text=text[start : start + page_chars]))
    return pages


def load_document_pages(
    path: str | Path,
    ocr_mode: OcrMode = "off",
    ocr_max_pages: int | None = None,
) -> list[PageText]:
    doc_path = Path(path)
    suffix = doc_path.suffix.lower()
    if suffix == ".pdf":
        return load_pdf_pages(doc_path, ocr_mode=ocr_mode, ocr_max_pages=ocr_max_pages)
    if suffix in {".txt", ".md"}:
        return load_text_pages(doc_path)
    raise ValueError(f"Unsupported document type: {doc_path.suffix}")


def _should_ocr(ocr_mode: OcrMode, pages: list[PageText], page_count: int) -> bool:
    if ocr_mode == "off":
        return False
    if ocr_mode == "on":
        return True
    if page_count == 0:
        return not pages
    extracted_ratio = len(pages) / max(page_count, 1)
    total_chars = sum(len(page.text.strip()) for page in pages)
    return extracted_ratio < 0.08 or total_chars < 2000


def load_pdf_pages_with_ocr(
    path: str | Path,
    max_pages: int | None = None,
    dpi: int = 180,
) -> list[PageText]:
    try:
        import fitz
        import numpy as np
        from PIL import Image
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:
        raise RuntimeError(
            "This PDF looks scanned and needs OCR. Install OCR dependencies with: "
            "python -m pip install -r requirements.txt"
        ) from exc

    pdf_path = Path(path)
    reader = fitz.open(str(pdf_path))
    ocr = RapidOCR()
    matrix = fitz.Matrix(dpi / 72, dpi / 72)
    pages: list[PageText] = []

    page_total = len(reader)
    page_limit = min(page_total, max_pages) if max_pages else page_total
    for index in range(page_limit):
        page = reader[index]
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        image = Image.open(BytesIO(pixmap.tobytes("png"))).convert("RGB")
        image_array = np.array(image)
        result, _ = ocr(image_array)
        lines = _ocr_lines(result)
        if lines:
            pages.append(PageText(page_number=index + 1, text="\n".join(lines)))
    reader.close()
    return pages


def _ocr_lines(result: object) -> list[str]:
    lines: list[str] = []
    if not result:
        return lines
    for item in result:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            text = item[1]
            if isinstance(text, str) and text.strip():
                lines.append(text.strip())
    return lines
