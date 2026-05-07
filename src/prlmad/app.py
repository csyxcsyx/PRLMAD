from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

from .agents import DEFAULT_RESOURCE_TYPES, AgentOrchestrator, GenerationRequest, LearnerInput
from .config import get_settings
from .knowledge_base import KnowledgeBase
from .pdf_loader import load_document_pages
from .spark_client import SparkAPIError, SparkClient


WEB_DIR = Path(__file__).resolve().parent / "web"
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
}


class PRLMADHandler(BaseHTTPRequestHandler):
    server_version = "PRLMAD/0.1"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send_file(WEB_DIR / "index.html")
            return
        if path == "/api/health":
            self._send_json({"ok": True, "documents": [doc.__dict__ for doc in self._kb().list_documents()]})
            return
        if path.startswith("/assets/"):
            target = (WEB_DIR / path.removeprefix("/assets/")).resolve()
            if WEB_DIR.resolve() not in target.parents:
                self._send_error(HTTPStatus.FORBIDDEN, "Forbidden")
                return
            self._send_file(target)
            return
        self._send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            body = self._read_json()
            if path == "/api/ingest":
                self._handle_ingest(body)
            elif path == "/api/search":
                self._handle_search(body)
            elif path == "/api/generate":
                self._handle_generate(body)
            else:
                self._send_error(HTTPStatus.NOT_FOUND, "Not found")
        except Exception as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))

    def log_message(self, format: str, *args) -> None:
        return

    def _settings(self):
        return get_settings()

    def _kb(self) -> KnowledgeBase:
        return KnowledgeBase(self._settings().db_path)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        return json.loads(raw or "{}")

    def _send_json(self, data: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self._send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        content = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", CONTENT_TYPES.get(path.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"ok": False, "error": message}, status=status)

    def _handle_ingest(self, body: dict) -> None:
        path = body.get("path")
        if not path:
            raise ValueError("path is required")
        course = body.get("course") or "操作系统"
        title = body.get("title") or Path(path).stem
        pages = load_document_pages(path, ocr_mode=body.get("ocr_mode") or "auto")
        info = self._kb().add_document(title=title, course=course, source_path=path, pages=pages)
        self._send_json({"ok": True, "document": info.__dict__})

    def _handle_search(self, body: dict) -> None:
        query = body.get("query") or ""
        course = body.get("course") or None
        top_k = int(body.get("top_k") or 6)
        results = self._kb().search(query, course=course, top_k=top_k)
        self._send_json(
            {
                "ok": True,
                "results": [
                    {
                        "title": item.title,
                        "course": item.course,
                        "page": item.page_label,
                        "text": item.text,
                        "score": item.score,
                    }
                    for item in results
                ],
            }
        )

    def _handle_generate(self, body: dict) -> None:
        settings = self._settings()
        client = SparkClient(
            api_key=settings.spark_api_key,
            base_url=settings.spark_base_url,
            model=settings.spark_model,
            user_id=settings.spark_user_id,
            enable_web_search=settings.spark_enable_web_search,
        )
        learner = body.get("learner") or {}
        resource_types = body.get("resource_types") or DEFAULT_RESOURCE_TYPES
        request = GenerationRequest(
            course=body.get("course") or "操作系统",
            learner=LearnerInput(
                major=learner.get("major", ""),
                goal=learner.get("goal", ""),
                knowledge_level=learner.get("knowledge_level", ""),
                learning_history=learner.get("learning_history", ""),
                preferences=learner.get("preferences", ""),
                weak_points=learner.get("weak_points", ""),
                available_time=learner.get("available_time", ""),
            ),
            resource_types=resource_types,
            top_k=int(body.get("top_k") or 6),
        )
        try:
            result = AgentOrchestrator(client, self._kb()).generate(request)
        except SparkAPIError as exc:
            raise ValueError(str(exc)) from exc
        self._send_json(
            {
                "ok": True,
                "profile": result.profile_markdown,
                "resources": result.resources,
                "path_plan": result.path_plan,
                "assessment": result.assessment,
                "citations": result.citations,
                "steps": result.steps,
                "markdown": result.to_markdown(),
            }
        )


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    httpd = ThreadingHTTPServer((host, port), PRLMADHandler)
    print(f"PRLMAD web server: http://{host}:{port}")
    httpd.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    serve(args.host, args.port)
