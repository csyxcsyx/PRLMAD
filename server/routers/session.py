from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from server.dependencies import get_knowledge_base, get_session_store, get_spark_client
from server.models.schemas import (
    CreateSessionRequest,
    UpdateSessionRequest,
    UpdateProfileRequest,
    LearningPathRequest,
    UpdatePathStepRequest,
)
from src.prlmad.agents import AgentOrchestrator

router = APIRouter(prefix="/api", tags=["session"])


@router.post("/session")
async def create_session(req: CreateSessionRequest):
    store = get_session_store()
    session = store.create_session(req.name, req.course)
    return {
        "session_id": session.session_id,
        "name": session.name,
        "course": session.course,
        "created_at": session.created_at,
    }


@router.get("/sessions")
async def list_sessions():
    store = get_session_store()
    sessions = store.list_sessions()
    return [
        {
            "session_id": s.session_id,
            "name": s.name,
            "course": s.course,
            "profile": s.profile,
            "message_count": s.message_count,
            "resource_count": s.resource_count,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
        }
        for s in sessions
    ]


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    store = get_session_store()
    try:
        s = store.get_session(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc
    return {
        "session_id": s.session_id,
        "name": s.name,
        "course": s.course,
        "profile": s.profile,
        "message_count": s.message_count,
        "resource_count": s.resource_count,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
    }


@router.put("/session/{session_id}")
async def update_session(session_id: str, req: UpdateSessionRequest):
    store = get_session_store()
    store.update_session(session_id, req.name, req.course)
    return {"ok": True}


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    store = get_session_store()
    store.delete_session(session_id)
    return {"ok": True}


@router.get("/profile/{session_id}")
async def get_profile(session_id: str):
    store = get_session_store()
    return store.get_profile(session_id)


@router.put("/profile/{session_id}")
async def update_profile(session_id: str, req: UpdateProfileRequest):
    store = get_session_store()
    store.update_profile(session_id, req.profile)
    return {"ok": True}


@router.post("/learning-path/generate")
async def generate_learning_path(req: LearningPathRequest):
    client = get_spark_client()
    kb = get_knowledge_base()
    store = get_session_store()

    try:
        store.get_session(req.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc

    profile = store.get_profile(req.session_id)
    orchestrator = AgentOrchestrator(client, kb)

    result = orchestrator.generate_learning_path(req.course, profile, req.knowledge_points)

    try:
        path_data = json.loads(result.strip().removeprefix("```json").removesuffix("```").strip())
    except json.JSONDecodeError:
        path_data = {"title": "学习路径", "steps": [], "raw_response": result}

    store.save_learning_path(req.session_id, path_data)
    return {"path": path_data}


@router.get("/learning-path/{session_id}")
async def get_learning_path(session_id: str):
    store = get_session_store()
    path_data = store.get_learning_path(session_id)
    return path_data or {"path": {}, "current_step": 0}


@router.put("/learning-path/{session_id}/step")
async def update_path_step(session_id: str, req: UpdatePathStepRequest):
    store = get_session_store()
    store.update_learning_path_step(session_id, req.current_step)
    return {"ok": True}
