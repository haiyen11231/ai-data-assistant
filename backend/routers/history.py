from __future__ import annotations
from fastapi import APIRouter, Request
from backend.models.schemas import HistoryItem, HistoryResponse
from backend.services.history_store import history_store

router = APIRouter(prefix="/history", tags=["history"])


def _session_id(request: Request) -> str:
    return request.cookies.get("session_id", "anonymous")


@router.get("/", response_model=HistoryResponse)
def list_history(request: Request) -> HistoryResponse:
    sid = _session_id(request)
    items = list(reversed(history_store.list_all(sid)))
    return HistoryResponse(success=True, items=items)


@router.post("/append", response_model=HistoryResponse)
def append_history(request: Request, item: HistoryItem) -> HistoryResponse:
    sid = _session_id(request)
    history_store.append(sid, item)
    return HistoryResponse(success=True, items=history_store.list_all(sid))
