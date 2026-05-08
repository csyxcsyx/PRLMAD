from __future__ import annotations

from functools import lru_cache

from src.prlmad.config import get_settings, Settings
from src.prlmad.knowledge_base import KnowledgeBase
from src.prlmad.spark_client import SparkClient
from src.prlmad.session_store import SessionStore


@lru_cache()
def get_settings_cached() -> Settings:
    return get_settings()


def get_knowledge_base() -> KnowledgeBase:
    settings = get_settings_cached()
    primary = KnowledgeBase(settings.db_path)
    active_path = settings.data_dir / "knowledge_active.sqlite3"
    if (
        settings.db_path.name == "knowledge.sqlite3"
        and active_path != settings.db_path
        and active_path.exists()
        and primary.get_chunk_count() == 0
    ):
        candidate = KnowledgeBase(active_path)
        if candidate.get_chunk_count() > 0:
            return candidate
    return primary


def get_session_store() -> SessionStore:
    settings = get_settings_cached()
    return SessionStore(settings.sessions_db_path)


def get_spark_client() -> SparkClient:
    settings = get_settings_cached()
    return SparkClient(
        api_key=settings.spark_api_key,
        base_url=settings.spark_base_url,
        model=settings.spark_model,
        user_id=settings.spark_user_id,
        enable_web_search=settings.spark_enable_web_search,
        offline_fallback=settings.spark_offline_fallback,
        trust_env_proxy=settings.spark_trust_env_proxy,
    )
