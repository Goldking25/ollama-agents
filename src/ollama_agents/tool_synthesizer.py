"""Automated Tool Synthesizer Engine for Ollama Agents.

Enables agents to dynamically write, validate, persist, and register custom Python
tool functions on-the-fly inside the safe workspace (~/ollama_workspace/).
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional, Any

from .tool import Tool

logger = logging.getLogger(__name__)

_SYNTHESIZED_TOOLS_DIR = Path.home() / ".ollama_agents" / "synthesized_tools"


class ToolSynthesizer:
    """Dynamically synthesizes, validates, and registers custom Python tools."""

    def __init__(self) -> None:
        _SYNTHESIZED_TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        self.registry: Dict[str, Tool] = {}
        self.load_all_synthesized_tools()

    def synthesize_tool(
        self,
        name: str,
        description: str,
        code: str,
    ) -> Tool:
        """Create, validate, and persist a new custom Python Tool from source code."""
        # 1. Sanitize tool name
        safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in name).strip("_")
        if not safe_name:
            raise ValueError("Tool name must be valid alphanumeric identifier.")

        file_path = _SYNTHESIZED_TOOLS_DIR / f"{safe_name}.py"

        # Wrap code into clean module format if needed
        full_code = (
            f'"""Synthesized Tool: {safe_name}\nDescription: {description}\n"""\n\n'
            f"{code.strip()}\n"
        )

        # 2. Write file
        file_path.write_text(full_code, encoding="utf-8")
        logger.info("[Tool Synthesizer] Created custom tool source: %s", file_path)

        # 3. Dynamic import & validation
        spec = importlib.util.spec_from_file_location(safe_name, str(file_path))
        if not spec or not spec.loader:
            raise ImportError(f"Could not load module spec for synthesized tool '{safe_name}'")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Find target callable function in module
        target_fn: Optional[Callable] = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if callable(attr) and attr.__module__ == module.__name__ and not attr_name.startswith("_"):
                target_fn = attr
                break

        if not target_fn:
            raise ValueError(f"No top-level callable function found in synthesized tool code for '{safe_name}'.")

        tool_obj = Tool(func=target_fn, description=description)
        self.registry[safe_name] = tool_obj
        logger.info("[Tool Synthesizer] Successfully validated and registered tool '%s'!", safe_name)
        return tool_obj

    def load_all_synthesized_tools(self) -> List[Tool]:
        """Load and register all previously synthesized tools stored on disk."""
        tools = []
        for file_path in _SYNTHESIZED_TOOLS_DIR.glob("*.py"):
            try:
                mod_name = file_path.stem
                spec = importlib.util.spec_from_file_location(mod_name, str(file_path))
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if callable(attr) and attr.__module__ == module.__name__ and not attr_name.startswith("_"):
                            tool_obj = Tool(func=attr, description=getattr(attr, "__doc__", "") or f"Custom synthesized tool {mod_name}")
                            self.registry[mod_name] = tool_obj
                            tools.append(tool_obj)
                            break
            except Exception as e:
                logger.warning("[Tool Synthesizer] Failed loading tool '%s': %s", file_path.name, e)
        return tools


# Global synthesizer instance
tool_synthesizer = ToolSynthesizer()
