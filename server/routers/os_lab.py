from __future__ import annotations

from fastapi import APIRouter, HTTPException

from server.dependencies import get_session_store
from server.models.schemas import OsLabEventRequest

router = APIRouter(prefix="/api/os-lab", tags=["os-lab"])


@router.post("/events")
async def add_os_lab_event(req: OsLabEventRequest):
    store = get_session_store()
    try:
        store.get_session(req.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc

    event_id = store.add_os_lab_event(
        session_id=req.session_id,
        algorithm_id=req.algorithm_id,
        algorithm_title=req.algorithm_title,
        event_type=req.event_type,
        frame_index=max(0, req.frame_index),
        total_frames=max(0, req.total_frames),
        metadata=req.metadata,
    )
    return {"ok": True, "id": event_id}


@router.get("/events/{session_id}")
async def list_os_lab_events(session_id: str, limit: int = 50):
    store = get_session_store()
    try:
        store.get_session(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc
    return store.get_os_lab_events(session_id, limit=max(1, min(limit, 200)))
