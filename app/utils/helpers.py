from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from collections.abc import Iterator


def new_request_id() -> str:
    return f"req_{uuid.uuid4().hex}"


def new_batch_id() -> str:
    return f"batch_{uuid.uuid4().hex[:12]}"


@contextmanager
def timer() -> Iterator[callable[[], float]]:
    start = time.perf_counter()

    def elapsed_ms() -> float:
        return (time.perf_counter() - start) * 1000

    yield elapsed_ms
