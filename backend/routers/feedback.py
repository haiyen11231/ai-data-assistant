from __future__ import annotations
from fastapi import APIRouter, Request, HTTPException
from backend.models.schemas import FeedbackRequest, FeedbackResponse
from backend.services.history_store import history_store

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.patch("/", response_model=FeedbackResponse)
def rate(request: Request, req: FeedbackRequest) -> FeedbackResponse:
    sid = request.cookies.get("session_id", "anonymous")
    updated = history_store.apply_feedback(sid, req)
    if updated is None:
        raise HTTPException(
            status_code=404,
            detail=f"Prompt {req.prompt_id!r} not found in this session.",
        )
    return FeedbackResponse(
        success=True,
        prompt_id=updated.prompt_id,
        rating=updated.rating or 0,
    )
