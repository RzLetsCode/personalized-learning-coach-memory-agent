"""
Enterprise AI Learning Coach - Streamlit Application

Full-stack Streamlit UI featuring:
  - Secure Authentication (login / signup with bcrypt)
  - Reactive Chat Interface (LangGraph agent)
  - File Upload -> Pinecone RAG indexing
  - Real-Time Analytics Dashboard (Pandas + Plotly)
  - Spaced Repetition (SRS) review surfacing

Run with: streamlit run app.py
"""

import streamlit as st
from dotenv import load_dotenv
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# --- Project imports ---
from backend.database.db_session import init_db, get_db_session
from backend.auth.user_service import (
    create_user,
    authenticate_user,
    get_user_by_id,
    start_study_session,
    end_study_session,
)
from backend.auth.security import is_strong_password
from src.schemas import AgentState, Message
from src.agent import agent_app
from src.memory.semantic_memory import index_user_material
from src.memory.srs_store import get_due_topics, get_mastery_summary
from backend.database.models import MCQScore, KnowledgePoint

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
load_dotenv()
init_db()


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="LearnMate - AI Learning Coach",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------
def init_session():
    defaults = {
        "messages": [],
        "user_id": None,
        "session_db_id": None,
        "is_authenticated": False,
        "username": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ---------------------------------------------------------------------------
# AUTH SIDEBAR
# ---------------------------------------------------------------------------
def render_auth():
    st.sidebar.markdown("## 🔐 Account")

    if st.session_state["is_authenticated"]:
        st.sidebar.success(f"Logged in as **{st.session_state['username']}**")
        if st.sidebar.button("Logout", use_container_width=True):
            # End active study session
            if st.session_state.get("session_db_id"):
                db = get_db_session()
                try:
                    end_study_session(db, st.session_state["session_db_id"])
                finally:
                    db.close()
            for key in ["user_id", "session_db_id", "is_authenticated", "username", "messages"]:
                st.session_state[key] = None if key != "messages" else []
            st.rerun()
        return

    tab_login, tab_signup = st.sidebar.tabs(["Login", "Sign Up"])

    with tab_login:
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Login", use_container_width=True):
            db = get_db_session()
            try:
                user = authenticate_user(db, email, password)
                if user:
                    session = start_study_session(db, user.id)
                    st.session_state["user_id"] = user.id
                    st.session_state["session_db_id"] = session.id
                    st.session_state["username"] = user.username
                    st.session_state["is_authenticated"] = True
                    st.success("Welcome back!")
                    st.rerun()
                else:
                    st.error("Invalid email or password.")
            finally:
                db.close()

    with tab_signup:
        username = st.text_input("Username", key="signup_username")
        email = st.text_input("Email", key="signup_email")
        password = st.text_input("Password", type="password", key="signup_password")
        learning_level = st.selectbox(
            "Learning level",
            ["beginner", "intermediate", "advanced"],
            key="signup_level",
        )
        if st.button("Create Account", use_container_width=True):
            valid, msg = is_strong_password(password)
            if not valid:
                st.error(msg)
            else:
                db = get_db_session()
                try:
                    user = create_user(
                        db,
                        username=username,
                        email=email,
                        password=password,
                        learning_level=learning_level,
                    )
                    session = start_study_session(db, user.id)
                    st.session_state["user_id"] = user.id
                    st.session_state["session_db_id"] = session.id
                    st.session_state["username"] = user.username
                    st.session_state["is_authenticated"] = True
                    st.success("Account created! Welcome to LearnMate.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
                finally:
                    db.close()


# ---------------------------------------------------------------------------
# FILE UPLOADER
# ---------------------------------------------------------------------------
def render_uploader():
    if not st.session_state["is_authenticated"]:
        return
    st.sidebar.markdown("---")
    st.sidebar.markdown("## 📂 Upload Study Material")
    uploaded = st.sidebar.file_uploader(
        "Upload .txt or .pdf (text)",
        type=["txt"],
        accept_multiple_files=True,
        key="file_uploader",
    )
    if uploaded and st.sidebar.button("Index Materials", use_container_width=True):
        docs = [f.read().decode("utf-8", errors="ignore") for f in uploaded]
        user_id = st.session_state["user_id"]
        with st.sidebar:
            with st.spinner("Indexing your materials..."):
                n = index_user_material(user_id, docs, source="uploaded_file")
        st.sidebar.success(f"Indexed {n} chunks from {len(docs)} file(s).")


# ---------------------------------------------------------------------------
# SRS REVIEW PANEL
# ---------------------------------------------------------------------------
def render_srs_panel():
    if not st.session_state["is_authenticated"]:
        return
    user_id = st.session_state["user_id"]
    db = get_db_session()
    try:
        due = get_due_topics(db, user_id, limit=5)
    finally:
        db.close()

    if not due:
        return

    st.sidebar.markdown("---")
    st.sidebar.markdown("## 🔔 Due for Review Today")
    for kp in due:
        days_overdue = (datetime.now().date() - kp.due_date).days
        label = f"**{kp.topic}**" + (f" _(+{days_overdue}d overdue)_" if days_overdue > 0 else "")
        st.sidebar.markdown(f"- {label}")


# ---------------------------------------------------------------------------
# ANALYTICS DASHBOARD
# ---------------------------------------------------------------------------
def render_analytics():
    if not st.session_state["is_authenticated"]:
        st.sidebar.info("Login to view analytics.")
        return

    user_id = st.session_state["user_id"]
    st.sidebar.markdown("---")
    st.sidebar.markdown("## 📊 Learning Analytics")

    db = get_db_session()
    try:
        mcqs = (
            db.query(MCQScore)
            .filter(MCQScore.user_id == user_id)
            .order_by(MCQScore.attempt_timestamp)
            .all()
        )
        mastery = get_mastery_summary(db, user_id)
    finally:
        db.close()

    if not mcqs:
        st.sidebar.caption("No quiz data yet. Ask for MCQs to see stats!")
        return

    # MCQ rolling accuracy chart
    df = pd.DataFrame([
        {
            "time": m.attempt_timestamp,
            "is_correct": int(m.is_correct),
            "topic": m.topic,
        }
        for m in mcqs
    ])
    df["rolling_accuracy"] = df["is_correct"].rolling(window=10, min_periods=1).mean() * 100

    fig_acc = px.line(
        df,
        x="time",
        y="rolling_accuracy",
        title="Rolling Accuracy (last 10 Qs)",
        labels={"rolling_accuracy": "Accuracy %", "time": "Date"},
        color_discrete_sequence=["#6C63FF"],
    )
    fig_acc.update_layout(height=220, margin=dict(l=0, r=0, t=30, b=0))
    st.sidebar.plotly_chart(fig_acc, use_container_width=True)

    # Topic breakdown
    if mastery["topics"]:
        topics_df = pd.DataFrame(mastery["topics"])
        fig_topic = px.bar(
            topics_df,
            x="topic",
            y="score",
            title="Mastery Score by Topic",
            color="score",
            color_continuous_scale="Viridis",
        )
        fig_topic.update_layout(height=220, margin=dict(l=0, r=0, t=30, b=0))
        st.sidebar.plotly_chart(fig_topic, use_container_width=True)

    # Summary stats
    col1, col2 = st.sidebar.columns(2)
    col1.metric("Mastered", mastery["mastered"])
    col2.metric("Due Review", mastery["needs_review"])


# ---------------------------------------------------------------------------
# CHAT INTERFACE (main area)
# ---------------------------------------------------------------------------
def render_chat():
    st.markdown(
        "<h1 style='text-align:center; color:#6C63FF;'>📚 LearnMate</h1>"
        "<p style='text-align:center; color:#888;'>Your Personalized AI Learning Coach</p>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    if not st.session_state["is_authenticated"]:
        st.info("Please login or create an account in the sidebar to start learning.")
        return

    # Display existing chat history
    for msg in st.session_state["messages"]:
        with st.chat_message(msg.role):
            st.markdown(msg.content)

    # User input
    user_input = st.chat_input(
        "Ask a question, request a quiz, or ask for your progress..."
    )
    if user_input:
        # Add user message
        st.session_state["messages"].append(
            Message(role="user", content=user_input)
        )
        with st.chat_message("user"):
            st.markdown(user_input)

        # Build state and invoke agent
        with st.chat_message("assistant"):
            with st.spinner("LearnMate is thinking..."):
                state = AgentState(
                    messages=st.session_state["messages"],
                    user_id=st.session_state["user_id"],
                    session_db_id=st.session_state.get("session_db_id"),
                )
                updated = agent_app.invoke(state)

                # Sync messages back
                st.session_state["messages"] = updated.messages

                # Display last assistant response
                last_reply = next(
                    (m.content for m in reversed(updated.messages) if m.role == "assistant"),
                    "I couldn't generate a response. Please try again.",
                )
                st.markdown(last_reply)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    init_session()
    render_auth()
    render_uploader()
    render_srs_panel()
    render_analytics()
    render_chat()


if __name__ == "__main__":
    main()
