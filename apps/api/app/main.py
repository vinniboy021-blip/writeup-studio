# SPDX-License-Identifier: MIT
"""Application composition, standardized errors and operational endpoints."""

import json
import logging
import secrets
import time
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.db import Base as Base
from app.modules.evidence.routes import router as evidence_router
from app.modules.identity.routes import router as identity_router
from app.modules.integrations.routes import router as integrations_router
from app.modules.studio.routes import router as studio_router
from app.modules.workspace.routes import router as workspace_router
from app.security import DB, correlation_id


logger = logging.getLogger("ctf.api")
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(message)s")
requests_total = Counter("ctf_api_requests_total", "API requests", ["method", "route", "status"])
request_duration = Histogram("ctf_api_request_seconds", "API request latency", ["method", "route"])


@asynccontextmanager
async def lifespan(app):
    logger.info(json.dumps({"event": "api.started", "environment": settings.environment}))
    yield
    logger.info(json.dumps({"event": "api.stopped"}))


app = FastAPI(
    title="CTF Writeup Studio API",
    version="1.0.0",
    license_info={"name": "MIT"},
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    started = time.monotonic()
    supplied = request.headers.get("X-Request-ID", "")
    request_id = supplied if len(supplied) <= 64 and supplied.isalnum() else secrets.token_hex(16)
    request.state.request_id = request_id
    context_token = correlation_id.set(request_id)
    try:
        response = await call_next(request)
        response.headers.update(
            {
                "X-Request-ID": request_id,
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "same-origin",
                "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
                "Cache-Control": response.headers.get("Cache-Control", "no-store"),
            }
        )
        if settings.environment == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        route = getattr(request.scope.get("route"), "path", "unmatched")
        elapsed = time.monotonic() - started
        if settings.metrics_enabled:
            requests_total.labels(request.method, route, str(response.status_code)).inc()
            request_duration.labels(request.method, route).observe(elapsed)
        logger.info(
            json.dumps(
                {
                    "event": "http.request",
                    "request_id": request_id,
                    "method": request.method,
                    "route": route,
                    "status": response.status_code,
                    "duration_ms": round(elapsed * 1000, 2),
                }
            )
        )
        return response
    finally:
        correlation_id.reset(context_token)


def error_response(request: Request, status: int, detail, headers=None):
    code = detail.get("code", "http_error") if isinstance(detail, dict) else "http_error"
    message = detail.get("message", "Requisição não processada") if isinstance(detail, dict) else str(detail)
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": detail if isinstance(detail, (dict, list)) else None,
            },
            "detail": detail,
            "request_id": getattr(request.state, "request_id", None),
        },
        headers=headers,
    )


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    return error_response(request, exc.status_code, exc.detail, exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    details = [{"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]} for error in exc.errors()]
    return error_response(request, 422, {"code": "validation_error", "message": "Dados inválidos", "errors": details})


@app.exception_handler(IntegrityError)
async def integrity_error(request: Request, exc: IntegrityError):
    return error_response(
        request, 409, {"code": "integrity_conflict", "message": "Dados relacionados ou duplicados inválidos"}
    )


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    logger.error(
        json.dumps(
            {
                "event": "http.failure",
                "request_id": getattr(request.state, "request_id", None),
                "exception_type": type(exc).__name__,
            }
        )
    )
    return error_response(request, 500, "Falha interna; consulte o identificador da requisição")


api = APIRouter()


@api.get("/health", tags=["Operação"])
def health():
    return {"status": "ok"}


@api.get("/ready", tags=["Operação"])
@api.get("/readiness", tags=["Operação"], include_in_schema=False)
def readiness(db: DB):
    try:
        db.execute(text("SELECT 1"))
        if not inspect(db.get_bind()).has_table("sessions"):
            raise HTTPException(503, "Migrations pendentes")
        if settings.queue_enabled or settings.rate_limit_backend == "redis":
            import redis

            redis.Redis.from_url(settings.redis_url, socket_timeout=2, socket_connect_timeout=2).ping()
        if settings.storage_backend == "s3":
            import boto3
            from botocore.config import Config

            client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint_url or None,
                aws_access_key_id=settings.s3_access_key or None,
                aws_secret_access_key=settings.s3_secret_key or None,
                region_name=settings.s3_region,
                config=Config(connect_timeout=2, read_timeout=2, retries={"max_attempts": 0}),
            )
            client.head_bucket(Bucket=settings.s3_bucket)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "Dependência indisponível") from exc
    return {"status": "ready"}


@api.get("/metrics", tags=["Operação"], include_in_schema=False)
def metrics(request: Request):
    if not settings.metrics_enabled:
        raise HTTPException(404, "Métricas desabilitadas")
    if settings.metrics_token and not secrets.compare_digest(
        request.headers.get("Authorization", ""), "Bearer " + settings.metrics_token
    ):
        raise HTTPException(401, "Token de métricas necessário")
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


api.include_router(identity_router)
api.include_router(workspace_router)
api.include_router(studio_router)
api.include_router(evidence_router)
api.include_router(integrations_router)
app.include_router(api, prefix="/api/v1")
