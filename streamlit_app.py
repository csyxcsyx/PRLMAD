from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
import streamlit as st

from prlmad.agents import (
    DEFAULT_RESOURCE_TYPES,
    RESOURCE_TYPE_NAMES,
    AgentOrchestrator,
    GenerationRequest,
    LearnerInput,
)
from prlmad.config import get_settings
from prlmad.knowledge_base import KnowledgeBase
from prlmad.spark_client import SparkAPIError, SparkClient
from prlmad.training import discover_knowledge_files, train_from_folder


st.set_page_config(
    page_title="PRLMAD 多智能体学习资源生成系统",
    layout="wide",
)


@st.cache_resource
def get_kb(db_path: str) -> KnowledgeBase:
    return KnowledgeBase(db_path)


def settings_and_kb() -> tuple[object, KnowledgeBase]:
    settings = get_settings()
    return settings, get_kb(str(settings.db_path))


def doc_dataframe(kb: KnowledgeBase) -> pd.DataFrame:
    docs = kb.list_documents()
    if not docs:
        return pd.DataFrame(columns=["课程", "标题", "片段数", "来源"])
    return pd.DataFrame(
        [
            {
                "课程": doc.course,
                "标题": doc.title,
                "片段数": doc.chunk_count,
                "来源": doc.source_path,
            }
            for doc in docs
        ]
    )


settings, kb = settings_and_kb()

st.title("基于大模型的个性化资源生成与学习多智能体系统")
st.caption("中国软件杯 A3 原型 · 操作系统课程本地知识库 · Spark-X2-Flash")

with st.sidebar:
    st.header("本地知识库")
    course = st.text_input("课程名称", value="操作系统")
    knowledge_dir = st.text_input("knowledge 文件夹", value=str(settings.knowledge_dir))
    ocr_options = ["auto", "off", "on"]
    default_ocr_index = ocr_options.index(settings.ocr_mode) if settings.ocr_mode in ocr_options else 0
    ocr_mode = st.selectbox(
        "PDF 解析模式",
        options=ocr_options,
        index=default_ocr_index,
        help="扫描版 PDF 建议使用 auto 或 on；纯文本 PDF 可用 off。",
    )
    limit_ocr_pages = st.checkbox("只 OCR 前 N 页调试")
    ocr_max_pages = None
    if limit_ocr_pages:
        ocr_max_pages = st.number_input("OCR 页数", min_value=1, max_value=100, value=10, step=1)

    files = discover_knowledge_files(knowledge_dir)
    st.metric("可导入文件", len(files))
    if files:
        with st.expander("文件列表", expanded=False):
            for path in files:
                st.write(path.name)

    if st.button("本地导入训练", type="primary", use_container_width=True):
        with st.spinner("正在解析教材并构建本地检索索引..."):
            summary = train_from_folder(
                knowledge_base=kb,
                knowledge_dir=knowledge_dir,
                course=course,
                replace=True,
                ocr_mode=ocr_mode,
                ocr_max_pages=int(ocr_max_pages) if ocr_max_pages else None,
            )
        if summary.success_count:
            st.success(f"训练完成：成功 {summary.success_count} 个，失败 {summary.failed_count} 个")
        else:
            st.error("没有文件成功入库，请查看下方错误信息。")
        st.session_state["train_results"] = [item.__dict__ for item in summary.results]

    if "train_results" in st.session_state:
        st.dataframe(pd.DataFrame(st.session_state["train_results"]), use_container_width=True)

tabs = st.tabs(["学习资源生成", "教材检索", "知识库状态", "运行配置"])

with tabs[0]:
    left, right = st.columns([0.92, 1.08], gap="large")
    with left:
        st.subheader("学习者画像输入")
        major = st.text_input("专业", value="计算机科学与技术")
        goal = st.text_area("学习目标", value="理解进程同步、死锁和内存管理", height=88)
        level = st.text_area("知识基础", value="学过 C/Python，操作系统概念容易混淆", height=88)
        history = st.text_area("学习历史", value="", height=76)
        preferences = st.text_input("资源偏好", value="图解、例题、代码实验")
        weak_points = st.text_input("薄弱点", value="信号量、死锁检测、页面置换算法")
        available_time = st.text_input("可用学习时间", value="每天 45 分钟")

        st.subheader("资源类型")
        selected_types = st.multiselect(
            "选择至少 5 种资源以满足赛题要求",
            options=list(RESOURCE_TYPE_NAMES.keys()),
            default=DEFAULT_RESOURCE_TYPES,
            format_func=lambda item: RESOURCE_TYPE_NAMES[item],
        )
        top_k = st.slider("教材片段召回数量", min_value=3, max_value=12, value=6)

        generate = st.button("生成个性化资源包", type="primary", use_container_width=True)

    with right:
        st.subheader("多智能体输出")
        if generate:
            if len(selected_types) < 5:
                st.warning("赛题要求至少生成 5 类个性化资源，建议至少选择 5 项。")
            client = SparkClient(
                api_key=settings.spark_api_key,
                base_url=settings.spark_base_url,
                model=settings.spark_model,
                user_id=settings.spark_user_id,
                enable_web_search=settings.spark_enable_web_search,
            )
            request = GenerationRequest(
                course=course,
                learner=LearnerInput(
                    major=major,
                    goal=goal,
                    knowledge_level=level,
                    learning_history=history,
                    preferences=preferences,
                    weak_points=weak_points,
                    available_time=available_time,
                ),
                resource_types=selected_types,
                top_k=top_k,
            )
            try:
                with st.spinner("画像、检索、资源生成、路径规划和评估智能体正在协作..."):
                    result = AgentOrchestrator(client, kb).generate(request)
                st.success("生成完成")
                st.write("协作进度")
                st.write("\n".join(f"- {step}" for step in result.steps))
                st.markdown(result.to_markdown())
                st.download_button(
                    "下载 Markdown",
                    data=result.to_markdown(),
                    file_name="personalized_learning_resources.md",
                    mime="text/markdown",
                )
            except SparkAPIError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(str(exc))
        else:
            st.info("先在左侧完成学习者信息，再点击生成。")

with tabs[1]:
    st.subheader("教材片段检索")
    query = st.text_input("检索问题", value="死锁的必要条件")
    search_top_k = st.slider("返回条数", min_value=1, max_value=10, value=5, key="search_top_k")
    if st.button("检索教材", use_container_width=False):
        results = kb.search(query, course=course, top_k=search_top_k)
        if not results:
            st.warning("未检索到相关片段。")
        for item in results:
            with st.expander(f"《{item.title}》{item.page_label} · score={item.score:.2f}", expanded=True):
                st.write(item.text)

with tabs[2]:
    st.subheader("已入库文档")
    st.dataframe(doc_dataframe(kb), use_container_width=True, hide_index=True)

with tabs[3]:
    st.subheader("运行配置")
    st.code(
        f"""数据库：{settings.db_path}
知识库目录：{settings.knowledge_dir}
Spark 接口：{settings.spark_base_url}
Spark 模型：{settings.spark_model}
Web Search：{settings.spark_enable_web_search}
API Key：{"已配置" if settings.spark_api_key else "未配置"}""",
        language="text",
    )
    st.markdown(
        "运行前请复制 `.env` 为 `.env`，并填写 `SPARK_API_KEY`。扫描版 PDF 需要安装 OCR 依赖。"
    )
