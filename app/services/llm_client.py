from __future__ import annotations

import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.core.constants import PERMANENT_STATUS_CODES, RETRYABLE_STATUS_CODES, TicketCategory
from app.models.internal_models import LLMClassification, TicketBatch
from app.services.retry import PermanentProviderError, RetryableError, RetryPolicy
from app.telemetry.metrics import BATCH_LATENCY, BATCHES_TOTAL
from app.utils.helpers import timer

logger = logging.getLogger(__name__)


class ProviderBatchResponse(BaseModel):
    results: list[dict[str, Any]]


class LLMProvider(ABC):
    name: str

    @abstractmethod
    async def classify_batch(self, batch: TicketBatch) -> list[LLMClassification]:
        raise NotImplementedError


class MockLLMProvider(LLMProvider):
    name = "mock"

    def __init__(self, latency_seconds: float = 0.03) -> None:
        self.latency_seconds = latency_seconds

    async def classify_batch(self, batch: TicketBatch) -> list[LLMClassification]:
        await asyncio.sleep(self.latency_seconds)
        return [self._classify(item.index, item.text) for item in batch.items]

    def _classify(self, index: int, text: str) -> LLMClassification:
        lowered = text.lower()
        category = TicketCategory.OTHER
        if any(word in lowered for word in ("battery", "screen", "laptop", "npu", "device", "overheat", "camera")):
            category = TicketCategory.HARDWARE_ISSUE
        elif any(word in lowered for word in ("crash", "install", "login", "app", "bug", "software", "driver")):
            category = TicketCategory.SOFTWARE_ISSUE
        elif any(word in lowered for word in ("hallucination", "wrong answer", "accuracy", "model", "quality")):
            category = TicketCategory.MODEL_QUALITY
        elif any(word in lowered for word in ("invoice", "billing", "refund", "charge", "payment", "subscription")):
            category = TicketCategory.BILLING
        summary = self._summary(text)
        return LLMClassification(index, category, summary, confidence=0.82)

    def _summary(self, text: str) -> str:
        normalized = re.sub(r"\s+", " ", text).strip()
        sentence = re.split(r"(?<=[.!?])\s+", normalized)[0]
        if len(sentence) > 180:
            sentence = sentence[:177].rstrip() + "..."
        return sentence if sentence.endswith((".", "!", "?")) else sentence + "."


class SarvamLLMProvider(LLMProvider):
    name = "sarvam"

    def __init__(self, settings: Settings) -> None:
        if not settings.sarvam_api_key:
            raise ValueError("SARVAM_API_KEY is required when LLM_PROVIDER=sarvam")
        self.settings = settings

    async def classify_batch(self, batch: TicketBatch) -> list[LLMClassification]:
        payload = self._build_payload(batch)
        headers = {"Authorization": f"Bearer {self.settings.sarvam_api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.post(self.settings.sarvam_api_url, headers=headers, json=payload)

        if response.status_code in RETRYABLE_STATUS_CODES:
            raise RetryableError(f"Sarvam API returned {response.status_code}", reason=str(response.status_code))
        if response.status_code in PERMANENT_STATUS_CODES:
            raise PermanentProviderError(f"Sarvam API returned {response.status_code}: {response.text[:300]}")
        response.raise_for_status()
        return self._parse_response(batch, response.json())

    def _build_payload(self, batch: TicketBatch) -> dict[str, Any]:
        tickets = [{"index": item.index, "text": item.text} for item in batch.items]
        system = (
            "Classify enterprise support tickets. Return strict JSON with key results. "
            "Each result must include ticket_index, category, summary, confidence. "
            "category must be one of hardware_issue, software_issue, model_quality, billing, other. "
            "summary must be one sentence."
        )
        return {
            "model": self.settings.sarvam_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps({"tickets": tickets}, ensure_ascii=False)},
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }

    def _parse_response(self, batch: TicketBatch, payload: dict[str, Any]) -> list[LLMClassification]:
        content = payload["choices"][0]["message"]["content"]
        try:
            parsed = ProviderBatchResponse.model_validate_json(content)
        except (KeyError, ValidationError, ValueError) as exc:
            raise RetryableError(f"malformed provider response: {exc}", reason="malformed_response") from exc

        results: list[LLMClassification] = []
        seen = {item.index for item in batch.items}
        for item in parsed.results:
            ticket_index = int(item["ticket_index"])
            if ticket_index not in seen:
                continue
            results.append(
                LLMClassification(
                    ticket_index=ticket_index,
                    category=TicketCategory(item["category"]),
                    summary=str(item["summary"]).strip(),
                    confidence=float(item.get("confidence", 0.75)),
                )
            )
        if len(results) != len(batch.items):
            raise RetryableError("provider response omitted tickets", reason="partial_provider_response")
        return results


class LLMClient:
    def __init__(self, provider: LLMProvider, retry_policy: RetryPolicy, timeout_seconds: float) -> None:
        self.provider = provider
        self.retry_policy = retry_policy
        self.timeout_seconds = timeout_seconds

    async def classify_batch(self, batch: TicketBatch) -> tuple[list[LLMClassification], int]:
        async def operation(attempt: int) -> list[LLMClassification]:
            logger.info("llm_batch_attempt", extra={"batch_id": batch.batch_id, "attempt": attempt})
            return await asyncio.wait_for(self.provider.classify_batch(batch), timeout=self.timeout_seconds)

        with timer() as elapsed_ms:
            try:
                results, retries = await self.retry_policy.run(operation)
            except Exception:
                BATCHES_TOTAL.labels(provider=self.provider.name, status="failed").inc()
                raise
            finally:
                BATCH_LATENCY.labels(provider=self.provider.name).observe(elapsed_ms() / 1000)

        BATCHES_TOTAL.labels(provider=self.provider.name, status="succeeded").inc()
        return results, retries
