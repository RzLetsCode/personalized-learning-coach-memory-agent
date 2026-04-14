"""
Production-Grade SQLAlchemy Database Models
Enterprise AI Learning Coach - Multi-Tier Memory System

Author: Enterprise AI Architect
Stack: PostgreSQL + SQLAlchemy + LangGraph
"""

from datetime import datetime, date
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
    Boolean,
    Text,
    JSON,
    Date,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from passlib.context import CryptContext
import uuid

from .db_session import Base

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ===========================================================================
# USER
# ===========================================================================
class User(Base):
    """User authentication and profile management."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_uuid = Column(
        String(50), unique=True, nullable=False, index=True,
        default=lambda: str(uuid.uuid4()),
    )
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)

    # Profile metadata
    full_name = Column(String(200), nullable=True)
    learning_level = Column(String(20), default="beginner")  # beginner | intermediate | advanced
    target_exam = Column(String(100), nullable=True)
    exam_date = Column(DateTime, nullable=True)
    preferred_learning_style = Column(String(50), default="examples")  # examples | mathematical | analogies
    areas_of_focus = Column(JSON, default=list)

    # Gamification
    login_streak = Column(Integer, default=0)
    total_sessions = Column(Integer, default=0)
    total_mcqs_attempted = Column(Integer, default=0)
    total_mcqs_correct = Column(Integer, default=0)

    # Account status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

    # Relationships
    sessions = relationship("StudySession", back_populates="user", cascade="all, delete-orphan")
    mcq_scores = relationship("MCQScore", back_populates="user", cascade="all, delete-orphan")
    knowledge_points = relationship("KnowledgePoint", back_populates="user", cascade="all, delete-orphan")

    # --- helpers ---
    def verify_password(self, plain_password: str) -> bool:
        return pwd_context.verify(plain_password, self.hashed_password)

    @staticmethod
    def hash_password(password: str) -> str:
        return pwd_context.hash(password)

    @property
    def accuracy_rate(self) -> float:
        if self.total_mcqs_attempted == 0:
            return 0.0
        return round((self.total_mcqs_correct / self.total_mcqs_attempted) * 100, 2)


# ===========================================================================
# STUDY SESSION
# ===========================================================================
class StudySession(Base):
    """Session tracking for multi-session memory persistence."""
    __tablename__ = "study_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        String(100), unique=True, nullable=False, index=True,
        default=lambda: f"session_{uuid.uuid4().hex}",
    )
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Timing
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    session_duration_seconds = Column(Integer, default=0)

    # Content tracking
    topics_covered = Column(JSON, default=list)
    questions_asked = Column(Integer, default=0)
    mcqs_attempted_in_session = Column(Integer, default=0)
    mcqs_correct_in_session = Column(Integer, default=0)

    # LangGraph checkpoint reference
    checkpoint_namespace = Column(String(200), nullable=True)

    # Quality metrics
    user_satisfaction_rating = Column(Float, nullable=True)   # 1.0 - 5.0
    identified_knowledge_gaps = Column(JSON, default=list)

    # Relationships
    user = relationship("User", back_populates="sessions")
    mcq_scores = relationship("MCQScore", back_populates="session", cascade="all, delete-orphan")

    @property
    def is_active(self) -> bool:
        return self.ended_at is None


# ===========================================================================
# MCQ SCORE
# ===========================================================================
class MCQScore(Base):
    """MCQ assessment results and adaptive learning metrics."""
    __tablename__ = "mcq_scores"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_db_id = Column(Integer, ForeignKey("study_sessions.id", ondelete="CASCADE"), nullable=False, index=True)

    # Identification
    mcq_id = Column(String(100), index=True, default=lambda: f"mcq_{uuid.uuid4().hex}")
    topic = Column(String(200), nullable=False, index=True)
    difficulty_level = Column(String(20), default="medium")   # easy | medium | hard

    # Content
    question_text = Column(Text, nullable=False)
    options = Column(JSON, nullable=False)                    # {"A": "...", "B": "...", ...}
    correct_answer = Column(String(10), nullable=False)
    user_answer = Column(String(10), nullable=True)

    # Performance
    is_correct = Column(Boolean, default=False)
    time_taken_seconds = Column(Integer, nullable=True)
    attempt_timestamp = Column(DateTime, default=datetime.utcnow)

    # Adaptive metadata
    was_retried = Column(Boolean, default=False)
    confidence_level = Column(String(20), nullable=True)      # high | medium | low
    explanation_requested = Column(Boolean, default=False)

    # Relationships
    user = relationship("User", back_populates="mcq_scores")
    session = relationship("StudySession", back_populates="mcq_scores")

    @property
    def performance_tag(self) -> str:
        if not self.is_correct:
            return "misconception"
        elif self.time_taken_seconds and self.time_taken_seconds < 30:
            return "mastered"
        return "neutral"


# ===========================================================================
# KNOWLEDGE POINT  (SRS / Spaced Repetition)
# ===========================================================================
class KnowledgePoint(Base):
    """
    Spaced Repetition unit per (user, topic).

    Tracks SM-2 style forgetting-curve parameters so the agent can
    proactively schedule reviews instead of only reacting to user prompts.
    """
    __tablename__ = "knowledge_points"
    __table_args__ = (
        UniqueConstraint("user_id", "topic", name="uq_user_topic"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    topic = Column(String(200), nullable=False, index=True)

    # SM-2 fields
    last_seen = Column(DateTime, default=datetime.utcnow)
    ease_factor = Column(Float, default=2.5)        # starts at 2.5, min 1.3
    interval_days = Column(Integer, default=1)      # current inter-review interval
    due_date = Column(Date, default=date.today)     # next review date
    knowledge_score = Column(Float, default=0.0)    # aggregate mastery score

    # Audit
    times_reviewed = Column(Integer, default=0)
    last_quality = Column(Integer, default=0)       # 0-5 quality rating from last review

    # Relationship
    user = relationship("User", back_populates="knowledge_points")
