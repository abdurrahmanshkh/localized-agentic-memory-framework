"""
Command-Line Interface (CLI) for Localized Agentic Memory Framework.

Provides an interactive terminal session with full mode support (:search:, :deepsearch:,
:remember:, :incognito:), verifiable context history, and session consolidation.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

try:
    from . import config, db, memory_service, models, router
    from .vector_store import VectorStore
except ImportError:
    # Handle direct script invocation
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import config
    import db
    import memory_service
    import models
    import router
    from vector_store import VectorStore


def main() -> None:
    print("=" * 60)
    print(f" {config.APP_NAME} v{config.APP_VERSION} (CLI Mode)")
    print("=" * 60)
    print(f"Runtime Data Directory: {config.get_runtime_data_dir()}")

    # 1. Initialize SQLite schema and migrations
    db.init_db()

    # 2. Check Ollama server & models
    ollama_status = models.check_ollama_status()
    if not ollama_status["running"]:
        print("\n[!] WARNING: Local Ollama server is not running.")
        print("    Chat, extraction, and conflict resolution will fail.")
        print("    To start Ollama, open the Ollama app or run 'ollama serve' in a terminal.\n")
    else:
        installed = ollama_status.get("models", [])
        print(f"[*] Ollama running. Detected models: {', '.join(installed) if installed else 'None'}")
        if not models.is_model_available(config.MODEL_CHAT):
            print(f"[!] Chat model '{config.MODEL_CHAT}' not found. Run: ollama pull {config.MODEL_CHAT}")

    session_id = str(uuid.uuid4())
    print(f"\nSession initialized: {session_id}")
    print("Prefixes available: :search:, :deepsearch:, :remember:, :incognito:")
    print("Type 'exit' to consolidate session and save memory.\n")

    conn = db.get_db_connection()
    vstore = VectorStore()
    mclient = models.LocalOllamaClient()

    try:
        while True:
            try:
                user_input = input("You: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nSession interrupted.")
                break

            if not user_input:
                continue

            if user_input.lower() == "exit":
                print("\nFinalizing session and consolidating memories...")
                try:
                    result = memory_service.consolidate_session(
                        conn=conn,
                        session_id=session_id,
                        client=mclient,
                        vector_store=vstore,
                    )
                    print(f"Consolidation complete: {result['facts_extracted']} extracted, "
                          f"{result['facts_added']} added, {result['duplicates']} duplicates, "
                          f"{result['updates']} updates.")
                except Exception as e:
                    print(f"[!] Consolidation encountered an error: {e}")
                break

            mode, cleaned_input = router.route_message(user_input)

            try:
                if mode == "incognito":
                    res = router.handle_incognito(cleaned_input, client=mclient)
                    print(f"\n[Incognito Assistant]: {res['reply']}\n")
                    print(f"  [stateless local execution | model inference: {res['infer_ms']:.1f}ms]\n")

                elif mode == "search":
                    res = router.handle_search(cleaned_input, client=mclient)
                    print(f"\nAssistant: {res['reply']}\n")
                    if res.get("sources"):
                        print("  Sources:")
                        for s in res["sources"]:
                            print(f"  - {s['title']}: {s['url']}")
                    print(f"  [search: {res['search_ms']:.1f}ms | inference: {res['infer_ms']:.1f}ms]\n")

                elif mode == "deepsearch":
                    res = router.handle_deepsearch(cleaned_input, client=mclient)
                    print(f"\nAssistant: {res['reply']}\n")
                    if res.get("sources"):
                        print("  Sources:")
                        for s in res["sources"]:
                            print(f"  - {s['title']}: {s['url']}")
                    print(f"  [scrape: {res['search_ms']:.1f}ms | inference: {res['infer_ms']:.1f}ms]\n")

                elif mode == "remember":
                    res = router.handle_remember(conn, cleaned_input, vector_store=vstore, client=mclient)
                    print(f"\nAssistant: {res['reply']}\n")
                    if res.get("recalled_facts"):
                        print("  Recalled Memories Used:")
                        for rf in res["recalled_facts"]:
                            sim = rf.get("similarity", 0.0)
                            print(f"  * (similarity: {sim:.2f}) {rf['fact_text']}")
                    print(f"  [inference: {res['infer_ms']:.1f}ms]\n")

                else:  # normal chat
                    res = router.handle_chat(conn, session_id, cleaned_input, client=mclient)
                    print(f"\nAssistant: {res['reply']}\n")
                    print(f"  [buffer write: {res['write_ms']:.2f}ms | inference: {res['infer_ms']:.1f}ms]\n")

            except models.OllamaConnectionError as e:
                print(f"\n[!] Ollama Error: {e}\n")
            except models.ModelNotFoundError as e:
                print(f"\n[!] Model Error: {e}\n")
            except Exception as e:
                print(f"\n[!] Processing Error: {e}\n")

    finally:
        conn.close()
        print("Session ended.")


if __name__ == "__main__":
    main()
