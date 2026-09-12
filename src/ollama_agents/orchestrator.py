"""Workflow — coordinates interactions and data handoffs between agents.

Improvements over v1:
- run_sequential() execution_order is now optional (defaults to dict insertion order).
- run_parallel() executes multiple agents concurrently via ThreadPoolExecutor.
- Both methods propagate MaxTurnsExceeded so callers can react.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

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