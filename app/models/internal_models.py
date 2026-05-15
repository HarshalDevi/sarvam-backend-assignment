from __future__ import annotations

from dataclasses import dataclass

from app.core.constants import TicketCategory


@dataclass(frozen=True)
class TicketItem:
    index: int
    text: str
    estimated_tokens: int


@dataclass(frozen=True)
class TicketBatch:
    batch_id: str
    items: list[TicketItem]
    prompt_tokens: int
    estimated_completion_tokens: int


@dataclass(frozen=True)
class LLMClassification:
    ticket_index: int
    category: TicketCategory
    summary: str
    confidence: float


@dataclass(frozen=True)
class ProviderFailure:
    ticket_index: int
    error_type: str
    reason: str
    attempts: int
    retryable: bool


@dataclass(frozen=True)
class RetryState:
    attempts: int
    elapsed_seconds: float
