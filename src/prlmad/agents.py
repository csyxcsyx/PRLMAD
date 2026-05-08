from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable, Protocol

from .knowledge_base import KnowledgeBase
from .safety import SYSTEM_SAFETY_POLICY, check_user_request


class ChatClient(Protocol):
    def chat(self, messages: list[dict[str, str]], stream: bool = True) -> str:
        ...


ProgressCallback = Callable[[str, dict], None]


RESOURCE_AGENT_PROMPTS: dict[str, str] = {
    "lecture_note": "你是操作系统课程讲授教师，输出结构化 Markdown 讲义，包含定义、机制、联系、易错点和课堂检查题。",
    "concept_map": "你是操作系统课程知识结构教师，输出 Mermaid mindmap 或 graph TD，并用严谨语言说明关键关系。",
    "exercises": "你是操作系统课程命题教师，生成选择题、判断题、简答题和实践题，给出答案、解析和考查意图。",
    "extended_reading": "你是操作系统课程拓展阅读教师，生成围绕教材知识点的延伸阅读材料、阅读目标和思考问题。",
    "case_project": "你是操作系统实验课教师，生成可操作的 Python 或操作系统实验案例，包含步骤、代码、观察指标和实验反思。",
    "video_script": "你是操作系统课程教学设计教师，生成 3-5 分钟教学视频脚本，包含分镜、旁白和板书要点。",
    "ppt_outline": "你是操作系统课程课件设计教师，生成 PPT 课件大纲，每页包含标题、核心概念、讲解备注和课堂提问。",
    "task_checklist": "你是操作系统课程学习规划教师，输出结构化学习任务清单，包含每日任务、完成标准和自测问题。",
    "review_material": "你是操作系统课程复习指导教师，生成阶段性复习资料，包含知识点速查表、典型题和易错提醒。",
}

DEFAULT_RESOURCE_TYPES = [
    "lecture_note",
    "concept_map",
    "exercises",
    "case_project",
    "video_script",
    "ppt_outline",
    "task_checklist",
]

RESOURCE_TYPE_NAMES = {
    "lecture_note": "课程讲解文档",
    "concept_map": "知识点思维导图",
    "exercises": "练习题库",
    "extended_reading": "拓展阅读材料",
    "case_project": "代码类实操案例",
    "video_script": "短视频/动画脚本",
    "ppt_outline": "PPT 课件大纲",
    "task_checklist": "学习任务清单",
    "review_material": "阶段性复习资料",
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
        {
            "role": "system",
            "content": (
                f"{SYSTEM_SAFETY_POLICY}\n"
                "你始终以高校课程专业教师的身份回答。表达应严谨、清晰、结构化，"
                "先解释概念依据，再给出学习建议；不使用表情符号，不使用夸张营销式语言。\n"
                f"{role_prompt}"
            ),
        },
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


def _learner_brief_from_profile(profile: dict) -> str:
    lines: list[str] = []
    field_map = {
        "major": "专业",
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
    }
    for key, label in field_map.items():
        value = profile.get(key, "")
        if value:
            lines.append(f"{label}：{value}")
        else:
            lines.append(f"{label}：未提供")
    return "\n".join(lines)


def _profile_dimensions_from_dict(profile: dict) -> str:
    parts: list[str] = []
    dims = [
        ("专业方向", profile.get("major", "")),
        ("年级", profile.get("grade", "")),
        ("知识基础水平", profile.get("knowledge_level", "")),
        ("课程学习目标", profile.get("goal", "")),
        ("认知风格", profile.get("cognitive_style", "")),
        ("学习习惯", profile.get("learning_habits", "")),
        ("学习兴趣", profile.get("preferences", "")),
        ("易错知识点与薄弱环节", profile.get("weak_points", "")),
        ("学习进度", profile.get("learning_progress", "")),
        ("资源偏好", profile.get("preferences", "")),
        ("时间安排", profile.get("available_time", "")),
        ("学习动机", profile.get("learning_motivation", "")),
        ("问题解决能力", profile.get("problem_solving", "")),
        ("实践能力", profile.get("practical_ability", "")),
        ("历史测评结果", profile.get("assessment_history", "")),
    ]
    for name, value in dims:
        if value:
            parts.append(f"- **{name}**: {value}")
    return "\n".join(parts) if parts else "暂无画像信息"


class AgentOrchestrator:
    def __init__(self, client: ChatClient, knowledge_base: KnowledgeBase):
        self.client = client
        self.knowledge_base = knowledge_base

    def generate(
        self,
        request: GenerationRequest,
        on_progress: ProgressCallback | None = None,
    ) -> GenerationResult:
        def emit(stage: str, detail: dict | None = None):
            if on_progress:
                on_progress(stage, detail or {})

        emit("safety_check", {"status": "running"})
        safety = check_user_request(request.learner.goal + request.learner.weak_points)
        if not safety.allowed:
            raise ValueError("请求包含不适合生成的内容：" + "；".join(safety.warnings))
        emit("safety_check", {"status": "done", "allowed": True})

        emit("knowledge_retrieval", {"status": "running"})
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
        emit("knowledge_retrieval", {"status": "done", "context_length": len(context), "snippet_count": len(snippets)})

        learner_brief = _learner_brief(request.learner)

        emit("profile_analysis", {"status": "running"})
        profile_markdown = self._profile_agent(request.course, learner_brief, context)
        emit("profile_analysis", {"status": "done", "profile": profile_markdown})

        resources: dict[str, str] = {}
        emit("resource_generation", {"status": "running", "total_types": len(request.resource_types)})

        resource_futures: dict = {}
        with ThreadPoolExecutor(max_workers=3) as executor:
            for resource_type in request.resource_types:
                prompt_template = RESOURCE_AGENT_PROMPTS.get(resource_type)
                if not prompt_template:
                    continue
                future = executor.submit(
                    self._resource_agent,
                    role_prompt=prompt_template,
                    course=request.course,
                    resource_type=resource_type,
                    learner_brief=learner_brief,
                    profile_markdown=profile_markdown,
                    context=context,
                )
                resource_futures[future] = resource_type

            for future in as_completed(resource_futures):
                resource_type = resource_futures[future]
                try:
                    resources[resource_type] = future.result()
                    emit("resource_generation", {
                        "status": "progress",
                        "agent": resource_type,
                        "agent_name": RESOURCE_TYPE_NAMES.get(resource_type, resource_type),
                        "state": "done",
                    })
                except Exception as exc:
                    resources[resource_type] = (
                        f"生成失败: {exc}\n\n请尝试重新生成该资源，或调整资源类型后重试。"
                    )
                    emit("resource_generation", {
                        "status": "progress",
                        "agent": resource_type,
                        "agent_name": RESOURCE_TYPE_NAMES.get(resource_type, resource_type),
                        "state": "error",
                        "error": str(exc),
                    })

        emit("path_planning", {"status": "running"})
        path_plan = self._path_planner(request.course, learner_brief, profile_markdown, context, resources)
        emit("path_planning", {"status": "done"})

        emit("assessment", {"status": "running"})
        assessment = self._assessment_agent(request.course, learner_brief, profile_markdown, context)
        emit("assessment", {"status": "done"})

        emit("done", {"resource_count": len(resources)})
        return GenerationResult(profile_markdown, resources, path_plan, assessment, citations, [])

    def _profile_agent(self, course: str, learner_brief: str, context: str) -> str:
        prompt = f"""课程：{course}

学习者原始信息：
{learner_brief}

教材片段：
{context}

请构建动态学习画像，至少包含 6 个维度：
知识基础、认知风格、学习目标、学习历史、资源偏好、易错点偏好、学习节奏、动机/反馈偏好。
输出 Markdown，不要编造未提供的个人隐私。"""
        return self.client.chat(_messages("你是学习画像智能体，也是一名课程学习诊断教师。", prompt))

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
- 使用专业教师授课口吻，先给出定义和条件，再解释推理过程，最后给学习检查点。
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
        return self.client.chat(_messages("你是学习路径规划智能体，也是一名课程教学设计教师。", prompt))

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
        return self.client.chat(_messages("你是学习效果评估智能体，也是一名课程评价教师。", prompt))

    def build_profile_from_conversation(
        self,
        course: str,
        conversation: list[dict[str, str]],
        existing_profile: dict | None = None,
    ) -> str:
        existing_text = ""
        if existing_profile:
            existing_text = f"\n当前已有的画像信息：\n{_profile_dimensions_from_dict(existing_profile)}"

        conversation_text = "\n".join(
            f"{'学生' if m['role'] == 'user' else '系统'}: {m['content']}"
            for m in conversation
        )
        prompt = f"""课程：{course}

以下是系统与学生之间的自然对话记录：
{conversation_text}
{existing_text}

请从对话中提取或更新学生学习画像，以 JSON 格式输出，包含以下字段（至少 6 个有值）：
- major: 专业方向
- grade: 年级
- goal: 课程学习目标
- knowledge_level: 知识基础水平
- cognitive_style: 认知风格与学习习惯
- preferences: 学习兴趣与资源偏好
- weak_points: 易错知识点与薄弱环节
- available_time: 可用学习时间安排
- learning_motivation: 学习动机
- problem_solving: 问题解决能力
- practical_ability: 实践能力

只基于对话中明确提及的信息填写对应字段，未提及的字段留空字符串。
输出格式：纯 JSON，不要包含 markdown 代码块标记。"""
        return self.client.chat(_messages("你是学习画像提取智能体，输出 JSON，判断标准应像专业教师一样审慎。", prompt))

    def tutor_chat(
        self,
        course: str,
        learner_brief: str,
        question: str,
        context: str = "",
    ) -> str:
        if not context:
            query = f"{course} {question}"
            snippets = self.knowledge_base.search(query, course=course, top_k=5)
            context = self.knowledge_base.format_context(snippets) if snippets else "当前知识库无相关教材片段。"

        prompt = f"""课程：{course}

学习者信息：
{learner_brief}

教材知识库片段：
{context}

学生问题：{question}

请基于教材片段提供辅导回答。要求：
- 使用操作系统课程教师的口吻，回答要有定义、推理、例子和检查点。
- 给出清晰的解题思路或概念解释
- 标注关键知识点和易错提醒
- 若教材片段不足，明确说明并建议查阅方向
- 提供进一步学习建议
- 用 Markdown 格式输出。"""
        return self.client.chat(_messages("你是智能辅导智能体，也是一名操作系统课程教师。", prompt))

    def generate_learning_path(
        self,
        course: str,
        profile: dict,
        knowledge_points: str = "",
    ) -> str:
        learner_brief = _learner_brief_from_profile(profile)
        if knowledge_points:
            context_query = f"{course} {knowledge_points}"
        else:
            context_query = f"{course} {profile.get('goal', '')} {profile.get('weak_points', '')}"
        snippets = self.knowledge_base.search(context_query, course=course, top_k=5)
        context = self.knowledge_base.format_context(snippets) if snippets else "暂无教材片段参考。"

        prompt = f"""课程：{course}

学习者信息：
{learner_brief}

知识点关注：{knowledge_points or '未指定'}

教材依据：
{context}

请规划 7 天以内的个性化学习路径。用 JSON 格式输出：
{{
  "title": "学习路径标题",
  "steps": [
    {{
      "day": 1,
      "topic": "学习主题",
      "goal": "当日学习目标",
      "content": "学习内容描述",
      "exercises": ["练习1", "练习2"],
      "resources": ["推荐资源1"],
      "estimated_time": "预计用时",
      "checkpoint": "检查点"
    }}
  ],
  "adjustment_strategy": "动态调整策略说明"
}}

输出格式：纯 JSON，不要包含 markdown 代码块标记。"""
        return self.client.chat(_messages("你是学习路径规划智能体，也是一名专业课程教学设计教师。", prompt))

    def evaluate_learning(
        self,
        course: str,
        profile: dict,
        activities: list[dict],
    ) -> str:
        learner_brief = _learner_brief_from_profile(profile)
        activities_text = "\n".join(
            f"- [{a.get('type', '')}] {a.get('description', '')}: {a.get('result', '')}"
            for a in activities
        )
        prompt = f"""课程：{course}

学习者信息：
{learner_brief}

学习活动记录：
{activities_text}

请进行多维度学习效果评估。用 JSON 格式输出：
{{
  "dimensions": {{
    "knowledge_mastery": {{ "score": 0-100, "comment": "评语" }},
    "progress_completion": {{ "score": 0-100, "comment": "评语" }},
    "exercise_accuracy": {{ "score": 0-100, "comment": "评语" }},
    "weak_points_improvement": {{ "score": 0-100, "comment": "评语" }},
    "resource_utilization": {{ "score": 0-100, "comment": "评语" }},
    "learning_engagement": {{ "score": 0-100, "comment": "评语" }}
  }},
  "overall_assessment": "综合评估",
  "suggestions": ["改进建议1", "改进建议2"],
  "profile_updates": {{ "字段名": "建议更新值" }}
}}

输出格式：纯 JSON，不要包含 markdown 代码块标记。"""
        return self.client.chat(_messages("你是学习效果评估智能体，也是一名课程评价教师。", prompt))
