from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram


REQUESTS_TOTAL = Counter("tickets_process_requests_total", "Total process requests", ["status"])
TICKETS_TOTAL = Counter("tickets_processed_total", "Ticket outcomes", ["outcome", "category"])
RETRIES_TOTAL = Counter("llm_retries_total", "LLM retry attempts", ["reason"])
BATCHES_TOTAL = Counter("llm_batches_total", "LLM batches", ["provider", "status"])
QUEUE_DEPTH = Gauge("processing_queue_depth", "Estimated queued tickets")
REQUEST_LATENCY = Histogram("tickets_process_latency_seconds", "End-to-end request latency")
BATCH_LATENCY = Histogram("llm_batch_latency_seconds", "LLM batch latency", ["provider"])
TOKEN_USAGE = Counter("estimated_tokens_total", "Estimated token usage", ["kind"])
