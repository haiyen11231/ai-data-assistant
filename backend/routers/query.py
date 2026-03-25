from __future__ import annotations
import os
import uuid

from fastapi import APIRouter, HTTPException
from backend.models.schemas import QueryRequest, QueryResponse
from backend.services.df_cache import df_cache
from backend.services.ai_engine import run_query

router = APIRouter(prefix="/query", tags=["query"])

_OPENAI_KEY: str = os.environ.get("OPENAI_API_KEY", "")


@router.post("/ask", response_model=QueryResponse)
def ask(req: QueryRequest) -> QueryResponse:
    if not _OPENAI_KEY:
        raise HTTPException(
            status_code=503,
            detail="AI features unavailable: OPENAI_API_KEY not configured.",
        )

    df = df_cache.get(req.dataset_id)
    if df is None:
        raise HTTPException(
            status_code=404,
            detail=f"Dataset {req.dataset_id!r} not found. Re-upload the file.",
        )

    result = run_query(df, req.question, _OPENAI_KEY)

    return QueryResponse(
        success=True,
        prompt_id=str(uuid.uuid4()),
        answer=result["answer"],
        chart_b64=result.get("chart_b64"),
        table_rows=result.get("table_rows"),
    )
