"""
Live integration test for Ollama connection.

Automatically skipped when Ollama is not running so that offline unit test runs
are never blocked.
"""

import pytest

from src import models


@pytest.mark.integration
def test_live_ollama_connection():
    status = models.check_ollama_status()
    if not status["running"]:
        pytest.skip("Local Ollama service is not running. Start with 'ollama serve' to run integration tests.")

    client = models.LocalOllamaClient()
    reply = client.chat("qwen2.5:1.5b", [{"role": "user", "content": "Hello!"}])
    assert reply and len(reply.strip()) > 0
