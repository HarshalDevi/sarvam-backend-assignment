from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.constants import TicketCategory


class TicketResult(BaseModel):
    ticket_index: int
    category: TicketCategory
    summary: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)
    provider: str


class TicketFailure(BaseModel):
    ticket_index: int
    error_type: str
    retry_attempts: int
    failure_reason: str
    retryable: bool = False


class ProcessingEstimate(BaseModel):
    estimated_wait_seconds: float
    estimated_processing_seconds: float
    estimated_completion_seconds: float
    queue_position: int
    estimated_batch_count: int
    estimated_prompt_tokens: int
    estimated_completion_tokens: int


class ProcessTicketsResponse(BaseModel):
    request_id: str
    correlation_id: str | None
    status: str
    estimate: ProcessingEstimate
    successes: list[TicketResult]
    failures: list[TicketFailure]
    success_count: int
    failure_count: int
    elapsed_ms: float
