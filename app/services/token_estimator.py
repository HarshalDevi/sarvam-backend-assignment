from __future__ import annotations

import math
import re

from app.core.constants import DEFAULT_PROMPT_OVERHEAD_TOKENS, DEFAULT_RESPONSE_TOKENS_PER_TICKET

TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


class TokenEstimator:
    """Fast conservative token estimator suitable for request shaping."""

    def estimate_text_tokens(self, text: str) -> int:
        lexical_tokens = len(TOKEN_PATTERN.findall(text))
        char_tokens = math.ceil(len(text) / 4)
        return max(1, int(max(lexical_tokens * 1.15, char_tokens)))

    def estimate_prompt_tokens(self, tickets: list[str]) -> int:
        return DEFAULT_PROMPT_OVERHEAD_TOKENS + sum(self.estimate_text_tokens(ticket) + 14 for ticket in tickets)

    def estimate_completion_tokens(self, ticket_count: int) -> int:
        return ticket_count * DEFAULT_RESPONSE_TOKENS_PER_TICKET
