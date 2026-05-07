from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Protocol


class PageLike(Protocol):
    page_number: int
    text: str


@dataclass(frozen=True)
class TextChunk:
    text: str
    page_start: int
    page_end: int


_MULTI_SPACE_RE = re.compile(r"[ \t]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;])")


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _MULTI_SPACE_RE.sub(" ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def _segments(text: str) -> list[str]:
    parts: list[str] = []
    for paragraph in re.split(r"\n{2,}", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        sentence_parts = [item.strip() for item in _SENTENCE_SPLIT_RE.split(paragraph)]
        for item in sentence_parts:
            if item:
                parts.append(item)
    return parts


def chunk_pages(
    pages: Iterable[PageLike],
    max_chars: int = 1100,
    overlap_chars: int = 160,
) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    buffer = ""
    page_start: int | None = None
    page_end: int | None = None

    def flush() -> None:
        nonlocal buffer, page_start, page_end
        clean = normalize_text(buffer)
        if clean and page_start is not None and page_end is not None:
            chunks.append(TextChunk(clean, page_start, page_end))
        if overlap_chars > 0 and clean:
            buffer = clean[-overlap_chars:]
            page_start = page_end
        else:
            buffer = ""
            page_start = None

    for page in pages:
        text = normalize_text(page.text)
        if not text:
            continue
        for segment in _segments(text):
            while len(segment) > max_chars:
                head = segment[:max_chars]
                segment = segment[max_chars - overlap_chars :]
                if buffer:
                    flush()
                chunks.append(TextChunk(normalize_text(head), page.page_number, page.page_number))

            if not buffer:
                page_start = page.page_number
            page_end = page.page_number
            if len(buffer) + len(segment) + 1 > max_chars and buffer:
                flush()
                if not buffer:
                    page_start = page.page_number
            buffer = f"{buffer}\n{segment}".strip()

    if buffer:
        flush()
    return chunks

