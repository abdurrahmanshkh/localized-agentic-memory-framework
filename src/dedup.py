"""
Deduplication module for Localized Agentic Memory Framework.

Provides 3-tier semantic deduplication:
- Layer 1: SHA-256 exact match
- Layer 2: Vector cosine similarity band
- Layer 3: Local LLM conflict resolution for ambiguous middle band
"""

from __future__ import annotations

import sqlite3
from typing import Any

try:
    from . import config, memory_service
    from .vector_store import VectorStore
except ImportError:
    import config
    import memory_service
    from vector_store import VectorStore


AUTO_DUPLICATE = config.AUTO_DUPLICATE_THRESHOLD
AUTO_DISTINCT = config.AUTO_DISTINCT_THRESHOLD
MODEL = config.MODEL_REASONING


def get_chroma_collection(chroma_dir: Any | None = None) -> Any:
    """Lazily creates or returns the main Chroma collection."""
    store = VectorStore(chroma_dir=chroma_dir)
    return store.get_collection()


def check_similarity(collection: Any, new_fact_text: str) -> tuple[float | None, str | None, str | None]:
    """Returns (similarity, matched_text, matched_id) for the closest existing fact, or (None, None, None)."""
    try:
        total = collection.count()
        if total == 0:
            return None, None, None
        result = collection.query(query_texts=[new_fact_text], n_results=1)
        if not result or not result.get("ids") or not result["ids"][0]:
            return None, None, None
        distance = result["distances"][0][0]
        similarity = max(0.0, min(1.0, 1.0 - distance))
        matched_text = result["documents"][0][0]
        matched_id = result["ids"][0][0]
        return similarity, matched_text, matched_id
    except Exception:
        return None, None, None


def resolve_conflict(existing_fact: str, new_fact: str, client: Any | None = None) -> str:
    """Evaluates whether an ambiguous middle-band fact pair is DUPLICATE, UPDATE, or DISTINCT."""
    return memory_service.resolve_conflict(existing_fact, new_fact, client=client, model=MODEL)


def trigger_deduplication(conn: sqlite3.Connection, vector_store: VectorStore | None = None) -> None:
    """Synchronizes pending facts from SQLite to Chroma vector store without destroying canonical rows."""
    vstore = vector_store or VectorStore()
    unindexed = conn.execute(
        "SELECT id, fact_text, source_session_id, category FROM facts WHERE synced_to_chroma = 0 AND status = 'active'"
    ).fetchall()

    if not unindexed:
        return

    for row in unindexed:
        fact_id = row["id"]
        fact_text = row["fact_text"]
        vstore.add_fact(
            fact_id=fact_id,
            fact_text=fact_text,
            metadata={"source_session_id": str(row["source_session_id"]), "category": str(row["category"])},
        )
        conn.execute("UPDATE facts SET synced_to_chroma = 1 WHERE id = ?", (fact_id,))
    conn.commit()


if __name__ == "__main__":
    from . import db
    with db.get_db() as conn:
        trigger_deduplication(conn)
