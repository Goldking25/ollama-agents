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
        auto_select_model: bool = True,
    ) -> None:
        from ollama_agents.model_selector import select_best_local_model
        if auto_select_model or model is None:
            self.model = select_best_local_model(task_type="reasoning", preferred=model)
        else:
            self.model = model

        self.max_steps = max_steps
        self.client = ollama.Client(host=host)
        logger.info("Planner initialized using model '%s'", self.model)

    def decompose(self, goal: str) -> List[str]:
        """Break *goal* into an ordered list of subtask strings.

        Returns:
            A list of subtask strings (without numbering prefix).

        Example::

            steps = planner.decompose("Research NVDA and write an investor brief")
            # → ["Fetch NVDA price data", "Search for NVDA earnings news", ...]
        """
        prompt = f"Goal: {goal.strip()}"
        logger.info("Planner decomposing goal: %s", goal)

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

    def hierarchical_decompose(
        self,
        goal: str,
        max_tasks: int = 8,
        session_context: str = "",
    ) -> List[str]:
        """Decompose a long-horizon goal into session-sized, independently executable tasks.

        Unlike ``decompose()``, this method produces larger tasks each designed
        to fit within a single agent session (~25 turns). Each task is a
        meaningful, self-contained unit of work.

        Args:
            goal: The high-level long-horizon goal.
            max_tasks: Maximum number of tasks to produce (default 8).
            session_context: Optional context about the environment or constraints.

        Returns:
            Ordered list of session-sized task descriptions.

        Example::

            tasks = planner.hierarchical_decompose(
                "Research IndBank stock and write a full investment report"
            )
            # -> [
            #   "Fetch IndBank (INDUSINDBK.NS) current price, 52-week range, and key financials",
            #   "Search for IndBank news, analyst ratings, and recent developments",
            #   "Research IndBank's financial health: NPA ratio, ROE, loan book growth",
            #   "Write a comprehensive markdown investment report with buy/hold/sell recommendation",
            # ]
        """
        system = (
            "You are a strategic task planner for a long-horizon autonomous agent. "
            "Break the goal into a numbered list of SESSIONS — each session is one "
            "independent, self-contained task an AI agent can complete in ~25 tool calls. "
            "Each task must:\n"
            "  - Be independently runnable without the outputs of later tasks\n"
            "  - Produce a concrete, reusable output (data, file, summary)\n"
            "  - Be specific enough to execute without further clarification\n\n"
            "Output ONLY the numbered list. No headers, no explanations.\n"
            "Example:\n"
            "1. Fetch current price, 52-week high/low, and market cap for the target stock.\n"
            "2. Search for recent news, earnings reports, and analyst ratings.\n"
            "3. Research financial health metrics: NPA, ROE, revenue growth.\n"
            "4. Write a full investment report and save it to 'reports/stock_report.md'.\n"
        )
        prompt = f"Goal: {goal.strip()}"
        if session_context:
            prompt += f"\n\nContext: {session_context}"

        logger.info("Hierarchical planner decomposing: %s", goal[:80])
        response = self.client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            options={"temperature": 0.2, "num_ctx": 4096},
        )
        if hasattr(response, "message"):
            content = response.message.content or ""
        else:
            content = response.get("message", {}).get("content", "")

        tasks = self._parse_steps(content)
        logger.info("Hierarchical planner produced %d tasks.", len(tasks))
        return tasks[:max_tasks]
