# Benchmark Results

Benchmarks use the mock LLM provider so the suite is deterministic and can run in CI without spending API credits. The goal is to measure the pipeline effects of batching, async scheduling, token estimation, and partial-failure accounting. Real Sarvam API benchmarks should be run with `LLM_PROVIDER=sarvam` in a staging account and compared against this baseline.

Command:

```bash
python benchmarks/benchmark.py --iterations 30
```

Representative local result:

| Batch size | p50 latency ms | p95 latency ms | tickets/sec | prompt tokens | completion tokens | cost USD | failure rate |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 26.2 | 31.0 | 37.8 | 6,270 | 1,440 | 0.0018 | 0.00% |
| 10 | 27.4 | 34.6 | 356.5 | 11,520 | 14,400 | 0.0104 | 0.00% |
| 50 | 31.8 | 41.2 | 1,487.0 | 32,760 | 72,000 | 0.0481 | 0.00% |

## Conclusion

For this workload the optimal batch size is 50 when judged by throughput and cost per ticket. The fixed prompt overhead is amortized across more tickets, and provider latency is paid once per 50 tickets instead of once per ticket.

The production default still treats 50 as a ceiling, not a constant. Very long tickets are split earlier by token budget. This avoids context-window overflow and reduces failure amplification: if a provider call permanently fails, the failure blast radius is one adaptive batch rather than the entire 500-ticket request.

## Tradeoffs

Batch size 1 has the lowest failure amplification and simplest retry behavior, but it wastes prompt overhead and provider round trips. Batch size 10 is a good latency-sensitive operating point. Batch size 50 is best for queue draining, overnight jobs, and high-throughput ingestion, as long as p95 latency and retry amplification remain inside SLO.
