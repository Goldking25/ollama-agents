"""
Long-Horizon Autonomous Agent Demo — ollama-agents v0.5.0

Goal: Research IndBank (IndusInd Bank) stock in the Indian market across
      multiple sessions and determine if it's a good investment.

This demo creates a multi-session goal that runs ONE task per execution:
  Session 1: Fetch current price, 52-week range, and key financial metrics
  Session 2: Search for recent news, analyst ratings, and developments
  Session 3: Research financial health (NPA, ROE, loan book growth)
  Session 4: Write complete investment report with buy/hold/sell recommendation

Run this script repeatedly — each run completes one session and advances the goal.
Progress is shown at startup. The goal completes after all tasks are done.

New L5 features demonstrated:
  Goal Registry    — persistent multi-session goal with progress tracking
  Context compression — history summarised when > 30 messages (infinite horizon)
  Hierarchical planning — goal decomposed into session-sized tasks
  run_goal()       — one session, one task, resumable forever
"""

import logging
from pathlib import Path

from ollama_agents import (
    Agent, GoalRegistry, MaxTurnsExceeded, MemoryStore, Planner,
)
from ollama_agents.tools import (
    get_realtime_market_quote, web_search, read_url, run_python,
    write_file, read_file,
)

try:
    from ollama_agents import VectorMemory
    _vmem = VectorMemory(agent_name="MarketScout")
    VECTOR_MEMORY_AVAILABLE = _vmem.available
except Exception:
    _vmem = None
    VECTOR_MEMORY_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)

# ─── Goal identity ────────────────────────────────────────────────────────────
GOAL_ID = "indbank-investment-research"
GOAL_DESCRIPTION = (
    "Research IndBank (IndusInd Bank, ticker: INDUSINDBK.NS) stock in the Indian "
    "market across multiple sessions. Collect price data, news, financial health "
    "metrics, and write a final markdown report recommending buy, hold, or sell."
)


def main() -> None:
    print("=" * 65)
    print("  Long-Horizon Autonomous Agent  v0.5.0")
    print("  Goal: IndBank Investment Research")
    print("=" * 65)

    registry = GoalRegistry()

    # ── Create goal on first run, load on subsequent runs ─────────────
    if not registry.exists(GOAL_ID):
        print("\n[New Goal] Decomposing into session-sized tasks...")
        planner = Planner(model="llama3.1")
        tasks = planner.hierarchical_decompose(
            goal=GOAL_DESCRIPTION,
            max_tasks=6,
            session_context=(
                "Use ticker INDUSINDBK.NS for yfinance. "
                "Indian market data. Save final report to 'reports/indbank_report.md'."
            ),
        )

        if not tasks:
            # Fallback if planner returns nothing
            tasks = [
                "Fetch IndusInd Bank (INDUSINDBK.NS) current price, 52-week high/low, "
                "market cap, P/E ratio, and EPS using the market data tool.",
                "Search for recent IndusInd Bank news, analyst ratings, quarterly results, "
                "and any major developments in the last 30 days.",
                "Research IndusInd Bank's financial health: NPA ratio, ROE, net interest "
                "margin, and loan book growth. Use web_search and read_url to find data.",
                "Write a comprehensive markdown investment report covering price analysis, "
                "news sentiment, financial health, risks, and a buy/hold/sell recommendation. "
                "Save to 'reports/indbank_report.md' using write_file.",
            ]

        goal = registry.create(
            goal_id=GOAL_ID,
            description=GOAL_DESCRIPTION,
            task_descriptions=tasks,
            agent_name="MarketScout",
        )
        print(f"  Created goal with {len(tasks)} tasks:")
        for i, t in enumerate(tasks, 1):
            print(f"    {i}. {t[:80]}...")
    else:
        goal = registry.load(GOAL_ID)
        print(f"\n[Resuming Goal] Progress: {goal.progress_pct:.0f}% "
              f"({len(goal.completed_tasks)}/{len(goal.tasks)} tasks done)")

    # ── Check if already complete ──────────────────────────────────────
    if goal.status == "completed":
        print("\n[DONE] This goal is already fully completed!")
        report = Path.home() / "ollama_workspace" / "reports" / "indbank_report.md"
        if report.exists():
            print(f"  Report: {report}")
        _show_summary(registry, GOAL_ID)
        return

    # ── Show current plan state ────────────────────────────────────────
    print(f"\n{goal.summary()}\n")

    # ── Build the agent ────────────────────────────────────────────────
    scout_memory = MemoryStore(
        agent_name="MarketScout",
        vector_memory=_vmem if VECTOR_MEMORY_AVAILABLE else None,
    )

    scout = Agent(
        name="MarketScout",
        role="Indian Market Financial Researcher and Analyst",
        instructions=(
            "You are researching IndusInd Bank (INDUSINDBK.NS) for an investment decision. "
            "Tools available:\n"
            "- get_realtime_market_quote(ticker): fetch stock price data\n"
            "- web_search(query): search for news and analysis\n"
            "- read_url(url): read full content from a URL\n"
            "- run_python(code): execute Python for calculations\n"
            "- write_file(filepath, content): save reports to disk\n"
            "- read_file(filepath): verify saved files\n\n"
            "For each task:\n"
            "1. Use the appropriate tools to gather information\n"
            "2. When done, write 'Final Answer:' followed by a clear summary of findings"
        ),
        model="llama3.1",
        tools=[get_realtime_market_quote, web_search, read_url, run_python, write_file, read_file],
        temperature=0.0,
        num_ctx=8192,
        memory=scout_memory,
        max_turns=25,
        compress_after=30,        # compress history at 30 messages
        confirm_actions=["write_file"],
        planner=Planner(model="llama3.1"),
        enable_checkpointing=True,
        enable_reflection=True,
    )

    # ── Run next task in this session ──────────────────────────────────
    output = scout.run_goal(goal_id=GOAL_ID, registry=registry)

    # ── Show final result ──────────────────────────────────────────────
    if output and output not in ("Goal already completed.", "Goal already completed — no pending tasks."):
        print("\n" + "─" * 65)
        print("  Session Output:")
        print("─" * 65)
        print(output[:1000])

    # ── Show updated progress ──────────────────────────────────────────
    _show_summary(registry, GOAL_ID)

    # ── Vector memory ──────────────────────────────────────────────────
    if VECTOR_MEMORY_AVAILABLE:
        print(f"\n[Vector Memory] {_vmem.count()} embeddings")

    scout_memory.close()

    # ── Prompt for next session ────────────────────────────────────────
    updated = registry.load(GOAL_ID)
    if updated and updated.status != "completed":
        next_t = updated.next_task
        print("\n" + "=" * 65)
        print("  Run this script again to continue the next session:")
        if next_t:
            print(f"  Next task: {next_t.description[:80]}")
        print("=" * 65)


def _show_summary(registry: GoalRegistry, goal_id: str) -> None:
    goal = registry.load(goal_id)
    if not goal:
        return
    print(f"\n{'─'*65}")
    print(f"  Goal Summary: {goal.id}")
    print(f"  Status: {goal.status}  |  Sessions run: {goal.session_count}")
    print(f"  Progress: {goal.progress_pct:.0f}% ({len(goal.completed_tasks)}/{len(goal.tasks)} tasks)")
    for t in goal.tasks:
        icon = {"completed": "[x]", "in_progress": "[>]",
                "failed": "[!]", "pending": "[ ]"}.get(t.status, "[ ]")
        print(f"    {icon} {t.description[:65]}")
    print(f"{'─'*65}")


if __name__ == "__main__":
    main()