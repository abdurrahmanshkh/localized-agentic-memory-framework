"""
Tests for Ollama client error boundaries, missing model diagnostics, and timeouts.
"""

from unittest.mock import MagicMock

import pytest

from src import models


def test_check_ollama_status_offline():
    """Verifies that an offline server returns running=False without raising an unhandled exception."""
    status = models.check_ollama_status(host="http://localhost:99999", timeout=0.5)
    assert not status["running"]
    assert status["models"] == []
    assert status["error"] is not None


def test_model_not_found_error_message():
    """Verifies that ModelNotFoundError provides a copy-pasteable pull command."""
    err = models.ModelNotFoundError("qwen2.5:1.5b")
    assert "ollama pull qwen2.5:1.5b" in str(err)
    assert err.model_name == "qwen2.5:1.5b"


def test_local_ollama_client_connection_error():
    """Verifies that network/connection errors are converted to OllamaConnectionError."""
    client = models.LocalOllamaClient(host="http://127.0.0.1:54321")
    # Mock internal ollama client to simulate connection refusal
    mock_raw_client = MagicMock()
    mock_raw_client.chat.side_effect = ConnectionError("Failed to connect to Ollama")
    client._client = mock_raw_client

    with pytest.raises(models.OllamaConnectionError) as exc_info:
        client.chat("qwen2.5:1.5b", [{"role": "user", "content": "hello"}])
    assert "Could not connect to Ollama server" in str(exc_info.value)


def test_local_ollama_client_model_not_found():
    """Verifies that model-missing errors are converted to ModelNotFoundError."""
    client = models.LocalOllamaClient()
    mock_raw_client = MagicMock()
    mock_raw_client.chat.side_effect = Exception("model 'llama3.2:3b' not found, try pulling it first")
    client._client = mock_raw_client

    with pytest.raises(models.ModelNotFoundError) as exc_info:
        client.chat("llama3.2:3b", [{"role": "user", "content": "hello"}])
    assert "ollama pull llama3.2:3b" in str(exc_info.value)


def test_local_ollama_client_timeout():
    """Verifies that timeout errors are caught and raised as InferenceTimeoutError."""
    client = models.LocalOllamaClient(default_timeout=5.0)
    mock_raw_client = MagicMock()
    mock_raw_client.chat.side_effect = Exception("Request timed out")
    client._client = mock_raw_client

    with pytest.raises(models.InferenceTimeoutError) as exc_info:
        client.chat("llama3.2:3b", [{"role": "user", "content": "hello"}])
    assert "timed out after 5.0 seconds" in str(exc_info.value)
