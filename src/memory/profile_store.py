# src/memory/profile_store.py
# Profile & episodic memory - key-value store for user profiles and quiz history

from typing import Dict, List, Optional, Any
from datetime import datetime
import json
import copy


class ProfileStore:
    """
    Key-value store for user profiles and episodic memory.
    Stores learner profiles, quiz results, and milestone events.
    In production: replace with Redis, DynamoDB, or PostgreSQL.
    """

    def __init__(self):
        self._profiles: Dict[str, Dict] = {}       # user_id -> UserProfile dict
        self._quiz_history: Dict[str, List] = {}   # user_id -> [QuizResult]
        self._milestones: Dict[str, List] = {}     # user_id -> [milestone events]
        self._study_streak: Dict[str, Dict] = {}   # user_id -> streak data

    # ------------------------------------------------------------------ #
    #  Profile Operations
    # ------------------------------------------------------------------ #

    def create_profile(self, profile_data: Dict) -> str:
        """Create a new learner profile. Returns user_id."""
        user_id = profile_data.get("user_id")
        if not user_id:
            import uuid
            user_id = str(uuid.uuid4())
            profile_data["user_id"] = user_id

        profile_data.setdefault("created_at", datetime.now().isoformat())
        profile_data.setdefault("last_active", datetime.now().isoformat())
        profile_data.setdefault("total_sessions", 0)
        profile_data.setdefault("total_questions_asked", 0)
        profile_data.setdefault("total_quiz_taken", 0)
        profile_data.setdefault("avg_quiz_score", 0.0)
        profile_data.setdefault("areas_of_focus", [])

        self._profiles[user_id] = profile_data
        self._quiz_history.setdefault(user_id, [])
        self._milestones.setdefault(user_id, [])
        self._study_streak[user_id] = {"current": 1, "best": 1, "last_date": datetime.now().strftime("%Y-%m-%d")}
        return user_id

    def get_profile(self, user_id: str) -> Optional[Dict]:
        """Retrieve a user profile by ID."""
        return copy.deepcopy(self._profiles.get(user_id))

    def update_profile(self, user_id: str, updates: Dict) -> bool:
        """Merge updates into an existing profile."""
        if user_id not in self._profiles:
            return False
        self._profiles[user_id].update(updates)
        self._profiles[user_id]["last_active"] = datetime.now().isoformat()
        return True

    def increment_session_count(self, user_id: str) -> None:
        if user_id in self._profiles:
            self._profiles[user_id]["total_sessions"] = self._profiles[user_id].get("total_sessions", 0) + 1
            self._update_streak(user_id)

    def increment_question_count(self, user_id: str) -> None:
        if user_id in self._profiles:
            self._profiles[user_id]["total_questions_asked"] = (
                self._profiles[user_id].get("total_questions_asked", 0) + 1
            )

    def add_area_of_focus(self, user_id: str, topic: str) -> None:
        if user_id in self._profiles:
            areas = self._profiles[user_id].setdefault("areas_of_focus", [])
            if topic not in areas:
                areas.append(topic)

    def profile_exists(self, user_id: str) -> bool:
        return user_id in self._profiles

    def get_all_user_ids(self) -> List[str]:
        return list(self._profiles.keys())

    # ------------------------------------------------------------------ #
    #  Quiz History
    # ------------------------------------------------------------------ #

    def save_quiz_result(self, user_id: str, result: Dict) -> None:
        """Save a completed quiz result and update average score."""
        result["taken_at"] = datetime.now().isoformat()
        self._quiz_history.setdefault(user_id, []).append(result)

        # Update profile stats
        if user_id in self._profiles:
            all_scores = [r.get("score_percent", 0) for r in self._quiz_history[user_id]]
            self._profiles[user_id]["avg_quiz_score"] = sum(all_scores) / len(all_scores)
            self._profiles[user_id]["total_quiz_taken"] = len(self._quiz_history[user_id])

        # Add milestone if score >= 80
        score = result.get("score_percent", 0)
        if score >= 90:
            self.add_milestone(user_id, f"Scored {score:.0f}% on {result.get('topic','?')} quiz! Excellent!")
        elif score >= 80:
            self.add_milestone(user_id, f"Scored {score:.0f}% on {result.get('topic','?')} quiz! Great job!")

    def get_quiz_history(self, user_id: str, last_n: int = 10) -> List[Dict]:
        history = self._quiz_history.get(user_id, [])
        return history[-last_n:]

    def get_weak_topics(self, user_id: str, threshold: float = 60.0) -> List[str]:
        """Return topics where average quiz score is below threshold."""
        topic_scores: Dict[str, List[float]] = {}
        for result in self._quiz_history.get(user_id, []):
            topic = result.get("topic", "Unknown")
            score = result.get("score_percent", 0)
            topic_scores.setdefault(topic, []).append(score)

        weak = []
        for topic, scores in topic_scores.items():
            avg = sum(scores) / len(scores)
            if avg < threshold:
                weak.append(f"{topic} (avg {avg:.0f}%)")
        return weak

    def get_strong_topics(self, user_id: str, threshold: float = 80.0) -> List[str]:
        """Return topics where average quiz score is at or above threshold."""
        topic_scores: Dict[str, List[float]] = {}
        for result in self._quiz_history.get(user_id, []):
            topic = result.get("topic", "Unknown")
            score = result.get("score_percent", 0)
            topic_scores.setdefault(topic, []).append(score)

        strong = []
        for topic, scores in topic_scores.items():
            avg = sum(scores) / len(scores)
            if avg >= threshold:
                strong.append(f"{topic} (avg {avg:.0f}%)")
        return strong

    # ------------------------------------------------------------------ #
    #  Milestone & Streak Tracking
    # ------------------------------------------------------------------ #

    def add_milestone(self, user_id: str, event: str) -> None:
        self._milestones.setdefault(user_id, []).append({
            "event": event,
            "date": datetime.now().isoformat(),
        })

    def get_milestones(self, user_id: str) -> List[Dict]:
        return self._milestones.get(user_id, [])

    def _update_streak(self, user_id: str) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        streak = self._study_streak.setdefault(user_id, {"current": 0, "best": 0, "last_date": ""})
        if streak["last_date"] == today:
            return
        # Simple streak logic
        streak["current"] += 1
        streak["best"] = max(streak["best"], streak["current"])
        streak["last_date"] = today

    def get_streak(self, user_id: str) -> Dict:
        return self._study_streak.get(user_id, {"current": 0, "best": 0})

    # ------------------------------------------------------------------ #
    #  Serialization (for Streamlit session_state persistence)
    # ------------------------------------------------------------------ #

    def export_all(self) -> Dict:
        return {
            "profiles": self._profiles,
            "quiz_history": self._quiz_history,
            "milestones": self._milestones,
            "streaks": self._study_streak,
        }

    def import_all(self, data: Dict) -> None:
        self._profiles = data.get("profiles", {})
        self._quiz_history = data.get("quiz_history", {})
        self._milestones = data.get("milestones", {})
        self._study_streak = data.get("streaks", {})


# Module-level singleton
_profile_store: Optional[ProfileStore] = None

def get_profile_store() -> ProfileStore:
    global _profile_store
    if _profile_store is None:
        _profile_store = ProfileStore()
    return _profile_store
