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
    return KnowledgeBase(settings.db_path)


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
