from __future__ import annotations

import pytest

from app.core.config import Settings
from app.services.batching import AdaptiveBatcher
from app.services.llm_client import LLMClient, MockLLMProvider
from app.services.processing import TicketProcessor
from app.services.queue_manager import QueueManager
from app.services.retry import RetryPolicy
from app.services.token_estimator import TokenEstimator


@pytest.mark.asyncio
async def test_processor_returns_successes_and_estimate() -> None:
    settings = Settings(max_tickets_per_llm_batch=2)
    processor = TicketProcessor(
        settings=settings,
        batcher=AdaptiveBatcher(settings, TokenEstimator()),
        llm_client=LLMClient(MockLLMProvider(0), RetryPolicy(base_delay_seconds=0.001), 1),
        queue_manager=QueueManager(100, 50),
    )
    response = await processor.process(["battery is overheating", "invoice charge wrong"], "req_test", None)
    assert response.success_count == 2
    assert response.failure_count == 0
    assert response.estimate.estimated_batch_count == 1
    assert response.successes[0].category == "hardware_issue"
    assert response.successes[1].category == "billing"
