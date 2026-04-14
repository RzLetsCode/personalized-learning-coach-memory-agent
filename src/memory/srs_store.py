"""
Spaced Repetition System (SRS) store for the Enterprise AI Learning Coach.

Implements SM-2 algorithm over the SQLAlchemy KnowledgePoint model.
This is a separate file from profile_store.py (which handles in-memory
short-term session data). This module handles long-term persistent SRS.
"""

from datetime import datetime, date, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session

from backend.database.models import KnowledgePoint


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def get_or_create_kp(db: Session, user_id: int, topic: str) -> KnowledgePoint:
    """
    Fetch or create a KnowledgePoint for a (user_id, topic) pair.
    """
    kp = (
        db.query(KnowledgePoint)
        .filter(
            KnowledgePoint.user_id == user_id,
            KnowledgePoint.topic == topic,
        )
        .first()
    )
    if kp is None:
        kp = KnowledgePoint(
            user_id=user_id,
            topic=topic,
            last_seen=datetime.utcnow(),
            ease_factor=2.5,
            interval_days=1,
            due_date=date.today(),
            knowledge_score=0.0,
            times_reviewed=0,
            last_quality=0,
        )
        db.add(kp)
        db.commit()
        db.refresh(kp)
    return kp


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def update_after_review(
    db: Session,
    user_id: int,
    topic: str,
    quality: int,
) -> KnowledgePoint:
    """
    Update SRS parameters after a review using simplified SM-2 algorithm.

    quality: 0-5
      0 = complete blackout / total failure
      3 = correct with difficulty
      5 = perfect recall

    Lower quality -> shorter interval (more frequent review).
    Higher quality -> longer interval + higher ease factor.
    """
    quality = max(0, min(5, quality))
    kp = get_or_create_kp(db, user_id, topic)

    # Update ease factor (SM-2 formula)
    ef = kp.ease_factor
    ef = ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    ef = max(1.3, ef)  # never go below 1.3

    # Update interval
    if quality < 3:
        interval = 1  # reset on failure
    elif kp.interval_days <= 1:
        interval = 2
    else:
        interval = max(2, int(kp.interval_days * ef))

    # Persist updates
    kp.ease_factor = round(ef, 4)
    kp.interval_days = interval
    kp.last_seen = datetime.utcnow()
    kp.due_date = date.today() + timedelta(days=interval)
    kp.knowledge_score = max(0.0, kp.knowledge_score + (quality - 2))
    kp.times_reviewed = (kp.times_reviewed or 0) + 1
    kp.last_quality = quality

    db.add(kp)
    db.commit()
    db.refresh(kp)
    return kp


def get_due_topics(
    db: Session,
    user_id: int,
    limit: int = 20,
) -> List[KnowledgePoint]:
    """
    Return topics that are due (or overdue) for review today.
    Ordered by most overdue first.
    """
    today = date.today()
    return (
        db.query(KnowledgePoint)
        .filter(
            KnowledgePoint.user_id == user_id,
            KnowledgePoint.due_date <= today,
        )
        .order_by(KnowledgePoint.due_date)
        .limit(limit)
        .all()
    )


def get_all_knowledge_points(
    db: Session,
    user_id: int,
) -> List[KnowledgePoint]:
    """Return all KnowledgePoints for a user (for analytics dashboard)."""
    return (
        db.query(KnowledgePoint)
        .filter(KnowledgePoint.user_id == user_id)
        .order_by(KnowledgePoint.knowledge_score.desc())
        .all()
    )


def get_mastery_summary(db: Session, user_id: int) -> dict:
    """
    Return a mastery summary dict for the analytics dashboard.
    """
    kps = get_all_knowledge_points(db, user_id)
    if not kps:
        return {"total_topics": 0, "mastered": 0, "needs_review": 0, "new": 0}

    mastered = [k for k in kps if k.knowledge_score >= 5]
    needs_review = [k for k in kps if k.due_date <= date.today()]
    new_topics = [k for k in kps if k.times_reviewed == 0]

    return {
        "total_topics": len(kps),
        "mastered": len(mastered),
        "needs_review": len(needs_review),
        "new": len(new_topics),
        "topics": [
            {
                "topic": k.topic,
                "score": k.knowledge_score,
                "due_date": str(k.due_date),
                "times_reviewed": k.times_reviewed,
            }
            for k in kps
        ],
    }
