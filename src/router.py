"""
Routing and mode dispatch module for Localized Agentic Memory Framework.

Directs user interactions to the appropriate subsystem:
- normal chat (local LLM with recent conversation context)
- :remember: (semantic recall from ChromaDB long-term memory)
- :incognito: (stateless local LLM, zero network calls, zero persistence)
- :search: (DuckDuckGo web search with citation links)
- :deepsearch: (multi-page web scrape and synthesis with citations)
"""

from __future__ import annotations

import sqlite3
import time
from typing import Any

try:
    from . import config, db, prompts, search
    from .models import LocalOllamaClient, OllamaClientInterface
    from .vector_store import VectorStore
except ImportError:
    import config
    import db
    import prompts
    import search
    from models import LocalOllamaClient, OllamaClientInterface
    from vector_store import VectorStore


# Recognized prefix commands mapped to mode identifiers
MODE_PREFIXES = [
    (":search:", "search"),
    (":deepsearch:", "deepsearch"),
    (":remember:", "remember"),
    (":incognito:", "incognito"),
]


def route_message(user_input: str) -> tuple[str, str]:
    """Parses input prefixes to determine interaction mode and returns (mode, cleaned_input)."""
    trimmed = user_input.strip()
    for prefix, mode in MODE_PREFIXES:
        if trimmed.lower().startswith(prefix):
            cleaned = trimmed[len(prefix):].strip()
            return mode, cleaned
    return "chat", trimmed


# ---------------------------------------------------------
# Mode Handlers
# ---------------------------------------------------------
def handle_chat(
    conn: sqlite3.Connection,
    session_id: str,
    cleaned_input: str,
    client: OllamaClientInterface | None = None,
) -> dict[str, Any]:
    """Default local chat turn.

    Includes current prompt and recent context exactly once, persists turns in SQLite buffer.
    """
    if not cleaned_input:
        return {
            "reply": "Please enter a message to chat.",
            "mode": "chat",
            "write_ms": 0.0,
            "infer_ms": 0.0,
            "user_msg_id": None,
            "assistant_msg_id": None,
        }

    mclient = client or LocalOllamaClient()

    # 1. Persist user turn to SQLite buffer first
    t0 = time.perf_counter()
    user_msg_id = db.save_turn(conn, session_id, "user", cleaned_input)
    write_ms = (time.perf_counter() - t0) * 1000

    # 2. Build conversation context window (up to MAX_HISTORY_TURNS recent turns)
    history = db.load_history(conn, session_id, limit=config.MAX_HISTORY_TURNS * 2)

    # 3. Model inference
    t1 = time.perf_counter()
    reply = mclient.chat(config.MODEL_CHAT, messages=history)
    infer_ms = (time.perf_counter() - t1) * 1000

    # 4. Persist assistant response to buffer
    t2 = time.perf_counter()
    assistant_msg_id = db.save_turn(conn, session_id, "assistant", reply)
    write_ms += (time.perf_counter() - t2) * 1000

    return {
        "reply": reply,
        "mode": "chat",
        "write_ms": write_ms,
        "infer_ms": infer_ms,
        "user_msg_id": user_msg_id,
        "assistant_msg_id": assistant_msg_id,
    }


def handle_incognito(
    cleaned_input: str,
    client: OllamaClientInterface | None = None,
) -> dict[str, Any]:
    """Stateless, local-only turn.

    ZERO external network requests, ZERO SQLite writes, ZERO Chroma reads/writes.
    """
    if not cleaned_input:
        return {
            "reply": "Incognito mode is active. Please enter a prompt for stateless execution.",
            "mode": "incognito",
            "write_ms": 0.0,
            "infer_ms": 0.0,
        }

    mclient = client or LocalOllamaClient()
    prompt = prompts.get_incognito_prompt(cleaned_input)

    t0 = time.perf_counter()
    reply = mclient.chat(
        config.MODEL_CHAT,
        messages=[{"role": "user", "content": prompt}],
    )
    infer_ms = (time.perf_counter() - t0) * 1000

    return {
        "reply": reply,
        "mode": "incognito",
        "write_ms": 0.0,
        "infer_ms": infer_ms,
        "user_msg_id": None,
        "assistant_msg_id": None,
    }


def handle_search(
    cleaned_input: str,
    client: OllamaClientInterface | None = None,
) -> dict[str, Any]:
    """Executes external DuckDuckGo search and formats an answer with citations."""
    if not cleaned_input:
        return {
            "reply": "Please provide a query after :search: (e.g. :search: latest discoveries in quantum computing).",
            "mode": "search",
            "sources": [],
            "infer_ms": 0.0,
            "search_ms": 0.0,
        }

    mclient = client or LocalOllamaClient()

    # 1. External Web Search
    t0 = time.perf_counter()
    try:
        results = search.search_web(cleaned_input, max_results=config.SEARCH_MAX_RESULTS)
    except Exception as e:
        return {
            "reply": f"Web search could not be completed: {e}",
            "mode": "search",
            "sources": [],
            "infer_ms": 0.0,
            "search_ms": (time.perf_counter() - t0) * 1000,
        }
    search_ms = (time.perf_counter() - t0) * 1000

    if not results:
        return {
            "reply": f"No web search results were found for: '{cleaned_input}'.",
            "mode": "search",
            "sources": [],
            "infer_ms": 0.0,
            "search_ms": search_ms,
        }

    # 2. Build synthesis prompt with untrusted data safeguards
    formatted_snippets = []
    sources = []
    for r in results:
        title = r.get("title", "")
        body = r.get("body", "")
        href = r.get("href", "")
        formatted_snippets.append(f"{title}: {body}")
        if href:
            sources.append({"title": title or href, "url": href})

    prompt = prompts.get_search_prompt(cleaned_input, "\n".join(formatted_snippets))

    # 3. Model Inference
    t1 = time.perf_counter()
    reply = mclient.chat(config.MODEL_EXTRACTION, [{"role": "user", "content": prompt}])
    infer_ms = (time.perf_counter() - t1) * 1000

    return {
        "reply": reply,
        "mode": "search",
        "sources": sources,
        "infer_ms": infer_ms,
        "search_ms": search_ms,
    }


def handle_deepsearch(
    cleaned_input: str,
    client: OllamaClientInterface | None = None,
) -> dict[str, Any]:
    """Executes multi-page scrape and synthesizes answers with source citations."""
    if not cleaned_input:
        return {
            "reply": "Please provide a query after :deepsearch: (e.g. :deepsearch: transformer architecture variations).",
            "mode": "deepsearch",
            "sources": [],
            "infer_ms": 0.0,
            "search_ms": 0.0,
        }

    mclient = client or LocalOllamaClient()

    t0 = time.perf_counter()
    try:
        scraped_data = search.search_and_scrape(cleaned_input, max_results=config.SEARCH_MAX_RESULTS)
    except Exception as e:
        return {
            "reply": f"Deep search failed to fetch pages: {e}",
            "mode": "deepsearch",
            "sources": [],
            "infer_ms": 0.0,
            "search_ms": (time.perf_counter() - t0) * 1000,
        }
    search_ms = (time.perf_counter() - t0) * 1000

    if not scraped_data:
        return {
            "reply": f"Could not retrieve webpage content for: '{cleaned_input}'.",
            "mode": "deepsearch",
            "sources": [],
            "infer_ms": 0.0,
            "search_ms": search_ms,
        }

    snippets = []
    sources = []
    for item in scraped_data:
        title = item.get("title", "")
        url = item.get("url", "")
        text = item.get("text", "")
        snippets.append(f"Source: {title} ({url})\n{text}")
        if url:
            sources.append({"title": title or url, "url": url})

    prompt = prompts.get_deepsearch_prompt(cleaned_input, "\n\n".join(snippets))

    t1 = time.perf_counter()
    reply = mclient.chat(config.MODEL_EXTRACTION, [{"role": "user", "content": prompt}])
    infer_ms = (time.perf_counter() - t1) * 1000

    return {
        "reply": reply,
        "mode": "deepsearch",
        "sources": sources,
        "infer_ms": infer_ms,
        "search_ms": search_ms,
    }


def handle_remember(
    conn: sqlite3.Connection,
    cleaned_input: str,
    vector_store: VectorStore | None = None,
    client: OllamaClientInterface | None = None,
) -> dict[str, Any]:
    """Queries semantic long-term memory and synthesizes a direct recall answer."""
    if not cleaned_input:
        return {
            "reply": "Please specify what you would like me to recall (e.g. :remember: what is my preferred programming language?).",
            "mode": "remember",
            "recalled_facts": [],
            "infer_ms": 0.0,
        }

    vstore = vector_store or VectorStore()
    mclient = client or LocalOllamaClient()

    # Query top semantic matches
    matches = vstore.query_similar(cleaned_input, n_results=5)

    if not matches:
        return {
            "reply": "I don't have any relevant memories about that yet.",
            "mode": "remember",
            "recalled_facts": [],
            "infer_ms": 0.0,
        }

    # Fetch canonical SQLite metadata for provenance transparency
    recalled_facts = []
    prompt_facts = []
    for m in matches:
        f_id = m["id"]
        row = conn.execute("SELECT * FROM facts WHERE id = ?", (f_id,)).fetchone()
        fact_dict = dict(row) if row else {"id": f_id, "fact_text": m["text"]}
        fact_dict["similarity"] = m.get("similarity", 0.0)
        recalled_facts.append(fact_dict)
        prompt_facts.append(m["text"])

    prompt = prompts.get_remember_prompt(cleaned_input, "\n".join(prompt_facts))

    t0 = time.perf_counter()
    reply = mclient.chat(config.MODEL_EXTRACTION, [{"role": "user", "content": prompt}])
    infer_ms = (time.perf_counter() - t0) * 1000

    return {
        "reply": reply,
        "mode": "remember",
        "recalled_facts": recalled_facts,
        "infer_ms": infer_ms,
    }
