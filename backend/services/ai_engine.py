from __future__ import annotations
import base64
import glob
import io
import os
import shutil
import tempfile
import uuid
from typing import Optional

import pandas as pd
from pandasai import SmartDataframe
from pandasai.llm import OpenAI as PandasAIOpenAI


def run_query(
    df: pd.DataFrame,
    question: str,
    openai_api_key: str,
) -> dict:
    tmp_dir = tempfile.mkdtemp(prefix="pandasai_")
    try:
        llm = PandasAIOpenAI(
            api_key=openai_api_key,
            model="gpt-4o",
        )

        sdf = SmartDataframe(
            df=df,
            config={
                "llm": llm,
                "save_charts": True,
                "save_charts_path": tmp_dir,
                "verbose": False,
                "enforce_privacy": True,
                "max_retries": 2,
            },
        )

        response = sdf.chat(question)

        # Chart detection
        chart_b64: Optional[str] = None
        chart_files = sorted(
            glob.glob(os.path.join(tmp_dir, "*.png")),
            key=os.path.getmtime,
            reverse=True,
        )
        if chart_files:
            with open(chart_files[0], "rb") as fh:
                chart_b64 = base64.b64encode(fh.read()).decode("utf-8")

        # DataFrame response 
        table_rows: Optional[list[dict]] = None
        answer: str

        if chart_b64:
            answer = "Here is the chart based on your question:"

        elif isinstance(response, pd.DataFrame):
            table_rows = response.fillna("").astype(str).to_dict(orient="records")
            answer = "Here are the results:"

        elif response is None:
            answer = "No response generated. Try rephrasing your question."

        else:
            answer = str(response)

        return {
            "answer": answer,
            "chart_b64": chart_b64,
            "table_rows": table_rows,
        }

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
