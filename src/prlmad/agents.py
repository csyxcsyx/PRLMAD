from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Protocol

from .knowledge_base import KnowledgeBase, SearchResult
from .safety import SYSTEM_SAFETY_POLICY, check_user_request


class ChatClient(Protocol):
    def chat(self, messages: list[dict[str, str]], stream: bool = True) -> str:
        ...


RESOURCE_AGENT_PROMPTS: dict[str, str] = {
    "lecture_note": "你是课程讲解智能体，输出结构化 Markdown 讲解文档，包含概念、联系、易错点和学习建议。",
    "concept_map": "你是知识结构智能体，输出 Mermaid mindmap 或 graph TD，并补充关键关系说明。",
    "exercises": "你是题库智能体，生成选择题、判断题、简答题和实践题，给出答案与解析。",
    "extended_reading": "你是拓展阅读智能体，生成围绕教材知识点的延伸阅读材料和阅读问题。",
    "case_project": "你是实践案例智能体，生成可操作的 Python 或操作系统实验案例，包含步骤、代码和观察指标。",
    "video_script": "你是多模态脚本智能体，生成 3-5 分钟短视频/动画脚本，包含分镜、旁白和画面元素。",
}


DEFAULT_RESOURCE_TYPES = [
    "lecture_note",
    "concept_map",
    "exercises",
    "case_project",
    "video_script",
]


RESOURCE_TYPE_NAMES = {
    "lecture_note": "课程讲解文档",
    "concept_map": "知识点思维导图",
    "exercises": "练习题库",
    "extended_reading": "拓展阅读材料",
    "case_project": "代码类实操案例",
    "video_script": "短视频/动画脚本",
}


@dataclass
class LearnerInput:
    major: str = ""
    goal: str = ""
    knowledge_level: str = ""
    learning_history: str = ""
    preferences: str = ""
    weak_points: str = ""
    available_time: str = ""


@dataclass
class GenerationRequest:
    course: str
    learner: LearnerInput
    resource_types: list[str] = field(default_factory=lambda: list(DEFAULT_RESOURCE_TYPES))
    top_k: int = 6


@dataclass
class GenerationResult:
    profile_markdown: str
    resources: dict[str, str]
    path_plan: str
    assessment: str
    citations: list[str]
    steps: list[str]

    def to_markdown(self) -> str:
        parts = ["# 个性化学习资源包", "## 学习画像", self.profile_markdown]
        for key, content in self.resources.items():
            parts.extend([f"## {RESOURCE_TYPE_NAMES.get(key, key)}", content])
        parts.extend(["## 个性化学习路径", self.path_plan, "## 学习效果评估", self.assessment])
        if self.citations:
            parts.append("## 检索来源")
            parts.extend(f"- {item}" for item in self.citations)
        return "\n\n".join(parts)


def _messages(role_prompt: str, user_prompt: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": f"{SYSTEM_SAFETY_POLICY}\n{role_prompt}"},
        {"role": "user", "content": user_prompt},
    ]


def _learner_brief(learner: LearnerInput) -> str:
    return "\n".join(
        [
            f"专业：{learner.major or '未提供'}",
            f"学习目标：{learner.goal or '未提供'}",
            f"知识基础：{learner.knowledge_level or '未提供'}",
            f"学习历史：{learner.learning_history or '未提供'}",
            f"资源偏好：{learner.preferences or '未提供'}",
            f"易错点/薄弱点：{learner.weak_points or '未提供'}",
            f"可用学习时间：{learner.available_time or '未提供'}",
        ]
    )


class AgentOrchestrator:
    def __init__(self, client: ChatClient, knowledge_base: KnowledgeBase):
        self.client = client
        self.knowledge_base = knowledge_base

    def generate(self, request: GenerationRequest) -> GenerationResult:
        safety = check_user_request(request.learner.goal + request.learner.weak_points)
        if not safety.allowed:
            raise ValueError("请求包含不适合生成的内容：" + "；".join(safety.warnings))

        steps = ["画像智能体分析学习者输入"]
        query = " ".join(
            [
                request.course,
                request.learner.goal,
                request.learner.knowledge_level,
                request.learner.weak_points,
            ]
        )
        snippets = self.knowledge_base.search(query, course=request.course, top_k=request.top_k)
        context = self.knowledge_base.format_context(snippets)
        if not context:
            context = "当前知识库没有检索到相关教材片段。"
        citations = [
            f"《{item.title}》{item.page_label}，chunk #{item.chunk_id}" for item in snippets
        ]

        learner_brief = _learner_brief(request.learner)
        profile_markdown = self._profile_agent(request.course, learner_brief, context)
        steps.append("检索智能体召回教材片段")

        resources: dict[str, str] = {}
        for resource_type in request.resource_types:
            prompt = RESOURCE_AGENT_PROMPTS.get(resource_type)
            if not prompt:
                continue
            resources[resource_type] = self._resource_agent(
                role_prompt=prompt,
                course=request.course,
                resource_type=resource_type,
                learner_brief=learner_brief,
                profile_markdown=profile_markdown,
                context=context,
            )
            steps.append(f"{RESOURCE_TYPE_NAMES.get(resource_type, resource_type)}智能体完成生成")

        path_plan = self._path_planner(request.course, learner_brief, profile_markdown, context, resources)
        steps.append("路径规划智能体完成学习顺序与推送建议")

        assessment = self._assessment_agent(request.course, learner_brief, profile_markdown, context)
        steps.append("评估智能体完成学习效果评估方案")

        return GenerationResult(profile_markdown, resources, path_plan, assessment, citations, steps)

    def _profile_agent(self, course: str, learner_brief: str, context: str) -> str:
        prompt = f"""课程：{course}

学习者原始信息：
{learner_brief}

教材片段：
{context}

请构建动态学习画像，至少包含 6 个维度：
知识基础、认知风格、学习目标、学习历史、资源偏好、易错点偏好、学习节奏、动机/反馈偏好。
输出 Markdown，不要编造未提供的个人隐私。"""
        return self.client.chat(_messages("你是学习画像智能体。", prompt))

    def _resource_agent(
        self,
        role_prompt: str,
        course: str,
        resource_type: str,
        learner_brief: str,
        profile_markdown: str,
        context: str,
    ) -> str:
        prompt = f"""课程：{course}
资源类型：{RESOURCE_TYPE_NAMES.get(resource_type, resource_type)}

学习者信息：
{learner_brief}

学习画像：
{profile_markdown}

教材依据：
{context}

请生成个性化学习资源。要求：
- 用 Markdown。
- 关键概念和结论尽量引用 [资料1]、[资料2] 等来源。
- 如果教材片段不足，明确说明不足位置。
- 内容要适合大学生自主学习，不生成与课程目标无关的泛泛建议。"""
        return self.client.chat(_messages(role_prompt, prompt))

    def _path_planner(
        self,
        course: str,
        learner_brief: str,
        profile_markdown: str,
        context: str,
        resources: dict[str, str],
    ) -> str:
        resource_index = "\n".join(f"- {RESOURCE_TYPE_NAMES.get(key, key)}" for key in resources)
        prompt = f"""课程：{course}

学习者信息：
{learner_brief}

学习画像：
{profile_markdown}

已生成资源：
{resource_index}

教材依据：
{context}

请规划 7 天以内的个性化学习路径，包含学习步骤、资源使用顺序、每日检查点、复习触发条件和动态调整策略。"""
        return self.client.chat(_messages("你是学习路径规划智能体。", prompt))

    def _assessment_agent(
        self,
        course: str,
        learner_brief: str,
        profile_markdown: str,
        context: str,
    ) -> str:
        prompt = f"""课程：{course}

学习者信息：
{learner_brief}

学习画像：
{profile_markdown}

教材依据：
{context}

请设计学习效果评估方案，包含行为数据、练习表现、资源使用反馈、知识掌握度和后续推送调整规则。"""
        return self.client.chat(_messages("你是学习效果评估智能体。", prompt))

    @staticmethod
    def parse_json_profile(text: str) -> dict[str, object]:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}

