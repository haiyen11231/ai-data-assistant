from __future__ import annotations
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session as DBSession

from backend.crud import prompts as prompt_crud
from backend.crud import feedback as fb_crud
from backend.db.session import get_db
from backend.models.schemas import HistoryItem, HistoryResponse

router = APIRouter(prefix="/history", tags=["history"])


def _session_id(request: Request) -> str:
    sid = request.cookies.get("session_id")
    if not sid:
        raise HTTPException(status_code=401, detail="No session cookie.")
    return sid


def _row_to_item(row) -> HistoryItem:
    rating = row.feedback.rating if row.feedback else None
    return HistoryItem(
        prompt_id=str(row.id),
        dataset_id=str(row.dataset_id),
        filename=row.dataset.filename if row.dataset else "",
        sheet_name=row.dataset.sheet_name if row.dataset else "",
        question=row.question,
        answer=row.answer,
        chart_b64=row.chart_b64,
        table_rows=row.table_rows,
        rating=rating,
    )


@router.get("/", response_model=HistoryResponse)
def list_history(
    request: Request,
    dataset_id: str | None = None,
    db: DBSession = Depends(get_db),
) -> HistoryResponse:
    sid = _session_id(request)
    rows = prompt_crud.list_prompts(db, sid, dataset_id=dataset_id)
    return HistoryResponse(success=True, items=[_row_to_item(r) for r in rows])
