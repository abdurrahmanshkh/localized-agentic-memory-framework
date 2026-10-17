"""
Tests for prefix routing, input validation, context window policy, and Incognito isolation.
"""

from src import router
from src.models import MockOllamaClient


def test_route_message_prefixes():
    """Verifies that prefixes are parsed cleanly, case-insensitively, and stripped."""
    assert router.route_message(":search: latest python release") == ("search", "latest python release")
    assert router.route_message(":SEARCH: uppercase test") == ("search", "uppercase test")
    assert router.route_message(":deepsearch: deep scrape topic") == ("deepsearch", "deep scrape topic")
    assert router.route_message(":remember: user preferences") == ("remember", "user preferences")
    assert router.route_message(":incognito: private question") == ("incognito", "private question")
    assert router.route_message("Just a normal conversation") == ("chat", "Just a normal conversation")


def test_empty_or_prefix_only_commands():
    """Verifies that empty queries or prefix-only inputs return helpful guidance without making external/LLM calls."""
    res_search = router.handle_search("")
    assert "Please provide a query" in res_search["reply"]

    res_deep = router.handle_deepsearch("")
    assert "Please provide a query" in res_deep["reply"]

    res_remember = router.handle_remember(None, "")
    assert "Please specify what you would like me to recall" in res_remember["reply"]

    res_incognito = router.handle_incognito("")
    assert "Incognito mode is active" in res_incognito["reply"]

    res_chat = router.handle_chat(None, "sess", "")
    assert "Please enter a message" in res_chat["reply"]


def test_normal_chat_includes_prompt_exactly_once(test_db):
    """Verifies that normal chat passes the current prompt exactly once to the model."""
    mock = MockOllamaClient(default_reply="I can help with that.")
    session_id = "test_turn_order_session"

    # First turn
    res = router.handle_chat(test_db, session_id, "What is my project deadline?", client=mock)
    assert res["reply"] == "I can help with that."

    # Inspect call history to mock client
    assert len(mock.call_history) == 1
    messages = mock.call_history[0]["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "What is my project deadline?"

    # Second turn
    _ = router.handle_chat(test_db, session_id, "Can you clarify that?", client=mock)
    assert len(mock.call_history) == 2
    messages2 = mock.call_history[1]["messages"]
    assert len(messages2) == 3
    assert messages2[0]["role"] == "user"
    assert messages2[0]["content"] == "What is my project deadline?"
    assert messages2[1]["role"] == "assistant"
    assert messages2[1]["content"] == "I can help with that."
    assert messages2[2]["role"] == "user"
    assert messages2[2]["content"] == "Can you clarify that?"


def test_incognito_mode_has_zero_persistence_or_network(test_db, test_vector_store):
    """Verifies that Incognito does not write to SQLite, does not read/write Chroma, and makes no network calls."""
    mock = MockOllamaClient(default_reply="Stateless answer")

    initial_conv_count = test_db.execute("SELECT count(*) FROM conversations").fetchone()[0]
    initial_fact_count = test_db.execute("SELECT count(*) FROM facts").fetchone()[0]
    initial_vector_count = test_vector_store.count()

    res = router.handle_incognito("Super secret query that must never be saved", client=mock)

    assert res["reply"] == "Stateless answer"
    assert res["mode"] == "incognito"

    # SQLite must remain unchanged
    final_conv_count = test_db.execute("SELECT count(*) FROM conversations").fetchone()[0]
    final_fact_count = test_db.execute("SELECT count(*) FROM facts").fetchone()[0]
    assert final_conv_count == initial_conv_count
    assert final_fact_count == initial_fact_count

    # Chroma must remain untouched
    assert test_vector_store.count() == initial_vector_count
