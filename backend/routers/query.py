from __future__ import annotations
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session as DBSession

from backend.crud import prompts as prompt_crud
from backend.crud import datasets as ds_crud
from backend.db.session import get_db
from backend.models.schemas import QueryRequest, QueryResponse
from backend.services.df_cache import df_cache
from backend.services.ai_engine import run_query
from backend.services import storage
import io, pandas as pd

router = APIRouter(prefix="/query", tags=["query"])
_OPENAI_KEY: str = os.environ.get("OPENAI_API_KEY", "")


def _session_id(request: Request) -> str:
    sid = request.cookies.get("session_id")
    if not sid:
        raise HTTPException(status_code=401, detail="No session cookie.")
    return sid


@router.post("/ask", response_model=QueryResponse)
def ask(
    request: Request,
    req: QueryRequest,
    db: DBSession = Depends(get_db),
) -> QueryResponse:
    sid = _session_id(request)

    if not _OPENAI_KEY:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured.")

    # Verify dataset ownership
    meta = ds_crud.get_dataset(db, req.dataset_id, sid)
    if meta is None:
        raise HTTPException(status_code=404, detail="Dataset not found.")

    # Load DataFrame (cache → S3 fallback)
    df = df_cache.get(req.dataset_id)
    if df is None:
        raw = storage.download_file(meta.s3_key)
        ext = meta.filename.rsplit(".", 1)[-1].lower()
        buf = io.BytesIO(raw)
        df = pd.read_csv(buf) if ext == "csv" else pd.ExcelFile(buf).parse(meta.sheet_name)
        df_cache.set(req.dataset_id, df)

    result = run_query(df, req.question, _OPENAI_KEY)
    prompt_id = str(uuid.uuid4())

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
