"""
Authoritative memory service for Localized Agentic Memory Framework.

Manages the complete lifecycle:
- Conversation ingestion and fact extraction
- 3-Layer deduplication (hash -> vector similarity -> LLM conflict resolution)
- Canonical SQLite updates with provenance and superseding history
- Vector index synchronization and reconciliation
- Memory Studio CRUD operations and export/import
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime
from typing import Any

try:
    from . import config, db, prompts
    from .models import LocalOllamaClient, OllamaClientInterface
    from .vector_store import VectorStore
except ImportError:
    import config
    import db
    import prompts
    from models import LocalOllamaClient, OllamaClientInterface
    from vector_store import VectorStore


def hash_fact(text: str) -> str:
    """Computes SHA-256 hash of normalized fact text."""
    normalized = " ".join(text.strip().lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def parse_extracted_facts(model_output: str) -> list[str]:
    """Extracts bulleted fact statements from model output, handling NO_FACTS and edge cases."""
    stripped = model_output.strip()
    if not stripped or stripped.upper() == "NO_FACTS" or "NO_FACTS" in stripped.splitlines()[0]:
        return []

    facts: list[str] = []
    for line in stripped.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- ") or line.startswith("* "):
            content = line[2:].strip()
            if content and content.upper() != "NO_FACTS":
                facts.append(content)
        elif line.startswith("• "):
            content = line[2:].strip()
            if content:
                facts.append(content)
    return facts


def parse_conflict_decision(decision_raw: str) -> str:
    """Strictly parses LLM conflict resolution decision without false duplicate positives."""
    normalized = decision_raw.strip().upper()
    tokens = [t.strip(".,;:!()[]'\"") for t in normalized.split()]

    if "DUPLICATE" in tokens:
        # Check for negation: e.g. "NOT DUPLICATE" or "NOT A DUPLICATE"
        if "NOT" in tokens or "NON" in tokens:
            return "DISTINCT"
        return "DUPLICATE"
    elif "UPDATE" in tokens:
        return "UPDATE"
    elif "DISTINCT" in tokens or "DIFFERENT" in tokens:
        return "DISTINCT"

    # Conservative fallback: treat as DISTINCT to prevent destructive false merges
    return "DISTINCT"


def resolve_conflict(
    existing_fact: str,
    new_fact: str,
    client: OllamaClientInterface | None = None,
    model: str | None = None,
) -> str:
    """Calls LLM for ambiguous middle-band pairs to determine DUPLICATE, UPDATE, or DISTINCT."""
    client = client or LocalOllamaClient()
    target_model = model or config.MODEL_REASONING
    prompt = prompts.get_conflict_resolution_prompt(existing_fact, new_fact)
    try:
        reply = client.chat(target_model, [{"role": "user", "content": prompt}])
        return parse_conflict_decision(reply)
    except Exception:
        # If model is unavailable or fails, fallback conservatively to DISTINCT
        return "DISTINCT"


def format_transcript(rows: list[sqlite3.Row]) -> str:
    """Formats conversation rows into a standard transcript for LLM fact extraction."""
    lines = []
    for r in rows:
        role = r["role"].upper()
        content = r["content"].strip()
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def has_conflicting_numbers_or_negation(fact_a: str, fact_b: str) -> bool:
    """Detects whether two facts differ on numbers, dates, or negation keywords."""
    import re
    # Extract numerical tokens (integers, years, dates)
    nums_a = set(re.findall(r'\b\d+\b', fact_a))
    nums_b = set(re.findall(r'\b\d+\b', fact_b))
    if nums_a != nums_b:
        return True

    # Check polarity / negation keywords
    negations = {
        "not", "never", "no", "dislike", "dislikes", "disliked",
        "hates", "hate", "unemployed", "stopped", "quit", "neither", "nor"
    }
    words_a = {w.lower() for w in re.findall(r'\b\w+\b', fact_a)}
    words_b = {w.lower() for w in re.findall(r'\b\w+\b', fact_b)}
    if (words_a & negations) != (words_b & negations):
        return True

    return False


def consolidate_session(
    conn: sqlite3.Connection,
    session_id: str,
    client: OllamaClientInterface | None = None,
    vector_store: VectorStore | None = None,
    retain_raw: bool = True,
    chunk_size: int = 50,
) -> dict[str, Any]:
    """Consolidates unconsolidated conversation turns for a session into durable memories.

    Idempotent and recoverable: processes in chunked batches, performs 3-tier
    deduplication, maintains canonical records in SQLite, and synchronizes Chroma vectors.
    """
    vstore = vector_store or VectorStore()
    mclient = client or LocalOllamaClient()

    # 1. Fetch all unconsolidated turns for this session
    unconsolidated_rows = conn.execute(
        "SELECT id, role, content FROM conversations WHERE session_id = ? AND consolidated = 0 ORDER BY id ASC",
        (session_id,),
    ).fetchall()

    if not unconsolidated_rows:
        return {
            "status": "empty",
            "message": "No unconsolidated turns to process.",
            "facts_extracted": 0,
            "facts_added": 0,
            "duplicates": 0,
            "updates": 0,
        }

    total_extracted = 0
    total_added = 0
    total_dupes = 0
    total_updates = 0
    processed_turn_ids: list[int] = []

    # 2. Process turns in chunks to avoid context overflows and silent dropped turns
    for i in range(0, len(unconsolidated_rows), chunk_size):
        chunk = unconsolidated_rows[i : i + chunk_size]
        chunk_ids = [r["id"] for r in chunk]
        transcript = format_transcript(chunk)

        # Call extraction model
        prompt = prompts.get_facts_prompt(transcript)
        try:
            extraction_reply = mclient.chat(
                config.MODEL_EXTRACTION,
                [{"role": "user", "content": prompt}],
            )
            extracted_facts = parse_extracted_facts(extraction_reply)
        except Exception as e:
            # Re-raise to alert caller without marking turns complete
            raise RuntimeError(f"Fact extraction failed on session {session_id}: {e}") from e

        total_extracted += len(extracted_facts)

        # 3. Deduplicate and store each extracted fact
        for fact_text in extracted_facts:
            f_hash = hash_fact(fact_text)

            # Layer 1: Exact Hash Match in SQLite
            exact_match = conn.execute(
                "SELECT id, fact_text FROM facts WHERE fact_hash = ? AND status = 'active'",
                (f_hash,),
            ).fetchone()

            if exact_match:
                total_dupes += 1
                continue

            # Layer 2: Vector Similarity in ChromaDB
            sim, matched_text, matched_id = vstore.check_similarity(fact_text)

            decision = "DISTINCT"
            if sim is not None and matched_text is not None and matched_id is not None:
                has_hard_diff = has_conflicting_numbers_or_negation(matched_text, fact_text)
                if sim >= config.AUTO_DUPLICATE_THRESHOLD and not has_hard_diff:
                    decision = "DUPLICATE"
                elif sim < config.AUTO_DISTINCT_THRESHOLD:
                    decision = "DISTINCT"
                else:
                    # Layer 3: LLM Conflict Resolution for ambiguous middle-band or hard diffs
                    decision = resolve_conflict(matched_text, fact_text, client=mclient)

            if decision == "DUPLICATE":
                total_dupes += 1
                continue

            # Insert fact into canonical SQLite store
            with db.transaction(conn):
                cursor = conn.execute(
                    """
                    INSERT INTO facts (
                        fact_text, fact_hash, source_session_id, synced_to_chroma, status, category
                    ) VALUES (?, ?, ?, 1, 'active', 'general')
                    """,
                    (fact_text, f_hash, session_id),
                )
                new_fact_id = cursor.lastrowid or 0

                if decision == "UPDATE" and matched_id is not None:
                    # Supersede the existing fact in SQLite
                    conn.execute(
                        "UPDATE facts SET status = 'superseded', superseded_by_id = ? WHERE id = ?",
                        (new_fact_id, int(matched_id)),
                    )
                    # Update vector index: remove old, add new
                    vstore.delete_fact(matched_id)
                    vstore.add_fact(
                        fact_id=new_fact_id,
                        fact_text=fact_text,
                        metadata={"source_session_id": session_id, "category": "general"},
                    )
                    total_updates += 1
                else:
                    # DISTINCT new fact: index into vector store
                    vstore.add_fact(
                        fact_id=new_fact_id,
                        fact_text=fact_text,
                        metadata={"source_session_id": session_id, "category": "general"},
                    )
                    total_added += 1

                # Update embedding_id reference
                conn.execute(
                    "UPDATE facts SET embedding_id = ? WHERE id = ?",
                    (str(new_fact_id), new_fact_id),
                )

        processed_turn_ids.extend(chunk_ids)

    # 4. Mark all processed turns as consolidated
    if processed_turn_ids:
        placeholders = ",".join("?" for _ in processed_turn_ids)
        with db.transaction(conn):
            conn.execute(
                f"UPDATE conversations SET consolidated = 1 WHERE id IN ({placeholders})",
                processed_turn_ids,
            )

    # 5. Configurable retention cleanup (only if explicitly opted out of raw retention)
    if not retain_raw and processed_turn_ids:
        with db.transaction(conn):
            placeholders = ",".join("?" for _ in processed_turn_ids)
            conn.execute(
                f"DELETE FROM conversations WHERE id IN ({placeholders})",
                processed_turn_ids,
            )

    return {
        "status": "success",
        "session_id": session_id,
        "turns_processed": len(processed_turn_ids),
        "facts_extracted": total_extracted,
        "facts_added": total_added,
        "duplicates": total_dupes,
        "updates": total_updates,
    }


# ---------------------------------------------------------
# Memory Studio Management Operations
# ---------------------------------------------------------
def list_memories(
    conn: sqlite3.Connection,
    status: str = "active",
    search_query: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Retrieves paginated memories from canonical SQLite store with optional filtering."""
    base_query = """
        SELECT id, fact_text, fact_hash, embedding_id, consolidated_date,
               source_session_id, synced_to_chroma, status, superseded_by_id,
               updated_at, category
        FROM facts
    """
    conditions = []
    params: list[Any] = []

    if status and status != "all":
        conditions.append("status = ?")
        params.append(status)

    if search_query and search_query.strip():
        conditions.append("fact_text LIKE ?")
        params.append(f"%{search_query.strip()}%")

    if conditions:
        base_query += " WHERE " + " AND ".join(conditions)

    base_query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(base_query, params).fetchall()
    return [dict(r) for r in rows]


def get_memory(conn: sqlite3.Connection, fact_id: int) -> dict[str, Any] | None:
    """Fetches a single memory record by ID."""
    row = conn.execute("SELECT * FROM facts WHERE id = ?", (fact_id,)).fetchone()
    return dict(row) if row else None


def update_memory(
    conn: sqlite3.Connection,
    vector_store: VectorStore,
    fact_id: int,
    new_text: str,
) -> bool:
    """Updates a memory's text in SQLite canonical store and synchronizes ChromaDB."""
    cleaned = new_text.strip()
    if not cleaned:
        return False

    f_hash = hash_fact(cleaned)
    now = datetime.now().isoformat()

    with db.transaction(conn):
        cursor = conn.execute(
            """
            UPDATE facts
            SET fact_text = ?, fact_hash = ?, updated_at = ?
            WHERE id = ?
            """,
            (cleaned, f_hash, now, fact_id),
        )
        if cursor.rowcount == 0:
            return False

        # Synchronize vector index
        vector_store.add_fact(
            fact_id=fact_id,
            fact_text=cleaned,
            metadata={"updated_at": now},
        )
        return True


def delete_memory(
    conn: sqlite3.Connection,
    vector_store: VectorStore,
    fact_id: int,
) -> bool:
    """Permanently deletes a memory from canonical SQLite and vector index."""
    with db.transaction(conn):
        cursor = conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
        if cursor.rowcount == 0:
            return False
        vector_store.delete_fact(fact_id)
        return True


def clear_all_memories(
    conn: sqlite3.Connection,
    vector_store: VectorStore,
) -> int:
    """Clears all facts from SQLite and empties the Chroma vector index."""
    with db.transaction(conn):
        cursor = conn.execute("DELETE FROM facts")
        count = cursor.rowcount
        vector_store.clear_all()
        return count


def reconcile_and_rebuild(
    conn: sqlite3.Connection,
    vector_store: VectorStore,
) -> dict[str, Any]:
    """Rebuilds and reconciles ChromaDB vector index from canonical SQLite records."""
    active_facts = conn.execute(
        "SELECT id, fact_text, source_session_id, category, consolidated_date FROM facts WHERE status = 'active'"
    ).fetchall()

    records = [dict(r) for r in active_facts]
    rebuilt_count = vector_store.rebuild_from_records(records)

    with db.transaction(conn):
        conn.execute("UPDATE facts SET synced_to_chroma = 1 WHERE status = 'active'")

    return {
        "status": "success",
        "canonical_active_count": len(records),
        "rebuilt_vectors": rebuilt_count,
    }


def export_memories(conn: sqlite3.Connection) -> dict[str, Any]:
    """Generates structured, versioned export payload of all memories."""
    rows = conn.execute("SELECT * FROM facts ORDER BY id ASC").fetchall()
    return {
        "version": "2.0",
        "exported_at": datetime.now().isoformat(),
        "total_memories": len(rows),
        "memories": [dict(r) for r in rows],
    }


def import_memories(
    conn: sqlite3.Connection,
    vector_store: VectorStore,
    data: dict[str, Any],
) -> dict[str, int]:
    """Imports memories from a JSON payload into SQLite and ChromaDB."""
    memories = data.get("memories", [])
    imported = 0
    skipped = 0

    for m in memories:
        text = m.get("fact_text", "").strip()
        if not text:
            skipped += 1
            continue

        f_hash = hash_fact(text)
        existing = conn.execute(
            "SELECT id FROM facts WHERE fact_hash = ? AND status = 'active'", (f_hash,)
        ).fetchone()

        if existing:
            skipped += 1
            continue

        with db.transaction(conn):
            cursor = conn.execute(
                """
                INSERT INTO facts (
                    fact_text, fact_hash, source_session_id, synced_to_chroma, status, category
                ) VALUES (?, ?, ?, 1, 'active', ?)
                """,
                (
                    text,
                    f_hash,
                    m.get("source_session_id", "import"),
                    m.get("category", "general"),
                ),
            )
            new_id = cursor.lastrowid or 0
            vector_store.add_fact(
                fact_id=new_id,
                fact_text=text,
                metadata={"source": "import", "category": m.get("category", "general")},
            )
            imported += 1

    return {"imported": imported, "skipped": skipped}
