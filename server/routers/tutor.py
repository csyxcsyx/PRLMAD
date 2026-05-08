from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from server.dependencies import get_knowledge_base, get_session_store, get_spark_client
from server.models.schemas import TutorRequest
from server.utils.sse import sse_event, sse_done, sse_error
from src.prlmad.agents import AgentOrchestrator, _learner_brief_from_profile

router = APIRouter(prefix="/api/tutor", tags=["tutor"])


async def _tutor_stream(
    client,
    orchestrator: AgentOrchestrator,
    session_store,
    session_id: str,
    course: str,
    question: str,
):
    profile = session_store.get_profile(session_id)
    learner_brief = _learner_brief_from_profile(profile)

    yield sse_event("stage", {"stage": "knowledge_retrieval", "status": "running"})
    query = f"{course} {question} {profile.get('weak_points', '')}"
    snippets = orchestrator.knowledge_base.search(query, course=course, top_k=5)
    context = orchestrator.knowledge_base.format_context(snippets) if snippets else "暂无教材片段参考。"
    citations = [
        f"《{s.title}》{s.page_label}"
        for s in snippets
    ]
    yield sse_event("stage", {"stage": "knowledge_retrieval", "status": "done"})

    answer = orchestrator.tutor_chat(course, learner_brief, question, context)
    yield sse_event("answer", {"content": answer, "citations": citations})

    session_store.add_tutor_log(session_id, question, answer, citations)
    yield sse_done()


@router.post("/stream")
async def tutor_stream(req: TutorRequest):
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
        _tutor_stream(client, orchestrator, session_store, req.session_id, req.course, req.question),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/logs/{session_id}")
async def get_tutor_logs(session_id: str):
    session_store = get_session_store()
    return session_store.get_tutor_logs(session_id)
