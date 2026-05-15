from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ProcessTicketsRequest(BaseModel):
    tickets: list[str] = Field(..., min_length=1, max_length=500)
    correlation_id: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("tickets")
    @classmethod
    def validate_ticket_text(cls, tickets: list[str]) -> list[str]:
        cleaned: list[str] = []
        for idx, ticket in enumerate(tickets):
            text = ticket.strip()
            if not text:
                raise ValueError(f"ticket at index {idx} is empty")
            if len(text) > 12_000:
                raise ValueError(f"ticket at index {idx} exceeds 12000 characters")
            cleaned.append(text)
        return cleaned
