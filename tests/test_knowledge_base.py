import unittest
from pathlib import Path
import sys
import uuid


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from prlmad.knowledge_base import KnowledgeBase, tokenize
from prlmad.pdf_loader import PageText


class KnowledgeBaseTests(unittest.TestCase):
    def test_tokenize_chinese_bigrams(self):
        tokens = tokenize("死锁检测")
        self.assertIn("死锁", tokens)
        self.assertIn("检测", tokens)

    def test_add_and_search(self):
        tmp_root = Path(__file__).resolve().parents[1] / "data" / "test_dbs"
        tmp_root.mkdir(parents=True, exist_ok=True)
        kb = KnowledgeBase(tmp_root / f"{uuid.uuid4().hex}.sqlite3")
        kb.add_document(
            title="操作系统概念",
            course="操作系统",
            source_path="os.txt",
            pages=[
                PageText(1, "死锁的必要条件包括互斥、占有并等待、不可抢占和循环等待。"),
                PageText(2, "页面置换算法包括 FIFO、LRU 和 Optimal。"),
            ],
        )
        results = kb.search("死锁 必要条件", course="操作系统", top_k=1)
        self.assertEqual(len(results), 1)
        self.assertIn("死锁", results[0].text)


if __name__ == "__main__":
    unittest.main()
