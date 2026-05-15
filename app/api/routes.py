from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from app.core.dependencies import get_processor
from app.models.request_models import ProcessTicketsRequest
from app.models.response_models import ProcessTicketsResponse
from app.services.processing import TicketProcessor
from app.telemetry.tracing import correlation_id_var, request_id_var
from app.utils.helpers import new_request_id

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.post("/tickets/process", response_model=ProcessTicketsResponse, status_code=status.HTTP_200_OK)
async def process_tickets(
    payload: ProcessTicketsRequest,
    request: Request,
    processor: TicketProcessor = Depends(get_processor),
) -> ProcessTicketsResponse:
    request_id = request.headers.get("x-request-id") or new_request_id()
    correlation_id = payload.correlation_id or request.headers.get("x-correlation-id")
    request_id_var.set(request_id)
    correlation_id_var.set(correlation_id)
    try:
        return await processor.process(payload.tickets, request_id=request_id, correlation_id=correlation_id)
    except OverflowError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
