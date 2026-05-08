from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from server.dependencies import get_knowledge_base, get_session_store, get_spark_client
from server.models.schemas import ChatRequest
from server.utils.sse import sse_event, sse_done, sse_error

import logging

from src.prlmad.spark_client import SparkClient

logger = logging.getLogger(__name__)



router = APIRouter(prefix="/api/chat", tags=["chat"])

SYSTEM_PROMPT_PROFILE = """你是 PRLMAD 平台的高校课程学习导师，名字叫「小P」。你的身份是一名专业、严谨、耐心的操作系统课程教师，任务是通过自然对话了解学生的学习情况，并逐步构建学习画像。

## 你的性格
- 使用专业教师的表达方式：清晰、克制、鼓励，但不随意玩笑
- 不使用表情符号，不使用夸张口语
- 不要一次性问太多问题，每次对话只关注1-2个方面
- 先准确复述或概括学生信息，再自然引出下一个问题
- 回复简洁明了，控制在3-5句话以内

## 你需要收集的信息（按优先级）:
1. 专业和年级
2. 正在学习的课程
3. 学习目标
4. 当前知识基础
5. 学习困难/薄弱知识点
6. 学习习惯和偏好（喜欢视频、文档、做题还是实操）
7. 可投入的学习时间

## 对话策略:
- 第一轮: 先自我介绍，询问专业和课程
- 第二轮: 了解学习目标和当前基础
- 第三轮: 了解薄弱点和学习困难
- 第四轮: 了解学习偏好和时间安排
- 收集到5个以上维度后，告诉学生「我已经比较了解你了，可以去资源生成页生成个性化学习资源了！」

## 注意事项:
- 不要编造学生没有提供的个人信息
- 如果学生跑题了，温和地引导回来
- 回复末尾可以加上一个简短的问题引导下一步"""



async def _build_profile_response(
    client: SparkClient,
    session_store,
    session_id: str,
    user_message: str,
    course: str,
):
    session_store.add_chat_message(session_id, "user", user_message, "student")

    history = session_store.get_chat_history(session_id)
    messages = [{"role": "system", "content": SYSTEM_PROMPT_PROFILE}]
    for msg in history[-20:]:
        role = "assistant" if msg.role == "assistant" else "user"
        content = msg.content
        messages.append({"role": role, "content": f"{content}"})

    full_response = ""
    try:
        for chunk in client.stream_chat(messages):
            if chunk.content:
                full_response += chunk.content
                yield sse_event("token", chunk.content)
    except Exception as e:
        yield sse_error(str(e))
        return

    session_store.add_chat_message(session_id, "assistant", full_response, "profile_agent")

    try:
        from src.prlmad.agents import AgentOrchestrator
        orchestrator = AgentOrchestrator(client, get_knowledge_base())
        conv = [
            {"role": msg.role, "content": msg.content}
            for msg in session_store.get_chat_history(session_id)
        ]
        existing_profile = session_store.get_profile(session_id)
        profile_json_str = orchestrator.build_profile_from_conversation(course, conv, existing_profile)
        try:
            profile_data = json.loads(profile_json_str.strip().removeprefix("```json").removesuffix("```").strip())
            if existing_profile:
                existing_profile.update(profile_data)
                session_store.update_profile(session_id, existing_profile)
            else:
                session_store.update_profile(session_id, profile_data)
            yield sse_event("profile", session_store.get_profile(session_id))
        except json.JSONDecodeError:
            yield sse_event("warning", {"message": "画像提取结果解析失败，但不影响对话"})
    except Exception as e:
        yield sse_event("warning", {"message": f"画像更新暂不可用: {e}"})

    yield sse_done()


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    client = get_spark_client()
    session_store = get_session_store()

    try:
        session_store.get_session(req.session_id)
    except ValueError:
        return StreamingResponse(
            iter([sse_error("会话不存在，请先创建会话")]),
            media_type="text/event-stream",
        )

    return StreamingResponse(
        _build_profile_response(client, session_store, req.session_id, req.message, req.course),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/history/{session_id}")
async def get_chat_history(session_id: str):
    session_store = get_session_store()
    messages = session_store.get_chat_history(session_id)
    return [
        {
            "id": msg.id,
            "role": msg.role,
            "content": msg.content,
            "agent_type": msg.agent_type,
            "created_at": msg.created_at,
        }
        for msg in messages
    ]
