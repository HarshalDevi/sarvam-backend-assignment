# Observability

## Structured Logs

Logs are JSON and include:

- timestamp
- level
- logger
- message
- request_id
- correlation_id
- batch_id
- attempt
- status_code
- elapsed_ms

Sample log:

```json
{"timestamp":"2026-05-15T12:00:00Z","level":"INFO","logger":"app.main","message":"http_request","request_id":"req_123","correlation_id":"case_456","status_code":200,"elapsed_ms":42.1}
```

## Metrics

Prometheus metrics are exposed at `/metrics`:

- `tickets_process_requests_total`
- `tickets_processed_total`
- `llm_retries_total`
- `llm_batches_total`
- `processing_queue_depth`
- `tickets_process_latency_seconds`
- `llm_batch_latency_seconds`
- `estimated_tokens_total`

## Tracing Design

The app stores request and correlation IDs in context variables so lower layers can attach the same identifiers. In a deployed version, these would map naturally to OpenTelemetry spans:

- HTTP request span
- queue reservation span
- batch construction span
- provider call span
- retry attempt span
