from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str
    message: str
    course: str = "操作系统"


class GenerateRequest(BaseModel):
    session_id: str
    course: str = "操作系统"
    knowledge_points: str = ""
    resource_types: list[str] = Field(default_factory=lambda: [
        "lecture_note", "concept_map", "exercises",
        "case_project", "video_script", "ppt_outline", "task_checklist",
    ])
    top_k: int = 6


class TutorRequest(BaseModel):
    session_id: str
    question: str
    course: str = "操作系统"


class EvaluateRequest(BaseModel):
    session_id: str


class IngestRequest(BaseModel):
    path: str
    course: str = "操作系统"
    title: str | None = None
    ocr_mode: str = "auto"
    ocr_dpi: int | None = None


class TrainRequest(BaseModel):
    knowledge_dir: str | None = None
    course: str = "操作系统"
    ocr_mode: str = "auto"
    max_pages: int | None = None
    ocr_dpi: int | None = None
    force_rebuild: bool = False


class SearchRequest(BaseModel):
    query: str
    course: str | None = None
    top_k: int = 6


class CreateSessionRequest(BaseModel):
    name: str = "新学习会话"
    course: str = "操作系统"


class UpdateSessionRequest(BaseModel):
    name: str | None = None
    course: str | None = None


class UpdateProfileRequest(BaseModel):
    profile: dict


class UpdatePathStepRequest(BaseModel):
    current_step: int


class LearningPathRequest(BaseModel):
    session_id: str
    knowledge_points: str = ""
    course: str = "操作系统"
