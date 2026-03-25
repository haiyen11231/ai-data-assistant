import uuid
import streamlit as st
import pandas as pd
import os, glob
from dotenv import load_dotenv
from pandasai import SmartDataframe
from pandasai.llm import OpenAI
import shutil

load_dotenv()

# Workflow:
# 1. User uploads CSV / Excel files
# 2. App parses them into pandas DataFrames
# 3. Stores them in memory (session_state)
# 4. Lets user:
# - pick a file/sheet
# - preview top N rows
# - inspect schema (columns, nulls, types)
# 4. Chat interface (like ChatGPT)
# - LLM-powered data analysis (PandasAI)
# - Chart generation
# - Conversation memory

# page config 
st.set_page_config(
    page_title="AI Data Assistant",
    page_icon="📊",
    layout="wide",
)


# session state init
if "dataframes" not in st.session_state:
    # dataframes = { "filename :: sheet_name": DataFrame }
    st.session_state["dataframes"] = {}

if "file_meta" not in st.session_state:
    # file_meta = [ { filename, sheet_name, rows, cols, key } ]
    st.session_state["file_meta"] = []

if "messages_by_file" not in st.session_state:
    # messages_by_file = { "filename :: sheet_name": [ { role, content, chart_path } ] }
    st.session_state["messages_by_file"] = {}

if "history" not in st.session_state:
    # Flat list of every Q&A across all files
    # [ { id, question, file_label, answer, chart_path, dataframe, rating } ]
    st.session_state["history"] = []

if "reuse_prompt" not in st.session_state:
    st.session_state["reuse_prompt"] = None

# sidebar
with st.sidebar:
    st.markdown("## Prompt history")

    history = st.session_state["history"]
    if not history:
        st.caption("No prompts yet.")
    else:
        for item in reversed(history):
            rating = item.get("rating")
            icon = "👍" if rating == 1 else ("👎" if rating == -1 else "")

            short_q = item["question"][:55] + "…" if len(item["question"]) > 55 else item["question"]

            col_btn, col_icon = st.sidebar.columns([9, 1])
            with col_btn:
                if st.button(
                    f"`@{item['file_label']}` {short_q}",
                    key=f"hist_{item['id']}",
                    use_container_width=True,
                ):
                    st.session_state["reuse_prompt"] = {
                        "question": item["question"],
                        "file_key": item["file_key"],
                    }
                    st.rerun()
            with col_icon:
                st.markdown(icon)

st.title("📊 AI Data Assistant")

# file parsing -> { sheet_name/filename: DataFrame }
def parse_uploaded_file(uploaded_file) -> dict[str, pd.DataFrame]:
    """
    Parse a CSV or Excel file into a dict of {sheet_name: DataFrame}.
    CSV files have one implicit sheet named after the file.
    Excel files can have multiple sheets.
    """
    filename = uploaded_file.name
    ext = filename.rsplit(".", 1)[-1].lower()

    if ext == "csv":
        df = pd.read_csv(uploaded_file)
        return {filename: df}

    elif ext in ("xls", "xlsx"):
        xl = pd.ExcelFile(uploaded_file)
        sheets = {}
        for sheet_name in xl.sheet_names:
            sheets[sheet_name] = xl.parse(sheet_name)
        return sheets

    else:
        st.error(f"Unsupported file type: .{ext}")
        return {}

# file/sheet identifier for session state storage
def make_key(filename: str, sheet_name: str) -> str:
    """Unique key for the dataframes dict."""
    return f"{filename} :: {sheet_name}"

# file uploader 
uploaded_files = st.file_uploader(
    "Upload one or more CSV or Excel files (.csv, .xls, .xlsx)",
    type=["csv", "xls", "xlsx"],
    accept_multiple_files=True,
)

if uploaded_files:
    for uploaded_file in uploaded_files:
        filename = uploaded_file.name

        # Skip if already parsed (avoid re-parsing on every rerun)
        # TODO: Use set with session_state to track loaded files for O(1) lookups
        already_loaded = any(
            m["filename"] == filename
            for m in st.session_state["file_meta"]
        )
        if already_loaded:
            continue

        # Parse the file
        with st.spinner(f"Parsing {filename}…"):
            sheets = parse_uploaded_file(uploaded_file)

        # Store each sheet in session state
        for sheet_name, df in sheets.items():
            key = make_key(filename, sheet_name)
            st.session_state["dataframes"][key] = df
            st.session_state["file_meta"].append({
                "filename": filename,
                "sheet_name": sheet_name,
                "rows": len(df),
                "cols": len(df.columns),
                "key": key,
            })

        st.success(f"✓ {filename} loaded — {len(sheets)} sheet(s)")

# preview section 
st.divider()

if not st.session_state["file_meta"]:
    st.info("Upload a file above to get started.")
    st.stop()

# Build dropdown options from loaded files
options = {
    f"{m['filename']} — {m['sheet_name']}": m["key"]
    for m in st.session_state["file_meta"]
}

col1, col2 = st.columns([3, 1])

with col1:
    selected_label = st.selectbox(
        "Select file / sheet to preview",
        options=list(options.keys()),
    )

with col2:
    n = st.number_input(
        "Top N rows",
        min_value=1,
        max_value=500,
        value=10,
        step=5,
    )

# Load the selected DataFrame
selected_key = options[selected_label]
df = st.session_state["dataframes"][selected_key]

# Metric cards
c1, c2, c3 = st.columns(3)
c1.metric("Total rows", f"{len(df):,}")
c2.metric("Columns", len(df.columns))
c3.metric("Showing", min(n, len(df)))

# Data table
st.dataframe(
    df.head(n),
    width="stretch",
    hide_index=True,
)

# Column info expander
with st.expander("Column details"):
    col_info = pd.DataFrame({
        "Column": df.columns,
        "Type": df.dtypes.astype(str).values,
        "Non-null": df.count().values,
        "Nulls": df.isnull().sum().values,
    })
    st.dataframe(col_info, width="stretch", hide_index=True)

# AI chat section
st.divider()
st.subheader("💬 Ask AI about your data")

openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    st.warning("⚠️ To enable AI features, set your OpenAI API key in the .env file.")
    st.stop()

# File selector for AI analysis
ai_options = {
    f"{m['filename']} — {m['sheet_name']}": m["key"]
    for m in st.session_state["file_meta"]
}

selected_ai_label = st.selectbox(
    "Select file / sheet for AI analysis",
    options=list(ai_options.keys()),
    key="ai_file_select",
    format_func=lambda x: f"@ {x}",
)
selected_ai_key = ai_options[selected_ai_label]
messages = st.session_state["messages_by_file"].setdefault(selected_ai_key, [])
ai_df = st.session_state["dataframes"][selected_ai_key]

# Suggested prompts only showed when there are no messages yet for this file
def _generate_suggestions(df: pd.DataFrame) -> list[str]:
    """
    Generate 3 relevant suggested questions based on the DataFrame's columns and types.
    Rules:
    - Always suggest a summary/overview question
    - Add numeric-specific questions if numeric columns exist
    - Add category-specific questions if low-cardinality text columns exist
    """
    suggestions = []
    cols = df.columns.tolist()
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    text_cols = [
        c for c in df.select_dtypes(include="object").columns.tolist()
        if df[c].nunique() < 20  # low cardinality = likely a category
    ]

    # Always: overview
    suggestions.append("Give me a summary of this dataset")

    # Numeric: distribution or top values
    if numeric_cols:
        col = numeric_cols[0]
        suggestions.append(f"What is the average {col}?")

    # Numeric + category: grouped analysis
    if numeric_cols and text_cols:
        num = numeric_cols[0]
        cat = text_cols[0]
        suggestions.append(f"Show {num} grouped by {cat} as a bar chart")

    # Category only (no numeric)
    elif text_cols and not numeric_cols:
        cat = text_cols[0]
        suggestions.append(f"What are the most common values in {cat}?")

    # Fallback if nothing specific found
    if len(suggestions) < 3:
        suggestions.append("Show me the top 10 rows")

    return suggestions[:3]  # cap at 3

if not messages:
    suggestions = _generate_suggestions(ai_df)
    if suggestions:
        st.markdown("**Not sure what to ask? Try one of these:**")
        cols = st.columns(len(suggestions))
        for i, suggestion in enumerate(suggestions):
            with cols[i]:
                if st.button(suggestion, key=f"suggest_{selected_ai_key}_{i}", width="stretch"):
                    st.session_state["pending_question"] = suggestion
                    st.rerun()

# Render existing chat messages
for msg_idx, msg in enumerate(messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        # If the message has a chart, display it
        if msg.get("chart_path") and msg["chart_path"]:
            try:
                st.image(msg["chart_path"], width="stretch")
            except Exception:
                pass
        # If the message has a DataFrame, display it
        if msg.get("dataframe") is not None:
            st.dataframe(msg["dataframe"].fillna("").astype(str), width="stretch", hide_index=False)
        
        # Add a feedback mechanism for each assistant response
        if msg["role"] == "assistant":
            # TODO: Should find better way to find assistant messages
            # Find matching history item for this message by position
            # assistant messages are every odd index (0=user, 1=assistant, 2=user...)
            history_idx = msg_idx // 2
            history = st.session_state["history"]

            if history_idx < len(history):
                current_rating = history[history_idx].get("rating")
                col1, col2, _ = st.columns([1, 1, 10])
                with col1:
                    up_style = "primary" if current_rating == 1 else "secondary"
                    if st.button("👍", key=f"up_{selected_ai_key}_{msg_idx}", type=up_style):
                        history[history_idx]["rating"] = 1
                        st.rerun()
                with col2:
                    dn_style = "primary" if current_rating == -1 else "secondary"
                    if st.button("👎", key=f"dn_{selected_ai_key}_{msg_idx}", type=dn_style):
                        history[history_idx]["rating"] = -1
                        st.rerun()

# Pick up any suggestion that was clicked on previous rerun
if "pending_question" in st.session_state:
    prefill = st.session_state.pop("pending_question")
else:
    prefill = None

# Pick up any prompt reuse action from the sidebar history
reuse = st.session_state.get("reuse_prompt")
if reuse:
    st.session_state["reuse_prompt"] = None
    # If the reused prompt is for a different file, we can't auto-switch
    # the selectbox, so just pre-fill the question for the current file
    prefill = reuse["question"]

question = st.chat_input("Ask a question about the data…")

# Use the suggestion click as the question if no manual input
question = question or prefill

if question:
    # Store question in session state and display immediately
    messages.append({
        "role": "user",
        "content": f"`@{selected_ai_label}` {question}",
        "chart_path": None,
    })
    with st.chat_message("user"):
        st.markdown(f"`@{selected_ai_label}` {question}")

    # Generate AI response
    with st.chat_message("assistant"):
        with st.spinner("Generating response…"):
            try:
                if "llm" not in st.session_state:
                    st.session_state["llm"] = OpenAI(
                        api_key=openai_api_key,
                        model="gpt-4o",
                    )

                llm = st.session_state["llm"]

                sdf = SmartDataframe(
                    df=ai_df,
                    config={
                        "llm": llm,
                        "save_charts": True,
                        "save_charts_path": "/tmp/pandasai_charts",
                        "verbose": False,
                        "enforce_privacy": True,
                        "max_retries": 2,
                    },
                )

                shutil.rmtree("/tmp/pandasai_charts", ignore_errors=True)
                response = sdf.chat(question)
                
                # Check for generated charts                
                chart_files = glob.glob("/tmp/pandasai_charts/*.png")
                chart_path = None
                chart_files = sorted(
                    glob.glob("/tmp/pandasai_charts/*.png"),
                    key=os.path.getmtime,
                    reverse=True,
                )
                if chart_files:
                    chart_path = chart_files[0]
                
                # Normalize response and render appropriately
                if chart_path:
                    # Render chart with a caption
                    response_str = "Here is the chart based on your question:"
                    st.markdown(response_str)
                    st.image(chart_path, width="stretch")

                elif isinstance(response, pd.DataFrame):
                    # Render DataFrame responses as tables
                    response_str = f"Here are the results:"
                    st.markdown(response_str)
                    st.dataframe(response.fillna("").astype(str), width="stretch", hide_index=False)

                elif response is None:
                    # Handle cases where the LLM doesn't return a direct answer
                    response_str = "No response generated. Try rephrasing your question."
                    st.markdown(response_str)

                else:
                    # Render plain text responses
                    response_str = str(response)
                    st.markdown(response_str)

                # Store the assistant's response in session state and history for future reference
                assistant_msg = {
                    "role": "assistant",
                    "content": response_str,
                    "chart_path": chart_path,
                    "dataframe": response if isinstance(response, pd.DataFrame) else None,
                }
                messages.append(assistant_msg)

                st.session_state["history"].append({
                    "id": str(uuid.uuid4()),
                    "question": question,
                    "file_label": selected_ai_label,
                    "file_key": selected_ai_key,
                    "answer": response_str,
                    "chart_path": chart_path,
                    "dataframe": response if isinstance(response, pd.DataFrame) else None,
                    "rating": None,
                })
            except Exception as e:
                error_msg = f"Error generating response: {str(e)}"
                st.error(error_msg)
                messages.append({
                    "role": "assistant",
                    "content": error_msg,
                    "chart_path": None,
                    "dataframe": None,
                })
        
    st.rerun()