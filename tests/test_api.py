from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_process_tickets_endpoint() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/tickets/process",
            json={"tickets": ["Laptop battery drains quickly", "Need refund for duplicate charge"]},
            headers={"x-request-id": "req_fixed"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["request_id"] == "req_fixed"
    assert payload["success_count"] == 2
    assert payload["failure_count"] == 0
    assert payload["estimate"]["estimated_batch_count"] >= 1


@pytest.mark.asyncio
async def test_process_tickets_rejects_empty_ticket() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/tickets/process", json={"tickets": [""]})

    assert response.status_code == 422
