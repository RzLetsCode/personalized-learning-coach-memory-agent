"""
Enterprise AI Learning Coach - Streamlit Application
"""

import json
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from backend.database.db_session import init_db, get_db_session
from backend.auth.user_service import (
    create_user,
    authenticate_user,
    start_study_session,
    end_study_session,
)
from backend.auth.security import is_strong_password
from src.schemas import AgentState, Message
from src.agent_v1 import agent_app
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
        "mcq_answers": {},
        "current_mcq_json": None,
        "last_quiz_score": None,
        "last_quiz_total": None,
        "quiz_difficulty": "medium",
        "quiz_num_questions": 3,
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
            if st.session_state.get("session_db_id"):
                db = get_db_session()
                try:
                    end_study_session(db, st.session_state["session_db_id"])
                finally:
                    db.close()
            for key in [
                "user_id",
                "session_db_id",
                "is_authenticated",
                "username",
                "messages",
                "mcq_answers",
                "current_mcq_json",
                "last_quiz_score",
                "last_quiz_total",
            ]:
                if key in ["messages"]:
                    st.session_state[key] = []
                elif key in ["mcq_answers"]:
                    st.session_state[key] = {}
                else:
                    st.session_state[key] = None
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
# QUIZ CONTROLS (sidebar)
# ---------------------------------------------------------------------------
def render_quiz_controls():
    if not st.session_state["is_authenticated"]:
        return

    st.sidebar.markdown("---")
    st.sidebar.markdown("## 🧪 Quiz Settings")

    st.session_state["quiz_difficulty"] = st.sidebar.selectbox(
        "Difficulty",
        options=["easy", "medium", "hard"],
        index=["easy", "medium", "hard"].index(st.session_state["quiz_difficulty"]),
    )

    st.session_state["quiz_num_questions"] = st.sidebar.slider(
        "Number of questions",
        min_value=1,
        max_value=10,
        value=st.session_state["quiz_num_questions"],
        step=1,
    )

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

    col1, col2 = st.sidebar.columns(2)
    col1.metric("Mastered", mastery["mastered"])
    col2.metric("Due Review", mastery["needs_review"])

# ---------------------------------------------------------------------------
# PER-QUIZ ANALYTICS
# ---------------------------------------------------------------------------
def render_quiz_analytics():
    if not st.session_state["is_authenticated"]:
        return
    if st.session_state["last_quiz_score"] is None:
        return

    st.sidebar.markdown("---")
    st.sidebar.markdown("## 🧮 Last Quiz Summary")

    score = st.session_state["last_quiz_score"]
    total = st.session_state["last_quiz_total"]
    pct = round(score / total * 100, 1) if total else 0.0

    st.sidebar.metric("Score", f"{score} / {total}")
    st.sidebar.caption(f"Accuracy: {pct}%")

# ---------------------------------------------------------------------------
# MCQ Rendering
# ---------------------------------------------------------------------------
def render_mcq_block_structured(data: dict):
    topic = data.get("topic", "MCQ Quiz")
    difficulty = data.get("difficulty", "medium")
    questions = data.get("questions", [])

    st.markdown(f"### {topic}")
    st.markdown(f"**Difficulty:** {difficulty.capitalize()}")
    st.markdown("---")

    user_choices = {}

    for idx, q in enumerate(questions, start=1):
        qid = q.get("id", f"q{idx}")
        with st.container(border=True):
            st.markdown(f"**Q{idx}. {q['question_text']}**")

            option_keys = list(q["options"].keys())

            selected = st.radio(
                "Select one option:",
                options=option_keys,
                format_func=lambda k: f"{k}. {q['options'][k]}",
                key=f"mcq_q_{qid}",
                label_visibility="collapsed",
            )

            user_choices[qid] = selected

    if st.button("Submit Quiz", key="submit_mcq_quiz"):
        # Build mcq_answers from JSON if not already done
        if not st.session_state["mcq_answers"]:
            answers = {}
            for q in questions:
                qid = q.get("id")
                ca = q.get("correct_answer")
                if qid and ca:
                    answers[qid] = ca
            st.session_state["mcq_answers"] = answers

        answers = st.session_state.get("mcq_answers", {})
        correct_count = 0
        total = len(questions)

        for q in questions:
            qid = q.get("id")
            user_ans = user_choices.get(qid)
            correct_ans = answers.get(qid)

            if correct_ans is None:
                st.warning(f"No correct answer cached for {qid}.")
                continue

            if user_ans == correct_ans:
                correct_count += 1
                st.success(f"{qid}: Correct")
            else:
                st.error(f"{qid}: Incorrect")

        st.info(f"Score: {correct_count} / {total}")
        st.session_state["last_quiz_score"] = correct_count
        st.session_state["last_quiz_total"] = total

# ---------------------------------------------------------------------------
# CHAT INTERFACE
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

    # 1) Show existing text history
    for msg in st.session_state["messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 2) If there is an active quiz, re-render it
    if st.session_state["current_mcq_json"] is not None:
        with st.chat_message("assistant"):
            render_mcq_block_structured(st.session_state["current_mcq_json"])

    # 3) New user input
    user_input = st.chat_input(
        "Ask a question, request a quiz, or ask for your progress..."
    )
    if not user_input:
        return

    st.session_state["messages"].append(
        {"role": "user", "content": user_input}
    )
    with st.chat_message("user"):
        st.markdown(user_input)

    # Clear previous quiz when new turn starts
    st.session_state["current_mcq_json"] = None
    st.session_state["mcq_answers"] = {}

    # 4) Call agent for this turn
    with st.chat_message("assistant"):
        with st.spinner("LearnMate is thinking..."):
            state = AgentState(
                messages=[Message(role=m["role"], content=m["content"]) for m in st.session_state["messages"]],
                user_id=st.session_state["user_id"],
                session_db_id=st.session_state.get("session_db_id"),
                # if AgentState has these:
                # quiz_difficulty=st.session_state["quiz_difficulty"],
                # quiz_num_questions=st.session_state["quiz_num_questions"],
            )

            updated_raw = agent_app.invoke(state)
            updated = AgentState(**updated_raw) if isinstance(updated_raw, dict) else updated_raw

            st.session_state["session_db_id"] = updated.session_db_id

            latest_assistant_msg = next(
                (m for m in reversed(updated.messages) if m.role == "assistant"),
                None,
            )
            assistant_content = latest_assistant_msg.content if latest_assistant_msg else \
                "I couldn't generate a response. Please try again."

            # Try MCQ JSON
            try:
                parsed = json.loads(assistant_content)
            except Exception:
                parsed = None

            if isinstance(parsed, dict) and parsed.get("type") == "mcq":
                # Cache full quiz JSON
                st.session_state["current_mcq_json"] = parsed

                # Short label in history
                history_text = f"[MCQ quiz generated on: {parsed.get('topic', 'Quiz')}]"
                st.session_state["messages"].append(
                    {"role": "assistant", "content": history_text}
                )

                render_mcq_block_structured(parsed)
            else:
                # Normal QA / analytics text
                st.session_state["messages"].append(
                    {"role": "assistant", "content": assistant_content}
                )
                st.markdown(assistant_content)

# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    init_session()
    render_auth()
    render_quiz_controls()
    render_uploader()
    render_srs_panel()
    render_analytics()
    render_quiz_analytics()
    render_chat()

if __name__ == "__main__":
    main()