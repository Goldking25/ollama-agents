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
        auto_gc: bool = True,
        auto_unload_on_switch: bool = True
    ):
        if self._initialized:
            return
        self.max_concurrent_agents = max_concurrent_agents
        self.ram_threshold_pct = ram_threshold_pct
        self.vram_threshold_pct = vram_threshold_pct
        self.auto_gc = auto_gc
        env_unload = os.getenv("AUTO_UNLOAD_ON_MODEL_SWITCH", "true").lower() in ("1", "true", "yes")
        self.auto_unload_on_switch = auto_unload_on_switch and env_unload
        self.active_agent_count = 0
        self.semaphore = threading.Semaphore(max_concurrent_agents)
        self._count_lock = threading.Lock()
        self._initialized = True
        logger.info(
            "MemorySafetyManager initialized (Max Concurrent: %d, RAM Threshold: %.1f%%, VRAM Threshold: %.1f%%, Auto-Unload: %s)",
            max_concurrent_agents, ram_threshold_pct, vram_threshold_pct, self.auto_unload_on_switch
        )

    def _get_ollama_base_url(self, host: Optional[str] = None) -> str:
        """Resolve Ollama base URL from argument, env, or default localhost."""
        if host:
            h = host.strip()
            if not h.startswith("http://") and not h.startswith("https://"):
                h = f"http://{h}"
            return h.rstrip("/")
        env_host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").strip()
        if not env_host.startswith("http://") and not env_host.startswith("https://"):
            env_host = f"http://{env_host}"
        return env_host.rstrip("/")

    def get_loaded_models(self, host: Optional[str] = None) -> list:
        """Query Ollama /api/ps to retrieve models currently resident in RAM/VRAM."""
        base_url = self._get_ollama_base_url(host)
        try:
            import httpx
            resp = httpx.get(f"{base_url}/api/ps", timeout=3.0)
            if resp.status_code == 200:
                raw_models = resp.json().get("models", [])
                result = []
                for m in raw_models:
                    name = m.get("name") or m.get("model") or ""
                    size_bytes = m.get("size", 0)
                    size_vram = m.get("size_vram", 0)
                    result.append({
                        "name": name,
                        "model": name,
                        "size_gb": round(size_bytes / (1024**3), 2),
                        "size_vram_gb": round(size_vram / (1024**3), 2),
                        "expires_at": m.get("expires_at"),
                        "details": m.get("details", {})
                    })
                return result
        except Exception as e:
            logger.debug("Failed to query loaded models from %s: %s", base_url, e)
        return []

    def unload_model(self, model_name: str, host: Optional[str] = None) -> bool:
        """Unload a specific model from Ollama RAM/VRAM immediately by sending keep_alive: 0."""
        if not model_name:
            return False
        base_url = self._get_ollama_base_url(host)
        try:
            import httpx
            resp = httpx.post(
                f"{base_url}/api/generate",
                json={"model": model_name, "keep_alive": 0},
                timeout=5.0
            )
            if resp.status_code == 200:
                logger.info("[MemorySafety] Successfully unloaded model '%s' from RAM/VRAM on %s", model_name, base_url)
                return True
            else:
                logger.warning("[MemorySafety] Unload request for '%s' returned status %d: %s", model_name, resp.status_code, resp.text)
        except Exception as e:
            logger.warning("[MemorySafety] Failed to unload model '%s' from %s: %s", model_name, base_url, e)
        return False

    def unload_all_loaded_models(self, host: Optional[str] = None) -> list:
        """Unload all currently loaded models from Ollama RAM/VRAM."""
        loaded = self.get_loaded_models(host=host)
        unloaded = []
        for m in loaded:
            m_name = m.get("name")
            if m_name and self.unload_model(m_name, host=host):
                unloaded.append(m_name)
        if unloaded:
            self._clean_torch_and_gc()
        return unloaded

    def _clean_torch_and_gc(self):
        """Clean PyTorch CUDA cache and run Python garbage collection."""
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
        except Exception:
            pass
        gc.collect()

    def prepare_model_switch(self, target_model: str, host: Optional[str] = None, force: bool = False) -> list:
        """Smart Model Switching: If another model is currently resident in RAM/VRAM,
        proactively unload it to prevent VRAM overflow, CPU offload latency, and OOM crashes.
        
        Args:
            target_model: The model about to be executed.
            host: Optional Ollama host URL.
            force: If True, unload even if auto_unload_on_switch is disabled.

        Returns:
            List of model names unloaded.
        """
        if not (self.auto_unload_on_switch or force) or not target_model:
            return []

        loaded = self.get_loaded_models(host=host)
        if not loaded:
            return []

        target_norm = target_model.strip().lower()
        target_clean = target_norm[:-7] if target_norm.endswith(":latest") else target_norm
        unloaded = []

        for m in loaded:
            loaded_name = (m.get("name") or m.get("model") or "").strip()
            if not loaded_name:
                continue
            l_norm = loaded_name.lower()
            l_clean = l_norm[:-7] if l_norm.endswith(":latest") else l_norm

            # Same model check (exact or canonical tag)
            if l_norm == target_norm or l_clean == target_clean:
                # Target model is already warm in memory
                continue

            logger.info(
                "[MemorySafety] Model switch detected: New task requires '%s'. Proactively unloading inactive loaded model '%s' (occupying %.2f GB in memory)...",
                target_model, loaded_name, m.get("size_gb", 0.0)
            )
            if self.unload_model(loaded_name, host=host):
                unloaded.append(loaded_name)

        if unloaded:
            self._clean_torch_and_gc()
            logger.info("[MemorySafety] Freed RAM/VRAM before executing '%s'. Unloaded: %s", target_model, unloaded)

        return unloaded

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
        """Get current system memory, GPU VRAM, CPU utilization stats, and loaded Ollama models."""
        mem = psutil.virtual_memory()
        gpu_stats = self._get_gpu_vram_stats()
        loaded = self.get_loaded_models()

        return {
            "ram_total_gb": round(mem.total / (1024**3), 2),
            "ram_available_gb": round(mem.available / (1024**3), 2),
            "ram_used_pct": mem.percent,
            "cpu_used_pct": psutil.cpu_percent(interval=None),
            "active_agents": self.active_agent_count,
            "max_concurrent": self.max_concurrent_agents,
            "gpu": gpu_stats,
            "loaded_models": loaded
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
        self._clean_torch_and_gc()

        # 2. Unload running models from Ollama GPU VRAM (set keep_alive: 0)
        unloaded_models = self.unload_all_loaded_models()

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
            "Garbage collection completed. Objects collected: %d. Unloaded models: %s. Free RAM: %.2f GB, Free VRAM: %.2f GB",
            collected, unloaded_models, stats["ram_available_gb"], vram_free
        )
        return {
            "collected_objects": collected,
            "unloaded_models": unloaded_models,
            "free_ram_gb": stats["ram_available_gb"],
            "vram_free_gb": vram_free,
            "gpu_available": stats["gpu"]["gpu_available"]
        }

# Module-level default singleton instance
memory_manager = MemorySafetyManager()
