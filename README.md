# Sarvam Backend Assignment

Production-grade FastAPI backend for batch enterprise ticket classification. The service accepts up to 500 raw support tickets, adaptively batches them for an LLM provider, applies bounded retries with jitter, returns partial successes, and exposes structured telemetry.

## Features

- FastAPI + Python 3.11 async service
- `POST /tickets/process` for up to 500 tickets
- Swappable LLM provider interface
- Mock provider for tests and local development
- Sarvam API adapter for production integration
- Adaptive batching based on token estimates and context window limits
- Exponential backoff with jitter for 429, 5xx, timeouts, and transient failures
- Partial failure handling with item-level failure details
- Queue reservation and immediate processing estimates
- JSON structured logging
- Prometheus metrics at `/metrics`
- Pytest unit and integration tests
- Docker and docker compose setup
- PDF-ready system design documentation in `docs/`

## Project Structure

```text
app/
  api/routes.py
  core/config.py
  services/batching.py
  services/retry.py
  services/llm_client.py
  services/processing.py
  services/queue_manager.py
  services/token_estimator.py
  telemetry/
  models/
benchmarks/
tests/
docs/
```

## Local Setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Docker

```bash
docker compose up --build
```

The API will be available at `http://localhost:8000`.

## API Example

Request:

```bash
curl -X POST http://localhost:8000/tickets/process \
  -H "Content-Type: application/json" \
  -H "x-request-id: req_demo" \
  -d '{
    "correlation_id": "customer_123",
    "tickets": [
      "Laptop battery drains quickly after firmware update.",
      "Please refund the duplicate subscription charge.",
      "The model produced a hallucinated policy citation."
    ]
  }'
```

Response shape:

```json
{
  "request_id": "req_demo",
  "correlation_id": "customer_123",
  "status": "succeeded",
  "estimate": {
    "estimated_wait_seconds": 0.0,
    "estimated_processing_seconds": 0.23,
    "estimated_completion_seconds": 0.23,
    "queue_position": 0,
    "estimated_batch_count": 1,
    "estimated_prompt_tokens": 230,
    "estimated_completion_tokens": 144
  },
  "successes": [
    {
      "ticket_index": 0,
      "category": "hardware_issue",
      "summary": "Laptop battery drains quickly after firmware update.",
      "confidence": 0.82,
      "provider": "mock"
    }
  ],
  "failures": [],
  "success_count": 3,
  "failure_count": 0,
  "elapsed_ms": 40.1
}
```

## Sarvam Provider

Local development uses `LLM_PROVIDER=mock`. To call Sarvam:

```bash
export LLM_PROVIDER=sarvam
export SARVAM_API_KEY=<your-key>
export SARVAM_API_URL=https://api.sarvam.ai/v1/chat/completions
export SARVAM_MODEL=sarvam-30b
uvicorn app.main:app
```

The provider expects Sarvam's chat-completions-style JSON response from `/v1/chat/completions`. If the public API shape differs, only `app/services/llm_client.py` needs to change because the rest of the pipeline depends on the provider interface.

## Batching Strategy

The adaptive batcher uses:

- max 50 tickets per provider call
- prompt token ceiling
- total context window ceiling
- conservative completion-token estimate

This keeps short-ticket throughput high while protecting long-ticket requests from context overflow. See `docs/batching_strategy.md`.

## Retry Strategy

Retries use exponential backoff and randomized jitter. The default budget is 5 total attempts, which covers transient overload without hiding sustained provider failure. Permanent 4xx errors are not retried. See `docs/retry_strategy.md`.

## Partial Failures

The API always attempts to return successful work. If one LLM batch fails permanently, successful batches are still returned and failed tickets are listed in `failures` with:

- ticket index
- error type
- retry attempts
- failure reason
- retryable flag

## Processing Estimate and Backpressure

Every response includes an `estimate` object with queue position, estimated wait time, estimated processing time, estimated completion time, estimated batch count, and estimated token usage. The estimate is computed immediately after queue reservation and before provider batch execution begins.

If queue capacity would be exceeded, the request is rejected immediately with HTTP 429 instead of allowing unbounded memory growth or unpredictable tail latency.

## Observability

Health and metrics:

```bash
curl http://localhost:8000/healthz
curl http://localhost:8000/metrics
```

Telemetry documentation is in `docs/observability.md`.

## Tests

```bash
pytest -q
```

Coverage includes:

- endpoint validation
- adaptive batching
- retry behavior
- processing estimates
- partial failure handling

## Benchmarks

```bash
python benchmarks/benchmark.py --iterations 30
```

Results and analysis are in `benchmarks/benchmark_results.md` and `docs/benchmark_analysis.md`.

## PDF Submission Assembly

The assignment requires one PDF upload. Recommended PDF content order:

1. `docs/architecture.md`
2. `docs/diagrams.md`
3. `README.md`
4. `docs/batching_strategy.md`
5. `docs/retry_strategy.md`
6. `docs/observability.md`
7. `docs/benchmark_analysis.md`
8. `benchmarks/benchmark_results.md`
9. Test output from `pytest -q`
10. GitHub repository link

All content is written to be PDF-ready and self-contained.
