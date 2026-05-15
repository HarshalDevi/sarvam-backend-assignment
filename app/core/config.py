from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "sarvam-ticket-inference-pipeline"
    environment: str = "local"
    log_level: str = "INFO"

    llm_provider: Literal["mock", "sarvam"] = "mock"
    sarvam_api_key: str | None = Field(default=None, alias="SARVAM_API_KEY")
    sarvam_api_url: str = "https://api.sarvam.ai/v1/chat/completions"
    sarvam_model: str = "sarvam-m"

    request_timeout_seconds: float = 12.0
    max_retries: int = 4
    retry_base_delay_seconds: float = 0.35
    retry_max_delay_seconds: float = 4.0

    max_tickets_per_request: int = 500
    context_window_tokens: int = 8192
    max_prompt_tokens_per_batch: int = 6200
    max_tickets_per_llm_batch: int = 50
    min_tickets_per_llm_batch: int = 1

    provider_concurrency: int = 8
    queue_max_items: int = 5_000
    nominal_tickets_per_second: float = 110.0

    prompt_token_price_per_1k: float = 0.00015
    completion_token_price_per_1k: float = 0.0006


@lru_cache
def get_settings() -> Settings:
    return Settings()
