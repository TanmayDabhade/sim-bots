from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "sqlite+pysqlite:///./arena.db"
    model_provider: Literal["demo", "openrouter"] = "demo"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    qwen_model_id: str = "qwen/qwen3-8b"
    gemma_model_id: str = "google/gemma-3-12b-it"
    phi_model_id: str = "microsoft/phi-4"
    llama_model_id: str = "meta-llama/llama-3.1-8b-instruct"
    market_period: str = "5d"
    market_interval: str = "1m"
    arena_interval_minutes: int = Field(default=1, ge=1, le=390)
    enable_scheduler: bool = True
    max_daily_trades: int = Field(default=390, ge=1)
    admin_token: str = ""
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def model_ids(self) -> dict[str, str]:
        return {
            "qwen": self.qwen_model_id,
            "gemma": self.gemma_model_id,
            "phi": self.phi_model_id,
            "llama": self.llama_model_id,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
