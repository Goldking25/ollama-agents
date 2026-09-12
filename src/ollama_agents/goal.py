"""Goal Registry — persistent, multi-session goal management for long-horizon tasks.

A Goal is a high-level intent that may take multiple sessions (hours/days) to complete.
Each goal has an ordered list of GoalTasks. The agent works through one task per session.

Storage: ~/.ollama_agents/goals/<goal_id>.json
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

_GOAL_DIR = Path.home() / ".ollama_agents" / "goals"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─── Data models ──────────────────────────────────────────────────────────────

@dataclass
class GoalTask:
    """A single executable unit within a Goal.

    Attributes:
        id:          Unique task identifier within the goal.
        description: What the agent needs to accomplish in this task.
        status:      One of 'pending', 'in_progress', 'completed', 'failed'.
        output:      The agent's output from this task (stored for future context).
        created:     ISO timestamp when the task was created.
        updated:     ISO timestamp of last status change.
        session:     Which session number completed this task.
    """
    id: str
    description: str
    status: str = "pending"
    output: str = ""
    created: str = field(default_factory=_now)
    updated: str = field(default_factory=_now)
    session: int = 0

    @property
    def is_done(self) -> bool:
        return self.status == "completed"

    @property
    def is_failed(self) -> bool:
        return self.status == "failed"


@dataclass
class Goal:
    """A long-horizon task that persists across multiple sessions.

    Attributes:
        id:            Unique goal identifier.
        description:   The high-level goal description.
        agent_name:    Name of the agent responsible for this goal.
        tasks:         Ordered list of GoalTask objects.
        status:        One of 'active', 'completed', 'failed', 'paused'.
        session_count: Number of sessions this goal has been worked on.
        created:       ISO timestamp of creation.
        updated:       ISO timestamp of last update.
        notes:         Free-form notes (used by agent to leave context for next session).
    """
    id: str
    description: str
    agent_name: str
    tasks: List[GoalTask] = field(default_factory=list)
    status: str = "active"
    session_count: int = 0
    created: str = field(default_factory=_now)
    updated: str = field(default_factory=_now)
    notes: str = ""

    @property
    def progress_pct(self) -> float:
        if not self.tasks:
            return 0.0
        done = sum(1 for t in self.tasks if t.is_done)
        return done / len(self.tasks) * 100

    @property
    def completed_tasks(self) -> List[GoalTask]:
        return [t for t in self.tasks if t.is_done]

    @property
    def pending_tasks(self) -> List[GoalTask]:
        return [t for t in self.tasks if t.status == "pending"]

    @property
    def next_task(self) -> Optional[GoalTask]:
        """Return the next pending or in-progress task."""
        for t in self.tasks:
            if t.status in ("pending", "in_progress"):
                return t
        return None

    def summary(self) -> str:
        """Build a compact multi-line progress summary."""
        lines = [
            f"Goal: {self.description}",
            f"Status: {self.status}  |  Progress: {self.progress_pct:.0f}%  "
            f"({len(self.completed_tasks)}/{len(self.tasks)} tasks)  "
            f"|  Sessions: {self.session_count}",
        ]
        for i, task in enumerate(self.tasks, 1):
            icon = {"completed": "[x]", "in_progress": "[>]",
                    "failed": "[!]", "pending": "[ ]"}.get(task.status, "[ ]")
            lines.append(f"  {icon} Task {i}: {task.description}")
        if self.notes:
            lines.append(f"Notes: {self.notes}")
        return "\n".join(lines)

    def context_for_next_session(self) -> str:
        """Build a context block injected into the agent's prompt at session start."""
        lines = [
            f"## Long-Horizon Goal Context (Session {self.session_count + 1})",
            f"Goal: {self.description}",
            f"Progress: {self.progress_pct:.0f}% ({len(self.completed_tasks)}/{len(self.tasks)} tasks done)",
            "",
        ]
        if self.completed_tasks:
            lines.append("### Already completed (DO NOT redo these):")
            for t in self.completed_tasks:
                lines.append(f"- {t.description}")
                if t.output:
                    lines.append(f"  Result: {t.output[:200]}")

        next_t = self.next_task
        if next_t:
            lines.append(f"\n### Your task for THIS session:")
            lines.append(f"  {next_t.description}")
            lines.append(
                "\nFocus ONLY on this task. When done, emit 'Final Answer:' with your result."
            )

        if self.notes:
            lines.append(f"\n### Notes from previous session:\n{self.notes}")

        return "\n".join(lines)


# ─── Registry ─────────────────────────────────────────────────────────────────

class GoalRegistry:
    """Manages creation, persistence, and retrieval of Goals.

    Usage::

        registry = GoalRegistry()

        goal = registry.create(
            goal_id="indbank-research",
            description="Research IndBank stock for investment decision",
            task_descriptions=["Fetch price data", "Search news", "Analyse"],
            agent_name="MarketScout",
        )

        task = registry.get_next_task("indbank-research")
        registry.complete_task("indbank-research", task.id, output="Price: ₹210")

        for g in registry.list_active():
            print(g.summary())
    """

    def __init__(self) -> None:
        _GOAL_DIR.mkdir(parents=True, exist_ok=True)

    def _path(self, goal_id: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in goal_id)
        return _GOAL_DIR / f"{safe}.json"

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(
        self,
        description: str,
        task_descriptions: List[str],
        agent_name: str,
        goal_id: Optional[str] = None,
    ) -> Goal:
        """Create and persist a new Goal with the given tasks.

        Args:
            description:       High-level goal description.
            task_descriptions: Ordered list of task descriptions.
            agent_name:        Agent that will work this goal.
            goal_id:           Optional custom ID. Auto-generated if not provided.

        Returns:
            The created :class:`Goal` object.
        """
        gid = goal_id or f"goal-{uuid.uuid4().hex[:8]}"
        tasks = [
            GoalTask(id=f"task-{i+1:03d}", description=desc)
            for i, desc in enumerate(task_descriptions)
        ]
        goal = Goal(id=gid, description=description, agent_name=agent_name, tasks=tasks)
        self._save(goal)
        logger.info("Goal created: '%s' with %d tasks.", gid, len(tasks))
        return goal

    def load(self, goal_id: str) -> Optional[Goal]:
        """Load a Goal by ID. Returns None if not found."""
        path = self._path(goal_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            tasks = [GoalTask(**t) for t in data.pop("tasks", [])]
            goal = Goal(**data, tasks=tasks)
            return goal
        except Exception as e:
            logger.error("Failed to load goal '%s': %s", goal_id, e)
            return None

    def exists(self, goal_id: str) -> bool:
        return self._path(goal_id).exists()

    def _save(self, goal: Goal) -> None:
        goal.updated = _now()
        data = asdict(goal)
        self._path(goal.id).write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.debug("Goal saved: '%s'", goal.id)

    # ------------------------------------------------------------------
    # Task management
    # ------------------------------------------------------------------

    def get_next_task(self, goal_id: str) -> Optional[GoalTask]:
        """Return the next pending or in-progress task for the goal."""
        goal = self.load(goal_id)
        return goal.next_task if goal else None

    def start_task(self, goal_id: str, task_id: str, session: int) -> None:
        """Mark a task as in_progress."""
        goal = self.load(goal_id)
        if not goal:
            return
        for task in goal.tasks:
            if task.id == task_id:
                task.status = "in_progress"
                task.session = session
                task.updated = _now()
                break
        self._save(goal)

    def complete_task(self, goal_id: str, task_id: str, output: str = "") -> None:
        """Mark a task as completed and store its output."""
        goal = self.load(goal_id)
        if not goal:
            return
        for task in goal.tasks:
            if task.id == task_id:
                task.status = "completed"
                task.output = output[:600]
                task.updated = _now()
                break

        # Auto-complete the goal if all tasks done
        if all(t.is_done for t in goal.tasks):
            goal.status = "completed"
            logger.info("Goal '%s' fully completed!", goal_id)

        self._save(goal)

    def fail_task(self, goal_id: str, task_id: str, reason: str = "") -> None:
        """Mark a task as failed."""
        goal = self.load(goal_id)
        if not goal:
            return
        for task in goal.tasks:
            if task.id == task_id:
                task.status = "failed"
                task.output = reason[:300]
                task.updated = _now()
                break
        self._save(goal)

    def save_notes(self, goal_id: str, notes: str) -> None:
        """Save free-form notes for the next session to read."""
        goal = self.load(goal_id)
        if goal:
            goal.notes = notes[:500]
            self._save(goal)

    def increment_session(self, goal_id: str) -> int:
        """Increment session counter. Returns new session number."""
        goal = self.load(goal_id)
        if not goal:
            return 1
        goal.session_count += 1
        self._save(goal)
        return goal.session_count

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_all(self) -> List[Goal]:
        """Return all goals sorted by updated timestamp."""
        goals = []
        for path in sorted(_GOAL_DIR.glob("*.json"), reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                tasks = [GoalTask(**t) for t in data.pop("tasks", [])]
                goals.append(Goal(**data, tasks=tasks))
            except Exception:
                pass
        return goals

    def list_active(self) -> List[Goal]:
        """Return only goals with status 'active'."""
        return [g for g in self.list_all() if g.status == "active"]

    # ── Convenient Aliases ─────────────────────────────────────────────
    def list_goals(self) -> List[Goal]:
        """Alias for list_all()."""
        return self.list_all()

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        """Alias for load()."""
        return self.load(goal_id)

    def create_goal(self, prompt: str, model: str = "deepseek-r1:8b") -> Goal:
        """Convenience method to decompose prompt into tasks and create a Goal."""
        from ollama_agents.planner import Planner
        planner = Planner(model=model)
        tasks = planner.hierarchical_decompose(prompt)
        task_descriptions = [t.get("description", str(t)) if isinstance(t, dict) else str(t) for t in tasks]
        return self.create(
            description=prompt,
            task_descriptions=task_descriptions if task_descriptions else [prompt],
            agent_name="AutonomousAgent",
        )
