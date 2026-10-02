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
import time
import logging
import textwrap
import subprocess
try:
    import psutil
except ImportError:
    psutil = None
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
    if psutil:
        mem = psutil.virtual_memory()
        cpu_used = psutil.cpu_percent(interval=None)
        ram_total = round(mem.total / (1024**3), 2)
        ram_available = round(mem.available / (1024**3), 2)
        ram_used_pct = mem.percent
    else:
        cpu_used = 0.0
        ram_total = 0.0
        ram_available = 0.0
        ram_used_pct = 0.0

    gpu_stats = _get_gpu_vram_stats()
    return {
        "status": "online",
        "hostname": os.environ.get("COMPUTERNAME", os.environ.get("HOSTNAME", "WorkerNode")),
        "platform": sys.platform,
        "cpu_cores": os.cpu_count() or 1,
        "cpu_used_pct": cpu_used,
        "ram_total_gb": ram_total,
        "ram_available_gb": ram_available,
        "ram_used_pct": ram_used_pct,
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

OLLAMA_PORT = 11434

@app.get("/api/tags")
def api_proxy_tags():
    """Proxy local Ollama tags or return empty list if Ollama is not running on this worker."""
    import urllib.request
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{OLLAMA_PORT}/api/tags", headers={"User-Agent": "WorkerNodeProxy/0.6.0"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {"models": []}

@app.get("/api/ps")
def api_proxy_ps():
    """Proxy local Ollama ps or return empty list."""
    import urllib.request
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{OLLAMA_PORT}/api/ps", headers={"User-Agent": "WorkerNodeProxy/0.6.0"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {"models": []}

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

def _start_http_heartbeat(master_url: str, worker_port: int = 9000, ollama_port: int = 11434):
    """Periodically register worker with master server over HTTP."""
    import urllib.request
    import threading

    clean_master = master_url.rstrip("/")
    if not clean_master.startswith(("http://", "https://")):
        clean_master = f"http://{clean_master}"
    reg_url = f"{clean_master}/api/cluster/register"

    def _heartbeat_loop():
        hostname = os.environ.get("COMPUTERNAME", os.environ.get("HOSTNAME", "WorkerNode"))
        payload = json.dumps({
            "hostname": hostname,
            "worker_port": worker_port,
            "ollama_port": ollama_port,
            "platform": sys.platform,
        }).encode("utf-8")

        first = True
        while True:
            try:
                req = urllib.request.Request(reg_url, data=payload, headers={"Content-Type": "application/json", "User-Agent": "WorkerNodeHeartbeat/0.6.0"})
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    if resp.status == 200:
                        if first:
                            print(f"  [+] Connected & registered with Master: {clean_master}")
                            first = False
            except Exception as e:
                if first:
                    print(f"  [!] Retrying connection to Master {clean_master}: {e}")
            time.sleep(10.0)

    t = threading.Thread(target=_heartbeat_loop, daemon=True)
    t.start()

def _start_mdns_announcer(worker_port: int = 9000, ollama_port: int = 11434):
    """Broadcast presence via UDP broadcast on local LAN so master nodes auto-discover this worker."""
    import socket
    import threading

    def _get_broadcast_destinations():
        dests = [("<broadcast>", 9999), ("255.255.255.255", 9999)]
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            parts = local_ip.split(".")
            if len(parts) == 4:
                dests.append((f"{parts[0]}.{parts[1]}.{parts[2]}.255", 9999))
        except Exception:
            pass
        return dests

    def _broadcast():
        hostname = os.environ.get("COMPUTERNAME", os.environ.get("HOSTNAME", "WorkerNode"))
        msg = f"OLLAMA_WORKER_ANNOUNCE:{hostname}:{ollama_port}:{worker_port}".encode("utf-8")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        dests = _get_broadcast_destinations()

        while True:
            for dest in dests:
                try:
                    sock.sendto(msg, dest)
                except Exception:
                    pass
            time.sleep(5.0)

    t = threading.Thread(target=_broadcast, daemon=True)
    t.start()


def main():
    global OLLAMA_PORT
    import argparse
    parser = argparse.ArgumentParser(description="Ollama Agents General Distributed Compute Worker Node")
    parser.add_argument("--host", default="0.0.0.0", help="Host address to bind (default 0.0.0.0)")
    parser.add_argument("--port", type=int, default=9000, help="Port to listen on (default 9000)")
    parser.add_argument("--ollama-port", type=int, default=11434, help="Port of local Ollama instance (default 11434)")
    parser.add_argument("--master", default=os.environ.get("MASTER_URL"), help="Master server URL (e.g. http://192.168.29.13:8100)")
    args = parser.parse_args()

    OLLAMA_PORT = args.ollama_port

    print(f"===================================================")
    print(f"  Ollama Agents General Distributed Compute Worker")
    print(f"  Listening on http://{args.host}:{args.port}")
    print(f"  Workspace: {WORKSPACE_ROOT}")
    if args.master:
        print(f"  Master Server: {args.master}")
        _start_http_heartbeat(args.master, worker_port=args.port, ollama_port=args.ollama_port)
    print(f"  mDNS Auto-Discovery: Active (UDP port 9999)")
    print(f"===================================================")

    _start_mdns_announcer(worker_port=args.port, ollama_port=args.ollama_port)
    uvicorn.run(app, host=args.host, port=args.port, reload=False)

if __name__ == "__main__":
    main()
