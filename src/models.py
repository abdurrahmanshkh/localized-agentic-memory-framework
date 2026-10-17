"""
Model client and health check module for Ollama integration.

Provides structured error handling, connection checks, model verification,
and dependency-injected client wrappers.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Protocol

try:
    import ollama
except ImportError:
    ollama = None

try:
    from . import config
except ImportError:
    import config


class OllamaError(Exception):
    """Base exception for Ollama model operations."""


class OllamaConnectionError(OllamaError):
    """Raised when the local Ollama server cannot be reached."""


class ModelNotFoundError(OllamaError):
    """Raised when the specified model is not installed locally."""
    def __init__(self, model_name: str):
        super().__init__(
            f"Required model '{model_name}' is not installed locally in Ollama.\n"
            f"To install it, run: ollama pull {model_name}"
        )
        self.model_name = model_name


class InferenceTimeoutError(OllamaError):
    """Raised when an inference call exceeds the configured timeout."""


def check_ollama_status(
    host: str | None = None,
    timeout: float = 1.0,
) -> dict[str, Any]:
    """Checks whether the Ollama server is responsive and returns metadata."""
    target_host = host or config.OLLAMA_HOST
    url = f"{target_host.rstrip('/')}/api/tags"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LAM-HealthCheck"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name", "") for m in data.get("models", [])]
                return {
                    "running": True,
                    "host": target_host,
                    "models": models,
                    "error": None,
                }
    except Exception as e:
        return {
            "running": False,
            "host": target_host,
            "models": [],
            "error": str(e),
        }
    return {
        "running": False,
        "host": target_host,
        "models": [],
        "error": "Unknown status",
    }


def is_model_available(model_name: str, host: str | None = None) -> bool:
    """Returns True if the model (or its prefix before ':') is installed."""
    status = check_ollama_status(host=host)
    if not status["running"]:
        return False
    installed = status.get("models", [])
    # Match exact or normalized name (e.g. 'qwen2.5:1.5b' vs 'qwen2.5:1.5b-instruct')
    target = model_name.strip().lower()
    for m in installed:
        m_lower = m.lower()
        if m_lower == target or m_lower.startswith(f"{target}:") or target.startswith(f"{m_lower}:"):
            return True
    return False


class OllamaClientInterface(Protocol):
    """Interface for model chat completion."""
    def chat(self, model: str, messages: list[dict[str, str]], timeout: float | None = None) -> str:
        ...


class LocalOllamaClient:
    """Production client wrapping the local Ollama Python library."""

    def __init__(self, host: str | None = None, default_timeout: float | None = None):
        self.host = host or config.OLLAMA_HOST
        self.default_timeout = default_timeout or config.OLLAMA_TIMEOUT
        self._client = None
        if ollama is not None:
            try:
                self._client = ollama.Client(host=self.host, timeout=self.default_timeout)
            except Exception:
                self._client = None

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        timeout: float | None = None,
    ) -> str:
        """Executes a chat completion against the local Ollama instance."""
        if ollama is None:
            raise OllamaConnectionError("The 'ollama' Python package is not installed.")

        client = self._client or ollama.Client(host=self.host, timeout=timeout or self.default_timeout)
        try:
            response = client.chat(model=model, messages=messages)
            if not response or "message" not in response:
                raise OllamaError("Malformed or empty response from Ollama.")
            return response["message"]["content"]
        except Exception as e:
            err_msg = str(e).lower()
            if "connection" in err_msg or "failed to connect" in err_msg or "winerror 10061" in err_msg:
                raise OllamaConnectionError(
                    f"Could not connect to Ollama server at {self.host}. "
                    "Make sure Ollama is running (`ollama serve`)."
                ) from e
            elif "not found" in err_msg or "try pulling it first" in err_msg:
                raise ModelNotFoundError(model) from e
            elif "timeout" in err_msg or "timed out" in err_msg:
                raise InferenceTimeoutError(
                    f"Model inference timed out after {timeout or self.default_timeout} seconds."
                ) from e
            else:
                raise OllamaError(f"Ollama inference error: {e}") from e


class MockOllamaClient:
    """Deterministic mock client for offline tests without requiring Ollama."""

    def __init__(self, responses: dict[str, str] | None = None, default_reply: str = "Mock answer"):
        self.responses = responses or {}
        self.default_reply = default_reply
        self.call_history: list[dict[str, Any]] = []

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        timeout: float | None = None,
    ) -> str:
        self.call_history.append({"model": model, "messages": messages, "timeout": timeout})
        # If last message content matches any key, return configured reply
        if messages:
            last_content = messages[-1].get("content", "")
            # Check for extraction instruction first
            if "You are a memory extraction system" in last_content:
                for pattern, reply in self.responses.items():
                    if pattern in ("extraction", "Conversation transcript", "transcript") or pattern.startswith("- "):
                        return reply
            # Sort remaining patterns by length descending
            for pattern in sorted(self.responses.keys(), key=len, reverse=True):
                if pattern in last_content:
                    return self.responses[pattern]
        return self.default_reply
