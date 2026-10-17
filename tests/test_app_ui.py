"""
Tests for Streamlit application UI elements, state initialization, and safe rendering.
"""

from streamlit.testing.v1 import AppTest


def test_app_loads_and_initializes_state():
    """Verifies that src/app.py starts without error and sets up default session state."""
    at = AppTest.from_file("../src/app.py")
    at.run(timeout=15)

    assert not at.exception
    assert at.session_state.session_id is not None
    assert at.session_state.selected_mode == "chat"
    assert at.session_state.retain_raw_conversations is True


def test_app_navigation_and_tab_rendering():
    """Verifies that navigation controls exist and display appropriate workspace views."""
    at = AppTest.from_file("../src/app.py")
    at.run(timeout=15)

    # Verify radio navigation control exists
    assert len(at.sidebar.radio) > 0
    radio = at.sidebar.radio[0]
    assert "💬 Chat Workspace" in radio.options
    assert "🧠 Memory Studio" in radio.options
    assert "⚙️ System & Health" in radio.options
    assert "📊 Benchmark & Demo" in radio.options
