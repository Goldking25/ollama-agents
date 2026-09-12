"""Task Checkpointing — save and restore agent state across process restarts.

Every tool call during a run is checkpointed to disk. If the process crashes,
the next call to Agent.run() with the same task_id resumes from the last saved state.

Checkpoint location: ~/.ollama_agents/checkpoints/<task_id>.json
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CHECKPOINT_DIR = Path.home() / ".ollama_agents" / "checkpoints"


class CheckpointState:
    """Snapshot of an agent's mid-run state.

    Attributes:
        task_id:         Unique identifier for this task run.
        task:            The original goal/prompt.
        agent_name:      Name of the agent being checkpointed.
        turn:            The turn number at the time of the checkpoint.
        history:         Full conversation history up to this point.
        completed_steps: Steps confirmed completed so far.
        remaining_steps: Steps still to be executed.
        tool_calls_made: Log of all tool names called so far.
        errors:          Log of tool errors encountered.
        timestamp:       ISO-8601 UTC timestamp of last save.
    """

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

    Usage::

        mgr = CheckpointManager()

        # Save state after each tool call
        mgr.save(state)

        # On next run: check for existing checkpoint
        state = mgr.load("my-task-id")
        if state:
            print(f"Resuming from turn {state.turn}")

        # Clean up on success
        mgr.delete("my-task-id")

        # List all in-progress tasks
        for cp in mgr.list_checkpoints():
            print(cp["task_id"], cp["timestamp"])
    """

    def __init__(self) -> None:
        _CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    def _path(self, task_id: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in task_id)
        return _CHECKPOINT_DIR / f"{safe}.json"

    def save(self, state: CheckpointState) -> None:
        """Persist *state* to disk. Overwrites any previous checkpoint for the same task_id."""
        state.timestamp = _now()
        path = self._path(state.task_id)
        try:
            path.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
            logger.debug("Checkpoint saved: %s (turn %d)", state.task_id, state.turn)
        except Exception as e:
            logger.warning("Failed to save checkpoint '%s': %s", state.task_id, e)

    def load(self, task_id: str) -> Optional[CheckpointState]:
        """Load the checkpoint for *task_id*, or return None if it doesn't exist."""
        path = self._path(task_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            state = CheckpointState.from_dict(data)
            logger.info(
                "Checkpoint loaded: '%s' — resuming from turn %d (completed: %s)",
                task_id, state.turn, state.completed_steps,
            )
            return state
        except Exception as e:
            logger.warning("Failed to load checkpoint '%s': %s — starting fresh.", task_id, e)
            return None

    def delete(self, task_id: str) -> None:
        """Remove the checkpoint file for *task_id* (call on successful completion)."""
        path = self._path(task_id)
        if path.exists():
            path.unlink()
            logger.info("Checkpoint deleted: '%s' (task completed successfully)", task_id)

    def exists(self, task_id: str) -> bool:
        """Return True if a checkpoint exists for *task_id*."""
        return self._path(task_id).exists()

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        """Return a summary list of all saved checkpoints (in-progress tasks)."""
        summaries = []
        for path in sorted(_CHECKPOINT_DIR.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                summaries.append({
                    "task_id": data.get("task_id", path.stem),
                    "agent_name": data.get("agent_name", "?"),
                    "turn": data.get("turn", 0),
                    "timestamp": data.get("timestamp", "?"),
                    "task_preview": data.get("task", "")[:80],
                    "completed_steps": len(data.get("completed_steps", [])),
                    "remaining_steps": len(data.get("remaining_steps", [])),
                })
            except Exception:
                pass
        return summaries


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
