# Privacy, Data Security, and Migration Guide

## 1. Overview and Core Privacy Principles

The **Localized Agentic Memory Framework** is designed as a privacy-conscious, local-first artificial intelligence assistant. Its primary objective is to maintain persistent cross-session memory while ensuring that personal data, conversations, and learned preferences remain strictly under user control.

### Core Guarantees:
1. **Local Model Inference:** All conversational completions, memory extractions, and conflict resolutions run through local models via Ollama. No third-party proprietary LLM APIs receive your prompts or facts.
2. **Explicit Network Boundaries:** Features that require external network access (standard Search and Deep Search via DuckDuckGo) are explicitly labeled and gated by user selection. They are never triggered accidentally.
3. **Canonical Relational Storage:** SQLite is the authoritative canonical store for all conversational records, extracted facts, timestamps, provenance, and statuses. ChromaDB serves as an ephemeral or rebuildable semantic vector index.
4. **Isolated Default Runtime Directory:** Runtime databases and indexes are stored by default outside the repository tree in an OS-standard user data directory, with a configurable environment variable override (`LAM_DATA_DIR`).

---

## 2. Modes and Network / Storage Matrix

The system provides 5 distinct operational modes. The table below discloses their exact storage and network behavior:

| Mode | Prefix / Selector | Network Access? | Persistent SQLite Buffer? | Persistent Chroma Vector? | Consolidation Target? |
|---|---|---|---|---|---|
| **Chat** | `(normal)` | **None (Offline)** | Yes (`conversations` table) | Yes (upon consolidation) | Yes |
| **Remember** | `:remember:` | **None (Offline)** | Yes (`conversations` table) | Read-only vector search | Yes |
| **Incognito** | `:incognito:` | **None (Offline)** | **No (0 writes)** | **No (0 writes / 0 reads)** | **No (Excluded)** |
| **Search** | `:search:` | **Yes (DuckDuckGo)** | Yes (`conversations` table) | No (External web search) | Yes |
| **Deep Search** | `:deepsearch:` | **Yes (DDG + Scrape)** | Yes (`conversations` table) | No (External web scrape) | Yes |

### Incognito Mode Guarantee
In earlier versions of the codebase, `:incognito:` mistakenly issued a DuckDuckGo web query. This has been remediated. Under the current implementation:
- **Zero Network Activity:** No HTTP requests are dispatched.
- **Zero Disk Persistence:** No entries are written to `conversations` or `facts` in SQLite.
- **Zero Vector Access:** ChromaDB is neither read nor written.
- **Excluded from Consolidation:** Incognito conversations will never be extracted into long-term memory.
- **Ephemeral State Only:** Context is maintained solely in transient process memory for the duration of the turn or session rerun.

---

## 3. Storage Architecture and Data Locations

### Default Storage Paths
- **Configurable Environment Override:** `LAM_DATA_DIR`
- **Windows Default:** `%LOCALAPPDATA%\LocalizedAgenticMemory`  
  (e.g., `C:\Users\<username>\AppData\Local\LocalizedAgenticMemory`)
- **macOS Default:** `~/Library/Application Support/LocalizedAgenticMemory`
- **Linux Default:** `~/.local/share/LocalizedAgenticMemory`

Inside the runtime data directory:
- `memory.db`: Authoritative SQLite database containing `conversations`, `facts`, and migration metadata.
- `chroma/`: ChromaDB persistent directory containing the HNSW vector indexes and embedding SQLite metadata.
- `exports/`: Default directory for user-requested JSON memory backups.

### Fallback & Testing Isolation
When running unit tests or specifying an isolated environment, setting `LAM_DATA_DIR=<custom_path>` redirects all database and vector operations cleanly without polluting user data or repository files.

---

## 4. Remediation of Tracked ChromaDB Exposure

### What Happened
In earlier commits of the project repository, the directory `chroma/` (containing `chroma.sqlite3`, `chroma.sqlite3.debug-backup`, and binary index files) was tracked and committed to Git. An inspection revealed that `chroma.sqlite3` held 387 embedding records and text snippets containing developer test dialogues and personal facts.

### Action Taken in This Upgrade
1. **Safe Local Backup:** The entire committed `chroma/` directory was backed up to `backups/legacy_chroma_committed_backup/`.
2. **Untracked from Git Tree:** `git rm -r --cached chroma/` was executed to ensure runtime databases are not tracked in modern commits.
3. **Strict Ignore Rules:** `.gitignore` was updated to exclude `chroma/`, `*.db`, `*.sqlite`, `*.sqlite3`, `*-wal`, `*-shm`, `backups/`, `exports/`, and debug backups.
4. **Isolated New Storage:** Default application runtime data was decoupled from the repository root and moved to `%LOCALAPPDATA%\LocalizedAgenticMemory`. A fresh clone starts with a clean, empty personal database.

### Public Git History Cleanup Guide (For Repository Owner)
> [!WARNING]
> Removing files from the Git working tree or the latest commit (`git rm --cached`) does **NOT** erase them from past Git commit history. If this repository was ever pushed to a public remote (such as GitHub), the previous commit objects still contain the old `chroma.sqlite3` file.

To permanently eradicate the legacy database from all past Git commits:

1. **Coordinate with Collaborators:** Ensure all team members have pushed any outstanding branches.
2. **Install `git-filter-repo`:**
   ```bash
   pip install git-filter-repo
   ```
3. **Execute Filter-Repo on a Fresh Clone:**
   ```bash
   # Clone a fresh copy into a temporary directory
   git clone --mirror <REPO_URL> repo-cleanup.git
   cd repo-cleanup.git

   # Analyze and purge chroma files from history
   git filter-repo --path chroma/ --invert-paths

   # Verify that chroma/ is gone from all commits
   git log --all --full-history -- "chroma/*"

   # Force push clean history to remote (requires admin permissions)
   git push origin --force --all
   git push origin --force --tags
   ```
4. **Secret Rotation:** If any API keys, passwords, or personal credentials were ever typed into chat while testing earlier versions, treat them as exposed and rotate them immediately.

---

## 5. Memory Deletion, Feedback, and Export Semantics

### Deletion Semantics
- **Single Memory Deletion:** When a user deletes a memory in the Memory Studio, the record is immediately deleted from the canonical SQLite `facts` table AND its corresponding embedding vector is deleted from the ChromaDB collection using its stable ID. It can no longer be retrieved by semantic search.
- **Bulk Memory Clear:** Requires explicit user confirmation. Clears both the SQLite `facts` table and Chroma collection completely.
- **Turn Feedback ("Thumbs Down"):** In chat, marking a response as unhelpful deletes the immediate user prompt and assistant turn from the SQLite `conversations` buffer. Because consolidation only extracts from remaining unconsolidated rows, rejected turns are never analyzed for fact extraction.

### Export & Import Semantics
- **JSON Export:** The Memory Studio provides a "Export Memories" feature. Exports produce a structured, versioned JSON payload containing memory text, timestamps, provenance, and categories.
  > [!NOTE]
  > Plain JSON exports are unencrypted. Store them in a secure location.
- **Safe Import:** Importing memories validates schema version and field integrity. Imported facts are assigned new UUIDs, recorded in SQLite, and indexed into ChromaDB. Existing data is preserved; duplicate facts are resolved via the standard 3-layer deduplication engine.
