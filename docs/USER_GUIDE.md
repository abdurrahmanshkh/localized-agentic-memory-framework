# User and Operation Guide: Localized Agentic Memory Framework

## 1. Getting Started

When you launch the framework (via `run.bat` or `streamlit run src/app.py`), the web interface opens with 5 primary workspaces accessible from the sidebar:
1. **💬 Chat Workspace:** Your primary conversational assistant.
2. **🧠 Memory Studio:** Browse, search, edit, delete, export, and rebuild memories.
3. **📜 Sessions & History:** Review previous sessions and configure conversation retention.
4. **⚙️ System & Health:** View live Ollama, model, SQLite, and Chroma diagnostics.
5. **📊 Benchmark & Demo:** Examine accuracy metrics, test fact pairs, and load synthetic demo data.

---

## 2. Interaction Modes Explained

You can select a mode by clicking its button in the Chat Workspace or by typing its command prefix in the message box.

### 💬 Mode 1: Chat (Default)
- **Prefix:** None (or simply type normally)
- **Behavior:** Standard conversational chat. The assistant maintains a recent context window of your conversation turns within the current session.
- **Privacy:** 100% offline and local. Turns are buffered in SQLite until session consolidation.

### 🧠 Mode 2: Remember
- **Prefix:** `:remember: <your query>`
- **Behavior:** Performs a semantic search against your ChromaDB long-term memory store, extracts relevant facts, and synthesizes a direct response.
- **Transparency:** An expandable panel displays the exact recalled memories used to construct the answer, including their cosine similarity score and source session.
- **Example:**
  ```text
  :remember: What is my final year project deadline?
  ```

### 🕶️ Mode 3: Incognito
- **Prefix:** `:incognito: <your query>`
- **Behavior:** A stateless, local-only conversation.
- **Strict Guarantees:**
  - **Zero Network Activity:** No web queries are dispatched.
  - **Zero Disk Persistence:** No entries are written to `conversations` or `facts` in SQLite.
  - **Zero Vector Access:** ChromaDB is neither read nor written.
  - Context exists strictly in transient RAM for that turn and is discarded immediately.

### 🔍 Mode 4: Search
- **Prefix:** `:search: <your query>`
- **Behavior:** Executes a targeted DuckDuckGo web search, downloads top snippets, and answers using the results.
- **Citations:** Displays reference sources with titles and clickable URLs.
- **Example:**
  ```text
  :search: Latest advancements in local LLM quantization
  ```

### 📖 Mode 5: Deep Search
- **Prefix:** `:deepsearch: <your query>`
- **Behavior:** Executes a web search and scrapes the full text of top result pages (using Trafilatura), synthesizing a concise 5-bullet summary.
- **Security:** Validates all URLs to prevent internal network requests (SSRF protection) and treats scraped content strictly as untrusted data.

---

## 3. Session Consolidation & Long-Term Memory

Memory is not extracted on every single message turn. Instead, it follows a clean session lifecycle:

1. **Chat Naturally:** Share your preferences, project details, decisions, or corrections during the session.
2. **End Session & Save Memory:** When you have finished your conversation, click the **"💾 End Session & Consolidate Memory"** button at the bottom of the Chat view.
3. **The 3-Layer Consolidation Pipeline Executes:**
   - **Extraction:** A local model (`llama3.2:3b`) parses the session transcript and extracts atomic standalone facts about the user.
   - **Layer 1 (Hash Check):** Exact duplicates are discarded immediately by comparing SHA-256 hashes against active facts in SQLite.
   - **Layer 2 (Vector Cosine Similarity):** Semantically identical facts ($s \ge 0.90$) are auto-skipped. Unrelated facts ($s < 0.70$) are indexed as distinct.
   - **Layer 3 (Conflict Reasoning):** Ambiguous pairs ($0.70 \le s < 0.90$) or facts with conflicting numbers/dates/negations are evaluated by the local LLM. If the fact represents an update, the old memory is marked `superseded` in SQLite and replaced in ChromaDB.
4. **Summary Feedback:** The UI reports how many facts were extracted, added, skipped as duplicates, or updated.

---

## 4. Using the Memory Studio

The **Memory Studio** gives you complete transparency and control over what the AI remembers about you:

### 1. Browse and Search Memories
- Use the search bar to filter stored memories by keyword.
- Filter by status (`active`, `superseded`, or `all`).

### 2. Edit / Correct a Memory
- Expand any memory card.
- Edit the text in the input box and click **"Save Edit"**.
- Both the canonical SQLite record and the Chroma vector embedding are updated simultaneously.

### 3. Delete an Individual Memory
- Click **"🗑️ Delete"** inside a memory card.
- The record is permanently purged from SQLite and removed from the Chroma vector index.

### 4. Reconcile & Rebuild Vector Index
- If you ever suspect that the Chroma vector index is out of sync or corrupted, click **"🔄 Reconcile & Rebuild Index"**.
- This scans all active facts in SQLite and idempotently rebuilds the vector store from scratch.

### 5. Export and Import
- **Export:** Click **"⬇️ Download Export (JSON)"** to save a timestamped, structured backup of all your memories.
- **Import:** Upload a previously exported JSON backup and click **"📥 Import Backup"**. Facts will be validated and merged safely through deduplication.

### 6. Danger Zone: Erase All Memories
- At the bottom of the Memory Studio, an expandable box allows you to erase the entire memory store after checking an explicit confirmation checkbox.

---

## 5. Academic Viva and Demonstration Mode

If you are demonstrating this project to professors, examiners, or teammates:

1. Navigate to the **📊 Benchmark & Demo** tab in the sidebar.
2. Click on **"🎓 Synthetic Viva Demo Mode"**.
3. Click **"📥 Load Synthetic Demo Dataset"**.
4. The system will load 7 non-personal, pre-tagged student facts (such as name, project topic, preferences, technical stack, presentation date).
5. Switch to **💬 Chat Workspace**:
   - Ask: `:remember: What is my capstone project topic?`
   - Observe how the assistant recalls the memory and displays the transparency panel showing similarity and source session.
6. Test a correction:
   - Type: `Actually, my presentation date has been moved to December 15th.`
   - Click **"End Session & Consolidate Memory"**.
   - Open Memory Studio and observe how the old presentation date was marked `superseded` and replaced with the new date.
7. Demonstrate Incognito:
   - Switch to `:incognito:` and ask a question.
   - Open Memory Studio and show that zero records were stored.
8. When finished, return to **📊 Benchmark & Demo** and click **"🧹 Clear Demo Dataset Only"** to remove only demo data while preserving personal memories.
