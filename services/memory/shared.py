"""Shared memory: cross-agent knowledge base for collaborative context."""

import logging
import time
import uuid
from typing import Optional

from services.memory.chroma_store import ChromaStore, MemoryEntry

logger = logging.getLogger("leetbot.memory.shared")


class SharedMemory:
    """Cross-agent knowledge store.

    Agents can write facts here that benefit other agents. For example, the
    stock agent might save "AAPL hit all-time high on 2026-03-14" which the
    news agent can then reference for context.
    """

    def __init__(self, store: ChromaStore):
        self._store = store
        self._collection = ChromaStore.COLLECTION_SHARED

    def save(
        self,
        content: str,
        source_agent: str,
        topic: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        doc_id = f"shared_{uuid.uuid4().hex[:12]}"
        meta = {
            "source_agent": source_agent,
            "topic": topic or "general",
            "timestamp": time.time(),
        }
        if metadata:
            meta.update(metadata)
        self._store.add(self._collection, doc_id, content, meta)
        return doc_id

    def search(
        self,
        query: str,
        n_results: int = 3,
        source_agent: Optional[str] = None,
    ) -> list[MemoryEntry]:
        where = None
        if source_agent:
            where = {"source_agent": source_agent}
        return self._store.query(
            self._collection,
            query_text=query,
            n_results=n_results,
            where=where,
        )
