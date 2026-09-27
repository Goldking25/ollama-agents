"""Memory & Concurrency Safety Manager for Ollama Agents.

Monitors system RAM and GPU VRAM utilization and manages semaphores / memory cleanup
to prevent out-of-memory (OOM) crashes during parallel agent execution or subagent spawning.
"""

import os
import gc
import logging
import threading
import subprocess
import psutil
from typing import Dict, Any, Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class MemorySafetyManager:
    """Singleton Memory Safety Manager that enforces System RAM & GPU VRAM resource bounds.

    Args:
        max_concurrent_agents: Maximum number of active subagents running simultaneously (default 3).
        ram_threshold_pct: Maximum allowed system RAM usage percentage before queuing tasks (default 85%).
        vram_threshold_pct: Maximum allowed GPU VRAM usage percentage before queuing tasks (default 90%).
        auto_gc: Whether to run Python garbage collection after task execution (default True).
    """

    _instance: Optional["MemorySafetyManager"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(MemorySafetyManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(
        self,
        max_concurrent_agents: int = 3,
        ram_threshold_pct: float = 85.0,
        vram_threshold_pct: float = 90.0,
        auto_gc: bool = True
    ):
        if self._initialized:
            return
        self.max_concurrent_agents = max_concurrent_agents
        self.ram_threshold_pct = ram_threshold_pct
        self.vram_threshold_pct = vram_threshold_pct
        self.auto_gc = auto_gc
        self.active_agent_count = 0
        self.semaphore = threading.Semaphore(max_concurrent_agents)
        self._count_lock = threading.Lock()
        self._initialized = True
        logger.info(
            "MemorySafetyManager initialized (Max Concurrent: %d, RAM Threshold: %.1f%%, VRAM Threshold: %.1f%%)",
            max_concurrent_agents, ram_threshold_pct, vram_threshold_pct
        )

    def _get_gpu_vram_stats(self) -> Dict[str, Any]:
        """Query NVIDIA GPU VRAM metrics via nvidia-smi if available."""
        try:
            res = subprocess.run(
                ['nvidia-smi', '--query-gpu=memory.total,memory.used,memory.free,utilization.gpu', '--format=csv,nounits,noheader'],
                capture_output=True, text=True, timeout=3.0
            )
            if res.returncode == 0 and res.stdout.strip():
                parts = [p.strip() for p in res.stdout.strip().split(',')]
                if len(parts) >= 4:
                    total = float(parts[0])
                    used = float(parts[1])
                    free = float(parts[2])
                    gpu_util = float(parts[3])
                    vram_pct = round((used / total) * 100.0, 1) if total > 0 else 0.0
                    return {
                        "gpu_available": True,
                        "vram_total_gb": round(total / 1024.0, 2),
                        "vram_used_gb": round(used / 1024.0, 2),
                        "vram_free_gb": round(free / 1024.0, 2),
                        "vram_used_pct": vram_pct,
                        "gpu_util_pct": gpu_util
                    }
        except Exception:
            pass

        return {
            "gpu_available": False,
            "vram_total_gb": 0.0,
            "vram_used_gb": 0.0,
            "vram_free_gb": 0.0,
            "vram_used_pct": 0.0,
            "gpu_util_pct": 0.0
        }

    def get_system_stats(self) -> Dict[str, Any]:
        """Get current system memory, GPU VRAM, and CPU utilization stats."""
        mem = psutil.virtual_memory()
        gpu_stats = self._get_gpu_vram_stats()

        return {
            "ram_total_gb": round(mem.total / (1024**3), 2),
            "ram_available_gb": round(mem.available / (1024**3), 2),
            "ram_used_pct": mem.percent,
            "cpu_used_pct": psutil.cpu_percent(interval=None),
            "active_agents": self.active_agent_count,
            "max_concurrent": self.max_concurrent_agents,
            "gpu": gpu_stats
        }

    def check_memory_headroom(self) -> bool:
        """Check if both System RAM and GPU VRAM usages are below safety limits."""
        stats = self.get_system_stats()
        is_safe = True

        if stats["ram_used_pct"] >= self.ram_threshold_pct:
            logger.warning(
                "System RAM pressure high! Usage at %.1f%% (Threshold: %.1f%%)",
                stats["ram_used_pct"], self.ram_threshold_pct
            )
            is_safe = False

        if stats["gpu"]["gpu_available"] and stats["gpu"]["vram_used_pct"] >= self.vram_threshold_pct:
            logger.warning(
                "GPU VRAM pressure high! Usage at %.1f%% (Threshold: %.1f%%). Free VRAM: %.2f GB",
                stats["gpu"]["vram_used_pct"], self.vram_threshold_pct, stats["gpu"]["vram_free_gb"]
            )
            is_safe = False

        return is_safe

    @contextmanager
    def acquire_execution_slot(self, timeout: float = 60.0):
        """Context manager to acquire a slot for agent execution within concurrency and memory bounds."""
        acquired = self.semaphore.acquire(timeout=timeout)
        if not acquired:
            raise RuntimeError(f"Memory safety limit reached: Could not acquire agent execution slot within {timeout}s.")

        with self._count_lock:
            self.active_agent_count += 1

        try:
            # Check RAM & VRAM headroom and trigger cleanup if memory is high
            if not self.check_memory_headroom() and self.auto_gc:
                self.force_garbage_collection()
            yield
        finally:
            with self._count_lock:
                self.active_agent_count -= 1
            self.semaphore.release()
            if self.auto_gc:
                self.force_garbage_collection()

    def force_garbage_collection(self) -> Dict[str, Any]:
        """Trigger explicit garbage collection to free unreferenced objects, PyTorch CUDA cache, and Ollama/ComfyUI GPU VRAM."""
        collected = gc.collect()

        # 1. Free PyTorch CUDA Cache if torch is available
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
        except Exception:
            pass

        # 2. Unload running models from Ollama GPU VRAM (set keep_alive: 0)
        try:
            import httpx
            ps_resp = httpx.get("http://127.0.0.1:11434/api/ps", timeout=3.0)
            if ps_resp.status_code == 200:
                models = ps_resp.json().get("models", [])
                for m in models:
                    model_name = m.get("name") or m.get("model")
                    if model_name:
                        httpx.post("http://127.0.0.1:11434/api/generate", json={"model": model_name, "keep_alive": 0}, timeout=5.0)
        except Exception as e:
            logger.debug("Ollama VRAM unload check: %s", e)

        # 3. Unload ComfyUI models from GPU VRAM if running
        try:
            import httpx
            httpx.post("http://127.0.0.1:8000/free", json={"unload_models": True, "free_memory": True}, timeout=3.0)
        except Exception:
            pass

        # 4. Unload SD Forge models from GPU VRAM if running
        try:
            import httpx
            httpx.post("http://127.0.0.1:7860/sdapi/v1/unload-checkpoint", timeout=3.0)
        except Exception:
            pass

        collected += gc.collect()
        stats = self.get_system_stats()
        vram_free = stats["gpu"]["vram_free_gb"] if stats["gpu"]["gpu_available"] else 0.0
        logger.info(
            "Garbage collection completed. Objects collected: %d. Free RAM: %.2f GB, Free VRAM: %.2f GB",
            collected, stats["ram_available_gb"], vram_free
        )
        return {
            "collected_objects": collected,
            "free_ram_gb": stats["ram_available_gb"],
            "vram_free_gb": vram_free,
            "gpu_available": stats["gpu"]["gpu_available"]
        }

# Module-level default singleton instance
memory_manager = MemorySafetyManager()
