from __future__ import annotations

import json

from fastapi import APIRouter

from server.dependencies import get_knowledge_base, get_session_store, get_spark_client
from server.models.schemas import EvaluateRequest
from src.prlmad.agents import AgentOrchestrator

router = APIRouter(prefix="/api/evaluate", tags=["evaluate"])


@router.post("/comprehensive")
async def evaluate(req: EvaluateRequest):
    client = get_spark_client()
    kb = get_knowledge_base()
    store = get_session_store()

    profile = store.get_profile(req.session_id)
    session = store.get_session(req.session_id)

    resources = store.get_resources(req.session_id)
    tutor_logs = store.get_tutor_logs(req.session_id)
    path_data = store.get_learning_path(req.session_id)

    activities = []
    for r in resources[:10]:
        activities.append({
            "type": "resource",
            "description": f"生成资源: {r.resource_name}",
            "result": "已生成",
        })
    for log in tutor_logs[:10]:
        activities.append({
            "type": "tutor",
            "description": f"辅导问答: {log['question'][:50]}",
            "result": "已回答",
        })
    if path_data and path_data.get("path", {}).get("steps"):
        completed = path_data.get("current_step", 0)
        total = len(path_data["path"]["steps"])
        activities.append({
            "type": "learning_path",
            "description": f"学习路径执行进度",
            "result": f"{completed}/{total} 步骤完成",
        })

    orchestrator = AgentOrchestrator(client, kb)
    result = orchestrator.evaluate_learning(session.course, profile, activities)

    try:
        eval_data = json.loads(result.strip().removeprefix("```json").removesuffix("```").strip())
    except json.JSONDecodeError:
        eval_data = {"raw_response": result, "dimensions": {}}

    store.add_evaluation(req.session_id, "comprehensive", eval_data)

    if eval_data.get("profile_updates"):
        updated_profile = dict(profile)
        updated_profile.update(eval_data["profile_updates"])
        store.update_profile(req.session_id, updated_profile)

    return {"evaluation": eval_data}


@router.get("/history/{session_id}")
async def get_evaluation_history(session_id: str):
    store = get_session_store()
    evaluations = store.get_evaluations(session_id)
    return [
        {
            "id": e.id,
            "eval_type": e.eval_type,
            "data": json.loads(e.data_json),
            "created_at": e.created_at,
        }
        for e in evaluations
    ]
