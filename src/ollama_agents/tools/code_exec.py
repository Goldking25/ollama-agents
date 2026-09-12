"""
File system and code execution tools for Ollama Agents.
Allows agents to read files, write code files, list directories, and execute terminal commands.
"""

import os
import subprocess
from typing import Dict, Any

def write_code_file(filepath: str, content: str) -> str:
    """Write or overwrite a source code file or document on the local file system.

    Args:
        filepath: Relative or absolute path to the file (e.g., 'mobile_app/App.js', 'index.html').
        content: The code or file text to write.
    """
    try:
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote {len(content)} characters to '{filepath}'."
    except Exception as e:
        return f"Failed to write file '{filepath}': {str(e)}"

def read_code_file(filepath: str) -> str:
    """Read contents of a file from the local file system.

    Args:
        filepath: Path to the file.
    """
    try:
        if not os.path.exists(filepath):
            return f"Error: File '{filepath}' does not exist."
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Failed to read file '{filepath}': {str(e)}"

def run_terminal_command(command: str) -> str:
    """Run a terminal or shell command in the local environment (e.g., 'npx create-react-native-app', 'npm install', 'git status').

    Args:
        command: The shell command string to execute.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=os.getcwd(),
        )
        output = result.stdout.strip()
        errors = result.stderr.strip()
        res = []
        if output:
            res.append(f"STDOUT:\n{output[:1500]}")
        if errors:
            res.append(f"STDERR:\n{errors[:1500]}")
        return "\n".join(res) if res else "Command executed with no output."
    except subprocess.TimeoutExpired:
        return f"Command timed out after 120 seconds: {command}"
    except Exception as e:
        return f"Failed to execute command '{command}': {str(e)}"
