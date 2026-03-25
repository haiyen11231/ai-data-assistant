from __future__ import annotations
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.db.models import Feedback


def upsert_feedback(
    db: Session,
    *,
    prompt_id: str,
    rating: int,
) -> Feedback:
    stmt = (
        pg_insert(Feedback)
        .values(
            prompt_id=UUID(prompt_id),
            rating=rating,
        )
        .on_conflict_do_update(
            index_elements=["prompt_id"],
            set_={
                "rating": rating,
                "updated_at": Feedback.updated_at,
            },
        )
        .returning(Feedback)
    )
    result = db.execute(stmt)
    db.commit()
    row = result.scalars().first()
    return row


def get_rating(db: Session, prompt_id: str) -> int | None:
    row = db.query(Feedback).filter(
        Feedback.prompt_id == UUID(prompt_id)
    ).first()
    return row.rating if row else None
