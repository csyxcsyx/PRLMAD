from __future__ import annotations

import json
import re

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


def _parse_json_object(text: str) -> dict:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            data = json.loads(cleaned[start:end + 1])
            return data if isinstance(data, dict) else {}
        raise


def _fallback_learning_path(
    course: str,
    profile: dict,
    knowledge_points: str,
    raw_response: str = "",
    error: str = "",
) -> dict:
    topic = (
        (knowledge_points or "").strip()
        or profile.get("weak_points")
        or profile.get("goal")
        or f"{course}核心知识"
    )
    time_hint = profile.get("available_time") or "每天 45-60 分钟"
    steps = [
        ("建立概念边界", "先弄清术语、对象和基本问题。", "用自己的话解释核心定义"),
        ("走通一个例子", "用简单场景观察状态变化和关键条件。", "能画出状态变化流程"),
        ("比较典型机制", "整理常见算法、策略或处理流程的适用条件。", "能说出每种机制适合什么情况"),
        ("做题和纠错", "完成基础题并记录错误原因。", "错题能归因到概念、条件或步骤"),
        ("实践或综合复盘", "用小实验、伪代码或思维导图完成一次迁移。", "能把知识点讲给别人听"),
    ]
    return {
        "title": f"{topic} 学习路径",
        "steps": [
            {
                "day": index,
                "topic": f"{topic}：{title}",
                "goal": title,
                "content": content,
                "exercises": ["复述核心概念", "完成 2-3 道基础检查题"],
                "resources": ["课程讲解文档", "练习题库", "学习任务清单"],
                "estimated_time": time_hint,
                "checkpoint": checkpoint,
            }
            for index, (title, content, checkpoint) in enumerate(steps, start=1)
        ],
        "adjustment_strategy": "如果当天检查点没有通过，下一天先复习该主题，再减少新内容输入。",
        "warning": error or "模型返回内容无法解析，已使用本地兜底路径。",
        "raw_response": raw_response,
    }


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

    try:
        result = orchestrator.generate_learning_path(req.course, profile, req.knowledge_points)
        try:
            path_data = _parse_json_object(result)
        except (json.JSONDecodeError, ValueError):
            path_data = _fallback_learning_path(req.course, profile, req.knowledge_points, raw_response=result)
        if not path_data.get("steps"):
            path_data = _fallback_learning_path(req.course, profile, req.knowledge_points, raw_response=result)
    except Exception as exc:
        path_data = _fallback_learning_path(req.course, profile, req.knowledge_points, error=str(exc))

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
