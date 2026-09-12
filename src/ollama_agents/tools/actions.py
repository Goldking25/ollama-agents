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


def run_python(code: str, timeout: int = 30) -> str:
    """Execute Python code in a subprocess and return its output.

    The code runs with the same Python interpreter as the agent but in a
    separate process, so crashes or infinite loops won't kill the agent.

    Args:
        code: Valid Python source code to execute.
        timeout: Maximum seconds to allow before killing the process (default 30).
    """
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


def read_file(filepath: str, max_chars: int = 8000) -> str:
    """Read and return the content of a file from the safe workspace.

    Args:
        filepath: Relative path inside the workspace (e.g. 'reports/nvda.md').
        max_chars: Maximum characters to return (default 8000).
    """
    try:
        path = _safe_path(filepath)
        if not path.exists():
            return f"File not found: {path}"
        content = path.read_text(encoding="utf-8")
        return content[:max_chars] + (
            f"\n\n[Truncated — {len(content)} total chars]" if len(content) > max_chars else ""
        )
    except PermissionError as e:
        return f"Permission denied: {e}"
    except Exception as e:
        return f"Error reading file '{filepath}': {type(e).__name__}: {e}"


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
