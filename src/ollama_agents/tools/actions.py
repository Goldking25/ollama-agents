"""Action tools — let the agent act on the world, not just read it.

Tools:
    read_url        Fetch and parse a webpage into clean text.
    run_python      Execute Python code in a sandboxed subprocess.
    write_file      Write text content to a file inside the safe workspace.
    read_file       Read a file from the safe workspace.
    run_terminal    Run a shell command inside the safe workspace.

Safe workspace root: ~/ollama_workspace/
All file and terminal operations are confined to this directory.
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Optional

# ─── Safe workspace ───────────────────────────────────────────────────────────
WORKSPACE_ROOT = Path.home() / "ollama_workspace"

# ─── Terminal blocklist (patterns that are never executed) ─────────────────────
_TERMINAL_BLOCKLIST = [
    "rm -rf",
    "rm -r /",
    "del /f",
    "del /s",
    "format",
    "shutdown",
    "reboot",
    "mkfs",
    "dd if=",
    ":(){:|:&};:",     # fork bomb
    "sudo rm",
    "chmod 777 /",
    "chown -R",
    "rd /s /q",
    "Remove-Item -Recurse -Force",
]


def _safe_path(filepath: str) -> Path:
    """Resolve *filepath* relative to WORKSPACE_ROOT and verify it stays inside."""
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    resolved = (WORKSPACE_ROOT / filepath).resolve()
    if not str(resolved).startswith(str(WORKSPACE_ROOT.resolve())):
        raise PermissionError(
            f"Path '{filepath}' escapes the safe workspace '{WORKSPACE_ROOT}'. "
            "Only paths inside ~/ollama_workspace/ are allowed."
        )
    return resolved


# ─── Tools ────────────────────────────────────────────────────────────────────

def read_url(url: str, max_chars: int = 8000) -> str:
    """Fetch a webpage and return its readable text content.

    Args:
        url: The full URL to fetch (must start with http:// or https://).
        max_chars: Maximum characters to return from the page (default 8000).
    """
    try:
        import httpx
        from bs4 import BeautifulSoup
    except ImportError:
        return "Error: httpx and beautifulsoup4 are required for read_url."

    if not url.startswith(("http://", "https://")):
        return f"Error: URL must start with http:// or https://. Got: {url}"

    try:
        response = httpx.get(url, timeout=15, follow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0 (compatible; ollama-agents/0.2)"})
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # Remove scripts, styles, nav, footer noise
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        # Collapse excessive blank lines
        lines = [l for l in text.splitlines() if l.strip()]
        clean = "\n".join(lines)
        return clean[:max_chars] + (f"\n\n[Truncated — {len(clean)} total chars]" if len(clean) > max_chars else "")
    except Exception as e:
        return f"Error fetching '{url}': {type(e).__name__}: {e}"


def run_python(code: str = None, timeout: int = 30, input: str = None) -> str:
    """Execute Python code in a subprocess and return its output.

    The code runs with the same Python interpreter as the agent but in a
    separate process, so crashes or infinite loops won't kill the agent.

    Args:
        code: Valid Python source code to execute.
        timeout: Maximum seconds to allow before killing the process (default 30).
        input: Fallback argument for the Python source code (used if 'code' is not provided).
    """
    if code is None and input is not None:
        code = input
    elif code is None and input is None:
        return "Error: You must provide the Python source code using the 'code' argument."

    try:
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(code)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout.strip()
        errors = result.stderr.strip()

        if result.returncode == 0:
            return output if output else "(Code ran successfully with no output)"
        else:
            return f"[Exit code {result.returncode}]\nSTDOUT: {output}\nSTDERR: {errors}"
    except subprocess.TimeoutExpired:
        return f"Error: Code execution timed out after {timeout} seconds."
    except Exception as e:
        return f"Error running Python code: {type(e).__name__}: {e}"


def write_file(filepath: str, content: str) -> str:
    """Write text content to a file inside the safe workspace (~/ollama_workspace/).

    Creates parent directories automatically. Overwrites if file already exists.

    Args:
        filepath: Relative path inside the workspace (e.g. 'reports/nvda.md').
        content: The text content to write to the file.
    """
    try:
        path = _safe_path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"Written {len(content.encode())} bytes to {path}"
    except PermissionError as e:
        return f"Permission denied: {e}"
    except Exception as e:
        return f"Error writing file '{filepath}': {type(e).__name__}: {e}"


def list_workspace_files(directory: str = "") -> str:
    """List all files and folders in the workspace directory (~/ollama_workspace/).

    Use this tool to find out what files, APKs, images, or documents exist in the workspace,
    or to find the exact filename and location of any generated artifact.

    Args:
        directory: Optional subdirectory inside workspace (default empty for workspace root).
    """
    try:
        clean_dir = directory.strip().lstrip("/\\") if directory else ""
        base = _safe_path(clean_dir) if clean_dir else WORKSPACE_ROOT
        if not base.exists():
            return f"Directory does not exist: {base}"
        items = []
        for p in base.rglob("*"):
            if any(part.startswith(".") for part in p.parts):
                continue
            rel = p.relative_to(WORKSPACE_ROOT)
            kind = "DIR" if p.is_dir() else f"FILE ({p.stat().st_size} bytes)"
            items.append(f"{rel} [{kind}]")
        if not items:
            return f"Workspace is currently empty at {WORKSPACE_ROOT}"
        return f"Files in workspace ({WORKSPACE_ROOT}):\n" + "\n".join(items[:60])
    except Exception as e:
        return f"Error listing workspace files: {e}"


def read_file(filepath: str, max_chars: int = 8000) -> str:
    """Read and return the content of a file from the safe workspace.

    Args:
        filepath: Relative path inside the workspace (e.g. 'src/MainActivity.java').
        max_chars: Maximum characters to return (default 8000).
    """
    try:
        path = _safe_path(filepath)
        if not path.exists():
            try:
                existing = [str(p.relative_to(WORKSPACE_ROOT)) for p in WORKSPACE_ROOT.rglob("*") if p.is_file()][:10]
                existing_str = ", ".join(existing) if existing else "None"
            except Exception:
                existing_str = "None"
            return f"[Error] File not found: '{path}'. Do not guess filenames! Files currently in workspace: [{existing_str}]. Call list_workspace_files() for full directory."
        content = path.read_text(encoding="utf-8")
        return content[:max_chars] + (
            f"\n\n[Truncated — {len(content)} total chars]" if len(content) > max_chars else ""
        )
    except PermissionError as e:
        return f"[Error] Permission denied: {e}"
    except Exception as e:
        return f"[Error] Error reading file '{filepath}': {type(e).__name__}: {e}"


def run_terminal(command: str, timeout: int = 30) -> str:
    """Run a shell command inside the safe workspace and return its output.

    The command runs with ~/ollama_workspace/ as the working directory.
    Dangerous commands (rm -rf, format, shutdown, etc.) are blocked.

    Args:
        command: The shell command to execute.
        timeout: Maximum seconds before the process is killed (default 30).
    """
    # Safety check
    lower_cmd = command.lower().strip()
    for blocked in _TERMINAL_BLOCKLIST:
        if blocked.lower() in lower_cmd:
            return (
                f"[Blocked] Command contains a forbidden pattern: '{blocked}'. "
                "This command was not executed."
            )

    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(WORKSPACE_ROOT),
        )
        output = result.stdout.strip()
        errors = result.stderr.strip()

        parts = []
        if output:
            parts.append(output)
        if errors:
            parts.append(f"STDERR: {errors}")
        if result.returncode != 0:
            parts.append(f"Exit code: {result.returncode}")

        return "\n".join(parts) if parts else "(Command completed with no output)"
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout} seconds."
    except Exception as e:
        return f"Error running command: {type(e).__name__}: {e}"


def delegate_subagent(role: str, task: str, model: str = "deepseek-r1:8b") -> str:
    """Delegate a specialized sub-task to a dedicated sub-agent powered by a chosen installed Ollama model.

    Use this tool to delegate work to lightweight specialized models installed locally (e.g.
    'huihui_ai/qwen2.5-abliterate:7b-instruct' for coding, 'deepseek-r1:8b' for reasoning, 'llama3.1:latest' for writing).

    Args:
        role: The role/specialization of the sub-agent (e.g. 'Coder', 'Researcher', 'Reviewer', 'MathSpecialist').
        task: Detailed instructions for what the sub-agent should do and return.
        model: Installed Ollama model identifier to power this sub-agent (default 'deepseek-r1:8b').
    """
    try:
        from ollama_agents.agent import Agent
        from ollama_agents.memory_manager import memory_manager
        from ollama_agents.tools import web_search, get_realtime_market_quote, write_file, read_file, run_terminal, run_python, test_ui_playwright

        from ollama_agents.cluster import cluster_manager
        best_node = cluster_manager.select_best_node_for_model(model)
        host_url = best_node.host_url if best_node else None
        node_name = best_node.name if best_node else "Local"

        with memory_manager.acquire_execution_slot(timeout=45.0):
            sub_agent = Agent(
                name=f"{role}SubAgent",
                role=role,
                instructions=f"You are a specialized sub-agent acting as a {role}. Execute the assigned sub-task thoroughly and concisely.",
                model=model,
                host=host_url,
                tools=[write_file, read_file, run_terminal, run_python, web_search, get_realtime_market_quote, test_ui_playwright],
                max_turns=15
            )
            result = sub_agent.run(task)
            return f"[SubAgent '{role}' ({model}) on Node '{node_name}' ({host_url or 'localhost'})]:\n{result}"
    except RuntimeError as re:
        return f"[Memory / Concurrency Safety Guard]: {re}"
    except Exception as e:
        return f"Error executing sub-agent delegation: {type(e).__name__}: {e}"


def rag_add_knowledge(text: str, source: str = "user_notes") -> str:
    """Store text content into the RAG vector embedding database for permanent semantic search.

    Args:
        text: The text snippet, documentation, or code content to embed.
        source: Name or label describing where this knowledge came from (e.g. 'indbank_report.md').
    """
    try:
        from ollama_agents.rag import VectorRAGStore
        rag = VectorRAGStore()
        success = rag.add_document(content=text, source=source)
        if success:
            return f"[RAG Memory] Successfully embedded and stored content from '{source}' into vector memory."
        return "[RAG Memory] Failed to embed content (empty or embedding model error)."
    except Exception as e:
        return f"Error saving to RAG memory: {type(e).__name__}: {e}"


def rag_search(query: str, top_k: int = 3) -> str:
    """Perform semantic vector search over stored RAG knowledge base.

    Args:
        query: The semantic search question or keywords.
        top_k: Number of most relevant document matches to return (default 3).
    """
    try:
        from ollama_agents.rag import VectorRAGStore
        rag = VectorRAGStore()
        matches = rag.query(query_text=query, top_k=top_k)
        if not matches:
            return "[RAG Search] No matching knowledge found in vector store."

        results = []
        for i, m in enumerate(matches, 1):
            results.append(f"{i}. [{m['source']}] (Score: {m['score']:.2f}):\n{m['content']}")
        return "\n\n".join(results)
    except Exception as e:
        return f"Error querying RAG memory: {type(e).__name__}: {e}"


def synthesize_new_tool(name: str, description: str, python_code: str) -> str:
    """Synthesize, validate, and register a new custom Python Tool function dynamically on-the-fly.

    Use this tool when a task requires custom computation, parsing, data transformation, or custom logic
    that is not provided by existing standard tools.

    Args:
        name: Name of the new tool (e.g. 'calculate_fibonacci', 'parse_custom_csv').
        description: Docstring / summary describing what the tool function does.
        python_code: Clean Python source code defining a top-level function that implements the tool.
    """
    try:
        from ollama_agents.tool_synthesizer import tool_synthesizer
        tool_obj = tool_synthesizer.synthesize_tool(name=name, description=description, code=python_code)
        return f"[Tool Synthesizer] Successfully compiled, validated, and registered custom tool '{tool_obj.name}'! Available for reuse across agents."
    except Exception as e:
        return f"[Tool Synthesizer Error] Failed to synthesize tool '{name}': {type(e).__name__}: {e}"

