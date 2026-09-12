"""Critic agent — reviews another agent's output and provides structured feedback.

The Critic acts as a quality gate before a Final Answer is returned.
If the output is lacking, it returns specific feedback so the main agent
can revise and resubmit. This loop closes the self-correction gap.

Usage::

    critic = Critic(model="deepseek-r1")
    result = critic.review(
        task="Summarise NVDA earnings",
        output="NVDA did well.",
    )
    if not result.approved:
        print(result.feedback)   # "Missing EPS figure, price change, and sources."
        print(result.revised)    # Critic's own improved version (if it wrote one)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import ollama

logger = logging.getLogger(__name__)

_CRITIC_SYSTEM = """\
You are a rigorous quality reviewer for AI-generated outputs. Your job is to \
evaluate whether a given output fully and accurately answers the task.

Respond in this EXACT format (no extra text outside these fields):

APPROVED: <yes or no>
SCORE: <0.0 to 1.0>
FEEDBACK: <one paragraph of specific, actionable feedback. If approved, write "Looks good.">
REVISED: <if APPROVED is no, write an improved version of the output here. Otherwise write "N/A">

Be strict. Approve only if the output is complete, accurate, and well-structured.\
"""


@dataclass
class CriticResult:
    """Structured result from a Critic review pass.

    Attributes:
        approved: Whether the output meets quality standards.
        score: Quality score from 0.0 (terrible) to 1.0 (perfect).
        feedback: Specific, actionable improvement notes.
        revised: Improved output written by the Critic (only if approved=False).
        raw: Raw LLM response text for debugging.
    """
    approved: bool
    score: float
    feedback: str
    revised: str = ""
    raw: str = ""


class Critic:
    """Reviews agent outputs and returns structured approval/feedback/revision.

    Args:
        model: Ollama model to use for critique (reasoning model recommended).
        host: Optional Ollama host URL.
        threshold: Minimum score (0.0–1.0) to count as approved (default 0.7).
    """

    def __init__(
        self,
        model: str = "deepseek-r1",
        host: Optional[str] = None,
        threshold: float = 0.7,
    ) -> None:
        self.model = model
        self.threshold = threshold
        self.client = ollama.Client(host=host)

    def review(self, task: str, output: str) -> CriticResult:
        """Review *output* against *task* and return a structured CriticResult.

        Args:
            task: The original task or goal the agent was trying to accomplish.
            output: The agent's produced output to evaluate.

        Returns:
            A :class:`CriticResult` with approval status, score, feedback, and
            optionally a revised version.
        """
        prompt = (
            f"TASK:\n{task.strip()}\n\n"
            f"OUTPUT TO REVIEW:\n{output.strip()}"
        )
        logger.info("Critic reviewing output for task: %s...", task[:60])

        response = self.client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": _CRITIC_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            options={"temperature": 0.1, "num_ctx": 8192},
        )

        if hasattr(response, "message"):
            raw = response.message.content or ""
        else:
            raw = response.get("message", {}).get("content", "")

        result = self._parse(raw)
        logger.info(
            "Critic result: approved=%s score=%.2f", result.approved, result.score
        )
        return result

    def _parse(self, raw: str) -> CriticResult:
        """Parse the structured critic response into a CriticResult."""
        def extract(label: str) -> str:
            match = re.search(rf"^{label}:\s*(.+?)(?=\n[A-Z]+:|$)", raw, re.IGNORECASE | re.MULTILINE | re.DOTALL)
            return match.group(1).strip() if match else ""

        approved_str = extract("APPROVED").lower()
        approved = approved_str.startswith("yes")

        score_str = extract("SCORE")
        try:
            score = float(score_str)
        except (ValueError, TypeError):
            score = 1.0 if approved else 0.5

        # Also enforce threshold
        if score < self.threshold:
            approved = False

        feedback = extract("FEEDBACK") or "No feedback provided."
        revised = extract("REVISED") if not approved else ""
        if revised.lower() in ("n/a", "na", ""):
            revised = ""

        return CriticResult(
            approved=approved,
            score=score,
            feedback=feedback,
            revised=revised,
            raw=raw,
        )
