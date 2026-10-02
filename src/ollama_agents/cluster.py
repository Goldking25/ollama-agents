"""Distributed Cluster Engine for Ollama Agents.

Enables multi-node distributed processing across local network laptops/PCs running Ollama.
Aggregates models across multiple nodes, balances task loads, offloads heavy sub-agent
workloads to secondary machines seamlessly, and auto-discovers worker nodes via Zeroconf/mDNS.
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


@dataclass
class ClusterNode:
    """Represents a remote or local computer node running Ollama or Worker Node."""
    host_url: str  # e.g. "http://192.168.1.50:11434" or "http://192.168.1.50:9000"
    name: str = "LocalNode"
    is_active: bool = False
    installed_models: List[str] = field(default_factory=list)
    loaded_models: List[Dict[str, Any]] = field(default_factory=list)
    vram_used_bytes: int = 0
    total_size_bytes: int = 0
    latency_ms: float = 0.0
    active_jobs: int = 0
    discovered_via: str = "manual"  # 'manual', 'mdns', 'http_register'
    node_type: str = "ollama"       # 'ollama', 'worker', or 'hybrid'
    worker_url: Optional[str] = None
    worker_stats: Dict[str, Any] = field(default_factory=dict)

    def ping_and_discover(self) -> bool:
        """Check node health: queries Ollama /api/tags AND/OR worker /api/worker/health."""
        base = self.host_url.rstrip('/')
        start_time = time.time()
        
        ollama_ok = False
        worker_ok = False
        
        # 1. Test Ollama API on this host_url
        url_tags = f"{base}/api/tags"
        url_ps = f"{base}/api/ps"
        try:
            req = urllib.request.Request(url_tags, headers={"User-Agent": "OllamaAgentsCluster/0.6.0"})
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    models = []
                    for m in data.get("models", []):
                        name = m.get("model", m.get("name")) if isinstance(m, dict) else str(m)
                        if name:
                            models.append(name)
                    self.installed_models = models
                    ollama_ok = True
                    self.latency_ms = round((time.time() - start_time) * 1000.0, 1)
        except Exception:
            pass

        # Query loaded model memory from /api/ps if Ollama is responsive
        if ollama_ok:
            try:
                req_ps = urllib.request.Request(url_ps, headers={"User-Agent": "OllamaAgentsCluster/0.6.0"})
                with urllib.request.urlopen(req_ps, timeout=2.5) as resp_ps:
                    if resp_ps.status == 200:
                        ps_data = json.loads(resp_ps.read().decode("utf-8"))
                        active_models = ps_data.get("models", [])
                        self.loaded_models = []
                        total_vram = 0
                        total_size = 0
                        for am in active_models:
                            m_name = am.get("name", am.get("model", "Unknown"))
                            vram_b = am.get("size_vram", 0)
                            size_b = am.get("size", 0)
                            total_vram += vram_b
                            total_size += size_b
                            self.loaded_models.append({
                                "name": m_name,
                                "size_vram_gb": round(vram_b / (1024**3), 2),
                                "size_gb": round(size_b / (1024**3), 2),
                                "context_length": am.get("context_length", 0)
                            })
                        self.vram_used_bytes = total_vram
                        self.total_size_bytes = total_size
            except Exception:
                pass

        # 2. Test Compute Worker API (/api/worker/health)
        # Check current base, or alternate port 9000
        worker_candidate_urls = [f"{base}/api/worker/health"]
        if ":11434" in base:
            worker_candidate_urls.append(f"{base.replace(':11434', ':9000')}/api/worker/health")
        elif not any(p in base for p in [":9000", ":11434"]):
            worker_candidate_urls.append(f"{base}:9000/api/worker/health")

        for w_url in worker_candidate_urls:
            try:
                req_w = urllib.request.Request(w_url, headers={"User-Agent": "OllamaAgentsCluster/0.6.0"})
                with urllib.request.urlopen(req_w, timeout=2.5) as resp_w:
                    if resp_w.status == 200:
                        self.worker_stats = json.loads(resp_w.read().decode("utf-8"))
                        self.worker_url = w_url.replace("/api/worker/health", "")
                        worker_ok = True
                        if not self.latency_ms:
                            self.latency_ms = round((time.time() - start_time) * 1000.0, 1)
                        break
            except Exception:
                pass

        # If base was port 9000 and Ollama was not found yet, also probe port 11434
        if not ollama_ok and ":9000" in base:
            ollama_alt = base.replace(":9000", ":11434")
            try:
                req_alt = urllib.request.Request(f"{ollama_alt}/api/tags", headers={"User-Agent": "OllamaAgentsCluster/0.6.0"})
                with urllib.request.urlopen(req_alt, timeout=2.5) as resp_alt:
                    if resp_alt.status == 200:
                        data_alt = json.loads(resp_alt.read().decode("utf-8"))
                        self.installed_models = [
                            m.get("model", m.get("name")) if isinstance(m, dict) else str(m)
                            for m in data_alt.get("models", [])
                        ]
                        ollama_ok = True
            except Exception:
                pass

        if ollama_ok and worker_ok:
            self.node_type = "hybrid"
        elif worker_ok:
            self.node_type = "worker"
        elif ollama_ok:
            self.node_type = "ollama"

        if ollama_ok or worker_ok:
            self.is_active = True
            logger.info("ClusterNode '%s' (%s) active [type=%s]: %d models, latency: %.1fms",
                        self.name, self.host_url, self.node_type, len(self.installed_models), self.latency_ms)
            return True
        else:
            self.is_active = False
            self.installed_models = []
            self.loaded_models = []
            self.vram_used_bytes = 0
            self.total_size_bytes = 0
            self.worker_stats = {}
            logger.debug("ClusterNode '%s' (%s) unreachable on both Ollama and Worker endpoints", self.name, self.host_url)
            return False


class DistributedClusterManager:
    """Manages a cluster of Ollama node instances across local network laptops with Zeroconf/mDNS auto-discovery."""

    def __init__(self, node_urls: Optional[List[str]] = None) -> None:
        self.nodes: Dict[str, ClusterNode] = {}
        # Default local node
        self.add_node("http://localhost:11434", name="PrimaryLaptop", source="manual")

        if node_urls:
            for i, url in enumerate(node_urls, 1):
                self.add_node(url, name=f"SecondaryLaptop-{i}", source="manual")

        # Start mDNS Auto-Discovery Listener in background thread
        self._start_mdns_discovery_listener()

    def add_node(self, host_url: str, name: Optional[str] = None, source: str = "manual") -> ClusterNode:
        """Add a new laptop/node to the cluster."""
        clean_url = host_url.rstrip("/")
        if not clean_url.startswith(("http://", "https://")):
            clean_url = f"http://{clean_url}"
        
        # If user did not provide a port, try port 9000 first, or fallback to 11434
        if clean_url.count(":") <= 1:
            try_9000 = f"{clean_url}:9000"
            temp_node = ClusterNode(host_url=try_9000, name=name or "WorkerNode")
            if temp_node.ping_and_discover():
                clean_url = try_9000
            else:
                clean_url = f"{clean_url}:11434"

        node_name = name or f"Node-{len(self.nodes) + 1}"
        node = ClusterNode(host_url=clean_url, name=node_name, discovered_via=source)
        node.ping_and_discover()
        self.nodes[clean_url] = node
        return node

    def _start_mdns_discovery_listener(self) -> None:
        """Background thread scanning local LAN UDP broadcast for secondary Ollama worker nodes."""
        def _udp_listen():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("", 9999))
                sock.settimeout(4.0)
                logger.info("[Zeroconf/mDNS Cluster Discovery] Active on UDP port 9999...")

                while True:
                    try:
                        data, addr = sock.recvfrom(1024)
                        msg = data.decode("utf-8", errors="ignore").strip()
                        if msg.startswith("OLLAMA_WORKER_ANNOUNCE:"):
                            parts = msg.split(":")
                            # Format: OLLAMA_WORKER_ANNOUNCE:<hostname>:<ollama_port>:<worker_port>
                            worker_host = addr[0]
                            worker_ollama_port = parts[2] if len(parts) >= 3 else "11434"
                            worker_api_port = parts[3] if len(parts) >= 4 else "9000"

                            # Prefer worker API port 9000 or Ollama port
                            candidate_url = f"http://{worker_host}:{worker_api_port}"
                            if candidate_url not in self.nodes and f"http://{worker_host}:{worker_ollama_port}" not in self.nodes:
                                node_name = f"AutoDiscovered-{parts[1]}" if len(parts) >= 2 else f"AutoDiscovered-{worker_host}"
                                logger.info("[Zeroconf Auto-Discovered Node] Found %s at %s!", node_name, candidate_url)
                                self.add_node(candidate_url, name=node_name, source="mdns")
                    except socket.timeout:
                        pass
                    except Exception:
                        time.sleep(2.0)
            except Exception as e:
                logger.warning("[mDNS Discovery Listener Offline]: %s", e)

        t = threading.Thread(target=_udp_listen, daemon=True)
        t.start()

    def refresh_cluster_status(self) -> Dict[str, Any]:
        """Ping all cluster nodes and aggregate active models."""
        active_count = 0
        all_models = set()

        for url, node in list(self.nodes.items()):
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
                "discovered_via": n.discovered_via,
                "node_type": getattr(n, 'node_type', 'ollama'),
                "worker_url": getattr(n, 'worker_url', None),
                "worker_stats": getattr(n, 'worker_stats', {}),
                "models": n.installed_models,
                "loaded_models": n.loaded_models,
                "vram_used_gb": round(n.vram_used_bytes / (1024**3), 2),
                "vram_used_bytes": n.vram_used_bytes,
                "total_size_gb": round(n.total_size_bytes / (1024**3), 2),
                "active_jobs": n.active_jobs
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
