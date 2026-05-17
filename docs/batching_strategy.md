# Adaptive Batching Strategy

The batcher estimates tokens for every ticket and builds batches that satisfy three constraints:

- Provider item ceiling: default 50 tickets per LLM call.
- Prompt token ceiling: default 6,200 prompt tokens.
- Context window ceiling: default 8,192 tokens including estimated completion.

In practice, this keeps short tickets efficient while still splitting long tickets safely. Batch size 50 is a ceiling, not a forced size. If a single ticket is unusually long, it becomes its own batch so it cannot cause the entire request to overflow.

Provider batch calls are dispatched concurrently using `asyncio.gather`, bounded by a semaphore from `provider_concurrency`. This means a request with several adaptive batches does not wait for every provider call serially, while still limiting upstream pressure.

The token estimator is deliberately conservative. It takes the larger of word-based estimate and character-count estimate, then adds fixed JSON/prompt overhead. In a hosted deployment, this can be swapped for provider-native tokenization when available.

Failure amplification is bounded by adaptive batching and split-and-retry isolation. A 500-ticket request usually becomes 10 provider calls. If one provider call fails permanently, the processor splits that failed batch into smaller halves and retries them, so good tickets can still be recovered instead of marking the full batch as failed.

## Immediate Processing Estimate and Admission Control

Before provider calls begin, the processor reserves lightweight queue capacity and returns estimate metadata in the API response. The estimate includes queue position, estimated wait seconds, estimated processing seconds, estimated completion seconds, estimated batch count, estimated prompt tokens, and estimated completion tokens.

Queue capacity is measured in ticket slots, with a default of 5,000 queued tickets. If the queue reservation would exceed that capacity, the API rejects the request with HTTP 429. This is intentional backpressure: it protects memory, keeps latency bounded, and tells clients to retry later instead of accepting work the service cannot process predictably.
