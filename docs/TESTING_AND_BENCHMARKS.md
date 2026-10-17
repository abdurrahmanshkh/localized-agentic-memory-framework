# Testing Strategy and Benchmark Evaluation

## 1. Quality Assurance Strategy

The framework employs a two-tier testing methodology designed for academic rigor and reproducibility:

1. **Deterministic Offline Unit & Regression Suite:**
   - Runs completely offline without requiring internet access or a running Ollama server.
   - Uses dependency injection and mock adapters (`MockOllamaClient`, in-memory `VectorStore`, temporary SQLite databases).
   - Validates all edge cases, input validation, transaction rollbacks, deduplication logic, SSRF protections, error handling, and Streamlit UI rendering.
2. **Live Integration Tests:**
   - Marked with `@pytest.mark.integration`.
   - Automatically skipped if the local Ollama server is offline so they never block clean-checkout CI builds or offline grading.

---

## 2. Test Suite Overview & Commands

### Running the Default Offline Test Suite
From the repository root with virtual environment activated:
```bash
python -m pytest -v
```
Or for concise output:
```bash
python -m pytest -q
```

### Running Specific Test Modules
```bash
# Test database initialization and migrations
python -m pytest tests/test_startup_and_db.py -v

# Test command routing and Incognito isolation
python -m pytest tests/test_chat_and_routing.py -v

# Test 3-layer deduplication and Memory Studio operations
python -m pytest tests/test_memory_and_dedup.py -v

# Test search sanitization and SSRF defenses
python -m pytest tests/test_search_and_security.py -v

# Test model error boundaries and timeouts
python -m pytest tests/test_models_and_errors.py -v

# Test end-to-end multi-turn conversation and recall lifecycle
python -m pytest tests/test_integration_offline.py -v

# Test Streamlit UI startup and navigation
python -m pytest tests/test_app_ui.py -v
```

### Running Live Integration Tests (Requires Ollama running)
```bash
python -m pytest -m "integration" -v
```

---

## 3. Test Module Coverage Breakdown (29 Automated Tests)

| Test Module | Tests | Key Capabilities Verified |
|---|---|---|
| `test_startup_and_db.py` | 5 | Fresh database creation, schema.sql execution, idempotent migrations, turn writes, session isolation, transaction rollback on failure, turn deletion feedback. |
| `test_chat_and_routing.py` | 4 | Prefix routing (:search:, :deepsearch:, :remember:, :incognito:), empty query validation, prompt inclusion exactly once in chat context, zero storage and zero network in Incognito. |
| `test_search_and_security.py` | 3 | SSRF protection (blocking localhost, 127.0.0.1, ::1, 10.x, 192.168.x, 172.16.x, 169.254.x), empty search handling, partial page scrape error absorption. |
| `test_models_and_errors.py` | 5 | Ollama offline health detection, ModelNotFoundError actionable message (`ollama pull`), connection error wrapping, inference timeout handling. |
| `test_memory_and_dedup.py` | 7 | Bulleted fact extraction parsing, NO_FACTS detection, strict conflict decision parsing (negation protection e.g. "NOT A DUPLICATE"), Layer 1 exact hash deduplication, Layer 3 UPDATE superseding old fact in SQLite, >50 message chunking, Memory Studio CRUD and rebuild, JSON export/import. |
| `test_integration_offline.py` | 1 | Full end-to-end lifecycle: Multi-turn chat -> Session consolidation -> New session recall with transparency metadata -> Incognito zero-trace verification. |
| `test_app_ui.py` | 2 | Streamlit AppTest simulation: verified error-free startup, state initialization, navigation radio options. |
| `test_chromadb.py` | 1 | ChromaDB in-memory collection creation, cosine space indexing, vector query. |
| `test_connection.py` | 1 | Live Ollama connection check (gracefully skipped when offline). |

---

## 4. Deduplication Benchmark (v3)

### Task Formulation
Given a pair of user facts $(A, B)$, predict whether $B$ represents an existing match (either a duplicate rephrasing or an updated state) versus a genuinely distinct new fact.

### Ground Truth Dataset
The benchmark uses 30 hand-labeled, representative fact pairs:
- **Duplicates (12 pairs):** Paraphrased facts on the same topic (e.g. *"User works as a Data Engineer"* vs *"The user is employed as a Data Engineer"*).
- **Easy Negatives (12 pairs):** Semantically and topically unrelated facts (e.g. *"User is 21 years old"* vs *"User runs a mango business"*).
- **Hard Negatives (6 pairs):** Facts on the exact same topic that differ on a critical detail (e.g. changed ages, changed companies, opposite sentiment/negation, changed project deadlines).

### Baseline System
- **Exact Match Baseline:** Normalized string comparison (`norm(a) == norm(b)`).

### Our System (3-Layer Deduplication Engine)
1. **Layer 1:** SHA-256 exact normalized hash match.
2. **Layer 2:** ChromaDB cosine similarity band ($s \ge 0.90 \to$ auto-duplicate, $s < 0.70 \to$ auto-distinct). Guarded by numerical/negation difference detection so that changing numbers or polarities are not mistakenly auto-merged.
3. **Layer 3:** Local LLM conflict resolution (`llama3.2:3b`) for the ambiguous middle band ($0.70 \le s < 0.90$) and hard negative differences.

---

## 5. Latest Measured Results (Actually Executed)

**Evaluation Date:** October 2026  
**Environment:** Python 3.12.10, ChromaDB 1.5.9, Windows 11  
**Execution Command:** `python src/benchmark.py --offline`  

| Metric | Baseline (Exact Match) | Our System (3-Layer Pipeline) | Improvement |
|---|---|---|---|
| **Precision** | 0.000 | **0.786** | +0.786 |
| **Recall** | 0.000 | **0.917** | +0.917 |
| **Accuracy** | 0.600 | **0.867** | +0.267 |
| **F1 Score** | 0.000 | **0.846** | +0.846 |

### Confusion Matrix Breakdown
- **Baseline Confusion:**
  - True Positives (TP): 0
  - False Positives (FP): 0
  - False Negatives (FN): 12 (failed to identify any paraphrased duplicates)
  - True Negatives (TN): 18
- **Our System Confusion:**
  - True Positives (TP): 11 (correctly identified 11 out of 12 paraphrased pairs)
  - False Positives (FP): 3
  - False Negatives (FN): 1
  - True Negatives (TN): 15 (correctly rejected 15 negative pairs)

### Output Artifacts
- Machine-readable metrics: `benchmark_results.json`
- Visualization chart: `benchmark_results.png`

---

## 6. Academic Analysis & Engineering Trade-offs

1. **Trade-off between Precision and Recall in Memory Systems:**
   In an AI memory framework, false merges (False Positives) are significantly more damaging than missing a duplicate (False Negatives). If the system incorrectly merges two distinct facts, user information is permanently corrupted or overwritten. Therefore:
   - Numerical and date mismatches bypass auto-duplication and require reasoning.
   - The decision parser conservatively defaults to `DISTINCT` on ambiguous or malformed model output.
2. **Reproducibility:**
   Running `python src/benchmark.py` will execute against live Ollama if available, or `--offline` for deterministic evaluation. All runs record the model configuration, thresholds, and environment metadata in the generated report.
