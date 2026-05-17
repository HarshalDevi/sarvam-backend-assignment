# Benchmark Analysis

The benchmark suite measures:

- end-to-end latency
- throughput in tickets per second
- estimated prompt tokens
- estimated completion tokens
- estimated cost
- failure rate

Cost estimates are illustrative and derived from configured prompt/completion token prices in the service settings. They are used for comparative batch-size analysis, not as a claim of exact Sarvam billing.

Batch sizes tested:

- 1
- 10
- 50

The included result file uses the mock provider for deterministic local testing. The benchmark suite can also call Sarvam directly when a valid API key is available:

```bash
LLM_PROVIDER=sarvam SARVAM_API_KEY=<key> python benchmarks/benchmark.py --iterations 10 --provider sarvam
```

The submitted benchmark table is kept as a mock-provider baseline because it is reproducible and safe to run in CI. I also ran live Sarvam API sanity checks through the same `/tickets/process` endpoint for batch sizes 1, 10, and 50. The live checks all succeeded, but latency was much higher than the local mock baseline: about 0.10 tickets/sec for batch 1, 0.09 tickets/sec for batch 10, and 0.16 tickets/sec for batch 50. Final batch-size tuning should still be validated against Sarvam latency and rate-limit headroom in staging.

The final decision should weigh throughput against failure amplification. Batch size 50 is best in the local baseline for throughput and cost, and the live API accepted a 50-ticket request. With a real provider, batch size 10 may still be better when p95 latency is the main concern because live latency is much higher than mock latency.
