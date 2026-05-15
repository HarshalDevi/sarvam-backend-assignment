from __future__ import annotations

import pytest

from app.services.retry import PermanentProviderError, RetryPolicy, RetryableError


@pytest.mark.asyncio
async def test_retry_eventually_succeeds() -> None:
    policy = RetryPolicy(max_attempts=4, base_delay_seconds=0.001, max_delay_seconds=0.001)
    calls = 0

    async def op(attempt: int) -> str:
        nonlocal calls
        calls += 1
        if attempt < 3:
            raise RetryableError("temporary", reason="test")
        return "ok"

    result, retries = await policy.run(op)
    assert result == "ok"
    assert retries == 2
    assert calls == 3


@pytest.mark.asyncio
async def test_retry_does_not_retry_permanent_errors() -> None:
    policy = RetryPolicy(max_attempts=4, base_delay_seconds=0.001, max_delay_seconds=0.001)
    calls = 0

    async def op(attempt: int) -> str:
        nonlocal calls
        calls += 1
        raise PermanentProviderError("bad request")

    with pytest.raises(PermanentProviderError):
        await policy.run(op)
    assert calls == 1
