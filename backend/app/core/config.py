"""Application settings, read from environment variables (and `.env` in development).

Secrets such as GITHUB_TOKEN are never hard-coded; they only come from the environment.
"""
from functools import lru_cache
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_name: str = "DeciTrace"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://decitrace:decitrace@localhost:5433/decitrace"
    cors_origins: List[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    github_token: Optional[str] = None
    # Protects endpoints that write decision candidates or rebuild indexes. Unset = those endpoints are disabled.
    decitrace_admin_token: Optional[str] = None

    # Any OpenAI-compatible endpoint serving open-weight models: Ollama (default), vLLM, llama.cpp server,
    # or a hosted provider. The API key is only sent to that endpoint, never to the frontend.
    ai_provider: str = "ollama"
    ai_base_url: str = "http://localhost:11434/v1"
    ai_model: str = "qwen3:8b"
    ai_api_key: Optional[str] = None
    ai_embed_model: Optional[str] = "qwen3-embedding:0.6b"  # empty disables vector search (full-text only)
    ai_extract_model: Optional[str] = None  # model for decision extraction; defaults to ai_model
    ai_timeout: float = 180.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
