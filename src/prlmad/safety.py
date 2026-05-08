from __future__ import annotations

from dataclasses import dataclass


SYSTEM_SAFETY_POLICY = """你是面向高校课程学习的多智能体系统。
必须遵守：
1. 生成内容优先依据给定教材片段，不能把没有依据的推断伪装成教材事实。
2. 若资料不足，明确写出"当前教材片段不足以确认"，并给出需要补充检索的知识点。
3. 不生成违法违规、隐私侵犯、考试作弊、攻击破坏类内容。
4. 涉及学术概念时保持中立、准确、可核查。
5. 重要结论尽量标注资料编号，例如 [资料1]。
"""


RISK_KEYWORDS = {
    "攻击": "网络攻击相关请求需要限定在防御性学习场景。",
    "绕过": "绕过限制类请求需要确认是否属于合法教学场景。",
    "作弊": "考试作弊类内容不可生成。",
    "代考": "考试作弊类内容不可生成。",
    "黑客": "黑客技术类内容不可生成。",
    "破解": "软件破解类内容不可生成。",
    "病毒": "病毒编写类内容不可生成。",
}


@dataclass(frozen=True)
class SafetyCheck:
    allowed: bool
    warnings: list[str]


def check_user_request(text: str) -> SafetyCheck:
    warnings: list[str] = []
    for keyword, warning in RISK_KEYWORDS.items():
        if keyword in text:
            warnings.append(warning)
    blocked = any("不可生成" in warning for warning in warnings)
    return SafetyCheck(allowed=not blocked, warnings=warnings)
