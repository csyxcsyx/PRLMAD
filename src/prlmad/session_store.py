from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid


@dataclass
class SessionInfo:
    session_id: str
    name: str
    course: str
    created_at: str
    updated_at: str
    profile: dict = field(default_factory=dict)
    message_count: int = 0
    resource_count: int = 0


@dataclass
class ChatMessage:
    id: int
    session_id: str
    role: str
    content: str
    agent_type: str
    created_at: str


@dataclass
class ResourceRecord:
    id: int
    session_id: str
    resource_type: str
    resource_name: str
    content: str
    metadata_json: str
    created_at: str


@dataclass
class EvaluationRecord:
    id: int
    session_id: str
    eval_type: str
    data_json: str
    created_at: str


class SessionStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    course TEXT NOT NULL DEFAULT '操作系统',
                    profile_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    agent_type TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS resources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    resource_name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS learning_paths (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL UNIQUE,
                    path_json TEXT NOT NULL DEFAULT '{}',
                    current_step INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    eval_type TEXT NOT NULL DEFAULT 'comprehensive',
                    data_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS tutor_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    citations_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_history(session_id);
                CREATE INDEX IF NOT EXISTS idx_resources_session ON resources(session_id);
                CREATE INDEX IF NOT EXISTS idx_evaluations_session ON evaluations(session_id);
                CREATE INDEX IF NOT EXISTS idx_tutor_logs_session ON tutor_logs(session_id);
                """
            )

    def create_session(self, name: str = "新学习会话", course: str = "操作系统") -> SessionInfo:
        session_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO sessions(session_id, name, course, profile_json, created_at, updated_at) VALUES (?, ?, ?, '{}', ?, ?)",
                (session_id, name, course, now, now),
            )
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> SessionInfo:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT s.*, (SELECT COUNT(*) FROM chat_history WHERE session_id = s.session_id) as msg_count, (SELECT COUNT(*) FROM resources WHERE session_id = s.session_id) as res_count FROM sessions s WHERE s.session_id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            raise ValueError(f"Session not found: {session_id}")
        return SessionInfo(
            session_id=row["session_id"],
            name=row["name"],
            course=row["course"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            profile=json.loads(row["profile_json"]),
            message_count=row["msg_count"],
            resource_count=row["res_count"],
        )

    def list_sessions(self) -> list[SessionInfo]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT s.*,
                       (SELECT COUNT(*) FROM chat_history WHERE session_id = s.session_id) as msg_count,
                       (SELECT COUNT(*) FROM resources WHERE session_id = s.session_id) as res_count
                FROM sessions s ORDER BY s.updated_at DESC
                """
            ).fetchall()
        return [
            SessionInfo(
                session_id=row["session_id"],
                name=row["name"],
                course=row["course"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                profile=json.loads(row["profile_json"]),
                message_count=row["msg_count"],
                resource_count=row["res_count"],
            )
            for row in rows
        ]

    def delete_session(self, session_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

    def update_session(self, session_id: str, name: str | None = None, course: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        updates = []
        params: list = []
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if course is not None:
            updates.append("course = ?")
            params.append(course)
        if updates:
            updates.append("updated_at = ?")
            params.append(now)
            params.append(session_id)
            with self.connect() as conn:
                conn.execute(f"UPDATE sessions SET {', '.join(updates)} WHERE session_id = ?", params)

    def get_profile(self, session_id: str) -> dict:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT profile_json FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if not row:
            return {}
        return json.loads(row["profile_json"])

    def update_profile(self, session_id: str, profile: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute(
                "UPDATE sessions SET profile_json = ?, updated_at = ? WHERE session_id = ?",
                (json.dumps(profile, ensure_ascii=False), now, session_id),
            )

    def add_chat_message(self, session_id: str, role: str, content: str, agent_type: str = "") -> ChatMessage:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO chat_history(session_id, role, content, agent_type, created_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, role, content, agent_type, now),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?", (now, session_id)
            )
        return ChatMessage(
            id=cursor.lastrowid,
            session_id=session_id,
            role=role,
            content=content,
            agent_type=agent_type,
            created_at=now,
        )

    def get_chat_history(self, session_id: str, limit: int = 50) -> list[ChatMessage]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM chat_history WHERE session_id = ? ORDER BY id ASC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [
            ChatMessage(
                id=row["id"],
                session_id=row["session_id"],
                role=row["role"],
                content=row["content"],
                agent_type=row["agent_type"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def add_resource(
        self, session_id: str, resource_type: str, resource_name: str, content: str, metadata: dict | None = None
    ) -> ResourceRecord:
        now = datetime.now(timezone.utc).isoformat()
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO resources(session_id, resource_type, resource_name, content, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, resource_type, resource_name, content, meta_json, now),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?", (now, session_id)
            )
        return ResourceRecord(
            id=cursor.lastrowid,
            session_id=session_id,
            resource_type=resource_type,
            resource_name=resource_name,
            content=content,
            metadata_json=meta_json,
            created_at=now,
        )

    def get_resources(self, session_id: str) -> list[ResourceRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM resources WHERE session_id = ? ORDER BY id DESC",
                (session_id,),
            ).fetchall()
        return [
            ResourceRecord(
                id=row["id"],
                session_id=row["session_id"],
                resource_type=row["resource_type"],
                resource_name=row["resource_name"],
                content=row["content"],
                metadata_json=row["metadata_json"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def get_resource(self, resource_id: int) -> ResourceRecord | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM resources WHERE id = ?", (resource_id,)).fetchone()
        if not row:
            return None
        return ResourceRecord(
            id=row["id"],
            session_id=row["session_id"],
            resource_type=row["resource_type"],
            resource_name=row["resource_name"],
            content=row["content"],
            metadata_json=row["metadata_json"],
            created_at=row["created_at"],
        )

    def save_learning_path(self, session_id: str, path_json: dict, current_step: int = 0) -> None:
        now = datetime.now(timezone.utc).isoformat()
        path_str = json.dumps(path_json, ensure_ascii=False)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO learning_paths(session_id, path_json, current_step, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET path_json = ?, current_step = ?, updated_at = ?
                """,
                (session_id, path_str, current_step, now, now, path_str, current_step, now),
            )
            conn.execute("UPDATE sessions SET updated_at = ? WHERE session_id = ?", (now, session_id))

    def get_learning_path(self, session_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM learning_paths WHERE session_id = ?", (session_id,)
            ).fetchone()
        if not row:
            return None
        return {
            "path": json.loads(row["path_json"]),
            "current_step": row["current_step"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def update_learning_path_step(self, session_id: str, current_step: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute(
                "UPDATE learning_paths SET current_step = ?, updated_at = ? WHERE session_id = ?",
                (current_step, now, session_id),
            )

    def add_evaluation(self, session_id: str, eval_type: str, data: dict) -> EvaluationRecord:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO evaluations(session_id, eval_type, data_json, created_at) VALUES (?, ?, ?, ?)",
                (session_id, eval_type, json.dumps(data, ensure_ascii=False), now),
            )
            conn.execute("UPDATE sessions SET updated_at = ? WHERE session_id = ?", (now, session_id))
        return EvaluationRecord(
            id=cursor.lastrowid,
            session_id=session_id,
            eval_type=eval_type,
            data_json=json.dumps(data, ensure_ascii=False),
            created_at=now,
        )

    def get_evaluations(self, session_id: str) -> list[EvaluationRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM evaluations WHERE session_id = ? ORDER BY id DESC",
                (session_id,),
            ).fetchall()
        return [
            EvaluationRecord(
                id=row["id"],
                session_id=row["session_id"],
                eval_type=row["eval_type"],
                data_json=row["data_json"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def add_tutor_log(self, session_id: str, question: str, answer: str, citations: list[str] | None = None) -> int:
        now = datetime.now(timezone.utc).isoformat()
        citations_json = json.dumps(citations or [], ensure_ascii=False)
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO tutor_logs(session_id, question, answer, citations_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, question, answer, citations_json, now),
            )
            conn.execute("UPDATE sessions SET updated_at = ? WHERE session_id = ?", (now, session_id))
            return cursor.lastrowid

    def get_tutor_logs(self, session_id: str, limit: int = 50) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tutor_logs WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "question": row["question"],
                "answer": row["answer"],
                "citations": json.loads(row["citations_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]
