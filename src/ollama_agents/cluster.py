"""Distributed Cluster Engine for Ollama Agents.

Enables multi-node distributed processing across local network laptops/PCs running Ollama.
Aggregates models across multiple nodes, balances task loads, and offloads heavy sub-agent
workloads to secondary machines seamlessly.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


@dataclass
class ClusterNode:
    """Represents a remote or local computer node running Ollama."""
    host_url: str  # e.g. "http://192.168.1.50:11434" or "http://localhost:11434"
    name: str = "LocalNode"
    is_active: bool = False
    installed_models: List[str] = field(default_factory=list)
    latency_ms: float = 0.0
    active_jobs: int = 0

    def ping_and_discover(self) -> bool:
        """Check node health and fetch installed Ollama models."""
        url = f"{self.host_url.rstrip('/')}/api/tags"
        start_time = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "OllamaAgentsCluster/0.6.0"})
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    models = []
                    raw_models = data.get("models", [])
                    for m in raw_models:
                        name = m.get("model", m.get("name")) if isinstance(m, dict) else str(m)
                        if name:
                            models.append(name)
                    self.installed_models = models
                    self.is_active = True
                    self.latency_ms = round((time.time() - start_time) * 1000.0, 1)
                    logger.info("ClusterNode '%s' (%s) active: %d models found (%.1fms)",
                                self.name, self.host_url, len(models), self.latency_ms)
                    return True
        except Exception as e:
            self.is_active = False
            self.installed_models = []
            logger.debug("ClusterNode '%s' (%s) unreachable: %s", self.name, self.host_url, e)
            return False
        return False


class DistributedClusterManager:
    """Manages a cluster of Ollama node instances across local network laptops."""

    def __init__(self, node_urls: Optional[List[str]] = None) -> None:
        self.nodes: Dict[str, ClusterNode] = {}
        # Default local node
        self.add_node("http://localhost:11434", name="PrimaryLaptop")

        if node_urls:
            for i, url in enumerate(node_urls, 1):
                self.add_node(url, name=f"SecondaryLaptop-{i}")

    def add_node(self, host_url: str, name: Optional[str] = None) -> ClusterNode:
        """Add a new laptop/node to the cluster."""
        clean_url = host_url.rstrip("/")
        if not clean_url.startswith(("http://", "https://")):
            clean_url = f"http://{clean_url}"
        if not clean_url.endswith(":11434") and not clean_url.count(":") > 1:
            clean_url = f"{clean_url}:11434"

        node_name = name or f"Node-{len(self.nodes) + 1}"
        node = ClusterNode(host_url=clean_url, name=node_name)
        node.ping_and_discover()
        self.nodes[clean_url] = node
        return node

    def refresh_cluster_status(self) -> Dict[str, Any]:
        """Ping all cluster nodes and aggregate active models."""
        active_count = 0
        all_models = set()

        for url, node in self.nodes.items():
            if node.ping_and_discover():
                active_count += 1
                all_models.update(node.installed_models)

        return {
            "total_nodes": len(self.nodes),
            "active_nodes": active_count,
            "aggregate_models": list(all_models),
            "nodes": [{
                "name": n.name,
                "url": n.host_url,
                "active": n.is_active,
                "latency_ms": n.latency_ms,
                "models_count": len(n.installed_models),
                "models": n.installed_models
            } for n in self.nodes.values()]
        }

    def select_best_node_for_model(self, model_name: str) -> Optional[ClusterNode]:
        """Find the optimal active node hosting *model_name* with the lowest active jobs/latency."""
        candidates = []
        for node in self.nodes.values():
            if node.is_active and model_name in node.installed_models:
                candidates.append(node)

        if not candidates:
            # Fallback: return any active node
            active_nodes = [n for n in self.nodes.values() if n.is_active]
            return active_nodes[0] if active_nodes else None

        # Sort candidates by active_jobs, then latency
        candidates.sort(key=lambda n: (n.active_jobs, n.latency_ms))
        return candidates[0]

    def run_distributed_goal(self, goal: str, max_tasks: int = 6) -> str:
        """Decompose *goal* and distribute subtask executions across all active cluster nodes/laptops."""
        from .planner import Planner
        from .agent import Agent
        from .model_selector import select_best_local_model
        from .tools import web_search, get_realtime_market_quote, run_python, write_file, read_file

        self.refresh_cluster_status()
        active_nodes = [n for n in self.nodes.values() if n.is_active]

        if not active_nodes:
            raise RuntimeError("No active Ollama cluster nodes available!")

        planner = Planner()
        tasks = planner.hierarchical_decompose(goal, max_tasks=max_tasks)
        logger.info("[Distributed Cluster] Decomposed goal into %d tasks across %d active laptops/nodes.",
                    len(tasks), len(active_nodes))

        def _worker(idx: int, task_desc: str):
            task_type = "coding" if any(w in task_desc.lower() for w in ["code", "python", "build"]) else "reasoning"
            model = select_best_local_model(task_type)
            node = self.select_best_node_for_model(model)

            if not node:
                node = active_nodes[0]

            node.active_jobs += 1
            try:
                logger.info("[Distributed Cluster] Task %d -> Node '%s' (%s) running model '%s'",
                            idx, node.name, node.host_url, model)
                agent = Agent(
                    name=f"ClusterWorker-{idx}",
                    role="Distributed Cluster Analyst",
                    model=model,
                    host=node.host_url,
                    tools=[web_search, get_realtime_market_quote, run_python, write_file, read_file],
                    max_turns=20
                )
                res = agent.run(task_desc)
                return idx, f"### Task {idx}: {task_desc}\n**Node**: `{node.name}` (`{node.host_url}`)\n**Model**: `{model}`\n\n{res}"
            finally:
                node.active_jobs -= 1

        results = {}
        with ThreadPoolExecutor(max_workers=len(active_nodes) * 2) as executor:
            futures = [executor.submit(_worker, idx, t) for idx, t in enumerate(tasks, 1)]
            for f in as_completed(futures):
                try:
                    idx, res = f.result()
                    results[idx] = res
                except Exception as e:
                    logger.error("Distributed worker task failed: %s", e)

        sorted_res = [results[i] for i in sorted(results.keys())]
        return f"# Distributed Multi-Laptop Execution Report\nActive Nodes: {len(active_nodes)}\n\n" + "\n\n---\n\n".join(sorted_res)


# Singleton cluster instance
cluster_manager = DistributedClusterManager()
