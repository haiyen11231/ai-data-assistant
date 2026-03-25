from __future__ import annotations
import uuid
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from backend.db.base import Base
from backend.db.session import engine
import backend.db.models  # noqa: F401 — register models with Base.metadata
from backend.services import storage
from backend.routers import datasets, query, history, feedback


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    storage.ensure_bucket()
    yield


app = FastAPI(
    title="AI Data Assistant — Backend",
    version="2.0.0",
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


@app.middleware("http")
async def session_cookie_middleware(request: Request, call_next):
    response: Response = await call_next(request)
    if "session_id" not in request.cookies:
        response.set_cookie(
            key="session_id",
            value=str(uuid.uuid4()),
            httponly=True,
            samesite="lax",
            max_age=86_400 * 30,   # 30 days for persistence
        )
    return response


PREFIX = "/api/v1"
app.include_router(datasets.router, prefix=PREFIX)
app.include_router(query.router,    prefix=PREFIX)
app.include_router(history.router,  prefix=PREFIX)
app.include_router(feedback.router, prefix=PREFIX)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
