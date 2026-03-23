import streamlit as st
import pandas as pd

# Workflow:
# 1. User uploads CSV / Excel files
# 2. App parses them into pandas DataFrames
# 3. Stores them in memory (session_state)
# 4. Lets user:
# - pick a file/sheet
# - preview top N rows
# - inspect schema (columns, nulls, types)

# page config 
st.set_page_config(
    page_title="AI Data Assistant",
    page_icon="📊",
    layout="wide",
)

st.title("📊 AI Data Assistant")
st.caption("Step 1 — upload files and preview data")

# session state init
if "dataframes" not in st.session_state:
    # dataframes = { "filename :: sheet_name": DataFrame }
    st.session_state["dataframes"] = {}

if "file_meta" not in st.session_state:
    # file_meta = [ { filename, sheet_name, rows, cols, key } ]
    st.session_state["file_meta"] = []


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
