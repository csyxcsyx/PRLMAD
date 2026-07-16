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

    def test_page_replacement_animates_every_reference(self) -> None:
        source = (ROOT / "templates" / "pages" / "os_lab.html").read_text(encoding="utf-8")
        for scenario in ("lruPage",):
            with self.subTest(scenario=scenario):
                match = re.search(
                    rf"{scenario}:\s*\{{.*?reference:\s*\[(.*?)\].*?frames:\s*\[(.*?)\]\s*,\s*\}}",
                    source,
                    re.DOTALL,
                )
                self.assertIsNotNone(match)
                reference_count = len(re.findall(r"\d+", match.group(1)))
                frame_count = len(re.findall(r"\{\s*pointer:", match.group(2)))
                self.assertEqual(frame_count, reference_count)

        self.assertIn("if (this.frameIndex >= last)", source)
        self.assertIn("this.stopRun();", source)

    def test_os_lab_shows_one_representative_per_category(self) -> None:
        source = (ROOT / "templates" / "pages" / "os_lab.html").read_text(encoding="utf-8")
        algorithm_list = source[source.index("algorithms: [") : source.index("get current()")]
        visible_ids = re.findall(r"id:\s*'([^']+)'", algorithm_list)
        self.assertEqual(
            visible_ids,
            ["rr", "firstFit", "lruPage", "producerConsumer", "banker"],
        )

        scenarios = source[source.index("scenarios()") : source.index("}));")]
        removed_ids = (
            "fcfs", "sjf", "priority", "bestFit", "worstFit", "fifoPage", "optPage",
            "schedule", "memory", "page", "thread", "deadlock",
        )
        for scenario in removed_ids:
            self.assertNotRegex(scenarios, rf"\b{scenario}:\s*\{{")

    def test_banker_frames_expose_resource_flow(self) -> None:
        source = (ROOT / "templates" / "pages" / "os_lab.html").read_text(encoding="utf-8")
        banker = source[source.index("banker: {") : source.index("};", source.index("banker: {"))]
        for work_after in ("[1, 0, 2]", "[3, 1, 2]", "[4, 1, 3]", "[5, 2, 4]"):
            self.assertIn(f"workAfter: {work_after}", banker)
        self.assertIn("sequence: ['P2', 'P1', 'P3']", banker)
        self.assertIn('class="banker-ledger"', source)
        self.assertIn('class="banker-matrix"', source)

    def test_producer_consumer_exposes_atomic_sync_steps(self) -> None:
        source = (ROOT / "templates" / "pages" / "os_lab.html").read_text(encoding="utf-8")
        scenario = source[source.index("producerConsumer: {") : source.index("banker: {")]
        operations = re.findall(r"operation:\s*'([^']+)'", scenario)
        self.assertEqual(
            operations,
            [
                "初始化",
                "P(empty)",
                "P(mutex)",
                "put(A); V(mutex); V(full)",
                "P(full); P(mutex)",
                "get(A); V(mutex); V(empty)",
            ],
        )
        self.assertIn('class="pc-semaphores"', source)
        self.assertIn('class="pc-pipeline"', source)

    def test_lru_frames_expose_recency_and_results(self) -> None:
        source = (ROOT / "templates" / "pages" / "os_lab.html").read_text(encoding="utf-8")
        scenario = source[source.index("lruPage: {") : source.index("producerConsumer: {")]
        self.assertEqual(len(re.findall(r"result:\s*'(?:hit|fault)'", scenario)), 10)
        self.assertEqual(len(re.findall(r"result:\s*'hit'", scenario)), 2)
        self.assertIn("blocks: [4, 3, 2]", scenario)
        self.assertIn("recency: [3, 2, 4]", scenario)
        self.assertIn("faults: 8, hits: 2", scenario)
        self.assertIn('class="lru-access-tape"', source)
        self.assertIn('class="lru-recency"', source)

    def test_first_fit_exposes_scan_and_split(self) -> None:
        source = (ROOT / "templates" / "pages" / "os_lab.html").read_text(encoding="utf-8")
        scenario = source[source.index("firstFit: {") : source.index("lruPage: {")]
        decisions = re.findall(r"decision:\s*'([^']+)'", scenario)
        self.assertEqual(
            decisions,
            ["pending", "occupied", "reject", "occupied", "fit", "allocated"],
        )
        self.assertIn("comparison: '260 ≥ 180'", scenario)
        self.assertIn("label: 'P3', start: 480, size: 180, type: 'allocated'", scenario)
        self.assertIn("label: '空闲', start: 660, size: 80, type: 'free'", scenario)
        self.assertIn('class="ff-map"', source)

    def test_playback_controls_live_in_experiment_toolbar(self) -> None:
        source = (ROOT / "templates" / "pages" / "os_lab.html").read_text(encoding="utf-8")
        toolbar = source[source.index('<div class="desktop-bar">') : source.index('<div class="workspace">')]
        stage_head = source[source.index('<div class="stage-head">') : source.index('<div class="experiment-controls">')]
        controls = source[source.index('<div class="experiment-controls">') : source.index('<div class="experiment-grid">')]
        self.assertNotIn('class="toolbar-step"', toolbar)
        self.assertNotIn('@click="resetAnimation()"', toolbar)
        self.assertNotIn('@click="resetLab()"', toolbar)
        self.assertNotIn('@click="resetAnimation()"', stage_head)
        self.assertIn('@click="resetLab()"', stage_head)
        self.assertIn('class="toolbar-step"', controls)
        self.assertIn('@click="backToCards()"', controls)
        self.assertIn('@click="resetAnimation()"', controls)
        self.assertIn('@click="toggleRun()"', controls)
        self.assertIn('@click="nextFrame()"', controls)
        self.assertNotIn('progress-track', source)
        self.assertNotIn('get progress()', source)

    def test_os_lab_uses_open_workbench_layout(self) -> None:
        source = (ROOT / "templates" / "pages" / "os_lab.html").read_text(encoding="utf-8")
        self.assertNotIn(".desktop-strip, .algo-card, .stage", source)
        self.assertRegex(source, r"\.stage\s*\{[^}]*border:\s*0;")
        for board in ("ff-board", "lru-board", "pc-board", "banker-board"):
            self.assertRegex(source, rf"\.{board}\s*\{{[^}}]*border:\s*0;")

    def test_os_lab_enters_fullscreen_after_algorithm_selection(self) -> None:
        source = (ROOT / "templates" / "pages" / "os_lab.html").read_text(encoding="utf-8")
        self.assertIn("immersive: false", source)
        self.assertIn("height: 100dvh", source)
        method_start = source.index("        openAlgorithm(id)")
        open_algorithm = source[method_start : source.index("        backToCards()", method_start)]
        self.assertIn("this.setImmersive(true)", open_algorithm)
        self.assertGreaterEqual(source.count("this.setImmersive(false)"), 2)
        self.assertIn("event.key === 'Escape'", source)

    def test_os_lab_highlights_code_for_each_step(self) -> None:
        source = (ROOT / "templates" / "pages" / "os_lab.html").read_text(encoding="utf-8")
        self.assertIn('class="code-line"', source)
        self.assertIn("activeCodeLines.includes(index + 1)", source)
        self.assertIn("codeLineMap: {", source)
        for scenario in ("rr", "firstFit", "lruPage", "producerConsumer", "banker"):
            self.assertRegex(source, rf"\b{scenario}:\s*\[\s*\[")
        self.assertIn("syncCodeFocus()", source)
        self.assertIn("this.backToCards()", source)

if __name__ == "__main__":
    unittest.main()
