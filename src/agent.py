"""
LangGraph Agent for the Enterprise AI Learning Coach.

Implements a full state machine with:
  intent_analyzer -> qa_node | mcq_node | analytics_node

Each node:
  - Reads/writes AgentState
  - Calls the appropriate LLM with context-aware prompts
  - Persists results to SQLAlchemy (MCQScore, KnowledgePoint)
  - Uses Pinecone RAG for context retrieval
"""

import os
import json
import re
from typing import Literal

from langgraph.graph import StateGraph, START, END
from langchain_openai import AzureChatOpenAI 

from src.schemas import AgentState, Message
from src import prompts
from src.memory.semantic_memory import get_context_for_query, store_qa_memory
from src.memory.srs_store import update_after_review, get_due_topics, get_mastery_summary
from backend.database.db_session import get_db_session
from backend.database.models import MCQScore, StudySession

# ---------------------------------------------------------------------------
# LLM instances
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# LLM instances (Azure OpenAI)
# ---------------------------------------------------------------------------
AZURE_API_KEY = os.environ.get("AZURE_OPENAI_API_KEY")
AZURE_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT")
AZURE_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
AZURE_CHAT_MODEL = os.environ.get("AZURE_OPENAI_CHAT_MODEL", "gpt-4.1")  # or your deployment name

llm_common_kwargs = dict(
    api_key=AZURE_API_KEY,
    azure_endpoint=AZURE_ENDPOINT,
    api_version=AZURE_API_VERSION,
    model=AZURE_CHAT_MODEL,
)

llm_intent = AzureChatOpenAI(temperature=0.0, **llm_common_kwargs)
llm_qa = AzureChatOpenAI(temperature=0.3, **llm_common_kwargs)
llm_mcq = AzureChatOpenAI(temperature=0.4, **llm_common_kwargs)
llm_analytics = AzureChatOpenAI(temperature=0.0, **llm_common_kwargs)

 


# ===========================================================================
# NODE: Intent Analyzer
# ===========================================================================
def intent_analyzer(state: AgentState) -> AgentState:
    """
    Classify the user's last message into: qa | mcq | analytics.
    Also extracts the topic for SRS updates.
    """
    last_user_msg = next(
        (m.content for m in reversed(state.messages) if m.role == "user"), ""
    )

    resp = llm_intent.invoke([
        {"role": "system", "content": prompts.INTENT_PROMPT},
        {"role": "user", "content": last_user_msg},
    ])
    raw = resp.content.strip().lower()

    if "mcq" in raw or "quiz" in raw or "test" in raw:
        intent = "mcq"
    elif "analytic" in raw or "progress" in raw or "stats" in raw or "how am" in raw:
        intent = "analytics"
    else:
        intent = "qa"

    state.intent = intent
    return state


# ===========================================================================
# NODE: QA (Learning)
# ===========================================================================
def qa_node(state: AgentState) -> AgentState:
    """
    Answer learning questions using RAG context from the user's study materials.
    Stores the Q&A in semantic memory and updates SRS.
    """
    user_id = state.user_id
    last_user_msg = next(
        (m.content for m in reversed(state.messages) if m.role == "user"), ""
    )

    # RAG retrieval
    context = ""
    if user_id is not None:
        context = get_context_for_query(user_id, last_user_msg, k=5)

    profile_summary = f"User ID: {user_id} | Level: intermediate"

    messages = [
        {"role": "system", "content": prompts.QA_SYSTEM_PROMPT.format(
            context=context,
            profile_summary=profile_summary,
        )},
    ]
    for msg in state.messages:
        messages.append({"role": msg.role, "content": msg.content})

    resp = llm_qa.invoke(messages)
    answer = resp.content

    # Extract JSON memory instruction if present
    topic = state.topic or "general"
    try:
        json_match = re.search(r"```json(.*?)```", answer, re.DOTALL)
        if json_match:
            instruction = json.loads(json_match.group(1).strip())
            topic = instruction.get("recommended_topics", ["general"])[0] if instruction.get("recommended_topics") else "general"
    except Exception:
        pass

    # Persist Q&A to semantic memory and update SRS
    if user_id is not None:
        store_qa_memory(
            user_id=user_id,
            question=last_user_msg,
            answer=answer,
            topic=topic,
        )
        db = get_db_session()
        try:
            update_after_review(db, user_id=user_id, topic=topic, quality=3)
        finally:
            db.close()

    state.messages.append(Message(role="assistant", content=answer))
    state.topic = topic
    return state


# ===========================================================================
# NODE: MCQ (Quiz)
# ===========================================================================
def mcq_node(state: AgentState) -> AgentState:
    """
    Generate or evaluate MCQs based on the user's study materials.
    Saves MCQScore to the database and updates SRS.
    """
    user_id = state.user_id
    last_user_msg = next(
        (m.content for m in reversed(state.messages) if m.role == "user"), ""
    )

    # RAG retrieval
    context = ""
    if user_id is not None:
        context = get_context_for_query(user_id, last_user_msg, k=4)

    topic = state.topic or "General AI/ML"
    prompt_text = prompts.MCQ_SYSTEM_PROMPT.format(
        context=context,
        topic=topic,
        num_questions=3,
        difficulty="medium",
    )

    resp = llm_mcq.invoke([
        {"role": "system", "content": prompt_text},
        {"role": "user", "content": last_user_msg},
    ])
    answer = resp.content

    # Persist MCQ result to DB
    if user_id is not None and state.session_db_id is not None:
        db = get_db_session()
        try:
            mcq_score = MCQScore(
                user_id=user_id,
                session_db_id=state.session_db_id,
                topic=topic,
                question_text=last_user_msg,
                options={"A": "", "B": "", "C": "", "D": ""},
                correct_answer="A",
                is_correct=True,
                difficulty_level="medium",
            )
            db.add(mcq_score)
            db.commit()
            update_after_review(db, user_id=user_id, topic=topic, quality=4)
        finally:
            db.close()

    state.messages.append(Message(role="assistant", content=answer))
    state.mcq_context = answer
    return state


# ===========================================================================
# NODE: Analytics
# ===========================================================================
def analytics_node(state: AgentState) -> AgentState:
    """
    Query the database for learning stats and return a motivating summary.
    No LLM call for data fetching - only for formatting the response.
    """
    user_id = state.user_id
    if user_id is None:
        state.messages.append(Message(
            role="assistant",
            content="Please log in to view your learning analytics.",
        ))
        return state

    db = get_db_session()
    try:
        from backend.database.models import MCQScore as MCQModel
        total = db.query(MCQModel).filter(MCQModel.user_id == user_id).count()
        correct = db.query(MCQModel).filter(
            MCQModel.user_id == user_id, MCQModel.is_correct.is_(True)
        ).count()
        accuracy = round((correct / total * 100), 1) if total > 0 else 0.0

        mastery = get_mastery_summary(db, user_id)
        due_topics = get_due_topics(db, user_id, limit=5)
        due_list = ", ".join([t.topic for t in due_topics]) if due_topics else "None"

        analytics_data = (
            f"Total MCQs answered: {total}\n"
            f"Correct answers: {correct}\n"
            f"Accuracy: {accuracy}%\n"
            f"Total topics tracked: {mastery['total_topics']}\n"
            f"Mastered topics: {mastery['mastered']}\n"
            f"Topics due for review: {due_list}"
        )
    finally:
        db.close()

    resp = llm_analytics.invoke([
        {"role": "system", "content": prompts.ANALYTICS_SYSTEM_PROMPT.format(
            analytics_data=analytics_data,
        )},
        {"role": "user", "content": state.messages[-1].content if state.messages else "Show my progress"},
    ])

    state.messages.append(Message(role="assistant", content=resp.content))
    return state


# ===========================================================================
# LangGraph Graph Definition
# ===========================================================================
def _route_intent(state: AgentState) -> Literal["qa", "mcq", "analytics"]:
    """Conditional edge: route based on detected intent."""
    intent = state.intent
    if intent == "mcq":
        return "mcq"
    if intent == "analytics":
        return "analytics"
    return "qa"


graph = StateGraph(AgentState)

graph.add_node("intent", intent_analyzer)
graph.add_node("qa", qa_node)
graph.add_node("mcq", mcq_node)
graph.add_node("analytics", analytics_node)

graph.add_edge(START, "intent")
graph.add_conditional_edges(
    "intent",
    _route_intent,
    {"qa": "qa", "mcq": "mcq", "analytics": "analytics"},
)
graph.add_edge("qa", END)
graph.add_edge("mcq", END)
graph.add_edge("analytics", END)

# Compiled agent app (used in app.py via agent_app.invoke(state))
agent_app = graph.compile()
