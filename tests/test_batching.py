from __future__ import annotations

from app.core.config import Settings
from app.services.batching import AdaptiveBatcher
from app.services.token_estimator import TokenEstimator


def test_adaptive_batching_respects_max_items() -> None:
    settings = Settings(max_tickets_per_llm_batch=10)
    batcher = AdaptiveBatcher(settings, TokenEstimator())
    batches = batcher.create_batches([f"ticket {i}" for i in range(25)])
    assert [len(batch.items) for batch in batches] == [10, 10, 5]


def test_adaptive_batching_splits_large_token_payloads() -> None:
    settings = Settings(max_tickets_per_llm_batch=50, max_prompt_tokens_per_batch=900)
    batcher = AdaptiveBatcher(settings, TokenEstimator())
    tickets = ["word " * 300 for _ in range(4)]
    batches = batcher.create_batches(tickets)
    assert len(batches) == 4
    assert all(len(batch.items) == 1 for batch in batches)
