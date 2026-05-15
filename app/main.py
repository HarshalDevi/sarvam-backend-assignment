from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request

from app.api.routes import router
from app.core.config import get_settings
from app.telemetry.logging_config import configure_logging
from app.telemetry.metrics import REQUEST_LATENCY

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Sarvam Backend Assignment - Ticket Inference Pipeline",
        version="1.0.0",
        description="Production-grade async ticket classification pipeline with batching, retries, telemetry, and partial failure handling.",
    )

    @app.middleware("http")
    async def request_logging(request: Request, call_next):
        start = time.perf_counter()
        response = None
        try:
            response = await call_next(request)
            return response
        finally:
            elapsed = time.perf_counter() - start
            REQUEST_LATENCY.observe(elapsed)
            logger.info(
                "http_request",
                extra={
                    "request_id": request.headers.get("x-request-id"),
                    "correlation_id": request.headers.get("x-correlation-id"),
                    "status_code": getattr(response, "status_code", None),
                    "elapsed_ms": round(elapsed * 1000, 3),
                },
            )

    app.include_router(router)
    return app


app = create_app()
