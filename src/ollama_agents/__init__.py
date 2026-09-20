"""Ollama Agents: Level 4 autonomous multi-agent orchestration — v0.5.0"""

from .agent import Agent
from .checkpoint import CheckpointManager, CheckpointState
from .critic import Critic, CriticResult
from .exceptions import AgentConfigError, MaxTurnsExceeded, OllamaAgentsError, ToolExecutionError
from .goal import Goal, GoalRegistry, GoalTask
from .memory import MemoryStore
from .cluster import DistributedClusterManager, cluster_manager
from .distributed_compute import GeneralDistributedComputeEngine, distributed_compute_engine
from .tool_synthesizer import ToolSynthesizer, tool_synthesizer
from .orchestrator import Workflow, Orchestrator
from .planner import Planner
from .tool import Tool
from .vector_memory import VectorMemory
from . import tools

__version__ = "0.6.0"
__all__ = [
    "Agent", "Tool", "Workflow", "Orchestrator", "Planner",
    "DistributedClusterManager", "cluster_manager",
    "GeneralDistributedComputeEngine", "distributed_compute_engine",
    "ToolSynthesizer", "tool_synthesizer",
    "MemoryStore", "VectorMemory",
    "Goal", "GoalTask", "GoalRegistry",
    "Critic", "CriticResult",
    "CheckpointManager", "CheckpointState",
    "OllamaAgentsError", "AgentConfigError", "MaxTurnsExceeded", "ToolExecutionError",
    "tools",
]