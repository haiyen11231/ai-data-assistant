from __future__ import annotations
import io
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy.orm import Session as DBSession

from app.crud import datasets as ds_crud
from app.db.session import get_db
from app.models.schemas import PreviewResponse, SheetMeta, UploadResponse
from app.services.df_cache import df_cache
from app.services.session_cache import session_cache
from app.services.rate_limiter import rate_limiter, RATE_LIMITS
from app.services.parser import parse_upload
from app.services import storage

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _session_id(request: Request) -> str:
    sid = request.cookies.get("session_id")
    if not sid:
        raise HTTPException(status_code=401, detail="No session cookie found.")
    return sid


def _get_client_ip(request: Request) -> str:
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    x_real_ip = request.headers.get("X-Real-IP")
    if x_real_ip:
        return x_real_ip
    return request.client.host if request.client else "unknown"


@router.post("/upload", response_model=UploadResponse)
async def upload_files(
    request: Request,
    files: list[UploadFile] = File(...),
    db: DBSession = Depends(get_db),
) -> UploadResponse:
    sid = _session_id(request)
    client_ip = _get_client_ip(request)

    # Rate limiting
    allowed, rate_info = rate_limiter.check_rate_limit(
        client_ip, 
        RATE_LIMITS["upload"]["limit"], 
        RATE_LIMITS["upload"]["window"], 
        "upload"
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Upload rate limit exceeded. Try again in {rate_info.get('reset_time', 60)} seconds."
        )

    all_sheets: list[SheetMeta] = []
    cache_metas: list[dict[str, Any]] = []

    for file in files:
        raw_bytes = await file.read()
        file.file = io.BytesIO(raw_bytes)

        sheets = await parse_upload(file)

        for s in sheets:
            df: pd.DataFrame = s.pop("df")
            dataset_id: str = s["dataset_id"]
            filename: str = s["filename"]

            # Check for existing dataset with same filename (re-upload case)
            existing_datasets = ds_crud.list_datasets(db, sid)
            for existing in existing_datasets:
                if existing.filename == filename and existing.sheet_name == s["sheet_name"]:
                    # Invalidate caches for re-uploaded dataset
                    df_cache.delete(str(existing.id))
                    session_cache.invalidate_dataset_meta(str(existing.id))

            # Store in MinIO
            s3_key = storage.upload_file(raw_bytes, sid, dataset_id, filename)

            # Store metadata in Postgres
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

            # Warm caches
            df_cache.set(dataset_id, df)
            
            sheet_meta = {
                "dataset_id": dataset_id,
                "filename": filename,
                "sheet_name": s["sheet_name"],
                "rows": len(df),
                "cols": len(df.columns),
                "columns": df.columns.tolist(),
            }
            cache_meta = {
                **sheet_meta,
                "s3_key": s3_key,
            }
            session_cache.set_dataset_meta(dataset_id, cache_meta)
            cache_metas.append(cache_meta)

            all_sheets.append(SheetMeta(**sheet_meta))

    # Warm session cache
    session_cache.warm_session_cache(sid, cache_metas)

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
    sid = _session_id(request)
    
    # Try session cache first
    cached_session = session_cache.get_session(sid)
    if cached_session and cached_session.get("dataset_count", 0) > 0:
        # Try to get cached metadata for each dataset
        cached_sheets = []
        rows = ds_crud.list_datasets(db, sid)  # Still need DB for authoritative list
        
        for row in rows:
            cached_meta = session_cache.get_dataset_meta(str(row.id))
            if cached_meta:
                cached_sheets.append(SheetMeta(**cached_meta))
            else:
                # Cache miss — build from DB and warm cache
                sheet_meta = SheetMeta(
                    dataset_id=str(row.id),
                    filename=row.filename,
                    sheet_name=row.sheet_name,
                    rows=row.row_count,
                    cols=row.col_count,
                    columns=row.columns,
                )
                session_cache.set_dataset_meta(
                    str(row.id),
                    {
                        **sheet_meta.dict(),
                        "s3_key": row.s3_key,
                    },
                )
                cached_sheets.append(sheet_meta)
                
        return UploadResponse(success=True, sheets=cached_sheets)
    
    # Cold path — no cache
    rows = ds_crud.list_datasets(db, sid)
    sheets = []
    for row in rows:
        sheet_meta = SheetMeta(
            dataset_id=str(row.id),
            filename=row.filename,
            sheet_name=row.sheet_name,
            rows=row.row_count,
            cols=row.col_count,
            columns=row.columns,
        )
        session_cache.set_dataset_meta(
            str(row.id),
            {
                **sheet_meta.dict(),
                "s3_key": row.s3_key,
            },
        )
        sheets.append(sheet_meta)
    
    return UploadResponse(success=True, sheets=sheets)


@router.get("/preview", response_model=PreviewResponse)
def preview(
    request: Request,
    dataset_id: str = Query(...),
    n: int = Query(default=10, ge=1, le=500),
    db: DBSession = Depends(get_db),
) -> PreviewResponse:
    """Preview with DataFrame caching (Redis fallback to MinIO)."""
    sid = _session_id(request)

    # Check cached metadata first
    cached_meta = session_cache.get_dataset_meta(dataset_id)
    if cached_meta and cached_meta.get("s3_key"):
        meta_dict = cached_meta
    else:
        # Fallback to database
        meta_row = ds_crud.get_dataset(db, dataset_id, sid)
        if meta_row is None:
            raise HTTPException(status_code=404, detail="Dataset not found.")
        meta_dict = {
            "filename": meta_row.filename,
            "sheet_name": meta_row.sheet_name,
            "s3_key": meta_row.s3_key,
            "row_count": meta_row.row_count,
            "col_count": meta_row.col_count,
            "columns": meta_row.columns,
        }
        session_cache.set_dataset_meta(dataset_id, meta_dict)

    # Try DataFrame cache (Redis)
    df = df_cache.get(dataset_id)

    if df is None:
        # Cache miss — load from MinIO
        try:
            raw_bytes = storage.download_file(meta_dict["s3_key"])
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Storage error: {exc}")
        
        buf = io.BytesIO(raw_bytes)
        ext = meta_dict["filename"].rsplit(".", 1)[-1].lower()
        
        if ext == "csv":
            df = pd.read_csv(buf)
        else:
            xl = pd.ExcelFile(buf, engine="openpyxl" if ext == "xlsx" else "xlrd")
            df = xl.parse(meta_dict["sheet_name"])
        
        # Warm the cache
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
        sheet_name=meta_dict["sheet_name"],
        filename=meta_dict["filename"],
        total_rows=len(df),
        columns=df.columns.tolist(),
        rows=top_n.to_dict(orient="records"),
        col_info=col_info,
    )
