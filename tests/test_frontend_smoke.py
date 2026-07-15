from __future__ import annotations

from pathlib import Path
import re
import unittest

from fastapi.testclient import TestClient

from server.main import app


ROOT = Path(__file__).resolve().parents[1]
PAGES = (
    "/",
    "/page/chat",
    "/page/generate",
    "/page/learning-path",
    "/page/tutor",
    "/page/evaluate",
    "/page/os-lab",
    "/page/knowledge",
)
REMOTE_RUNTIME_ASSET = re.compile(
    r'<(?:script|link)[^>]+(?:src|href)=["\']https?://',
    re.IGNORECASE,
)


class FrontendSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_pages_render_with_local_runtime_assets(self) -> None:
        for path in PAGES:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIsNone(REMOTE_RUNTIME_ASSET.search(response.text))
                self.assertNotIn("x-html=", response.text)
                self.assertIn('/static/css/app.css', response.text)
                self.assertIn('/static/js/ai-renderer.js', response.text)
                self.assertIn('KnowStack', response.text)
                self.assertIn('/static/images/knowstack.png', response.text)

    def test_required_static_assets_are_served(self) -> None:
        assets = (
            "/static/css/app.css",
            "/static/js/app.js",
            "/static/js/ai-renderer.js",
            "/static/images/knowstack.png",
            "/static/vendor/alpine.min.js",
            "/static/vendor/marked.umd.js",
            "/static/vendor/purify.min.js",
            "/static/vendor/echarts.min.js",
            "/static/vendor/mermaid.min.js",
        )
        for path in assets:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertGreater(len(response.content), 100)

    def test_os_lab_events_are_recorded_for_session(self) -> None:
        session_resp = self.client.post("/api/session", json={"name": "OS Lab Smoke"})
        self.assertEqual(session_resp.status_code, 200)
        session_id = session_resp.json()["session_id"]
        try:
            event_resp = self.client.post(
                "/api/os-lab/events",
                json={
                    "session_id": session_id,
                    "algorithm_id": "rr",
                    "algorithm_title": "RR 时间片轮转",
                    "event_type": "open_algorithm",
                    "frame_index": 0,
                    "total_frames": 6,
                },
            )
            self.assertEqual(event_resp.status_code, 200)

            events_resp = self.client.get(f"/api/os-lab/events/{session_id}")
            self.assertEqual(events_resp.status_code, 200)
            events = events_resp.json()
            self.assertEqual(events[0]["algorithm_id"], "rr")
            self.assertEqual(events[0]["event_type"], "open_algorithm")
        finally:
            self.client.delete(f"/api/session/{session_id}")

    def test_compiled_css_contains_responsive_and_motion_guards(self) -> None:
        css = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
        self.assertIn("prefers-reduced-motion: reduce", css)
        self.assertIn(".profile-step-nav", css)
        self.assertIn(".resource-library", css)

    def test_initial_session_selection_is_explicit(self) -> None:
        source = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        init_source = source[source.index("async init()") : source.index("setBusy(task")]
        self.assertNotIn("localStorage", init_source)
        self.assertNotIn("savedSessionId", init_source)
        self.assertNotIn("this.sessions[0]", init_source)
        self.assertIn("window.location.hash.slice(1)", init_source)


if __name__ == "__main__":
    unittest.main()
