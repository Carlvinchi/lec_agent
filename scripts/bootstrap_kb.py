"""One-shot: loads curated financial concepts into ChromaDB."""
import json, chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

ef = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
client = chromadb.PersistentClient(path="data/chroma")
col = client.get_or_create_collection("finance_kb", embedding_function=ef)

with open("data/kb_seed.json") as f:
    entries = json.load(f)   # list of {"term": str, "definition": str}

texts = []
metadatas = []

for e in entries["entries"]:
    text_to_embed = f"term: {e['term']} full_name: {e['full_name']} definition: {e['definition']} formula: {e['formula']} interpretation: {e['interpretation']}"
    texts.append(text_to_embed)
    metadatas.append(e)

col.upsert(
    ids=[e['term'] for e in entries["entries"]],
    documents=texts,
    metadatas=metadatas,
)
print(f"Loaded {len(texts)} concepts into ChromaDB.")
