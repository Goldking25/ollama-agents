"""Agent — Level 4 autonomous LLM agent powered by a local Ollama model.

New in this version (long-horizon):
- Context compression: history is summarised when it exceeds compress_after messages.
- run_goal(): drives a multi-session Goal from the GoalRegistry, one task per session.
- Planner integration: replan() called on tool failure.
- Checkpointing: crash-safe resumption via task_id.
- Self-improvement: reflection loop after each run.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

import ollama

from .checkpoint import CheckpointManager, CheckpointState
from .exceptions import AgentConfigError, MaxTurnsExceeded, ToolExecutionError
from .memory import MemoryStore
from .tool import Tool
# GoalRegistry imported lazily inside run_goal() to avoid circular imports

logger = logging.getLogger(__name__)

# ─── ReAct prompt ─────────────────────────────────────────────────────────────
_REACT_INSTRUCTIONS = """
## Reasoning Protocol
Follow the Thought → Action → Observation cycle for every tool call.

Thought: <why you are taking this action>
[tool call happens automatically]
Observation: <what the tool returned>
Thought: <what you conclude>
... (repeat as needed)
Final Answer: <your complete response>

Rules:
- Always start with a Thought before calling a tool.
- Emit "Final Answer:" only when the task is fully complete.
- If a tool fails, reason about why and try an alternative approach.
- When the plan is updated, follow the new steps.
"""

# ─── Reflection prompt ────────────────────────────────────────────────────────
_REFLECTION_SYSTEM = """\
You are reflecting on a completed task to extract lessons for future runs.
Be concise and specific. Output exactly 3 bullet points:
- What worked: <one sentence>
- What failed or was slow: <one sentence, or 'Nothing significant'>
- Next time I will: <one concrete improvement>\
"""


class Agent:
    """Level 4 autonomous agent with planning, checkpointing, and self-improvement.

    Args:
        name: Human-readable agent name.
        role: One-line specialisation description.
        instructions: Detailed operating guidelines. Must not be empty.
        model: Ollama model identifier (default ``"llama3.1"``).
        tools: Python callables to expose as tools.
        temperature: Sampling temperature.
        num_ctx: Context window size in tokens.
        host: Optional Ollama server URL.
        memory: Optional :class:`MemoryStore` for persistent cross-run memory.
        max_turns: Hard cap on reasoning turns per ``run()`` call (default 25).
        stateful: If ``True``, history persists across successive ``run()`` calls.
        confirm_actions: Tool names that require human approval before execution.
        critic: Optional :class:`Critic` that reviews output before returning.
        max_critique_rounds: Max critic revision cycles (default 2).
        planner: Optional :class:`Planner` for decomposing goals and replanning.
        enable_checkpointing: Save state to disk after every tool call (default True).
        enable_reflection: Write a self-improvement lesson after each run (default True).
    """

    def __init__(
        self,
        name: str = "AssistantAgent",
        role: str = "General Assistant",
        instructions: str = "You are a helpful, autonomous AI assistant. Use available tools when necessary to answer questions or complete tasks.",
        model: str = "deepseek-r1:8b",
        tools: Optional[List[Callable]] = None,
        temperature: float = 0.0,
        num_ctx: int = 8192,
        host: Optional[str] = None,
        memory: Optional[MemoryStore] = None,
        max_turns: int = 25,
        stateful: bool = False,
        confirm_actions: Optional[List[str]] = None,
        critic: Optional["Critic"] = None,  # type: ignore[name-defined]  # noqa: F821
        max_critique_rounds: int = 2,
        planner: Optional["Planner"] = None,  # type: ignore[name-defined]  # noqa: F821
        enable_checkpointing: bool = True,
        enable_reflection: bool = True,
        compress_after: int = 30,
    ) -> None:
        if not name.strip():
            raise AgentConfigError("Agent 'name' cannot be empty.")
        if not instructions.strip():
            raise AgentConfigError("Agent 'instructions' cannot be empty.")

        self.name = name
        self.role = role
        self.model = model
        self.temperature = temperature
        self.num_ctx = num_ctx
        self.max_turns = max_turns
        self.stateful = stateful
        self.memory = memory
        self.client = ollama.Client(host=host)
        self.confirm_actions: Set[str] = set(confirm_actions or [])
        self.critic = critic
        self.max_critique_rounds = max_critique_rounds
        self.planner = planner
        self.enable_checkpointing = enable_checkpointing
        self.enable_reflection = enable_reflection
        self.compress_after = compress_after
        self._checkpoint_mgr = CheckpointManager() if enable_checkpointing else None

        self._base_system_prompt = (
            f"You are {self.name}, specialized as a {self.role}.\n"
            f"Operating Guidelines:\n{instructions.strip()}"
        )

        self.tools: Dict[str, Tool] = {
            fn.__name__: Tool(fn) for fn in (tools or [])
        }
        self.history: List[Dict[str, Any]] = []
        self.reset()

    # ──────────────────────────────────────────────────────────────────
    # System prompt
    # ──────────────────────────────────────────────────────────────────

    def _build_system_prompt(self, task: str = "") -> str:
        """Assemble full system prompt including memory, reflections, and ReAct format."""
        parts = [self._base_system_prompt]

        if self.memory:
            mem_ctx = self.memory.build_memory_context(query=task)
            if mem_ctx:
                parts.append(f"\n## Long-Term Memory\n{mem_ctx}")

            # Inject past self-improvement reflections
            reflections = self.memory.recall_facts(query="reflection", limit=3)
            if reflections:
                parts.append("\n## Self-Improvement Notes (from past runs)")
                for _, lesson in reflections:
                    parts.append(lesson)

        if self.tools:
            parts.append(_REACT_INSTRUCTIONS)

        return "\n".join(parts)

    # ──────────────────────────────────────────────────────────────────
    # State management
    # ──────────────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Reset conversation history to the initial system context."""
        self.history = [{"role": "system", "content": self._build_system_prompt()}]

    # ──────────────────────────────────────────────────────────────────
    # Response unwrapping
    # ──────────────────────────────────────────────────────────────────

    def _to_dict(self, obj: Any) -> Dict[str, Any]:
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            return obj.dict()
        if isinstance(obj, dict):
            return obj
        return {k: getattr(obj, k) for k in dir(obj) if not k.startswith("_")}

    def _extract_message(self, response: Any) -> Dict[str, Any]:
        if hasattr(response, "message"):
            return self._to_dict(response.message)
        if isinstance(response, dict) and "message" in response:
            return self._to_dict(response["message"])
        raise ValueError(f"Unexpected Ollama response shape: {type(response)}")

    def _parse_text_tool_calls(self, content: str) -> List[Dict[str, Any]]:
        """Fallback tool call extractor for models like llama3.1 that output JSON objects or code blocks."""
        import re
        import json

        calls = []
        if not content:
            return calls

        tool_names = set(self.tools.keys()) if self.tools else set()

        # 1. Parse full JSON objects with "name" and "parameters"/"arguments"
        decoder = json.JSONDecoder()
        pos = 0
        while pos < len(content):
            idx = content.find('{', pos)
            if idx == -1:
                break
            try:
                obj, end = decoder.raw_decode(content[idx:])
                pos = idx + end
                if isinstance(obj, dict) and "name" in obj:
                    fn_name = obj["name"]
                    if not tool_names or fn_name in tool_names:
                        fn_args = obj.get("parameters") or obj.get("arguments") or {}
                        if not isinstance(fn_args, dict):
                            fn_args = {}
                        calls.append({"function": {"name": fn_name, "arguments": fn_args}})
            except Exception:
                pos = idx + 1

        if not calls:
            # 2. Code block fallback ```json ... ```
            code_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
            for block in code_blocks:
                try:
                    data = json.loads(block.strip())
                    if isinstance(data, dict) and "name" in data and data["name"] in self.tools:
                        fn_args = data.get("parameters") or data.get("arguments") or {}
                        calls.append({"function": {"name": data["name"], "arguments": fn_args}})
                except Exception:
                    pass

        return calls

    # ──────────────────────────────────────────────────────────────────
    # Human-in-the-loop
    # ──────────────────────────────────────────────────────────────────

    def _confirm_tool_call(self, fn_name: str, fn_args: Dict[str, Any]) -> bool:
        print(f"\n{'─'*52}")
        print(f"  [!] Human Approval Required")
        print(f"  Tool : {fn_name}")
        print(f"  Args : {fn_args}")
        print(f"{'─'*52}")
        try:
            answer = input("  Approve? (y/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        if answer not in ("y", "yes"):
            print("  [Denied] Skipping.\n")
            return False
        return True

    # ──────────────────────────────────────────────────────────────────
    # Tool execution
    # ──────────────────────────────────────────────────────────────────

    def _execute_tool(self, fn_name: str, fn_args: Dict[str, Any]) -> str:
        if fn_name not in self.tools:
            return f"[Error] Tool '{fn_name}' is not registered."
        if fn_name in self.confirm_actions:
            if not self._confirm_tool_call(fn_name, fn_args):
                return "[User denied this action. Try a different approach.]"
        try:
            return self.tools[fn_name].execute(**fn_args)
        except ToolExecutionError as e:
            logger.error("Tool failed permanently: %s", e)
            return (
                f"[Tool Failure] '{fn_name}' failed after all retries. "
                f"Reason: {e.cause}. Try a different approach."
            )

    # ──────────────────────────────────────────────────────────────────
    # Self-improvement reflection
    # ──────────────────────────────────────────────────────────────────

    def _reflect(
        self,
        task: str,
        outcome: str,
        tool_calls_made: List[str],
        errors: List[str],
    ) -> None:
        """Generate a self-improvement lesson and store it in memory."""
        if not self.memory:
            return
        try:
            tool_log = ", ".join(tool_calls_made[-10:]) or "none"
            error_log = "; ".join(errors[-5:]) or "none"
            prompt = (
                f"Task: {task[:300]}\n"
                f"Outcome: {outcome[:300]}\n"
                f"Tools used: {tool_log}\n"
                f"Errors: {error_log}"
            )
            response = self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": _REFLECTION_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                options={"temperature": 0.3, "num_ctx": 4096},
            )
            if hasattr(response, "message"):
                reflection = response.message.content or ""
            else:
                reflection = response.get("message", {}).get("content", "")

            if reflection.strip():
                key = f"reflection_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
                self.memory.save_fact(key, reflection.strip(), tags="reflection")
                self.memory.write_note(f"[{key}] {reflection.strip()}")
                logger.info("[%s] Reflection stored: %s", self.name, key)

                # Auto-refine skill blueprints based on self-improvement lessons
                if self.planner:
                    try:
                        self.planner.auto_refine_skills(reflection.strip())
                    except Exception as sk_err:
                        logger.warning("Skill auto-refine failed: %s", sk_err)
        except Exception as e:
            logger.warning("Reflection failed (non-critical): %s", e)

    # ──────────────────────────────────────────────────────────────────
    # Core run loop
    # ──────────────────────────────────────────────────────────────────

    def run(
        self,
        user_prompt: str,
        max_turns: Optional[int] = None,
        task_id: Optional[str] = None,
    ) -> str:
        """Execute the ReAct loop until Final Answer or max_turns.

        Args:
            user_prompt: The task or goal for this agent.
            max_turns: Override instance max_turns for this call.
            task_id: Unique ID for checkpointing. If a checkpoint exists with
                     this ID, the run resumes from where it left off. On
                     successful completion the checkpoint is deleted.

        Returns:
            The agent's final answer string.

        Raises:
            MaxTurnsExceeded: If the turn limit is reached. The checkpoint
                              is kept so the caller can resume.
        """
        limit = max_turns if max_turns is not None else self.max_turns

        # ── Tracking state ────────────────────────────────────────────
        completed_steps: List[str] = []
        remaining_steps: List[str] = []
        tool_calls_made: List[str] = []
        errors: List[str] = []
        start_turn = 0

        # ── Checkpoint restore ────────────────────────────────────────
        checkpoint: Optional[CheckpointState] = None
        if task_id and self._checkpoint_mgr:
            checkpoint = self._checkpoint_mgr.load(task_id)

        if checkpoint:
            print(f"\n[Resume] Restoring checkpoint '{task_id}' from turn {checkpoint.turn}...")
            self.history = checkpoint.history
            completed_steps = checkpoint.completed_steps
            remaining_steps = checkpoint.remaining_steps
            tool_calls_made = checkpoint.tool_calls_made
            errors = checkpoint.errors
            start_turn = checkpoint.turn
        else:
            # Fresh start: Ensure Skill file exists BEFORE doing anything (even before planning)
            from ollama_agents.skills import SkillRegistry
            skill_reg = SkillRegistry()
            skill_reg.ensure_skill_for_goal(user_prompt, model=self.model)

            if not self.stateful:
                self.history = [
                    {"role": "system", "content": self._build_system_prompt(task=user_prompt)}
                ]
            self.history.append({"role": "user", "content": user_prompt})

            # ── Planner: decompose goal into steps ────────────────────
            if self.planner:
                remaining_steps = self.planner.decompose(user_prompt)
                if remaining_steps:
                    step_list = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(remaining_steps))
                    logger.info("[%s] Plan:\n%s", self.name, step_list)
                    self.history.append({
                        "role": "user",
                        "content": (
                            f"Here is your execution plan:\n{step_list}\n\n"
                            f"Follow these steps in order."
                        ),
                    })

        tool_schemas = [t.schema for t in self.tools.values()] if self.tools else None
        options = {"temperature": self.temperature, "num_ctx": self.num_ctx}
        last_content = ""

        # ── Helper: save checkpoint ───────────────────────────────────
        def _save_cp(turn: int) -> None:
            if task_id and self._checkpoint_mgr:
                self._checkpoint_mgr.save(CheckpointState(
                    task_id=task_id,
                    task=user_prompt,
                    agent_name=self.name,
                    turn=turn,
                    history=self.history,
                    completed_steps=completed_steps,
                    remaining_steps=remaining_steps,
                    tool_calls_made=tool_calls_made,
                    errors=errors,
                ))

        # ── Main loop ─────────────────────────────────────────────────
        for turn in range(start_turn, limit):
            logger.debug("[%s] Turn %d/%d", self.name, turn + 1, limit)

            # ── Context compression ────────────────────────────────────
            if len(self.history) > self.compress_after:
                self._compress_history()

            try:
                response = self.client.chat(
                    model=self.model,
                    messages=self.history,
                    tools=tool_schemas if tool_schemas else None,
                    options=options,
                )
            except ollama.ResponseError as err:
                if "does not support tools" in str(err).lower() or err.status_code == 400:
                    # Model doesn't support native tool parameter - fall back to text prompt tools
                    response = self.client.chat(
                        model=self.model,
                        messages=self.history,
                        options=options,
                    )
                else:
                    raise err

            msg = self._extract_message(response)
            self.history.append(msg)

            content: str = msg.get("content") or ""
            tool_calls_list: List[Any] = msg.get("tool_calls") or []
            last_content = content

            # Fallback: if model (e.g. llama3.1) returned JSON text tool calls instead of native tool_calls
            if not tool_calls_list and content:
                text_calls = self._parse_text_tool_calls(content)
                if text_calls:
                    tool_calls_list = text_calls

            # ── Goal-completion detection ──────────────────────────────
            if "Final Answer:" in content:
                answer = content.split("Final Answer:", 1)[-1].strip()
                logger.info("[%s] Final Answer at turn %d.", self.name, turn + 1)

                # ── Critic review ──────────────────────────────────────
                if self.critic:
                    for rnd in range(self.max_critique_rounds):
                        result = self.critic.review(task=user_prompt, output=answer)
                        status = "Approved" if result.approved else "Needs revision"
                        print(f"\n  [Critic round {rnd+1}] {status} (score={result.score:.2f})")
                        if result.approved:
                            break
                        print(f"  Feedback: {result.feedback}")
                        if result.revised:
                            answer = result.revised
                            break
                        self.history.append({
                            "role": "user",
                            "content": (
                                f"Critic feedback:\n{result.feedback}\n"
                                "Revise and start with 'Final Answer:'"
                            ),
                        })
                        rev = self.client.chat(
                            model=self.model, messages=self.history,
                            tools=tool_schemas, options=options,
                        )
                        rev_msg = self._extract_message(rev)
                        self.history.append(rev_msg)
                        rev_content = rev_msg.get("content") or ""
                        if "Final Answer:" in rev_content:
                            answer = rev_content.split("Final Answer:", 1)[-1].strip()

                # ── Persist episode ────────────────────────────────────
                if self.memory:
                    self.memory.save_episode(task=user_prompt[:120], summary=answer[:400])

                # ── Self-improvement reflection ────────────────────────
                if self.enable_reflection:
                    self._reflect(user_prompt, answer, tool_calls_made, errors)

                # ── Delete checkpoint on success ───────────────────────
                if task_id and self._checkpoint_mgr:
                    self._checkpoint_mgr.delete(task_id)

                return answer

            # ── No tool calls and no Final Answer ─────────────────────
            if not tool_calls_list:
                if content:
                    if self.memory:
                        self.memory.save_episode(task=user_prompt[:120], summary=content[:400])
                    if self.enable_reflection:
                        self._reflect(user_prompt, content, tool_calls_made, errors)
                    if task_id and self._checkpoint_mgr:
                        self._checkpoint_mgr.delete(task_id)
                    return content
                # Empty response — nudge
                self.history.append({
                    "role": "user",
                    "content": (
                        "Please continue. When done, write 'Final Answer: <your answer>'"
                    ),
                })
                continue

            # ── Execute tool calls ─────────────────────────────────────
            for call in tool_calls_list:
                call_data = self._to_dict(call)
                func_data = self._to_dict(call_data.get("function") or {})
                fn_name: str = func_data.get("name") or ""
                fn_args: Dict[str, Any] = func_data.get("arguments") or {}

                logger.info("[%s] Tool: %s(%s)", self.name, fn_name, fn_args)
                tool_calls_made.append(fn_name)

                output = self._execute_tool(fn_name, fn_args)
                self.history.append({"role": "tool", "content": output})

                # ── Replan on tool failure ─────────────────────────────
                is_failure = output.startswith("[Tool Failure]") or output.startswith("[Error]")
                if is_failure and self.planner and remaining_steps:
                    failure_reason = output[:200]
                    errors.append(f"{fn_name}: {failure_reason}")
                    logger.warning("[%s] Tool failed — triggering replan.", self.name)
                    try:
                        failed_step = remaining_steps[0] if remaining_steps else fn_name
                        revised = self.planner.replan(
                            goal=user_prompt,
                            completed_steps=completed_steps,
                            failed_step=failed_step,
                            failure_reason=failure_reason,
                            remaining_steps=remaining_steps,
                        )
                        if revised:
                            remaining_steps = revised
                            step_list = "\n".join(
                                f"  {i+1}. {s}" for i, s in enumerate(revised)
                            )
                            logger.info("[%s] Revised plan:\n%s", self.name, step_list)
                            self.history.append({
                                "role": "user",
                                "content": (
                                    f"The previous step failed. Updated plan:\n{step_list}\n"
                                    "Continue with the revised plan."
                                ),
                            })
                    except Exception as replan_err:
                        logger.warning("Replan failed (non-critical): %s", replan_err)

                # ── Save checkpoint after every tool call ──────────────
                _save_cp(turn + 1)

            # ── Advance plan tracking ──────────────────────────────────
            if remaining_steps and not is_failure:  # type: ignore[possibly-undefined]
                done = remaining_steps.pop(0)
                completed_steps.append(done)

        # ── Turn limit reached ─────────────────────────────────────────
        raise MaxTurnsExceeded(turns=limit, last_output=last_content)

    # ──────────────────────────────────────────────────────────────────
    # Context compression
    # ──────────────────────────────────────────────────────────────────

    def _compress_history(self) -> None:
        """Summarise the oldest half of messages to free up context space.

        Keeps the system prompt and the most recent half of messages intact.
        The older half is replaced with a single summary assistant message.
        Called automatically inside the run loop when len(history) > compress_after.
        """
        # Never compress if we have too few messages
        if len(self.history) <= 4:
            return

        system_msgs = [m for m in self.history if m.get("role") == "system"]
        non_system = [m for m in self.history if m.get("role") != "system"]

        # Split: compress the older half, keep the newer half
        split = len(non_system) // 2
        to_compress = non_system[:split]
        to_keep = non_system[split:]

        if not to_compress:
            return

        # Build a short transcript to summarise
        transcript_lines = []
        for m in to_compress:
            role = m.get("role", "")
            content = str(m.get("content") or "")[:300]
            transcript_lines.append(f"{role.upper()}: {content}")
        transcript = "\n".join(transcript_lines)

        logger.info(
            "[%s] Compressing %d messages (history=%d > threshold=%d).",
            self.name, len(to_compress), len(self.history), self.compress_after,
        )

        try:
            resp = self.client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Summarise the following agent conversation turns into a "
                            "single concise paragraph. Include all factual findings, "
                            "tool results, and decisions made. Be specific and dense — "
                            "this summary will replace the original turns."
                        ),
                    },
                    {"role": "user", "content": transcript},
                ],
                options={"temperature": 0.1, "num_ctx": 4096},
            )
            if hasattr(resp, "message"):
                summary = resp.message.content or ""
            else:
                summary = resp.get("message", {}).get("content", "")
        except Exception as e:
            logger.warning("Compression summarisation failed (%s) — skipping.", e)
            return

        summary_msg = {
            "role": "assistant",
            "content": f"[Compressed summary of earlier turns]: {summary.strip()}",
        }
        self.history = system_msgs + [summary_msg] + to_keep
        logger.info("[%s] History compressed: %d -> %d messages.", self.name,
                    len(system_msgs) + len(non_system), len(self.history))

    # ──────────────────────────────────────────────────────────────────
    # Long-horizon: run_goal()
    # ──────────────────────────────────────────────────────────────────

    def run_goal(
        self,
        goal_id: str,
        registry: Optional["GoalRegistry"] = None,  # type: ignore[name-defined]  # noqa: F821
        max_turns: Optional[int] = None,
    ) -> str:
        """Run the next pending task of a long-horizon Goal.

        Each call to ``run_goal()`` works on exactly ONE task from the goal.
        Call it again (in the next session) to continue with the next task.
        The goal completes automatically when all tasks are done.
        """
        if registry is None:
            from ollama_agents.goal import GoalRegistry
            registry = GoalRegistry()

        goal = registry.load(goal_id)
        if goal is None:
            raise ValueError(f"Goal '{goal_id}' not found in registry.")

        if goal.status == "completed":
            return "Goal already completed."

        task = goal.next_task
        if task is None:
            return "Goal already completed — no pending tasks."

        # Increment session counter
        session_num = registry.increment_session(goal_id)
        registry.start_task(goal_id, task.id, session=session_num)

        print(f"\n{'='*60}")
        print(f"  Long-Horizon Goal: {goal.id}")
        print(f"  Session #{session_num}  |  Progress: {goal.progress_pct:.0f}%")
        print(f"  Task: {task.description}")
        print(f"{'='*60}\n")

        # Build a prompt that includes goal context
        goal_ctx = goal.context_for_next_session()
        full_prompt = f"{goal_ctx}\n\nYour task for this session:\n{task.description}"

        task_id_for_checkpoint = f"{goal_id}-{task.id}"

        try:
            output = self.run(
                user_prompt=full_prompt,
                max_turns=max_turns,
                task_id=task_id_for_checkpoint,
            )
            registry.complete_task(goal_id, task.id, output=output)

            # Reload to get updated progress
            updated_goal = registry.load(goal_id)
            if updated_goal:
                pct = updated_goal.progress_pct
                remaining = len(updated_goal.pending_tasks)
                print(f"\n  Task complete! Goal progress: {pct:.0f}%")
                if remaining > 0:
                    next_t = updated_goal.next_task
                    print(f"  Next session will run: '{next_t.description if next_t else '?'}'")
                else:
                    print(f"  All tasks complete! Goal '{goal_id}' is DONE.")
            return output

        except MaxTurnsExceeded as e:
            # Mark as in_progress (not failed), checkpoint is kept
            logger.warning(
                "[%s] MaxTurnsExceeded on task '%s'. Checkpoint kept for resume.",
                self.name, task.id,
            )
            print(f"\n  [!] Turn limit hit. Re-run to continue from checkpoint.")
            return e.last_output or "(no output yet)"

    # ──────────────────────────────────────────────────────────────────
    # Async wrapper
    # ──────────────────────────────────────────────────────────────────

    async def arun(
        self,
        user_prompt: str,
        max_turns: Optional[int] = None,
        task_id: Optional[str] = None,
    ) -> str:
        """Async wrapper around :meth:`run` for use in async contexts."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.run, user_prompt, max_turns, task_id)

    # ──────────────────────────────────────────────────────────────────
    # Dunder helpers
    # ──────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"Agent(name={self.name!r}, model={self.model!r}, "
            f"tools={list(self.tools)}, max_turns={self.max_turns}, "
            f"planner={'yes' if self.planner else 'no'}, "
            f"checkpointing={self.enable_checkpointing}, "
            f"reflection={self.enable_reflection})"
        )