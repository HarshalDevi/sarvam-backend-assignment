# Adaptive Batching Strategy

The batcher estimates tokens for every ticket and builds batches that satisfy three constraints:

- Provider item ceiling: default 50 tickets per LLM call.
- Prompt token ceiling: default 6,200 prompt tokens.
- Context window ceiling: default 8,192 tokens including estimated completion.

This gives high throughput for short tickets while safely splitting long tickets. Batch size 50 is a ceiling, not a forced size. If a single ticket is unusually long, it becomes its own batch so it cannot cause the entire request to overflow.

The token estimator is deliberately conservative. It takes the larger of lexical-token estimate and character-count estimate, then adds fixed JSON/prompt overhead. Production systems would replace this with provider-native tokenization when available.

Failure amplification is bounded to one adaptive batch. A 500-ticket request usually becomes 10 provider calls; if one provider call fails permanently, the API can still return the other 450 successes and 50 failures.

## Immediate Estimate and Admission Control

Before provider calls begin, the processor reserves lightweight queue capacity and returns estimate metadata in the API response. The estimate includes queue position, estimated wait seconds, estimated processing seconds, estimated completion seconds, estimated batch count, estimated prompt tokens, and estimated completion tokens.

Example estimate shape:

```json
{
  "queue_position": 0,
  "estimated_wait_seconds": 0.0,
  "estimated_processing_seconds": 0.44,
  "estimated_completion_seconds": 0.44,
  "estimated_batch_count": 1,
  "estimated_prompt_tokens": 283,
  "estimated_completion_tokens": 192
}
```

If the queue reservation would exceed configured capacity, the API rejects the request with HTTP 429. This is intentional backpressure: it protects memory, keeps latency bounded, and tells clients to retry later instead of silently accepting work the service cannot process predictably.
