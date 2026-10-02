"""Goal Registry — persistent, multi-session goal management for long-horizon tasks.

A Goal is a high-level intent that may take multiple sessions (hours/days) to complete.
Each goal has an ordered list of GoalTasks. The agent works through one task per session.

Storage: ~/.ollama_agents/agent_state.db  (SQLite, WAL mode)
Legacy JSON files in ~/.ollama_agents/goals/ are automatically migrated on first access.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

_STATE_DIR = Path.home() / ".ollama_agents"
_GOAL_DIR = _STATE_DIR / "goals"          # kept for legacy JSON migration
_DB_PATH = _STATE_DIR / "agent_state.db"

# Module-level connection pool (one connection per thread via threading.local)
_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """Return a thread-local SQLite connection to agent_state.db with WAL mode."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-8000")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.row_factory = sqlite3.Row
        _local.conn = conn
        _ensure_schema(conn)
    return _local.conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS goals (
            id            TEXT PRIMARY KEY,
            description   TEXT NOT NULL,
            agent_name    TEXT NOT NULL DEFAULT '',
            status        TEXT NOT NULL DEFAULT 'active',
            session_count INTEGER NOT NULL DEFAULT 0,
            created       TEXT NOT NULL,
            updated       TEXT NOT NULL,
            notes         TEXT DEFAULT '',
            model         TEXT DEFAULT 'deepseek-r1:8b',
            final_summary TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS goal_tasks (
            id             TEXT NOT NULL,
            goal_id        TEXT NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
            description    TEXT NOT NULL,
            status         TEXT NOT NULL DEFAULT 'pending',
            output         TEXT DEFAULT '',
            created        TEXT NOT NULL,
            updated        TEXT NOT NULL,
            session        INTEGER NOT NULL DEFAULT 0,
            model_override TEXT DEFAULT NULL,
            sort_order     INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (id, goal_id)
        );

        CREATE INDEX IF NOT EXISTS idx_goal_tasks_goal_id ON goal_tasks(goal_id);
        CREATE INDEX IF NOT EXISTS idx_goals_status       ON goals(status);
    """)
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─── Data models ──────────────────────────────────────────────────────────────

@dataclass
class GoalTask:
    """A single executable unit within a Goal."""
    id: str
    description: str
    status: str = "pending"
    output: str = ""
    created: str = field(default_factory=_now)
    updated: str = field(default_factory=_now)
    session: int = 0
    model_override: Optional[str] = None

    @property
    def is_done(self) -> bool:
        return self.status == "completed"

    @property
    def is_failed(self) -> bool:
        return self.status == "failed"

    @property
    def is_blocked(self) -> bool:
        return self.status == "blocked"


def is_task_failure_output(output: str) -> bool:
    """Detect if an execution output represents an error, failure, or stuck loop."""
    if not output or not isinstance(output, str):
        return True
    stripped = output.strip()
    if stripped.startswith("[Error]") or stripped.startswith("[Tool Failure]"):
        return True
    if "Agent stopped:" in stripped:
        return True
    if "timed out" in stripped.lower():
        return True
    if "Traceback (most recent call last)" in stripped:
        return True
    if "repeated identical tool call" in stripped.lower():
        return True
    return False


@dataclass
class Goal:
    """A long-horizon task that persists across multiple sessions."""
    id: str
    description: str
    agent_name: str
    tasks: List[GoalTask] = field(default_factory=list)
    status: str = "active"
    session_count: int = 0
    created: str = field(default_factory=_now)
    updated: str = field(default_factory=_now)
    notes: str = ""
    model: str = "deepseek-r1:8b"
    final_summary: str = ""

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
        """Return the next pending or in-progress task. Blocked goals/tasks cannot run."""
        if self.status in ("completed", "blocked", "failed"):
            return None
        for t in self.tasks:
            if t.status in ("pending", "in_progress"):
                return t
        return None

    def summary(self) -> str:
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
        lines = [
            f"## Long-Horizon Goal Context (Session {self.session_count + 1})",
            f"Overall Goal: {self.description}",
            f"Progress: {self.progress_pct:.0f}% ({len(self.completed_tasks)}/{len(self.tasks)} tasks completed)",
            "",
        ]
        if self.completed_tasks:
            lines.append("### Previous Sessions Completed Sub-Tasks & Outputs (Use this existing work & context!):")
            for t in self.completed_tasks:
                lines.append(f"✓ Sub-task: {t.description}")
                if t.output:
                    lines.append(f"  Output/Artifacts: {t.output[:1200]}")
            lines.append("\nIMPORTANT INSTRUCTION: Build directly upon the existing code, files, scripts, or APK artifacts produced in the previous sub-tasks above. Do NOT refuse tasks by claiming inability—you have local terminal access, python capabilities, and compilation tools.")

        next_t = self.next_task
        if next_t:
            lines.append(f"\n### Your current task for THIS session:")
            lines.append(f"  {next_t.description}")
            lines.append(
                "\nFocus on completing this task. When finished, summarize your work and emit 'Final Answer:' with your result."
            )

        if self.notes:
            lines.append(f"\n### Notes from previous session:\n{self.notes}")

        return "\n".join(lines)


# ─── Registry ─────────────────────────────────────────────────────────────────

class GoalRegistry:
    """Manages creation, persistence, and retrieval of Goals.

    All state is stored in ~/.ollama_agents/agent_state.db (SQLite, WAL mode).
    Legacy JSON files in ~/.ollama_agents/goals/ are automatically migrated on
    first access so existing goals are never lost.
    """

    def __init__(self) -> None:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        _get_conn()                  # ensure schema exists
        self._migrate_json_goals()   # one-time JSON → SQLite migration

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_id(goal_id: str) -> str:
        return "".join(c if c.isalnum() or c in "-_" else "_" for c in goal_id)

    def _save(self, goal: Goal) -> None:
        """Persist a Goal and all its tasks to SQLite in a single transaction."""
        goal.updated = _now()
        conn = _get_conn()
        with conn:
            conn.execute(
                """INSERT INTO goals (id, description, agent_name, status, session_count,
                        created, updated, notes, model, final_summary)
                   VALUES (:id,:description,:agent_name,:status,:session_count,
                           :created,:updated,:notes,:model,:final_summary)
                   ON CONFLICT(id) DO UPDATE SET
                       description=excluded.description,
                       agent_name=excluded.agent_name,
                       status=excluded.status,
                       session_count=excluded.session_count,
                       updated=excluded.updated,
                       notes=excluded.notes,
                       model=excluded.model,
                       final_summary=excluded.final_summary""",
                {
                    "id": goal.id,
                    "description": goal.description,
                    "agent_name": goal.agent_name,
                    "status": goal.status,
                    "session_count": goal.session_count,
                    "created": goal.created,
                    "updated": goal.updated,
                    "notes": goal.notes,
                    "model": goal.model,
                    "final_summary": goal.final_summary,
                },
            )
            # Upsert all tasks
            for idx, task in enumerate(goal.tasks):
                conn.execute(
                    """INSERT INTO goal_tasks
                           (id, goal_id, description, status, output,
                            created, updated, session, model_override, sort_order)
                       VALUES (?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(id, goal_id) DO UPDATE SET
                           description=excluded.description,
                           status=excluded.status,
                           output=excluded.output,
                           updated=excluded.updated,
                           session=excluded.session,
                           model_override=excluded.model_override,
                           sort_order=excluded.sort_order""",
                    (
                        task.id, goal.id, task.description, task.status,
                        task.output or "", task.created, task.updated,
                        task.session, task.model_override, idx,
                    ),
                )
        logger.debug("Goal saved to SQLite: '%s'", goal.id)

    def _load_from_db(self, goal_id: str) -> Optional[Goal]:
        conn = _get_conn()
        row = conn.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone()
        if not row:
            return None
        task_rows = conn.execute(
            "SELECT * FROM goal_tasks WHERE goal_id=? ORDER BY sort_order ASC", (goal_id,)
        ).fetchall()
        tasks = [
            GoalTask(
                id=r["id"],
                description=r["description"],
                status=r["status"],
                output=r["output"] or "",
                created=r["created"],
                updated=r["updated"],
                session=r["session"],
                model_override=r["model_override"],
            )
            for r in task_rows
        ]
        return Goal(
            id=row["id"],
            description=row["description"],
            agent_name=row["agent_name"],
            tasks=tasks,
            status=row["status"],
            session_count=row["session_count"],
            created=row["created"],
            updated=row["updated"],
            notes=row["notes"] or "",
            model=row["model"] or "deepseek-r1:8b",
            final_summary=row["final_summary"] or "",
        )

    def _migrate_json_goals(self) -> None:
        """One-time migration: import any legacy JSON goal files into SQLite."""
        if not _GOAL_DIR.exists():
            return
        conn = _get_conn()
        for path in _GOAL_DIR.glob("*.json"):
            if path.suffix != ".json":
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                goal_id = data.get("id", path.stem)
                # Skip if already in DB
                if conn.execute("SELECT 1 FROM goals WHERE id=?", (goal_id,)).fetchone():
                    continue
                tasks = [GoalTask(**t) for t in data.pop("tasks", [])]
                goal = Goal(**data, tasks=tasks)
                self._save(goal)
                # Rename migrated file so we don't re-import it
                path.rename(path.with_suffix(".json.migrated"))
                logger.info("Migrated legacy goal JSON → SQLite: '%s'", goal_id)
            except Exception as e:
                logger.warning("Could not migrate goal file %s: %s", path, e)

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
        goal = self._load_from_db(goal_id)
        if goal is None:
            logger.warning("Goal '%s' not found in SQLite DB.", goal_id)
        return goal

    def exists(self, goal_id: str) -> bool:
        conn = _get_conn()
        return bool(conn.execute("SELECT 1 FROM goals WHERE id=?", (goal_id,)).fetchone())

    def delete_goal(self, goal_id: str) -> bool:
        conn = _get_conn()
        with conn:
            conn.execute("DELETE FROM goal_tasks WHERE goal_id=?", (goal_id,))
            cur = conn.execute("DELETE FROM goals WHERE id=?", (goal_id,))
        deleted = cur.rowcount > 0
        if deleted:
            logger.info("Goal deleted from SQLite: '%s'", goal_id)
        return deleted

    def add_followup_task(self, goal_id: str, prompt: str) -> Optional[GoalTask]:
        goal = self.load(goal_id)
        if not goal:
            return None
        task_num = len(goal.tasks) + 1
        new_task = GoalTask(id=f"task-{task_num:03d}", description=f"Follow-up: {prompt}")
        goal.tasks.append(new_task)
        if goal.status == "completed":
            goal.status = "active"
            goal.final_summary = ""
        self._save(goal)
        logger.info("Added follow-up task to goal '%s': %s", goal_id, prompt)
        return new_task

    # ------------------------------------------------------------------
    # Task management
    # ------------------------------------------------------------------

    def get_next_task(self, goal_id: str) -> Optional[GoalTask]:
        goal = self.load(goal_id)
        return goal.next_task if goal else None

    def start_task(self, goal_id: str, task_id: str, session: int) -> None:
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
        goal = self.load(goal_id)
        if not goal:
            return
        for task in goal.tasks:
            if task.id == task_id:
                task.status = "completed"
                task.output = output[:2000]
                task.updated = _now()
                break
        if all(t.is_done for t in goal.tasks):
            goal.status = "completed"
            logger.info("Goal '%s' fully completed!", goal_id)
        self._save(goal)

    def fail_task(self, goal_id: str, task_id: str, reason: str = "") -> None:
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

    def reset_task(self, goal_id: str, task_id: str, model_override: Optional[str] = None) -> None:
        goal = self.load(goal_id)
        if not goal:
            return
        for task in goal.tasks:
            if task.id == task_id:
                task.status = "pending"
                task.output = ""
                task.updated = _now()
                if model_override:
                    task.model_override = model_override
                try:
                    from ollama_agents.checkpoint import CheckpointManager
                    CheckpointManager().delete(f"{goal_id}-{task.id}")
                except Exception:
                    pass
                break
        self._save(goal)

    def replan_remaining_tasks(
        self,
        goal_id: str,
        failed_task_id: str,
        new_task_descriptions: List[str],
    ) -> bool:
        """Replace remaining pending/blocked subtasks with revised steps from the replanner."""
        goal = self.load(goal_id)
        if not goal:
            return False

        failed_idx = -1
        for idx, task in enumerate(goal.tasks):
            if task.id == failed_task_id:
                failed_idx = idx
                break

        if failed_idx == -1:
            logger.warning("replan_remaining_tasks: task '%s' not found in goal '%s'", failed_task_id, goal_id)
            return False

        preserved_tasks = goal.tasks[: failed_idx + 1]
        start_num = len(preserved_tasks) + 1
        new_tasks = []
        for i, desc in enumerate(new_task_descriptions):
            new_tasks.append(
                GoalTask(
                    id=f"task-{start_num + i:03d}",
                    description=desc,
                    status="pending",
                )
            )

        conn = _get_conn()
        with conn:
            conn.execute(
                "DELETE FROM goal_tasks WHERE goal_id = ? AND sort_order > ?",
                (goal_id, failed_idx),
            )

        goal.tasks = preserved_tasks + new_tasks
        goal.status = "active"
        self._save(goal)
        logger.info(
            "Goal '%s' dynamically replanned: replaced remaining tasks with %d new steps.",
            goal_id,
            len(new_tasks),
        )
        return True

    def block_downstream_tasks(
        self,
        goal_id: str,
        failed_task_id: str,
        reason: str = "",
    ) -> None:
        """Cascade failure: mark all downstream pending tasks as 'blocked'."""
        goal = self.load(goal_id)
        if not goal:
            return

        failed_found = False
        blocked_count = 0
        for task in goal.tasks:
            if task.id == failed_task_id:
                failed_found = True
                continue
            if failed_found and task.status in ("pending", "in_progress"):
                task.status = "blocked"
                task.output = f"⛔ Cascaded Block: Upstream task '{failed_task_id}' failed: {reason[:200]}"
                task.updated = _now()
                blocked_count += 1

        goal.status = "blocked"
        self._save(goal)
        logger.warning(
            "Goal '%s' marked blocked: cascaded failure from task '%s' to %d downstream tasks.",
            goal_id,
            failed_task_id,
            blocked_count,
        )

    def set_task_model(self, goal_id: str, task_id: str, model: Optional[str]) -> bool:
        """Update model_override for a specific sub-task in a goal."""
        goal = self.load(goal_id)
        if not goal:
            return False
        found = False
        for task in goal.tasks:
            if task.id == task_id:
                task.model_override = model.strip() if (model and model.strip()) else None
                task.updated = _now()
                found = True
                break
        if found:
            self._save(goal)
            logger.info("Updated task '%s' in goal '%s' model_override to: %s", task_id, goal_id, model)
        return found

    def set_goal_model(self, goal_id: str, model: str) -> bool:
        """Update the default execution model for an entire goal."""
        goal = self.load(goal_id)
        if not goal:
            return False
        goal.model = model.strip() if (model and model.strip()) else "deepseek-r1:8b"
        goal.updated = _now()
        self._save(goal)
        logger.info("Updated goal '%s' model to: %s", goal_id, goal.model)
        return True

    def save_notes(self, goal_id: str, notes: str) -> None:
        goal = self.load(goal_id)
        if goal:
            goal.notes = notes[:500]
            self._save(goal)

    def save_final_summary(self, goal_id: str, summary: str) -> None:
        goal = self.load(goal_id)
        if goal:
            goal.final_summary = summary
            self._save(goal)

    def increment_session(self, goal_id: str) -> int:
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
        conn = _get_conn()
        rows = conn.execute(
            "SELECT id FROM goals ORDER BY updated DESC"
        ).fetchall()
        goals = []
        for row in rows:
            g = self._load_from_db(row["id"])
            if g:
                goals.append(g)
        return goals

    def list_active(self) -> List[Goal]:
        return [g for g in self.list_all() if g.status == "active"]

    # ── Convenient Aliases ─────────────────────────────────────────────
    def list_goals(self) -> List[Goal]:
        return self.list_all()

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        return self.load(goal_id)

    def create_goal(self, prompt: str, model: str = "deepseek-r1:8b") -> Goal:
        from ollama_agents.planner import Planner
        planner = Planner(model=model)
        tasks = planner.hierarchical_decompose(prompt)
        task_descriptions = [t.get("description", str(t)) if isinstance(t, dict) else str(t) for t in tasks]
        goal = self.create(
            description=prompt,
            task_descriptions=task_descriptions if task_descriptions else [prompt],
            agent_name="AutonomousAgent",
        )
        goal.model = model
        self._save(goal)
        return goal
