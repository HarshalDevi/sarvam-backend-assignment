from __future__ import annotations

from enum import StrEnum


class TicketCategory(StrEnum):
    HARDWARE_ISSUE = "hardware_issue"
    SOFTWARE_ISSUE = "software_issue"
    MODEL_QUALITY = "model_quality"
    BILLING = "billing"
    OTHER = "other"


RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
PERMANENT_STATUS_CODES = {400, 401, 403, 404, 422}

DEFAULT_PROMPT_OVERHEAD_TOKENS = 180
DEFAULT_RESPONSE_TOKENS_PER_TICKET = 48
SECONDS_PER_TICKET_BASELINE = 0.09
