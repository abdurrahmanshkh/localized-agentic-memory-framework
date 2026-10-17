"""
Database access and schema migration module for Localized Agentic Memory.

Manages SQLite connections, automatic schema initialization, and transactional
safety. SQLite serves as the canonical store for all conversational records and facts.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

try:
    from . import config
except ImportError:
    import config


def get_db_connection(
    db_path: str | Path | None = None,
    timeout: float = 15.0,
    check_same_thread: bool = False,
) -> sqlite3.Connection:
    """Creates a configured SQLite connection with row factory and safe pragmas."""
    if db_path is None:
        db_path = config.get_db_path()
    else:
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        str(db_path),
        timeout=timeout,
        check_same_thread=check_same_thread,
    )
    conn.row_factory = sqlite3.Row
    # Enable Write-Ahead Logging for concurrency and busy timeout resilience
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute(f"PRAGMA busy_timeout = {int(timeout * 1000)};")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def get_db(db_path: str | Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for a database connection that closes automatically."""
    conn = get_db_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for an atomic database transaction with automatic rollback."""
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db(
    db_path: str | Path | None = None,
    schema_path: str | Path | None = None,
) -> None:
    """Initializes SQLite database and ensures all required tables, columns, and indexes exist.

    Safe to call repeatedly on startup (idempotent).
    """
    if schema_path is None:
        schema_path = config.get_schema_path()
    else:
        schema_path = Path(schema_path)

    with get_db(db_path) as conn:
        with transaction(conn):
            # 1. Execute base schema if tables do not exist
            if schema_path.exists():
                with open(schema_path, "r", encoding="utf-8") as f:
                    conn.executescript(f.read())
            else:
                # Fallback embedded DDL if schema.sql cannot be reached
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS conversations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        consolidated INTEGER DEFAULT 0
                    );
                    CREATE TABLE IF NOT EXISTS facts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        fact_text TEXT NOT NULL,
                        fact_hash TEXT UNIQUE NOT NULL,
                        embedding_id TEXT,
                        consolidated_date DATE DEFAULT CURRENT_DATE,
                        source_session_id TEXT,
                        synced_to_chroma INTEGER DEFAULT 0
                    );
                """)

            # 2. Migration tracking table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    description TEXT
                );
            """)

            # 3. Add enhanced columns to facts if not already present
            existing_cols = {
                row["name"] for row in conn.execute("PRAGMA table_info(facts)").fetchall()
            }

            if "status" not in existing_cols:
                conn.execute("ALTER TABLE facts ADD COLUMN status TEXT DEFAULT 'active';")
            if "superseded_by_id" not in existing_cols:
                conn.execute("ALTER TABLE facts ADD COLUMN superseded_by_id INTEGER DEFAULT NULL;")
            if "updated_at" not in existing_cols:
                conn.execute("ALTER TABLE facts ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP;")
            if "category" not in existing_cols:
                conn.execute("ALTER TABLE facts ADD COLUMN category TEXT DEFAULT 'general';")

            # 4. Performance & lookup indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id, consolidated);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_facts_hash ON facts(fact_hash);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_facts_status ON facts(status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_facts_synced ON facts(synced_to_chroma);")

            # Record migration version 2 (enhanced metadata & provenance)
            conn.execute("""
                INSERT OR IGNORE INTO schema_migrations (version, description)
                VALUES (2, 'Enhanced fact metadata, status tracking, and indexes');
            """)


# ---------------------------------------------------------
# Turn / Conversation Helpers
# ---------------------------------------------------------
def save_turn(conn: sqlite3.Connection, session_id: str, role: str, content: str) -> int:
    """Inserts a single conversation turn into the buffer and returns its ID."""
    with transaction(conn):
        cursor = conn.execute(
            "INSERT INTO conversations (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content),
        )
        return cursor.lastrowid or 0


def load_history(conn: sqlite3.Connection, session_id: str, limit: int | None = None) -> list[dict[str, str]]:
    """Loads ordered conversation history for a given session."""
    query = "SELECT role, content FROM conversations WHERE session_id = ? ORDER BY id ASC"
    if limit:
        # Load most recent N messages in chronological order
        subquery = f"SELECT role, content FROM conversations WHERE session_id = ? ORDER BY id DESC LIMIT {int(limit)}"
        rows = conn.execute(subquery, (session_id,)).fetchall()
        rows = list(reversed(rows))
    else:
        rows = conn.execute(query, (session_id,)).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def delete_turns(conn: sqlite3.Connection, turn_ids: list[int]) -> int:
    """Permanently deletes specific turn IDs (used by user feedback rejection)."""
    valid_ids = [int(i) for i in turn_ids if i is not None]
    if not valid_ids:
        return 0
    placeholders = ",".join("?" for _ in valid_ids)
    with transaction(conn):
        cursor = conn.execute(
            f"DELETE FROM conversations WHERE id IN ({placeholders})",
            valid_ids,
        )
        return cursor.rowcount
