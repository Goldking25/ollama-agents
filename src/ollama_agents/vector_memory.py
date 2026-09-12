"""Semantic vector memory using ChromaDB and Ollama embeddings.

Stores text as embeddings and retrieves by semantic similarity — finding
relevant memories even when the query uses different words than what was stored.

Embedding model: nomic-embed-text (pull with: ollama pull nomic-embed-text)
Database location: ~/.ollama_agents/vectors/<agent_name>/
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

_VECTOR_DIR = Path.home() / ".ollama_agents" / "vectors"
_EMBED_MODEL = "nomic-embed-text"


class VectorMemory:
    """Semantic memory store backed by ChromaDB + Ollama embeddings.

    Args:
        agent_name: Scopes this memory to a specific agent.
        embed_model: Ollama embedding model to use (default: nomic-embed-text).
        host: Optional Ollama host URL.
        top_k: Number of results returned by recall() (default 4).
    """

    def __init__(
        self,
        agent_name: str,
        embed_model: str = _EMBED_MODEL,
        host: Optional[str] = None,
        top_k: int = 4,
    ) -> None:
        self.agent_name = agent_name
        self.embed_model = embed_model
        self.top_k = top_k

        try:
            import chromadb
            import ollama as _ollama

            self._ollama = _ollama.Client(host=host)

            db_path = _VECTOR_DIR / agent_name
            db_path.mkdir(parents=True, exist_ok=True)

            self._client = chromadb.PersistentClient(path=str(db_path))
            safe_name = "".join(c if c.isalnum() else "_" for c in agent_name).lower()
            self._collection = self._client.get_or_create_collection(
                name=f"{safe_name}_memory",
                metadata={"hnsw:space": "cosine"},
            )
            self._available = True
            logger.debug("VectorMemory ready for agent '%s' at %s", agent_name, db_path)

        except ImportError:
            logger.warning(
                "chromadb not installed — VectorMemory disabled. "
                "Install with: pip install chromadb"
            )
            self._available = False
        except Exception as e:
            logger.warning("VectorMemory init failed: %s — falling back to disabled.", e)
            self._available = False

    @property
    def available(self) -> bool:
        """True if ChromaDB and the embedding model are operational."""
        return self._available

    def _embed(self, text: str) -> List[float]:
        """Generate an embedding vector for *text* using Ollama."""
        response = self._ollama.embeddings(model=self.embed_model, prompt=text)
        if hasattr(response, "embedding"):
            return response.embedding
        return response.get("embedding", [])

    def store(self, text: str, tags: str = "", doc_id: Optional[str] = None) -> None:
        """Store *text* as an embedding in the vector database.

        Args:
            text: The text to embed and store.
            tags: Optional comma-separated tags for metadata filtering.
            doc_id: Optional unique ID. Auto-generated if not provided.
        """
        if not self._available:
            return
        try:
            embedding = self._embed(text)
            self._collection.add(
                ids=[doc_id or str(uuid.uuid4())],
                embeddings=[embedding],
                documents=[text],
                metadatas=[{"tags": tags, "agent": self.agent_name}],
            )
            logger.debug("VectorMemory stored: %s...", text[:60])
        except Exception as e:
            logger.warning("VectorMemory.store failed: %s", e)

    def recall(self, query: str, n_results: Optional[int] = None) -> List[str]:
        """Return the *n* most semantically similar stored texts to *query*.

        Args:
            query: Natural language query to find relevant memories.
            n_results: Number of results (defaults to self.top_k).

        Returns:
            List of matching text strings, most relevant first.
        """
        if not self._available:
            return []
        try:
            k = n_results or self.top_k
            embedding = self._embed(query)
            results = self._collection.query(
                query_embeddings=[embedding],
                n_results=min(k, self._collection.count() or 1),
            )
            docs = results.get("documents", [[]])[0]
            logger.debug("VectorMemory recalled %d results for: %s", len(docs), query[:60])
            return docs
        except Exception as e:
            logger.warning("VectorMemory.recall failed: %s", e)
            return []

    def count(self) -> int:
        """Return the total number of stored embeddings."""
        if not self._available:
            return 0
        try:
            return self._collection.count()
        except Exception:
            return 0

    def build_context(self, query: str) -> str:
        """Build a compact memory block from semantically relevant recalls."""
        memories = self.recall(query)
        if not memories:
            return ""
        lines = ["## Semantic Memory (most relevant past experiences)"]
        for mem in memories:
            lines.append(f"- {mem}")
        return "\n".join(lines)
