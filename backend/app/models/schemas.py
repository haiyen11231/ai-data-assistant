from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field


# Upload dataset
class SheetMeta(BaseModel):
    dataset_id: str
    filename: str
    sheet_name: str
    rows: int
    cols: int
    columns: list[str]


class UploadResponse(BaseModel):
    success: bool
    sheets: list[SheetMeta]
    message: str = ""


# Preview dataset (top-N rows)
class PreviewRequest(BaseModel):
    dataset_id: str
    n: int = Field(default=10, ge=1, le=500)


class PreviewResponse(BaseModel):
    success: bool
    dataset_id: str
    sheet_name: str
    filename: str
    total_rows: int
    columns: list[str]
    rows: list[dict[str, Any]]          # top-N rows as JSON records
    col_info: list[dict[str, Any]]      # [{Column, Type, Non-null, Nulls}]
    message: str = ""


# Query AI assistant
class QueryRequest(BaseModel):
    dataset_id: str
    question: str = Field(..., min_length=1, max_length=2000)


class QueryResponse(BaseModel):
    success: bool
    prompt_id: str
    answer: str
    chart_b64: Optional[str] = None  
    table_rows: Optional[list[dict[str, Any]]] = None
    message: str = ""


# Prompt history
class HistoryItem(BaseModel):
    prompt_id: str
    dataset_id: str
    filename: str
    sheet_name: str
    question: str
    answer: str
    chart_b64: Optional[str] = None
    table_rows: Optional[list[dict[str, Any]]] = None
    rating: Optional[int] = None        # 1 = 👍, -1 = 👎, None = unrated


class HistoryResponse(BaseModel):
    success: bool
    items: list[HistoryItem]


# Feedback
class FeedbackRequest(BaseModel):
    prompt_id: str
    rating: int = Field(..., ge=-1, le=1)   # -1, 0 (reset), or 1


class FeedbackResponse(BaseModel):
    success: bool
    prompt_id: str
    rating: int
    message: str = ""
