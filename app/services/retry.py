from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from app.telemetry.metrics import RETRIES_TOTAL

T = TypeVar("T")


class RetryableError(Exception):
    def __init__(self, message: str, reason: str = "transient") -> None:
        super().__init__(message)
        self.reason = reason


class PermanentProviderError(Exception):
    pass


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 5
    base_delay_seconds: float = 0.35
    max_delay_seconds: float = 4.0
    jitter_ratio: float = 0.25

    async def run(self, operation: Callable[[int], Awaitable[T]]) -> tuple[T, int]:
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return await operation(attempt), attempt - 1
            except PermanentProviderError:
                raise
            except RetryableError as exc:
                last_error = exc
                RETRIES_TOTAL.labels(reason=exc.reason).inc()
                if attempt >= self.max_attempts:
                    break
                await asyncio.sleep(self._delay(attempt))
            except (asyncio.TimeoutError, ConnectionError, OSError) as exc:
                last_error = exc
                RETRIES_TOTAL.labels(reason=exc.__class__.__name__).inc()
                if attempt >= self.max_attempts:
                    break
                await asyncio.sleep(self._delay(attempt))

        assert last_error is not None
        raise RetryableError(f"retry budget exhausted: {last_error}", reason=last_error.__class__.__name__)

    def _delay(self, attempt: int) -> float:
        raw = min(self.max_delay_seconds, self.base_delay_seconds * (2 ** (attempt - 1)))
        jitter = raw * self.jitter_ratio
        return max(0.0, raw + random.uniform(-jitter, jitter))
