import streamlit as st
from utils.api_client import ask_question, get_chart_url, submit_feedback

# Flatten file_meta into options for the @ selector
# What is file_key vs file_label? file_key is the unique identifier used in backend API calls, while file_label is the human-readable name shown in the UI. We need both to display options and make API requests.
def _flat_options(file_meta: list) -> list[dict]:
    opts = []
    for m in file_meta:
        display = m["filename"]
        if m["filename"] != m["sheet_name"]:
            display = f"{m['filename']} / {m['sheet_name']}"
        opts.append({
            "display": display,
            "file_key": m["file_key"],
            "file_label": m["sheet_name"],
        })
    return opts

# Render a single chat message, including feedback buttons if applicable
def _render_message(msg: dict, idx: int, session_id: str):
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.markdown(msg["content"])
        else:
            st.markdown(msg["content"])

            # Show chart if this message has one
            if msg.get("has_chart") and msg.get("prompt_id"):
                chart_url = get_chart_url(msg["prompt_id"])
                try:
                    st.image(chart_url, width="stretch")
                except Exception:
                    st.caption("Chart could not be displayed.")

            # Thumbs up / down feedback buttons
            prompt_id = msg.get("prompt_id")
            if prompt_id:
                current_rating = msg.get("rating")
                col1, col2, _ = st.columns([1, 1, 10])
                with col1:
                    up_type = "primary" if current_rating == 1 else "secondary"
                    if st.button("👍", key=f"up_{idx}_{prompt_id}", type=up_type):
                        try:
                            submit_feedback(session_id, prompt_id, 1)
                            st.session_state["messages"][idx]["rating"] = 1
                            st.rerun()
                        except Exception:
                            st.toast("Could not save feedback.", icon="⚠️")
                with col2:
                    dn_type = "primary" if current_rating == -1 else "secondary"
                    if st.button("👎", key=f"dn_{idx}_{prompt_id}", type=dn_type):
                        try:
                            submit_feedback(session_id, prompt_id, -1)
                            st.session_state["messages"][idx]["rating"] = -1
                            st.rerun()
                        except Exception:
                            st.toast("Could not save feedback.", icon="⚠️")
                
# Main function to render the chat interface
def render_chat(session_id: str):
    file_meta = st.session_state.get("file_meta", [])
    if not file_meta:
        st.info("Upload a file and select a sheet to start asking questions.")
        return
    
    options = _flat_options(file_meta)

    if "messages" not in st.session_state:
        st.session_state["messages"] = []

    
    # # Get options for the @ selector
    # ai_options = {
    #     f"{m['filename']} — {m['sheet_name']}": m["file_key"]
    #     for m in st.session_state["file_meta"]
    # }

    # selected_ai_label = st.selectbox(
    #     "Select file / sheet for AI analysis",
    #     options=list(ai_options.keys()),
    #     key="ai_file_select",
    #     format_func=lambda x: f"@ {x}",
    # )
    # selected_ai_key = ai_options[selected_ai_label]
    # messages = st.session_state["messages_by_file"].setdefault(selected_ai_key, []) 
    # ai_df = st.session_state["dataframes"][selected_ai_key] 
    # # Render existing chat messages
    # for idx, msg in enumerate(messages):
    #     _render_message(msg, idx, session_id)
    # question = st.chat_input("Ask a question about the data…")  
    # if question:
    #     # Store question in session state and display immediately
    #     messages.append({
    #         "role": "user",
    #         "content": f"`@{selected_ai_label}` {question}",
    #         "chart_path": None,
    #     })
    #     with st.chat_message("user"):
    #         st.markdown(f"`@{selected_ai_label}` {question}")

    #     # Generate AI response
    #     with st.chat_message("assistant"):
    #         with st.spinner("Generating response…"):
    #             try:
    #                 response = ask_question(selected_ai_key, question)
    #             except Exception as e:
    #                 st.error(f"Error: {e}")
    #                 return
                
    #             chart_path = response.get("chart_path")
