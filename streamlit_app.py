from __future__ import annotations

import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
import streamlit as st

from prlmad.agents import (
    DEFAULT_RESOURCE_TYPES,
    RESOURCE_AGENT_PROMPTS,
    RESOURCE_TYPE_NAMES,
    AgentOrchestrator,
    GenerationRequest,
    LearnerInput,
)
from prlmad.config import get_settings
from prlmad.knowledge_base import KnowledgeBase
from prlmad.safety import SYSTEM_SAFETY_POLICY, check_user_request
from prlmad.spark_client import SparkAPIError, SparkClient
from prlmad.training import discover_knowledge_files, train_from_folder

# ==================== Page Config ====================
st.set_page_config(
    page_title="PRLMAD · 个性化学习多智能体系统",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ==================== CSS ====================
st.markdown(
    """
<style>
    [data-testid="stSidebar"]         { display: none !important; }
    [data-testid="stSidebarCollapsedControl"] { display: none !important; }
    .main .block-container            { padding: 1rem 2rem 2rem 2rem; max-width: 1400px; }
    footer                            { display: none !important; }

    .stButton > button {
        border-radius: 10px; font-weight: 600; transition: all 0.2s;
    }

    div[data-testid="stExpander"] {
        border: 1px solid #e2e8f0; border-radius: 12px;
        background: white; box-shadow: 0 1px 3px rgba(0,0,0,.05);
    }

    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
        border: 1px solid #e2e8f0; border-radius: 12px; padding: 12px 16px;
    }

    .pipeline-box {
        border: 2px solid #e2e8f0; border-radius: 14px; padding: 16px 20px;
        background: #fafbfc; margin: 12px 0;
    }
    .profile-radar-card {
        border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px;
        background: white; text-align: center;
    }
</style>
""",
    unsafe_allow_html=True,
)

# ==================== Presets ====================
MAJOR_PRESETS = {
    "计算机科学与技术": "计算机科学与技术",
    "软件工程": "软件工程",
    "人工智能": "人工智能",
    "数据科学与大数据技术": "数据科学与大数据技术",
    "网络工程": "网络工程",
    "信息安全": "信息安全",
    "电子信息工程": "电子信息工程",
    "通信工程": "通信工程",
    "物联网工程": "物联网工程",
    "数学与应用数学": "数学与应用数学",
}

GOAL_PRESETS = {
    "进程同步与死锁": "理解进程同步机制、死锁预防与避免策略",
    "内存管理": "掌握内存分页、分段和虚拟内存管理原理",
    "文件系统原理": "理解文件系统结构、目录实现与磁盘调度",
    "调度算法": "掌握进程调度算法与实时调度策略",
    "并发编程": "理解并发编程模型、信号量与互斥锁",
    "I/O系统": "掌握I/O系统原理与磁盘管理",
    "全面学习": "系统学习操作系统全部核心概念与机制",
    "期末考试复习": "操作系统期末全面复习，重点突破薄弱环节",
}

KNOWLEDGE_PRESETS = {
    "学过编程概念易混淆": "学过 C/Python，操作系统概念容易混淆",
    "有编程基础无OS经验": "有编程基础但缺乏操作系统学习经验",
    "了解基础需深入": "了解基本概念但细节模糊，需要深入学习",
    "有一定基础想提升": "有一定操作系统基础，希望深入学习进阶内容",
    "零基础初学": "零基础，从头开始系统学习操作系统",
    "考研复习": "正在准备考研，需要系统梳理操作系统知识体系",
}

HISTORY_PRESETS = {
    "已完成进程管理": "已完成进程与线程章节，掌握进程状态转换与调度基础",
    "已完成内存管理": "已完成内存管理章节，了解分页与分段基本概念",
    "正在学习文件系统": "正在学习文件系统，对inode和目录结构尚不熟悉",
    "刚开课初学": "刚开课不久，完成导论章节学习",
    "自学中进度灵活": "通过线上课程自学，学习节奏较灵活",
    "学过但遗忘较多": "曾学习过操作系统但知识点遗忘较多，需要重新梳理",
}

PREFERENCES_PRESETS = {
    "图解+例题+代码": "图解说明、例题练习、代码实验",
    "视频讲解": "视频讲解、动画演示、可视化理解",
    "结构化文档": "结构化文档、教材总结、知识归纳",
    "思维导图+PPT": "思维导图、PPT课件、概念图",
    "动手实验": "动手实验、项目实操、代码驱动",
    "综合多模态": "图文+视频+文档+实操综合学习",
}

WEAK_POINTS_PRESETS = {
    "信号量·死锁·页面置换": "信号量机制、死锁检测与避免、页面置换算法",
    "进程调度": "进程调度算法比较与实时调度策略",
    "内存分页与分段": "内存分页机制、分段机制与虚拟内存实现",
    "文件系统实现": "文件系统结构、目录实现与磁盘空间管理",
    "I/O与磁盘": "I/O系统架构、磁盘调度算法与RAID",
    "并发同步": "并发编程模型、同步机制设计与互斥实现",
    "整体框架": "操作系统整体架构及各模块间关联关系",
}

TIME_PRESETS = {
    "每天30分钟": "每天 30 分钟",
    "每天45分钟": "每天 45 分钟",
    "每天1小时": "每天 1 小时",
    "每天2小时": "每天 2 小时",
    "每周3-5小时": "每周 3-5 小时",
    "弹性安排": "学习时间不固定，弹性安排",
}

PROFILE_DIMENSIONS = [
    ("知识基础", "knowledge"),
    ("学习目标", "goal"),
    ("认知风格", "cognitive"),
    ("资源偏好", "preference"),
    ("薄弱环节", "weakness"),
    ("时间投入", "time"),
]

# ==================== Session State ====================
_DEFAULTS = {
    "profile": {
        "major": "计算机科学与技术",
        "goal": "理解进程同步、死锁和内存管理",
        "knowledge_level": "学过 C/Python，操作系统概念容易混淆",
        "learning_history": "",
        "preferences": "图解、例题、代码实验",
        "weak_points": "信号量、死锁检测、页面置换算法",
        "available_time": "每天 45 分钟",
    },
    "profile_complete": False,
    "current_page": "profile",
    "course": "操作系统",
    "resource_types": list(DEFAULT_RESOURCE_TYPES),
    "top_k": 6,
    "generate_result": None,
    "generate_error": None,
    "tutor_messages": [],
    "conv_stage": 0,
    "conv_messages": [],
    "conv_active": False,
    "train_results": None,
    "search_results": None,
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ==================== Cached ====================
@st.cache_resource
def get_kb(db_path: str) -> KnowledgeBase:
    return KnowledgeBase(db_path)


settings = get_settings()
kb = get_kb(str(settings.db_path))


def _spark_client() -> SparkClient:
    return SparkClient(
        api_key=settings.spark_api_key,
        base_url=settings.spark_base_url,
        model=settings.spark_model,
        user_id=settings.spark_user_id,
        enable_web_search=settings.spark_enable_web_search,
    )


def _learner_input() -> LearnerInput:
    p = st.session_state.profile
    return LearnerInput(
        major=p["major"],
        goal=p["goal"],
        knowledge_level=p["knowledge_level"],
        learning_history=p["learning_history"],
        preferences=p["preferences"],
        weak_points=p["weak_points"],
        available_time=p["available_time"],
    )


# ==================== Preset Helpers ====================
def _ensure(key: str, default: object) -> None:
    if key not in st.session_state:
        st.session_state[key] = default


def preset_selectbox(label: str, presets: dict[str, str], default_key: str, prefix: str, help: str = "") -> str:
    ck = f"{prefix}_custom"
    pk = f"{prefix}_preset"
    _ensure(pk, default_key)
    _ensure(ck, "")

    opts = list(presets.keys()) + ["✍️ 自定义输入..."]
    cur = st.session_state[pk]
    idx = len(opts) - 1 if cur == "__custom__" else list(presets.keys()).index(cur) if cur in presets else 0

    sel = st.selectbox(label, opts, index=idx, key=f"{prefix}_sel", help=help)

    if sel == "✍️ 自定义输入...":
        st.session_state[pk] = "__custom__"
        if not st.session_state[ck] and cur not in ("__custom__", ""):
            st.session_state[ck] = presets.get(cur, "")
        return st.text_input("输入内容", key=ck, label_visibility="collapsed", placeholder="请输入...")
    st.session_state[pk] = sel
    return presets[sel]


def preset_text_area(label: str, presets: dict[str, str], default_key: str, prefix: str, help: str = "") -> str:
    ck = f"{prefix}_custom"
    pk = f"{prefix}_preset"
    _ensure(pk, default_key)
    _ensure(ck, "")

    opts = list(presets.keys()) + ["✍️ 自定义输入..."]
    cur = st.session_state[pk]
    idx = len(opts) - 1 if cur == "__custom__" else list(presets.keys()).index(cur) if cur in presets else 0

    sel = st.selectbox(label, opts, index=idx, key=f"{prefix}_sel", help=help)

    if sel == "✍️ 自定义输入...":
        st.session_state[pk] = "__custom__"
        if not st.session_state[ck] and cur not in ("__custom__", ""):
            st.session_state[ck] = presets.get(cur, "")
        return st.text_area("输入内容", key=ck, label_visibility="collapsed", placeholder="请输入...", height=80)
    st.session_state[pk] = sel
    return presets[sel]


def profile_to_lines() -> str:
    p = st.session_state.profile
    return "\n".join(
        f"专业：{p['major'] or '未提供'}\n"
        f"学习目标：{p['goal'] or '未提供'}\n"
        f"知识基础：{p['knowledge_level'] or '未提供'}\n"
        f"学习历史：{p['learning_history'] or '未提供'}\n"
        f"资源偏好：{p['preferences'] or '未提供'}\n"
        f"薄弱点：{p['weak_points'] or '未提供'}\n"
        f"可用时间：{p['available_time'] or '未提供'}"
    )


# ==================== Pipeline Viz ====================
PIPELINE_STAGES = ["画像分析", "知识检索", "资源生成", "路径规划", "效果评估"]


def render_pipeline(completed_steps: list[str]) -> None:
    """Render a visual pipeline diagram showing agent collaboration flow."""
    done_set = set()
    for s in completed_steps:
        if "画像" in s:
            done_set.add("画像分析")
        if "检索" in s:
            done_set.add("知识检索")
        if "完成生成" in s or "生成异常" in s:
            done_set.add("资源生成")
        if "路径" in s:
            done_set.add("路径规划")
        if "评估" in s:
            done_set.add("效果评估")

    cols = st.columns(len(PIPELINE_STAGES))
    for i, stage in enumerate(PIPELINE_STAGES):
        with cols[i]:
            done = stage in done_set
            icon = "✅" if done else "⬜"
            color = "#22c55e" if done else "#94a3b8"
            st.markdown(
                f"<div style='text-align:center;padding:10px;border-radius:10px;"
                f"background:{'#f0fdf4' if done else '#f8fafc'};"
                f"border:2px solid {color};font-size:14px;'>{icon}<br><b>{stage}</b></div>",
                unsafe_allow_html=True,
            )
            if i < len(PIPELINE_STAGES) - 1:
                st.markdown(
                    "<div style='text-align:center;color:#94a3b8;font-size:18px;'>→</div>",
                    unsafe_allow_html=True,
                )


# ==================== Profile Page ====================
def profile_radar_html(dimensions: list[tuple[str, str]], values: list[int]) -> str:
    """Generate a simple HTML/CSS radar-style profile card."""
    total = max(values) or 1
    bars = "".join(
        f"<div style='margin:6px 0;'><div style='display:flex;justify-content:space-between;"
        f"font-size:13px;margin-bottom:2px;'><span>{name}</span><span style='color:#64748b'>{val}/{total}</span></div>"
        f"<div style='background:#e2e8f0;border-radius:6px;height:10px;'>"
        f"<div style='background:linear-gradient(90deg,#6366f1,#8b5cf6);height:10px;border-radius:6px;"
        f"width:{val/max(total,1)*100}%;'></div></div></div>"
        for (name, _), val in zip(dimensions, values)
    )
    return f"<div style='padding:8px;'>{bars}</div>"


def render_profile_page() -> None:
    st.markdown("## 👤 学习画像构建")
    st.caption("构建你的个性化学习画像，系统将基于此为你生成定制化学习资源。")

    tab_q, tab_c = st.tabs(["⚡ 快速填表", "💬 对话式构建"])

    with tab_q:
        c1, c2 = st.columns(2)
        with c1:
            major = preset_selectbox("专业", MAJOR_PRESETS, "计算机科学与技术", "major")
            goal = preset_text_area("学习目标", GOAL_PRESETS, "进程同步与死锁", "goal")
            level = preset_text_area("知识基础", KNOWLEDGE_PRESETS, "学过编程概念易混淆", "level")
            history = preset_text_area("学习历史", HISTORY_PRESETS, "自学中进度灵活", "history")
        with c2:
            preferences = preset_selectbox("资源偏好", PREFERENCES_PRESETS, "图解+例题+代码", "prefs")
            weak_points = preset_selectbox("薄弱点", WEAK_POINTS_PRESETS, "信号量·死锁·页面置换", "weak")
            available_time = preset_selectbox("可用时间", TIME_PRESETS, "每天45分钟", "time")

        if st.button("💾 保存画像并开始", type="primary", use_container_width=True):
            st.session_state.profile = {
                "major": major,
                "goal": goal,
                "knowledge_level": level,
                "learning_history": history,
                "preferences": preferences,
                "weak_points": weak_points,
                "available_time": available_time,
            }
            st.session_state.profile_complete = True
            st.success("画像已保存！点击顶部导航栏「资源生成」开始生成。")
            st.balloons()

        with st.expander("📋 当前画像预览", expanded=True):
            _show_profile_preview()

    with tab_c:
        render_conversational_profile()


def _show_profile_preview() -> None:
    p = st.session_state.profile
    filled = sum(1 for v in p.values() if v)
    st.progress(filled / max(len(p), 1), text=f"画像完整度 {filled}/{len(p)}")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("专业", p["major"] or "未填写")
        st.metric("知识基础", (p["knowledge_level"] or "未填写")[:20] + ("..." if len(p["knowledge_level"] or "") > 20 else ""))
    with c2:
        st.metric("学习目标", (p["goal"] or "未填写")[:25] + ("..." if len(p["goal"] or "") > 25 else ""))
        st.metric("薄弱点", (p["weak_points"] or "未填写")[:20] + ("..." if len(p["weak_points"] or "") > 20 else ""))
    with c3:
        st.metric("资源偏好", (p["preferences"] or "未填写")[:18] + ("..." if len(p["preferences"] or "") > 18 else ""))
        st.metric("可用时间", p["available_time"] or "未填写")

    with st.expander("🔍 完整画像详情", expanded=False):
        st.markdown(f"""
| 维度 | 内容 |
|------|------|
| 专业 | {p['major'] or '未填写'} |
| 学习目标 | {p['goal'] or '未填写'} |
| 知识基础 | {p['knowledge_level'] or '未填写'} |
| 学习历史 | {p['learning_history'] or '未填写'} |
| 资源偏好 | {p['preferences'] or '未填写'} |
| 薄弱点 | {p['weak_points'] or '未填写'} |
| 可用时间 | {p['available_time'] or '未填写'} |
""")


# ==================== Conversational Profile Builder ====================
CONV_QUESTIONS = [
    ("major", "你好！我是你的智能学习助手 🎓\n\n首先，请告诉我你的**专业**是什么？"),
    ("goal", "明白了。你学习《{course}》课程的**主要目标**是什么？\n\n比如：想重点掌握哪些知识点？是为了考试还是项目实践？"),
    ("knowledge_level", "了解了。你目前的**编程基础和操作系统知识**掌握程度如何？\n\n之前学过哪些相关课程？"),
    ("learning_history", "很好。请简单描述一下你的**学习历史**：之前学过操作系统的哪些章节？最近的学习进度如何？"),
    ("preferences", "谢谢！你偏好什么类型的**学习资源**？\n\n比如：图解说明、视频讲解、代码实验、结构化文档、PPT课件？"),
    ("weak_points", "在学习操作系统时，哪些**知识点你感觉比较困难**或容易出错？"),
    ("available_time", "最后，你每天大概能投入**多少时间**来学习？"),
]

CONV_COMPLETION = (
    "太棒了！我已经从对话中提取了你的学习画像。\n\n"
    "你可以切换到「快速填表」标签页查看和修改，或者直接前往「资源生成」页面开始生成个性化学习资源。"
)


def render_conversational_profile() -> None:
    msgs = st.session_state.conv_messages
    stage = st.session_state.conv_stage
    active = st.session_state.conv_active
    profile = st.session_state.profile

    # Init
    if not msgs and not active:
        st.session_state.conv_messages = [
            {"role": "assistant", "content": CONV_QUESTIONS[0][1].format(course=st.session_state.course)}
        ]
        st.session_state.conv_stage = 0
        st.session_state.conv_active = True
        st.rerun()

    # Display conversation
    for msg in msgs:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if stage >= len(CONV_QUESTIONS):
        st.success("对话完成！画像已自动提取。")
        with st.expander("📋 提取的画像", expanded=True):
            _show_profile_preview()
        if st.button("🔄 重新对话", use_container_width=True):
            st.session_state.conv_messages = []
            st.session_state.conv_stage = 0
            st.session_state.conv_active = True
            st.rerun()
        return

    if user_input := st.chat_input("输入你的回答..."):
        msgs.append({"role": "user", "content": user_input})
        field, _ = CONV_QUESTIONS[stage]
        profile[field] = user_input
        st.session_state.profile = profile
        st.session_state.profile_complete = True

        stage += 1
        st.session_state.conv_stage = stage

        if stage < len(CONV_QUESTIONS):
            _, question = CONV_QUESTIONS[stage]
            msgs.append({"role": "assistant", "content": question.format(course=st.session_state.course)})
        else:
            msgs.append({"role": "assistant", "content": CONV_COMPLETION})
            st.session_state.conv_active = False
        st.rerun()


# ==================== Generate Page ====================
def render_generate_page() -> None:
    st.markdown("## 📚 多智能体协同资源生成")
    st.caption("多个专业智能体分工协作，为你生成个性化、多模态的学习资源包。")

    if not st.session_state.profile_complete and not any(
        st.session_state.profile.get(k) for k in ["goal", "major"]
    ):
        st.warning("👈 请先前往「学习画像」页面填写你的学习信息，再回来生成资源。")
        if st.button("前往画像页面", use_container_width=True):
            st.session_state.current_page = "profile"
            st.rerun()
        return

    with st.expander("⚙️ 生成设置", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            course = st.text_input("课程", value=st.session_state.course)
            st.session_state.course = course
        with c2:
            top_k = st.slider("教材片段召回数", 3, 12, st.session_state.top_k)
            st.session_state.top_k = top_k
        with c3:
            selected = st.multiselect(
                "资源类型（≥5种）",
                options=list(RESOURCE_TYPE_NAMES.keys()),
                default=st.session_state.resource_types,
                format_func=lambda t: RESOURCE_TYPE_NAMES[t],
            )
            st.session_state.resource_types = selected

        if len(selected) < 5:
            st.caption("⚠️ 当前不足5种，赛题要求至少5类资源。")

        st.caption(
            "已选资源："
            + " · ".join(RESOURCE_TYPE_NAMES[t] for t in selected if t in RESOURCE_TYPE_NAMES)
        )

    if st.button("🚀 启动多智能体生成", type="primary", use_container_width=True):
        if len(selected) < 5:
            st.error("请至少选择 5 种资源类型。")
            return
        _run_generation(course, selected, top_k)

    if st.session_state.generate_result:
        result = st.session_state.generate_result
        st.divider()
        st.subheader("🤝 智能体协作流水线")
        render_pipeline(result.steps)

        st.divider()
        st.subheader("📋 协作过程")
        for s in result.steps:
            icon = "✅" if "完成" in s else "⚠️" if "异常" in s else "➡️"
            st.write(f"{icon} {s}")

        st.divider()
        st.subheader("📦 生成结果")
        st.markdown(result.to_markdown())
        st.download_button(
            "📥 下载 Markdown 资源包",
            data=result.to_markdown(),
            file_name="personalized_learning_resources.md",
            mime="text/markdown",
        )

    if st.session_state.generate_error:
        st.error(st.session_state.generate_error)


def _run_generation(course: str, selected: list[str], top_k: int) -> None:
    client = _spark_client()
    request = GenerationRequest(
        course=course,
        learner=_learner_input(),
        resource_types=selected,
        top_k=top_k,
    )
    try:
        status = st.status("⏳ 多智能体协作中...", expanded=True)
        status.write("📋 画像智能体分析学习者输入...")
        status.write("🔍 检索智能体召回教材片段...")

        orchestrator = AgentOrchestrator(client, kb)
        result = orchestrator.generate(request)

        for s in result.steps:
            status.write(f"✅ {s}")
        status.update(label="✅ 生成完成！", state="complete", expanded=False)

        st.session_state.generate_result = result
        st.session_state.generate_error = None
    except SparkAPIError as exc:
        st.session_state.generate_error = f"Spark API 调用失败: {exc}"
        st.session_state.generate_result = None
    except ValueError as exc:
        st.session_state.generate_error = str(exc)
        st.session_state.generate_result = None
    except Exception as exc:
        st.session_state.generate_error = f"生成异常: {exc}"
        st.session_state.generate_result = None


# ==================== Path Page ====================
def render_path_page() -> None:
    st.markdown("## 🗺️ 个性化学习路径")
    st.caption("基于你的画像和生成资源，智能规划最优学习顺序与每日任务。")

    result = st.session_state.generate_result
    if not result:
        st.info("请先在「资源生成」页面生成学习资源包，系统将自动为你规划学习路径。")
        if st.button("前往资源生成页面", use_container_width=True):
            st.session_state.current_page = "generate"
            st.rerun()
        return

    st.markdown("### 📅 学习路径规划")
    st.markdown(result.path_plan)

    if result.citations:
        with st.expander("📖 引用教材片段", expanded=False):
            for c in result.citations:
                st.write(f"- {c}")


# ==================== Tutor Page ====================
def render_tutor_page() -> None:
    st.markdown("## 💡 智能辅导")
    st.caption("基于教材知识库的 RAG 问答，为你提供针对性学习辅导。")

    if not st.session_state.profile_complete:
        st.info("建议先完成「学习画像」构建，辅导效果更佳。")

    tutor_msgs = st.session_state.tutor_messages

    for msg in tutor_msgs:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if user_q := st.chat_input("输入你的问题，如「什么是死锁的必要条件？」"):
        tutor_msgs.append({"role": "user", "content": user_q})

        snippets = kb.search(user_q, course=st.session_state.course, top_k=5)
        ctx = kb.format_context(snippets) if snippets else "当前知识库无相关教材片段。"

        client = _spark_client()
        sys_msg = (
            f"{SYSTEM_SAFETY_POLICY}\n"
            "你是智能辅导智能体。根据教材知识库回答学生问题，提供清晰的解题思路、"
            "关键知识点解释、易错提醒和进一步学习建议。用 Markdown 格式回答。"
        )
        user_msg = (
            f"课程：{st.session_state.course}\n"
            f"学生画像：\n{profile_to_lines()}\n\n"
            f"教材知识库片段：\n{ctx}\n\n"
            f"学生问题：{user_q}\n\n"
            f"请基于教材片段给出辅导回答。若资料不足请明确说明。"
        )
        msgs = [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_msg},
        ]
        try:
            answer = client.chat(msgs)
        except SparkAPIError:
            answer = "辅导服务暂时不可用，请稍后重试。"
        except Exception as exc:
            answer = f"辅导请求异常: {exc}"

        tutor_msgs.append({"role": "assistant", "content": answer})
        st.rerun()


# ==================== Assessment Page ====================
def render_assessment_page() -> None:
    st.markdown("## 📊 学习效果评估")
    st.caption("多维度评估学习进展，动态调整后续学习策略。")

    result = st.session_state.generate_result
    if not result:
        st.info("请先在「资源生成」页面生成学习资源包，系统将为你设计评估方案。")
        if st.button("前往资源生成页面", use_container_width=True):
            st.session_state.current_page = "generate"
            st.rerun()
        return

    p = st.session_state.profile
    filled_count = sum(1 for v in p.values() if v)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("画像完整度", f"{filled_count}/7", f"{filled_count/7*100:.0f}%")
    with c2:
        res_count = len(result.resources)
        st.metric("生成资源数", f"{res_count} 类", f"+{res_count}")
    with c3:
        cit_count = len(result.citations or [])
        st.metric("引用片段", f"{cit_count} 条")
    with c4:
        step_count = len(result.steps)
        st.metric("智能体协同", f"{step_count} 步")

    st.divider()
    st.markdown("### 📝 评估方案")
    st.markdown(result.assessment)

    st.divider()
    st.markdown("### 📈 画像维度雷达")
    dims = PROFILE_DIMENSIONS
    values = [max(1, min(10, len(p.get("goal", "")) // 2)) for _ in dims]
    values[0] = min(10, max(1, len(p.get("knowledge_level", "")) // 3))
    values[1] = min(10, max(1, len(p.get("goal", "")) // 3))
    values[2] = 5
    values[3] = min(10, max(1, len(p.get("preferences", "")) // 2))
    values[4] = min(10, max(1, len(p.get("weak_points", "")) // 2))
    values[5] = min(10, max(1, len(p.get("available_time", "")) // 3))
    st.markdown(profile_radar_html(dims, values), unsafe_allow_html=True)


# ==================== KB Page ====================
def render_kb_page() -> None:
    st.markdown("## ⚙️ 知识库管理")
    st.caption("管理本地教材知识库：导入、检索、查看状态和运行配置。")

    tab_import, tab_search, tab_status, tab_config = st.tabs(
        ["📥 导入训练", "🔍 教材检索", "📊 知识库状态", "🔧 运行配置"]
    )

    with tab_import:
        c1, c2 = st.columns(2)
        with c1:
            course_input = st.text_input("课程名称", value=st.session_state.course, key="kb_course")
            knowledge_dir = st.text_input("knowledge 文件夹", value=str(settings.knowledge_dir))
        with c2:
            ocr_options = ["auto", "off", "on"]
            default_ocr = ocr_options.index(settings.ocr_mode) if settings.ocr_mode in ocr_options else 0
            ocr_mode = st.selectbox("PDF 解析模式", ocr_options, index=default_ocr)
            limit_ocr = st.checkbox("仅 OCR 前 N 页调试")
            ocr_max = None
            if limit_ocr:
                ocr_max = st.number_input("OCR 页数", 1, 100, 10, key="ocr_max")

        files = discover_knowledge_files(knowledge_dir)
        st.metric("可导入文件", len(files))
        if files:
            with st.expander("📄 文件列表", expanded=False):
                for fp in files:
                    st.write(f"- {fp.name} ({fp.stat().st_size / 1024 / 1024:.1f} MB)")

        if st.button("🔄 本地导入训练", type="primary", use_container_width=True):
            with st.spinner("正在解析教材并构建检索索引..."):
                summary = train_from_folder(
                    knowledge_base=kb,
                    knowledge_dir=knowledge_dir,
                    course=course_input,
                    replace=True,
                    ocr_mode=ocr_mode,
                    ocr_max_pages=int(ocr_max) if ocr_max else None,
                )
            if summary.success_count:
                st.success(f"训练完成：成功 {summary.success_count}，失败 {summary.failed_count}")
            else:
                st.error("无文件成功入库。")
            st.session_state.train_results = [r.__dict__ for r in summary.results]

        if st.session_state.train_results:
            st.dataframe(pd.DataFrame(st.session_state.train_results), use_container_width=True)

    with tab_search:
        c1, c2 = st.columns([3, 1])
        with c1:
            query = st.text_input("检索问题", value="死锁的必要条件", key="kb_query")
        with c2:
            s_topk = st.slider("返回条数", 1, 10, 5, key="kb_stopk")
            if st.button("检索", use_container_width=True):
                results = kb.search(query, course=course_input, top_k=s_topk)
                if not results:
                    st.warning("未检索到相关片段。")
                for item in results:
                    with st.expander(
                        f"《{item.title}》{item.page_label} · score={item.score:.2f}", expanded=True
                    ):
                        st.write(item.text)

    with tab_status:
        docs = kb.list_documents()
        if not docs:
            st.info("暂无已入库文档。请在「导入训练」中添加。")
        else:
            st.dataframe(
                pd.DataFrame([
                    {"课程": d.course, "标题": d.title, "片段数": d.chunk_count, "来源": d.source_path}
                    for d in docs
                ]),
                use_container_width=True,
                hide_index=True,
            )

    with tab_config:
        st.code(
            f"""数据库路径   : {settings.db_path}
知识库目录   : {settings.knowledge_dir}
Spark 接口   : {settings.spark_base_url}
Spark 模型   : {settings.spark_model}
Web Search   : {settings.spark_enable_web_search}
OCR 模式     : {settings.ocr_mode}
API Key      : {"已配置" if settings.spark_api_key else "未配置 ⚠️"}""",
            language="text",
        )
        st.markdown("运行前请确保 `.env` 文件已配置 `SPARK_API_KEY`。")


# ==================== Top Navigation ====================
PAGES = {
    "👤 学习画像": "profile",
    "📚 资源生成": "generate",
    "🗺️ 学习路径": "path",
    "💡 智能辅导": "tutor",
    "📊 学习评估": "assessment",
    "⚙️ 知识库": "kb",
}


def render_nav() -> None:
    cols = st.columns(len(PAGES))
    current = st.session_state.current_page
    for i, (label, page_id) in enumerate(PAGES.items()):
        with cols[i]:
            is_active = current == page_id
            btn_type = "primary" if is_active else "secondary"
            if st.button(label, key=f"nav_{page_id}", use_container_width=True, type=btn_type):
                st.session_state.current_page = page_id
                st.rerun()


def _nav_underline() -> None:
    """Optional: render an underline indicator beneath the active nav item."""
    pass


# ==================== Main ====================
st.markdown(
    "<h1 style='text-align:center;margin-bottom:0;'>📚 PRLMAD</h1>"
    "<p style='text-align:center;color:#64748b;margin-top:0;font-size:15px;'>"
    "个性化学习资源多智能体系统 · 中国软件杯 A3 原型</p>",
    unsafe_allow_html=True,
)

render_nav()
st.divider()

page_renderers = {
    "profile": render_profile_page,
    "generate": render_generate_page,
    "path": render_path_page,
    "tutor": render_tutor_page,
    "assessment": render_assessment_page,
    "kb": render_kb_page,
}

renderer = page_renderers.get(st.session_state.current_page, render_profile_page)
renderer()
