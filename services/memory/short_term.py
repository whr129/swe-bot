"""Short-term memory: recent conversations with TTL-based expiration."""

import logging
import time
import uuid
from typing import Optional

from services.memory.chroma_store import ChromaStore, MemoryEntry

logger = logging.getLogger("leetbot.memory.short_term")


class ShortTermMemory:
    """Stores recent conversations with automatic expiry.

    Conversations are embedded and stored in ChromaDB for semantic retrieval.
    Entries older than ``ttl_days`` are pruned periodically.
    """

    def __init__(self, store: ChromaStore, ttl_days: int = 7):
        self._store = store
        self._ttl_seconds = ttl_days * 86400
        self._collection = ChromaStore.COLLECTION_SHORT_TERM

    def add_conversation(
        self,
        user_id: int,
        question: str,
        answer: str,
        agent_name: str,
        metadata: Optional[dict] = None,
    ) -> str:
        doc_id = f"conv_{user_id}_{uuid.uuid4().hex[:12]}"
        content = f"Q: {question}\nA: {answer}"
        meta = {
            "user_id": str(user_id),
            "agent_name": agent_name,
            "type": "conversation",
            "timestamp": time.time(),
        }
        if metadata:
            meta.update(metadata)
        self._store.add(self._collection, doc_id, content, meta)
        return doc_id

    def recall(
        self,
        user_id: int,
        query: str,
        agent_name: Optional[str] = None,
        limit: int = 5,
    ) -> list[MemoryEntry]:
        where: dict = {"user_id": str(user_id)}
        if agent_name:
            where = {"$and": [{"user_id": str(user_id)}, {"agent_name": agent_name}]}
        return self._store.query(
            self._collection,
            query_text=query,
            n_results=limit,
            where=where,
        )

    def prune(self) -> int:
        return self._store.prune_by_age(self._collection, self._ttl_seconds)
