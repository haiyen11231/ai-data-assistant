from __future__ import annotations
import uuid
import os
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.db.base import Base
from backend.db.session import engine
import backend.db.models  # noqa: F401
from backend.services import storage
from backend.services.redis_client import ping as redis_ping
from backend.services.rate_limiter import rate_limiter, RATE_LIMITS
from backend.routers import datasets, query, history, feedback

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting AI Data Assistant backend...")
    
    # Create Postgres tables
    Base.metadata.create_all(bind=engine)
    logger.info("✓ Postgres tables ready")
    
    # Ensure MinIO bucket
    storage.ensure_bucket()
    logger.info("✓ MinIO bucket ready")
    
    # Test Redis connection
    if redis_ping():
        logger.info("✓ Redis connection ready")
    else:
        logger.warning("⚠ Redis connection failed — caching disabled")
    
    yield
    
    # Shutdown
    logger.info("Shutting down backend...")


app = FastAPI(
    title="AI Data Assistant — Backend",
    version="2.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

_ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:8501,http://frontend:8501",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Rate limiting middleware
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Apply rate limits based on request path."""
    # Extract client IP
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        client_ip = x_forwarded_for.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"
    
    # Skip rate limiting for health checks and docs
    if request.url.path in ["/api/health", "/api/docs", "/api/redoc", "/api/openapi.json"]:
        return await call_next(request)
    
    # Apply appropriate rate limit based on path
    if "/query/" in request.url.path:
        limit_type = "ai_query"
    elif "/datasets/upload" in request.url.path:
        limit_type = "upload"
    else:
        limit_type = "general"
    
    config = RATE_LIMITS[limit_type]
    allowed, rate_info = rate_limiter.check_rate_limit(
        client_ip, config["limit"], config["window"], limit_type
    )
    
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "limit_type": limit_type,
                "retry_after": rate_info.get("reset_time", 60),
            }
        )
    
    response: Response = await call_next(request)
    
    # Add rate limit headers
    response.headers["X-RateLimit-Limit"] = str(rate_info.get("limit", 0))
    response.headers["X-RateLimit-Remaining"] = str(rate_info.get("remaining", 0))
    response.headers["X-RateLimit-Reset"] = str(rate_info.get("reset_time", 0))
    
    return response


# Session cookie middleware
@app.middleware("http")
async def session_cookie_middleware(request: Request, call_next):
    response: Response = await call_next(request)
    if "session_id" not in request.cookies:
        response.set_cookie(
            key="session_id",
            value=str(uuid.uuid4()),
            httponly=True,
            samesite="lax",
            max_age=86_400 * 30,   # 30 days
        )
    return response


# Routes 
PREFIX = "/api/v1"
app.include_router(datasets.router, prefix=PREFIX)
app.include_router(query.router,    prefix=PREFIX)
app.include_router(history.router,  prefix=PREFIX)
app.include_router(feedback.router, prefix=PREFIX)


@app.get("/api/health")
def health() -> dict:
    """Health check with Redis status."""
    redis_ok = redis_ping()
    return {
        "status": "ok",
        "redis": "ok" if redis_ok else "unavailable",
        "caching": "enabled" if redis_ok else "disabled",
    }
