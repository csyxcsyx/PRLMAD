from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .knowledge_base import KnowledgeBase
from .pdf_loader import OcrMode, load_document_pages


SUPPORTED_KNOWLEDGE_EXTENSIONS = {".pdf", ".txt", ".md"}
ProgressCallback = Callable[[str, dict], None]


def _emit(progress: ProgressCallback | None, stage: str, **detail) -> None:
    if progress:
        progress(stage, detail)


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


def get_pdf_page_count(path: str | Path) -> int | None:
    doc_path = Path(path)
    if doc_path.suffix.lower() != ".pdf":
        return None
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(doc_path)).pages)
    except Exception:
        return None


def train_from_folder(
    knowledge_base: KnowledgeBase,
    knowledge_dir: str | Path,
    course: str = "操作系统",
    replace: bool = False,
    ocr_mode: OcrMode = "auto",
    ocr_max_pages: int | None = None,
    on_progress: ProgressCallback | None = None,
) -> TrainingSummary:
    files = discover_knowledge_files(knowledge_dir)
    results: list[TrainingFileResult] = []
    _emit(on_progress, "train_discovered", knowledge_dir=str(Path(knowledge_dir)), total_files=len(files))

    for file_index, path in enumerate(files, start=1):
        title = path.stem
        try:
            existing = knowledge_base.get_document_by_source(path, course)
            pdf_page_count = get_pdf_page_count(path)
            target_last_page = min(pdf_page_count, ocr_max_pages) if pdf_page_count and ocr_max_pages else pdf_page_count
            start_page = 1
            if existing and not replace:
                _min_page, max_page = knowledge_base.get_document_page_extent(existing.id)
                if target_last_page and max_page >= target_last_page:
                    _emit(
                        on_progress,
                        "file_skipped",
                        index=file_index,
                        total_files=len(files),
                        path=str(path),
                        title=title,
                        course=course,
                        existing_pages=max_page,
                        total_pages=target_last_page,
                    )
                    results.append(
                        TrainingFileResult(
                            path=str(path),
                            title=title,
                            course=course,
                            ok=True,
                            message="知识库已包含完整文档，已跳过",
                            page_count=max_page,
                            chunk_count=existing.chunk_count,
                        )
                    )
                    continue
                if max_page > 0:
                    start_page = max_page + 1

            _emit(
                on_progress,
                "file_start",
                index=file_index,
                total_files=len(files),
                path=str(path),
                title=title,
                course=course,
                start_page=start_page,
                total_pages=target_last_page or 0,
                mode="replace" if replace else ("resume" if existing else "new"),
            )
            pages = load_document_pages(
                path,
                ocr_mode=ocr_mode,
                ocr_max_pages=ocr_max_pages,
                start_page=start_page,
                on_progress=lambda stage, detail, p=path, i=file_index: _emit(
                    on_progress,
                    stage,
                    **detail,
                    file_index=i,
                    total_files=len(files),
                    file_name=p.name,
                ),
            )
            _emit(
                on_progress,
                "file_pages_loaded",
                index=file_index,
                total_files=len(files),
                title=title,
                pages=len(pages),
            )
            info = knowledge_base.upsert_document_pages(
                title=title,
                course=course,
                source_path=path,
                pages=pages,
                replace=replace,
                on_progress=lambda stage, detail, p=path, i=file_index: _emit(
                    on_progress,
                    stage,
                    **detail,
                    file_index=i,
                    total_files=len(files),
                    file_name=p.name,
                ),
            )
            _emit(
                on_progress,
                "file_done",
                index=file_index,
                total_files=len(files),
                title=title,
                pages=len(pages),
                chunks=info.chunk_count,
                start_page=start_page,
                total_pages=target_last_page or 0,
            )
            results.append(
                TrainingFileResult(
                    path=str(path),
                    title=title,
                    course=course,
                    ok=True,
                    message="已完成本地知识库构建" if start_page == 1 else f"已从第 {start_page} 页继续导入",
                    page_count=len(pages),
                    chunk_count=info.chunk_count,
                )
            )
        except Exception as exc:
            _emit(
                on_progress,
                "file_error",
                index=file_index,
                total_files=len(files),
                title=title,
                error=str(exc),
            )
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
    _emit(
        on_progress,
        "train_done",
        total_files=len(files),
        success_count=success_count,
        failed_count=len(results) - success_count,
    )
    return TrainingSummary(
        knowledge_dir=str(Path(knowledge_dir)),
        course=course,
        total_files=len(files),
        success_count=success_count,
        failed_count=len(results) - success_count,
        results=results,
    )
