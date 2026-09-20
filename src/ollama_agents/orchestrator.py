"""Workflow — coordinates interactions and data handoffs between agents.

Improvements over v1:
- run_sequential() execution_order is now optional (defaults to dict insertion order).
- run_parallel() executes multiple agents concurrently via ThreadPoolExecutor.
- Both methods propagate MaxTurnsExceeded so callers can react.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

from .agent import Agent
from .exceptions import MaxTurnsExceeded

logger = logging.getLogger(__name__)


class Workflow:
    """Coordinates interactions and data handoffs between agents.

    Args:
        agents: Mapping of agent name → Agent instance. Insertion order determines
                the default sequential execution order.
    """

    def __init__(self, agents: Dict[str, Agent]) -> None:
        self.agents = agents

    # ------------------------------------------------------------------
    # Sequential pipeline
    # ------------------------------------------------------------------

    def run_sequential(
        self,
        task: str,
        execution_order: Optional[List[str]] = None,
    ) -> str:
        """Run a task sequentially across agents, passing each output as the next input.

        Args:
            task: The initial task prompt.
            execution_order: Names of agents to run, in order. Defaults to the
                             insertion order of the ``agents`` dict.

        Returns:
            The final agent's output string.

        Raises:
            KeyError: If an agent name in *execution_order* is not registered.
            MaxTurnsExceeded: If any agent in the pipeline hits its turn limit.
        """
        order = execution_order or list(self.agents.keys())
        output = task

        for agent_name in order:
            if agent_name not in self.agents:
                raise KeyError(
                    f"Agent '{agent_name}' not registered. "
                    f"Available: {list(self.agents.keys())}"
                )
            agent = self.agents[agent_name]
            logger.info("Workflow: running agent '%s'.", agent_name)
            output = agent.run(output)

        return output

    # ------------------------------------------------------------------
    # Parallel execution
    # ------------------------------------------------------------------

    def run_parallel(
        self,
        task: str,
        agent_names: Optional[List[str]] = None,
        max_workers: Optional[int] = None,
    ) -> Dict[str, str]:
        """Run multiple agents on the *same* task concurrently.

        All agents receive the same *task* string and produce independent outputs.
        Useful for running multiple scout agents in parallel before aggregation.

        Args:
            task: The task prompt sent to every agent.
            agent_names: Subset of agents to run. Defaults to all registered agents.
            max_workers: Thread pool size. Defaults to the number of agents.

        Returns:
            Dict mapping agent name → output string (or error description on failure).
        """
        names = agent_names or list(self.agents.keys())
        workers = max_workers or len(names)
        results: Dict[str, str] = {}

        logger.info("Workflow: running %d agents in parallel: %s", len(names), names)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_name = {
                executor.submit(self.agents[name].run, task): name
                for name in names
                if name in self.agents
            }
            for future in as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    results[name] = future.result()
                except MaxTurnsExceeded as e:
                    logger.warning("Agent '%s' hit turn limit: %s", name, e)
                    results[name] = e.last_output or f"[MaxTurnsExceeded after {e.turns} turns]"
                except Exception as e:
                    logger.error("Agent '%s' raised an unexpected error: %s", name, e)
                    results[name] = f"[Error] {type(e).__name__}: {e}"

        return results


class Orchestrator:
    """Smart Multi-Agent Orchestrator.

    Decomposes high-level goals into subtasks, classifies each subtask by capability,
    dynamically routes each task to the optimal local Ollama worker model, and enforces
    a final Reviewer Model quality gate before calling the execution complete.
    """

    def __init__(self, default_model: Optional[str] = None, reviewer_model: Optional[str] = None) -> None:
        from .model_selector import select_best_local_model
        self.default_model = default_model
        self.reviewer_model = reviewer_model or select_best_local_model(task_type="reasoning")

    def classify_task_type(self, task_desc: str) -> str:
        """Classify a task into capability category: 'coding', 'reasoning', 'vision', or 'general'."""
        desc_lower = task_desc.lower()
        if any(w in desc_lower for w in ["code", "python", "script", "function", "debug", "fix", "program", "build"]):
            return "coding"
        elif any(w in desc_lower for w in ["reason", "analyze", "evaluate", "plan", "research", "compare", "report"]):
            return "reasoning"
        elif any(w in desc_lower for w in ["image", "vision", "screenshot", "diagram", "draw"]):
            return "vision"
        return "general"

    def review_output(self, task: str, output: str) -> Tuple[bool, str, float]:
        """Run Reviewer Model (Critic) pass on output before marking done."""
        from .critic import Critic
        critic = Critic(model=self.reviewer_model)
        review_result = critic.review(task=task, output=output)
        
        final_text = output
        if not review_result.approved and review_result.revised:
            logger.info("Reviewer Model provided revised output for task.")
            final_text = review_result.revised

        return review_result.approved, final_text, review_result.score

    def run_goal_with_model_routing(self, goal: str, max_tasks: int = 6) -> str:
        """Decompose *goal*, execute subtasks with specialized worker models, and review with Reviewer model."""
        from .planner import Planner
        from .model_selector import select_best_local_model
        from .tools import web_search, get_realtime_market_quote, run_python, write_file, read_file, synthesize_new_tool

        planner = Planner(model=self.default_model)
        tasks = planner.hierarchical_decompose(goal, max_tasks=max_tasks)

        logger.info("Orchestrator: Goal decomposed into %d tasks.", len(tasks))
        task_results = []

        for idx, task_desc in enumerate(tasks, 1):
            task_type = self.classify_task_type(task_desc)
            best_model = select_best_local_model(task_type=task_type, preferred=self.default_model)

            # Ensure skill file exists for this specific subtask & model before starting
            from .skills import SkillRegistry
            skill_reg = SkillRegistry()
            task_skill = skill_reg.ensure_skill_for_goal(task_desc, model=best_model)

            logger.info("Orchestrator: Routing Task %d to worker model '%s' (Skill: '%s', category: %s)", 
                        idx, best_model, task_skill.name, task_type)

            worker = Agent(
                name=f"Worker-{task_type.capitalize()}",
                role=f"Specialized {task_type.capitalize()} Analyst",
                instructions=f"Skill Blueprint [{task_skill.name} v{task_skill.version}]: {task_skill.instructions}",
                model=best_model,
                tools=[web_search, get_realtime_market_quote, run_python, write_file, read_file, synthesize_new_tool],
                max_turns=25,
            )

            raw_out = worker.run(task_desc)

            # Reviewer Quality Gate Pass
            logger.info("Orchestrator: Reviewing Task %d output with Reviewer Model '%s'...", idx, self.reviewer_model)
            approved, reviewed_out, score = self.review_output(task=task_desc, output=raw_out)
            status_label = f"Approved (Score: {score:.2f})" if approved else f"Revised by Reviewer (Score: {score:.2f})"

            task_results.append(
                f"### Task {idx}: {task_desc}\n"
                f"**Worker Model**: `{best_model}` (`{task_type}`)\n"
                f"**Reviewer Quality Gate**: `{self.reviewer_model}` - **{status_label}**\n\n"
                f"{reviewed_out}"
            )

        combined_summary = "\n\n---\n\n".join(task_results)

        # Final Overall Reviewer Synthesis
        logger.info("Orchestrator: Conducting final overall synthesis review with Reviewer Model '%s'...", self.reviewer_model)
        _, overall_review, overall_score = self.review_output(task=goal, output=combined_summary)

        return (
            f"# Goal Execution Report\n"
            f"**Goal**: {goal}\n"
            f"**Reviewer Model Quality Rating**: `{self.reviewer_model}` ({overall_score:.2f}/1.00)\n\n"
            f"## Final Reviewer Summary & Verification\n{overall_review}\n\n"
            f"---\n\n"
            f"## Task Execution Details\n"
            f"{combined_summary}"
        )

    def run_goal_parallel(self, goal: str, max_workers: int = 3, max_tasks: int = 6) -> str:
        """Decompose *goal* into subtasks and execute subtasks concurrently across worker threads with Memory Safety guards."""
        from .planner import Planner
        from .model_selector import select_best_local_model
        from .memory_manager import memory_manager
        from .tools import web_search, get_realtime_market_quote, run_python, write_file, read_file
        from concurrent.futures import ThreadPoolExecutor, as_completed

        planner = Planner(model=self.default_model)
        tasks = planner.hierarchical_decompose(goal, max_tasks=max_tasks)

        logger.info("Orchestrator: Executing %d tasks in PARALLEL mode (Max Workers: %d)...", len(tasks), max_workers)
        
        def _execute_subtask(idx: int, task_desc: str):
            with memory_manager.acquire_execution_slot(timeout=60.0):
                task_type = self.classify_task_type(task_desc)
                best_model = select_best_local_model(task_type=task_type, preferred=self.default_model)

                from .skills import SkillRegistry
                skill_reg = SkillRegistry()
                task_skill = skill_reg.ensure_skill_for_goal(task_desc, model=best_model)

                logger.info("Parallel Worker %d: Running task on '%s' (Skill: '%s')", idx, best_model, task_skill.name)

                worker = Agent(
                    name=f"ParallelWorker-{idx}",
                    role=f"Specialized {task_type.capitalize()} Analyst",
                    instructions=f"Skill Blueprint [{task_skill.name} v{task_skill.version}]: {task_skill.instructions}",
                    model=best_model,
                    tools=[web_search, get_realtime_market_quote, run_python, write_file, read_file],
                    max_turns=25,
                )

                raw_out = worker.run(task_desc)
                approved, reviewed_out, score = self.review_output(task=task_desc, output=raw_out)
                status_label = f"Approved (Score: {score:.2f})" if approved else f"Revised by Reviewer (Score: {score:.2f})"

                return idx, (
                    f"### Task {idx}: {task_desc}\n"
                    f"**Worker Model**: `{best_model}` (`{task_type}`)\n"
                    f"**Reviewer Quality Gate**: `{self.reviewer_model}` - **{status_label}**\n\n"
                    f"{reviewed_out}"
                )

        results_dict = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_execute_subtask, idx, t_desc) for idx, t_desc in enumerate(tasks, 1)]
            for future in as_completed(futures):
                try:
                    idx, res_text = future.result()
                    results_dict[idx] = res_text
                except Exception as e:
                    logger.error("Parallel task execution error: %s", e)

        # Sort tasks by original order
        sorted_results = [results_dict[i] for i in sorted(results_dict.keys())]
        combined_summary = "\n\n---\n\n".join(sorted_results)

        # Final Reviewer Pass
        logger.info("Orchestrator: Conducting overall synthesis review for parallel execution...")
        _, overall_review, overall_score = self.review_output(task=goal, output=combined_summary)

        return (
            f"# Parallel Goal Execution Report\n"
            f"**Goal**: {goal}\n"
            f"**Execution Mode**: Parallel Multi-Agent (Workers: {max_workers})\n"
            f"**Reviewer Model Quality Rating**: `{self.reviewer_model}` ({overall_score:.2f}/1.00)\n\n"
            f"## Final Reviewer Summary & Verification\n{overall_review}\n\n"
            f"---\n\n"
            f"## Parallel Task Execution Details\n"
            f"{combined_summary}"
        )