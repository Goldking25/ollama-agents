"""Task Checkpointing — save and restore agent state across process restarts.

Every tool call during a run is checkpointed to disk. If the process crashes,
the next call to Agent.run() with the same task_id resumes from the last saved state.

Storage: ~/.ollama_agents/agent_state.db  (SQLite, WAL mode — shared with GoalRegistry)
Legacy JSON files in ~/.ollama_agents/checkpoints/ are auto-migrated on first access.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CHECKPOINT_DIR = Path.home() / ".ollama_agents" / "checkpoints"  # legacy, kept for migration


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_conn():
    """Reuse the module-level connection from goal.py (same DB, same WAL session)."""
    from ollama_agents.goal import _get_conn as _goal_get_conn, _ensure_schema
    conn = _goal_get_conn()
    # Ensure checkpoint table exists (idempotent)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS checkpoints (
            task_id         TEXT PRIMARY KEY,
            task            TEXT NOT NULL DEFAULT '',
            agent_name      TEXT NOT NULL DEFAULT '',
            turn            INTEGER NOT NULL DEFAULT 0,
            history_json    TEXT NOT NULL DEFAULT '[]',
            completed_steps TEXT NOT NULL DEFAULT '[]',
            remaining_steps TEXT NOT NULL DEFAULT '[]',
            tool_calls_made TEXT NOT NULL DEFAULT '[]',
            errors          TEXT NOT NULL DEFAULT '[]',
            timestamp       TEXT NOT NULL
        );
    """)
    conn.commit()
    return conn


class CheckpointState:
    """Snapshot of an agent's mid-run state."""

    def __init__(
        self,
        task_id: str,
        task: str,
        agent_name: str,
        turn: int = 0,
        history: Optional[List[Dict[str, Any]]] = None,
        completed_steps: Optional[List[str]] = None,
        remaining_steps: Optional[List[str]] = None,
        tool_calls_made: Optional[List[str]] = None,
        errors: Optional[List[str]] = None,
        timestamp: str = "",
    ) -> None:
        self.task_id = task_id
        self.task = task
        self.agent_name = agent_name
        self.turn = turn
        self.history: List[Dict[str, Any]] = history or []
        self.completed_steps: List[str] = completed_steps or []
        self.remaining_steps: List[str] = remaining_steps or []
        self.tool_calls_made: List[str] = tool_calls_made or []
        self.errors: List[str] = errors or []
        self.timestamp = timestamp or _now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task": self.task,
            "agent_name": self.agent_name,
            "turn": self.turn,
            "history": self.history,
            "completed_steps": self.completed_steps,
            "remaining_steps": self.remaining_steps,
            "tool_calls_made": self.tool_calls_made,
            "errors": self.errors,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CheckpointState":
        return cls(**{k: v for k, v in data.items() if k in cls.__init__.__code__.co_varnames})


class CheckpointManager:
    """Manages saving, loading, and deleting agent checkpoints.

    Checkpoints are stored in the shared ~/.ollama_agents/agent_state.db SQLite
    database with WAL mode enabled — no more per-file JSON writes that block
    concurrent readers.  The public API is identical to the old file-based version.

    Legacy JSON files in ~/.ollama_agents/checkpoints/ are migrated on first use.
    """

    def __init__(self) -> None:
        _get_conn()   # ensure table schema exists
        self._migrate_json_checkpoints()

    def _migrate_json_checkpoints(self) -> None:
        """One-time migration: import legacy JSON checkpoint files into SQLite."""
        if not _CHECKPOINT_DIR.exists():
            return
        conn = _get_conn()
        for path in _CHECKPOINT_DIR.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                task_id = data.get("task_id", path.stem)
                if conn.execute("SELECT 1 FROM checkpoints WHERE task_id=?", (task_id,)).fetchone():
                    continue
                conn.execute(
                    """INSERT OR IGNORE INTO checkpoints
                       (task_id, task, agent_name, turn, history_json, completed_steps,
                        remaining_steps, tool_calls_made, errors, timestamp)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        task_id,
                        data.get("task", ""),
                        data.get("agent_name", ""),
                        data.get("turn", 0),
                        json.dumps(data.get("history", [])),
                        json.dumps(data.get("completed_steps", [])),
                        json.dumps(data.get("remaining_steps", [])),
                        json.dumps(data.get("tool_calls_made", [])),
                        json.dumps(data.get("errors", [])),
                        data.get("timestamp", _now()),
                    ),
                )
                conn.commit()
                path.rename(path.with_suffix(".json.migrated"))
                logger.info("Migrated legacy checkpoint JSON → SQLite: '%s'", task_id)
            except Exception as e:
                logger.warning("Could not migrate checkpoint file %s: %s", path, e)

    def save(self, state: CheckpointState) -> None:
        """Persist *state* to SQLite. Overwrites any previous checkpoint for the same task_id."""
        state.timestamp = _now()
        conn = _get_conn()
        try:
            with conn:
                conn.execute(
                    """INSERT INTO checkpoints
                           (task_id, task, agent_name, turn, history_json, completed_steps,
                            remaining_steps, tool_calls_made, errors, timestamp)
                       VALUES (?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(task_id) DO UPDATE SET
                           task=excluded.task,
                           agent_name=excluded.agent_name,
                           turn=excluded.turn,
                           history_json=excluded.history_json,
                           completed_steps=excluded.completed_steps,
                           remaining_steps=excluded.remaining_steps,
                           tool_calls_made=excluded.tool_calls_made,
                           errors=excluded.errors,
                           timestamp=excluded.timestamp""",
                    (
                        state.task_id,
                        state.task,
                        state.agent_name,
                        state.turn,
                        json.dumps(state.history),
                        json.dumps(state.completed_steps),
                        json.dumps(state.remaining_steps),
                        json.dumps(state.tool_calls_made),
                        json.dumps(state.errors),
                        state.timestamp,
                    ),
                )
            logger.debug("Checkpoint saved to SQLite: %s (turn %d)", state.task_id, state.turn)
        except Exception as e:
            logger.warning("Failed to save checkpoint '%s': %s", state.task_id, e)

    def load(self, task_id: str) -> Optional[CheckpointState]:
        """Load the checkpoint for *task_id*, or return None if it doesn't exist."""
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM checkpoints WHERE task_id=?", (task_id,)
            ).fetchone()
            if not row:
                return None
            state = CheckpointState(
                task_id=row["task_id"],
                task=row["task"],
                agent_name=row["agent_name"],
                turn=row["turn"],
                history=json.loads(row["history_json"]),
                completed_steps=json.loads(row["completed_steps"]),
                remaining_steps=json.loads(row["remaining_steps"]),
                tool_calls_made=json.loads(row["tool_calls_made"]),
                errors=json.loads(row["errors"]),
                timestamp=row["timestamp"],
            )
            logger.info(
                "Checkpoint loaded: '%s' — resuming from turn %d (completed: %s)",
                task_id, state.turn, state.completed_steps,
            )
            return state
        except Exception as e:
            logger.warning("Failed to load checkpoint '%s': %s — starting fresh.", task_id, e)
            return None

    def delete(self, task_id: str) -> None:
        """Remove the checkpoint for *task_id* (call on successful completion)."""
        conn = _get_conn()
        with conn:
            conn.execute("DELETE FROM checkpoints WHERE task_id=?", (task_id,))
        logger.info("Checkpoint deleted: '%s' (task completed successfully)", task_id)

    def exists(self, task_id: str) -> bool:
        conn = _get_conn()
        return bool(conn.execute("SELECT 1 FROM checkpoints WHERE task_id=?", (task_id,)).fetchone())

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        """Return a summary list of all saved checkpoints (in-progress tasks)."""
        conn = _get_conn()
        rows = conn.execute(
            "SELECT task_id, agent_name, turn, timestamp, task, completed_steps, remaining_steps "
            "FROM checkpoints ORDER BY timestamp ASC"
        ).fetchall()
        summaries = []
        for row in rows:
            try:
                completed = json.loads(row["completed_steps"])
                remaining = json.loads(row["remaining_steps"])
                summaries.append({
                    "task_id": row["task_id"],
                    "agent_name": row["agent_name"],
                    "turn": row["turn"],
                    "timestamp": row["timestamp"],
                    "task_preview": (row["task"] or "")[:80],
                    "completed_steps": len(completed),
                    "remaining_steps": len(remaining),
                })
            except Exception:
                pass
        return summaries
