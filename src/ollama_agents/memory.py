"""Persistent two-tier memory for Ollama agents.

Short-term memory: in-memory message list (cleared per run unless stateful=True).
Long-term memory: SQLite database that survives across process restarts.

Database location: ~/.ollama_agents/<agent_name>.db
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

_DB_DIR = Path.home() / ".ollama_agents"


def _get_db_path(agent_name: str) -> Path:
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c if c.isalnum() else "_" for c in agent_name).lower()
    return _DB_DIR / f"{safe_name}.db"


class MemoryStore:
    """Persistent memory backend for a single agent.

    Usage::

        mem = MemoryStore("MarketScout")
        mem.save_fact("nvda_price", "138.20", tags="finance,nvda")
        facts = mem.recall_facts("NVDA price")
        mem.save_episode("Fetch NVDA data", "Found price 138.20 and 3 news items.")
        recent = mem.load_recent_episodes(n=3)
    """

    def __init__(self, agent_name: str = "AssistantAgent", vector_memory: "Optional[VectorMemory]" = None) -> None:
        self.agent_name = agent_name
        self.vector_memory = vector_memory  # optional semantic memory layer
        self._db_path = _get_db_path(agent_name)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._setup()
        logger.debug("MemoryStore for '%s' opened at %s", agent_name, self._db_path)

    # ------------------------------------------------------------------
    # Schema setup
    # ------------------------------------------------------------------

    def _setup(self) -> None:
        cur = self._conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS facts (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                key       TEXT NOT NULL,
                value     TEXT NOT NULL,
                tags      TEXT DEFAULT '',
                created   TEXT NOT NULL,
                updated   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS episodes (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                task      TEXT NOT NULL,
                summary   TEXT NOT NULL,
                created   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scratchpad (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                note      TEXT NOT NULL,
                created   TEXT NOT NULL
            );
        """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Facts  (key/value store with optional tags)
    # ------------------------------------------------------------------

    def save_fact(self, key: str, value: str, tags: str = "") -> None:
        """Upsert a named fact (overwrites existing key)."""
        now = _now()
        cur = self._conn.cursor()
        cur.execute("SELECT id FROM facts WHERE key = ?", (key,))
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE facts SET value=?, tags=?, updated=? WHERE key=?",
                (value, tags, now, key),
            )
        else:
            cur.execute(
                "INSERT INTO facts (key, value, tags, created, updated) VALUES (?,?,?,?,?)",
                (key, value, tags, now, now),
            )
        self._conn.commit()

    def recall_facts(self, query: str = "", limit: int = 10) -> List[Tuple[str, str]]:
        """Return (key, value) pairs whose key or tags contain *query*.

        If *query* is empty, returns the *limit* most-recently updated facts.
        """
        cur = self._conn.cursor()
        if query:
            pattern = f"%{query.lower()}%"
            cur.execute(
                """SELECT key, value FROM facts
                   WHERE lower(key) LIKE ? OR lower(tags) LIKE ? OR lower(value) LIKE ?
                   ORDER BY updated DESC LIMIT ?""",
                (pattern, pattern, pattern, limit),
            )
        else:
            cur.execute(
                "SELECT key, value FROM facts ORDER BY updated DESC LIMIT ?",
                (limit,),
            )
        return cur.fetchall()

    def delete_fact(self, key: str) -> None:
        """Remove a fact by key."""
        self._conn.execute("DELETE FROM facts WHERE key = ?", (key,))
        self._conn.commit()

    # ------------------------------------------------------------------
    # Episodes  (run summaries)
    # ------------------------------------------------------------------

    def save_episode(self, task: str, summary: str) -> None:
        """Append a completed task episode to long-term memory."""
        self._conn.execute(
            "INSERT INTO episodes (task, summary, created) VALUES (?,?,?)",
            (task, summary, _now()),
        )
        self._conn.commit()

    def load_recent_episodes(self, n: int = 3) -> List[Tuple[str, str, str]]:
        """Return the *n* most recent (task, summary, created) tuples."""
        cur = self._conn.cursor()
        cur.execute(
            "SELECT task, summary, created FROM episodes ORDER BY id DESC LIMIT ?",
            (n,),
        )
        return list(reversed(cur.fetchall()))

    # ------------------------------------------------------------------
    # Scratchpad  (free-form agent notes)
    # ------------------------------------------------------------------

    def write_note(self, note: str) -> None:
        """Append a free-form note to the scratchpad."""
        self._conn.execute(
            "INSERT INTO scratchpad (note, created) VALUES (?,?)",
            (note, _now()),
        )
        self._conn.commit()

    def read_notes(self, limit: int = 5) -> List[str]:
        """Return the *limit* most recent scratchpad notes."""
        cur = self._conn.cursor()
        cur.execute(
            "SELECT note FROM scratchpad ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [row[0] for row in reversed(cur.fetchall())]

    # ------------------------------------------------------------------
    # Helpers for system-prompt injection
    # ------------------------------------------------------------------

    def build_memory_context(self, query: str = "") -> str:
        """Build a compact memory block to inject into the agent's system prompt."""
        lines: List[str] = []

        episodes = self.load_recent_episodes(n=3)
        if episodes:
            lines.append("## Recent Task History")
            for task, summary, created in episodes:
                lines.append(f"- [{created[:10]}] {task}: {summary}")

        facts = self.recall_facts(query=query, limit=8)
        if facts:
            lines.append("## Remembered Facts")
            for key, value in facts:
                lines.append(f"- {key}: {value}")

        notes = self.read_notes(limit=3)
        if notes:
            lines.append("## Scratchpad Notes")
            for note in notes:
                lines.append(f"- {note}")

        # Semantic vector memory (if attached)
        if self.vector_memory and self.vector_memory.available and query:
            sem_ctx = self.vector_memory.build_context(query)
            if sem_ctx:
                lines.append(sem_ctx)

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def get_reflections(self, limit: int = 10) -> List[dict]:
        """Return formatted reflection notes for display in CLI and Web Dashboard."""
        notes = self.read_notes(limit=limit)
        return [{"key": f"Reflection #{i+1}", "content": note} for i, note in enumerate(notes)]

    def close(self) -> None:
        self._conn.close()

    def __repr__(self) -> str:
        return f"MemoryStore(agent={self.agent_name!r}, db={self._db_path})"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
