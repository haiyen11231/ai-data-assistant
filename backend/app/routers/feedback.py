from __future__ import annotations
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.crud import feedback as fb_crud
from app.crud import prompts as prompt_crud
from app.db.session import get_db
from app.models.schemas import FeedbackRequest, FeedbackResponse

router = APIRouter(prefix="/feedback", tags=["feedback"])


def _session_id(request: Request) -> str:
    sid = request.cookies.get("session_id")
    if not sid:
        raise HTTPException(status_code=401, detail="No session cookie.")
    return sid


@router.patch("/", response_model=FeedbackResponse)
def rate(
    request: Request,
    req: FeedbackRequest,
    db: DBSession = Depends(get_db),
) -> FeedbackResponse:
    sid = _session_id(request)

    # Verify the prompt belongs to this session (access control)
    prompt = prompt_crud.get_prompt(db, req.prompt_id, sid)
    if prompt is None:
        raise HTTPException(
            status_code=404,
            detail=f"Prompt {req.prompt_id!r} not found in this session.",
        )

    fb_crud.upsert_feedback(db, prompt_id=req.prompt_id, rating=req.rating)

    return FeedbackResponse(
        success=True,
        prompt_id=req.prompt_id,
        rating=req.rating,
    )
