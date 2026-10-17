"""
Tests for startup, database initialization, schema migration, and transaction safety.
"""

import pytest

from src import db


def test_fresh_startup_creates_tables_and_indexes(temp_data_dir):
    """Verifies that init_db creates all expected tables, columns, and indexes."""
    db_path = temp_data_dir / "fresh.db"
    assert not db_path.exists()

    db.init_db(db_path=db_path)
    assert db_path.exists()

    conn = db.get_db_connection(db_path=db_path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "conversations" in tables
    assert "facts" in tables
    assert "schema_migrations" in tables

    # Verify enhanced columns in facts
    fact_cols = {r["name"] for r in conn.execute("PRAGMA table_info(facts)").fetchall()}
    assert "status" in fact_cols
    assert "superseded_by_id" in fact_cols
    assert "category" in fact_cols
    assert "synced_to_chroma" in fact_cols
    conn.close()


def test_reopening_db_is_idempotent(temp_data_dir):
    """Verifies that running init_db multiple times does not corrupt or wipe existing data."""
    db_path = temp_data_dir / "idempotent.db"
    db.init_db(db_path=db_path)

    conn = db.get_db_connection(db_path=db_path)
    db.save_turn(conn, "session_1", "user", "Hello world")
    conn.close()

    # Second init call
    db.init_db(db_path=db_path)

    conn2 = db.get_db_connection(db_path=db_path)
    history = db.load_history(conn2, "session_1")
    assert len(history) == 1
    assert history[0]["content"] == "Hello world"
    conn2.close()


def test_conversation_writes_and_session_isolation(test_db):
    """Verifies turn ordering, role persistence, and session isolation."""
    db.save_turn(test_db, "session_a", "user", "Message 1 from A")
    db.save_turn(test_db, "session_b", "user", "Message 1 from B")
    db.save_turn(test_db, "session_a", "assistant", "Reply 1 to A")

    hist_a = db.load_history(test_db, "session_a")
    hist_b = db.load_history(test_db, "session_b")

    assert len(hist_a) == 2
    assert hist_a[0]["role"] == "user"
    assert hist_a[0]["content"] == "Message 1 from A"
    assert hist_a[1]["role"] == "assistant"
    assert hist_a[1]["content"] == "Reply 1 to A"

    assert len(hist_b) == 1
    assert hist_b[0]["content"] == "Message 1 from B"


def test_transaction_rollback_on_error(test_db):
    """Verifies that errors inside transaction block trigger a safe rollback."""
    initial_count = test_db.execute("SELECT count(*) FROM conversations").fetchone()[0]

    with pytest.raises(RuntimeError):
        with db.transaction(test_db):
            test_db.execute(
                "INSERT INTO conversations (session_id, role, content) VALUES ('s1', 'user', 'should rollback')"
            )
            raise RuntimeError("Simulated crash")

    final_count = test_db.execute("SELECT count(*) FROM conversations").fetchone()[0]
    assert final_count == initial_count


def test_delete_turns_feedback(test_db):
    """Verifies that delete_turns permanently purges specified turns from SQLite."""
    id1 = db.save_turn(test_db, "sess", "user", "Unhelpful question")
    id2 = db.save_turn(test_db, "sess", "assistant", "Unhelpful answer")
    _ = db.save_turn(test_db, "sess", "user", "Good question")

    deleted = db.delete_turns(test_db, [id1, id2])
    assert deleted == 2

    history = db.load_history(test_db, "sess")
    assert len(history) == 1
    assert history[0]["content"] == "Good question"
