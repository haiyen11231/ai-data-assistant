import streamlit as st
import pandas as pd
import os, glob
from dotenv import load_dotenv
from pandasai import SmartDataframe
from pandasai.llm import OpenAI

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

st.title("📊 AI Data Assistant")
st.caption("Step 2 — upload files, preview data, and ask AI questions")

# session state init
if "dataframes" not in st.session_state:
    # dataframes = { "filename :: sheet_name": DataFrame }
    st.session_state["dataframes"] = {}

if "file_meta" not in st.session_state:
    # file_meta = [ { filename, sheet_name, rows, cols, key } ]
    st.session_state["file_meta"] = []
if "messages" not in st.session_state:
    # messages = [ { role, content, chart_path } ]
    st.session_state["messages"] = []

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
    use_container_width=True,
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
    st.dataframe(col_info, use_container_width=True, hide_index=True)

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
ai_df = st.session_state["dataframes"][selected_ai_key]

# Render existing chat messages
for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        # If the message has a chart, display it
        if msg.get("chart_path") and msg["chart_path"]:
            try:
                st.image(msg["chart_path"], width="stretch")
            except Exception:
                pass

question = st.chat_input("Ask a question about the data…")

if question:
    # Store question in session state and display immediately
    st.session_state["messages"].append({
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
                llm = OpenAI(
                    api_key=openai_api_key,
                    model="gpt-4o",
                )

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

                response = sdf.chat(question)
                
                # Check for generated charts                chart_files = glob.glob("/tmp/pandasai_charts/*.png")
                chart_path = None
                chart_files = sorted(
                    glob.glob("/tmp/pandasai_charts/*.png"),
                    key=os.path.getmtime,
                    reverse=True,
                )
                if chart_files:
                    chart_path = chart_files[0]
                
                # Normalize response
                if chart_path:
                    response_str = "Here is the chart based on your question:"
                elif isinstance(response, pd.DataFrame):
                    response_str = response.to_markdown(index=False)
                elif response is None:
                    response_str = "No response generated. Try rephrasing your question."
                else:
                    response_str = str(response)
                
                st.markdown(response_str)
                if chart_path:
                    st.image(chart_path, width="stretch")

                # Store the assistant's response in session state
                st.session_state["messages"].append({
                    "role": "assistant",
                    "content": response_str,
                    "chart_path": chart_path,
                })
            except Exception as e:
                error_msg = f"Error generating response: {str(e)}"
                st.error(error_msg)
                st.session_state["messages"].append({
                    "role": "assistant",
                    "content": error_msg,
                    "chart_path": None,
                })
        
    st.rerun()