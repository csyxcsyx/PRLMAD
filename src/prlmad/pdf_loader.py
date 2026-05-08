from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Callable, Literal


@dataclass(frozen=True)
class PageText:
    page_number: int
    text: str


OcrMode = Literal["off", "auto", "on"]
ProgressCallback = Callable[[str, dict], None]


def _emit(progress: ProgressCallback | None, stage: str, **detail) -> None:
    if progress:
        progress(stage, detail)


def load_pdf_pages(
    path: str | Path,
    ocr_mode: OcrMode = "off",
    ocr_max_pages: int | None = None,
    start_page: int = 1,
    ocr_dpi: int = 180,
    on_progress: ProgressCallback | None = None,
) -> list[PageText]:
    pdf_path = Path(path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    pages: list[PageText] = []
    page_count = 0
    text_page_total = 0
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
        start_page = max(1, start_page)
        end_page = min(page_count, ocr_max_pages) if ocr_max_pages else page_count
        text_page_total = max(end_page - start_page + 1, 0)
        _emit(
            on_progress,
            "pdf_text_start",
            path=str(pdf_path),
            total=text_page_total,
            pdf_pages=page_count,
            start_page=start_page,
            end_page=end_page,
        )
        for offset, index in enumerate(range(start_page, end_page + 1), start=1):
            page = reader.pages[index - 1]
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            if text.strip():
                pages.append(PageText(page_number=index, text=text))
            _emit(
                on_progress,
                "pdf_text_page",
                path=str(pdf_path),
                page=offset,
                absolute_page=index,
                total=text_page_total,
                extracted_pages=len(pages),
            )
        _emit(
            on_progress,
            "pdf_text_done",
            path=str(pdf_path),
            total=text_page_total,
            extracted_pages=len(pages),
        )

    if _should_ocr(ocr_mode, pages, text_page_total or page_count):
        return load_pdf_pages_with_ocr(
            pdf_path,
            max_pages=ocr_max_pages,
            start_page=start_page,
            dpi=ocr_dpi,
            on_progress=on_progress,
        )
    return pages


def load_text_pages(
    path: str | Path,
    page_chars: int = 4000,
    on_progress: ProgressCallback | None = None,
) -> list[PageText]:
    text_path = Path(path)
    if not text_path.exists():
        raise FileNotFoundError(f"Text file not found: {text_path}")

    text = text_path.read_text(encoding="utf-8")
    pages: list[PageText] = []
    for index, start in enumerate(range(0, len(text), page_chars), start=1):
        pages.append(PageText(page_number=index, text=text[start:start + page_chars]))
        _emit(on_progress, "text_page", path=str(text_path), page=index, total=max(len(text) // page_chars + 1, 1))
    return pages


def load_document_pages(
    path: str | Path,
    ocr_mode: OcrMode = "off",
    ocr_max_pages: int | None = None,
    start_page: int = 1,
    on_progress: ProgressCallback | None = None,
) -> list[PageText]:
    doc_path = Path(path)
    suffix = doc_path.suffix.lower()
    if suffix == ".pdf":
        return load_pdf_pages(
            doc_path,
            ocr_mode=ocr_mode,
            ocr_max_pages=ocr_max_pages,
            start_page=start_page,
            on_progress=on_progress,
        )
    if suffix in {".txt", ".md"}:
        return load_text_pages(doc_path, on_progress=on_progress)
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
    start_page: int = 1,
    dpi: int = 180,
    on_progress: ProgressCallback | None = None,
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
    start_page = max(1, start_page)
    end_page = min(page_total, max_pages) if max_pages else page_total
    page_limit = max(end_page - start_page + 1, 0)
    _emit(
        on_progress,
        "pdf_ocr_start",
        path=str(pdf_path),
        total=page_limit,
        pdf_pages=page_total,
        start_page=start_page,
        end_page=end_page,
    )
    for offset, index in enumerate(range(start_page - 1, end_page), start=1):
        page = reader[index]
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        image = Image.open(BytesIO(pixmap.tobytes("png"))).convert("RGB")
        image_array = np.array(image)
        result, _ = ocr(image_array)
        lines = _ocr_lines(result)
        if lines:
            pages.append(PageText(page_number=index + 1, text="\n".join(lines)))
        _emit(
            on_progress,
            "pdf_ocr_page",
            path=str(pdf_path),
            page=offset,
            absolute_page=index + 1,
            total=page_limit,
            extracted_pages=len(pages),
        )
    reader.close()
    _emit(on_progress, "pdf_ocr_done", path=str(pdf_path), total=page_limit, extracted_pages=len(pages))
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
