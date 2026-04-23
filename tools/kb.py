from __future__ import annotations
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from langchain_core.tools import tool

_ef = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
_client = chromadb.PersistentClient(path="data/chroma")
_collection = _client.get_or_create_collection("finance_kb", embedding_function=_ef)

@tool("finance_kb")
def lookup_knowledge_base(term: str, top_k: int = 3) -> list[dict]:
    """Look up definitions and explanations of financial terms, ratios, or concepts from the internal finance knowledge base.

    Args:
        term: Financial term or concept to look up (e.g., "EBITDA", "working capital", "yield curve").
        top_k: Number of matching results to return. Default is 3.
    """
    results = _collection.query(query_texts=[term], n_results=top_k)
    return [
        {"term": m["term"], "definition": m.get("definition", d), "distance": dist}
        for m, d, dist in zip(
            results["metadatas"][0],
            results["documents"][0],
            results["distances"][0],
        )
        if "term" in m
    ]
