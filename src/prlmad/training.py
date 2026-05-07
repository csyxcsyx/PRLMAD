from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .knowledge_base import KnowledgeBase
from .pdf_loader import OcrMode, load_document_pages


SUPPORTED_KNOWLEDGE_EXTENSIONS = {".pdf", ".txt", ".md"}


@dataclass(frozen=True)
class TrainingFileResult:
    path: str
    title: str
    course: str
    ok: bool
    message: str
    page_count: int = 0
    chunk_count: int = 0


@dataclass(frozen=True)
class TrainingSummary:
    knowledge_dir: str
    course: str
    total_files: int
    success_count: int
    failed_count: int
    results: list[TrainingFileResult]


def discover_knowledge_files(knowledge_dir: str | Path) -> list[Path]:
    root = Path(knowledge_dir)
    if not root.exists():
        return []
    return sorted(
        [
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_KNOWLEDGE_EXTENSIONS
        ],
        key=lambda item: str(item).lower(),
    )


def train_from_folder(
    knowledge_base: KnowledgeBase,
    knowledge_dir: str | Path,
    course: str = "操作系统",
    replace: bool = True,
    ocr_mode: OcrMode = "auto",
    ocr_max_pages: int | None = None,
) -> TrainingSummary:
    files = discover_knowledge_files(knowledge_dir)
    results: list[TrainingFileResult] = []

    for path in files:
        title = path.stem
        try:
            pages = load_document_pages(path, ocr_mode=ocr_mode, ocr_max_pages=ocr_max_pages)
            info = knowledge_base.add_document(
                title=title,
                course=course,
                source_path=path,
                pages=pages,
                replace=replace,
            )
            results.append(
                TrainingFileResult(
                    path=str(path),
                    title=title,
                    course=course,
                    ok=True,
                    message="已完成本地知识库构建",
                    page_count=len(pages),
                    chunk_count=info.chunk_count,
                )
            )
        except Exception as exc:
            results.append(
                TrainingFileResult(
                    path=str(path),
                    title=title,
                    course=course,
                    ok=False,
                    message=str(exc),
                )
            )

    success_count = sum(1 for item in results if item.ok)
    return TrainingSummary(
        knowledge_dir=str(Path(knowledge_dir)),
        course=course,
        total_files=len(files),
        success_count=success_count,
        failed_count=len(results) - success_count,
        results=results,
    )

