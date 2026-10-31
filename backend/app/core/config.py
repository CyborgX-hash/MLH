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

    # Used by later milestones; declared now so configuration is documented in one place.
    github_token: Optional[str] = None
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen2.5:1.5b"


@lru_cache
def get_settings() -> Settings:
    return Settings()
