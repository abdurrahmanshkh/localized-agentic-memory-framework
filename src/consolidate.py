"""
Consolidation module (facade for memory_service).

Provides backward compatibility for existing scripts while delegating to the
authoritative, recoverable memory_service engine.
"""

from __future__ import annotations

import sqlite3
from typing import Any

try:
    from . import memory_service
except ImportError:
    import memory_service


def format_rows_as_transcript(rows: list[Any]) -> str:
    """Formats conversation rows into a transcript."""
    return memory_service.format_transcript(rows)


def get_facts(transcript: str, client: Any | None = None) -> list[str] | None:
    """Extracts atomic facts from a transcript."""
    from .config import MODEL_EXTRACTION
    from .models import LocalOllamaClient
    from .prompts import get_facts_prompt

    mclient = client or LocalOllamaClient()
    prompt = get_facts_prompt(transcript)
    try:
        reply = mclient.chat(MODEL_EXTRACTION, [{"role": "user", "content": prompt}])
        facts = memory_service.parse_extracted_facts(reply)
        return facts if facts else None
    except Exception:
        return None


def hash_converter(fact_list: list[str]) -> list[tuple[str, str]]:
    """Converts a list of facts into (text, sha256_hash) tuples."""
    return [(fact, memory_service.hash_fact(fact)) for fact in fact_list]


def trigger_consolidation(conn: sqlite3.Connection, session_id: str) -> dict[str, Any]:
    """Runs end-to-end recoverable session consolidation."""
    return memory_service.consolidate_session(conn, session_id)


if __name__ == "__main__":
    from . import db
    with db.get_db() as conn:
        print("Running consolidation check...")
