from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import math
from pathlib import Path
import re
import sqlite3
from sqlite3 import OperationalError
from typing import Callable, Iterable

from .pdf_loader import PageText
from .text_splitter import TextChunk, chunk_pages


ProgressCallback = Callable[[str, dict], None]


def _emit(progress: ProgressCallback | None, stage: str, **detail) -> None:
    if progress:
        progress(stage, detail)


TOKEN_RE = re.compile(r"[A-Za-z0-9_+#./()-]+|[\u4e00-\u9fff]+")


@dataclass(frozen=True)
class DocumentInfo:
    id: int
    title: str
    course: str
    source_path: str
    created_at: str
    chunk_count: int


@dataclass(frozen=True)
class SearchResult:
    chunk_id: int
    title: str
    course: str
    source_path: str
    page_start: int
    page_end: int
    text: str
    score: float

    @property
    def page_label(self) -> str:
        if self.page_start == self.page_end:
            return f"p.{self.page_start}"
        return f"pp.{self.page_start}-{self.page_end}"


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for match in TOKEN_RE.finditer(text.lower()):
        item = match.group(0)
        if not item:
            continue
        if "\u4e00" <= item[0] <= "\u9fff":
            if len(item) == 1:
                tokens.append(item)
                continue
            for size in (1, 2, 3):
                if len(item) >= size:
                    tokens.extend(item[i:i + size] for i in range(0, len(item) - size + 1))
        else:
            tokens.append(item)
    return tokens


class KnowledgeBase:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._init_db()
        except OperationalError:
            if self._recover_empty_db():
                self._init_db()
            else:
                raise

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=OFF")
            conn.execute("PRAGMA synchronous=OFF")
        except OperationalError:
            conn.close()
            if self._recover_empty_db():
                conn = sqlite3.connect(str(self.db_path))
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=OFF")
                conn.execute("PRAGMA synchronous=OFF")
            else:
                raise
        return conn

    def _recover_empty_db(self) -> bool:
        if not self.db_path.exists() or self.db_path.stat().st_size != 0:
            return False
        self.db_path.unlink(missing_ok=True)
        journal = self.db_path.with_name(self.db_path.name + "-journal")
        journal.unlink(missing_ok=True)
        return True

    def _init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    course TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER NOT NULL,
                    ordinal INTEGER NOT NULL,
                    page_start INTEGER NOT NULL,
                    page_end INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS chunk_terms (
                    chunk_id INTEGER NOT NULL,
                    term TEXT NOT NULL,
                    tf INTEGER NOT NULL,
                    PRIMARY KEY(chunk_id, term),
                    FOREIGN KEY(chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_documents_course ON documents(course);
                CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source_path);
                CREATE INDEX IF NOT EXISTS idx_chunk_terms_term ON chunk_terms(term);
                """
            )

    def add_document(
        self,
        title: str,
        course: str,
        source_path: str | Path,
        pages: Iterable[PageText],
        replace: bool = True,
        on_progress: ProgressCallback | None = None,
    ) -> DocumentInfo:
        page_list = list(pages)
        _emit(on_progress, "chunk_start", title=title, pages=len(page_list))
        chunks = chunk_pages(page_list)
        _emit(on_progress, "chunk_done", title=title, pages=len(page_list), chunks=len(chunks))
        if not chunks:
            raise ValueError("No text chunks were extracted from the document.")

        source = str(Path(source_path))
        created_at = datetime.now(timezone.utc).isoformat()

        with self.connect() as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            if replace:
                _emit(on_progress, "db_replace_start", title=title, course=course)
                rows = conn.execute(
                    "SELECT id FROM documents WHERE source_path = ? AND course = ?",
                    (source, course),
                ).fetchall()
                for row in rows:
                    conn.execute("DELETE FROM documents WHERE id = ?", (row["id"],))
                _emit(on_progress, "db_replace_done", title=title, deleted=len(rows))

            cursor = conn.execute(
                "INSERT INTO documents(title, course, source_path, created_at) VALUES (?, ?, ?, ?)",
                (title, course, source, created_at),
            )
            document_id = int(cursor.lastrowid)

            total_chunks = len(chunks)
            _emit(on_progress, "db_index_start", title=title, chunks=total_chunks)
            for ordinal, chunk in enumerate(chunks, start=1):
                chunk_cursor = conn.execute(
                    """
                    INSERT INTO chunks(document_id, ordinal, page_start, page_end, text)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (document_id, ordinal - 1, chunk.page_start, chunk.page_end, chunk.text),
                )
                chunk_id = int(chunk_cursor.lastrowid)
                counts = Counter(tokenize(chunk.text))
                conn.executemany(
                    "INSERT INTO chunk_terms(chunk_id, term, tf) VALUES (?, ?, ?)",
                    ((chunk_id, term, tf) for term, tf in counts.items()),
                )
                _emit(
                    on_progress,
                    "db_index_chunk",
                    title=title,
                    chunk=ordinal,
                    total=total_chunks,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                )
            _emit(on_progress, "db_index_done", title=title, chunks=total_chunks)

        return DocumentInfo(document_id, title, course, source, created_at, len(chunks))

    def upsert_document_pages(
        self,
        title: str,
        course: str,
        source_path: str | Path,
        pages: Iterable[PageText],
        replace: bool = False,
        on_progress: ProgressCallback | None = None,
    ) -> DocumentInfo:
        source = str(Path(source_path))
        if replace:
            return self.add_document(
                title=title,
                course=course,
                source_path=source,
                pages=pages,
                replace=True,
                on_progress=on_progress,
            )

        existing = self.get_document_by_source(source, course)
        if not existing:
            return self.add_document(
                title=title,
                course=course,
                source_path=source,
                pages=pages,
                replace=False,
                on_progress=on_progress,
            )

        page_list = list(pages)
        _emit(on_progress, "chunk_start", title=title, pages=len(page_list))
        chunks = chunk_pages(page_list)
        _emit(on_progress, "chunk_done", title=title, pages=len(page_list), chunks=len(chunks))
        if not chunks:
            return self.get_document(existing.id)

        with self.connect() as conn:
            current_max_ordinal = conn.execute(
                "SELECT COALESCE(MAX(ordinal), -1) FROM chunks WHERE document_id = ?",
                (existing.id,),
            ).fetchone()[0]
            total_chunks = len(chunks)
            _emit(on_progress, "db_index_start", title=title, chunks=total_chunks)
            for index, chunk in enumerate(chunks, start=1):
                chunk_cursor = conn.execute(
                    """
                    INSERT INTO chunks(document_id, ordinal, page_start, page_end, text)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (existing.id, current_max_ordinal + index, chunk.page_start, chunk.page_end, chunk.text),
                )
                chunk_id = int(chunk_cursor.lastrowid)
                counts = Counter(tokenize(chunk.text))
                conn.executemany(
                    "INSERT INTO chunk_terms(chunk_id, term, tf) VALUES (?, ?, ?)",
                    ((chunk_id, term, tf) for term, tf in counts.items()),
                )
                _emit(
                    on_progress,
                    "db_index_chunk",
                    title=title,
                    chunk=index,
                    total=total_chunks,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                )
            _emit(on_progress, "db_index_done", title=title, chunks=total_chunks)
        return self.get_document(existing.id)

    def list_documents(self) -> list[DocumentInfo]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT d.*, COUNT(c.id) AS chunk_count
                FROM documents d
                LEFT JOIN chunks c ON c.document_id = d.id
                GROUP BY d.id
                ORDER BY d.created_at DESC
                """
            ).fetchall()
        return [
            DocumentInfo(
                id=row["id"],
                title=row["title"],
                course=row["course"],
                source_path=row["source_path"],
                created_at=row["created_at"],
                chunk_count=row["chunk_count"],
            )
            for row in rows
        ]

    def get_document(self, document_id: int) -> DocumentInfo:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT d.*, COUNT(c.id) AS chunk_count
                FROM documents d
                LEFT JOIN chunks c ON c.document_id = d.id
                WHERE d.id = ?
                GROUP BY d.id
                """,
                (document_id,),
            ).fetchone()
        if not row:
            raise ValueError(f"Document not found: {document_id}")
        return DocumentInfo(
            id=row["id"],
            title=row["title"],
            course=row["course"],
            source_path=row["source_path"],
            created_at=row["created_at"],
            chunk_count=row["chunk_count"],
        )

    def get_document_by_source(self, source_path: str | Path, course: str) -> DocumentInfo | None:
        source = str(Path(source_path))
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT d.*, COUNT(c.id) AS chunk_count
                FROM documents d
                LEFT JOIN chunks c ON c.document_id = d.id
                WHERE d.source_path = ? AND d.course = ?
                GROUP BY d.id
                ORDER BY d.id DESC
                LIMIT 1
                """,
                (source, course),
            ).fetchone()
        if not row:
            return None
        return DocumentInfo(
            id=row["id"],
            title=row["title"],
            course=row["course"],
            source_path=row["source_path"],
            created_at=row["created_at"],
            chunk_count=row["chunk_count"],
        )

    def get_document_page_extent(self, document_id: int) -> tuple[int, int]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MIN(page_start), 0), COALESCE(MAX(page_end), 0) FROM chunks WHERE document_id = ?",
                (document_id,),
            ).fetchone()
        return int(row[0] or 0), int(row[1] or 0)

    def search(self, query: str, course: str | None = None, top_k: int = 6) -> list[SearchResult]:
        query_terms = Counter(tokenize(query))
        if not query_terms:
            return []

        terms = [term for term, _ in query_terms.most_common(80)]
        placeholders = ",".join("?" for _ in terms)
        params: list[object] = list(terms)
        course_clause = ""
        if course:
            course_clause = "AND d.course = ?"
            params.append(course)
        params.append(max(top_k * 5, top_k))

        sql = f"""
            SELECT
                c.id AS chunk_id,
                c.page_start,
                c.page_end,
                c.text,
                d.title,
                d.course,
                d.source_path,
                SUM(t.tf) AS raw_score,
                COUNT(*) AS matched_terms
            FROM chunk_terms t
            JOIN chunks c ON c.id = t.chunk_id
            JOIN documents d ON d.id = c.document_id
            WHERE t.term IN ({placeholders}) {course_clause}
            GROUP BY c.id
            ORDER BY raw_score DESC, matched_terms DESC
            LIMIT ?
        """

        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        results: list[SearchResult] = []
        exact = query.strip().lower()
        for row in rows:
            text = row["text"]
            score = float(row["raw_score"] or 0)
            score += 2.0 * float(row["matched_terms"] or 0)
            if exact and exact in text.lower():
                score += 20.0
            score += math.log(max(len(text), 1), 10)
            results.append(
                SearchResult(
                    chunk_id=row["chunk_id"],
                    title=row["title"],
                    course=row["course"],
                    source_path=row["source_path"],
                    page_start=row["page_start"],
                    page_end=row["page_end"],
                    text=text,
                    score=score,
                )
            )

        results.sort(key=lambda item: item.score, reverse=True)
        return results[:top_k]

    def format_context(self, results: Iterable[SearchResult], max_chars_each: int = 900) -> str:
        lines: list[str] = []
        for index, result in enumerate(results, start=1):
            text = result.text
            if len(text) > max_chars_each:
                text = text[:max_chars_each].rstrip() + "..."
            lines.append(
                f"[资料{index}] 《{result.title}》{result.page_label}，课程：{result.course}\n{text}"
            )
        return "\n\n".join(lines)

    def get_document_chunks(self, document_id: int) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, ordinal, page_start, page_end, text FROM chunks WHERE document_id = ? ORDER BY ordinal",
                (document_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_document_count(self) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM documents").fetchone()
        return row[0] if row else 0

    def get_chunk_count(self) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()
        return row[0] if row else 0
