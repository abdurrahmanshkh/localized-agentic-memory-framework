"""
Vector store interface for ChromaDB long-term semantic memory.

Provides lazy initialization, persistent/in-memory modes, index synchronization,
and semantic similarity queries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import chromadb
except ImportError:
    chromadb = None

try:
    from . import config
except ImportError:
    import config


class VectorStore:
    """Encapsulates ChromaDB collection operations with safe error handling."""

    def __init__(
        self,
        chroma_dir: str | Path | None = None,
        in_memory: bool = False,
        collection_name: str = "main",
    ):
        self.in_memory = in_memory
        self.collection_name = collection_name
        if in_memory:
            self.chroma_dir = None
        else:
            self.chroma_dir = Path(chroma_dir) if chroma_dir else config.get_chroma_dir()
        self._client = None
        self._collection = None

    def _get_client(self) -> Any:
        if chromadb is None:
            raise RuntimeError("The 'chromadb' package is not installed.")
        if self._client is None:
            if self.in_memory:
                self._client = chromadb.Client()
            else:
                self.chroma_dir.mkdir(parents=True, exist_ok=True)
                self._client = chromadb.PersistentClient(path=str(self.chroma_dir))
        return self._client

    def get_collection(self) -> Any:
        """Lazily obtains or creates the Chroma collection."""
        if self._collection is None:
            client = self._get_client()
            self._collection = client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def count(self) -> int:
        """Returns total number of vector records in the collection."""
        try:
            return self.get_collection().count()
        except Exception:
            return 0

    def query_similar(
        self,
        query_text: str,
        n_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Queries collection by cosine similarity.

        Returns a list of dicts with keys: 'id', 'text', 'distance', 'similarity', 'metadata'.
        Returns [] safely if collection is empty.
        """
        col = self.get_collection()
        total_items = self.count()
        if total_items == 0:
            return []

        actual_n = min(n_results, total_items)
        try:
            results = col.query(
                query_texts=[query_text],
                n_results=actual_n,
            )
        except Exception:
            return []

        matches = []
        if not results or not results.get("ids") or not results["ids"][0]:
            return matches

        ids = results["ids"][0]
        docs = results.get("documents", [[]])[0]
        dists = results.get("distances", [[]])[0]
        metas = results.get("metadatas", [[]])[0] if results.get("metadatas") else [{}] * len(ids)

        for i in range(len(ids)):
            dist = dists[i] if i < len(dists) else 1.0
            # Cosine distance to cosine similarity: sim = 1.0 - distance
            # For HNSW cosine, distance is 1 - cos(u, v)
            sim = max(0.0, min(1.0, 1.0 - dist))
            matches.append({
                "id": str(ids[i]),
                "text": str(docs[i]) if i < len(docs) else "",
                "distance": float(dist),
                "similarity": float(sim),
                "metadata": metas[i] if i < len(metas) and metas[i] is not None else {},
            })

        return matches

    def check_similarity(self, new_fact_text: str) -> tuple[float | None, str | None, str | None]:
        """Returns (similarity, matched_text, matched_id) for the closest fact, or (None, None, None)."""
        matches = self.query_similar(new_fact_text, n_results=1)
        if not matches:
            return None, None, None
        top = matches[0]
        return top["similarity"], top["text"], top["id"]

    def add_fact(
        self,
        fact_id: str | int,
        fact_text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Adds or updates a fact vector in Chroma."""
        col = self.get_collection()
        str_id = str(fact_id)
        meta = dict(metadata) if metadata else {"source": "local"}
        col.upsert(
            documents=[fact_text],
            ids=[str_id],
            metadatas=[meta],
        )

    def delete_fact(self, fact_id: str | int) -> None:
        """Removes a fact vector by ID if present."""
        col = self.get_collection()
        str_id = str(fact_id)
        try:
            col.delete(ids=[str_id])
        except Exception:
            pass

    def clear_all(self) -> None:
        """Clears all records in the collection."""
        client = self._get_client()
        try:
            client.delete_collection(name=self.collection_name)
        except Exception:
            pass
        self._collection = None

    def rebuild_from_records(self, records: list[dict[str, Any]]) -> int:
        """Rebuilds the entire collection idempotently from canonical SQLite records."""
        self.clear_all()
        col = self.get_collection()
        if not records:
            return 0

        ids = [str(r["id"]) for r in records]
        documents = [str(r["fact_text"]) for r in records]
        metadatas = [
            {
                "source_session_id": str(r.get("source_session_id", "")),
                "category": str(r.get("category", "general")),
                "consolidated_date": str(r.get("consolidated_date", "")),
            }
            for r in records
        ]

        batch_size = 100
        total_added = 0
        for i in range(0, len(ids), batch_size):
            b_ids = ids[i : i + batch_size]
            b_docs = documents[i : i + batch_size]
            b_metas = metadatas[i : i + batch_size]
            col.add(documents=b_docs, ids=b_ids, metadatas=b_metas)
            total_added += len(b_ids)

        return total_added
