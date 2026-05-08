from __future__ import annotations

from queue import Queue
from pathlib import Path
from threading import Thread

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from server.dependencies import get_knowledge_base, get_settings_cached
from server.models.schemas import IngestRequest, TrainRequest, SearchRequest
from src.prlmad.knowledge_base import KnowledgeBase
from src.prlmad.pdf_loader import load_document_pages
from src.prlmad.training import train_from_folder
from server.utils.sse import sse_done, sse_error, sse_event

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.post("/ingest")
async def ingest(req: IngestRequest):
    kb = get_knowledge_base()
    settings = get_settings_cached()
    file_path = Path(req.path)
    if not file_path.is_absolute():
        file_path = settings.base_dir / file_path
    if not file_path.exists():
        return {"ok": False, "error": f"文件不存在: {req.path}"}

    try:
        pages = load_document_pages(file_path, ocr_mode=req.ocr_mode)
        info = kb.add_document(
            title=req.title or file_path.stem,
            course=req.course,
            source_path=file_path,
            pages=pages,
        )
        return {
            "ok": True,
            "document": {
                "id": info.id,
                "title": info.title,
                "course": info.course,
                "chunk_count": info.chunk_count,
                "created_at": info.created_at,
            },
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/train")
async def train(req: TrainRequest):
    kb = get_knowledge_base()
    settings = get_settings_cached()
    knowledge_dir = req.knowledge_dir or str(settings.knowledge_dir)

    try:
        summary = train_from_folder(
            kb,
            knowledge_dir,
            course=req.course,
            replace=req.force_rebuild,
            ocr_mode=req.ocr_mode,
            ocr_max_pages=req.max_pages,
        )
        return {
            "ok": True,
            "summary": {
                "knowledge_dir": summary.knowledge_dir,
                "course": summary.course,
                "total_files": summary.total_files,
                "success_count": summary.success_count,
                "failed_count": summary.failed_count,
                "results": [
                    {
                        "path": r.path,
                        "title": r.title,
                        "ok": r.ok,
                        "message": r.message,
                        "page_count": r.page_count,
                        "chunk_count": r.chunk_count,
                    }
                    for r in summary.results
                ],
            },
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/train/stream")
async def train_stream(req: TrainRequest):
    settings = get_settings_cached()
    knowledge_dir = req.knowledge_dir or str(settings.knowledge_dir)

    def stream():
        events: Queue[str | None] = Queue()

        def on_progress(stage: str, detail: dict) -> None:
            events.put(sse_event("progress", {"stage": stage, **detail}))

        def worker() -> None:
            try:
                kb = KnowledgeBase(settings.db_path)
                summary = train_from_folder(
                    kb,
                    knowledge_dir,
                    course=req.course,
                    replace=req.force_rebuild,
                    ocr_mode=req.ocr_mode,
                    ocr_max_pages=req.max_pages,
                    on_progress=on_progress,
                )
                events.put(sse_event("summary", {
                    "knowledge_dir": summary.knowledge_dir,
                    "course": summary.course,
                    "total_files": summary.total_files,
                    "success_count": summary.success_count,
                    "failed_count": summary.failed_count,
                    "results": [
                        {
                            "path": r.path,
                            "title": r.title,
                            "ok": r.ok,
                            "message": r.message,
                            "page_count": r.page_count,
                            "chunk_count": r.chunk_count,
                        }
                        for r in summary.results
                    ],
                }))
                events.put(sse_done())
            except Exception as exc:
                events.put(sse_error(str(exc)))
            finally:
                events.put(None)

        Thread(target=worker, daemon=True).start()
        while True:
            item = events.get()
            if item is None:
                break
            yield item

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/search")
async def search(req: SearchRequest):
    kb = get_knowledge_base()
    results = kb.search(req.query, course=req.course, top_k=req.top_k)
    return {
        "ok": True,
        "query": req.query,
        "results": [
            {
                "title": r.title,
                "course": r.course,
                "page": r.page_label,
                "text": r.text,
                "score": round(r.score, 2),
                "chunk_id": r.chunk_id,
            }
            for r in results
        ],
    }


@router.get("/status")
async def status():
    kb = get_knowledge_base()
    settings = get_settings_cached()
    docs = kb.list_documents()
    courses = sorted({d.course for d in docs})
    configured_db_path = settings.db_path
    actual_db_path = kb.db_path
    candidate_path = settings.data_dir / "knowledge_active.sqlite3"
    fallback_candidate = None
    if candidate_path != actual_db_path and candidate_path.exists():
        try:
            candidate_kb = KnowledgeBase(candidate_path)
            fallback_candidate = {
                "path": str(candidate_path),
                "document_count": len(candidate_kb.list_documents()),
                "chunk_count": candidate_kb.get_chunk_count(),
            }
        except Exception as exc:
            fallback_candidate = {"path": str(candidate_path), "error": str(exc)}
    return {
        "doc_count": len(docs),
        "document_count": len(docs),
        "course_count": len(courses),
        "chunk_count": kb.get_chunk_count(),
        "db_path": str(actual_db_path),
        "configured_db_path": str(configured_db_path),
        "using_fallback_db": actual_db_path != configured_db_path,
        "db_exists": actual_db_path.exists(),
        "db_size_bytes": actual_db_path.stat().st_size if actual_db_path.exists() else 0,
        "knowledge_dir": str(settings.knowledge_dir),
        "knowledge_dir_exists": settings.knowledge_dir.exists(),
        "fallback_candidate": fallback_candidate,
        "documents": [
            {
                "id": d.id,
                "title": d.title,
                "course": d.course,
                "chunk_count": d.chunk_count,
                "created_at": d.created_at,
            }
            for d in docs
        ],
    }
