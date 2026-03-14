"""RAG-based memory system backed by ChromaDB.

Provides short-term, long-term, and shared memory through a unified
MemoryManager facade.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from services.memory.chroma_store import ChromaStore, MemoryEntry
from services.memory.long_term import LongTermMemory
from services.memory.shared import SharedMemory
from services.memory.short_term import ShortTermMemory

logger = logging.getLogger("leetbot.memory")

__all__ = [
    "MemoryManager",
    "MemoryContext",
    "MemoryEntry",
    "ChromaStore",
    "ShortTermMemory",
    "LongTermMemory",
    "SharedMemory",
]


@dataclass
class MemoryContext:
    """Aggregated memory context returned by recall."""

    recent_conversations: list[dict] = field(default_factory=list)
    relevant_facts: list[dict] = field(default_factory=list)
    preferences: dict[str, Any] = field(default_factory=dict)
    shared_context: list[dict] = field(default_factory=list)

    def is_empty(self) -> bool:
        return (
            not self.recent_conversations
            and not self.relevant_facts
            and not self.preferences
            and not self.shared_context
        )

    def to_prompt_block(self, user_id: int) -> str:
        if self.is_empty():
            return ""
        data = {
            "recent_conversations": self.recent_conversations,
            "relevant_facts": self.relevant_facts,
            "preferences": self.preferences,
            "shared_context": self.shared_context,
        }
        return (
            f"\n\n[User memory for Discord user {user_id}]:\n"
            + json.dumps(data, default=str, ensure_ascii=False)
        )


class MemoryManager:
    """Unified facade for the RAG memory system.

    Agents interact with this class; it delegates to the appropriate
    short-term, long-term, and shared stores.
    """

    def __init__(
        self,
        persist_dir: str = "data/chromadb",
        openai_api_key: Optional[str] = None,
        embedding_model: str = "text-embedding-3-small",
        short_term_ttl_days: int = 7,
        recall_limit: int = 5,
    ):
        self._store = ChromaStore(
            persist_dir=persist_dir,
            openai_api_key=openai_api_key,
            embedding_model=embedding_model,
        )
        self.short_term = ShortTermMemory(self._store, ttl_days=short_term_ttl_days)
        self.long_term = LongTermMemory(self._store)
        self.shared = SharedMemory(self._store)
        self._recall_limit = recall_limit

    def recall(
        self,
        user_id: int,
        query: str,
        agent_name: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> MemoryContext:
        """Semantic recall across all memory layers."""
        n = limit or self._recall_limit

        conversations = self.short_term.recall(user_id, query, agent_name=agent_name, limit=n)
        facts = self.long_term.recall(user_id, query, limit=n)
        preferences = self.long_term.get_preferences(user_id)
        shared = self.shared.search(query, n_results=min(n, 3))

        return MemoryContext(
            recent_conversations=[
                {"content": e.content, "score": round(e.score, 3)}
                for e in conversations
            ],
            relevant_facts=[
                {"content": e.content, "importance": e.metadata.get("importance", "normal"), "score": round(e.score, 3)}
                for e in facts
            ],
            preferences=preferences,
            shared_context=[
                {"content": e.content, "source": e.metadata.get("source_agent", ""), "score": round(e.score, 3)}
                for e in shared
            ],
        )

    def add_conversation(
        self,
        user_id: int,
        question: str,
        answer: str,
        agent_name: str,
        metadata: Optional[dict] = None,
    ) -> str:
        return self.short_term.add_conversation(
            user_id, question, answer, agent_name, metadata
        )

    def save_fact(
        self,
        user_id: int,
        fact: str,
        agent_name: str,
        importance: str = "normal",
    ) -> str:
        return self.long_term.save_fact(user_id, fact, agent_name, importance)

    def save_preference(self, user_id: int, key: str, value: Any) -> str:
        return self.long_term.save_preference(user_id, key, value)

    def save_shared(
        self,
        content: str,
        source_agent: str,
        topic: Optional[str] = None,
    ) -> str:
        return self.shared.save(content, source_agent, topic)

    def prune_short_term(self) -> int:
        return self.short_term.prune()
