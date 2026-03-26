from __future__ import annotations
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session as DBSession

from app.crud import prompts as prompt_crud
from app.crud import datasets as ds_crud
from app.db.session import get_db
from app.models.schemas import QueryRequest, QueryResponse
from app.services.df_cache import df_cache
from app.services.query_cache import query_cache
from app.services.session_cache import session_cache
from app.services.rate_limiter import rate_limiter, RATE_LIMITS
from app.services.ai_engine import run_query
from app.services import storage
import io, pandas as pd

router = APIRouter(prefix="/query", tags=["query"])
_OPENAI_KEY: str = os.environ.get("OPENAI_API_KEY", "")


def _session_id(request: Request) -> str:
    sid = request.cookies.get("session_id")
    if not sid:
        raise HTTPException(status_code=401, detail="No session cookie.")
    return sid


def _get_client_ip(request: Request) -> str:
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/ask", response_model=QueryResponse)
def ask(
    request: Request,
    req: QueryRequest,
    db: DBSession = Depends(get_db),
) -> QueryResponse:
    """AI query with rate limiting and result caching."""
    sid = _session_id(request)
    client_ip = _get_client_ip(request)

    if not _OPENAI_KEY:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured.")

    # Rate limiting for AI queries (more restrictive)
    allowed, rate_info = rate_limiter.check_rate_limit(
        client_ip,
        RATE_LIMITS["ai_query"]["limit"],
        RATE_LIMITS["ai_query"]["window"],
        "ai_query"
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"AI query rate limit exceeded. {rate_info.get('remaining', 0)} queries remaining. Reset in {rate_info.get('reset_time', 60)}s."
        )

    # Verify dataset ownership
    cached_meta = session_cache.get_dataset_meta(req.dataset_id)
    if cached_meta:
        meta_dict = cached_meta
    else:
        meta_row = ds_crud.get_dataset(db, req.dataset_id, sid)
        if meta_row is None:
            raise HTTPException(status_code=404, detail="Dataset not found.")
        meta_dict = {
            "filename": meta_row.filename,
            "sheet_name": meta_row.sheet_name,
            "s3_key": meta_row.s3_key,
        }

    # CACHE CHECK 
    # Try cached query result first
    cached_result = query_cache.get(req.question, req.dataset_id)
    if cached_result:
        prompt_id = str(uuid.uuid4())
        
        # Still persist to Postgres for history (with cache flag)
        prompt_crud.create_prompt(
            db,
            session_id=sid,
            dataset_id=req.dataset_id,
            prompt_id=prompt_id,
            question=req.question + " [CACHED]",  # Mark as cached in history
            answer=cached_result["answer"],
            chart_b64=cached_result.get("chart_b64"),
            table_rows=cached_result.get("table_rows"),
        )

        return QueryResponse(
            success=True,
            prompt_id=prompt_id,
            answer=cached_result["answer"],
            chart_b64=cached_result.get("chart_b64"),
            table_rows=cached_result.get("table_rows"),
            message="(cached result)"
        )

    # CACHE MISS → RUN AI QUERY 
    # Load DataFrame (Redis cache → MinIO fallback)
    df = df_cache.get(req.dataset_id)
    if df is None:
        raw = storage.download_file(meta_dict["s3_key"])
        ext = meta_dict["filename"].rsplit(".", 1)[-1].lower()
        buf = io.BytesIO(raw)
        df = pd.read_csv(buf) if ext == "csv" else pd.ExcelFile(buf).parse(meta_dict["sheet_name"])
        df_cache.set(req.dataset_id, df)

    # Run AI query
    result = run_query(df, req.question, _OPENAI_KEY)
    prompt_id = str(uuid.uuid4())

    # Cache the result
    query_cache.set(
        req.question,
        req.dataset_id,
        result["answer"],
        result.get("chart_b64"),
        result.get("table_rows"),
    )

    # Persist to Postgres
    prompt_crud.create_prompt(
        db,
        session_id=sid,
        dataset_id=req.dataset_id,
        prompt_id=prompt_id,
        question=req.question,
        answer=result["answer"],
        chart_b64=result.get("chart_b64"),
        table_rows=result.get("table_rows"),
    )

    return QueryResponse(
        success=True,
        prompt_id=prompt_id,
        answer=result["answer"],
        chart_b64=result.get("chart_b64"),
        table_rows=result.get("table_rows"),
    )
