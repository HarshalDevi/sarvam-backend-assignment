# Benchmark Results

Benchmarks use the mock LLM provider so the suite is deterministic and can run in CI without spending API credits. The goal is to measure the pipeline effects of batching, async scheduling, token estimation, and partial-failure accounting. Real Sarvam API benchmarks should be run with `LLM_PROVIDER=sarvam` in a staging account and compared against this baseline.

Cost values are illustrative estimates based on configured prompt/completion token prices. They are intended to compare batch sizes under the same assumptions, not to represent exact provider billing.

Mock baseline command:

```bash
python benchmarks/benchmark.py --iterations 30
```

Live Sarvam command when an API key is available:

```bash
LLM_PROVIDER=sarvam SARVAM_API_KEY=<key> python benchmarks/benchmark.py --iterations 10 --provider sarvam
```

Live Sarvam API sanity checks through `POST /tickets/process`:

| Batch size | status | success_count | failure_count | elapsed_ms | live tickets/sec | Notes |
|---:|---|---:|---:|---:|---:|---|
| 1 | succeeded | 1 | 0 | 9730.873 | 0.10 | Single-ticket live provider check |
| 10 | succeeded | 10 | 0 | 111499.662 | 0.09 | Larger structured JSON response |
| 50 | succeeded | 50 | 0 | 313183.973 | 0.16 | Required live large-batch sanity check |

Verified local mock benchmark table:

| Batch size | p50 latency ms | p95 latency ms | tickets/sec | prompt tokens | completion tokens | cost USD | failure rate |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 31.22 | 35.30 | 31.89 | 6,420 | 1,440 | 0.00183 | 0.00% |
| 10 | 30.98 | 32.47 | 322.04 | 14,820 | 14,400 | 0.01086 | 0.00% |
| 50 | 30.99 | 32.36 | 1,609.60 | 52,500 | 72,000 | 0.05107 | 0.00% |

## Benchmark Conclusion

For the local mock baseline, the optimal batch size is 50 when judged by throughput and cost per ticket. The fixed prompt overhead is amortized across more tickets, and provider latency is paid once per 50 tickets instead of once per ticket. This conclusion should be validated against live Sarvam latency and rate-limit headroom before using it as the production operating point.

The production default still treats 50 as a ceiling, not a constant. Very long tickets are split earlier by token budget. This avoids context-window overflow and reduces failure amplification. If a provider batch permanently fails, the processor splits the batch and retries smaller halves until it recovers good tickets or isolates the bad ticket.

## Tradeoffs

Batch size 1 has the lowest failure amplification and simplest retry behavior, but it wastes prompt overhead and provider round trips. Batch size 10 is a good latency-sensitive operating point. Batch size 50 is best for queue draining, overnight jobs, and high-throughput ingestion, as long as p95 latency and retry amplification remain inside SLO.
