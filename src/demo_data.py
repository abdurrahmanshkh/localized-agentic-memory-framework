"""
Synthetic demo dataset loader for academic presentations, vivas, and test evaluations.

Provides clean, non-personal sample facts that demonstrate semantic recall,
conflict updates, and deduplication without polluting personal memory stores.
"""

from __future__ import annotations

import sqlite3
from typing import Any

try:
    from . import memory_service
    from .vector_store import VectorStore
except ImportError:
    import memory_service
    from vector_store import VectorStore


SYNTHETIC_DEMO_FACTS = [
    {
        "fact_text": "User is a final year computer engineering student.",
        "category": "Academic",
    },
    {
        "fact_text": "User is developing the Localized Agentic Memory Framework for their final year project.",
        "category": "Project",
    },
    {
        "fact_text": "User prefers direct, concise answers without conversational small talk.",
        "category": "Preferences",
    },
    {
        "fact_text": "User works with Python, SQLite, and ChromaDB on local consumer hardware.",
        "category": "Technical",
    },
    {
        "fact_text": "User is based in Navi Mumbai.",
        "category": "Profile",
    },
    {
        "fact_text": "User is focused on local edge-AI inference using Ollama.",
        "category": "Technical",
    },
    {
        "fact_text": "User's capstone project presentation is scheduled for next month.",
        "category": "Academic",
    },
]


def load_synthetic_demo_data(
    conn: sqlite3.Connection,
    vector_store: VectorStore,
) -> dict[str, Any]:
    """Loads synthetic facts into the active database and vector store with 'demo' tags."""
    imported_count = 0
    skipped_count = 0

    for item in SYNTHETIC_DEMO_FACTS:
        text = item["fact_text"]
        cat = item["category"]
        f_hash = memory_service.hash_fact(text)

        existing = conn.execute(
            "SELECT id FROM facts WHERE fact_hash = ? AND status = 'active'",
            (f_hash,),
        ).fetchone()

        if existing:
            skipped_count += 1
            continue

        with conn:
            cursor = conn.execute(
                """
                INSERT INTO facts (
                    fact_text, fact_hash, source_session_id, synced_to_chroma, status, category
                ) VALUES (?, ?, 'synthetic_demo', 1, 'active', ?)
                """,
                (text, f_hash, f"demo_{cat.lower()}"),
            )
            new_id = cursor.lastrowid or 0
            vector_store.add_fact(
                fact_id=new_id,
                fact_text=text,
                metadata={"source_session_id": "synthetic_demo", "category": cat, "is_demo": "true"},
            )
            conn.execute("UPDATE facts SET embedding_id = ? WHERE id = ?", (str(new_id), new_id))
            imported_count += 1

    return {
        "status": "success",
        "imported": imported_count,
        "skipped": skipped_count,
        "total_demo_facts": len(SYNTHETIC_DEMO_FACTS),
    }


def clear_synthetic_demo_data(
    conn: sqlite3.Connection,
    vector_store: VectorStore,
) -> int:
    """Removes only synthetic demo records, preserving any genuine user memories."""
    demo_rows = conn.execute(
        "SELECT id FROM facts WHERE source_session_id = 'synthetic_demo' OR category LIKE 'demo_%'"
    ).fetchall()

    if not demo_rows:
        return 0

    demo_ids = [r["id"] for r in demo_rows]
    for fid in demo_ids:
        vector_store.delete_fact(fid)

    placeholders = ",".join("?" for _ in demo_ids)
    with conn:
        cursor = conn.execute(
            f"DELETE FROM facts WHERE id IN ({placeholders})",
            demo_ids,
        )
        return cursor.rowcount
