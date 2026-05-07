import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from prlmad.pdf_loader import PageText
from prlmad.text_splitter import chunk_pages, normalize_text


class TextSplitterTests(unittest.TestCase):
    def test_normalize_text(self):
        self.assertEqual(normalize_text("a   b\r\n\r\n\r\nc"), "a b\n\nc")

    def test_chunk_pages_keeps_page_range(self):
        pages = [
            PageText(1, "进程是程序的一次执行。线程是调度的基本单位。" * 20),
            PageText(2, "死锁需要互斥、占有并等待、不可抢占、循环等待。" * 20),
        ]
        chunks = chunk_pages(pages, max_chars=120, overlap_chars=20)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks[0].page_start, 1)
        self.assertGreaterEqual(chunks[-1].page_end, 2)


if __name__ == "__main__":
    unittest.main()
