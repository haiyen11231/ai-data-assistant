from __future__ import annotations
import io
import uuid
import pandas as pd
from fastapi import UploadFile, HTTPException

MAX_FILE_SIZE = 10 * 1024 * 1024   # 10 MB

# Magic bytes for supported formats
_MAGIC = {
    b"\x50\x4b\x03\x04": "xlsx",           # ZIP-based (xlsx)
    b"\xd0\xcf\x11\xe0": "xls",            # Compound Document (xls)
}


def _check_magic(data: bytes, ext: str) -> None:
    if ext == "csv":
        return
    for magic, fmt in _MAGIC.items():
        if data[:4] == magic and fmt == ext:
            return
    if data[:4] in _MAGIC and ext in ("xls", "xlsx"):
        return
    raise HTTPException(
        status_code=415,
        detail=f"File content does not match declared extension .{ext}",
    )


async def parse_upload(
    file: UploadFile,
) -> list[dict]:
    filename: str = file.filename or "upload"
    ext = filename.rsplit(".", 1)[-1].lower()

    if ext not in ("csv", "xls", "xlsx"):
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: .{ext}. Accepted: csv, xls, xlsx",
        )

    raw: bytes = await file.read()

    if len(raw) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {len(raw) / 1_048_576:.1f} MB. Max 10 MB.",
        )

    _check_magic(raw, ext)

    buf = io.BytesIO(raw)
    sheets: list[dict] = []

    try:
        if ext == "csv":
            df = pd.read_csv(buf)
            _validate_df(df, filename)
            sheets.append({
                "dataset_id": str(uuid.uuid4()),
                "filename": filename,
                "sheet_name": filename,
                "df": df,
            })

        else:
            xl = pd.ExcelFile(buf, engine="openpyxl" if ext == "xlsx" else "xlrd")
            for sheet_name in xl.sheet_names:
                df = xl.parse(sheet_name)
                _validate_df(df, f"{filename}::{sheet_name}")
                sheets.append({
                    "dataset_id": str(uuid.uuid4()),
                    "filename": filename,
                    "sheet_name": sheet_name,
                    "df": df,
                })

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not parse {filename}: {exc}",
        )

    return sheets


def _validate_df(df: pd.DataFrame, label: str) -> None:
    if df.empty or len(df.columns) == 0:
        raise HTTPException(
            status_code=422,
            detail=f"'{label}' appears to be empty.",
        )
