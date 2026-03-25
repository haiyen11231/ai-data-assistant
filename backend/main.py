from __future__ import annotations
import uuid
import os

from dotenv import load_dotenv
load_dotenv() 

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import datasets, query, history, feedback

app = FastAPI(
    title="AI Data Assistant — Backend",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS
# Allow requests only from the Streamlit container / localhost dev server.
_ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:8501,http://streamlit:8501",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,       # needed for cookie-based sessions
    allow_methods=["*"],
    allow_headers=["*"],
)

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
            # secure=True,  # uncomment when HTTPS 
            max_age=86_400,   # 24 hours
        )
    return response

# Routers 
PREFIX = "/api/v1"

app.include_router(datasets.router, prefix=PREFIX)
app.include_router(query.router,    prefix=PREFIX)
app.include_router(history.router,  prefix=PREFIX)
app.include_router(feedback.router, prefix=PREFIX)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
