"""General Distributed Compute Client Engine for Ollama Agents.

Manages remote general computation tasks (Python execution, shell commands, build jobs)
across secondary compute nodes (Port 9000) in the local network cluster.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


class ComputeNodeClient:
    """Client connection to a remote General Compute Worker Node (Port 9000)."""

    def __init__(self, host_url: str, name: str = "ComputeNode") -> None:
        clean_url = host_url.rstrip("/")
        if not clean_url.startswith(("http://", "https://")):
            clean_url = f"http://{clean_url}"
        if not clean_url.endswith(":9000") and ":" not in clean_url[7:]:
            clean_url = f"{clean_url}:9000"

        self.host_url = clean_url
        self.name = name
        self.is_active = False
        self.stats: Dict[str, Any] = {}

    def ping(self) -> bool:
        """Ping worker node health endpoint."""
        url = f"{self.host_url}/api/worker/health"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "OllamaAgentsComputeClient/0.6.0"})
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status == 200:
                    self.stats = json.loads(resp.read().decode("utf-8"))
                    self.is_active = True
                    return True
        except Exception as e:
            self.is_active = False
            logger.debug("ComputeNode '%s' (%s) offline: %s", self.name, self.host_url, e)
            return False
        return False

    def run_python_remote(self, code: str, timeout: int = 45) -> Dict[str, Any]:
        """Execute Python code on remote compute node."""
        url = f"{self.host_url}/api/worker/python"
        payload = json.dumps({"code": code, "timeout": timeout}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout + 5) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return {"status": "error", "message": f"Failed remote Python execution on '{self.name}': {e}"}

    def run_terminal_remote(self, command: str, timeout: int = 60) -> Dict[str, Any]:
        """Execute a shell command on remote compute node."""
        url = f"{self.host_url}/api/worker/terminal"
        payload = json.dumps({"command": command, "timeout": timeout}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout + 5) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return {"status": "error", "message": f"Failed remote terminal execution on '{self.name}': {e}"}


class GeneralDistributedComputeEngine:
    """Manages multi-node general compute workloads across local network laptops."""

    def __init__(self, node_urls: Optional[List[str]] = None) -> None:
        self.nodes: Dict[str, ComputeNodeClient] = {}
        # Local compute node
        self.add_node("http://localhost:9000", name="PrimaryLaptopCompute")

        if node_urls:
            for i, url in enumerate(node_urls, 1):
                self.add_node(url, name=f"SecondaryLaptopCompute-{i}")

    def add_node(self, host_url: str, name: Optional[str] = None) -> ComputeNodeClient:
        """Add a compute worker node to the pool."""
        clean_url = host_url.rstrip("/")
        if not clean_url.startswith(("http://", "https://")):
            clean_url = f"http://{clean_url}"
        if not clean_url.endswith(":9000") and ":" not in clean_url[7:]:
            clean_url = f"{clean_url}:9000"

        node_name = name or f"ComputeNode-{len(self.nodes) + 1}"
        client = ComputeNodeClient(host_url=clean_url, name=node_name)
        client.ping()
        self.nodes[clean_url] = client
        return client

    def list_active_nodes(self) -> List[ComputeNodeClient]:
        """List active remote compute nodes."""
        active = []
        for client in self.nodes.values():
            if client.ping():
                active.append(client)
        return active

    def execute_python_distributed(self, code: str, preferred_node: Optional[str] = None) -> Dict[str, Any]:
        """Run Python code on the least loaded compute node."""
        active = self.list_active_nodes()
        if not active:
            raise RuntimeError("No active general compute nodes available!")

        target = active[0]
        if preferred_node:
            for n in active:
                if preferred_node in (n.name, n.host_url):
                    target = n
                    break

        logger.info("[General Compute Engine] Routing Python execution to node '%s' (%s)", target.name, target.host_url)
        return target.run_python_remote(code)

    def execute_terminal_distributed(self, command: str, preferred_node: Optional[str] = None) -> Dict[str, Any]:
        """Run a build/shell command on the least loaded compute node."""
        active = self.list_active_nodes()
        if not active:
            raise RuntimeError("No active general compute nodes available!")

        target = active[0]
        if preferred_node:
            for n in active:
                if preferred_node in (n.name, n.host_url):
                    target = n
                    break

        logger.info("[General Compute Engine] Routing terminal command to node '%s' (%s)", target.name, target.host_url)
        return target.run_terminal_remote(command)


# Global general compute engine instance
distributed_compute_engine = GeneralDistributedComputeEngine()
