# Changelog: Localized Agentic Memory Framework

All notable changes to this project are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.0.0] - 2026-10-17

### 🔒 Security, Privacy, and Data Protection
- **Committed Database Untracked & Backed Up:** Removed tracked runtime ChromaDB files (`chroma/chroma.sqlite3`, `chroma.sqlite3.debug-backup`, binary index files) containing 387 historical developer test embeddings from Git index. Safely backed up to `backups/legacy_chroma_committed_backup/`.
- **Decoupled Default Runtime Storage:** Moved runtime databases to platform-standard user application data directories (`%LOCALAPPDATA%\LocalizedAgenticMemory` on Windows) with `LAM_DATA_DIR` environment override, ensuring zero repository pollution on fresh clones.
- **Fixed Incognito Mode Privacy Leak:** Completely eliminated the unintentional DuckDuckGo web search in `:incognito:` mode. Incognito is now guaranteed local-only and stateless: 0 external requests, 0 SQLite writes, 0 Chroma reads/writes.
- **SSRF Defense on Web Scraping:** Added URL validation blocking requests to `localhost`, loopbacks, and private IP subnets (`10.x`, `192.168.x`, `172.16-31.x`, `169.254.x`).
- **XSS Remediation:** Replaced raw HTML text interpolation (`unsafe_allow_html=True`) in Streamlit with native `st.chat_message` and standard Markdown.
- **Prompt Injection Hardening:** Added explicit security delimiters in search and scraping prompt templates to treat retrieved web data as untrusted reference material.

### 🐛 Bug Fixes & Reliability
- **Fixed DDGS Import Crash:** Resolved `ModuleNotFoundError: No module named 'ddgs'` by importing from `duckduckgo_search` with fallback to `ddgs`.
- **Fixed Chat Turn Ordering & Empty Context:** Fixed `src/chat.py` and `src/app.py` so user turns are persisted before inference and the current prompt is included in model context exactly once.
- **Automatic Schema Initialization:** Added automatic database initialization and versioned migrations on startup (`src/db.py`), resolving `no such table: conversations` on fresh clones.
- **Preserved Canonical SQLite Store:** Removed `clear_synced_facts()` from `dedup.py` which formerly destroyed SQLite records upon vector indexing. SQLite is now the authoritative store with provenance, timestamps, categories, and superseding history.
- **Fixed Destructive Premature Conversation Deletion:** Prevented `consolidate.py` from deleting raw turns before deduplication and indexing succeed. Added configurable retention policy.
- **Fixed 50-Message Consolidation Ceiling:** Replaced hardcoded `LIMIT 50` with chunked batch processing so conversations of any length are fully extracted without dropping turns.
- **Strict Conflict Decision Parser:** Fixed conflict resolution parser to prevent "NOT A DUPLICATE" from being parsed as DUPLICATE, with safe fallback to DISTINCT.
- **Hard Negative Guardrail:** Added numerical, date, and negation detection in deduplication to prevent facts with differing numbers/dates from being mistakenly auto-merged.
- **Lazy Chroma Client:** Eliminated module-level PersistentClient instantiation in `dedup.py` that created `./chroma` during imports.

### ✨ New Features & Enhancements
- **Memory Studio:** Added dedicated management dashboard in Streamlit to browse, search, edit, delete, clear, export (JSON), and import memories.
- **Reconcile & Rebuild:** Added one-click index reconciliation to repair or rebuild the Chroma vector store from canonical SQLite records.
- **Transparent Recall:** `:remember:` queries now display an expandable breakdown of the exact recalled facts used to construct the answer, including cosine similarity scores and source session IDs.
- **Live Health Diagnostics:** Added genuine status indicators for Ollama server, chat model (`qwen2.5:1.5b`), reasoning model (`llama3.2:3b`), SQLite, and Chroma.
- **Synthetic Viva Demo Mode:** Built a non-personal student demo dataset with one-click load and clean operations for academic project evaluations.
- **Interactive Sandbox:** Added a live fact-pair evaluator in the UI demonstrating the 3-layer deduplication trace.
- **Robust Windows & Cross-Platform Scripts:** Upgraded `setup.bat` and `run.bat` with error trapping and path resolution; added `setup.sh` and `run.sh`.

### 🧪 Automated Testing & Benchmarking
- **Pytest Regression Suite:** Built 29 automated tests (28 offline, 1 live integration) covering database initialization, routing, Incognito isolation, deduplication, Memory Studio CRUD, and Streamlit AppTest UI simulation.
- **Multi-OS CI Workflow:** Added GitHub Actions CI pipeline running formatting, linting, and offline test gates across Python 3.10, 3.11, and 3.12.
- **Benchmark v3:** Upgraded deduplication benchmark with live and offline modes, generating `benchmark_results.json` and `benchmark_results.png` (Precision: 0.786, Recall: 0.917, Accuracy: 0.867, F1: 0.846).

---

## [1.0.0] - Prior Baseline
- Initial student prototype with ephemeral SQLite buffer, keyword routing, basic consolidation, and preliminary Chroma indexing.
