"""Ollama Agents: Level 4 autonomous multi-agent orchestration — v0.5.0"""

from .agent import Agent
from .checkpoint import CheckpointManager, CheckpointState
from .critic import Critic, CriticResult
from .exceptions import AgentConfigError, MaxTurnsExceeded, OllamaAgentsError, ToolExecutionError
from .goal import Goal, GoalRegistry, GoalTask
from .memory import MemoryStore
from .orchestrator import Workflow
from .planner import Planner
from .tool import Tool
from .vector_memory import VectorMemory
from . import tools

__version__ = "0.5.0"
__all__ = [
    "Agent", "Tool", "Workflow", "Planner",
    "MemoryStore", "VectorMemory",
    "Goal", "GoalTask", "GoalRegistry",
    "Critic", "CriticResult",
    "CheckpointManager", "CheckpointState",
    "OllamaAgentsError", "AgentConfigError", "MaxTurnsExceeded", "ToolExecutionError",
    "tools",
]