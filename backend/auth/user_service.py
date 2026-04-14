"""
User CRUD service for the Enterprise AI Learning Coach.

Handles user registration, authentication, profile updates,
and session management - all persisted via SQLAlchemy.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from backend.database.models import User, StudySession
from backend.auth.security import hash_password, verify_password


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------
def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """Fetch user by email address."""
    return db.query(User).filter(User.email == email).first()


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    """Fetch user by username."""
    return db.query(User).filter(User.username == username).first()


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    """Fetch user by primary key."""
    return db.query(User).filter(User.id == user_id).first()


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------
def create_user(
    db: Session,
    username: str,
    email: str,
    password: str,
    full_name: str = "",
    learning_level: str = "beginner",
    preferred_learning_style: str = "examples",
) -> User:
    """
    Register a new user.
    Raises ValueError if email or username already exists.
    """
    if get_user_by_email(db, email):
        raise ValueError(f"Email '{email}' is already registered.")
    if get_user_by_username(db, username):
        raise ValueError(f"Username '{username}' is already taken.")

    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        learning_level=learning_level,
        preferred_learning_style=preferred_learning_style,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """
    Verify credentials.
    Returns the User object on success, None on failure.
    """
    user = get_user_by_email(db, email)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    user.last_login = datetime.utcnow()
    user.login_streak = (user.login_streak or 0) + 1
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Profile updates
# ---------------------------------------------------------------------------
def update_user_profile(
    db: Session,
    user_id: int,
    full_name: Optional[str] = None,
    learning_level: Optional[str] = None,
    target_exam: Optional[str] = None,
    preferred_learning_style: Optional[str] = None,
    areas_of_focus: Optional[list] = None,
) -> Optional[User]:
    """Partially update user profile fields."""
    user = get_user_by_id(db, user_id)
    if not user:
        return None
    if full_name is not None:
        user.full_name = full_name
    if learning_level is not None:
        user.learning_level = learning_level
    if target_exam is not None:
        user.target_exam = target_exam
    if preferred_learning_style is not None:
        user.preferred_learning_style = preferred_learning_style
    if areas_of_focus is not None:
        user.areas_of_focus = areas_of_focus
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------
def start_study_session(db: Session, user_id: int) -> StudySession:
    """Create and persist a new study session for the user."""
    session = StudySession(user_id=user_id)
    db.add(session)
    user = get_user_by_id(db, user_id)
    if user:
        user.total_sessions = (user.total_sessions or 0) + 1
    db.commit()
    db.refresh(session)
    return session


def end_study_session(
    db: Session,
    session_db_id: int,
    topics_covered: Optional[list] = None,
    satisfaction_rating: Optional[float] = None,
) -> Optional[StudySession]:
    """Mark a study session as ended and save optional metadata."""
    session = db.query(StudySession).filter(StudySession.id == session_db_id).first()
    if not session:
        return None
    session.ended_at = datetime.utcnow()
    if session.started_at:
        delta = session.ended_at - session.started_at
        session.session_duration_seconds = int(delta.total_seconds())
    if topics_covered is not None:
        session.topics_covered = topics_covered
    if satisfaction_rating is not None:
        session.user_satisfaction_rating = satisfaction_rating
    db.commit()
    db.refresh(session)
    return session
