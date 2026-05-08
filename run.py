from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.prlmad.config import get_settings
from src.prlmad.knowledge_base import KnowledgeBase
from src.prlmad.spark_client import SparkAPIError, SparkClient
from src.prlmad.training import train_from_folder


def _progress_bar(current: int, total: int, width: int = 28) -> str:
    if total <= 0:
        return "[" + "." * width + "]"
    done = min(width, max(0, int(width * current / total)))
    return "[" + "#" * done + "." * (width - done) + "]"


def _make_progress_printer():
    state = {"inline": False}

    def newline_if_needed() -> None:
        if state["inline"]:
            print()
            state["inline"] = False

    def progress(stage: str, detail: dict) -> None:
        if stage == "flush":
            newline_if_needed()
            return

        progress_labels = {
            "pdf_text_page": ("PDF文本提取", "page", "total"),
            "pdf_ocr_page": ("OCR识别", "page", "total"),
            "text_page": ("文本读取", "page", "total"),
            "db_index_chunk": ("知识切片入库", "chunk", "total"),
        }
        if stage in progress_labels:
            label, current_key, total_key = progress_labels[stage]
            current = int(detail.get(current_key) or 0)
            total = int(detail.get(total_key) or 0)
            percent = int(current * 100 / total) if total else 0
            extra = ""
            if stage.startswith("pdf_"):
                extra = f" 已提取页:{detail.get('extracted_pages', 0)}"
            if stage == "db_index_chunk":
                extra = f" 页码:{detail.get('page_start')}-{detail.get('page_end')}"
            sys.stdout.write(
                f"\r{label:<12} {_progress_bar(current, total)} {current}/{total} {percent:3d}%{extra}   "
            )
            sys.stdout.flush()
            state["inline"] = current < total
            if current >= total:
                print()
            return

        newline_if_needed()
        if stage == "train_discovered":
            print(f"发现教材文件: {detail.get('total_files', 0)} 个")
        elif stage == "file_start":
            print(
                f"开始导入: {detail.get('title')} ({detail.get('index')}/{detail.get('total_files')}), "
                f"模式={detail.get('mode')}, 起始页={detail.get('start_page', 1)}, "
                f"目标页数={detail.get('total_pages') or '未知'}"
            )
        elif stage == "file_skipped":
            print(
                f"跳过: {detail.get('title')} 已完整导入 "
                f"({detail.get('existing_pages')}/{detail.get('total_pages')} 页)"
            )
        elif stage == "pdf_text_start":
            print(f"PDF页数: {detail.get('pdf_pages')}，开始文本提取...")
        elif stage == "pdf_text_done":
            print(f"文本提取完成: {detail.get('extracted_pages')}/{detail.get('total')} 页有文本")
        elif stage == "pdf_ocr_start":
            print(f"进入OCR识别: 计划处理 {detail.get('total')} / {detail.get('pdf_pages')} 页")
        elif stage == "pdf_ocr_done":
            print(f"OCR完成: {detail.get('extracted_pages')}/{detail.get('total')} 页有文本")
        elif stage == "file_pages_loaded":
            print(f"页面读取完成: {detail.get('pages')} 页")
        elif stage == "chunk_start":
            print("开始文本切片...")
        elif stage == "chunk_done":
            print(f"文本切片完成: {detail.get('chunks')} 个切片")
        elif stage == "db_replace_start":
            print("替换旧知识库记录...")
        elif stage == "db_replace_done":
            print(f"旧记录删除完成: {detail.get('deleted')} 条文档记录")
        elif stage == "db_index_start":
            print("开始写入SQLite索引...")
        elif stage == "db_index_done":
            print(f"索引写入完成: {detail.get('chunks')} 个切片")
        elif stage == "file_done":
            print(f"导入完成: {detail.get('title')}，页数 {detail.get('pages')}，切片 {detail.get('chunks')}")
        elif stage == "file_error":
            print(f"导入失败: {detail.get('title')}，{detail.get('error')}")
        elif stage == "train_done":
            print(f"训练结束: 成功 {detail.get('success_count')}，失败 {detail.get('failed_count')}")

    return progress


def _pdf_page_count(path: Path) -> int | None:
    if path.suffix.lower() != ".pdf" or not path.exists():
        return None
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(path)).pages)
    except Exception:
        return None


def cmd_train(args: argparse.Namespace) -> None:
    settings = get_settings()
    kb = KnowledgeBase(settings.db_path)
    progress = None if args.quiet else _make_progress_printer()
    summary = train_from_folder(
        kb,
        args.knowledge_dir or str(settings.knowledge_dir),
        course=args.course,
        replace=args.force_rebuild,
        ocr_mode=args.ocr_mode,
        ocr_max_pages=args.max_pages,
        on_progress=progress,
    )
    if progress:
        progress("flush", {})
    print(f"Course: {summary.course}")
    print(f"Files: {summary.total_files}, Success: {summary.success_count}, Failed: {summary.failed_count}")
    for r in summary.results:
        status = "OK" if r.ok else "FAIL"
        print(f"  [{status}] {r.title}: pages={r.page_count}, chunks={r.chunk_count}")
        if not r.ok:
            print(f"         Error: {r.message}")


def cmd_status(args: argparse.Namespace) -> None:
    settings = get_settings()
    kb = KnowledgeBase(settings.db_path)
    docs = kb.list_documents()
    print(f"Documents: {len(docs)}, Total chunks: {kb.get_chunk_count()}")
    for d in docs:
        chunks = kb.get_document_chunks(d.id)
        min_page = min((c["page_start"] for c in chunks), default=0)
        max_page = max((c["page_end"] for c in chunks), default=0)
        chars = sum(len(c["text"]) for c in chunks)
        source_path = Path(d.source_path)
        if not source_path.is_absolute():
            source_path = settings.base_dir / source_path
        total_pages = _pdf_page_count(source_path)
        page_info = f"pages={min_page}-{max_page}"
        if total_pages:
            complete = "complete" if max_page >= total_pages else "partial"
            page_info = f"{page_info}/{total_pages} ({complete})"
        print(
            f"  - {d.title} ({d.course}): {d.chunk_count} chunks, {page_info}, chars={chars}, {d.created_at}"
        )


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn
    uvicorn.run(
        "server.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


def cmd_check_spark(args: argparse.Namespace) -> None:
    settings = get_settings()
    client = SparkClient(
        api_key=settings.spark_api_key,
        base_url=settings.spark_base_url,
        model=settings.spark_model,
        user_id=settings.spark_user_id,
        enable_web_search=settings.spark_enable_web_search,
        offline_fallback=False,
        trust_env_proxy=settings.spark_trust_env_proxy,
        timeout=args.timeout,
    )
    messages = [
        {"role": "user", "content": "请只回复一句话：Spark-X2-Flash 连接成功。"},
    ]
    print("Checking Spark-X2-Flash connection...")
    try:
        answer = client.chat(messages, stream=True).strip()
    except SparkAPIError as exc:
        print("FAILED")
        print(str(exc))
        if "10061" in str(exc):
            print("Hint: 当前环境变量里可能存在不可用的 HTTP_PROXY/HTTPS_PROXY。")
            print("      默认 SPARK_TRUST_ENV_PROXY=false 会让应用直连 Spark；如果你确实需要代理，请确认代理端口正在运行。")
        raise SystemExit(1) from exc
    print("OK")
    print(answer[:500] or "(empty response)")


def main() -> None:
    parser = argparse.ArgumentParser(description="PRLMAD")
    sub = parser.add_subparsers(dest="command")

    train_parser = sub.add_parser("train", help="Train knowledge base from knowledge folder")
    train_parser.add_argument("--knowledge-dir", help="Path to knowledge folder")
    train_parser.add_argument("--course", default="操作系统")
    train_parser.add_argument("--ocr-mode", choices=["off", "auto", "on"], default="auto")
    train_parser.add_argument("--max-pages", type=int, help="Max pages to OCR")
    train_parser.add_argument("--quiet", action="store_true", help="Hide progress output")
    train_parser.add_argument("--force-rebuild", action="store_true", help="Delete existing document records and rebuild from page 1")
    train_parser.set_defaults(func=cmd_train)

    status_parser = sub.add_parser("status", help="Show knowledge base status")
    status_parser.set_defaults(func=cmd_status)

    serve_parser = sub.add_parser("serve", help="Start web server")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    reload_group = serve_parser.add_mutually_exclusive_group()
    reload_group.add_argument("--reload", dest="reload", action="store_true", help="Enable auto reload")
    reload_group.add_argument("--no-reload", dest="reload", action="store_false", help="Disable auto reload")
    serve_parser.set_defaults(reload=True)
    serve_parser.set_defaults(func=cmd_serve)

    check_parser = sub.add_parser("check-spark", help="Check Spark-X2-Flash API connectivity")
    check_parser.add_argument("--timeout", type=int, default=30)
    check_parser.set_defaults(func=cmd_check_spark)

    args = parser.parse_args()
    if args.command:
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
