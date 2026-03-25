from __future__ import annotations
from uuid import UUID

from sqlalchemy.orm import Session

from backend.db.models import Dataset, Session as SessionModel


def get_or_create_session(db: Session, session_id: str) -> SessionModel:
    sid = UUID(session_id)
    row = db.query(SessionModel).filter(SessionModel.id == sid).first()
    if row is None:
        row = SessionModel(id=sid)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def create_dataset(
    db: Session,
    *,
    session_id: str,
    dataset_id: str,
    filename: str,
    sheet_name: str,
    s3_key: str,
    row_count: int,
    col_count: int,
    columns: list[str],
) -> Dataset:
    get_or_create_session(db, session_id)
    row = Dataset(
        id=UUID(dataset_id),
        session_id=UUID(session_id),
        filename=filename,
        sheet_name=sheet_name,
        s3_key=s3_key,
        row_count=row_count,
        col_count=col_count,
        columns=columns,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_dataset(db: Session, dataset_id: str, session_id: str) -> Dataset | None:
    return (
        db.query(Dataset)
        .filter(
            Dataset.id == UUID(dataset_id),
            Dataset.session_id == UUID(session_id),
        )
        .first()
    )


def list_datasets(db: Session, session_id: str) -> list[Dataset]:
    return (
        db.query(Dataset)
        .filter(Dataset.session_id == UUID(session_id))
        .order_by(Dataset.created_at.asc())
        .all()
    )
