from __future__ import annotations
import base64
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from api_client import get_client

load_dotenv()

st.set_page_config(page_title="AI Data Assistant", page_icon="📊", layout="wide")

client = get_client()

def _restore_session() -> None:
    result = client.list_datasets()
    if not result.get("success"):
        return
    known_ids = {m["dataset_id"] for m in st.session_state.get("file_meta", [])}
    for sheet in result.get("sheets", []):
        if sheet["dataset_id"] not in known_ids:
            st.session_state.setdefault("file_meta", []).append(sheet)


# Session state init
if "file_meta" not in st.session_state:
    st.session_state["file_meta"] = []
if "messages_by_dataset" not in st.session_state:
    st.session_state["messages_by_dataset"] = {}
if "reuse_prompt" not in st.session_state:
    st.session_state["reuse_prompt"] = None

_restore_session()   # ← runs on every rerun; idempotent

# Sidebar 
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
            short_q = (
                item["question"][:55] + "…"
                if len(item["question"]) > 55
                else item["question"]
            )
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

st.title("📊 AI Data Assistant")

# Upload 
uploaded_files = st.file_uploader(
    "Upload one or more CSV or Excel files",
    type=["csv", "xls", "xlsx"],
    accept_multiple_files=True,
)

if uploaded_files:
    known = {m["filename"] for m in st.session_state["file_meta"]}
    new_files = [f for f in uploaded_files if f.name not in known]
    if new_files:
        with st.spinner(f"Uploading {len(new_files)} file(s)…"):
            payload = [(f.name, f.read(), f.type or "application/octet-stream") for f in new_files]
            result = client.upload_files(payload)
        if result.get("success"):
            for sheet in result["sheets"]:
                if sheet["dataset_id"] not in {m["dataset_id"] for m in st.session_state["file_meta"]}:
                    st.session_state["file_meta"].append(sheet)
            st.success(result.get("message", "Files loaded."))
        else:
            st.error(f"Upload failed: {result.get('message')}")

st.divider()
if not st.session_state["file_meta"]:
    st.info("Upload a file above to get started.")
    st.stop()

# Preview
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
preview_resp = client.preview(selected_dataset_id, n)

if not preview_resp.get("success"):
    st.error(f"Preview error: {preview_resp.get('message')}")
else:
    c1, c2, c3 = st.columns(3)
    c1.metric("Total rows", f"{preview_resp['total_rows']:,}")
    c2.metric("Columns", len(preview_resp['columns']))
    c3.metric("Showing", min(n, preview_resp['total_rows']))
    st.dataframe(pd.DataFrame(preview_resp["rows"]), use_container_width=True, hide_index=True)
    with st.expander("Column details"):
        st.dataframe(pd.DataFrame(preview_resp["col_info"]), use_container_width=True, hide_index=True)

# AI Chat 
st.divider()
st.subheader("💬 Ask AI about your data")

ai_options = {f"{m['filename']} — {m['sheet_name']}": m for m in st.session_state["file_meta"]}
selected_ai_label = st.selectbox(
    "Select file / sheet for AI analysis",
    list(ai_options.keys()),
    key="ai_file_select",
    format_func=lambda x: f"@ {x}",
)
selected_ai_meta = ai_options[selected_ai_label]
selected_ai_dataset_id = selected_ai_meta["dataset_id"]
messages = st.session_state["messages_by_dataset"].setdefault(selected_ai_dataset_id, [])

if not messages:
    suggestions = [
        "Give me a summary of this dataset",
        f"Show distribution of {selected_ai_meta['columns'][0]} as a bar chart" if selected_ai_meta.get("columns") else "What are the column names?",
        "How many missing values are there per column?",
    ]
    st.markdown("**Not sure what to ask? Try one of these:**")
    sug_cols = st.columns(len(suggestions))
    for i, sug in enumerate(suggestions):
        with sug_cols[i]:
            if st.button(sug, key=f"sug_{selected_ai_dataset_id}_{i}", use_container_width=True):
                st.session_state["pending_question"] = sug
                st.rerun()

for msg_idx, msg in enumerate(messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("chart_b64"):
            st.image(base64.b64decode(msg["chart_b64"]), use_container_width=True)
        if msg.get("table_rows"):
            st.dataframe(pd.DataFrame(msg["table_rows"]), use_container_width=True, hide_index=False)
        if msg["role"] == "assistant" and msg.get("prompt_id"):
            pid = msg["prompt_id"]
            cur = msg.get("rating")
            fb1, fb2, _ = st.columns([1, 1, 10])
            with fb1:
                if st.button("👍", key=f"up_{pid}", type="primary" if cur == 1 else "secondary"):
                    client.rate(pid, 1); msg["rating"] = 1; st.rerun()
            with fb2:
                if st.button("👎", key=f"dn_{pid}", type="primary" if cur == -1 else "secondary"):
                    client.rate(pid, -1); msg["rating"] = -1; st.rerun()

prefill = st.session_state.pop("pending_question", None)
reuse = st.session_state.get("reuse_prompt")
if reuse:
    st.session_state["reuse_prompt"] = None
    prefill = reuse["question"]

question = st.chat_input("Ask a question about the data…") or prefill

if question:
    messages.append({"role": "user", "content": f"`@{selected_ai_label}` {question}"})
    with st.chat_message("user"):
        st.markdown(f"`@{selected_ai_label}` {question}")

    with st.chat_message("assistant"):
        with st.spinner("Generating response…"):
            result = client.ask(selected_ai_dataset_id, question)

        if not result.get("success"):
            err = result.get("message", "Unknown error")
            st.error(f"Error: {err}")
            messages.append({"role": "assistant", "content": f"Error: {err}"})
        else:
            st.markdown(result["answer"])
            if result.get("chart_b64"):
                st.image(base64.b64decode(result["chart_b64"]), use_container_width=True)
            if result.get("table_rows"):
                st.dataframe(pd.DataFrame(result["table_rows"]), use_container_width=True)
            messages.append({
                "role": "assistant",
                "content": result["answer"],
                "chart_b64": result.get("chart_b64"),
                "table_rows": result.get("table_rows"),
                "prompt_id": result["prompt_id"],
                "rating": None,
            })
    st.rerun()
