from __future__ import annotations
import base64
import io
import uuid

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from api_client import get_client   # thin httpx wrapper

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Data Assistant",
    page_icon="📊",
    layout="wide",
)

# ─────────────────────────────────────────────────────────────────────────────
# Session state initialisation
# ─────────────────────────────────────────────────────────────────────────────
if "file_meta" not in st.session_state:
    st.session_state["file_meta"] = []

if "messages_by_dataset" not in st.session_state:
    # { dataset_id: [ { role, content, chart_b64, table_rows } ] }
    st.session_state["messages_by_dataset"] = {}

if "reuse_prompt" not in st.session_state:
    st.session_state["reuse_prompt"] = None

client = get_client()

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar — prompt history (fetched from backend)
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🕘 Prompt history")
    hist_resp = client.get_history()
    history_items: list[dict] = hist_resp.get("items", [])

    if not history_items:
        st.caption("No prompts yet.")
    else:
        for item in history_items:
            rating = item.get("rating")
            icon = "👍" if rating == 1 else ("👎" if rating == -1 else "⬜")
            short_q = item["question"][:55] + "…" if len(item["question"]) > 55 else item["question"]
            label = f"`@{item['filename']} / {item['sheet_name']}` {short_q}"

            col_btn, col_icon = st.sidebar.columns([9, 1])
            with col_btn:
                if st.button(label, key=f"hist_{item['prompt_id']}", use_container_width=True):
                    st.session_state["reuse_prompt"] = {
                        "question": item["question"],
                        "dataset_id": item["dataset_id"],
                    }
                    st.rerun()
            with col_icon:
                st.markdown(icon)

# ─────────────────────────────────────────────────────────────────────────────
# Main title
# ─────────────────────────────────────────────────────────────────────────────
st.title("📊 AI Data Assistant")

# ─────────────────────────────────────────────────────────────────────────────
# File upload
# ─────────────────────────────────────────────────────────────────────────────
uploaded_files = st.file_uploader(
    "Upload one or more CSV or Excel files (.csv, .xls, .xlsx)",
    type=["csv", "xls", "xlsx"],
    accept_multiple_files=True,
)

if uploaded_files:
    already_loaded_names = {m["filename"] for m in st.session_state["file_meta"]}
    new_files = [f for f in uploaded_files if f.name not in already_loaded_names]

    if new_files:
        with st.spinner(f"Uploading {len(new_files)} file(s)…"):
            # Build the multipart payload — read bytes once, don't stream
            payload = [
                (f.name, f.read(), f.type or "application/octet-stream")
                for f in new_files
            ]
            result = client.upload_files(payload)

        if result.get("success"):
            for sheet in result["sheets"]:
                st.session_state["file_meta"].append(sheet)
            st.success(result.get("message", "Files loaded."))
        else:
            st.error(f"Upload failed: {result.get('message')}")

# ─────────────────────────────────────────────────────────────────────────────
# Guard — nothing loaded yet
# ─────────────────────────────────────────────────────────────────────────────
st.divider()
if not st.session_state["file_meta"]:
    st.info("Upload a file above to get started.")
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# Data preview section
# ─────────────────────────────────────────────────────────────────────────────
options = {
    f"{m['filename']} — {m['sheet_name']}": m["dataset_id"]
    for m in st.session_state["file_meta"]
}

col1, col2 = st.columns([3, 1])
with col1:
    selected_label = st.selectbox("Select file / sheet to preview", list(options.keys()))
with col2:
    n = st.number_input("Top N rows", min_value=1, max_value=500, value=10, step=5)

selected_dataset_id = options[selected_label]

# Fetch preview from backend
preview_resp = client.preview(selected_dataset_id, n)

if not preview_resp.get("success"):
    st.error(f"Preview error: {preview_resp.get('message')}")
else:
    total_rows = preview_resp["total_rows"]
    columns = preview_resp["columns"]
    rows = preview_resp["rows"]
    col_info = preview_resp["col_info"]

    c1, c2, c3 = st.columns(3)
    c1.metric("Total rows", f"{total_rows:,}")
    c2.metric("Columns", len(columns))
    c3.metric("Showing", min(n, total_rows))

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with st.expander("Column details"):
        st.dataframe(pd.DataFrame(col_info), use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────────────────────────────────
# AI chat section
# ─────────────────────────────────────────────────────────────────────────────
st.divider()
st.subheader("💬 Ask AI about your data")

# File selector for AI (can differ from preview selector)
ai_options = {
    f"{m['filename']} — {m['sheet_name']}": m
    for m in st.session_state["file_meta"]
}
selected_ai_label = st.selectbox(
    "Select file / sheet for AI analysis",
    list(ai_options.keys()),
    key="ai_file_select",
    format_func=lambda x: f"@ {x}",
)
selected_ai_meta = ai_options[selected_ai_label]
selected_ai_dataset_id = selected_ai_meta["dataset_id"]
messages = st.session_state["messages_by_dataset"].setdefault(selected_ai_dataset_id, [])

# Suggested prompts
def _generate_suggestions(meta: dict) -> list[str]:
    suggestions = ["Give me a summary of this dataset"]
    columns: list[str] = meta.get("columns", [])
    numeric_hints = {"age", "fare", "price", "count", "total", "salary", "score"}
    guessed_numeric = [c for c in columns if any(h in c.lower() for h in numeric_hints)]
    if guessed_numeric:
        suggestions.append(f"What is the average {guessed_numeric[0]}?")
    if len(columns) >= 2:
        suggestions.append(f"Show distribution of {columns[0]} as a bar chart")
    return suggestions[:3]

if not messages:
    suggestions = _generate_suggestions(selected_ai_meta)
    st.markdown("**Not sure what to ask? Try one of these:**")
    sug_cols = st.columns(len(suggestions))
    for i, sug in enumerate(suggestions):
        with sug_cols[i]:
            if st.button(sug, key=f"sug_{selected_ai_dataset_id}_{i}", use_container_width=True):
                st.session_state["pending_question"] = sug
                st.rerun()

# Render chat history 
for msg_idx, msg in enumerate(messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

        # Chart (base64 PNG)
        if msg.get("chart_b64"):
            img_bytes = base64.b64decode(msg["chart_b64"])
            st.image(img_bytes, use_container_width=True)

        # Table result
        if msg.get("table_rows"):
            st.dataframe(
                pd.DataFrame(msg["table_rows"]),
                use_container_width=True,
                hide_index=False,
            )

        # Feedback buttons for assistant messages
        if msg["role"] == "assistant" and msg.get("prompt_id"):
            prompt_id = msg["prompt_id"]
            current_rating = msg.get("rating")
            fb_col1, fb_col2, _ = st.columns([1, 1, 10])
            with fb_col1:
                up_type = "primary" if current_rating == 1 else "secondary"
                if st.button("👍", key=f"up_{prompt_id}", type=up_type):
                    client.rate(prompt_id, 1)
                    msg["rating"] = 1
                    st.rerun()
            with fb_col2:
                dn_type = "primary" if current_rating == -1 else "secondary"
                if st.button("👎", key=f"dn_{prompt_id}", type=dn_type):
                    client.rate(prompt_id, -1)
                    msg["rating"] = -1
                    st.rerun()

# Question input
prefill: str | None = None

if "pending_question" in st.session_state:
    prefill = st.session_state.pop("pending_question")

reuse = st.session_state.get("reuse_prompt")
if reuse:
    st.session_state["reuse_prompt"] = None
    prefill = reuse["question"]

question = st.chat_input("Ask a question about the data…") or prefill

if question:
    # Append user message immediately
    messages.append({"role": "user", "content": f"`@{selected_ai_label}` {question}"})
    with st.chat_message("user"):
        st.markdown(f"`@{selected_ai_label}` {question}")

    # Call backend AI endpoint
    with st.chat_message("assistant"):
        with st.spinner("Generating response…"):
            result = client.ask(selected_ai_dataset_id, question)

        if not result.get("success"):
            err = result.get("message", "Unknown error")
            st.error(f"Error: {err}")
            messages.append({"role": "assistant", "content": f"Error: {err}"})
        else:
            answer = result["answer"]
            chart_b64 = result.get("chart_b64")
            table_rows = result.get("table_rows")
            prompt_id = result["prompt_id"]

            st.markdown(answer)

            if chart_b64:
                st.image(base64.b64decode(chart_b64), use_container_width=True)

            if table_rows:
                st.dataframe(
                    pd.DataFrame(table_rows),
                    use_container_width=True,
                    hide_index=False,
                )

            # Append assistant message with all metadata
            assistant_msg = {
                "role": "assistant",
                "content": answer,
                "chart_b64": chart_b64,
                "table_rows": table_rows,
                "prompt_id": prompt_id,
                "rating": None,
            }
            messages.append(assistant_msg)

            # Persist to backend history store
            client.append_history({
                "prompt_id": prompt_id,
                "dataset_id": selected_ai_dataset_id,
                "filename": selected_ai_meta["filename"],
                "sheet_name": selected_ai_meta["sheet_name"],
                "question": question,
                "answer": answer,
                "chart_b64": chart_b64,
                "table_rows": table_rows,
                "rating": None,
            })

    st.rerun()
