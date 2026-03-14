"""Long-term memory: persistent facts, preferences, and curated knowledge."""

import logging
import time
import uuid
from typing import Any, Optional

from services.memory.chroma_store import ChromaStore, MemoryEntry

logger = logging.getLogger("leetbot.memory.long_term")


class LongTermMemory:
    """Persistent memory for preferences, facts, and important insights.

    Unlike short-term memory, entries here do NOT expire automatically.
    """

    def __init__(self, store: ChromaStore):
        self._store = store
        self._collection = ChromaStore.COLLECTION_LONG_TERM

    def save_preference(self, user_id: int, key: str, value: Any) -> str:
        doc_id = f"pref_{user_id}_{key}"
        content = f"User preference — {key}: {value}"
        meta = {
            "user_id": str(user_id),
            "category": "preference",
            "key": key,
            "timestamp": time.time(),
        }
        self._store.add(self._collection, doc_id, content, meta)
        return doc_id

    def save_fact(
        self,
        user_id: int,
        fact: str,
        agent_name: str,
        importance: str = "normal",
    ) -> str:
        doc_id = f"fact_{user_id}_{uuid.uuid4().hex[:12]}"
        meta = {
            "user_id": str(user_id),
            "agent_name": agent_name,
            "category": "fact",
            "importance": importance,
            "timestamp": time.time(),
        }
        self._store.add(self._collection, doc_id, fact, meta)
        return doc_id

    def recall(
        self,
        user_id: int,
        query: str,
        limit: int = 5,
    ) -> list[MemoryEntry]:
        return self._store.query(
            self._collection,
            query_text=query,
            n_results=limit,
            where={"user_id": str(user_id)},
        )

    def get_preferences(self, user_id: int) -> dict[str, Any]:
        """Return all preferences for a user as a key->value dict."""
        try:
            results = self._store._col(self._collection).get(
                where={
                    "$and": [
                        {"user_id": str(user_id)},
                        {"category": "preference"},
                    ]
                },
            )
        except Exception:
            return {}

        prefs: dict[str, Any] = {}
        for i, doc in enumerate(results.get("documents", [])):
            meta = results["metadatas"][i] if i < len(results.get("metadatas", [])) else {}
            key = meta.get("key", "")
            if key and doc:
                value_part = doc.split(": ", 1)[-1] if ": " in doc else doc
                prefs[key] = value_part
        return prefs
