from __future__ import annotations

import asyncio
import logging

from app.core.config import Settings
from app.models.internal_models import TicketBatch
from app.models.response_models import ProcessTicketsResponse, TicketFailure, TicketResult
from app.services.batching import AdaptiveBatcher
from app.services.llm_client import LLMClient
from app.services.queue_manager import QueueManager
from app.services.retry import PermanentProviderError, RetryableError
from app.telemetry.metrics import REQUESTS_TOTAL, TICKETS_TOTAL, TOKEN_USAGE
from app.utils.helpers import timer

logger = logging.getLogger(__name__)


class TicketProcessor:
    def __init__(
        self,
        settings: Settings,
        batcher: AdaptiveBatcher,
        llm_client: LLMClient,
        queue_manager: QueueManager,
    ) -> None:
        self.settings = settings
        self.batcher = batcher
        self.llm_client = llm_client
        self.queue_manager = queue_manager
        self._semaphore = asyncio.Semaphore(settings.provider_concurrency)

    async def process(self, tickets: list[str], request_id: str, correlation_id: str | None) -> ProcessTicketsResponse:
        batches = self.batcher.create_batches(tickets)
        prompt_tokens = sum(batch.prompt_tokens for batch in batches)
        completion_tokens = sum(batch.estimated_completion_tokens for batch in batches)
        reservation = await self.queue_manager.reserve(len(tickets))
        estimate = self.queue_manager.estimate(reservation, len(batches), prompt_tokens, completion_tokens)

        successes: list[TicketResult] = []
        failures: list[TicketFailure] = []

        with timer() as elapsed_ms:
            try:
                batch_results = await asyncio.gather(
                    *(self._process_batch_resilient(batch) for batch in batches),
                    return_exceptions=True,
                )
            finally:
                await self.queue_manager.release(len(tickets))

            for batch, outcome in zip(batches, batch_results, strict=True):
                if isinstance(outcome, Exception):
                    retry_attempts = self.settings.max_retries
                    error_type = outcome.__class__.__name__
                    retryable = isinstance(outcome, RetryableError)
                    for item in batch.items:
                        failures.append(
                            TicketFailure(
                                ticket_index=item.index,
                                error_type=error_type,
                                retry_attempts=retry_attempts,
                                failure_reason=str(outcome),
                                retryable=retryable,
                            )
                        )
                    continue

                classifications, retries, isolated_failures = outcome
                failures.extend(isolated_failures)
                for classification in classifications:
                    successes.append(
                        TicketResult(
                            ticket_index=classification.ticket_index,
                            category=classification.category,
                            summary=classification.summary,
                            confidence=classification.confidence,
                            provider=self.llm_client.provider.name,
                        )
                    )
                    TICKETS_TOTAL.labels(outcome="success", category=classification.category.value).inc()

                returned_indexes = {classification.ticket_index for classification in classifications}
                failed_indexes = {failure.ticket_index for failure in isolated_failures}
                for item in batch.items:
                    if item.index not in returned_indexes and item.index not in failed_indexes:
                        failures.append(
                            TicketFailure(
                                ticket_index=item.index,
                                error_type="MissingProviderResult",
                                retry_attempts=retries,
                                failure_reason="provider did not return a classification for this ticket",
                                retryable=True,
                            )
                        )

        for failure in failures:
            TICKETS_TOTAL.labels(outcome="failure", category="unknown").inc()

        TOKEN_USAGE.labels(kind="prompt").inc(prompt_tokens)
        TOKEN_USAGE.labels(kind="completion").inc(completion_tokens)
        status = "partial_success" if failures and successes else "failed" if failures else "succeeded"
        REQUESTS_TOTAL.labels(status=status).inc()

        return ProcessTicketsResponse(
            request_id=request_id,
            correlation_id=correlation_id,
            status=status,
            estimate=estimate,
            successes=sorted(successes, key=lambda item: item.ticket_index),
            failures=sorted(failures, key=lambda item: item.ticket_index),
            success_count=len(successes),
            failure_count=len(failures),
            elapsed_ms=round(elapsed_ms(), 3),
        )

    async def _process_batch(self, batch):
        async with self._semaphore:
            try:
                return await self.llm_client.classify_batch(batch)
            except PermanentProviderError:
                raise
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("batch_failed", extra={"batch_id": batch.batch_id}, exc_info=exc)
                raise

    async def _process_batch_resilient(self, batch: TicketBatch) -> tuple[list, int, list[TicketFailure]]:
        try:
            classifications, retries = await self._process_batch(batch)
            return classifications, retries, []
        except Exception as exc:
            if len(batch.items) <= 1:
                item = batch.items[0]
                return (
                    [],
                    self.settings.max_retries,
                    [
                        TicketFailure(
                            ticket_index=item.index,
                            error_type=exc.__class__.__name__,
                            retry_attempts=self.settings.max_retries,
                            failure_reason=str(exc),
                            retryable=isinstance(exc, RetryableError),
                        )
                    ],
                )

            midpoint = len(batch.items) // 2
            left = TicketBatch(
                batch_id=f"{batch.batch_id}_left",
                items=batch.items[:midpoint],
                prompt_tokens=max(1, batch.prompt_tokens // 2),
                estimated_completion_tokens=batch.estimated_completion_tokens // 2,
            )
            right = TicketBatch(
                batch_id=f"{batch.batch_id}_right",
                items=batch.items[midpoint:],
                prompt_tokens=max(1, batch.prompt_tokens - left.prompt_tokens),
                estimated_completion_tokens=batch.estimated_completion_tokens - left.estimated_completion_tokens,
            )
            left_result, right_result = await asyncio.gather(
                self._process_batch_resilient(left),
                self._process_batch_resilient(right),
            )
            classifications = [*left_result[0], *right_result[0]]
            failures = [*left_result[2], *right_result[2]]
            retries = max(left_result[1], right_result[1], self.settings.max_retries)
            return classifications, retries, failures
