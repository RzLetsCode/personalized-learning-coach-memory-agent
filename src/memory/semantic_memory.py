"""
Long-term Semantic Memory for the Enterprise AI Learning Coach.

Upgraded from FAISS (local, non-persistent) to Pinecone (cloud, persistent)
with per-user metadata filtering for strict data isolation.

Fallback: If Pinecone env vars are missing, falls back to FAISS for local dev.
"""

import os
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.schema import Document
from langchain_openai import AzureOpenAIEmbeddings
 
from dotenv import load_dotenv
load_dotenv()   
 

# ---------------------------------------------------------------------------
# Backend selection: Pinecone (prod) or FAISS (local dev fallback)
# ---------------------------------------------------------------------------
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "learning-coach-index")
USE_PINECONE = bool(PINECONE_API_KEY)

if USE_PINECONE:
    try:
        from langchain_pinecone import PineconeVectorStore
        PINECONE_AVAILABLE = True
    except ImportError:
        PINECONE_AVAILABLE = False
        USE_PINECONE = False
else:
    PINECONE_AVAILABLE = False

# if not USE_PINECONE:
#     try:
#         from langchain_community.vectorstores import FAISS
#         FAISS_AVAILABLE = True
#     except ImportError:
#         FAISS_AVAILABLE = False

# ---------------------------------------------------------------------------
# Shared resources (Azure OpenAI + text splitter)
# ---------------------------------------------------------------------------

EMBED_MODEL = os.environ.get("AZURE_OPENAI_EMBEDDINGS_MODEL")
if not EMBED_MODEL:
    raise RuntimeError("AZURE_OPENAI_EMBEDDINGS_MODEL is not set")

_embeddings = AzureOpenAIEmbeddings(
    api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
    azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
    api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
    model=EMBED_MODEL,  # must be a non-empty string
)

_text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=150,
    length_function=len,
)
# FAISS fallback in-memory store (only used in local dev)
_faiss_store = None


# ---------------------------------------------------------------------------
# Pinecone helpers (production)
# ---------------------------------------------------------------------------
def _get_pinecone_store() -> "PineconeVectorStore":
    return PineconeVectorStore(
        index_name=PINECONE_INDEX_NAME,
        embedding=_embeddings,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def index_user_material(
    user_id: int,
    docs: List[str],
    source: str = "uploaded_file",
) -> int:
    """
    Chunk, embed and store study material for a specific user.
    Each chunk is tagged with user_id metadata for later filtering.

    Returns the number of chunks indexed.
    """
    global _faiss_store

    texts: List[str] = []
    metadatas: List[Dict] = []

    for doc_text in docs:
        chunks = _text_splitter.split_text(doc_text)
        for chunk in chunks:
            texts.append(chunk)
            metadatas.append({
                "user_id": str(user_id),
                "source": source,
                "indexed_at": datetime.utcnow().isoformat(),
                "chunk_id": str(uuid.uuid4()),
            })

    if not texts:
        return 0

    if USE_PINECONE and PINECONE_AVAILABLE:
        store = _get_pinecone_store()
        store.add_texts(texts=texts, metadatas=metadatas)
    elif FAISS_AVAILABLE:
        if _faiss_store is None:
            _faiss_store = FAISS.from_texts(texts, _embeddings, metadatas=metadatas)
        else:
            _faiss_store.add_texts(texts, metadatas=metadatas)

    return len(texts)


def search_user_material(
    user_id: int,
    query: str,
    k: int = 5,
) -> List[Document]:
    """
    Semantic search over the user's indexed materials.
    Uses metadata filtering to ensure strict per-user isolation.

    Returns up to k most relevant Document chunks.
    """
    global _faiss_store

    if USE_PINECONE and PINECONE_AVAILABLE:
        store = _get_pinecone_store()
        results = store.similarity_search(
            query,
            k=k,
            filter={"user_id": {"$eq": str(user_id)}},
        )
        return results

    elif FAISS_AVAILABLE and _faiss_store is not None:
        # FAISS doesn't support server-side filtering; filter post-retrieval
        raw = _faiss_store.similarity_search(query, k=k * 3)
        filtered = [
            doc for doc in raw
            if doc.metadata.get("user_id") == str(user_id)
        ]
        return filtered[:k]

    return []


def store_qa_memory(
    user_id: int,
    question: str,
    answer: str,
    topic: str = "general",
    tag: str = "neutral",
    confidence_score: float = 0.5,
) -> None:
    """
    Store a Q&A pair as a searchable memory chunk.
    Tagged with topic and performance metadata.
    """
    text = f"Q: {question}\nA: {answer}"
    metadata = {
        "user_id": str(user_id),
        "topic": topic,
        "tag": tag,
        "confidence_score": confidence_score,
        "source": "qa_memory",
        "indexed_at": datetime.utcnow().isoformat(),
        "chunk_id": str(uuid.uuid4()),
    }
    index_user_material(user_id, [text], source="qa_memory")


def search_qa_memories(
    user_id: int,
    query: str,
    k: int = 5,
    tag_filter: Optional[str] = None,
) -> List[Document]:
    """
    Search through past Q&A memories.
    Optionally filter by tag (neutral, misconception, mastered).
    """
    results = search_user_material(user_id, query, k=k * 2)
    if tag_filter:
        results = [
            doc for doc in results
            if doc.metadata.get("tag") == tag_filter
        ]
    return results[:k]


def get_context_for_query(
    user_id: int,
    query: str,
    k: int = 5,
) -> str:
    """
    Convenience wrapper: return a formatted context string from the top-k
    most relevant chunks for use in LLM prompt construction.
    """
    docs = search_user_material(user_id, query, k=k)
    if not docs:
        return "No relevant context found in your study materials."
    context_parts = []
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source", "material")
        context_parts.append(f"[{i}] ({source}):\n{doc.page_content}")
    return "\n\n".join(context_parts)
