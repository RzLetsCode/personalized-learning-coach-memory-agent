"""
Pydantic schemas for all memory documents used in the Learning Coach agent.
Includes both existing profile/quiz schemas and LangGraph AgentState.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Any
from datetime import datetime
import uuid


# ===========================================================================
# EXISTING PROFILE & QUIZ SCHEMAS (unchanged)
# ===========================================================================

class UserProfile(BaseModel):
    """Persistent profile for each learner, stored in the key-value profile store."""
    user_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    level: Literal["beginner", "intermediate", "advanced"] = "beginner"
    target_topic: str = "General AI/ML"
    exam_date: Optional[str] = None
    preferred_style: Literal["examples", "mathematical", "analogies", "visual"] = "examples"
    areas_of_focus: List[str] = Field(default_factory=list)
    total_sessions: int = 0
    total_questions_asked: int = 0
    total_quiz_taken: int = 0
    avg_quiz_score: float = 0.0
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    last_active: str = Field(default_factory=lambda: datetime.now().isoformat())

    class Config:
        extra = "allow"


class QAMemory(BaseModel):
    """A single Q&A interaction stored in the semantic vector store."""
    memory_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    topic: str
    user_question: str
    assistant_answer: str
    tag: Literal["misconception", "mastered", "neutral"] = "neutral"
    confidence_score: float = 0.5
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class SessionSummary(BaseModel):
    """End-of-session summary stored in the vector store for cross-session retrieval."""
    summary_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    session_number: int
    date: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    topics_covered: List[str] = Field(default_factory=list)
    difficulties: List[str] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    recommended_next_topics: List[str] = Field(default_factory=list)
    mood: Literal["confident", "neutral", "struggling"] = "neutral"


class QuizQuestion(BaseModel):
    """A single quiz question with multiple choice options."""
    question_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    topic: str
    question_text: str
    question_type: Literal["mcq", "true_false", "fill_blank"] = "mcq"
    options: List[str] = Field(default_factory=list)
    correct_answer: str
    explanation: str
    difficulty: Literal["easy", "medium", "hard"] = "medium"


class QuizResult(BaseModel):
    """Result of a completed quiz session stored in the profile store."""
    quiz_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    topic: str
    num_questions: int
    num_correct: int
    score_percent: float
    difficulty: str
    weak_areas: List[str] = Field(default_factory=list)
    strong_areas: List[str] = Field(default_factory=list)
    taken_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class MemoryUpdateInstruction(BaseModel):
    """Structured JSON the LLM returns after each turn, instructing memory writes."""
    new_qa_memories: List[dict] = Field(default_factory=list)
    session_note: Optional[str] = None
    update_profile_fields: dict = Field(default_factory=dict)
    detected_misconceptions: List[str] = Field(default_factory=list)
    detected_strengths: List[str] = Field(default_factory=list)
    recommended_topics: List[str] = Field(default_factory=list)
    confidence_estimate: float = 0.5


# ===========================================================================
# LANGGRAPH AGENT STATE (added at bottom - coexists with above)
# ===========================================================================

IntentType = Literal["qa", "mcq", "analytics"]


class Message(BaseModel):
    """A single chat message in the agent conversation."""
    role: Literal["user", "assistant"]
    content: str


class AgentState(BaseModel):
    """
    Shared LangGraph state for the Personalized Learning Coach.
    Flows through every node in the graph.
    """
    messages: List[Message] = Field(default_factory=list)
    intent: Optional[IntentType] = None
    user_id: Optional[int] = None              # SQLAlchemy User.id (int PK)
    session_db_id: Optional[int] = None        # Active StudySession.id
    mcq_context: Optional[Any] = None          # Parsed MCQ dict from mcq_node
    analytics_request: Optional[str] = None    # Analytics sub-query string
    retrieved_context: Optional[str] = None    # Pinecone RAG context string
    topic: Optional[str] = None                # Detected topic for SRS update
