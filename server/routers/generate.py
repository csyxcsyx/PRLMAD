from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from queue import Queue

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from server.dependencies import get_knowledge_base, get_session_store, get_spark_client
from server.models.schemas import GenerateRequest
from server.utils.sse import sse_event, sse_done, sse_error
from src.prlmad.agents import AgentOrchestrator, LearnerInput
from src.prlmad.spark_client import SparkClient
from src.prlmad.session_store import SessionStore

router = APIRouter(prefix="/api/generate", tags=["generate"])


def _profile_markdown_from_profile(profile: dict, learner_brief: str) -> str:
    labels = {
        "major": "专业方向",
        "grade": "年级",
        "goal": "学习目标",
        "knowledge_level": "知识基础",
        "learning_history": "学习历史",
        "preferences": "资源偏好",
        "weak_points": "薄弱知识点",
        "available_time": "可用学习时间",
        "cognitive_style": "认知风格",
        "learning_habits": "学习习惯",
        "learning_motivation": "学习动机",
        "problem_solving": "问题解决能力",
        "practical_ability": "实践能力",
    }
    rows = [
        f"- **{label}**：{str(profile.get(key, '')).strip()}"
        for key, label in labels.items()
        if str(profile.get(key, "")).strip()
    ]
    if rows:
        return "## 学习画像摘要\n\n" + "\n".join(rows)
    return "## 学习画像摘要\n\n" + learner_brief


def _resource_worker_count(resource_count: int) -> int:
    try:
        configured = int(os.getenv("PRLMAD_RESOURCE_WORKERS", "4"))
    except ValueError:
        configured = 4
    return max(1, min(resource_count or 1, configured, 8))


async def _generate_resources_stream(
    client: SparkClient,
    orchestrator: AgentOrchestrator,
    session_store: SessionStore,
    session_id: str,
    course: str,
    knowledge_points: str,
    resource_types: list[str],
    top_k: int,
):
    profile = session_store.get_profile(session_id)
    focus_topic = (knowledge_points or "").strip()

    learner = LearnerInput(
        major=profile.get("major", ""),
        goal=profile.get("goal", "") or focus_topic,
        knowledge_level=profile.get("knowledge_level", ""),
        learning_history=profile.get("learning_history", ""),
        preferences=profile.get("preferences", ""),
        weak_points=profile.get("weak_points", ""),
        available_time=profile.get("available_time", ""),
    )

    try:
        from src.prlmad.safety import check_user_request
        safety = check_user_request(" ".join([focus_topic, learner.goal, learner.weak_points]))
        if not safety.allowed:
            yield sse_error("请求包含不适合生成的内容：" + "；".join(safety.warnings))
            return
        yield sse_event("stage", {"stage": "safety_check", "status": "done"})

        yield sse_event("stage", {"stage": "knowledge_retrieval", "status": "running"})
        snippets = orchestrator.knowledge_base.search(
            f"{course} {focus_topic} {learner.goal} {learner.weak_points}",
            course=course,
            top_k=top_k,
        )
        context = orchestrator.knowledge_base.format_context(snippets) if snippets else "暂无教材片段参考。"
        yield sse_event("stage", {"stage": "knowledge_retrieval", "status": "done", "snippet_count": len(snippets)})

        learner_brief_lines = [
            f"本次学习知识点：{focus_topic or '未指定，请围绕画像薄弱点生成'}",
            f"专业：{learner.major or '未提供'}",
            f"学习目标：{learner.goal or '未提供'}",
            f"知识基础：{learner.knowledge_level or '未提供'}",
            f"薄弱点：{learner.weak_points or '未提供'}",
            f"资源偏好：{learner.preferences or '未提供'}",
        ]
        learner_brief = "\n".join(learner_brief_lines)

        yield sse_event("stage", {"stage": "profile_analysis", "status": "running"})
        profile_md = _profile_markdown_from_profile(profile, learner_brief)
        yield sse_event("stage", {"stage": "profile_analysis", "status": "done"})

        from src.prlmad.agents import RESOURCE_AGENT_PROMPTS, RESOURCE_TYPE_NAMES

        resources: dict[str, str] = {}
        yield sse_event("stage", {"stage": "resource_generation", "status": "running", "total": len(resource_types)})

        events: Queue[str | None] = Queue()

        def generate_one_resource(rt: str, role_prompt: str) -> None:
            name = RESOURCE_TYPE_NAMES.get(rt, rt)
            parts: list[str] = []
            events.put(sse_event("resource_start", {"type": rt, "name": name}))
            try:
                for token in orchestrator.stream_resource_agent(
                    role_prompt=role_prompt,
                    course=course,
                    resource_type=rt,
                    learner_brief=learner_brief,
                    profile_markdown=profile_md,
                    context=context,
                    focus_topic=focus_topic,
                ):
                    parts.append(token)
                    events.put(sse_event("resource_delta", {
                        "type": rt,
                        "name": name,
                        "delta": token,
                    }))

                result = "".join(parts)
                resources[rt] = result
                session_store.add_resource(session_id, rt, name, result)
                events.put(sse_event("resource_done", {
                    "type": rt,
                    "name": name,
                    "content": result,
                }))
            except Exception as exc:
                events.put(sse_event("resource_error", {
                    "type": rt,
                    "name": name,
                    "error": str(exc),
                }))
            finally:
                events.put(None)

        submitted = 0
        with ThreadPoolExecutor(max_workers=_resource_worker_count(len(resource_types))) as executor:
            for rt in resource_types:
                prompt_template = RESOURCE_AGENT_PROMPTS.get(rt)
                if not prompt_template:
                    continue
                executor.submit(generate_one_resource, rt, prompt_template)
                submitted += 1

            completed = 0
            while completed < submitted:
                item = events.get()
                if item is None:
                    completed += 1
                    yield sse_event("stage", {
                        "stage": "resource_generation",
                        "status": "running",
                        "generated": len(resources),
                        "total": submitted,
                    })
                    continue
                yield item

        yield sse_event("stage", {
            "stage": "resource_generation",
            "status": "done",
            "generated": len(resources),
        })

        yield sse_event("done", {"resource_count": len(resources)})

    except Exception as e:
        yield sse_error(str(e))


@router.post("/stream")
async def generate_stream(req: GenerateRequest):
    client = get_spark_client()
    kb = get_knowledge_base()
    session_store = get_session_store()
    orchestrator = AgentOrchestrator(client, kb)

    try:
        session_store.get_session(req.session_id)
    except ValueError:
        return StreamingResponse(
            iter([sse_error("会话不存在")]),
            media_type="text/event-stream",
        )

    return StreamingResponse(
        _generate_resources_stream(
            client, orchestrator, session_store,
            req.session_id, req.course, req.knowledge_points,
            req.resource_types, req.top_k,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/list/{session_id}")
async def list_resources(session_id: str):
    session_store = get_session_store()
    resources = session_store.get_resources(session_id)
    return [
        {
            "id": r.id,
            "resource_type": r.resource_type,
            "resource_name": r.resource_name,
            "content": r.content,
            "created_at": r.created_at,
        }
        for r in resources
    ]


@router.get("/{resource_id}")
async def get_resource(resource_id: int):
    session_store = get_session_store()
    r = session_store.get_resource(resource_id)
    if not r:
        return {"error": "资源不存在"}
    return {
        "id": r.id,
        "resource_type": r.resource_type,
        "resource_name": r.resource_name,
        "content": r.content,
        "created_at": r.created_at,
    }
