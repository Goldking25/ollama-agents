"""RAG Vector Embeddings Engine for Ollama Agents.

Provides local semantic embedding search over documents and codebase files
using Ollama's native embedding endpoint (e.g. nomic-embed-text, bge-m3, all-minilm).
Uses cosine similarity over normalized float vector arrays stored in SQLite.
"""

import math
import json
import sqlite3
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import ollama

logger = logging.getLogger(__name__)

_DB_DIR = Path.home() / ".ollama_agents" / "rag"

def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two float vectors."""
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)

class VectorRAGStore:
    """Persistent RAG Vector Store using SQLite and local Ollama embedding models."""

    def __init__(
        self,
        collection_name: str = "default_knowledge",
        embedding_model: str = "nomic-embed-text",
        host: Optional[str] = None
    ) -> None:
        self.collection_name = collection_name
        self.embedding_model = embedding_model
        self.client = ollama.Client(host=host)
        
        _DB_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c if c.isalnum() else "_" for c in collection_name).lower()
        self._db_path = _DB_DIR / f"{safe_name}.db"
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._setup()

    def _setup(self) -> None:
        cur = self._conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source      TEXT NOT NULL,
                content     TEXT NOT NULL,
                embedding   TEXT NOT NULL,
                metadata    TEXT DEFAULT '{}',
                created_at  TEXT NOT NULL
            );
        """)
        self._conn.commit()

    def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding vector using local Ollama model."""
        try:
            resp = self.client.embeddings(model=self.embedding_model, prompt=text)
            if hasattr(resp, "embedding"):
                return resp.embedding
            if isinstance(resp, dict) and "embedding" in resp:
                return resp["embedding"]
            return None
        except Exception as e:
            # Fallback to general model if specific embedding model is not yet pulled
            try:
                resp = self.client.embeddings(model="deepseek-r1:8b", prompt=text)
                if hasattr(resp, "embedding"):
                    return resp.embedding
                if isinstance(resp, dict) and "embedding" in resp:
                    return resp["embedding"]
            except Exception:
                pass
            logger.warning("Failed to generate embedding via Ollama (%s): %s", self.embedding_model, e)
            return None

    def add_document(self, content: str, source: str = "user", metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Embed and store a text document snippet into vector memory."""
        if not content.strip():
            return False

        embedding = self._generate_embedding(content)
        if not embedding:
            logger.warning("Could not generate vector embedding for document.")
            return False

        meta_json = json.dumps(metadata or {})
        emb_json = json.dumps(embedding)
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()

        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO documents (source, content, embedding, metadata, created_at) VALUES (?,?,?,?,?)",
            (source, content, emb_json, meta_json, now)
        )
        self._conn.commit()
        return True

    def query(self, query_text: str, top_k: int = 4) -> List[Dict[str, Any]]:
        """Perform semantic search using vector similarity."""
        query_vec = self._generate_embedding(query_text)
        if not query_vec:
            return []

        cur = self._conn.cursor()
        cur.execute("SELECT id, source, content, embedding, metadata FROM documents")
        rows = cur.fetchall()

        results = []
        for doc_id, source, content, emb_str, meta_str in rows:
            try:
                emb = json.loads(emb_str)
                sim = _cosine_similarity(query_vec, emb)
                results.append({
                    "id": doc_id,
                    "source": source,
                    "content": content,
                    "score": sim,
                    "metadata": json.loads(meta_str)
                })
            except Exception:
                continue

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def build_rag_context(self, query_text: str, top_k: int = 3) -> str:
        """Format top relevant RAG document matches into a prompt context block."""
        matches = self.query(query_text, top_k=top_k)
        if not matches:
            return ""

        lines = ["## 🔍 Semantic RAG Context (Retrieved Knowledge)"]
        for idx, m in enumerate(matches, 1):
            if m["score"] > 0.3:  # minimum relevance threshold
                lines.append(f"{idx}. [{m['source']}] (Relevance: {m['score']:.2f})\n   {m['content'][:400]}")
        
        return "\n".join(lines) if len(lines) > 1 else ""
