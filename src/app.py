"""
Localized Agentic Memory Framework - Streamlit Web Application

A privacy-first, local AI memory assistant featuring:
- Conversational chat with recent context memory
- Semantic recall (:remember:) with transparent provenance
- Stateless local Incognito mode (:incognito:)
- External web search (:search:, :deepsearch:) with cited sources
- Dedicated Memory Studio (browse, search, edit, delete, export, import, reconcile)
- Live testable health diagnostics (Ollama, models, SQLite, Chroma)
- Interactive deduplication testing and synthetic viva demo data
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

import chromadb
import streamlit as st

try:
    from . import config, db, dedup, demo_data, memory_service, models, router
    from .vector_store import VectorStore
except ImportError:
    import config
    import db
    import dedup
    import demo_data
    import memory_service
    import models
    import router
    from vector_store import VectorStore

# ---------------------------------------------------------
# Page Configuration & Styling
# ---------------------------------------------------------
st.set_page_config(
    page_title=f"{config.APP_NAME} v{config.APP_VERSION}",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom minimal CSS for clean spacing, badges, and readability
st.markdown("""
<style>
    .reportview-container .main .block-container {
        max-width: 1100px;
        padding-top: 2rem;
        padding-bottom: 3rem;
    }
    .badge-local {
        display: inline-block;
        background-color: #E8F5E9;
        color: #2E7D32;
        border: 1px solid #A5D6A7;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.82rem;
        font-weight: 600;
        margin-left: 8px;
    }
    .badge-network {
        display: inline-block;
        background-color: #E3F2FD;
        color: #1565C0;
        border: 1px solid #90CAF9;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.82rem;
        font-weight: 600;
        margin-left: 8px;
    }
    .badge-incognito {
        display: inline-block;
        background-color: #EDE7F6;
        color: #512DA8;
        border: 1px solid #B39DDB;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.82rem;
        font-weight: 600;
        margin-left: 8px;
    }
    .timing-caption {
        color: #757575;
        font-size: 0.78rem;
        margin-top: 4px;
    }
    .stButton>button {
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------
# Application State Initialization
# ---------------------------------------------------------
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []

if "selected_mode" not in st.session_state:
    st.session_state.selected_mode = "chat"

if "retain_raw_conversations" not in st.session_state:
    st.session_state.retain_raw_conversations = True

# Initialize database schema automatically on startup
db.init_db()

# Cached services
@st.cache_resource
def get_vector_store() -> VectorStore:
    return VectorStore()

vector_store = get_vector_store()
db_conn = db.get_db_connection()


# ---------------------------------------------------------
# Health Check Helper
# ---------------------------------------------------------
def get_system_health() -> dict[str, Any]:
    ollama_info = models.check_ollama_status(timeout=0.5)
    installed_models = [m.lower() for m in ollama_info.get("models", [])]

    def _is_installed(model_name: str) -> bool:
        target = model_name.strip().lower()
        for m in installed_models:
            if m == target or m.startswith(f"{target}:") or target.startswith(f"{m}:"):
                return True
        return False

    chat_ready = ollama_info["running"] and _is_installed(config.MODEL_CHAT)
    extraction_ready = ollama_info["running"] and _is_installed(config.MODEL_EXTRACTION)

    try:
        active_facts_count = db_conn.execute("SELECT count(*) FROM facts WHERE status = 'active'").fetchone()[0]
        conversations_count = db_conn.execute("SELECT count(*) FROM conversations").fetchone()[0]
        db_ready = True
    except Exception:
        active_facts_count = 0
        conversations_count = 0
        db_ready = False

    vector_count = vector_store.count()

    overall_ready = ollama_info["running"] and chat_ready and extraction_ready and db_ready

    return {
        "overall_ready": overall_ready,
        "ollama_running": ollama_info["running"],
        "ollama_host": ollama_info["host"],
        "models_installed": ollama_info.get("models", []),
        "chat_model_ready": chat_ready,
        "extraction_model_ready": extraction_ready,
        "db_ready": db_ready,
        "active_facts_count": active_facts_count,
        "conversations_count": conversations_count,
        "vector_count": vector_count,
    }


health = get_system_health()


# ---------------------------------------------------------
# Sidebar Navigation & System Status
# ---------------------------------------------------------
with st.sidebar:
    st.title("🧠 Local Memory")
    st.caption(f"{config.APP_NAME} v{config.APP_VERSION}")

    # Genuine status badge
    if health["overall_ready"]:
        st.success("● System Ready (Local Offline)")
    elif not health["ollama_running"]:
        st.error("● Ollama Offline")
    elif not health["chat_model_ready"] or not health["extraction_model_ready"]:
        st.warning("● Required Model Missing")
    else:
        st.info("● System Initializing")

    st.markdown("---")
    navigation = st.radio(
        "Navigation",
        ["💬 Chat Workspace", "🧠 Memory Studio", "📜 Sessions & History", "⚙️ System & Health", "📊 Benchmark & Demo"],
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.markdown("### Quick Stats")
    col_stat1, col_stat2 = st.columns(2)
    col_stat1.metric("Active Facts", health["active_facts_count"])
    col_stat2.metric("Vectors", health["vector_count"])

    st.markdown("---")
    st.markdown("### Active Session")
    st.caption(f"`{st.session_state.session_id[:8]}...`")

    if st.button("➕ New Chat Session", use_container_width=True):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()


# =========================================================
# TAB 1: CHAT WORKSPACE
# =========================================================
if navigation == "💬 Chat Workspace":
    # Header with mode descriptions and badges
    header_col1, header_col2 = st.columns([3, 1])
    with header_col1:
        st.subheader("Conversational Workspace")
    with header_col2:
        current_mode = st.session_state.selected_mode
        if current_mode in ("search", "deepsearch"):
            st.markdown('<div class="badge-network">🌐 External Web Access</div>', unsafe_allow_html=True)
        elif current_mode == "incognito":
            st.markdown('<div class="badge-incognito">🕶️ Stateless Incognito</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="badge-local">🔒 Local Device Only</div>', unsafe_allow_html=True)

    # Mode Selector Bar
    modes = [
        ("chat", "💬 Chat", "Normal conversation with recent context memory"),
        ("remember", "🧠 Remember", "Semantic recall from long-term memory store"),
        ("incognito", "🕶️ Incognito", "Stateless, zero network requests, zero storage"),
        ("search", "🔍 Search", "Quick DuckDuckGo web search with cited sources"),
        ("deepsearch", "📖 Deep Search", "Multi-page scraping and synthesized summary"),
    ]

    mode_cols = st.columns(len(modes))
    for i, (m_id, m_label, m_desc) in enumerate(modes):
        with mode_cols[i]:
            is_active = st.session_state.selected_mode == m_id
            if st.button(
                m_label,
                key=f"btn_mode_{m_id}",
                type="primary" if is_active else "secondary",
                use_container_width=True,
                help=m_desc,
            ):
                st.session_state.selected_mode = m_id
                st.rerun()

    # Mode helper description
    active_desc = next(d for k, _, d in modes if k == st.session_state.selected_mode)
    st.caption(f"**Active Mode:** {active_desc}")

    # Conversation Container
    chat_container = st.container()
    with chat_container:
        if not st.session_state.messages:
            st.info("Start chatting with your assistant. When you end a session, key facts about you are extracted, deduplicated, and remembered for future conversations.")

        for idx, msg in enumerate(st.session_state.messages):
            role = msg["role"]
            content = msg["content"]
            with st.chat_message(role):
                st.markdown(content)

                # Show sources if any (for search modes)
                if msg.get("sources"):
                    with st.expander("🔗 Reference Sources Cited"):
                        for s in msg["sources"]:
                            st.markdown(f"- [{s['title']}]({s['url']})")

                # Show recalled memory transparency (for remember mode)
                if msg.get("recalled_facts"):
                    with st.expander("🧠 Recalled Memories Used to Answer"):
                        for rf in msg["recalled_facts"]:
                            sim = rf.get("similarity", 0.0)
                            st.markdown(f"- **(similarity: {sim:.2f})** {rf['fact_text']}")

                # Show honest timing breakdown
                if msg.get("timing"):
                    t = msg["timing"]
                    timing_parts = []
                    if "infer_ms" in t:
                        timing_parts.append(f"Model: {t['infer_ms']:.1f}ms")
                    if "write_ms" in t and t["write_ms"] > 0:
                        timing_parts.append(f"DB Write: {t['write_ms']:.2f}ms")
                    if "search_ms" in t and t["search_ms"] > 0:
                        timing_parts.append(f"Network: {t['search_ms']:.1f}ms")
                    if timing_parts:
                        st.markdown(f'<div class="timing-caption">{" | ".join(timing_parts)}</div>', unsafe_allow_html=True)

                # Turn feedback buttons for saved turns
                if role == "assistant" and msg.get("user_msg_id") and not msg.get("feedback_given"):
                    fcol1, fcol2, _ = st.columns([1, 1, 8])
                    with fcol1:
                        if st.button("👍 Helpful", key=f"thumb_up_{idx}"):
                            st.session_state.messages[idx]["feedback_given"] = "up"
                            st.rerun()
                    with fcol2:
                        if st.button("👎 Remove", key=f"thumb_down_{idx}", help="Removes this interaction from session memory"):
                            # Delete turns from SQLite buffer
                            db.delete_turns(db_conn, [msg.get("user_msg_id"), msg.get("assistant_msg_id")])
                            st.session_state.messages[idx]["feedback_given"] = "down"
                            st.rerun()
                elif msg.get("feedback_given") == "down":
                    st.caption("Turn marked unhelpful: removed from session buffer and excluded from memory.")

    # Chat Input
    user_prompt = st.chat_input("Type your message (or use prefixes: :search:, :deepsearch:, :remember:, :incognito:)...")

    if user_prompt:
        # Check prefix routing first
        detected_mode, cleaned_input = router.route_message(user_prompt)
        effective_mode = detected_mode if detected_mode != "chat" else st.session_state.selected_mode

        # Display and record user prompt
        st.session_state.messages.append({"role": "user", "content": user_prompt})

        # Process through appropriate handler
        mclient = models.LocalOllamaClient()
        assistant_record: dict[str, Any] = {"role": "assistant"}

        with st.spinner("Processing..."):
            try:
                if effective_mode == "incognito":
                    res = router.handle_incognito(cleaned_input, client=mclient)
                    assistant_record.update({
                        "content": res["reply"],
                        "timing": {"infer_ms": res["infer_ms"]},
                    })

                elif effective_mode == "search":
                    res = router.handle_search(cleaned_input, client=mclient)
                    assistant_record.update({
                        "content": res["reply"],
                        "sources": res.get("sources", []),
                        "timing": {"infer_ms": res["infer_ms"], "search_ms": res["search_ms"]},
                    })

                elif effective_mode == "deepsearch":
                    res = router.handle_deepsearch(cleaned_input, client=mclient)
                    assistant_record.update({
                        "content": res["reply"],
                        "sources": res.get("sources", []),
                        "timing": {"infer_ms": res["infer_ms"], "search_ms": res["search_ms"]},
                    })

                elif effective_mode == "remember":
                    res = router.handle_remember(db_conn, cleaned_input, vector_store=vector_store, client=mclient)
                    assistant_record.update({
                        "content": res["reply"],
                        "recalled_facts": res.get("recalled_facts", []),
                        "timing": {"infer_ms": res["infer_ms"]},
                    })

                else:  # normal chat
                    res = router.handle_chat(db_conn, st.session_state.session_id, cleaned_input, client=mclient)
                    assistant_record.update({
                        "content": res["reply"],
                        "user_msg_id": res.get("user_msg_id"),
                        "assistant_msg_id": res.get("assistant_msg_id"),
                        "timing": {"infer_ms": res["infer_ms"], "write_ms": res["write_ms"]},
                    })

            except models.OllamaConnectionError as e:
                assistant_record["content"] = f"⚠️ **Ollama Service Unavailable**\n\n{e}"
            except models.ModelNotFoundError as e:
                assistant_record["content"] = f"⚠️ **Required Model Missing**\n\n{e}"
            except Exception as e:
                assistant_record["content"] = f"⚠️ **Error:** {e}"

        st.session_state.messages.append(assistant_record)
        st.rerun()

    # Session Consolidation Footer
    st.markdown("---")
    cons_col1, cons_col2 = st.columns([2, 1])
    with cons_col1:
        st.markdown("**Session Actions**")
        st.caption("Consolidate current session conversation into permanent deduplicated facts.")
    with cons_col2:
        if st.button("💾 End Session & Consolidate Memory", type="primary", use_container_width=True):
            with st.spinner("Extracting durable facts and running 3-layer deduplication..."):
                try:
                    c_res = memory_service.consolidate_session(
                        conn=db_conn,
                        session_id=st.session_state.session_id,
                        vector_store=vector_store,
                        retain_raw=st.session_state.retain_raw_conversations,
                    )
                    if c_res["status"] == "empty":
                        st.info("No new conversation turns to consolidate.")
                    else:
                        st.success(
                            f"Consolidation complete: {c_res['facts_extracted']} facts extracted, "
                            f"{c_res['facts_added']} added to long-term memory, "
                            f"{c_res['duplicates']} duplicates skipped, "
                            f"{c_res['updates']} updates superseded."
                        )
                except Exception as e:
                    st.error(f"Consolidation failed: {e}")


# =========================================================
# TAB 2: MEMORY STUDIO
# =========================================================
elif navigation == "🧠 Memory Studio":
    st.subheader("Memory Studio")
    st.caption("Inspect, search, edit, delete, export, and rebuild your authoritative local memory store.")

    mem_col_left, mem_col_right = st.columns([3, 1])
    with mem_col_left:
        search_query = st.text_input("🔍 Search stored memories", placeholder="Filter memories by keyword...")
    with mem_col_right:
        status_filter = st.selectbox("Status Filter", ["active", "superseded", "all"])

    memories = memory_service.list_memories(db_conn, status=status_filter, search_query=search_query, limit=100)

    st.markdown(f"**Found {len(memories)} memories**")

    if not memories:
        st.info("No memories match your query. Chat normally and consolidate sessions to build memories.")
    else:
        for m in memories:
            m_id = m["id"]
            with st.expander(f"#{m_id}: {m['fact_text'][:80]}... ({m['status'].upper()})", expanded=False):
                st.markdown(f"**Full Fact:** {m['fact_text']}")
                meta_cols = st.columns(4)
                meta_cols[0].caption(f"**Category:** {m.get('category', 'general')}")
                meta_cols[1].caption(f"**Created:** {m.get('consolidated_date', 'N/A')}")
                meta_cols[2].caption(f"**Status:** {m.get('status', 'active')}")
                meta_cols[3].caption(f"**Source Session:** `{str(m.get('source_session_id', ''))[:8]}...`")

                if m.get("superseded_by_id"):
                    st.caption(f"↳ Superseded by Fact #{m['superseded_by_id']}")

                # Edit Memory
                edit_col, del_col = st.columns([3, 1])
                with edit_col:
                    new_text = st.text_input("Edit memory text", value=m["fact_text"], key=f"edit_input_{m_id}")
                    if st.button("Save Edit", key=f"save_edit_{m_id}"):
                        if new_text.strip() != m["fact_text"]:
                            memory_service.update_memory(db_conn, vector_store, m_id, new_text.strip())
                            st.success(f"Memory #{m_id} updated.")
                            st.rerun()

                with del_col:
                    st.write("")
                    st.write("")
                    if st.button("🗑️ Delete", key=f"del_btn_{m_id}", type="secondary"):
                        memory_service.delete_memory(db_conn, vector_store, m_id)
                        st.warning(f"Memory #{m_id} deleted permanently.")
                        st.rerun()

    st.markdown("---")
    st.markdown("### Management & Portability")
    mgt_col1, mgt_col2, mgt_col3 = st.columns(3)

    # Reconcile & Rebuild
    with mgt_col1:
        st.markdown("**Index Reconciliation**")
        st.caption("Rebuilds the Chroma vector store from canonical SQLite facts.")
        if st.button("🔄 Reconcile & Rebuild Index", use_container_width=True):
            with st.spinner("Rebuilding vector store from canonical records..."):
                rep = memory_service.reconcile_and_rebuild(db_conn, vector_store)
                st.success(f"Rebuild finished: {rep['rebuilt_vectors']} vectors indexed.")

    # Export Memories
    with mgt_col2:
        st.markdown("**Export Memories**")
        st.caption("Download all stored facts as portable JSON.")
        export_payload = memory_service.export_memories(db_conn)
        export_json = json.dumps(export_payload, indent=2)
        st.download_button(
            label="⬇️ Download Export (JSON)",
            data=export_json,
            file_name=f"lam_memories_{datetime.now().strftime('%Y%m%d')}.json" if 'datetime' in locals() else "lam_memories.json",
            mime="application/json",
            use_container_width=True,
        )

    # Import Memories
    with mgt_col3:
        st.markdown("**Import Memories**")
        st.caption("Restore memories from a JSON export file.")
        uploaded_file = st.file_uploader("Choose backup file", type=["json"], label_visibility="collapsed")
        if uploaded_file is not None:
            if st.button("📥 Import Backup", use_container_width=True):
                try:
                    data = json.load(uploaded_file)
                    imp_res = memory_service.import_memories(db_conn, vector_store, data)
                    st.success(f"Imported: {imp_res['imported']} new facts ({imp_res['skipped']} skipped duplicates).")
                    st.rerun()
                except Exception as e:
                    st.error(f"Import failed: {e}")

    # Bulk Clear Section (Safeguarded)
    st.markdown("---")
    with st.expander("⚠️ Danger Zone: Clear Entire Memory Store"):
        st.warning("This action permanently deletes all facts from SQLite and empties the Chroma vector index. This cannot be undone.")
        confirm_clear = st.checkbox("I understand that this will erase all stored memories")
        if st.button("Erase All Memories", type="primary", disabled=not confirm_clear):
            cleared_count = memory_service.clear_all_memories(db_conn, vector_store)
            st.success(f"Erased {cleared_count} memories from storage.")
            st.rerun()


# =========================================================
# TAB 3: SESSIONS & HISTORY
# =========================================================
elif navigation == "📜 Sessions & History":
    st.subheader("Session Management & Conversation Logs")
    st.caption("Review previous session buffers, consolidation statuses, and retention settings.")

    # Retention Setting
    ret_col1, ret_col2 = st.columns([2, 1])
    with ret_col1:
        st.markdown("**Raw Conversation Retention Policy**")
        st.caption("Choose whether raw turns remain in SQLite after successful consolidation or are purged for privacy.")
    with ret_col2:
        st.session_state.retain_raw_conversations = st.toggle(
            "Retain Raw Conversations After Consolidation",
            value=st.session_state.retain_raw_conversations,
        )

    st.markdown("---")
    # Fetch recent sessions
    sessions_query = """
        SELECT session_id, count(*) as turn_count,
               sum(case when consolidated = 1 then 1 else 0 end) as consolidated_count,
               min(timestamp) as started_at
        FROM conversations
        GROUP BY session_id
        ORDER BY min(timestamp) DESC
        LIMIT 20
    """
    session_rows = db_conn.execute(sessions_query).fetchall()

    if not session_rows:
        st.info("No conversation sessions recorded yet.")
    else:
        for s in session_rows:
            sid = s["session_id"]
            t_count = s["turn_count"]
            c_count = s["consolidated_count"] or 0
            is_active = sid == st.session_state.session_id

            with st.expander(f"Session `{sid[:8]}...` | {t_count} turns ({c_count} consolidated) | Started: {s['started_at']}", expanded=is_active):
                turns = db.load_history(db_conn, sid)
                for t in turns:
                    st.markdown(f"**{t['role'].capitalize()}:** {t['content']}")


# =========================================================
# TAB 4: SYSTEM & HEALTH
# =========================================================
elif navigation == "⚙️ System & Health":
    st.subheader("System Health, Configuration, & Privacy")
    st.caption("Diagnostic metrics verifying local Ollama inference, storage paths, and privacy isolation.")

    h_col1, h_col2 = st.columns(2)

    with h_col1:
        st.markdown("### Service Diagnostics")
        st.markdown(f"**Ollama Service:** {'🟢 Running' if health['ollama_running'] else '🔴 Offline'}")
        st.caption(f"Host: `{health['ollama_host']}`")

        st.markdown(f"**Chat Model (`{config.MODEL_CHAT}`):** {'🟢 Available' if health['chat_model_ready'] else '🔴 Missing'}")
        st.markdown(f"**Reasoning/Extraction Model (`{config.MODEL_EXTRACTION}`):** {'🟢 Available' if health['extraction_model_ready'] else '🔴 Missing'}")

        if not health["ollama_running"]:
            st.error("Ollama is not running. Start the service using:\n```bash\nollama serve\n```")
        elif not health["chat_model_ready"] or not health["extraction_model_ready"]:
            st.warning("To download missing models, run in a terminal:\n```bash\nollama pull qwen2.5:1.5b\nollama pull llama3.2:3b\n```")

    with h_col2:
        st.markdown("### Storage & Paths")
        st.markdown(f"**Canonical Database:** {'🟢 Connected' if health['db_ready'] else '🔴 Error'}")
        st.caption(f"`{config.get_db_path()}`")

        st.markdown(f"**ChromaDB Vector Store:** 🟢 Initialized ({health['vector_count']} records)")
        st.caption(f"`{config.get_chroma_dir()}`")

        st.markdown(f"**Runtime Data Directory:** `{config.get_runtime_data_dir()}`")

    st.markdown("---")
    st.markdown("### Privacy & Network Disclosure")
    st.table([
        {"Mode": "Chat (💬)", "Offline?": "Yes (Local)", "SQLite Persisted?": "Yes", "Chroma Indexed?": "Upon session end", "Network Activity": "None"},
        {"Mode": "Remember (🧠)", "Offline?": "Yes (Local)", "SQLite Persisted?": "Yes", "Chroma Indexed?": "Read-only recall", "Network Activity": "None"},
        {"Mode": "Incognito (🕶️)", "Offline?": "Yes (Local)", "SQLite Persisted?": "No (0 writes)", "Chroma Indexed?": "No (0 access)", "Network Activity": "None"},
        {"Mode": "Search (🔍)", "Offline?": "No (External)", "SQLite Persisted?": "Yes", "Chroma Indexed?": "No", "Network Activity": "DuckDuckGo Text API"},
        {"Mode": "Deep Search (📖)", "Offline?": "No (External)", "SQLite Persisted?": "Yes", "Chroma Indexed?": "No", "Network Activity": "DDG + Web Scraping"},
    ])


# =========================================================
# TAB 5: BENCHMARK & DEMO
# =========================================================
elif navigation == "📊 Benchmark & Demo":
    st.subheader("Academic Benchmark & Demonstration")
    st.caption("Verification harness for the 3-layer deduplication engine and synthetic viva demo data.")

    bench_tab1, bench_tab2, bench_tab3 = st.tabs(["📈 Benchmark Evaluation", "🧪 Test Fact Pair Sandbox", "🎓 Synthetic Viva Demo Mode"])

    # Sub-tab 1: Benchmark Results
    with bench_tab1:
        st.markdown("### Latest Measured Results")
        bench_json_path = config.PROJECT_ROOT / "benchmark_results.json"
        bench_png_path = config.PROJECT_ROOT / "benchmark_results.png"

        if bench_json_path.exists():
            with open(bench_json_path, "r", encoding="utf-8") as f:
                bdata = json.load(f)

            b_base = bdata["baseline"]
            b_sys = bdata["system"]
            b_meta = bdata.get("metadata", {})

            st.caption(f"**Evaluated on:** {b_meta.get('evaluation_date', 'N/A')} | **Mode:** {b_meta.get('mode', 'N/A')} | **Test Pairs:** {b_meta.get('total_pairs', 'N/A')}")

            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            m_col1.metric("Precision", f"{b_sys['precision']:.3f}", delta=f"{b_sys['precision'] - b_base['precision']:.3f} vs baseline")
            m_col2.metric("Recall", f"{b_sys['recall']:.3f}", delta=f"{b_sys['recall'] - b_base['recall']:.3f} vs baseline")
            m_col3.metric("Accuracy", f"{b_sys['accuracy']:.3f}", delta=f"{b_sys['accuracy'] - b_base['accuracy']:.3f} vs baseline")
            m_col4.metric("F1 Score", f"{b_sys['f1']:.3f}", delta=f"{b_sys['f1'] - b_base['f1']:.3f} vs baseline")

            if bench_png_path.exists():
                st.image(str(bench_png_path), caption="Deduplication Pipeline Performance Comparison")
        else:
            st.info("No benchmark results generated yet. Run `python src/benchmark.py` in the terminal.")

    # Sub-tab 2: Interactive Sandbox
    with bench_tab2:
        st.markdown("### Test a Fact Pair Live")
        st.caption("Enter two facts to trace how the 3-layer pipeline evaluates them (Exact Hash -> Vector Cosine -> LLM Conflict Resolution).")

        sand_col1, sand_col2 = st.columns(2)
        with sand_col1:
            fact1 = st.text_input("Existing Fact (Fact A)", value="User is 21 years old")
        with sand_col2:
            fact2 = st.text_input("New Fact (Fact B)", value="User is 22 years old")

        if st.button("Evaluate Pair Through Pipeline", type="primary"):
            norm1 = " ".join(fact1.strip().lower().split())
            norm2 = " ".join(fact2.strip().lower().split())

            st.markdown("#### Execution Trace:")
            # Layer 1 Check
            h1 = memory_service.hash_fact(fact1)
            h2 = memory_service.hash_fact(fact2)
            st.write(f"**Layer 1 (Exact Hash Match):** Hash A=`{h1[:12]}...` vs Hash B=`{h2[:12]}...`")
            if h1 == h2:
                st.success("Result: EXACT DUPLICATE (Resolved at Layer 1)")
            else:
                st.info("Result: Hashes distinct -> Proceeding to Layer 2")

                # Layer 2 Check
                test_chroma = chromadb.Client()
                col = test_chroma.create_collection(name="sandbox_test", metadata={"hnsw:space": "cosine"})
                col.add(documents=[fact1], ids=["f1"])
                sim, _, _ = dedup.check_similarity(col, fact2)
                test_chroma.delete_collection("sandbox_test")

                sim_val = sim if sim is not None else 0.0
                has_hard_diff = memory_service.has_conflicting_numbers_or_negation(fact1, fact2)
                st.write(f"**Layer 2 (Cosine Similarity):** `{sim_val:.3f}` (Hard differences detected: `{has_hard_diff}`)")

                if sim_val >= config.AUTO_DUPLICATE_THRESHOLD and not has_hard_diff:
                    st.success("Result: AUTO DUPLICATE (Resolved at Layer 2)")
                elif sim_val < config.AUTO_DISTINCT_THRESHOLD and not has_hard_diff:
                    st.info("Result: AUTO DISTINCT (Resolved at Layer 2)")
                else:
                    st.warning("Result: Ambiguous similarity or hard differences detected -> Proceeding to Layer 3")
                    # Layer 3 Check
                    mclient = models.LocalOllamaClient()
                    dec = dedup.resolve_conflict(fact1, fact2, client=mclient)
                    st.markdown(f"**Layer 3 (LLM Conflict Resolution):** Decision = **`{dec}`**")
                    if dec == "UPDATE":
                        st.info("Action: Update existing memory record (supersede old, add new)")
                    elif dec == "DUPLICATE":
                        st.success("Action: Skip duplicate vector")
                    else:
                        st.info("Action: Add as distinct new memory")

    # Sub-tab 3: Synthetic Viva Demo Mode
    with bench_tab3:
        st.markdown("### Synthetic Viva Demo Dataset")
        st.caption("Load a clean set of synthetic student facts to demonstrate the framework during a project viva without exposing personal data.")

        demo_col1, demo_col2 = st.columns(2)
        with demo_col1:
            if st.button("📥 Load Synthetic Demo Dataset", use_container_width=True, type="primary"):
                demo_res = demo_data.load_synthetic_demo_data(db_conn, vector_store)
                st.success(f"Loaded {demo_res['imported']} synthetic demo facts ({demo_res['skipped']} skipped).")
                st.rerun()

        with demo_col2:
            if st.button("🧹 Clear Demo Dataset Only", use_container_width=True):
                cleared = demo_data.clear_synthetic_demo_data(db_conn, vector_store)
                st.info(f"Cleared {cleared} synthetic demo records. Personal memories remain intact.")
                st.rerun()

        st.markdown("#### Sample Demo Facts Provided:")
        for df in demo_data.SYNTHETIC_DEMO_FACTS:
            st.markdown(f"- **[{df['category']}]** {df['fact_text']}")
