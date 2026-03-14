"""ChromaDB wrapper providing vector store operations for the memory system."""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

logger = logging.getLogger("leetbot.memory.chroma")


@dataclass
class MemoryEntry:
    """Single memory entry returned from a query."""

    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    entry_id: str = ""


class ChromaStore:
    """Thin wrapper around ChromaDB for the three memory collections."""

    COLLECTION_SHORT_TERM = "short_term"
    COLLECTION_LONG_TERM = "long_term"
    COLLECTION_SHARED = "shared"

    def __init__(
        self,
        persist_dir: str = "data/chromadb",
        openai_api_key: Optional[str] = None,
        embedding_model: str = "text-embedding-3-small",
    ):
        persist_path = Path(persist_dir)
        persist_path.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(path=str(persist_path))

        if openai_api_key:
            self._embed_fn = OpenAIEmbeddingFunction(
                api_key=openai_api_key,
                model_name=embedding_model,
            )
        else:
            self._embed_fn = chromadb.utils.embedding_functions.DefaultEmbeddingFunction()

        self._collections: dict[str, chromadb.Collection] = {}
        for name in (
            self.COLLECTION_SHORT_TERM,
            self.COLLECTION_LONG_TERM,
            self.COLLECTION_SHARED,
        ):
            self._collections[name] = self._client.get_or_create_collection(
                name=name,
                embedding_function=self._embed_fn,
                metadata={"hnsw:space": "cosine"},
            )

    def _col(self, name: str) -> chromadb.Collection:
        return self._collections[name]

    def add(
        self,
        collection: str,
        doc_id: str,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        meta = metadata or {}
        meta.setdefault("timestamp", time.time())
        self._col(collection).upsert(
            ids=[doc_id],
            documents=[content],
            metadatas=[meta],
        )

    def query(
        self,
        collection: str,
        query_text: str,
        n_results: int = 5,
        where: Optional[dict] = None,
    ) -> list[MemoryEntry]:
        col = self._col(collection)
        try:
            count = col.count()
        except Exception:
            count = 0
        if count == 0:
            return []

        effective_n = min(n_results, count)
        if effective_n == 0:
            return []

        kwargs: dict[str, Any] = {
            "query_texts": [query_text],
            "n_results": effective_n,
        }
        if where:
            kwargs["where"] = where

        try:
            results = col.query(**kwargs)
        except Exception as e:
            logger.warning("ChromaDB query failed: %s", e)
            return []

        entries: list[MemoryEntry] = []
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for i, doc_id in enumerate(ids):
            score = 1.0 - distances[i] if i < len(distances) else 0.0
            entries.append(MemoryEntry(
                content=docs[i] if i < len(docs) else "",
                metadata=metadatas[i] if i < len(metadatas) else {},
                score=score,
                entry_id=doc_id,
            ))

        return entries

    def delete(
        self,
        collection: str,
        where: Optional[dict] = None,
        ids: Optional[list[str]] = None,
    ) -> None:
        col = self._col(collection)
        if ids:
            col.delete(ids=ids)
        elif where:
            col.delete(where=where)

    def prune_by_age(self, collection: str, max_age_seconds: float) -> int:
        """Delete entries older than max_age_seconds. Returns count deleted."""
        col = self._col(collection)
        cutoff = time.time() - max_age_seconds
        try:
            old = col.get(where={"timestamp": {"$lt": cutoff}})
        except Exception:
            return 0
        old_ids = old.get("ids", [])
        if old_ids:
            col.delete(ids=old_ids)
        return len(old_ids)

    def count(self, collection: str, where: Optional[dict] = None) -> int:
        col = self._col(collection)
        if where:
            try:
                results = col.get(where=where)
                return len(results.get("ids", []))
            except Exception:
                return 0
        return col.count()
