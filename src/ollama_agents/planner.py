"""Goal Planner — decomposes a high-level goal into an ordered list of subtasks.

The planner uses a lightweight reasoning model (no tools required) to produce a
numbered task list that the agent can then execute step by step.
"""

import logging
import re
from typing import List, Optional

import ollama

logger = logging.getLogger(__name__)

_PLANNER_SYSTEM = """\
You are a precise task planner. Given a high-level goal, break it down into a \
numbered list of concrete, atomic subtasks. Each subtask should be actionable and \
specific enough for an AI agent to execute independently.

Output ONLY the numbered list. Example format:
1. Fetch the current price of NVDA using a market data tool.
2. Search the web for NVDA earnings news from the last 7 days.
3. Summarise the price and news into a 3-bullet investor briefing.

Do NOT include explanations, headers, or any text outside the numbered list.\
"""


_REPLAN_SYSTEM = """\
You are a precise task re-planner. A step in an ongoing plan has failed or needs adjustment.
Given the goal, the steps completed so far, what failed, and why, produce a REVISED numbered \
list of remaining steps to still accomplish the goal.

Output ONLY the numbered list of remaining steps. Example:
1. Try an alternative approach to write the file using a different path.
2. Verify the file was written correctly by reading it back.

Do NOT repeat already-completed steps. Do NOT include explanations outside the list."""


class Planner:
    """Decomposes a high-level goal into concrete subtasks using an LLM.

    Args:
        model: Ollama model to use for planning. If None/default, automatically selects the best local reasoning model.
        host: Optional Ollama host URL.
        max_steps: Maximum subtasks to return.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        host: Optional[str] = None,
        max_steps: int = 10,
        auto_select_model: bool = False,
    ) -> None:
        from ollama_agents.model_selector import select_best_local_model
        if model:
            self.model = model
        else:
            self.model = select_best_local_model(task_type="reasoning")

        self.max_steps = max_steps
        self.client = ollama.Client(host=host)
        logger.info("Planner initialized using model '%s'", self.model)

    def decompose(self, goal: str) -> List[str]:
        """Break *goal* into an ordered list of subtask strings."""
        # BEFORE STARTING ANYTHING: Check/Generate Skill file first
        from ollama_agents.skills import SkillRegistry
        skill_registry = SkillRegistry()
        skill = skill_registry.ensure_skill_for_goal(goal, model=self.model)

        prompt = f"Goal: {goal.strip()}\nUsing Skill: {skill.name}\nInstructions: {skill.instructions}"
        logger.info("Planner decomposing goal with skill '%s': %s", skill.name, goal)

        response = self.client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": _PLANNER_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            options={"temperature": 0.2, "num_ctx": 4096},
        )

        # Handle both Pydantic model and dict response
        if hasattr(response, "message"):
            content = response.message.content or ""
        else:
            content = response.get("message", {}).get("content", "")

        steps = self._parse_steps(content)
        logger.info("Planner produced %d steps.", len(steps))
        return steps[: self.max_steps]

    @staticmethod
    def _parse_steps(text: str) -> List[str]:
        """Extract numbered list items from raw model output."""
        steps = []
        for line in text.splitlines():
            stripped = line.strip()
            # Match "1. Step text" or "1) Step text"
            match = re.match(r"^\d+[.)]\s+(.+)", stripped)
            if match:
                steps.append(match.group(1).strip())
        return steps

    def replan(
        self,
        goal: str,
        completed_steps: List[str],
        failed_step: str,
        failure_reason: str,
        remaining_steps: Optional[List[str]] = None,
    ) -> List[str]:
        """Produce a revised plan after a step failure.

        Args:
            goal: The original high-level goal.
            completed_steps: Steps that have already been completed successfully.
            failed_step: The step that failed.
            failure_reason: Why the step failed.
            remaining_steps: The steps that were still pending (may be replaced).

        Returns:
            A new list of remaining steps to accomplish the goal.
        """
        context = (
            f"Goal: {goal}\n"
            f"Completed steps:\n" +
            ("\n".join(f"  - {s}" for s in completed_steps) or "  (none)") +
            f"\n\nFailed step: {failed_step}"
            f"\nFailure reason: {failure_reason}"
        )
        if remaining_steps:
            context += "\nOriginal remaining steps:\n" + "\n".join(
                f"  - {s}" for s in remaining_steps
            )

        logger.info("Planner replanning after failure: %s", failed_step)

        response = self.client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": _REPLAN_SYSTEM},
                {"role": "user", "content": context},
            ],
            options={"temperature": 0.2, "num_ctx": 4096},
        )

        if hasattr(response, "message"):
            content = response.message.content or ""
        else:
            content = response.get("message", {}).get("content", "")

        steps = self._parse_steps(content)
        logger.info("Replanner produced %d revised steps.", len(steps))
        return steps[: self.max_steps]

    def assess_required_skills(self, goal: str) -> List[str]:
        """Assess which registered skills and tools are required for a goal before decomposition."""
        from ollama_agents.skills import SkillRegistry
        registry = SkillRegistry()
        available_skills = registry.list_skills()

        # Fast path: keyword matching to avoid extra LLM latency during goal creation
        goal_lower = goal.lower()
        matched = []
        for s in available_skills:
            if any(tool.lower() in goal_lower for tool in s.required_tools) or s.name.lower() in goal_lower:
                matched.append(s.name)

        if matched:
            return matched

        return ["PythonCodingSkill"]

    def hierarchical_decompose(
        self,
        goal: str,
        max_tasks: int = 8,
        session_context: str = "",
    ) -> List[str]:
        """Decompose a long-horizon goal into session-sized, skill-aware tasks."""
        # BEFORE STARTING ANYTHING: Check if skill file exists; if not, create skill file before planning
        from ollama_agents.skills import SkillRegistry
        registry = SkillRegistry()
        skill = registry.ensure_skill_for_goal(goal, model=self.model)

        required_skills = self.assess_required_skills(goal)
        if skill.name not in required_skills:
            required_skills.append(skill.name)

        skill_prompts = []
        for sk_name in required_skills:
            sk = registry.load(sk_name)
            if sk:
                skill_prompts.append(f"Skill '{sk.name}' (v{sk.version}): {sk.instructions}")

        skills_block = "\n".join(skill_prompts) if skill_prompts else ""

        system = (
            "You are a strategic task planner for a long-horizon autonomous agent. "
            "Break the goal into a numbered list of SESSIONS — each session is one "
            "independent, self-contained task an AI agent can complete in ~25 tool calls. "
            "Each task must:\n"
            "  - Be independently runnable without the outputs of later tasks\n"
            "  - Produce a concrete, reusable output (data, file, summary)\n"
            "  - Be specific enough to execute without further clarification\n\n"
            f"Required Skills Guidance:\n{skills_block}\n\n"
            "Output ONLY the numbered list. No headers, no explanations.\n"
        )
        prompt = f"Goal: {goal.strip()}"
        if session_context:
            prompt += f"\n\nContext: {session_context}"

        logger.info("Hierarchical planner decomposing: %s (Skills: %s)", goal[:80], required_skills)
        try:
            # Use short 8.0s timeout so goal registration returns quickly without freezing UI
            short_client = ollama.Client(timeout=8.0)
            response = short_client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                options={"temperature": 0.2, "num_ctx": 2048},
            )
            if hasattr(response, "message"):
                content = response.message.content or ""
            else:
                content = response.get("message", {}).get("content", "")

            tasks = self._parse_steps(content)
            logger.info("Hierarchical planner produced %d tasks.", len(tasks))
            if tasks:
                return tasks[:max_tasks]
            
            # Actionable fallback breakdown if LLM output was unparseable
            return [
                f"Gather required context and analyze target files for: {goal}",
                f"Write code, generate media, or perform primary actions for: {goal}",
                f"Verify, execute, and compile final output report for: {goal}"
            ]
        except Exception as e:
            logger.warning("Goal decomposition failed (%s). Using actionable multi-task breakdown.", e)
            return [
                f"Gather required context and analyze target files for: {goal}",
                f"Write code, generate media, or perform primary actions for: {goal}",
                f"Verify, execute, and compile final output report for: {goal}"
            ]

    def auto_refine_skills(self, reflection_text: str) -> None:
        """Self-improvement pass: update registered skills based on post-task reflection lessons."""
        from ollama_agents.skills import SkillRegistry
        registry = SkillRegistry()
        skills = registry.list_skills()

        for skill in skills:
            # If reflection notes a failure or optimization related to this skill, update it
            if any(tool.lower() in reflection_text.lower() for tool in skill.required_tools) or skill.name.lower() in reflection_text.lower():
                lesson_line = reflection_text.splitlines()[-1] if reflection_text.strip() else reflection_text
                registry.refine_skill(
                    skill_name=skill.name,
                    lesson_learned=f"Auto-Refined from run: {lesson_line[:120]}",
                    new_instruction=f"Optimized handling based on reflection: {lesson_line[:150]}"
                )
                logger.info("Auto-refined skill '%s' based on self-improvement reflection.", skill.name)
