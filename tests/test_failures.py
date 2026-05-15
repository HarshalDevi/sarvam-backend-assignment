from __future__ import annotations

import pytest

from app.core.config import Settings
from app.models.internal_models import TicketBatch
from app.services.batching import AdaptiveBatcher
from app.services.llm_client import LLMClient, LLMProvider, MockLLMProvider
from app.services.processing import TicketProcessor
from app.services.queue_manager import QueueManager
from app.services.retry import RetryPolicy, RetryableError
from app.services.token_estimator import TokenEstimator


class SelectiveFailProvider(LLMProvider):
    name = "selective_fail"

    def __init__(self) -> None:
        self.mock = MockLLMProvider(0)

    async def classify_batch(self, batch: TicketBatch):
        if any(item.index >= 2 for item in batch.items):
            raise RetryableError("upstream overloaded", reason="503")
        return await self.mock.classify_batch(batch)


@pytest.mark.asyncio
async def test_partial_failure_keeps_successful_batches() -> None:
    settings = Settings(max_tickets_per_llm_batch=2, max_retries=1)
    processor = TicketProcessor(
        settings=settings,
        batcher=AdaptiveBatcher(settings, TokenEstimator()),
        llm_client=LLMClient(SelectiveFailProvider(), RetryPolicy(max_attempts=2, base_delay_seconds=0.001), 1),
        queue_manager=QueueManager(100, 50),
    )
    response = await processor.process(["battery", "invoice", "model bad", "driver crash"], "req_test", None)
    assert response.status == "partial_success"
    assert response.success_count == 2
    assert response.failure_count == 2
    assert {failure.ticket_index for failure in response.failures} == {2, 3}
