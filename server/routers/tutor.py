from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from server.dependencies import get_knowledge_base, get_session_store, get_spark_client
from server.models.schemas import TutorRequest
from server.utils.sse import sse_event, sse_done, sse_error
from src.prlmad.agents import AgentOrchestrator, _learner_brief_from_profile

router = APIRouter(prefix="/api/tutor", tags=["tutor"])


def _fallback_tutor_answer(course: str, question: str, error: str = "") -> str:
    note = f"\n\n> 后端生成时遇到问题：{error}" if error else ""
    return f"""## 解答思路：{question}

我先用本地兜底方式给你一个可执行的学习思路。你可以把问题拆成三层：

1. **对象**：这个问题涉及进程、线程、内存页、文件还是设备资源。
2. **状态**：对象在什么条件下发生变化。
3. **规则**：{course} 中用什么机制、算法或约束来处理这种变化。

建议先回到教材定义，再配一个小例子走完整流程。如果是算法题，先手算一轮状态变化；如果是概念题，先写出“定义、条件、例子、易错点”四项。{note}
"""


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
    citations: list[str] = []

    try:
        yield sse_event("stage", {"stage": "knowledge_retrieval", "status": "running"})
        query = f"{course} {question} {profile.get('weak_points', '')}"
        snippets = orchestrator.knowledge_base.search(query, course=course, top_k=5)
        context = orchestrator.knowledge_base.format_context(snippets) if snippets else "暂无教材片段参考。"
        citations = [
            f"《{s.title}》{s.page_label}"
            for s in snippets
        ]
        yield sse_event("stage", {"stage": "knowledge_retrieval", "status": "done", "snippet_count": len(snippets)})

        answer = orchestrator.tutor_chat(course, learner_brief, question, context).strip()
        if not answer:
            answer = _fallback_tutor_answer(course, question, "模型返回了空内容")
    except Exception as exc:
        answer = _fallback_tutor_answer(course, question, str(exc))
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
