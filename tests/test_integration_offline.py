"""
End-to-End offline integration tests.

Exercises the complete user lifecycle:
Multi-turn conversation -> Session Consolidation -> Semantic Recall across sessions -> Incognito verification.
"""

from src import memory_service, router
from src.models import MockOllamaClient


def test_full_lifecycle_chat_consolidate_recall(test_db, test_vector_store):
    """Proves that a user can chat in session 1, consolidate memories, and recall them accurately in session 2."""
    session_1 = "student_session_1"

    mock = MockOllamaClient(
        responses={
            "What is my project topic?": "I'd love to know what your project is about!",
            "I am building a localized agentic memory framework": "That sounds like a great final year project!",
            # Extraction response
            "Conversation transcript": "- User is building a localized agentic memory framework for their final year project",
            # Recall response
            "Remembered facts": "Your project is the localized agentic memory framework.",
        }
    )

    # 1. Turn 1 in Session 1
    res1 = router.handle_chat(test_db, session_1, "What is my project topic?", client=mock)
    assert "I'd love to know" in res1["reply"]

    # 2. Turn 2 in Session 1 (User shares project info)
    res2 = router.handle_chat(test_db, session_1, "I am building a localized agentic memory framework", client=mock)
    assert "final year project" in res2["reply"]

    # Verify conversation buffer has 4 rows (2 user, 2 assistant)
    conv_rows = test_db.execute("SELECT count(*) FROM conversations WHERE session_id = ?", (session_1,)).fetchone()[0]
    assert conv_rows == 4

    # 3. End of Session 1: Consolidate
    c_res = memory_service.consolidate_session(
        test_db, session_1, client=mock, vector_store=test_vector_store
    )
    assert c_res["status"] == "success"
    assert c_res["facts_added"] == 1

    # Verify SQLite facts table holds the canonical memory
    memories = memory_service.list_memories(test_db, status="active")
    assert len(memories) == 1
    assert "localized agentic memory framework" in memories[0]["fact_text"]
    assert memories[0]["source_session_id"] == session_1

    # Verify vector store holds the embedding
    assert test_vector_store.count() == 1

    # 4. Session 2: User opens a new session and asks recall question
    recall_res = router.handle_remember(
        test_db,
        "What am I working on?",
        vector_store=test_vector_store,
        client=mock,
    )

    assert "localized agentic memory framework" in recall_res["reply"]
    # Check transparency metadata
    assert len(recall_res["recalled_facts"]) == 1
    recalled = recall_res["recalled_facts"][0]
    assert "localized agentic memory framework" in recalled["fact_text"]
    assert recalled["source_session_id"] == session_1
    assert "similarity" in recalled

    # 5. Session 3: Incognito turn leaves zero footprint
    incog_res = router.handle_incognito(
        "Temporary query that should leave no trace",
        client=mock,
    )
    assert incog_res["mode"] == "incognito"

    # Confirm facts and vector counts remained exactly 1
    assert len(memory_service.list_memories(test_db, status="active")) == 1
    assert test_vector_store.count() == 1
