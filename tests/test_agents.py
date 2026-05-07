import unittest
from pathlib import Path
import sys
import uuid


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from prlmad.agents import AgentOrchestrator, GenerationRequest, LearnerInput
from prlmad.knowledge_base import KnowledgeBase
from prlmad.pdf_loader import PageText
from prlmad.spark_client import FakeSparkClient


class AgentTests(unittest.TestCase):
    def test_orchestrator_generates_requested_resources(self):
        tmp_root = Path(__file__).resolve().parents[1] / "data" / "test_dbs"
        tmp_root.mkdir(parents=True, exist_ok=True)
        kb = KnowledgeBase(tmp_root / f"{uuid.uuid4().hex}.sqlite3")
        kb.add_document(
            title="操作系统概念",
            course="操作系统",
            source_path="os.txt",
            pages=[PageText(1, "死锁需要互斥、占有并等待、不可抢占、循环等待。")],
        )
        result = AgentOrchestrator(FakeSparkClient(), kb).generate(
            GenerationRequest(
                course="操作系统",
                learner=LearnerInput(major="计算机", goal="理解死锁"),
                resource_types=["lecture_note", "exercises"],
            )
        )
        self.assertIn("lecture_note", result.resources)
        self.assertIn("exercises", result.resources)
        self.assertTrue(result.steps)


if __name__ == "__main__":
    unittest.main()
