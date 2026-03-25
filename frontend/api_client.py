from __future__ import annotations
import os
from typing import Any, Optional
import httpx

_BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
_TIMEOUT = 120.0 


class APIClient:
    def __init__(self):
        self._client = httpx.Client(
            base_url=_BACKEND_URL,
            timeout=_TIMEOUT,
            follow_redirects=True,
        )

    # Datasets
    def upload_files(self, files: list[tuple[str, bytes, str]]) -> dict:
        try:
            response = self._client.post(
                "/api/v1/datasets/upload",
                files=[
                    ("files", (name, content, ctype))
                    for name, content, ctype in files
                ],
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"success": False, "message": e.response.text, "sheets": []}
        except Exception as e:
            return {"success": False, "message": str(e), "sheets": []}

    def list_datasets(self) -> dict:
        try:
            response = self._client.get("/api/v1/datasets/list")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"success": False, "message": str(e), "sheets": []}
    
    def preview(self, dataset_id: str, n: int = 10) -> dict:
        try:
            response = self._client.get(
                "/api/v1/datasets/preview",
                params={"dataset_id": dataset_id, "n": n},
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"success": False, "message": e.response.text}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # Query 
    def ask(self, dataset_id: str, question: str) -> dict:
        try:
            response = self._client.post(
                "/api/v1/query/ask",
                json={"dataset_id": dataset_id, "question": question},
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"success": False, "message": e.response.text}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # History 
    def get_history(self) -> dict:
        try:
            response = self._client.get("/api/v1/history/")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"success": False, "message": str(e), "items": []}

    def append_history(self, item: dict) -> dict:
        try:
            response = self._client.post("/api/v1/history/append", json=item)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"success": False, "message": str(e), "items": []}

    # Feedback
    def rate(self, prompt_id: str, rating: int) -> dict:
        try:
            response = self._client.patch(
                "/api/v1/feedback/",
                json={"prompt_id": prompt_id, "rating": rating},
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"success": False, "message": str(e)}

def get_client() -> APIClient:
    import streamlit as st
    if "_api_client" not in st.session_state:
        st.session_state["_api_client"] = APIClient()
    return st.session_state["_api_client"]
