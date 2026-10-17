"""
Pytest configuration and deterministic test fixtures.

Provides isolated temporary databases, in-memory Chroma vector stores,
and mock model clients so tests never require internet access or a running Ollama server.
"""

import shutil
import tempfile
import uuid
from pathlib import Path

import pytest

from src import db
from src.models import MockOllamaClient
from src.vector_store import VectorStore


@pytest.fixture
def temp_data_dir(monkeypatch):
    """Creates an isolated temporary directory for runtime data and overrides LAM_DATA_DIR."""
    temp_dir = tempfile.mkdtemp(prefix="lam_test_")
    monkeypatch.setenv("LAM_DATA_DIR", temp_dir)
    # Also reload paths
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def test_db(temp_data_dir):
    """Initializes and returns a clean SQLite connection in the temp directory."""
    db_path = temp_data_dir / "memory.db"
    db.init_db(db_path=db_path)
    conn = db.get_db_connection(db_path=db_path)
    yield conn
    conn.close()


@pytest.fixture
def test_vector_store():
    """Returns an in-memory Chroma VectorStore isolated from disk."""
    store = VectorStore(in_memory=True, collection_name=f"test_{uuid.uuid4().hex[:8]}")
    yield store
    store.clear_all()


@pytest.fixture
def mock_ollama():
    """Returns a configurable mock Ollama client."""
    return MockOllamaClient()
