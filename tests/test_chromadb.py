"""
ChromaDB vector store verification test.
"""

import chromadb


def test_chromadb_embedding_and_retrieval():
    """Verifies that Chroma can create an in-memory collection, add documents, and query them."""
    client = chromadb.Client()
    collection = client.create_collection(
        name="test_verification",
        metadata={"hnsw:space": "cosine"},
    )

    collection.add(
        documents=[
            "User's name is Ubadah",
            "The user is called Ubadah",
            "User likes volleyball",
        ],
        ids=["1", "2", "3"],
    )

    result = collection.query(query_texts=["User's name is Ubadah"], n_results=3)

    assert result["ids"] and len(result["ids"][0]) == 3
    # Exact match document should be the first result with distance ~0
    assert result["ids"][0][0] == "1"
    assert result["documents"][0][0] == "User's name is Ubadah"
