from __future__ import annotations

from app.core.config import Settings
from app.core.constants import DEFAULT_PROMPT_OVERHEAD_TOKENS, DEFAULT_RESPONSE_TOKENS_PER_TICKET
from app.models.internal_models import TicketBatch, TicketItem
from app.services.token_estimator import TokenEstimator
from app.utils.helpers import new_batch_id


class AdaptiveBatcher:
    def __init__(self, settings: Settings, token_estimator: TokenEstimator) -> None:
        self.settings = settings
        self.token_estimator = token_estimator

    def create_batches(self, tickets: list[str]) -> list[TicketBatch]:
        items = [
            TicketItem(index=i, text=text, estimated_tokens=self.token_estimator.estimate_text_tokens(text))
            for i, text in enumerate(tickets)
        ]

        batches: list[TicketBatch] = []
        current: list[TicketItem] = []
        prompt_tokens = DEFAULT_PROMPT_OVERHEAD_TOKENS

        for item in items:
            item_prompt_cost = item.estimated_tokens + 14
            projected_prompt = prompt_tokens + item_prompt_cost
            projected_completion = (len(current) + 1) * DEFAULT_RESPONSE_TOKENS_PER_TICKET
            projected_total = projected_prompt + projected_completion

            too_many_items = len(current) >= self.settings.max_tickets_per_llm_batch
            context_overflow = projected_total > self.settings.context_window_tokens
            prompt_overflow = projected_prompt > self.settings.max_prompt_tokens_per_batch

            if current and (too_many_items or context_overflow or prompt_overflow):
                batches.append(self._build_batch(current, prompt_tokens))
                current = []
                prompt_tokens = DEFAULT_PROMPT_OVERHEAD_TOKENS

            if item_prompt_cost + DEFAULT_PROMPT_OVERHEAD_TOKENS > self.settings.max_prompt_tokens_per_batch:
                batches.append(
                    self._build_batch(
                        [item],
                        min(
                            item_prompt_cost + DEFAULT_PROMPT_OVERHEAD_TOKENS,
                            self.settings.max_prompt_tokens_per_batch,
                        ),
                    )
                )
                continue

            current.append(item)
            prompt_tokens += item_prompt_cost

        if current:
            batches.append(self._build_batch(current, prompt_tokens))

        return batches

    def estimate_batch_count(self, tickets: list[str]) -> int:
        return len(self.create_batches(tickets))

    def _build_batch(self, items: list[TicketItem], prompt_tokens: int) -> TicketBatch:
        return TicketBatch(
            batch_id=new_batch_id(),
            items=list(items),
            prompt_tokens=prompt_tokens,
            estimated_completion_tokens=len(items) * DEFAULT_RESPONSE_TOKENS_PER_TICKET,
        )
