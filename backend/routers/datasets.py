from __future__ import annotations
from typing import Any
import pandas as pd
from fastapi import APIRouter, File, UploadFile, HTTPException, Query

from backend.models.schemas import (
    SheetMeta, UploadResponse, PreviewResponse,
)
from backend.services.parser import parse_upload
from backend.services.df_cache import df_cache

router = APIRouter(prefix="/datasets", tags=["datasets"])

@router.post("/upload", response_model=UploadResponse)
async def upload_files(
    files: list[UploadFile] = File(...),
) -> UploadResponse:
    all_sheets: list[SheetMeta] = []

    for file in files:
        sheets = await parse_upload(file)
        for s in sheets:
            df: pd.DataFrame = s.pop("df")
            df_cache.set(s["dataset_id"], df)
            all_sheets.append(
                SheetMeta(
                    **s,
                    rows=len(df),
                    cols=len(df.columns),
                    columns=df.columns.tolist(),
                )
            )

    return UploadResponse(
        success=True,
        sheets=all_sheets,
        message=f"Loaded {len(all_sheets)} sheet(s)",
    )


@router.get("/preview", response_model=PreviewResponse)
def preview(
    dataset_id: str = Query(...),
    n: int = Query(default=10, ge=1, le=500),
) -> PreviewResponse:
    df = df_cache.get(dataset_id)
    if df is None:
        raise HTTPException(
            status_code=404,
            detail=f"Dataset {dataset_id!r} not found. Re-upload the file.",
        )

    top_n = df.head(n).fillna("").astype(str)

    col_info: list[dict[str, Any]] = [
        {
            "Column": col,
            "Type": str(df[col].dtype),
            "Non-null": int(df[col].count()),
            "Nulls": int(df[col].isnull().sum()),
        }
        for col in df.columns
    ]

    return PreviewResponse(
        success=True,
        dataset_id=dataset_id,
        sheet_name="",
        filename="",
        total_rows=len(df),
        columns=df.columns.tolist(),
        rows=top_n.to_dict(orient="records"),
        col_info=col_info,
    )
