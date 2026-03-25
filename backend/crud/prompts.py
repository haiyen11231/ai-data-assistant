from __future__ import annotations
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from backend.db.models import Dataset, Prompt, Session as SessionModel
from backend.crud.datasets import get_or_create_session


def create_prompt(
    db: Session,
    *,
    session_id: str,
    dataset_id: str,
    prompt_id: str,
    question: str,
    answer: str,
    chart_b64: str | None = None,
    table_rows: list[dict] | None = None,
) -> Prompt:
    get_or_create_session(db, session_id)
    row = Prompt(
        id=UUID(prompt_id),
        session_id=UUID(session_id),
        dataset_id=UUID(dataset_id),
        question=question,
        answer=answer,
        chart_b64=chart_b64,
        table_rows=table_rows,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_prompts(
    db: Session,
    session_id: str,
    dataset_id: str | None = None,
    limit: int = 200,
) -> list[Prompt]:
    q = (
        db.query(Prompt)
        .options(
            joinedload(Prompt.dataset),
            joinedload(Prompt.feedback),
        )
        .filter(Prompt.session_id == UUID(session_id))
    )
    if dataset_id:
        q = q.filter(Prompt.dataset_id == UUID(dataset_id))
    return q.order_by(Prompt.created_at.desc()).limit(limit).all()


def get_prompt(db: Session, prompt_id: str, session_id: str) -> Prompt | None:
    return (
        db.query(Prompt)
        .options(joinedload(Prompt.feedback))
        .filter(
            Prompt.id == UUID(prompt_id),
            Prompt.session_id == UUID(session_id),
        )
        .first()
    )
