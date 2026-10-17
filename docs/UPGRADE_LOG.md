# Localized Agentic Memory Framework: Upgrade Log

This chronological engineering log documents every meaningful change made to the repository. It is written so that collaborators, evaluators, and engineering students can understand what changed, why, how it works now, and how it was verified.

---

## [Phase 1 - Baseline & Data Protection] 2026-10-17

### Problem / Limitation Before the Change
1. **Committed Runtime Database Artifacts:** The Git repository tracked runtime Chroma database files (`chroma/chroma.sqlite3`, `chroma.sqlite3.debug-backup`, and index files in `chroma/510a0e79-ce1f-4d20-b235-9ebcf2b527c0/`). Inspection confirmed that `chroma.sqlite3` contained 387 stored embedding records with personal greeting transcripts and user facts from earlier testing.
2. **Fragile Working Directory Dependencies:** Storage paths were relative (`data/memory.db`, `./chroma`), meaning execution from any other folder corrupted or fragmented data stores.
3. **No Systematic Audit or Baseline Test Record:** The project lacked a comprehensive architectural map, issue register, and baseline test execution log.

### Files / Modules Changed
- `docs/PROJECT_AUDIT.md`: Created comprehensive architecture analysis, issue register (18 confirmed defects), data flow, and baseline execution record.
- `docs/UPGRADE_LOG.md`: Initialized chronological upgrade register.
- `backups/legacy_chroma_committed_backup/`: Created a safe local backup of the legacy Chroma directory.
- `c:\Users\abdur\Code Projects\localized-agentic-memory-framework\.gitignore`: Updated to comprehensively ignore databases, vector stores, backups, logs, test artifacts, and caches.

### What Changed and How It Works Now
- **Backup Created:** All files previously in `chroma/` were backed up safely to `backups/legacy_chroma_committed_backup/` so no historical data is lost during remediation.
- **Untracked from Git:** The runtime directory `chroma/` was untracked from the Git index (`git rm -r --cached chroma/`) while preserving the local copy on disk.
- **Hardened `.gitignore`:** Configured `.gitignore` to explicitly ignore `chroma/`, `backups/`, `*.db`, `*.sqlite`, `*.sqlite3`, `*-wal`, `*-shm`, `logs/`, `exports/`, and pytest caches.
- **Audit Published:** `docs/PROJECT_AUDIT.md` outlines the confirmed defect register and planned architectural remediation.

### Why the Change Was Needed & Trade-offs
- **Reason:** Committing runtime databases into a public or shared repository exposes personal user data and causes synchronization conflicts between machines. Fresh clones must start with an empty, isolated store.
- **Trade-off:** Removing files from the latest commit index does not rewrite past Git commit history. A separate advisory in `docs/PRIVACY_AND_DATA_MIGRATION.md` provides safe instructions for repository owners if they wish to rewrite public Git history using `git-filter-repo`.

### Tests / Commands Executed & Exact Results
- `python --version; ollama --version`: Python 3.12.10 detected; Ollama not found in system PATH.
- `.\.venv\Scripts\python.exe -m pip list`: Verified installed packages (`chromadb 1.5.9`, `streamlit 1.65.0`, `duckduckgo-search 8.1.1`, `ollama 0.6.3`). Identified missing `pytest` and `matplotlib`.
- `.\.venv\Scripts\python.exe -c "from ddgs import DDGS"`: FAILED (Exit 1: `ModuleNotFoundError: No module named 'ddgs'`).
- `.\.venv\Scripts\python.exe -c "from duckduckgo_search import DDGS"`: PASSED (Exit 0).
- `.\.venv\Scripts\python.exe tests/test.py`: PASSED (Exit 0, created `data/memory.db`).
- `.\.venv\Scripts\python.exe tests/test_chromadb.py`: PASSED (Exit 0, downloaded default ONNX model `all-MiniLM-L6-v2` ~79MB).
- `.\.venv\Scripts\python.exe tests/test_connection.py`: FAILED (Exit 1: `ConnectionError: Failed to connect to Ollama`).
- `.\.venv\Scripts\python.exe src/benchmark.py`: FAILED (Exit 1: `ModuleNotFoundError: No module named 'matplotlib'`).

### Migration or Data Impact
- The committed `chroma/` files have been untracked from Git. Existing local files remain intact and backed up in `backups/legacy_chroma_committed_backup/`. Users cloning anew will no longer inherit someone else's personal memories.

### Known Limitations or Follow-up Items
- Runtime data paths still need to be migrated to a centralized configuration module (`src/config.py`) using `LAM_DATA_DIR`.
- Offline pytest suite needs to be established.

---

## [Phase 2 - Core Refactoring, Storage Migration & Interaction Reliability] 2026-10-17

### Problem / Limitation Before the Change
1. **Scattered Configurations & Model IDs:** Model tags, timeouts, and thresholds were hardcoded across multiple files (`app.py`, `chat.py`, `router.py`, `dedup.py`).
2. **Missing Schema Initialization:** `app.py` assumed `data/memory.db` existed with tables already created. A fresh clone crashed on startup with SQLite `OperationalError: no such table: conversations`.
3. **Turn Ordering & History Inconsistency:** In the CLI (`src/chat.py`), `load_history()` ran before the user prompt was saved, resulting in the current prompt being omitted or handled unpredictably.
4. **Fragile External Search & SSRF Risk:** In `src/router.py`, `from ddgs import DDGS` failed because the installed package was `duckduckgo_search`. In `handle_deepsearch()`, any single failed web fetch crashed the entire search turn. There was no SSRF protection against private IP scraping.
5. **Incognito Privacy Leak:** The `incognito` mode issued a DuckDuckGo search without using the results, leaking queries to public search engines while falsely claiming to be an incognito session.
6. **No Mock Client or Offline Testing:** All tests required a live Ollama daemon and pre-pulled models.

### Files / Modules Changed
- `src/config.py`: Created centralized configuration module resolving `LAM_DATA_DIR` (`%LOCALAPPDATA%\LocalizedAgenticMemory` or `~/.local/share/LocalizedAgenticMemory`), default models (`qwen2.5:1.5b`, `llama3.2:3b`), timeouts, and similarity thresholds.
- `src/db.py`: Implemented robust SQLite layer with automatic schema initialization (`init_db`), WAL journal mode, parameterized queries, and schema migration adding `status`, `superseded_by_id`, `updated_at`, and `category` columns to `facts`.
- `src/models.py`: Created `LocalOllamaClient` and `MockOllamaClient` abstraction with fast timeout detection (`check_ollama_status`), graceful error mapping (`OllamaConnectionError`, `ModelNotFoundError`, `InferenceTimeoutError`).
- `src/vector_store.py`: Built lazy-initialized ChromaDB wrapper with cosine distance, automatic index directory resolution inside `LAM_DATA_DIR`, metadata sanitization, and full index rebuild capabilities.
- `src/search.py`: Implemented dual-import DDGS search (`duckduckgo_search` / `ddgs`), per-page exception absorption (partial success handling), content size truncation (12,000 chars), and strict SSRF prevention (`is_safe_external_url`) blocking loopback, link-local, and RFC-1918 private IP ranges.
- `src/prompts.py`: Hardened system prompts with anti-prompt-injection delimiters for web search summaries and fact extraction.
- `src/router.py`: Rebuilt query routing with input validation, command prefix routing (`:search:`, `:deepsearch:`, `:remember:`, `:incognito:`), bounded context-window trimming, and a strictly stateless, offline Incognito mode.
- `src/chat.py`: Upgraded CLI REPL with pre-flight health checks and correct user-turn persistence ordering before inference.

### What Changed and How It Works Now
- **Storage Relocation:** User runtime data is now placed in `%LOCALAPPDATA%\LocalizedAgenticMemory` on Windows (or `~/.local/share/LocalizedAgenticMemory` on Linux/macOS), keeping the Git repository strictly code-only. Configurable via the `LAM_DATA_DIR` environment variable.
- **Self-Healing Schema:** On any application startup (CLI, UI, tests), `init_db()` runs automatically, applies `data/schema.sql`, and runs incremental migrations safely within transactions.
- **True Incognito Mode:** Incognito now performs zero network requests, zero SQLite reads/writes, zero Chroma vector reads/writes, and leaves no persistent memory traces.
- **Graceful Error Degradation:** Missing Ollama or absent models no longer crash with unhandled stack traces; the UI and CLI display clear, actionable diagnostic messages with setup commands.
- **SSRF Hardening:** Search fetcher validates URLs before requesting, ensuring internal networks and loopback services cannot be probed.

### Why the Change Was Needed & Trade-offs
- **Reason:** A final-year engineering system must not crash on fresh launch or leak network queries when in privacy mode.
- **Trade-off:** Incognito no longer accesses web search; web search is now an explicit user-selected tool (`Search` or `Deep Search`) with clear external network disclosures.

### Tests / Commands Executed & Exact Results
- Created unit tests in `tests/test_startup_and_db.py`, `tests/test_chat_and_routing.py`, `tests/test_search_and_security.py`, and `tests/test_models_and_errors.py`.
- Ran `.\.venv\Scripts\python.exe -m pytest tests/test_startup_and_db.py tests/test_chat_and_routing.py tests/test_search_and_security.py tests/test_models_and_errors.py -q`:
  - Result: **17 passed** in 3.42s.

### Migration or Data Impact
- Automatic schema migration runs on first connection; existing `memory.db` files are upgraded with new metadata columns without dropping existing conversation or fact tables.

---

## [Phase 3 - Memory Integrity, Deduplication & Memory Studio] 2026-10-17

### Problem / Limitation Before the Change
1. **Destructive Memory Lifecycle:** In `src/dedup.py`, `clear_synced_facts()` deleted facts from SQLite once indexed into ChromaDB. If Chroma crashed or index files were corrupted, user memories were permanently lost.
2. **Hard Negative Collapses:** Facts like "User is 21 years old" and "User is 22 years old" had high vector cosine similarity (0.965), which exceeded the automatic duplicate threshold (0.90) and resulted in the framework silently discarding changed numbers and updates without LLM conflict checks.
3. **Session Consolidation Vulnerability:** `consolidate.py` used a hardcoded `LIMIT 50`, dropping messages beyond turn 50 in long sessions. Repeated consolidation triggers resulted in duplicated extraction.
4. **No User Memory Inspection or Correction:** Users had no way to view, edit, search, or delete stored memories from the application.

### Files / Modules Changed
- `src/memory_service.py`: Implemented canonical memory service where SQLite is the durable single source of truth and ChromaDB is a rebuildable projection.
- `src/memory_service.py`: Built 3-layer deduplication engine:
  - Layer 1: Exact normalized text hash match (O(1)).
  - Layer 2: Cosine vector similarity check. If similarity > 0.90 AND the texts do not have numerical/date/negation differences, treat as duplicate.
  - Layer 3: Conservative LLM conflict resolution. If similarity is between 0.75 and 0.90, or if numbers/negations differ, prompt LLM to classify as `DUPLICATE`, `CONTRADICTS_UPDATE`, or `DISTINCT`.
- `src/memory_service.py`: Added `has_conflicting_numbers_or_negation()` heuristic to protect hard negatives from false auto-deduplication.
- `src/memory_service.py`: Added full memory lifecycle operations: `list_facts()`, `search_facts()`, `update_fact()` (with versioning and superseding provenance), `delete_fact()` (removing from both SQLite and Chroma), `clear_all_facts()`, `reconcile_index()`, `export_memories()`, and `import_memories()`.
- `src/memory_service.py`: Added chunked session consolidation (50-message windows) with idempotent session tracking and status flags.

### What Changed and How It Works Now
- **Canonical Storage Preserved:** Facts are never deleted from SQLite upon vector indexing. SQLite holds full metadata (status, created_at, updated_at, category, superseded_by_id).
- **Index Rebuildability:** If the Chroma index is deleted or out-of-sync, `reconcile_index()` can rebuild the entire vector store directly from SQLite in seconds.
- **Hard-Negative Protection:** Changes in numerical values (e.g., age, salary, dates) or negation words (e.g., "like" vs "hate") are automatically caught and routed to LLM conflict resolution rather than falsely merged as duplicates.
- **Memory Studio API:** Full administrative control over user memories, supporting pagination, keyword filtering, edits with provenance, single/bulk deletions, and JSON backup/restore.

### Why the Change Was Needed & Trade-offs
- **Reason:** Users must have sovereignty over their personal data. Memory loss via syncing deletions or false duplicate merges undermines the core thesis of an agentic memory assistant.
- **Trade-off:** Adding Layer 3 LLM conflict evaluation slightly increases consolidation latency when facts are ambiguous, but preserves data correctness.

### Tests / Commands Executed & Exact Results
- Created `tests/test_memory_and_dedup.py` with 7 comprehensive unit tests (exact duplicate, semantic duplicate, hard-negative number preservation, contradiction updates, consolidation idempotence, CRUD operations, and index reconciliation).
- Ran `.\.venv\Scripts\python.exe -m pytest tests/test_memory_and_dedup.py -q`:
  - Result: **7 passed** in 2.15s.

---

## [Phase 4 - UI/UX Redesign & Student Viva Demonstration Mode] 2026-10-17

### Problem / Limitation Before the Change
1. **Unsafe HTML Injection:** `src/app.py` rendered user and model messages via `st.markdown(..., unsafe_allow_html=True)` inside custom HTML divs, exposing the interface to XSS injection.
2. **Misleading "System Ready" Status:** The green badge was displayed on page load without verifying whether Ollama, required models, or databases were actually operational.
3. **No Visual Separation of Network vs Local Modes:** Users could not tell when external web requests were being made versus purely local offline inference.
4. **Single Monolithic View:** Chat, memory, and settings were crammed into one confusing layout without dedicated inspection tooling.
5. **UI Latency from Uncached Health Checks:** Synchronous Ollama checks with 5-second timeouts stalled the Streamlit UI event loop when Ollama was offline.

### Files / Modules Changed
- `src/app.py`: Complete overhaul into a professional 5-workspace multi-tab interface:
  - **Chat Workspace:** Native `st.chat_message` with streaming response, clear mode selector, external network badges, transparent memory recall expanders, and web source citations.
  - **Memory Studio:** Interactive memory management table, semantic vector search tool, fact editor, deletion with confirmation dialog, index rebuild button, and JSON export/import.
  - **Sessions & History:** Session browser, message inspector, and explicit session consolidation triggers with visual progress flow.
  - **System & Health:** Diagnostic dashboard checking SQLite, Chroma, Ollama service, and model availability with fast timeouts (0.5s/1.0s), data directory info, and privacy explanations.
  - **Benchmark & Demo:** Viva presentation workspace with academic benchmark results, interactive charts, and a synthetic 1-click demo dataset loader.
- `src/demo_data.py`: Created synthetic demo dataset containing non-personal academic scenarios (preferences, project context, hardware details) for safe presentation without exposing real user data.
- `tests/test_app_ui.py`: Added Streamlit UI automated test suite using `streamlit.testing.v1.AppTest`.

### What Changed and How It Works Now
- **100% Safe Native Rendering:** Zero custom HTML injection. All chat content and memories are rendered via Streamlit's native components (`st.chat_message`, `st.markdown`, `st.dataframe`).
- **Real-Time Network Badging:** When "Search" or "Deep Search" is active, a prominent `EXTERNAL NETWORK ACTIVE` badge appears. In "Chat", "Recall", or "Incognito", a `100% LOCAL & OFFLINE` badge is displayed.
- **Fast Diagnostic Polling:** Health checks use a 0.5s connection probe with internal caching, preventing UI thread stalls even when Ollama is stopped.
- **Viva Demo Mode:** A student can click "Load Synthetic Demo", demonstrate recall across sessions, show deduplication in action, and wipe the demo cleanly with zero risk to personal data.

### Why the Change Was Needed & Trade-offs
- **Reason:** Academic defense and real-world evaluation require an intuitive, bug-free interface that demonstrates transparency and security.
- **Trade-off:** Custom CSS styling was reduced in favor of standard Streamlit components to ensure compatibility with future Streamlit updates.

### Tests / Commands Executed & Exact Results
- Ran `.\.venv\Scripts\python.exe -m pytest tests/test_app_ui.py -q`:
  - Result: **2 passed** in 3.10s.

---

## [Phase 5 - Benchmarking, Packaging, DevOps & Documentation] 2026-10-17

### Problem / Limitation Before the Change
1. **Unreproducible Benchmark:** `src/benchmark.py` crashed due to missing `matplotlib` and had only 28 hardcoded test pairs. It had no offline deterministic evaluation mode.
2. **Missing Dependencies & Packaging:** `requirements.txt` lacked `pytest`, `matplotlib`, and `ruff`. Setup and run scripts lacked prerequisite checks and failed silently.
3. **No CI Pipeline:** The repository had no continuous integration to guarantee code quality or prevent regressions across operating systems.
4. **Scattered and Incomplete Documentation:** The README was minimal and did not explain architecture, privacy boundaries, or viva demonstration workflows.

### Files / Modules Changed
- `src/benchmark.py`: Overhauled into benchmark v3 supporting:
  - 30 comprehensive evaluation pairs (exact duplicates, semantic paraphrases, hard negatives with changed numbers/dates, contradictions/negations, and distinct facts).
  - `--offline` deterministic evaluation flag using `MockOllamaClient` alongside live Ollama execution.
  - Generates verified metrics in `benchmark_results.json` and visual comparison chart `benchmark_results.png`.
- `requirements.txt` & `requirements-dev.txt`: Split runtime and development dependencies cleanly.
- `pyproject.toml` & `pytest.ini`: Configured modern Python packaging, Ruff linter rules, and pytest test markers.
- `setup.bat` & `run.bat`: Hardened Windows scripts with directory resolution (`%~dp0`), Python 3.10+ validation, virtual environment activation, dependency installation, and error exits.
- `setup.sh` & `run.sh`: Added cross-platform shell scripts for Linux and macOS.
- `.github/workflows/ci.yml`: Added GitHub Actions CI matrix testing Ubuntu and Windows on Python 3.10, 3.11, and 3.12, running Ruff linting and the offline pytest suite.
- `docs/ARCHITECTURE.md`: Created detailed architectural guide with Mermaid diagrams, storage models, and data flows.
- `docs/INSTALLATION_WINDOWS.md`: Comprehensive Windows setup, troubleshooting, and Ollama configuration guide.
- `docs/USER_GUIDE.md`: Full end-user guide covering interaction modes, Memory Studio operations, and viva presentation scripts.
- `docs/TESTING_AND_BENCHMARKS.md`: Complete testing documentation, offline execution commands, and benchmark results analysis.
- `docs/PRIVACY_AND_DATA_MIGRATION.md`: Privacy boundaries, mode data matrix, legacy data migration, and Git history cleanup guidance.
- `CHANGELOG.md`: Release-oriented summary of v2.0.0 changes.
- `README.md`: Polished root documentation with badge status, quickstart, and feature overview.

### What Changed and How It Works Now
- **Verified Benchmark Metrics:** Benchmark v3 was executed in offline mode:
  - Framework: Precision = 0.786, Recall = 0.917, Accuracy = 0.867, F1 = 0.846.
  - Naive Baseline: Precision = 0.000, Recall = 0.000, Accuracy = 0.600, F1 = 0.000.
  - Generates publication-ready `benchmark_results.json` and `benchmark_results.png`.
- **Reliable Zero-Click Setup:** Windows users can simply double-click `setup.bat` followed by `run.bat` to launch the application.
- **Zero-Failure Offline Regression:** Full test suite runs completely offline in ~7 seconds without external network or Ollama requirements.
- **Ruff Compliance:** All codebase files pass Ruff linting with 0 errors.

### Tests / Commands Executed & Exact Results
- Benchmark run: `.\.venv\Scripts\python.exe src/benchmark.py --offline`
  - Output: `Accuracy: 0.867, Precision: 0.786, Recall: 0.917, F1: 0.846`. Successfully wrote `benchmark_results.json` and `benchmark_results.png`.
- Full pytest run: `.\.venv\Scripts\python.exe -m pytest -q`
  - Output: **28 passed, 1 skipped in 7.02s** (1 skipped test was the explicit live Ollama integration test).
- Ruff check: `.\.venv\Scripts\python.exe -m ruff check src tests`
  - Output: `All checks passed!` (0 errors).

---

