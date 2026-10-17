# Project Audit: Localized Agentic Memory Framework

**Audit Date:** October 2026  
**Auditor:** Senior AI Systems & QA Engineer (Antigravity)  
**Project:** Localized Agentic Memory Framework (Final Year Engineering Project)  
**Target Environment:** Local execution on Windows/macOS/Linux, Python 3.12, Streamlit, Ollama, SQLite, ChromaDB  

---

## 1. Executive Summary

An exhaustive technical, architectural, QA, and privacy audit was performed on the repository. The project demonstrates a compelling and well-conceived dual-tier memory concept (ephemeral conversation buffer in SQLite -> consolidation and fact extraction via local LLM -> 3-layer semantic deduplication -> long-term vector memory in ChromaDB). 

However, the current codebase exhibits several critical structural defects, data integrity risks, privacy contradictions, and runtime failures that prevent it from functioning reliably on a fresh clone. Most notably:
1. **Repository Data & Privacy Incident:** A live Chroma database (`chroma/chroma.sqlite3` with 387 embedding records, index binary files, and `chroma.sqlite3.debug-backup`) containing previous developer chat snippets and extracted personal facts was committed to the Git repository.
2. **Fatal Dependency & Import Mismatch:** `src/router.py` attempts `from ddgs import DDGS`, which crashes immediately on import under `duckduckgo-search` (`ModuleNotFoundError: No module named 'ddgs'`).
3. **Broken Chat Context in CLI and UI:** `handle_chat(cleaned_input)` in both `src/chat.py` and `src/app.py` completely ignores its argument. In `chat.py`, the turn is not persisted before calling `load_history()`, causing the model to receive an empty prompt on turn 1.
4. **Canonical Store Self-Destruction:** `dedup.clear_synced_facts()` deletes all SQLite facts once they are synced to Chroma, destroying the relational source of truth, provenance, timestamps, and recovery capability.
5. **Premature Conversation Deletion:** `consolidate.py` deletes raw conversation turns immediately upon fact extraction before deduplication or vector indexing completes, risking irrecoverable data loss on mid-pipeline failure.
6. **False "Incognito" Privacy Leak:** `:incognito:` mode advertises itself as stateless and local, but actually fires an external HTTP request to DuckDuckGo (even though the prompt never consumes the search result).
7. **No Automatic Schema Initialization:** A fresh clone crashes because `src/app.py` does not execute `data/schema.sql` on startup.
8. **Missing Test Suite & Undeclared Dependencies:** The repository lacks automated unit tests; existing `tests/` files are manual scripts that require live external services. `src/benchmark.py` crashes due to missing `matplotlib`.

---

## 2. Architecture and Data Flow

### 2.1 Entry Points
- **Web Interface:** `src/app.py` (Streamlit web application).
- **CLI Interface:** `src/chat.py` (Command-line REPL loop).
- **Benchmark:** `src/benchmark.py` (Evaluation harness for deduplication accuracy).

### 2.2 Component Roles
- `src/prompts.py`: Template generation for web search, deepsearch, incognito, fact extraction, memory recall, and conflict resolution.
- `src/router.py`: Prefix-based command routing (`:search:`, `:deepsearch:`, `:remember:`, `:incognito:`), DuckDuckGo search execution, and ChromaDB query for memory recall.
- `src/consolidate.py`: Extracts atomic facts from raw session conversations via local LLM (`llama3.2:3b`), performs SHA-256 hash deduplication (Layer 1), and inserts facts into SQLite.
- `src/dedup.py`: Multi-tier deduplication. Queries unindexed facts from SQLite, compares against ChromaDB vectors via cosine similarity (Layer 2), routes ambiguous similarities (0.70 <= sim < 0.90) to local LLM conflict resolution (Layer 3), indexes to ChromaDB, and clears SQLite rows.
- `data/schema.sql`: DDL for `conversations` (buffer) and `facts` (extracted memories).

### 2.3 End-to-End Interaction & Memory Lifecycle Flow

```text
[User Input]
     │
     ├──> Prefix Router (src/router.py)
     │         ├── :search:     ──> DuckDuckGo Text Search ──> LLM ──> Answer
     │         ├── :deepsearch: ──> DDG + Trafilatura Scraping ──> LLM ──> Answer
     │         ├── :remember:   ──> ChromaDB Semantic Query ──> LLM ──> Answer
     │         ├── :incognito:  ──> Local LLM Only (Ephemeral, No Storage, No Web)
     │         └── Normal Chat  ──> SQLite Buffer ──> LLM Context ──> Answer
     │
[Session End / Consolidation]
     │
     ├──> src/consolidate.py
     │         ├── Extract conversation turns (SQLite)
     │         ├── Format transcript & call LLM fact extractor
     │         ├── Layer 1: SHA-256 exact match deduplication
     │         └── Insert candidate facts into SQLite canonical store
     │
     └──> src/dedup.py
               ├── Query pending facts from SQLite canonical store
               ├── Layer 2: Vector cosine similarity check (ChromaDB)
               │      ├── sim >= 0.90 ──> DUPLICATE (skip vector write)
               │      ├── sim < 0.70  ──> DISTINCT (index new vector)
               │      └── 0.70 <= sim < 0.90 ──> Layer 3: LLM Conflict Resolution
               │                                      ├── DUPLICATE
               │                                      ├── UPDATE (supersede)
               │                                      └── DISTINCT
               └── Synchronize index status in canonical SQLite store (DO NOT DELETE)
```

---

## 3. High-Priority Privacy & Repository Incident

### 3.1 Incident Analysis
- **Committed Files:**
  - `chroma/chroma.sqlite3` (Contains SQLite schema with tables `collections`, `embeddings`, `embedding_fulltext_search_content`).
  - `chroma/chroma.sqlite3.debug-backup`
  - `chroma/510a0e79-ce1f-4d20-b235-9ebcf2b527c0/*.bin`, `*.pickle`
- **Inspection Findings:**
  Inspecting `chroma/chroma.sqlite3` revealed **387 stored embedding records** and raw text content in fulltext search tables, including developer greeting exchanges and personal facts (e.g., student name, preferences, project details).
- **Root Cause:**
  `dedup.py` called `chromadb.PersistentClient()` without specifying a path, which defaults to `./chroma` in the current working directory. Although `.gitignore` included `chroma/`, the directory had already been tracked prior to being added to `.gitignore`. Git does not untrack committed files retroactively when `.gitignore` is modified.

### 3.2 Mitigation & Safety Actions Taken
1. **Preserve Safe Local Backup:** Extracted and copied all committed runtime artifacts to `backups/legacy_chroma_committed_backup/` for owner inspection.
2. **Untrack from Repository Index:** Executed `git rm -r --cached chroma/` so that runtime files are no longer tracked in future commits.
3. **Comprehensive `.gitignore` Hardening:** Added explicit ignore rules for all local databases (`*.db`, `*.sqlite`, `*.sqlite3`, `*-wal`, `*-shm`), Chroma directories, backup directories, test artifacts, exports, and caches.
4. **Isolated Default Runtime Directory:** Re-architect the application to store runtime databases in an OS-standard application-data folder (e.g., `%LOCALAPPDATA%\LocalizedAgenticMemory` on Windows) with `LAM_DATA_DIR` environment override, ensuring zero repository pollution on fresh clones.
5. **Public History Cleanup Advisory:** Documented explicit instructions for the repository owner to purge historical Git commits using `git-filter-repo` if this repository is publicly published.

---

## 4. Issue Register

### Legend
- **CD**: Confirmed Defect (verified by code analysis and execution failure)
- **LD**: Likely Defect (high-risk edge case or race condition)
- **FE**: Future / Structural Enhancement

| ID | Severity | File(s) & Function(s) | Category | Description | Remediation Plan |
|---|---|---|---|---|---|
| **CD-01** | Critical | `src/router.py:2` | Dependency / Import | `from ddgs import DDGS` fails with `ModuleNotFoundError`. Package installed is `duckduckgo_search`. | Import from `duckduckgo_search` with fallback to `ddgs`. Reconcile `requirements.txt`. |
| **CD-02** | Critical | `src/chat.py:52-64, 111` | Logic / Context | Model inference occurs before saving the user prompt to DB. `handle_chat(cleaned_input)` ignores `cleaned_input`. First turn receives empty context. | Save user turn before inference or pass current input directly in messages list. Pass `cleaned_input` explicitly. |
| **CD-03** | Critical | `src/app.py:179-184` | Logic / Context | `handle_chat(cleaned_input)` ignores its argument and reads only DB history. Redundant/fragile state contract. | Unify chat-turn lifecycle contract; pass current prompt explicitly. |
| **CD-04** | Critical | `src/app.py:141`, `data/schema.sql` | Startup / Database | Startup does not run `schema.sql`. Fresh clone crashes with `no such table: conversations`. | Implement automatic DB initialization and schema migration on app startup. |
| **CD-05** | High | `src/app.py:13`, `src/chat.py:10`, `src/dedup.py:15` | Configuration / Paths | Relative paths `data/memory.db` and `./chroma` depend on cwd. Running from outside root breaks storage. | Use centralized config with `pathlib` and support `LAM_DATA_DIR`. |
| **CD-06** | High | `src/router.py:107-122` | Privacy / Security | `:incognito:` performs an unprompted DuckDuckGo web search, leaking private queries to the web while ignoring the results. | Redefine Incognito as local-only, stateless, non-persistent: no network search, no DB writes. |
| **CD-07** | Critical | `src/dedup.py:61-63, 106` | Data Loss / Architecture | `clear_synced_facts()` deletes all SQLite facts after indexing into Chroma. Destroys the canonical store and metadata. | Stop deleting synced facts! Retain SQLite as authoritative store with `synced_to_chroma = 1` and full provenance. |
| **CD-08** | High | `src/consolidate.py:120-125, 144` | Data Loss / Integrity | `del_raw_conversations()` deletes raw turns before deduplication or indexing is verified. | Retain conversation records or only purge after end-to-end verified pipeline completion. Add configurable retention. |
| **CD-09** | Medium | `src/consolidate.py:30, 39` | Scalability / Ingestion | Hardcoded `LIMIT 50` on conversations leaves turns > 50 unprocessed or permanently dropped. | Ingest all unconsolidated turns in chunked batches without silent drops. |
| **CD-10** | Low | `src/consolidate.py:20-25` | Dead Code / Defect | `get_unconsolidated_session_ids` is unused and crashes if `fetchone()` returns `None`. | Remove or correctly implement and test. |
| **CD-11** | Medium | `src/dedup.py:21` | Import Side-Effect | `collection = get_chroma_collection()` runs on import, initializing persistent DB in cwd immediately. | Refactor to lazy-initialized service or context factory. |
| **CD-12** | Medium | `src/benchmark.py:17`, `requirements.txt` | Dependency | Benchmark imports `matplotlib` without declaring it in `requirements.txt`. | Add `matplotlib` to `requirements-dev.txt` / development dependencies. |
| **CD-13** | High | `src/app.py:225, 230` | Security (XSS) | User and model messages injected directly into custom HTML via `unsafe_allow_html=True`. | Replace with native Streamlit `st.chat_message` or sanitize inputs. |
| **CD-14** | Medium | `src/app.py:210-214` | UX / Credibility | UI displays "System Ready" static green badge without verifying Ollama, models, SQLite, or Chroma. | Implement genuine testable health check reporting actual component statuses. |
| **CD-15** | Medium | `src/router.py:71-86` | Reliability / SSRF | `handle_deepsearch` crashes if any single page fails to download. No timeouts, no private IP validation. | Add per-result error handling, timeout, URL validation, and size capping. |
| **CD-16** | Medium | `src/dedup.py:53-58` | Logic / NLP | `if "DUPLICATE" in decision` misidentifies "NOT A DUPLICATE", and unknown outputs silently become `DISTINCT`. | Strict decision parser with conservative fallback. |
| **CD-17** | Medium | `setup.bat`, `run.bat` | DevOps / Windows | Scripts lack error checking (`errorlevel`), prerequisite validation, and graceful exit diagnostics. | Rewrite setup and run scripts with validation, error traps, and diagnostic hints. |
| **CD-18** | High | `tests/` directory | QA / Automation | Tests are manual scripts; no repeatable offline pytest suite exists. | Implement comprehensive deterministic pytest regression suite with mocks. |
| **LD-01** | High | `src/dedup.py:93-96` | Concurrency / Integrity | `UPDATE` deletes from Chroma by `matched_id` and re-adds with `fact_id`, but old SQLite row is already gone. | Store supersedes/history relationship in SQLite. |
| **LD-02** | Medium | `src/app.py:348-356` | Streamlit State | Mode button reruns and enter callback can drop input or cause state desynchronization. | Streamline Streamlit form/input flow using unified state handler. |
| **FE-01** | Feature | UI / Memory Management | UX / Product | No way for users to view, search, edit, delete, or export their stored memories. | Build a dedicated "Memory Studio" tab with browse, edit, delete, export, and rebuild index. |
| **FE-02** | Feature | Architecture | Transparency | System does not explain why a recalled memory was used or show citations. | Return source memory metadata with recall and cite external search URLs. |

---

## 5. Baseline Test & Static Check Execution Record

| Command Run | Environment | Result | Details |
|---|---|---|---|
| `python --version; ollama --version` | System PATH | Python 3.12.10 OK, Ollama not in PATH | Ollama binary not installed/accessible on test machine. |
| `.\.venv\Scripts\python.exe -m pip list` | Virtualenv `.venv` | Pass | Identified missing `pytest`, `matplotlib`, and verified versions of `streamlit` (1.65), `chromadb` (1.5.9), `duckduckgo_search` (8.1.1). |
| `.\.venv\Scripts\python.exe -c "from ddgs import DDGS"` | Virtualenv `.venv` | **FAIL** (Exit 1) | `ModuleNotFoundError: No module named 'ddgs'`. Confirmed defect CD-01. |
| `.\.venv\Scripts\python.exe -c "from duckduckgo_search import DDGS"` | Virtualenv `.venv` | **PASS** (Exit 0) | Confirmed `duckduckgo_search` provides `DDGS`. |
| `.\.venv\Scripts\python.exe tests/test.py` | Virtualenv `.venv` | Pass (Exit 0) | Created `data/memory.db` manually from `data/schema.sql`. |
| `.\.venv\Scripts\python.exe tests/test_chromadb.py` | Virtualenv `.venv` | Pass (Exit 0) | Downloaded Chroma ONNX model `all-MiniLM-L6-v2` (~79MB), created collection, queried vectors. |
| `.\.venv\Scripts\python.exe tests/test_connection.py` | Virtualenv `.venv` | **FAIL** (Exit 1) | `ConnectionError: Failed to connect to Ollama`. Confirmed cannot run online Ollama tests in this environment. |
| `.\.venv\Scripts\python.exe src/benchmark.py` | Virtualenv `.venv` | **FAIL** (Exit 1) | `ModuleNotFoundError: No module named 'matplotlib'`. Confirmed defect CD-12. |

---

## 6. Implementation & Remediation Roadmap

The remediation strictly adheres to the mandated priority order:
- **Phase 1: Foundation & Reliability (Data Protection, Config, Canonical Storage, Correct Interactions, Offline Pytest Suite)**
- **Phase 2: Memory Integrity & Transparency (SQLite Canonical Store, Superceding/Versioning, Memory Studio Operations, Idempotency)**
- **Phase 3: UI Redesign & Product Polish (Modern Streamlit Design System, Real Health Status, Safe Rendering, Responsive Layout)**
- **Phase 4: Benchmarking, Packaging, & Documentation (Synthetic Viva Demo, Extended Benchmark Harness, Complete Guides)**
