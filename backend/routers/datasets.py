"""
Upload flow:
  1. Validate file (parser.py — unchanged)
  2. Parse into DataFrames (parser.py — unchanged)
  3. Upload raw bytes to S3 (storage.py)
  4. Write metadata row to Postgres (crud/datasets.py)
  5. Cache DataFrame in LRU cache (df_cache.py)
  6. Return SheetMeta to frontend

The cache-miss → S3 reload means the app survives backend restarts
without losing access to previously uploaded data.
"""

from __future__ import annotations
import io
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy.orm import Session as DBSession

from backend.crud import datasets as ds_crud
from backend.db.session import get_db
from backend.models.schemas import PreviewResponse, SheetMeta, UploadResponse
from backend.services.df_cache import df_cache
from backend.services.parser import parse_upload
from backend.services import storage

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _session_id(request: Request) -> str:
    sid = request.cookies.get("session_id")
    if not sid:
        raise HTTPException(status_code=401, detail="No session cookie found.")
    return sid


@router.post("/upload", response_model=UploadResponse)
async def upload_files(
    request: Request,
    files: list[UploadFile] = File(...),
    db: DBSession = Depends(get_db),
) -> UploadResponse:
    """
    Upload files → S3 + Postgres + LRU cache.
    """
    sid = _session_id(request)
    all_sheets: list[SheetMeta] = []

    for file in files:
        # Read raw bytes once — needed both for S3 and for parsing
        raw_bytes = await file.read()
        file.file = io.BytesIO(raw_bytes)   # reset so parse_upload can read again

        sheets = await parse_upload(file)

        for s in sheets:
            df: pd.DataFrame = s.pop("df")
            dataset_id: str = s["dataset_id"]
            filename: str = s["filename"]

            # 1. Store raw file in S3 (one object per sheet for Excel;
            #    same bytes for CSV's single sheet)
            s3_key = storage.upload_file(
                file_bytes=raw_bytes,
                session_id=sid,
                dataset_id=dataset_id,
                filename=filename,
            )

            # 2. Persist metadata to Postgres
            ds_crud.create_dataset(
                db,
                session_id=sid,
                dataset_id=dataset_id,
                filename=filename,
                sheet_name=s["sheet_name"],
                s3_key=s3_key,
                row_count=len(df),
                col_count=len(df.columns),
                columns=df.columns.tolist(),
            )

            # 3. Warm the LRU cache
            df_cache.set(dataset_id, df)

            all_sheets.append(
                SheetMeta(
                    dataset_id=dataset_id,
                    filename=filename,
                    sheet_name=s["sheet_name"],
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


@router.get("/list", response_model=UploadResponse)
def list_datasets(
    request: Request,
    db: DBSession = Depends(get_db),
) -> UploadResponse:
    """
    Return all datasets for this session.
    Called by the frontend on page load to restore file_meta
    without re-uploading (history survives refresh).
    """
    sid = _session_id(request)
    rows = ds_crud.list_datasets(db, sid)
    sheets = [
        SheetMeta(
            dataset_id=str(row.id),
            filename=row.filename,
            sheet_name=row.sheet_name,
            rows=row.row_count,
            cols=row.col_count,
            columns=row.columns,
        )
        for row in rows
    ]
    return UploadResponse(success=True, sheets=sheets)


@router.get("/preview", response_model=PreviewResponse)
def preview(
    request: Request,
    dataset_id: str = Query(...),
    n: int = Query(default=10, ge=1, le=500),
    db: DBSession = Depends(get_db),
) -> PreviewResponse:
    """
    Return top-N rows. Loads from LRU cache; falls back to S3 on miss.
    """
    sid = _session_id(request)

    # Verify ownership via Postgres
    meta = ds_crud.get_dataset(db, dataset_id, sid)
    if meta is None:
        raise HTTPException(
            status_code=404,
            detail=f"Dataset {dataset_id!r} not found for this session.",
        )

    # Try cache first
    df = df_cache.get(dataset_id)

    if df is None:
        # Cache miss — reload from S3
        try:
            raw_bytes = storage.download_file(meta.s3_key)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Could not retrieve file from storage: {exc}",
            )
        buf = io.BytesIO(raw_bytes)
        ext = meta.filename.rsplit(".", 1)[-1].lower()
        if ext == "csv":
            df = pd.read_csv(buf)
        else:
            xl = pd.ExcelFile(buf, engine="openpyxl" if ext == "xlsx" else "xlrd")
            df = xl.parse(meta.sheet_name)
        df_cache.set(dataset_id, df)

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
        sheet_name=meta.sheet_name,
        filename=meta.filename,
        total_rows=len(df),
        columns=df.columns.tolist(),
        rows=top_n.to_dict(orient="records"),
        col_info=col_info,
    )
