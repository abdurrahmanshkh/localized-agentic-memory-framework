"""
Tests for 3-layer deduplication, fact extraction parsing, session consolidation,
and Memory Studio management operations.
"""

from src import db, memory_service
from src.models import MockOllamaClient


def test_parse_extracted_facts():
    """Verifies parsing of bulleted facts, NO_FACTS, and malformed outputs."""
    output_standard = "- User is 21 years old\n- User lives in Mumbai\n- User studies Computer Science"
    facts = memory_service.parse_extracted_facts(output_standard)
    assert facts == [
        "User is 21 years old",
        "User lives in Mumbai",
        "User studies Computer Science",
    ]

    # Asterisks and bullets
    output_symbols = "* User prefers dark mode\n• User works with Python"
    assert memory_service.parse_extracted_facts(output_symbols) == [
        "User prefers dark mode",
        "User works with Python",
    ]

    # NO_FACTS detection
    assert memory_service.parse_extracted_facts("NO_FACTS") == []
    assert memory_service.parse_extracted_facts("NO_FACTS\nExtra garbage") == []
    assert memory_service.parse_extracted_facts("") == []
    assert memory_service.parse_extracted_facts("   \n\n  ") == []


def test_parse_conflict_decision_strictness():
    """Verifies that conflict decisions are parsed strictly and negations are not misidentified."""
    assert memory_service.parse_conflict_decision("DUPLICATE") == "DUPLICATE"
    assert memory_service.parse_conflict_decision("Duplicate.") == "DUPLICATE"
    assert memory_service.parse_conflict_decision("UPDATE") == "UPDATE"
    assert memory_service.parse_conflict_decision("Update.") == "UPDATE"
    assert memory_service.parse_conflict_decision("DISTINCT") == "DISTINCT"

    # Negation protection: "NOT DUPLICATE" must NOT be parsed as DUPLICATE!
    assert memory_service.parse_conflict_decision("This is NOT a duplicate.") == "DISTINCT"
    assert memory_service.parse_conflict_decision("Not duplicate, these are different facts.") == "DISTINCT"

    # Fallback protection: Unrecognized/garbage defaults safely to DISTINCT
    assert memory_service.parse_conflict_decision("I am unable to answer.") == "DISTINCT"
    assert memory_service.parse_conflict_decision("Uncertain relationship.") == "DISTINCT"


def test_layer1_exact_hash_deduplication(test_db, test_vector_store):
    """Verifies that exact duplicate facts are filtered at Layer 1 by hash match."""
    mock = MockOllamaClient(
        responses={
            "Conversation transcript": "- User is a software engineer"
        }
    )

    # First session consolidation
    db.save_turn(test_db, "session_1", "user", "I am a software engineer")
    res1 = memory_service.consolidate_session(
        test_db, "session_1", client=mock, vector_store=test_vector_store
    )
    assert res1["facts_added"] == 1
    assert res1["duplicates"] == 0

    # Second session mentions the exact same fact
    db.save_turn(test_db, "session_2", "user", "I am a software engineer")
    res2 = memory_service.consolidate_session(
        test_db, "session_2", client=mock, vector_store=test_vector_store
    )
    assert res2["facts_added"] == 0
    assert res2["duplicates"] == 1

    # Ensure only 1 active fact in SQLite
    active = memory_service.list_memories(test_db, status="active")
    assert len(active) == 1
    assert active[0]["fact_text"] == "User is a software engineer"


def test_layer3_update_supersedes_old_memory(test_db, test_vector_store):
    """Verifies that an UPDATE decision marks the old SQLite fact superseded and replaces the vector."""
    # Seed existing fact in SQLite and Chroma
    cursor = test_db.execute(
        "INSERT INTO facts (fact_text, fact_hash, synced_to_chroma, status) VALUES ('User is 21 years old', 'h1', 1, 'active')"
    )
    test_db.commit()
    old_id = cursor.lastrowid
    test_vector_store.add_fact(old_id, "User is 21 years old")

    # Mock extraction returns "User is 22 years old", and conflict resolution returns "UPDATE"
    mock = MockOllamaClient(
        responses={
            "Conversation transcript": "- User is 22 years old",
            "Existing fact: User is 21 years old": "UPDATE",
        }
    )

    db.save_turn(test_db, "session_age", "user", "It's my birthday, I am 22 now!")
    res = memory_service.consolidate_session(
        test_db, "session_age", client=mock, vector_store=test_vector_store
    )

    assert res["updates"] == 1

    # Verify SQLite status
    old_record = test_db.execute("SELECT * FROM facts WHERE id = ?", (old_id,)).fetchone()
    assert old_record["status"] == "superseded"
    assert old_record["superseded_by_id"] is not None

    new_record = test_db.execute("SELECT * FROM facts WHERE id = ?", (old_record["superseded_by_id"],)).fetchone()
    assert new_record["status"] == "active"
    assert new_record["fact_text"] == "User is 22 years old"

    # Verify vector store holds the new fact and not the old one
    matches = test_vector_store.query_similar("User is 22 years old", n_results=5)
    match_texts = [m["text"] for m in matches]
    assert "User is 22 years old" in match_texts
    assert "User is 21 years old" not in match_texts


def test_consolidation_large_session_chunking(test_db, test_vector_store):
    """Verifies that sessions with >50 messages are processed in chunks without dropping turns."""
    # Create 60 turns
    for i in range(60):
        db.save_turn(test_db, "large_session", "user" if i % 2 == 0 else "assistant", f"Turn message {i}")

    mock = MockOllamaClient(default_reply="- User had an extended conversation")

    res = memory_service.consolidate_session(
        test_db, "large_session", client=mock, vector_store=test_vector_store, chunk_size=25
    )

    assert res["status"] == "success"
    assert res["turns_processed"] == 60

    # Verify that all 60 turns are marked consolidated
    unconsolidated_left = test_db.execute(
        "SELECT count(*) FROM conversations WHERE session_id = 'large_session' AND consolidated = 0"
    ).fetchone()[0]
    assert unconsolidated_left == 0


def test_memory_studio_crud_and_rebuild(test_db, test_vector_store):
    """Verifies Memory Studio operations: list, search, update, delete, clear, rebuild."""
    # 1. Add sample memories
    test_db.execute(
        "INSERT INTO facts (fact_text, fact_hash, synced_to_chroma, status) VALUES ('Fact A', 'hA', 1, 'active')"
    )
    test_db.execute(
        "INSERT INTO facts (fact_text, fact_hash, synced_to_chroma, status) VALUES ('Fact B', 'hB', 1, 'active')"
    )
    test_db.commit()
    test_vector_store.add_fact(1, "Fact A")
    test_vector_store.add_fact(2, "Fact B")

    # 2. List & Search
    mems = memory_service.list_memories(test_db, search_query="Fact A")
    assert len(mems) == 1
    assert mems[0]["fact_text"] == "Fact A"

    # 3. Update Memory
    ok = memory_service.update_memory(test_db, test_vector_store, 1, "Fact A Updated")
    assert ok
    updated = memory_service.get_memory(test_db, 1)
    assert updated["fact_text"] == "Fact A Updated"

    # 4. Delete Memory
    deleted = memory_service.delete_memory(test_db, test_vector_store, 2)
    assert deleted
    assert memory_service.get_memory(test_db, 2) is None
    assert test_vector_store.count() == 1

    # 5. Reconcile & Rebuild
    rebuild_res = memory_service.reconcile_and_rebuild(test_db, test_vector_store)
    assert rebuild_res["status"] == "success"
    assert rebuild_res["rebuilt_vectors"] == 1


def test_export_and_import_memories(test_db, test_vector_store):
    """Verifies that memory exports and imports preserve schema structure and avoid duplicates."""
    tea_hash = memory_service.hash_fact("User likes tea")
    test_db.execute(
        "INSERT INTO facts (fact_text, fact_hash, synced_to_chroma, status) VALUES ('User likes tea', ?, 1, 'active')",
        (tea_hash,),
    )
    test_db.commit()

    export_payload = memory_service.export_memories(test_db)
    assert export_payload["version"] == "2.0"
    assert export_payload["total_memories"] == 1
    assert export_payload["memories"][0]["fact_text"] == "User likes tea"

    # Import into clean db
    import_data = {
        "version": "2.0",
        "memories": [
            {"fact_text": "User likes coffee", "category": "preference"},
            {"fact_text": "User likes tea", "category": "preference"},  # duplicate
        ],
    }
    result = memory_service.import_memories(test_db, test_vector_store, import_data)
    assert result["imported"] == 1
    assert result["skipped"] == 1  # exact duplicate skipped
