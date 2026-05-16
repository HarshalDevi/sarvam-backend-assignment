# Benchmark Methodology

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

The included result file uses the mock provider for deterministic CI. For a real staging run, set:

```bash
LLM_PROVIDER=sarvam
SARVAM_API_KEY=<key>
python benchmarks/benchmark.py --iterations 30
```

The final decision should weigh throughput against failure amplification. Batch size 50 is usually best for cost and throughput; batch size 10 may be preferable for stricter p95 latency SLOs.
