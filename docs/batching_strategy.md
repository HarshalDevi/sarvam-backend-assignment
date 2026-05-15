# Adaptive Batching Strategy

The batcher estimates tokens for every ticket and builds batches that satisfy three constraints:

- Provider item ceiling: default 50 tickets per LLM call.
- Prompt token ceiling: default 6,200 prompt tokens.
- Context window ceiling: default 8,192 tokens including estimated completion.

This gives high throughput for short tickets while safely splitting long tickets. Batch size 50 is a ceiling, not a forced size. If a single ticket is unusually long, it becomes its own batch so it cannot cause the entire request to overflow.

The token estimator is deliberately conservative. It takes the larger of lexical-token estimate and character-count estimate, then adds fixed JSON/prompt overhead. Production systems would replace this with provider-native tokenization when available.

Failure amplification is bounded to one adaptive batch. A 500-ticket request usually becomes 10 provider calls; if one provider call fails permanently, the API can still return the other 450 successes and 50 failures.
