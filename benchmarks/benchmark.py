from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import Settings
from app.services.batching import AdaptiveBatcher
from app.services.llm_client import LLMClient, MockLLMProvider, SarvamLLMProvider
from app.services.processing import TicketProcessor
from app.services.queue_manager import QueueManager
from app.services.retry import RetryPolicy
from app.services.token_estimator import TokenEstimator


SAMPLE_TICKETS = [
    "Laptop battery drains from 100% to 20% in one hour after the firmware update.",
    "The app crashes when I upload logs from the enterprise console.",
    "The model gave a wrong answer for policy lookup and cited a non-existent clause.",
    "Please refund the duplicate subscription charge on our latest invoice.",
    "User cannot log in after SSO configuration changed.",
]


@dataclass(frozen=True)
class BenchmarkResult:
    batch_size: int
    latency_ms_p50: float
    latency_ms_p95: float
    throughput_tickets_per_second: float
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    failure_rate: float


def build_processor(max_batch_size: int, provider_name: str) -> TicketProcessor:
    settings = Settings(max_tickets_per_llm_batch=max_batch_size, provider_concurrency=8, llm_provider=provider_name)
    estimator = TokenEstimator()
    provider = SarvamLLMProvider(settings) if provider_name == "sarvam" else MockLLMProvider(latency_seconds=0.025)
    return TicketProcessor(
        settings=settings,
        batcher=AdaptiveBatcher(settings, estimator),
        llm_client=LLMClient(provider, RetryPolicy(base_delay_seconds=0.001), settings.request_timeout_seconds),
        queue_manager=QueueManager(10_000, settings.nominal_tickets_per_second),
    )


async def run_case(batch_size: int, iterations: int, provider_name: str) -> BenchmarkResult:
    processor = build_processor(batch_size, provider_name)
    latencies: list[float] = []
    total_tickets = 0
    failures = 0
    prompt_tokens = 0
    completion_tokens = 0
    started = time.perf_counter()
    tickets = [SAMPLE_TICKETS[i % len(SAMPLE_TICKETS)] for i in range(batch_size)]

    for i in range(iterations):
        request_started = time.perf_counter()
        response = await processor.process(tickets, request_id=f"bench_{batch_size}_{i}", correlation_id="benchmark")
        latencies.append((time.perf_counter() - request_started) * 1000)
        total_tickets += len(tickets)
        failures += response.failure_count
        prompt_tokens += response.estimate.estimated_prompt_tokens
        completion_tokens += response.estimate.estimated_completion_tokens

    elapsed = time.perf_counter() - started
    settings = Settings()
    cost = (prompt_tokens / 1000 * settings.prompt_token_price_per_1k) + (
        completion_tokens / 1000 * settings.completion_token_price_per_1k
    )
    return BenchmarkResult(
        batch_size=batch_size,
        latency_ms_p50=statistics.median(latencies),
        latency_ms_p95=statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies),
        throughput_tickets_per_second=total_tickets / elapsed,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        estimated_cost_usd=cost,
        failure_rate=failures / max(1, total_tickets),
    )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--provider", choices=["mock", "sarvam"], default="mock")
    args = parser.parse_args()
    results = [await run_case(size, args.iterations, args.provider) for size in (1, 10, 50)]
    print("| Batch size | p50 latency ms | p95 latency ms | tickets/sec | prompt tokens | completion tokens | cost USD | failure rate |")
    print("|---:|---:|---:|---:|---:|---:|---:|---:|")
    for result in results:
        print(
            f"| {result.batch_size} | {result.latency_ms_p50:.2f} | {result.latency_ms_p95:.2f} | "
            f"{result.throughput_tickets_per_second:.2f} | {result.prompt_tokens} | "
            f"{result.completion_tokens} | {result.estimated_cost_usd:.5f} | {result.failure_rate:.2%} |"
        )


if __name__ == "__main__":
    asyncio.run(main())
