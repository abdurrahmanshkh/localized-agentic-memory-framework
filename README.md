# Localized Agentic Memory Framework

[![CI Quality Gate](https://github.com/abdurrahmanshkh/localized-agentic-memory-framework/actions/workflows/ci.yml/badge.svg)](https://github.com/abdurrahmanshkh/localized-agentic-memory-framework/actions)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Local Inference: Ollama](https://img.shields.io/badge/Inference-Ollama%20Local-orange.svg)](https://ollama.com)

An edge-deployed, privacy-first AI memory system with dual-tier scheduled consolidation, 3-layer semantic deduplication, and a user-controlled Memory Studio — running entirely on consumer hardware.

---

## 📖 Overview

Standard AI assistants suffer from context amnesia: every session begins from scratch, forcing users to repeatedly explain their personal background, preferences, project constraints, and technical stack. Cloud solutions exist, but require uploading sensitive personal details and continuous conversational telemetry to proprietary servers.

The **Localized Agentic Memory Framework** solves this problem by providing **durable cross-session memory while ensuring that 100% of data and model inference remains on your personal machine**:

- **Dual-Tier Memory Architecture:** Recent conversations are buffered in an ephemeral SQLite store. At the end of a session, an autonomous consolidation agent extracts atomic facts about the user.
- **3-Layer Semantic Deduplication:** Extracted facts pass through exact hash matching, cosine similarity gating, and middle-band local LLM reasoning to prevent redundancy and handle updates/corrections gracefully.
- **Canonical Relational Truth:** SQLite is the authoritative canonical store for all facts, timestamps, categories, and provenance. ChromaDB serves as an auxiliary, rebuildable semantic vector index.
- **Memory Studio:** A comprehensive management interface allowing users to browse, search, edit, delete, export (JSON), import, and rebuild their memory store.
- **Verifiable Privacy:** Strictly offline by default. Features that make network requests (web search) are explicitly labeled and gated by user selection.

---

## 🏗️ Architecture at a Glance

```text
                                 [ User Input ]
                                       │
                ┌──────────────────────┴──────────────────────┐
                ▼                                             ▼
       Normal / Local Modes                         External Web Modes
  (Chat, Remember, Incognito)                      (Search, Deep Search)
                │                                             │
      ┌─────────┴─────────┐                         ┌─────────┴─────────┐
      ▼                   ▼                         ▼                   ▼
   SQLite            Ollama LLM                 DuckDuckGo         Trafilatura
Ephemeral Buffer  (Qwen / Llama 3)               Web Search        Page Scraper
      │
      ▼
 [ Session Consolidation ]
      │
      ├──> Layer 1: SHA-256 Exact Hash Match
      ├──> Layer 2: Vector Cosine Similarity (ChromaDB)
      └──> Layer 3: Local LLM Conflict Resolution (Duplicate vs Update vs Distinct)
      │
      ▼
 [ Canonical SQLite Storage & ChromaDB Vector Index ]
      │
      ▼
 [ Memory Studio & Cross-Session Semantic Recall ]
```

---

## ⚡ Quick Start

### 1. Prerequisites
- **Python 3.10, 3.11, or 3.12** installed and added to your system `PATH`.
- **[Ollama](https://ollama.com/download)** installed and running.
- Pull the recommended lightweight local models:
  ```bash
  ollama pull qwen2.5:1.5b
  ollama pull llama3.2:3b
  ```

### 2. Installation

#### Windows (Automated)
Simply double-click `setup.bat` or run:
```cmd
setup.bat
```

#### Linux / macOS (Automated)
```bash
chmod +x setup.sh run.sh
./setup.sh
```

#### Manual Installation (PowerShell / Bash)
```bash
python -m venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
python -c "from src import db; db.init_db()"
```

### 3. Launching the Assistant

#### Web Interface (Streamlit)
- **Windows:** Double-click `run.bat`
- **Terminal:**
  ```bash
  streamlit run src/app.py
  ```
The interface opens at `http://localhost:8501`.

#### Terminal CLI
```bash
python src/chat.py
```

---

## 🎮 Interaction Modes

| Mode | Prefix / Button | Offline? | Storage | Purpose |
|---|---|---|---|---|
| **Chat** | *(default)* | **Yes** | Buffered in SQLite | Standard conversational chat with recent session context. |
| **Remember** | `:remember:` | **Yes** | Read-only vector recall | Semantic recall of stored facts with similarity scores and provenance. |
| **Incognito** | `:incognito:` | **Yes** | **Zero Persistence** | 100% stateless execution: no network calls, no DB writes, no Chroma access. |
| **Search** | `:search:` | No | Buffered in SQLite | Live DuckDuckGo web search with cited source links. |
| **Deep Search** | `:deepsearch:` | No | Buffered in SQLite | Multi-page scraping (Trafilatura) with SSRF defenses and 5-bullet summary. |

---

## 🧪 Testing and Benchmarks

### Automated Offline Regression Suite
The repository includes a comprehensive pytest suite (29 tests) that runs offline in ~12 seconds without requiring Ollama or internet access:
```bash
python -m pytest -v
```

### Deduplication Benchmark (v3)
Evaluates the 3-layer deduplication pipeline against 30 ground-truth pairs (including hard negatives with numerical changes, date mismatches, and negation words):
```bash
# Run against local Ollama (if running)
python src/benchmark.py

# Run in deterministic offline evaluation mode
python src/benchmark.py --offline
```

**Latest Measured Results:**
- **Precision:** 0.786
- **Recall:** 0.917
- **Accuracy:** 0.867
- **F1 Score:** 0.846  *(Baseline Exact Match: 0.000)*

Outputs: `benchmark_results.json` and `benchmark_results.png`.

---

## 🎓 Academic Viva & Demonstration Walkthrough

To demonstrate the system during a final-year evaluation:
1. Open the **📊 Benchmark & Demo** tab in the sidebar.
2. Select **"🎓 Synthetic Viva Demo Mode"** and click **"Load Synthetic Demo Dataset"** (imports 7 non-personal sample facts).
3. Switch to **💬 Chat Workspace**:
   - Query: `:remember: What is my capstone project topic?`
   - Observe how the assistant recalls the memory and expands the transparency panel showing similarity score and source session.
4. Test conflict resolution and updates:
   - Type: `Actually, my project deadline was extended to December 20th.`
   - Click **"💾 End Session & Consolidate Memory"**.
   - Open **🧠 Memory Studio** to show how the old deadline fact was marked `superseded` and replaced by the new active fact in both SQLite and ChromaDB.
5. Demonstrate privacy:
   - Ask a question in `:incognito:` mode.
   - Show in Memory Studio and SQLite that zero entries were recorded.
6. When finished, click **"🧹 Clear Demo Dataset Only"** to purge demo facts while preserving personal memories.

---

## 📁 Project Documentation

Detailed technical documentation is available in the `docs/` directory:

- [Project Audit & Confirmed Defects](docs/PROJECT_AUDIT.md): Comprehensive baseline audit, defect register, and remediation roadmap.
- [System Architecture](docs/ARCHITECTURE.md): Component diagrams, schema specifications, and deduplication logic.
- [Windows Installation Guide](docs/INSTALLATION_WINDOWS.md): Step-by-step setup, troubleshooting, and configuration on Windows.
- [User & Operations Guide](docs/USER_GUIDE.md): Complete guide to interaction modes, Memory Studio, and viva demonstration.
- [Testing & Benchmarks](docs/TESTING_AND_BENCHMARKS.md): Test suite details, execution commands, and benchmark evaluation.
- [Privacy & Data Migration Guide](docs/PRIVACY_AND_DATA_MIGRATION.md): Data locations, legacy Chroma exposure remediation, and Git history cleanup guidance.
- [Upgrade Log](docs/UPGRADE_LOG.md): Student-readable chronological log of all architectural and code changes.
- [Changelog](CHANGELOG.md): Concise release-oriented summary of user-visible updates.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
