"""
Configuration module for Localized Agentic Memory Framework.

Provides centralized paths, model configuration, similarity thresholds,
and environment overrides.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Project root (root of repository)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Default application data directory outside the repository
def get_default_data_dir() -> Path:
    """Returns platform-standard user application data directory."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "LocalizedAgenticMemory"
        return Path.home() / "AppData" / "Local" / "LocalizedAgenticMemory"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "LocalizedAgenticMemory"
    else:
        # Linux / Unix XDG base
        base = os.environ.get("XDG_DATA_HOME")
        if base:
            return Path(base) / "LocalizedAgenticMemory"
        return Path.home() / ".local" / "share" / "LocalizedAgenticMemory"


def get_runtime_data_dir() -> Path:
    """Returns the effective data directory, checking LAM_DATA_DIR override first."""
    override = os.environ.get("LAM_DATA_DIR")
    if override:
        path = Path(override).expanduser().resolve()
    else:
        path = get_default_data_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_db_path() -> Path:
    """Returns absolute path to the SQLite canonical database."""
    return get_runtime_data_dir() / "memory.db"


def get_chroma_dir() -> Path:
    """Returns absolute path to the ChromaDB vector storage directory."""
    chroma_dir = get_runtime_data_dir() / "chroma"
    chroma_dir.mkdir(parents=True, exist_ok=True)
    return chroma_dir


def get_exports_dir() -> Path:
    """Returns absolute path to the JSON memory exports directory."""
    exports_dir = get_runtime_data_dir() / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    return exports_dir


def get_schema_path() -> Path:
    """Returns absolute path to the canonical schema.sql file in repo."""
    return PROJECT_ROOT / "data" / "schema.sql"


# ---------------------------------------------------------
# Model & Inference Configuration
# ---------------------------------------------------------
MODEL_CHAT = os.environ.get("LAM_MODEL_CHAT", "qwen2.5:1.5b")
MODEL_EXTRACTION = os.environ.get("LAM_MODEL_EXTRACTION", "llama3.2:3b")
MODEL_REASONING = os.environ.get("LAM_MODEL_REASONING", "llama3.2:3b")

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_TIMEOUT = float(os.environ.get("LAM_OLLAMA_TIMEOUT", "30.0"))

# ---------------------------------------------------------
# Deduplication Similarity Thresholds
# ---------------------------------------------------------
# >= AUTO_DUPLICATE: Confident duplicate, skip redundant vector add
AUTO_DUPLICATE_THRESHOLD = float(os.environ.get("LAM_AUTO_DUP_THRESHOLD", "0.90"))
# < AUTO_DISTINCT: Confident distinct, add new vector immediately
AUTO_DISTINCT_THRESHOLD = float(os.environ.get("LAM_AUTO_DISTINCT_THRESHOLD", "0.70"))

# ---------------------------------------------------------
# Limits & Guardrails
# ---------------------------------------------------------
MAX_HISTORY_TURNS = int(os.environ.get("LAM_MAX_HISTORY_TURNS", "10"))
SEARCH_MAX_RESULTS = int(os.environ.get("LAM_SEARCH_MAX_RESULTS", "5"))
SEARCH_TIMEOUT = float(os.environ.get("LAM_SEARCH_TIMEOUT", "15.0"))
PAGE_DOWNLOAD_TIMEOUT = float(os.environ.get("LAM_PAGE_TIMEOUT", "8.0"))
MAX_PAGE_CONTENT_BYTES = 50_000

# App Metadata
APP_NAME = "Localized Agentic Memory"
APP_VERSION = "2.0.0"
