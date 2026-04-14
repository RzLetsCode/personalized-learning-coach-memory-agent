# src/memory/short_term.py
# Short-term session memory - sliding window conversation history

from typing import List, Dict, Any, Optional
from datetime import datetime


class ShortTermMemory:
    """In-memory session store (thread-scoped). Replace with LangGraph SqliteSaver in production."""

    def __init__(self, max_turns: int = 20):
        self.max_turns = max_turns
        self._sessions: Dict[str, List[Dict[str, Any]]] = {}
        self._metadata: Dict[str, Dict] = {}

    def start_session(self, thread_id: str, user_id: str) -> None:
        if thread_id not in self._sessions:
            self._sessions[thread_id] = []
            self._metadata[thread_id] = {
                "user_id": user_id,
                "started_at": datetime.now().isoformat(),
                "turn_count": 0,
            }

    def add_turn(self, thread_id: str, role: str, content: str, metadata: Optional[Dict] = None) -> None:
        if thread_id not in self._sessions:
            self._sessions[thread_id] = []
            self._metadata[thread_id] = {"turn_count": 0}
        turn = {"role": role, "content": content, "timestamp": datetime.now().isoformat(), **(metadata or {})}
        self._sessions[thread_id].append(turn)
        self._metadata[thread_id]["turn_count"] = self._metadata[thread_id].get("turn_count", 0) + 1
        # Sliding window
        if len(self._sessions[thread_id]) > self.max_turns * 2:
            self._sessions[thread_id] = self._sessions[thread_id][-self.max_turns * 2:]

    def get_history(self, thread_id: str, last_n: int = 10) -> List[Dict]:
        turns = self._sessions.get(thread_id, [])
        return turns[-last_n:] if last_n else turns

    def get_full_history(self, thread_id: str) -> List[Dict]:
        return self._sessions.get(thread_id, [])

    def get_formatted_history(self, thread_id: str, last_n: int = 6) -> str:
        turns = self.get_history(thread_id, last_n)
        return "\n".join(f"{t.get('role','user').upper()}: {t.get('content','')[:400]}" for t in turns)

    def clear_session(self, thread_id: str) -> None:
        self._sessions.pop(thread_id, None)
        self._metadata.pop(thread_id, None)

    def get_session_metadata(self, thread_id: str) -> Dict:
        return self._metadata.get(thread_id, {})

    def session_exists(self, thread_id: str) -> bool:
        return thread_id in self._sessions

    def get_turn_count(self, thread_id: str) -> int:
        return self._metadata.get(thread_id, {}).get("turn_count", 0)

    def export_session(self, thread_id: str) -> Dict:
        return {"history": self._sessions.get(thread_id, []), "metadata": self._metadata.get(thread_id, {})}

    def import_session(self, thread_id: str, data: Dict) -> None:
        self._sessions[thread_id] = data.get("history", [])
        self._metadata[thread_id] = data.get("metadata", {})


_store_instance: Optional[ShortTermMemory] = None

def get_short_term_store(max_turns: int = 20) -> ShortTermMemory:
    global _store_instance
    if _store_instance is None:
        _store_instance = ShortTermMemory(max_turns=max_turns)
    return _store_instance
