"""
CLI Interface for Ollama Agents — v0.6.0

Built with Typer and Rich for beautiful terminal interactions.
"""

import sys
import json
import typer
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.markdown import Markdown

from ollama_agents import Agent, GoalRegistry, MemoryStore

app = typer.Typer(
    name="ollama-agents",
    help="Level 4 Autonomous Agent CLI powered by local Ollama models",
    add_completion=False,
)
console = Console()

# ── 1. Run Single Task ────────────────────────────────────────────────────────
@app.command(name="run")
def run_task(
    prompt: str = typer.Argument(..., help="The task prompt for the agent to execute."),
    model: str = typer.Option("deepseek-r1:8b", "--model", "-m", help="Ollama model name."),
    max_turns: int = typer.Option(25, "--turns", "-t", help="Maximum turns for the execution loop."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed execution debug logs."),
):
    """Run a single autonomous task with the agent."""
    console.print(Panel(f"[bold cyan]Task:[/bold cyan] {prompt}\n[dim]Model: {model} | Max turns: {max_turns}[/dim]", title="Ollama Agent", border_style="cyan"))

    agent = Agent(model=model, max_turns=max_turns, verbose=verbose)
    
    with console.status("[bold green]Agent working on task...[/bold green]", spinner="dots"):
        result = agent.run(prompt)

    console.print("\n[bold green][SUCCESS] Task Completed[/bold green]\n")
    console.print(Panel(Markdown(result), title="Result", border_style="green"))


# ── 2. Goal Management ─────────────────────────────────────────────────────────
goal_app = typer.Typer(help="Manage long-horizon autonomous goals.")
app.add_typer(goal_app, name="goal")

@goal_app.command(name="create")
def create_goal(
    prompt: str = typer.Argument(..., help="The long-horizon goal description."),
    model: str = typer.Option("deepseek-r1:8b", "--model", "-m", help="Ollama model name."),
):
    """Create and decompose a new long-horizon goal."""
    console.print(f"[bold cyan]Decomposing Goal:[/bold cyan] {prompt}")
    registry = GoalRegistry()
    
    with console.status("[bold yellow]Decomposing goal into session tasks...[/bold yellow]", spinner="bouncingBar"):
        goal = registry.create_goal(prompt, model=model)

    console.print(f"\n[bold green][SUCCESS] Goal Created![/bold green] (ID: [bold gold1]{goal.goal_id}[/bold gold1])\n")
    
    table = Table(title="Goal Tasks", show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("Task Title", style="cyan")
    table.add_column("Status", style="yellow")
    
    for idx, t in enumerate(goal.tasks, 1):
        table.add_row(str(idx), t.title, t.status)
        
    console.print(table)
    console.print(f"\nTo execute the first task, run:\n  [bold white]ollama-agents goal run {goal.goal_id}[/bold white]")


@goal_app.command(name="list")
def list_goals():
    """List all stored long-horizon goals."""
    registry = GoalRegistry()
    goals = registry.list_goals()

    if not goals:
        console.print("[dim]No goals found. Create one with `ollama-agents goal create \"...\"`[/dim]")
        return

    table = Table(title="Autonomous Goals", show_header=True, header_style="bold cyan")
    table.add_column("Goal ID", style="gold1")
    table.add_column("Title", style="white")
    table.add_column("Progress", style="green")
    table.add_column("Tasks", style="dim")

    for g in goals:
        completed = sum(1 for t in g.tasks if t.status == "completed")
        total = len(g.tasks)
        pct = int((completed / total) * 100) if total else 0
        table.add_row(g.goal_id, g.title[:50], f"{pct}% ({completed}/{total})", str(total))

    console.print(table)


@goal_app.command(name="run")
def run_goal(
    goal_id: str = typer.Argument(..., help="Goal ID to execute next task for."),
    model: str = typer.Option("qwen2.5:3b", "--model", "-m", help="Ollama model override."),
):
    """Execute the next pending task for a goal."""
    registry = GoalRegistry()
    goal = registry.get_goal(goal_id)

    if not goal:
        console.print(f"[red]Goal '{goal_id}' not found.[/red]")
        raise typer.Exit(1)

    next_task = next((t for t in goal.tasks if t.status != "completed"), None)
    if not next_task:
        console.print(f"[bold green][SUCCESS] All tasks for goal '{goal.title}' are already complete![/bold green]")
        return

    console.print(Panel(f"[bold yellow]Goal:[/bold yellow] {goal.title}\n[bold cyan]Executing Task ({goal.progress_pct:.0f}% Done):[/bold cyan] {next_task.title}", border_style="yellow"))

    agent = Agent(model=model, max_turns=25)
    
    with console.status("[bold green]Executing task...[/bold green]", spinner="dots"):
        task_res, goal_status = agent.run_goal(goal_id=goal_id)

    console.print("\n[bold green][SUCCESS] Task Finished![/bold green]\n")
    console.print(Panel(Markdown(task_res), title="Task Result", border_style="green"))
    console.print(f"\n[bold yellow]Updated Goal Progress:[/bold yellow] {goal_status.progress_pct:.1f}% complete.")


@app.command(name="kill-all")
def kill_all_tasks():
    """Emergency Kill Switch: Terminate all running background processes and reset stuck task states."""
    console.print("[bold red]🛑 Activating Emergency Kill Switch...[/bold red]")
    registry = GoalRegistry()
    goals = registry.list_goals()
    killed_count = 0

    for goal in goals:
        for t in goal.tasks:
            if t.status == "in_progress":
                registry.fail_task(goal.id, t.id, reason="Stopped by Emergency Kill-All Switch")
                killed_count += 1

    from ollama_agents.server import ACTIVE_EXECUTIONS
    ACTIVE_EXECUTIONS.clear()

    console.print(Panel(f"[bold green][SUCCESS] Emergency Kill Switch executed cleanly.[/bold green]\n[dim]Reset {killed_count} stuck tasks & cleared process registry.[/dim]", title="Kill Switch Complete", border_style="red"))


# ── 3. Memory Inspector ───────────────────────────────────────────────────────
@app.command(name="reflections")
def show_reflections(
    limit: int = typer.Option(5, "--limit", "-l", help="Number of recent reflections to show."),
):
    """View self-improvement notes and reflections stored in agent memory."""
    mem = MemoryStore()
    reflections = mem.get_reflections(limit=limit)

    if not reflections:
        console.print("[dim]No reflections recorded yet. Run agent tasks to generate self-reflections.[/dim]")
        return

    console.print(Panel("[bold magenta]Self-Improvement Reflections[/bold magenta]", border_style="magenta"))
    for ref in reflections:
        key = ref.get("key", "Reflection")
        content = ref.get("content", "")
        console.print(Panel(Markdown(content), title=key, border_style="dim"))


# ── 4. Models Listing ─────────────────────────────────────────────────────────
@app.command(name="models")
def list_models():
    """List all available local Ollama models installed on this machine."""
    import ollama
    try:
        models_data = ollama.list()
        models_list = models_data.get("models", [])
        
        if not models_list:
            console.print("[dim]No Ollama models found installed on local machine.[/dim]")
            return

        table = Table(title="Installed Local Ollama Models", show_header=True, header_style="bold cyan")
        table.add_column("Model Name", style="bold white")
        table.add_column("Size", style="yellow")
        table.add_column("Modified", style="dim")

        for m in models_list:
            name = getattr(m, 'model', getattr(m, 'name', str(m)))
            if hasattr(m, 'size') and m.size:
                size_str = f"{m.size / (1024**3):.2f} GB"
            else:
                size_str = "-"
            mod_raw = getattr(m, 'modified_at', "")
            mod_str = str(mod_raw)[:10] if mod_raw else "-"
            table.add_row(name, size_str, mod_str)

        console.print(table)
    except Exception as e:
        console.print(f"[red]Error fetching Ollama models: {e}[/red]")


@app.command(name="search-hf")
def search_hf(
    query: str = typer.Argument(..., help="Search term for Hugging Face GGUF models (e.g. qwen, deepseek, mistral)."),
):
    """Search Hugging Face Hub for GGUF models and display Ollama pull tags."""
    from ollama_agents.model_selector import search_huggingface_models
    console.print(f"[bold cyan]Searching Hugging Face Hub GGUF models for:[/bold cyan] {query}")
    
    with console.status("[bold yellow]Querying Hugging Face API...[/bold yellow]", spinner="dots"):
        results = search_huggingface_models(query=query)

    if not results:
        console.print("[dim]No matching GGUF models found on Hugging Face.[/dim]")
        return

    table = Table(title="Hugging Face GGUF Models for Ollama", show_header=True, header_style="bold magenta")
    table.add_column("Model ID", style="cyan")
    table.add_column("Ollama Tag", style="bold green")
    table.add_column("Downloads", style="yellow")
    table.add_column("Likes", style="white")

    for item in results:
        table.add_row(item["id"], item["ollama_tag"], str(item["downloads"]), str(item["likes"]))

    console.print(table)
    console.print("\nTo add a model to your local Ollama list, run:\n  [bold white]ollama pull <Ollama Tag>[/bold white]")


# ── 5. Web Serve Command ─────────────────────────────────────────────────────
@app.command(name="serve")
def serve_web(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host address to bind."),
    port: int = typer.Option(8000, "--port", "-p", help="Port to listen on."),
):
    """Launch the Web Dashboard UI."""
    import uvicorn
    console.print(f"[bold green]Launching Ollama Agents Web UI at http://{host}:{port}[/bold green]")
    uvicorn.run("ollama_agents.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    app()
