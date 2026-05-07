from __future__ import annotations

import argparse
import json
from pathlib import Path

from .agents import DEFAULT_RESOURCE_TYPES, AgentOrchestrator, GenerationRequest, LearnerInput
from .config import get_settings
from .knowledge_base import KnowledgeBase
from .pdf_loader import load_document_pages
from .spark_client import SparkClient
from .training import train_from_folder


def _kb() -> KnowledgeBase:
    settings = get_settings()
    return KnowledgeBase(settings.db_path)


def cmd_ingest(args: argparse.Namespace) -> None:
    settings = get_settings()
    pages = load_document_pages(
        args.path,
        ocr_mode=args.ocr_mode or settings.ocr_mode,
        ocr_max_pages=args.ocr_max_pages,
    )
    info = _kb().add_document(
        title=args.title or Path(args.path).stem,
        course=args.course,
        source_path=args.path,
        pages=pages,
        replace=not args.keep_existing,
    )
    print(json.dumps(info.__dict__, ensure_ascii=False, indent=2))


def cmd_search(args: argparse.Namespace) -> None:
    results = _kb().search(args.query, course=args.course, top_k=args.top_k)
    if not results:
        print("未检索到相关片段。")
        return
    for index, result in enumerate(results, start=1):
        preview = result.text[:280].replace("\n", " ")
        print(f"[{index}] {result.title} {result.page_label} score={result.score:.2f}")
        print(preview)
        print()


def cmd_generate(args: argparse.Namespace) -> None:
    settings = get_settings()
    client = SparkClient(
        api_key=settings.spark_api_key,
        base_url=settings.spark_base_url,
        model=settings.spark_model,
        user_id=settings.spark_user_id,
        enable_web_search=settings.spark_enable_web_search,
    )
    request = GenerationRequest(
        course=args.course,
        learner=LearnerInput(
            major=args.major,
            goal=args.goal,
            knowledge_level=args.level,
            learning_history=args.history,
            preferences=args.preferences,
            weak_points=args.weak_points,
            available_time=args.available_time,
        ),
        resource_types=args.types,
        top_k=args.top_k,
    )
    result = AgentOrchestrator(client, _kb()).generate(request)
    print(result.to_markdown())


def cmd_docs(args: argparse.Namespace) -> None:
    docs = _kb().list_documents()
    print(json.dumps([doc.__dict__ for doc in docs], ensure_ascii=False, indent=2))


def cmd_train(args: argparse.Namespace) -> None:
    settings = get_settings()
    summary = train_from_folder(
        knowledge_base=_kb(),
        knowledge_dir=args.knowledge_dir or settings.knowledge_dir,
        course=args.course,
        replace=not args.keep_existing,
        ocr_mode=args.ocr_mode or settings.ocr_mode,
        ocr_max_pages=args.ocr_max_pages,
    )
    print(
        json.dumps(
            {
                "knowledge_dir": summary.knowledge_dir,
                "course": summary.course,
                "total_files": summary.total_files,
                "success_count": summary.success_count,
                "failed_count": summary.failed_count,
                "results": [item.__dict__ for item in summary.results],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PRLMAD command line")
    sub = parser.add_subparsers(required=True)

    ingest = sub.add_parser("ingest", help="Import a PDF/TXT/MD document into the knowledge base")
    ingest.add_argument("--path", required=True)
    ingest.add_argument("--course", default="操作系统")
    ingest.add_argument("--title")
    ingest.add_argument("--keep-existing", action="store_true")
    ingest.add_argument("--ocr-mode", choices=["off", "auto", "on"])
    ingest.add_argument("--ocr-max-pages", type=int)
    ingest.set_defaults(func=cmd_ingest)

    train = sub.add_parser("train", help="Build the local knowledge base from the knowledge folder")
    train.add_argument("--knowledge-dir")
    train.add_argument("--course", default="操作系统")
    train.add_argument("--keep-existing", action="store_true")
    train.add_argument("--ocr-mode", choices=["off", "auto", "on"])
    train.add_argument("--ocr-max-pages", type=int)
    train.set_defaults(func=cmd_train)

    search = sub.add_parser("search", help="Search the local knowledge base")
    search.add_argument("query")
    search.add_argument("--course")
    search.add_argument("--top-k", type=int, default=5)
    search.set_defaults(func=cmd_search)

    generate = sub.add_parser("generate", help="Generate personalized resources through agents")
    generate.add_argument("--course", default="操作系统")
    generate.add_argument("--major", default="")
    generate.add_argument("--goal", required=True)
    generate.add_argument("--level", default="")
    generate.add_argument("--history", default="")
    generate.add_argument("--preferences", default="")
    generate.add_argument("--weak-points", default="")
    generate.add_argument("--available-time", default="")
    generate.add_argument("--types", nargs="+", default=DEFAULT_RESOURCE_TYPES)
    generate.add_argument("--top-k", type=int, default=6)
    generate.set_defaults(func=cmd_generate)

    docs = sub.add_parser("docs", help="List imported documents")
    docs.set_defaults(func=cmd_docs)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
