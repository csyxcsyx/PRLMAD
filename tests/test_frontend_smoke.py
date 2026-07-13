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

    def test_required_static_assets_are_served(self) -> None:
        assets = (
            "/static/css/app.css",
            "/static/js/app.js",
            "/static/js/ai-renderer.js",
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

    def test_compiled_css_contains_responsive_and_motion_guards(self) -> None:
        css = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
        self.assertIn("prefers-reduced-motion: reduce", css)
        self.assertIn(".profile-step-nav", css)
        self.assertIn(".resource-library", css)


if __name__ == "__main__":
    unittest.main()
