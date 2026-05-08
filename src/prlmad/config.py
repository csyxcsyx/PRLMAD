from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]


def load_dotenv(path: Path | None = None) -> None:
    env_path = path or BASE_DIR / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ[key] = value


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    base_dir: Path
    data_dir: Path
    db_path: Path
    sessions_db_path: Path
    knowledge_dir: Path
    spark_api_key: str | None
    spark_base_url: str
    spark_model: str
    spark_user_id: str
    spark_enable_web_search: bool
    spark_offline_fallback: bool
    spark_trust_env_proxy: bool
    ocr_mode: str


def get_settings() -> Settings:
    load_dotenv()

    data_dir = Path(os.getenv("PRLMAD_DATA_DIR", str(BASE_DIR / "data")))
    if not data_dir.is_absolute():
        data_dir = BASE_DIR / data_dir

    db_path = Path(os.getenv("PRLMAD_DB_PATH", str(data_dir / "knowledge.sqlite3")))
    if not db_path.is_absolute():
        db_path = BASE_DIR / db_path

    sessions_db_path = Path(os.getenv("PRLMAD_SESSIONS_DB_PATH", str(data_dir / "sessions.sqlite3")))
    if not sessions_db_path.is_absolute():
        sessions_db_path = BASE_DIR / sessions_db_path

    knowledge_dir = Path(os.getenv("PRLMAD_KNOWLEDGE_DIR", str(BASE_DIR / "knowledge")))
    if not knowledge_dir.is_absolute():
        knowledge_dir = BASE_DIR / knowledge_dir

    return Settings(
        base_dir=BASE_DIR,
        data_dir=data_dir,
        db_path=db_path,
        sessions_db_path=sessions_db_path,
        knowledge_dir=knowledge_dir,
        spark_api_key=os.getenv("SPARK_API_KEY"),
        spark_base_url=os.getenv(
            "SPARK_BASE_URL",
            "https://spark-api-open.xf-yun.com/agent/v1/chat/completions",
        ),
        spark_model=os.getenv("SPARK_MODEL", "spark-x"),
        spark_user_id=os.getenv("SPARK_USER_ID", "prlmad-demo-user"),
        spark_enable_web_search=_as_bool(os.getenv("SPARK_ENABLE_WEB_SEARCH"), False),
        spark_offline_fallback=_as_bool(os.getenv("PRLMAD_OFFLINE_FALLBACK"), False),
        spark_trust_env_proxy=_as_bool(os.getenv("SPARK_TRUST_ENV_PROXY"), False),
        ocr_mode=os.getenv("PRLMAD_OCR_MODE", "auto"),
    )
