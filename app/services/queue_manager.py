from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.core.constants import SECONDS_PER_TICKET_BASELINE
from app.models.response_models import ProcessingEstimate
from app.services.token_estimator import TokenEstimator
from app.telemetry.metrics import QUEUE_DEPTH


@dataclass
class QueueReservation:
    ticket_count: int
    queue_position: int


class QueueManager:
    def __init__(self, max_items: int, nominal_tickets_per_second: float) -> None:
        self.max_items = max_items
        self.nominal_tickets_per_second = nominal_tickets_per_second
        self._queued_items = 0
        self._lock = asyncio.Lock()

    async def reserve(self, ticket_count: int) -> QueueReservation:
        async with self._lock:
            if self._queued_items + ticket_count > self.max_items:
                raise OverflowError("processing queue capacity exceeded")
            position = self._queued_items
            self._queued_items += ticket_count
            QUEUE_DEPTH.set(self._queued_items)
            return QueueReservation(ticket_count=ticket_count, queue_position=position)

    async def release(self, ticket_count: int) -> None:
        async with self._lock:
            self._queued_items = max(0, self._queued_items - ticket_count)
            QUEUE_DEPTH.set(self._queued_items)

    def estimate(
        self,
        reservation: QueueReservation,
        batch_count: int,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> ProcessingEstimate:
        wait_seconds = reservation.queue_position / max(1.0, self.nominal_tickets_per_second)
        processing_seconds = max(
            0.15,
            reservation.ticket_count * SECONDS_PER_TICKET_BASELINE / max(1, min(batch_count, 8)),
        ) + batch_count * 0.08
        return ProcessingEstimate(
            estimated_wait_seconds=round(wait_seconds, 3),
            estimated_processing_seconds=round(processing_seconds, 3),
            estimated_completion_seconds=round(wait_seconds + processing_seconds, 3),
            queue_position=reservation.queue_position,
            estimated_batch_count=batch_count,
            estimated_prompt_tokens=prompt_tokens,
            estimated_completion_tokens=completion_tokens,
        )


def estimate_tokens_for_tickets(estimator: TokenEstimator, tickets: list[str]) -> tuple[int, int]:
    return estimator.estimate_prompt_tokens(tickets), estimator.estimate_completion_tokens(len(tickets))
