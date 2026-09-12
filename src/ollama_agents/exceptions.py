"""Custom exceptions for the ollama-agents framework."""


class OllamaAgentsError(Exception):
    """Base exception for all ollama-agents errors."""


class AgentConfigError(OllamaAgentsError):
    """Raised when an Agent is misconfigured (e.g. empty instructions)."""


class MaxTurnsExceeded(OllamaAgentsError):
    """Raised when an agent reaches its max_turns limit without producing a Final Answer.

    Attributes:
        turns: Number of turns consumed.
        last_output: The last content string the agent produced before hitting the limit.
    """

    def __init__(self, turns: int, last_output: str = "") -> None:
        self.turns = turns
        self.last_output = last_output
        super().__init__(
            f"Agent hit the {turns}-turn limit without completing the task. "
            f"Increase max_turns or refine the goal."
        )


class ToolExecutionError(OllamaAgentsError):
    """Raised when a tool fails after all retry attempts.

    Attributes:
        tool_name: Name of the tool that failed.
        cause: The underlying exception.
    """

    def __init__(self, tool_name: str, cause: Exception) -> None:
        self.tool_name = tool_name
        self.cause = cause
        super().__init__(
            f"Tool '{tool_name}' failed after all retries: "
            f"{type(cause).__name__}: {cause}"
        )
