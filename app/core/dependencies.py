from __future__ import annotations

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.services.batching import AdaptiveBatcher
from app.services.llm_client import LLMClient, MockLLMProvider, SarvamLLMProvider
from app.services.processing import TicketProcessor
from app.services.queue_manager import QueueManager
from app.services.retry import RetryPolicy
from app.services.token_estimator import TokenEstimator


@lru_cache
def get_token_estimator() -> TokenEstimator:
    return TokenEstimator()


@lru_cache
def get_queue_manager() -> QueueManager:
    settings = get_settings()
    return QueueManager(settings.queue_max_items, settings.nominal_tickets_per_second)


@lru_cache
def get_llm_client() -> LLMClient:
    settings = get_settings()
    retry = RetryPolicy(
        max_attempts=settings.max_retries + 1,
        base_delay_seconds=settings.retry_base_delay_seconds,
        max_delay_seconds=settings.retry_max_delay_seconds,
    )
    if settings.llm_provider == "sarvam":
        provider = SarvamLLMProvider(settings)
    else:
        provider = MockLLMProvider(latency_seconds=0.035)
    return LLMClient(provider=provider, retry_policy=retry, timeout_seconds=settings.request_timeout_seconds)


def get_processor() -> TicketProcessor:
    settings: Settings = get_settings()
    estimator = get_token_estimator()
    batcher = AdaptiveBatcher(settings=settings, token_estimator=estimator)
    return TicketProcessor(
        settings=settings,
        batcher=batcher,
        llm_client=get_llm_client(),
        queue_manager=get_queue_manager(),
    )
