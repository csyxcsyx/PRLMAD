from __future__ import annotations

from dataclasses import dataclass
import json
import random
import re
import time
from typing import Any, Iterator

try:
    import requests
except ImportError:  # pragma: no cover - exercised when dependencies are not installed yet.
    requests = None

from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener, urlopen


class SparkAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChatChunk:
    content: str = ""
    reasoning_content: str = ""
    raw: dict[str, Any] | None = None


class SparkClient:
    def __init__(
        self,
        api_key: str | None,
        base_url: str,
        model: str = "spark-x",
        user_id: str = "prlmad-demo-user",
        enable_web_search: bool = False,
        offline_fallback: bool = True,
        trust_env_proxy: bool = False,
        timeout: int = 90,
    ):
        self.api_key = api_key.strip() if api_key else None
        self.base_url = base_url.strip()
        self.model = model
        self.user_id = user_id
        self.enable_web_search = enable_web_search
        self.offline_fallback = offline_fallback
        self.trust_env_proxy = trust_env_proxy
        self.timeout = timeout

    def _authorization(self) -> str:
        placeholder_keys = ("your_api_password_here", "您的APIpassword", "APIpassword")
        if not self.api_key or any(item in self.api_key for item in placeholder_keys):
            raise SparkAPIError("SPARK_API_KEY is not configured. Copy .env.example to .env and set your key.")
        if self.api_key.lower().startswith("bearer "):
            return self.api_key
        return f"Bearer {self.api_key}"

    def _body(self, messages: list[dict[str, str]], stream: bool) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "user": self.user_id,
            "messages": messages,
            "stream": stream,
        }
        if self.enable_web_search:
            body["tools"] = [
                {
                    "type": "web_search",
                    "web_search": {"enable": True, "search_mode": "deep"},
                }
            ]
        return body

    def _request(self, messages: list[dict[str, str]], stream: bool):
        headers = {
            "Authorization": self._authorization(),
            "content-type": "application/json",
        }
        body = self._body(messages, stream)

        if requests is None:
            return self._request_with_urllib(body, headers)

        session = requests.Session()
        session.trust_env = self.trust_env_proxy
        try:
            response = session.post(
                url=self.base_url,
                json=body,
                headers=headers,
                stream=stream,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            session.close()
            raise SparkAPIError(f"Spark API request failed: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text[:1200]
            response.close()
            session.close()
            raise SparkAPIError(f"Spark API returned HTTP {response.status_code}: {detail}")
        return _RequestsResponseAdapter(response, session)

    def _request_with_urllib(self, body: dict[str, Any], headers: dict[str, str]):
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = Request(self.base_url, data=payload, headers=headers, method="POST")
        try:
            if self.trust_env_proxy:
                response = urlopen(request, timeout=self.timeout)
            else:
                opener = build_opener(ProxyHandler({}))
                response = opener.open(request, timeout=self.timeout)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1200]
            raise SparkAPIError(f"Spark API returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise SparkAPIError(f"Spark API request failed: {exc.reason}") from exc
        return _UrllibResponseAdapter(response)

    def _request_with_retry(
        self, messages: list[dict[str, str]], stream: bool, max_retries: int = 3
    ):
        base_delay = 1.0
        for attempt in range(max_retries):
            try:
                return self._request(messages, stream)
            except SparkAPIError as exc:
                if attempt == max_retries - 1:
                    raise
                cause_name = exc.__cause__.__class__.__name__ if exc.__cause__ else ""
                if "HTTP 5" in str(exc) or cause_name in {
                    "ConnectionError",
                    "Timeout",
                    "ConnectTimeout",
                    "ReadTimeout",
                    "SSLError",
                    "URLError",
                }:
                    delay = base_delay * (2**attempt) + random.uniform(0, 0.5)
                    time.sleep(delay)
                    continue
                raise

    def stream_chat(self, messages: list[dict[str, str]]) -> Iterator[ChatChunk]:
        try:
            response = self._request_with_retry(messages, stream=True)
        except SparkAPIError as exc:
            if not self.offline_fallback:
                raise
            for part in _chunk_text(_offline_response(messages, str(exc))):
                yield ChatChunk(content=part, raw={"offline_fallback": True, "error": str(exc)})
            return

        with response:
            for raw_line in response.iter_lines():
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith(b"data:"):
                    line = line[5:].strip()
                if line == b"[DONE]":
                    break
                try:
                    payload = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                choice = (payload.get("choices") or [{}])[0]
                delta = choice.get("delta") or {}
                yield ChatChunk(
                    content=delta.get("content") or "",
                    reasoning_content=delta.get("reasoning_content") or "",
                    raw=payload,
                )

    def chat(self, messages: list[dict[str, str]], stream: bool = True) -> str:
        if stream:
            parts: list[str] = []
            for chunk in self.stream_chat(messages):
                parts.append(chunk.content)
            return "".join(parts)

        try:
            response = self._request_with_retry(messages, stream=False)
        except SparkAPIError as exc:
            if not self.offline_fallback:
                raise
            return _offline_response(messages, str(exc))

        with response:
            payload = response.json()
        choice = (payload.get("choices") or [{}])[0]
        message = choice.get("message") or choice.get("delta") or {}
        return message.get("content") or ""


class _UrllibResponseAdapter:
    def __init__(self, response):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def iter_lines(self):
        return self._response

    def json(self) -> dict[str, Any]:
        return json.loads(self._response.read().decode("utf-8"))

    def close(self) -> None:
        self._response.close()


class _RequestsResponseAdapter:
    def __init__(self, response, session):
        self._response = response
        self._session = session

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def iter_lines(self):
        return self._response.iter_lines()

    def json(self) -> dict[str, Any]:
        return self._response.json()

    def close(self) -> None:
        self._response.close()
        self._session.close()


def _chunk_text(text: str, size: int = 18) -> Iterator[str]:
    for start in range(0, len(text), size):
        yield text[start:start + size]


def _messages_text(messages: list[dict[str, str]]) -> tuple[str, str]:
    system = "\n".join(m.get("content", "") for m in messages if m.get("role") == "system")
    user = "\n".join(m.get("content", "") for m in messages if m.get("role") == "user")
    return system, user


def _offline_response(messages: list[dict[str, str]], error: str) -> str:
    system, user = _messages_text(messages)
    if "输出 JSON" in system or "JSON 格式输出" in user or "JSON 格式" in user:
        if "学习效果评估" in system or "多维度学习效果评估" in user:
            return _offline_eval_json(user)
        if "学习路径" in system or "学习路径" in user:
            return _offline_path_json(user)
        if "学习画像" in system or "画像" in user:
            return json.dumps(_infer_profile(user), ensure_ascii=False)

    if "学习画像构建助手" in system:
        return _offline_chat_reply(user, error)
    if "智能辅导智能体" in system:
        return _offline_tutor_reply(user, error)
    if "学习画像智能体" in system:
        return _offline_profile_markdown(user, error)
    if "学习路径规划智能体" in system:
        return _offline_path_markdown(user, error)
    if "学习效果评估智能体" in system:
        return _offline_assessment_markdown(user, error)
    return _offline_resource_markdown(system, user, error)


def _offline_notice(error: str) -> str:
    return (
        "> 当前为本地演示模式：后端暂时无法连接 Spark API。"
        "真实模型恢复后会自动使用在线生成。\n\n"
    )


def _infer_profile(text: str) -> dict[str, str]:
    profile = {
        "major": "",
        "grade": "",
        "goal": "",
        "knowledge_level": "",
        "cognitive_style": "",
        "preferences": "",
        "weak_points": "",
        "available_time": "",
        "learning_motivation": "",
        "problem_solving": "",
        "practical_ability": "",
    }

    if "软件工程" in text:
        profile["major"] = "软件工程"
    elif "计算机" in text:
        profile["major"] = "计算机相关专业"
    else:
        match = re.search(r"我是(.{1,18}?专业)", text)
        if match:
            profile["major"] = match.group(1)

    grade = re.search(r"(大[一二三四五]|研[一二三]|本科[一二三四]年级)", text)
    if grade:
        profile["grade"] = grade.group(1)

    goal = re.search(r"(?:想|希望|目标是|打算)([^。！？\n]{4,60})", text)
    if goal:
        profile["goal"] = goal.group(1).strip("，, ")
    elif "操作系统" in text:
        profile["goal"] = "系统学习操作系统核心概念"

    learned = re.search(r"学过([^。！？\n]{2,50})", text)
    if learned:
        profile["knowledge_level"] = "已有基础：" + learned.group(1).strip("，, ")
    elif any(word in text for word in ("基础", "了解", "不多", "模糊")):
        profile["knowledge_level"] = "基础待巩固，需要从概念和案例入手"

    weak_sentence = re.search(r"([^。！？\n]*(?:不太明白|不明白|薄弱|困难|模糊|抽象|不会)[^。！？\n]*)", text)
    if weak_sentence:
        profile["weak_points"] = weak_sentence.group(1).strip("，, ")

    pref_sentence = re.search(r"([^。！？\n]*(?:喜欢|偏好|更适合)[^。！？\n]*)", text)
    if pref_sentence:
        profile["preferences"] = pref_sentence.group(1).strip("，, ")

    time_match = re.search(r"((?:每天|每周)?[^。！？\n]{0,12}\d+(?:\.\d+)?\s*(?:小时|分钟|h|min)[^。！？\n]*)", text)
    if time_match:
        profile["available_time"] = time_match.group(1).strip("，, ")

    if profile["preferences"]:
        profile["cognitive_style"] = "适合用图解、示例和练习驱动学习"
    if profile["goal"]:
        profile["learning_motivation"] = "目标导向，希望围绕课程重点提升理解和应用能力"
    if "代码" in text or "实践" in text or "实验" in text:
        profile["practical_ability"] = "愿意通过代码或实验理解操作系统机制"
    return profile


def _topic_from_prompt(prompt: str) -> str:
    for label in ("知识点关注：", "学生问题：", "资源类型：", "课程："):
        if label in prompt:
            value = prompt.split(label, 1)[1].splitlines()[0].strip()
            if value and value != "未指定":
                return value
    for key in ("进程", "死锁", "内存", "页面置换", "虚拟内存", "信号量", "文件系统"):
        if key in prompt:
            return key
    return "操作系统核心知识"


def _offline_chat_reply(user: str, error: str) -> str:
    profile = _infer_profile(user)
    next_question = "你现在最想先攻克哪个知识点，比如进程同步、死锁、内存管理或文件系统？"
    if profile.get("weak_points"):
        next_question = "这个薄弱点我记下了。你更希望用图解、做题，还是代码实验来突破它？"
    return (
        _offline_notice(error)
        + "收到，我已经记录了你的学习信息。"
        + f"目前画像中比较明确的是：{profile.get('major') or '专业方向待补充'}，"
        + f"目标是{profile.get('goal') or '学习操作系统'}。"
        + next_question
    )


def _offline_profile_markdown(user: str, error: str) -> str:
    profile = _infer_profile(user)
    rows = [
        ("专业方向", profile["major"] or "待补充"),
        ("学习目标", profile["goal"] or "掌握操作系统核心概念"),
        ("知识基础", profile["knowledge_level"] or "需要通过对话进一步确认"),
        ("资源偏好", profile["preferences"] or "建议混合使用讲解、图示、练习和实验"),
        ("薄弱环节", profile["weak_points"] or "待通过辅导和练习发现"),
        ("学习节奏", profile["available_time"] or "建议每日 45-60 分钟"),
    ]
    body = "\n".join(f"- **{name}**：{value}" for name, value in rows)
    return _offline_notice(error) + "## 学习画像\n\n" + body


def _offline_resource_markdown(system: str, user: str, error: str) -> str:
    topic = _topic_from_prompt(user)
    if "题库智能体" in system:
        return _offline_notice(error) + f"""## {topic} 练习题

1. **选择题**：下列哪一项最能体现操作系统资源管理的目标？
   - A. 只提高单个程序速度
   - B. 在安全、公平和效率之间协调资源使用
   - C. 只负责图形界面
   - D. 只管理网络连接
   - **答案**：B

2. **简答题**：请说明 {topic} 与进程调度、内存管理或同步机制之间的联系。

3. **实践题**：选择一个课堂案例，画出关键状态变化，并说明每一步可能出现的风险。
"""
    if "知识结构智能体" in system:
        return _offline_notice(error) + f"""```mermaid
graph TD
    A["{topic}"] --> B["核心概念"]
    A --> C["典型问题"]
    A --> D["解决策略"]
    D --> E["算法或机制"]
    D --> F["边界条件"]
```

建议先理解概念边界，再用例题验证条件和状态转换。
"""
    if "实践案例智能体" in system:
        return _offline_notice(error) + f"""## {topic} 实操案例

目标：用一个小实验观察操作系统机制的输入、状态变化和输出。

步骤：
1. 明确实验对象和资源约束。
2. 设计两个对比场景：正常执行与边界情况。
3. 记录状态变化、耗时和异常现象。
4. 回到教材概念，解释观察结果。

检查点：能否说明每个状态变化背后的系统原因。
"""
    return _offline_notice(error) + f"""## {topic} 学习材料

### 核心概念
围绕 {topic} 学习时，先抓住对象、状态、操作和约束四个层次。

### 学习建议
- 先阅读教材相关片段，标出定义和必要条件。
- 再用一个具体例子走完整流程。
- 最后做 3-5 道小题，检查是否能迁移到新场景。

### 易错提醒
不要只背结论，要能解释条件为什么成立，以及条件变化后结果会怎样。
"""


def _offline_path_json(user: str) -> str:
    topic = _topic_from_prompt(user)
    data = {
        "title": f"{topic} 7天学习路径",
        "steps": [
            {
                "day": day,
                "topic": f"{topic} 第{day}步",
                "goal": goal,
                "content": content,
                "exercises": ["复述核心概念", "完成一个小例题"],
                "resources": ["课程讲解文档", "练习题库", "实操案例"],
                "estimated_time": "45-60分钟",
                "checkpoint": "能用自己的话解释并完成对应练习",
            }
            for day, goal, content in [
                (1, "建立概念地图", "梳理定义、对象和基本术语。"),
                (2, "理解运行机制", "按输入、状态、输出分析关键流程。"),
                (3, "掌握典型算法", "比较常见策略和适用条件。"),
                (4, "处理边界情况", "分析异常、冲突和资源竞争。"),
                (5, "完成实践验证", "用代码、伪代码或流程图复现实例。"),
                (6, "集中练习纠错", "整理错题并标注原因。"),
                (7, "复盘迁移应用", "总结知识点之间的联系。"),
            ]
        ],
        "adjustment_strategy": "若某天检查点未通过，次日先复习该主题并减少新内容输入。",
    }
    return json.dumps(data, ensure_ascii=False)


def _offline_path_markdown(user: str, error: str) -> str:
    topic = _topic_from_prompt(user)
    return _offline_notice(error) + f"""## {topic} 学习路径

1. 建立概念地图：明确术语、对象和基本关系。
2. 走通机制流程：用一个例子说明状态如何变化。
3. 比较典型算法：关注适用条件、优缺点和边界。
4. 做题纠错：把错误归因到概念、条件或步骤。
5. 实践验证：用实验或伪代码复现关键过程。
"""


def _offline_tutor_reply(user: str, error: str) -> str:
    topic = _topic_from_prompt(user)
    return _offline_notice(error) + f"""## 解答思路：{topic}

先把问题拆成三层：

1. **对象**：题目讨论的是进程、内存页、文件还是设备资源。
2. **状态**：这些对象在什么条件下发生变化。
3. **规则**：操作系统用什么算法或同步机制约束变化。

建议你把题目中的关键词标出来，再对应到教材中的定义、必要条件和例子。若涉及算法，先手算一轮状态变化，再总结规律。
"""


def _offline_assessment_markdown(user: str, error: str) -> str:
    return _offline_notice(error) + """## 学习效果评估方案

- **知识掌握度**：能否准确复述概念并解释边界。
- **练习表现**：题目错误是否集中在同一类条件判断。
- **实践能力**：能否用代码、流程图或例子复现机制。
- **资源利用率**：讲解、题库、路径和辅导是否形成闭环。
- **后续调整**：薄弱点连续两次未通过时，优先回到教材片段和例题。
"""


def _offline_eval_json(user: str) -> str:
    data = {
        "dimensions": {
            "knowledge_mastery": {"score": 68, "comment": "已有学习活动记录，建议继续用例题巩固关键概念。"},
            "progress_completion": {"score": 60, "comment": "路径进度仍需通过每日检查点确认。"},
            "exercise_accuracy": {"score": 55, "comment": "暂无足够练习正确率数据，先按中等水平估计。"},
            "weak_points_improvement": {"score": 58, "comment": "薄弱点需要通过辅导记录和错题继续观察。"},
            "resource_utilization": {"score": 72, "comment": "已生成或使用多类资源，具备继续推进基础。"},
            "learning_engagement": {"score": 70, "comment": "有会话和学习行为，投入度较好。"},
        },
        "overall_assessment": "当前评估由本地演示模式生成，适合用于流程预览。接入 Spark 后会根据更丰富的上下文生成个性化评估。",
        "suggestions": ["围绕薄弱点做一组小题", "把教材定义和例题整理成一页速查表", "完成一次实践验证再进行复评"],
        "profile_updates": {},
    }
    return json.dumps(data, ensure_ascii=False)
