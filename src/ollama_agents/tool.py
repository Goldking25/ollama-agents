"""Tool — wraps a Python callable into an Ollama-compatible function tool.

Improvements over v1:
- Docstring ``Args:`` section is parsed to produce meaningful per-parameter descriptions.
- ``execute()`` supports retry with exponential back-off.
- On final failure raises ``ToolExecutionError`` instead of returning an error string.
"""

import inspect
import json
import logging
import re
import time
from typing import Any, Callable, Dict, get_args, get_origin, List, Optional

from .exceptions import ToolExecutionError

logger = logging.getLogger(__name__)


class Tool:
    """Wraps a Python callable into an Ollama-compatible function tool."""

    TYPE_MAP: Dict[Any, str] = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }

    def __init__(self, func: Callable, description: Optional[str] = None) -> None:
        self.func = func
        self.name = func.__name__
        raw_doc = inspect.getdoc(func) or ""
        self.description = description or (raw_doc.split("\n")[0].strip() or "No description provided.")
        self._param_docs = self._parse_param_docs(raw_doc)
        self.schema = self._build_schema()

    # ------------------------------------------------------------------
    # Type mapping
    # ------------------------------------------------------------------

    def _map_type(self, py_type: Any) -> str:
        """Map a Python type annotation to a JSON Schema type string."""
        origin = get_origin(py_type)
        if origin is not None:
            # Handle Optional[T] / Union[T, None]
            args = [a for a in get_args(py_type) if a is not type(None)]
            if args:
                return self.TYPE_MAP.get(args[0], "string")
        return self.TYPE_MAP.get(py_type, "string")

    # ------------------------------------------------------------------
    # Docstring parser for per-parameter descriptions
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_param_docs(docstring: str) -> Dict[str, str]:
        """Extract parameter descriptions from a Google-style docstring ``Args:`` block.

        Returns a mapping of {param_name: description}.
        """
        param_docs: Dict[str, str] = {}
        in_args = False
        current_param: Optional[str] = None
        current_lines: List[str] = []

        for line in docstring.splitlines():
            stripped = line.strip()

            if stripped.lower() in ("args:", "arguments:", "parameters:"):
                in_args = True
                continue

            # Stop at the next top-level section
            if in_args and stripped and not line.startswith(" ") and stripped.endswith(":"):
                break

            if in_args:
                # New parameter entry — "param_name: description" or "param_name (type): description"
                match = re.match(r"^(\w+)(?:\s*\(.*?\))?\s*:\s*(.*)", stripped)
                if match and line.startswith(("    ", "\t")):
                    if current_param:
                        param_docs[current_param] = " ".join(current_lines).strip()
                    current_param = match.group(1)
                    current_lines = [match.group(2)]
                elif current_param and stripped:
                    # Continuation line
                    current_lines.append(stripped)

        if current_param:
            param_docs[current_param] = " ".join(current_lines).strip()

        return param_docs

    # ------------------------------------------------------------------
    # Schema builder
    # ------------------------------------------------------------------

    def _build_schema(self) -> Dict[str, Any]:
        sig = inspect.signature(self.func)
        properties: Dict[str, Any] = {}
        required: List[str] = []

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            annotation = param.annotation
            param_type = self._map_type(
                annotation if annotation != inspect.Parameter.empty else str
            )
            description = self._param_docs.get(
                param_name, f"The {param_name.replace('_', ' ')} value."
            )
            properties[param_name] = {
                "type": param_type,
                "description": description,
            }

            if param.default == inspect.Parameter.empty:
                required.append(param_name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    # ------------------------------------------------------------------
    # Execution with retry
    # ------------------------------------------------------------------

    def execute(self, retries: int = 2, backoff: float = 0.5, **kwargs: Any) -> str:
        """Execute the tool safely, returning serialised JSON or a plain string.

        Args:
            retries: Number of retry attempts on failure (default 2).
            backoff: Base seconds to wait between retries (doubles each attempt).
            **kwargs: Arguments forwarded to the wrapped function.

        Raises:
            ToolExecutionError: When all retry attempts are exhausted.
        """
        last_exc: Exception = RuntimeError("Unknown error")
        delay = backoff

        for attempt in range(retries + 1):
            try:
                result = self.func(**kwargs)
                output = json.dumps(result) if not isinstance(result, str) else result
                if attempt > 0:
                    logger.info("Tool '%s' succeeded on attempt %d.", self.name, attempt + 1)
                return output
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Tool '%s' failed (attempt %d/%d): %s: %s",
                    self.name, attempt + 1, retries + 1, type(exc).__name__, exc,
                )
                if attempt < retries:
                    time.sleep(delay)
                    delay *= 2

        raise ToolExecutionError(self.name, last_exc)