"""Distributed Worker Node Server for Ollama Agents.

Runs on secondary laptops / remote machines in the local network to execute:
1. Remote Python source code execution
2. Remote Shell / Terminal commands ^& build scripts
3. Remote Tool calls and data processing
4. Health ^& memory monitoring
"""

from __future__ import annotations

import os
import sys
import gc
import json
import logging
import textwrap
import subprocess
import psutil
from pathlib import Path
from typing import Dict, Any, Optional
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

logger = logging.getLogger("DistributedWorkerNode")

app = FastAPI(title="Ollama Agents Distributed Compute Worker Node", version="0.6.0")

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WORKSPACE_ROOT = Path.home() / "ollama_workspace"
WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)

# ── Pydantic Request Models ────────────────────────────────────────────────────
class ExecutePythonRequest(BaseModel):
    code: str
    timeout: int = 45

class ExecuteTerminalRequest(BaseModel):
    command: str
    timeout: int = 60

class ExecuteToolRequest(BaseModel):
    tool_name: str
    kwargs: Dict[str, Any] = {}

# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/api/worker/health")
def api_worker_health():
    """Report node hardware metrics (CPU, RAM, GPU, OS)."""
    mem = psutil.virtual_memory()
    gpu_stats = _get_gpu_vram_stats()
    return {
        "status": "online",
        "hostname": os.environ.get("COMPUTERNAME", os.environ.get("HOSTNAME", "WorkerNode")),
        "platform": sys.platform,
        "cpu_cores": os.cpu_count(),
        "cpu_used_pct": psutil.cpu_percent(interval=None),
        "ram_total_gb": round(mem.total / (1024**3), 2),
        "ram_available_gb": round(mem.available / (1024**3), 2),
        "ram_used_pct": mem.percent,
        "gpu": gpu_stats,
        "workspace_path": str(WORKSPACE_ROOT),
    }

@app.post("/api/worker/python")
def api_execute_python(req: ExecutePythonRequest):
    """Execute arbitrary Python source code remotely inside the worker's workspace."""
    try:
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(req.code)],
            capture_output=True,
            text=True,
            timeout=req.timeout,
            cwd=str(WORKSPACE_ROOT),
        )
        output = result.stdout.strip()
        errors = result.stderr.strip()
        return {
            "status": "success" if result.returncode == 0 else "failed",
            "returncode": result.returncode,
            "stdout": output,
            "stderr": errors,
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail=f"Python execution timed out after {req.timeout}s.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/worker/terminal")
def api_execute_terminal(req: ExecuteTerminalRequest):
    """Execute a shell/terminal command remotely inside the worker's workspace."""
    try:
        result = subprocess.run(
            req.command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=req.timeout,
            cwd=str(WORKSPACE_ROOT),
        )
        output = result.stdout.strip()
        errors = result.stderr.strip()
        return {
            "status": "success" if result.returncode == 0 else "failed",
            "returncode": result.returncode,
            "stdout": output,
            "stderr": errors,
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail=f"Terminal command timed out after {req.timeout}s.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/worker/tool")
def api_execute_tool(req: ExecuteToolRequest):
    """Execute a built-in or synthesized tool function remotely on this node."""
    try:
        from ollama_agents.tools import synthesize_new_tool, run_python, write_file, read_file
        from ollama_agents.tool_synthesizer import tool_synthesizer

        tool_name = req.tool_name
        if tool_name in tool_synthesizer.registry:
            tool_obj = tool_synthesizer.registry[tool_name]
            output = tool_obj.execute(**req.kwargs)
            return {"status": "success", "tool_name": tool_name, "output": output}

        if tool_name == "run_python":
            output = run_python(**req.kwargs)
            return {"status": "success", "tool_name": tool_name, "output": output}
        elif tool_name == "write_file":
            output = write_file(**req.kwargs)
            return {"status": "success", "tool_name": tool_name, "output": output}
        elif tool_name == "read_file":
            output = read_file(**req.kwargs)
            return {"status": "success", "tool_name": tool_name, "output": output}

        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not registered on worker node.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def _get_gpu_vram_stats() -> Dict[str, Any]:
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
                return {
                    "gpu_available": True,
                    "vram_total_gb": round(total / 1024.0, 2),
                    "vram_used_gb": round(used / 1024.0, 2),
                    "vram_free_gb": round(free / 1024.0, 2),
                    "vram_used_pct": round((used / total) * 100.0, 1),
                    "gpu_util_pct": gpu_util,
                }
    except Exception:
        pass
    return {"gpu_available": False, "vram_total_gb": 0.0, "vram_used_gb": 0.0, "vram_free_gb": 0.0, "vram_used_pct": 0.0, "gpu_util_pct": 0.0}

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Ollama Agents General Distributed Compute Worker Node")
    parser.add_argument("--host", default="0.0.0.0", help="Host address to bind (default 0.0.0.0)")
    parser.add_argument("--port", type=int, default=9000, help="Port to listen on (default 9000)")
    args = parser.parse_args()

    print(f"===================================================")
    print(f"  Ollama Agents General Distributed Compute Worker")
    print(f"  Listening on http://{args.host}:{args.port}")
    print(f"  Workspace: {WORKSPACE_ROOT}")
    print(f"===================================================")
    uvicorn.run(app, host=args.host, port=args.port, reload=False)

if __name__ == "__main__":
    main()
