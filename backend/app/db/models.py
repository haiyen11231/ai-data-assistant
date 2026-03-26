from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime,
    ForeignKey, Integer, SmallInteger, String, Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
import uuid

from app.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Session(Base):
    __tablename__ = "sessions"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    last_seen  = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    datasets = relationship("Dataset", back_populates="session", cascade="all, delete-orphan")
    prompts  = relationship("Prompt",  back_populates="session", cascade="all, delete-orphan")


class Dataset(Base):
    __tablename__ = "datasets"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id  = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    filename    = Column(String(512), nullable=False)
    sheet_name  = Column(String(255), nullable=False)
    s3_key      = Column(String(1024), nullable=False)       # bucket-relative path
    row_count   = Column(BigInteger, nullable=False, default=0)
    col_count   = Column(Integer, nullable=False, default=0)
    columns     = Column(JSONB, nullable=False, default=list) # ["col1", "col2", ...]
    created_at  = Column(DateTime(timezone=True), default=_now, nullable=False)

    session = relationship("Session", back_populates="datasets")
    prompts = relationship("Prompt", back_populates="dataset")


class Prompt(Base):
    __tablename__ = "prompts"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id  = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset_id  = Column(UUID(as_uuid=True), ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True, index=True)
    question    = Column(Text, nullable=False)
    answer      = Column(Text, nullable=False)
    chart_b64   = Column(Text, nullable=True)
    table_rows  = Column(JSONB, nullable=True)   # list[dict] or null
    created_at  = Column(DateTime(timezone=True), default=_now, nullable=False, index=True)

    session  = relationship("Session", back_populates="prompts")
    dataset  = relationship("Dataset", back_populates="prompts")
    feedback = relationship("Feedback", back_populates="prompt", uselist=False, cascade="all, delete-orphan")


class Feedback(Base):
    __tablename__ = "feedback"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prompt_id  = Column(UUID(as_uuid=True), ForeignKey("prompts.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    rating     = Column(SmallInteger, nullable=False)   # 1 or -1
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    prompt = relationship("Prompt", back_populates="feedback")
