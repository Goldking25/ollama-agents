"""
FastAPI Server Backend for Ollama Agents Web Dashboard.
"""

import os
import json
import base64
import asyncio
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pathlib import Path
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ollama_agents import Agent, GoalRegistry, MemoryStore
from ollama_agents.exceptions import MaxTurnsExceeded

app = FastAPI(title="Ollama Agents Web Dashboard", version="0.6.0")

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Pydantic Request Schemas ───────────────────────────────────────────────────
class SingleTaskRequest(BaseModel):
    prompt: str
    model: str = "deepseek-r1:8b"
    max_turns: int = 50
    session_id: Optional[str] = "default_session"
    attachment: Optional[str] = ""

class FollowupRequest(BaseModel):
    prompt: str
    auto_run: bool = True

class CreateGoalRequest(BaseModel):
    prompt: str
    model: str = "deepseek-r1:8b"

class PullModelRequest(BaseModel):
    model_tag: str

class AddNodeRequest(BaseModel):
    host_url: str
    name: Optional[str] = None

# Global active model pull status tracker
PULLING_MODELS: Dict[str, Any] = {}

import logging
logger = logging.getLogger(__name__)

# ── Self-Modification: codebase location ──────────────────────────────────────
import sys as _sys
CODEBASE_PATH = str(Path(__file__).parent.resolve())   # e.g. .../src/ollama_agents
CODEBASE_INSTRUCTIONS = f"""
## 🛠️ Self-Modification Capability
You can read, edit, and improve YOUR OWN source code. Your codebase is at:
  {CODEBASE_PATH}

Key source files you may need to edit:
  {CODEBASE_PATH}/agent.py          — core agent loop & prompting
  {CODEBASE_PATH}/server.py         — FastAPI server & all API endpoints
  {CODEBASE_PATH}/memory.py         — SQLite memory store
  {CODEBASE_PATH}/goal.py           — long-horizon goal registry
  {CODEBASE_PATH}/checkpoint.py     — run state checkpointing
  {CODEBASE_PATH}/tools/search.py   — web search tool
  {CODEBASE_PATH}/tools/comfyui.py  — video generation tool
  {CODEBASE_PATH}/static/index.html — web dashboard UI
  {CODEBASE_PATH}/memory_manager.py — VRAM / GC management

Workflow for self-modification:
  1. Use read_file to inspect the file that needs changing.
  2. Use write_file to apply the fix (write the complete corrected file).
  3. Optionally use run_terminal to run: git -C "{CODEBASE_PATH}/../.." add -A && git -C "{CODEBASE_PATH}/../.." commit -m "<message>" && git -C "{CODEBASE_PATH}/../.." push
  4. Use run_terminal to restart: curl -s -X POST http://localhost:8100/api/system/restart
  5. The server restarts in ~3 seconds with your fix applied.

IMPORTANT: Only modify files under {CODEBASE_PATH}. Always read before writing.
"""


# ── WebSocket Real-Time Push Endpoint ─────────────────────────────────────────
@app.websocket("/ws/cluster")
async def websocket_cluster_stream(websocket: WebSocket):
    """Multi-event WebSocket: pushes cluster_status, system_stats, and goals_update
    so the UI never needs to poll those endpoints with setInterval."""
    await websocket.accept()
    from ollama_agents.cluster import cluster_manager
    import psutil

    tick = 0   # used to stagger different push intervals on a common loop
    try:
        while True:
            # ── Cluster status (every 2.5 s) ─────────────────────────
            try:
                status = cluster_manager.refresh_cluster_status()
                await websocket.send_json({"type": "cluster_status", "data": status})
            except Exception:
                pass

            # ── System stats (every 5 s, i.e. every 2nd tick) ────────
            if tick % 2 == 0:
                try:
                    mem = psutil.virtual_memory()
                    stats: Dict[str, Any] = {
                        "ram_used_pct": round(mem.percent, 1),
                        "free_ram_gb": round(mem.available / (1024 ** 3), 2),
                        "active_agents": len([t for t in __import__("asyncio").all_tasks()
                                              if "execute_goal" in t.get_name()]),
                        "gpu": None,
                    }
                    try:
                        import torch
                        if torch.cuda.is_available():
                            used = torch.cuda.memory_allocated(0)
                            total = torch.cuda.get_device_properties(0).total_memory
                            stats["gpu"] = {
                                "gpu_available": True,
                                "vram_used_pct": round(used / total * 100, 1),
                                "vram_free_gb": round((total - used) / (1024 ** 3), 2),
                            }
                    except Exception:
                        pass
                    await websocket.send_json({"type": "system_stats", "data": stats})
                except Exception:
                    pass

            # ── Goals update (every 3 s, i.e. every ~1.2th tick — approximate with mod 1) ─
            if tick % 1 == 0:
                try:
                    registry = GoalRegistry()
                    goals = registry.list_all()
                    goals_payload = []
                    for g in goals:
                        goals_payload.append({
                            "id": g.id,
                            "description": g.description,
                            "status": g.status,
                            "progress_pct": round(g.progress_pct, 1),
                            "session_count": g.session_count,
                            "model": g.model,
                            "updated": g.updated,
                            "tasks": [
                                {"id": t.id, "description": t.description,
                                 "status": t.status, "output": (t.output or "")[:200]}
                                for t in g.tasks
                            ],
                        })
                    await websocket.send_json({"type": "goals_update", "data": goals_payload})
                except Exception:
                    pass

            tick += 1
            await asyncio.sleep(2.5)

    except (WebSocketDisconnect, RuntimeError, Exception) as e:
        logger.debug("WebSocket connection closed: %s", e)


# ── API Endpoints ─────────────────────────────────────────────────────────────
@app.get("/api/cluster/nodes")
def api_get_cluster_nodes():
    """Get status of all connected laptops/nodes in the distributed cluster and aggregated models."""
    from ollama_agents.cluster import cluster_manager
    return cluster_manager.refresh_cluster_status()

@app.post("/api/cluster/nodes/add")
def api_add_cluster_node(req: AddNodeRequest):
    """Connect a secondary laptop/computer running Ollama to the distributed agent cluster."""
    from ollama_agents.cluster import cluster_manager
    node = cluster_manager.add_node(host_url=req.host_url, name=req.name)
    if node.is_active:
        return {"status": "success", "message": f"Successfully connected secondary laptop node '{node.name}' ({node.host_url})!", "node": node.__dict__}
    return {"status": "warning", "message": f"Added node '{node.name}' ({node.host_url}), but could not reach Ollama API. Ensure 'OLLAMA_HOST=0.0.0.0' is set on secondary machine.", "node": node.__dict__}

@app.post("/api/goals/{goal_id}/followup")
def api_add_goal_followup(goal_id: str, req: FollowupRequest, background_tasks: BackgroundTasks):
    """Add a follow-up question or new sub-task to an existing goal and optionally execute it immediately."""
    registry = GoalRegistry()
    goal = registry.get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    new_task = registry.add_followup_task(goal_id, req.prompt)
    if not new_task:
        raise HTTPException(status_code=500, detail="Failed to add follow-up task")

    if req.auto_run:
        # Trigger background execution for the follow-up task
        res = api_run_goal_task(goal_id=goal_id, background_tasks=background_tasks, auto_continue=True)
        return {"status": "success", "task": new_task.__dict__, "execution": res}

    return {"status": "success", "task": new_task.__dict__, "message": "Follow-up task appended to goal."}
@app.get("/api/models/installed")
@app.get("/api/models")
def api_list_models():
    """List all available Ollama models installed locally and across cluster nodes."""
    import ollama
    from ollama_agents.model_selector import is_multimodal_model
    from ollama_agents.cluster import cluster_manager
    try:
        models_data = ollama.Client(host=os.getenv('OLLAMA_HOST', 'http://127.0.0.1:11434'), timeout=5.0).list()
        raw_models = getattr(models_data, 'models', models_data.get('models', []))
        names = []
        for m in raw_models:
            name = getattr(m, 'model', getattr(m, 'name', None))
            if not name and isinstance(m, dict):
                name = m.get('model', m.get('name'))
            if name:
                names.append(str(name))

        # Include cluster models if any remote nodes are active
        try:
            cluster_status = cluster_manager.refresh_cluster_status()
            for cm in cluster_status.get("aggregate_models", []):
                if cm not in names:
                    names.append(cm)
        except Exception as ce:
            logger.debug("Cluster models query failed: %s", ce)

        # Fallback if Ollama is empty or initializing
        final_names = names if names else ["deepseek-r1:8b", "llama3.1:latest"]

        # Annotate capability metadata
        model_details = [
            {
                "name": name,
                "is_multimodal": is_multimodal_model(name),
                "capabilities": [
                    cap for cap, cond in [
                        ("vision", is_multimodal_model(name)),
                        ("coding", any(k in name.lower() for k in ["coder", "qwen2.5", "qwen3.5", "qwen3.8"])),
                        ("reasoning", "deepseek-r1" in name.lower()),
                        ("general", True),
                    ] if cond
                ]
            }
            for name in final_names
        ]

        return {
            "status": "success",
            "models": final_names,
            "details": model_details,
            "pulling": list(PULLING_MODELS.keys())
        }
    except Exception as e:
        logger.error("Failed to list installed models: %s", e)
        fallback_names = ["deepseek-r1:8b", "llama3.1:latest"]
        fallback_details = [
            {"name": "deepseek-r1:8b", "is_multimodal": False, "capabilities": ["reasoning", "coding", "general"]},
            {"name": "llama3.1:latest", "is_multimodal": False, "capabilities": ["general"]}
        ]
        return {
            "status": "error",
            "models": fallback_names,
            "details": fallback_details,
            "error": str(e),
            "pulling": list(PULLING_MODELS.keys())
        }

@app.get("/api/system/stats")
def api_system_stats():
    """Get live RAM/CPU utilization and active subagent execution counts."""
    from ollama_agents.memory_manager import memory_manager
    return memory_manager.get_system_stats()

@app.post("/api/system/gc")
def api_trigger_gc():
    """Force garbage collection to clean up memory."""
    from ollama_agents.memory_manager import memory_manager
    return memory_manager.force_garbage_collection()

@app.post("/api/system/restart")
def api_restart_server():
    """Trigger clean server process restart to reload Python modules."""
    def _shutdown():
        time.sleep(0.5)
        os._exit(42)  # Exit code 42 triggers start_agent.bat restart loop

    import threading, time
    threading.Thread(target=_shutdown, daemon=True).start()
    return {"status": "restarting", "message": "Server process is restarting..."}

@app.get("/api/codebase/files")
def api_list_codebase_files():
    """Return a flat list of all editable source files in the agent codebase."""
    exts = {".py", ".html", ".js", ".css", ".md", ".bat", ".toml", ".cfg", ".txt"}
    skip_dirs = {"__pycache__", ".git", ".venv", "venv", "node_modules", ".mypy_cache"}
    files = []
    base = Path(CODEBASE_PATH).parent.parent  # repo root
    for p in sorted(base.rglob("*")):
        if any(part in skip_dirs for part in p.parts):
            continue
        if p.is_file() and p.suffix in exts:
            try:
                rel = str(p.relative_to(base)).replace("\\", "/")
                files.append({"path": rel, "full_path": str(p), "size": p.stat().st_size})
            except Exception:
                pass
    return {"codebase_root": str(base), "files": files}


@app.post("/api/models/pull")
def api_pull_model(req: PullModelRequest, background_tasks: BackgroundTasks):
    """Pull a new GGUF model from Hugging Face / Ollama in the background."""
    model_tag = req.model_tag.strip()
    if not model_tag:
        raise HTTPException(status_code=400, detail="Model tag cannot be empty.")

    if model_tag in PULLING_MODELS:
        return {"status": "already_pulling", "message": f"Model '{model_tag}' is already being pulled in the background."}

    def _pull():
        PULLING_MODELS[model_tag] = {"status": "downloading"}
        try:
            import ollama
            logger.info("Pulling model '%s' into local Ollama...", model_tag)
            ollama.pull(model_tag)
            logger.info("Successfully pulled model '%s'!", model_tag)
        except Exception as e:
            logger.error("Failed to pull model '%s': %s", model_tag, e)
        finally:
            PULLING_MODELS.pop(model_tag, None)

    background_tasks.add_task(_pull)
    return {"status": "started", "message": f"Download started for model '{model_tag}'. You can track progress or refresh installed models once done."}

@app.get("/api/models/search-hf")
def api_search_hf_models(query: str):
    """Search Hugging Face Hub for GGUF models compatible with local Ollama."""
    from ollama_agents.model_selector import search_huggingface_models
    results = search_huggingface_models(query=query)
    return {"query": query, "results": results}

@app.get("/api/models/trending-hf")
def api_trending_hf_models():
    """Fetch daily trending GGUF models from Hugging Face Hub."""
    from ollama_agents.model_selector import fetch_trending_hf_models
    results = fetch_trending_hf_models()
    return {"results": results}

@app.post("/api/upload")
async def api_upload_file(file: UploadFile = File(...)):
    """Upload a file or image for analysis, editing, or reference by the agent."""
    try:
        upload_dir = Path.home() / "ollama_workspace" / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # Sanitize filename
        safe_filename = Path(file.filename).name
        dest_path = upload_dir / safe_filename
        
        contents = await file.read()
        dest_path.write_bytes(contents)
        
        rel_path = f"uploads/{safe_filename}"
        return {
            "status": "success",
            "filename": safe_filename,
            "filepath": rel_path,
            "full_path": str(dest_path),
            "size": len(contents),
            "message": f"File '{safe_filename}' uploaded successfully to '{rel_path}'."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {e}")

@app.get("/api/goals")
def api_list_goals():
    """List all long-horizon goals."""
    registry = GoalRegistry()
    goals = registry.list_goals()
    return [{
        "goal_id": g.id,
        "title": g.description,
        "model": g.agent_name,
        "created_at": g.created,
        "progress_pct": g.progress_pct,
        "final_summary": getattr(g, 'final_summary', ''),
        "tasks_count": len(g.tasks),
        "tasks": [t.__dict__ for t in g.tasks]
    } for g in goals]

@app.post("/api/goals/create")
def api_create_goal(req: CreateGoalRequest):
    """Decompose and save a new goal."""
    registry = GoalRegistry()
    
    # Sanitize model name so the planner doesn't crash on invalid model names
    model_name = req.model
    if not model_name or model_name == "AutonomousAgent":
        model_name = "deepseek-r1:8b"
        
    goal = registry.create_goal(req.prompt, model=model_name)
    return {"status": "success", "goal": goal.__dict__, "tasks": [t.__dict__ for t in goal.tasks]}

# Global active execution registry for kill switch
ACTIVE_EXECUTIONS: Dict[str, Any] = {}

@app.post("/api/goals/{goal_id}/run")
def api_run_goal_task(goal_id: str, background_tasks: BackgroundTasks, auto_continue: bool = True):
    """Trigger goal tasks in the background. If auto_continue=True, automatically proceeds through all remaining pending sub-tasks."""
    registry = GoalRegistry()
    goal = registry.get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    next_task = goal.next_task
    if not next_task:
        return {"status": "completed", "message": "All tasks for this goal are already complete."}

    if goal_id in ACTIVE_EXECUTIONS:
        return {"status": "already_running", "message": f"Goal {goal_id} is already running in the background."}

    def _execute():
        ACTIVE_EXECUTIONS[goal_id] = {"status": "running"}
        try:
            from ollama_agents.tools import web_search, get_realtime_market_quote, write_file, read_file, run_terminal, run_python, delegate_subagent, rag_add_knowledge, rag_search, generate_image_sd_forge, edit_image_sd_forge, edit_image, generate_video_comfyui, github_clone_repo, github_create_branch, github_commit_and_push, github_create_pull_request, github_status, test_ui_playwright, build_android_apk
            
            while True:
                # Re-fetch latest goal state
                current_goal = registry.get_goal(goal_id)
                if not current_goal:
                    break

                curr_task = current_goal.next_task
                if not curr_task:
                    # All tasks done! Generate overall final synthesis summary
                    if not current_goal.final_summary:
                        try:
                            model_name = getattr(current_goal, 'model', None) or getattr(current_goal, 'agent_name', 'deepseek-r1:8b')
                            if model_name == "AutonomousAgent" or not model_name:
                                model_name = "deepseek-r1:8b"
                            agent = Agent(model=model_name, max_turns=10)
                            
                            subtask_outputs = []
                            for t in current_goal.tasks:
                                subtask_outputs.append(f"- Sub-task: {t.description}\n  Result: {t.output[:400]}")
                            
                            summary_prompt = (
                                f"Goal: {current_goal.description}\n\n"
                                f"All {len(current_goal.tasks)} session sub-tasks have been completed. Here are the outputs:\n"
                                + "\n".join(subtask_outputs) +
                                "\n\nProvide a comprehensive, high-level final summary and overall conclusion for this completed goal."
                            )
                            summary_res = agent.run(summary_prompt)
                            registry.save_final_summary(goal_id, summary_res)
                        except Exception as sum_err:
                            logger.warning("Final summary synthesis failed: %s", sum_err)
                    break

                model_name = getattr(current_goal, 'model', None) or getattr(current_goal, 'agent_name', 'deepseek-r1:8b')
                if model_name == "AutonomousAgent" or not model_name:
                    model_name = "deepseek-r1:8b"
                    
                if hasattr(curr_task, 'model_override') and curr_task.model_override:
                    model_name = curr_task.model_override

                from ollama_agents.cluster import cluster_manager
                best_node = cluster_manager.select_best_node_for_model(model_name)
                host_url = best_node.host_url if best_node else None

                from ollama_agents.memory_manager import memory_manager
                try:
                    memory_manager.force_garbage_collection()
                except Exception as gc_err:
                    logger.debug("Pre-task GC cleanup: %s", gc_err)

                memory = MemoryStore(agent_name="AssistantAgent")
                agent = Agent(
                    model=model_name,
                    host=host_url,
                    tools=[write_file, read_file, run_terminal, run_python, web_search, get_realtime_market_quote, delegate_subagent, rag_add_knowledge, rag_search, generate_image_sd_forge, edit_image_sd_forge, edit_image, generate_video_comfyui, github_clone_repo, github_create_branch, github_commit_and_push, github_create_pull_request, github_status, test_ui_playwright, build_android_apk],
                    memory=memory,
                    max_turns=120
                )
                
                # Execute current session sub-task
                agent.run_goal(goal_id)

                # Check if task is still in_progress (e.g. MaxTurnsExceeded) — don't retry infinitely
                refreshed = registry.get_goal(goal_id)
                if refreshed and refreshed.next_task and refreshed.next_task.id == curr_task.id and refreshed.next_task.status == "in_progress":
                    logger.warning("Task '%s' still in_progress after execution (likely MaxTurnsExceeded). Marking as failed.", curr_task.id)
                    registry.fail_task(goal_id, curr_task.id, reason="timed out")

                if not auto_continue or goal_id not in ACTIVE_EXECUTIONS:
                    break

        except Exception as e:
            curr_g = registry.get_goal(goal_id)
            if curr_g and curr_g.next_task:
                registry.fail_task(goal_id, curr_g.next_task.id, reason=str(e))
        finally:
            ACTIVE_EXECUTIONS.pop(goal_id, None)

    background_tasks.add_task(_execute)
    return {"status": "started", "message": f"Execution started for goal {goal_id} (Auto-continue: {auto_continue})"}

@app.post("/api/goals/{goal_id}/tasks/{task_id}/retry")
def api_retry_goal_task(goal_id: str, task_id: str, background_tasks: BackgroundTasks, auto_continue: bool = True, model_override: Optional[str] = None):
    """Reset a task to pending and optionally resume execution."""
    registry = GoalRegistry()
    goal = registry.get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
        
    registry.reset_task(goal_id, task_id, model_override=model_override)
    return api_run_goal_task(goal_id, background_tasks, auto_continue=auto_continue)

@app.post("/api/goals/{goal_id}/kill")
def api_kill_goal_execution(goal_id: str):
    """Kill active background execution for a specific goal and reset task state safely."""
    ACTIVE_EXECUTIONS.pop(goal_id, None)
    registry = GoalRegistry()
    goal = registry.get_goal(goal_id)
    
    # Mark in-progress tasks as cancelled/pending in registry
    if goal:
        for t in goal.tasks:
            if t.status == "in_progress":
                registry.fail_task(goal_id, t.id, reason="Execution stopped by user Kill Switch")

    return {"status": "killed", "message": f"Killed active execution and reset state for goal {goal_id}"}

@app.delete("/api/goals/{goal_id}")
def api_delete_goal(goal_id: str):
    """Permanently delete a goal, terminate any in-flight background execution, and clean up stored state."""
    # Instantly stop active background execution loop if running
    ACTIVE_EXECUTIONS.pop(goal_id, None)
    
    registry = GoalRegistry()
    success = registry.delete_goal(goal_id)
    if not success:
        raise HTTPException(status_code=404, detail="Goal not found or could not be deleted")
    return {"status": "success", "message": f"Goal '{goal_id}' deleted successfully."}

@app.post("/api/tasks/kill-all")
def api_kill_all_executions():
    """Emergency Kill Switch: Stop all active goal & single task executions and reset state."""
    registry = GoalRegistry()
    goals = registry.list_goals()
    killed_count = 0

    for goal in goals:
        for t in goal.tasks:
            if t.status == "in_progress":
                registry.fail_task(goal.id, t.id, reason="Stopped by Emergency Kill-All Switch")
                killed_count += 1

    ACTIVE_EXECUTIONS.clear()
    return {"status": "success", "message": f"Emergency Kill Switch activated. Cleared {killed_count} active tasks."}



def resolve_multimodal_images(attachment_path: str) -> List[str]:
    """Resolve workspace file attachment and return base64-encoded image strings for Ollama payload."""
    if not attachment_path:
        return []

    workspace_dir = Path.home() / "ollama_workspace"
    candidates = [
        workspace_dir / attachment_path,
        workspace_dir / "uploads" / attachment_path,
        workspace_dir / "uploads" / Path(attachment_path).name,
        Path(attachment_path),
    ]
    target = None
    for cand in candidates:
        try:
            if cand.exists() and cand.is_file():
                target = cand
                break
        except Exception:
            continue

    if not target:
        return []

    ext = target.suffix.lower().lstrip(".")
    image_exts = {"png", "jpg", "jpeg", "webp", "gif", "bmp"}
    video_exts = {"mp4", "webm", "mov", "avi", "mkv"}

    if ext in image_exts:
        try:
            b64_str = base64.b64encode(target.read_bytes()).decode("utf-8")
            return [b64_str]
        except Exception as e:
            logger.error("Failed to read image %s: %s", target, e)
            return []
    elif ext in video_exts:
        try:
            import cv2
            frames_b64 = []
            cap = cv2.VideoCapture(str(target))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames > 0:
                sample_indices = [int(total_frames * ratio) for ratio in [0.1, 0.5, 0.9]]
                for idx in sample_indices:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                    ret, frame = cap.read()
                    if ret:
                        _, buf = cv2.imencode(".jpg", frame)
                        frames_b64.append(base64.b64encode(buf).decode("utf-8"))
            cap.release()
            return frames_b64
        except Exception as ve:
            logger.warning("Video frame extraction unavailable (%s); skipping video frames", ve)
            return []

    return []

# Global session agents registry for stateful chat history
SESSION_AGENTS: Dict[str, Agent] = {}

@app.post("/api/task/run")
def api_run_single_task(req: SingleTaskRequest):
    """Run a single task or conversation message with stateful history persistence."""
    try:
        from ollama_agents.tools import web_search, get_realtime_market_quote, write_file, read_file, list_workspace_files, run_terminal, run_python, delegate_subagent, rag_add_knowledge, rag_search, generate_image_sd_forge, edit_image_sd_forge, edit_image, generate_video_comfyui, github_clone_repo, github_create_branch, github_commit_and_push, github_create_pull_request, github_status, test_ui_playwright, build_android_apk
        from ollama_agents.cluster import cluster_manager

        session_key = req.session_id or "default_session"
        best_node = cluster_manager.select_best_node_for_model(req.model)
        host_url = best_node.host_url if best_node else None

        # Resolve multimodal images if attachment is provided
        images = resolve_multimodal_images(req.attachment) if req.attachment else []

        # Reuse existing stateful Agent or create a new session agent
        if session_key not in SESSION_AGENTS or SESSION_AGENTS[session_key].model != req.model:
            memory = MemoryStore(agent_name="AssistantAgent")
            new_agent = Agent(
                model=req.model,
                host=host_url,
                instructions=(
                    "You are a relentless, highly capable autonomous AI agent. When given a task or goal, you never take 'No' "
                    "for an answer and will not stop until the job is completely finished. Proactively use all available tools, "
                    "troubleshoot any errors independently, and deliver finished, verified results without making excuses."
                    + CODEBASE_INSTRUCTIONS
                ),
                tools=[write_file, read_file, list_workspace_files, run_terminal, run_python, web_search, get_realtime_market_quote, delegate_subagent, rag_add_knowledge, rag_search, generate_image_sd_forge, edit_image_sd_forge, edit_image, generate_video_comfyui, github_clone_repo, github_create_branch, github_commit_and_push, github_create_pull_request, github_status, test_ui_playwright, build_android_apk],
                memory=memory,
                stateful=True,
                max_turns=req.max_turns
            )
            # Rehydrate in-memory conversational history from persistent DB
            prior_msgs = memory.get_chat_history(session_id=session_key, limit=30)
            for pm in prior_msgs:
                role = "user" if pm["role"] == "user" else "assistant"
                msg_dict = {"role": role, "content": pm["content"]}
                if role == "user" and pm.get("attachment"):
                    pm_imgs = resolve_multimodal_images(pm["attachment"])
                    if pm_imgs:
                        msg_dict["images"] = pm_imgs
                new_agent.history.append(msg_dict)
            
            SESSION_AGENTS[session_key] = new_agent

        agent = SESSION_AGENTS[session_key]
        agent.max_turns = req.max_turns
        
        # Save user message to persistent DB
        mem = agent.memory or MemoryStore(agent_name="AssistantAgent")
        mem.save_chat_message(session_id=session_key, role="user", content=req.prompt, attachment=req.attachment or "", model=req.model)

        try:
            result = agent.run(req.prompt, max_turns=req.max_turns, images=images if images else None)
        except MaxTurnsExceeded as mte:
            last_out = getattr(mte, 'last_output', '') or ''
            result = (
                f"{last_out}\n\n"
                f"*(Note: Reached turn limit of {mte.turns}. You can ask me to continue or expand on any step above.)*"
            )
        
        # Save agent response to persistent DB
        mem.save_chat_message(session_id=session_key, role="agent", content=result, model=req.model)

        return {"status": "completed", "result": result, "session_id": session_key, "model": req.model}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("startup")
async def on_startup():
    """Pre-warm Gradle daemon on startup for instant APK builds."""
    try:
        from ollama_agents.tools.android_builder import prewarm_gradle_daemon
        prewarm_gradle_daemon()
    except Exception as e:
        logger.debug("Startup Gradle prewarm failed: %s", e)

@app.post("/api/chat/stream")
async def api_chat_stream(req: SingleTaskRequest):
    """Server-Sent Events (SSE) streaming endpoint for real-time agent thoughts, tool calls, and answers."""
    import queue
    import threading
    from ollama_agents.cluster import cluster_manager
    from ollama_agents.tools import (
        write_file, read_file, list_workspace_files, run_terminal, run_python, web_search,
        get_realtime_market_quote, delegate_subagent, rag_add_knowledge,
        rag_search, generate_image_sd_forge, edit_image_sd_forge, edit_image,
        generate_video_comfyui, github_clone_repo, github_create_branch,
        github_commit_and_push, github_create_pull_request, github_status,
        test_ui_playwright, build_android_apk
    )

    session_key = req.session_id or "default_session"
    best_node = cluster_manager.select_best_node_for_model(req.model)
    host_url = best_node.host_url if best_node else None

    # Resolve multimodal images if attachment is provided
    images = resolve_multimodal_images(req.attachment) if req.attachment else []

    if session_key not in SESSION_AGENTS or SESSION_AGENTS[session_key].model != req.model:
        memory = MemoryStore(agent_name="AssistantAgent")
        new_agent = Agent(
            model=req.model,
            host=host_url,
            instructions=(
                "You are a relentless, highly capable autonomous AI agent. When given a task or goal, you never take 'No' "
                "for an answer and will not stop until the job is completely finished. Proactively use all available tools, "
                "troubleshoot any errors independently, and deliver finished, verified results without making excuses."
                + CODEBASE_INSTRUCTIONS
            ),
            tools=[write_file, read_file, list_workspace_files, run_terminal, run_python, web_search, get_realtime_market_quote, delegate_subagent, rag_add_knowledge, rag_search, generate_image_sd_forge, edit_image_sd_forge, edit_image, generate_video_comfyui, github_clone_repo, github_create_branch, github_commit_and_push, github_create_pull_request, github_status, test_ui_playwright, build_android_apk],
            memory=memory,
            stateful=True,
            max_turns=req.max_turns
        )
        prior_msgs = memory.get_chat_history(session_id=session_key, limit=30)
        for pm in prior_msgs:
            role = "user" if pm["role"] == "user" else "assistant"
            msg_dict = {"role": role, "content": pm["content"]}
            if role == "user" and pm.get("attachment"):
                pm_imgs = resolve_multimodal_images(pm["attachment"])
                if pm_imgs:
                    msg_dict["images"] = pm_imgs
            new_agent.history.append(msg_dict)
        SESSION_AGENTS[session_key] = new_agent

    agent = SESSION_AGENTS[session_key]
    agent.max_turns = req.max_turns

    mem = agent.memory or MemoryStore(agent_name="AssistantAgent")
    mem.save_chat_message(session_id=session_key, role="user", content=req.prompt, attachment=req.attachment or "", model=req.model)

    event_queue: queue.Queue = queue.Queue()

    def on_event_callback(event: Dict[str, Any]):
        event_queue.put(event)

    def run_worker():
        try:
            res = agent.run(req.prompt, max_turns=req.max_turns, on_event=on_event_callback, images=images if images else None)
            mem.save_chat_message(session_id=session_key, role="agent", content=res, model=req.model)
            event_queue.put({"type": "done", "result": res, "response": res, "model": req.model})
        except MaxTurnsExceeded as mte:
            last_out = getattr(mte, 'last_output', '') or ''
            res = (
                f"{last_out}\n\n"
                f"*(Note: Reached turn limit of {mte.turns}. You can ask me to continue or expand on any step above.)*"
            )
            mem.save_chat_message(session_id=session_key, role="agent", content=res, model=req.model)
            event_queue.put({"type": "done", "result": res, "response": res, "model": req.model})
        except Exception as err:
            logger.exception("Chat worker failed: %s", err)
            event_queue.put({"type": "error", "error": str(err), "message": str(err), "model": req.model})
        finally:
            event_queue.put({"type": "_stream_closed"})

    worker_thread = threading.Thread(target=run_worker, daemon=True)
    worker_thread.start()

    async def event_generator():
        terminal_event_sent = False
        while True:
            try:
                while not event_queue.empty():
                    item = event_queue.get_nowait()
                    if item.get("type") == "_stream_closed":
                        if not terminal_event_sent:
                            yield f"data: {json.dumps({'type': 'error', 'error': 'Worker terminated unexpectedly', 'message': 'Worker terminated unexpectedly', 'model': req.model})}\n\n"
                            terminal_event_sent = True
                        return
                    yield f"data: {json.dumps(item)}\n\n"
                    if item.get("type") in ("done", "error"):
                        terminal_event_sent = True
                        return
                if not worker_thread.is_alive() and event_queue.empty():
                    if not terminal_event_sent:
                        yield f"data: {json.dumps({'type': 'error', 'error': 'Worker terminated unexpectedly', 'message': 'Worker terminated unexpectedly', 'model': req.model})}\n\n"
                        terminal_event_sent = True
                    return
                await asyncio.sleep(0.08)
            except Exception as e:
                if not terminal_event_sent:
                    yield f"data: {json.dumps({'type': 'error', 'error': str(e), 'message': str(e), 'model': req.model})}\n\n"
                    terminal_event_sent = True
                return

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/chat/history")
def api_get_chat_history(session_id: Optional[str] = "default_session", limit: int = 100):
    """Retrieve full historical chat messages for a session from persistent database."""
    session_key = session_id or "default_session"
    mem = MemoryStore(agent_name="AssistantAgent")
    messages = mem.get_chat_history(session_id=session_key, limit=limit)
    return {"status": "success", "session_id": session_key, "messages": messages}

@app.get("/api/chat/sessions")
def api_list_chat_sessions():
    """List all saved chat sessions with stats."""
    mem = MemoryStore(agent_name="AssistantAgent")
    sessions = mem.list_chat_sessions()
    return {"status": "success", "sessions": sessions}

@app.delete("/api/chat/sessions/{session_id}")
def api_delete_chat_session(session_id: str):
    """Delete a chat session and free memory."""
    if session_id in SESSION_AGENTS:
        SESSION_AGENTS.pop(session_id, None)
    mem = MemoryStore(agent_name="AssistantAgent")
    mem.delete_chat_session(session_id=session_id)
    return {"status": "success", "message": f"Session '{session_id}' deleted."}

@app.post("/api/chat/clear")
def api_clear_chat(session_id: Optional[str] = "default_session"):
    """Clear chat history and reset agent memory for a session."""
    session_key = session_id or "default_session"
    if session_key in SESSION_AGENTS:
        SESSION_AGENTS.pop(session_key, None)
    mem = MemoryStore(agent_name="AssistantAgent")
    mem.clear_chat_history(session_id=session_key)
    return {"status": "success", "message": f"Cleared session agent history for '{session_key}'."}

@app.get("/api/workspace/files")
def api_list_workspace_files():
    """List files in ~/ollama_workspace with metadata for the file explorer tab."""
    workspace = Path.home() / "ollama_workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    files = []

    for p in workspace.rglob("*"):
        if p.is_file():
            rel = p.relative_to(workspace)
            rel_str = str(rel).replace("\\", "/")
            if any(part.startswith(".") or part in ("node_modules", ".gradle", "build", "intermediates") for part in rel.parts[:-1]):
                continue
            stat = p.stat()
            ext = p.suffix.lower().lstrip(".")
            file_type = "apk" if ext == "apk" else ("image" if ext in ("png", "jpg", "jpeg", "webp") else ("code" if ext in ("py", "java", "json", "xml", "js", "html") else "file"))
            files.append({
                "name": p.name,
                "relative_path": rel_str,
                "size": stat.st_size,
                "size_formatted": f"{(stat.st_size / 1024):.1f} KB" if stat.st_size < 1024*1024 else f"{(stat.st_size / (1024*1024)):.2f} MB",
                "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "type": file_type,
                "extension": ext,
                "download_url": f"/workspace/{rel_str}"
            })

    files.sort(key=lambda x: x["modified"], reverse=True)
    return {"status": "success", "workspace_path": str(workspace), "files": files}

@app.get("/api/workspace/file")
def api_get_workspace_file_content(path: str):
    """Read file preview text for code, json, md, etc."""
    workspace = Path.home() / "ollama_workspace"
    target = (workspace / path).resolve()
    if not str(target).startswith(str(workspace.resolve())):
        raise HTTPException(status_code=403, detail="Access denied: outside workspace")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    if target.stat().st_size > 2 * 1024 * 1024:
        return {"filename": target.name, "path": path, "is_binary": True, "content": "(File exceeds preview size limit 2MB. Please download directly.)"}

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        return {"filename": target.name, "path": path, "is_binary": False, "content": content}
    except Exception as e:
        return {"filename": target.name, "path": path, "is_binary": True, "content": f"(Could not read text: {e})"}

@app.delete("/api/workspace/file")
def api_delete_workspace_file(path: str):
    """Delete a workspace file."""
    workspace = Path.home() / "ollama_workspace"
    target = (workspace / path).resolve()
    if not str(target).startswith(str(workspace.resolve())):
        raise HTTPException(status_code=403, detail="Access denied: outside workspace")
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")
    if target.is_file():
        target.unlink()
    elif target.is_dir():
        import shutil
        shutil.rmtree(target)
    return {"status": "success", "message": f"Deleted {path}"}

class ApplyReflectionFixRequest(BaseModel):
    key: str
    content: str
    model: Optional[str] = "deepseek-r1:8b"

@app.get("/api/reflections")
def api_get_reflections(limit: int = 10):
    """Get stored agent self-reflections."""
    mem = MemoryStore()
    return mem.get_reflections(limit=limit)

@app.post("/api/reflections/apply-fix")
def api_apply_reflection_fix(req: ApplyReflectionFixRequest, background_tasks: BackgroundTasks):
    """Automatically convert an agent self-reflection lesson into a live autonomous code fix/optimization goal."""
    registry = GoalRegistry()
    prompt = (
        f"Self-Improvement Auto-Fix based on Reflection [{req.key}]:\n\n"
        f"Reflection Content:\n{req.content}\n\n"
        "Your Task:\n"
        "1. Inspect the codebase, tools, or configuration to locate where the issue described in this reflection occurred.\n"
        "2. Implement the necessary code modifications, refactorings, or tool improvements to permanently resolve this issue.\n"
        "3. Test and verify your changes to confirm the issue is fixed."
    )
    model_name = req.model or "deepseek-r1:8b"
    if model_name == "AutonomousAgent":
        model_name = "deepseek-r1:8b"
        
    goal = registry.create_goal(prompt, model=model_name)
    api_run_goal_task(goal.id, background_tasks, auto_continue=True)
    return {
        "status": "success",
        "message": f"Autonomous auto-fix initiated for reflection '{req.key}'!",
        "goal_id": goal.id
    }

# ── Media Studio Endpoints (SD WebUI Forge & ComfyUI) ─────────────────────────
@app.get("/api/media/status")
def api_media_status(
    forge_url: str = "http://127.0.0.1:7860",
    comfy_url: Optional[str] = None,
    comfyui_url: Optional[str] = None
):
    """Check connectivity and health status of local SD WebUI Forge and ComfyUI services."""
    import urllib.request
    target_comfy = comfy_url or comfyui_url or "http://127.0.0.1:8000"
    
    forge_res = {"online": False, "url": forge_url, "error": None}
    try:
        req = urllib.request.Request(f"{forge_url.rstrip('/')}/sdapi/v1/options", headers={"User-Agent": "OllamaAgents"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status == 200:
                forge_res["online"] = True
    except Exception as e:
        forge_res["error"] = f"Connection refused (offline)"

    comfy_res = {"online": False, "url": target_comfy, "error": None}
    try:
        req = urllib.request.Request(f"{target_comfy.rstrip('/')}/system_stats", headers={"User-Agent": "OllamaAgents"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status == 200:
                comfy_res["online"] = True
    except Exception as e:
        # Also try prompt endpoint if system_stats is unavailable
        try:
            req_prompt = urllib.request.Request(f"{target_comfy.rstrip('/')}/prompt", headers={"User-Agent": "OllamaAgents"})
            with urllib.request.urlopen(req_prompt, timeout=1.5) as resp_p:
                if resp_p.status == 200:
                    comfy_res["online"] = True
        except Exception:
            comfy_res["error"] = f"Connection refused (offline)"

    return {
        "status": "success",
        "forge": forge_res,
        "comfy": comfy_res
    }

@app.delete("/api/media/{filename}")
def api_media_delete(filename: str, media_type: str = "all"):
    """Delete a generated image or video."""
    workspace = Path.home() / "ollama_workspace"
    img_path = workspace / "images" / filename
    vid_path = workspace / "videos" / filename
    
    deleted = False
    if img_path.exists() and img_path.is_file():
        img_path.unlink()
        deleted = True
    elif vid_path.exists() and vid_path.is_file():
        vid_path.unlink()
        deleted = True
        
    if deleted:
        return {"status": "success", "message": f"Deleted {filename}"}
    else:
        raise HTTPException(status_code=404, detail="File not found")

@app.get("/api/media/gallery")
def api_media_gallery(media_type: str = "all"):
    """List all generated images and videos saved in ~/ollama_workspace/."""
    workspace = Path.home() / "ollama_workspace"
    img_dir = workspace / "images"
    vid_dir = workspace / "videos"
    img_dir.mkdir(parents=True, exist_ok=True)
    vid_dir.mkdir(parents=True, exist_ok=True)

    images = []
    if media_type in ("all", "images", "image"):
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp"):
            for p in img_dir.glob(ext):
                try:
                    stat = p.stat()
                    images.append({
                        "name": p.name,
                        "url": f"/workspace/images/{p.name}",
                        "size": stat.st_size,
                        "size_formatted": f"{(stat.st_size / 1024):.1f} KB" if stat.st_size < 1024*1024 else f"{(stat.st_size / (1024*1024)):.2f} MB",
                        "modified": float(stat.st_mtime),
                        "modified_formatted": datetime.fromtimestamp(stat.st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                        "type": "image"
                    })
                except Exception:
                    pass
        images.sort(key=lambda x: x["modified"], reverse=True)

    videos = []
    if media_type in ("all", "videos", "video"):
        for ext in ("*.mp4", "*.webm", "*.mov", "*.gif"):
            for p in vid_dir.glob(ext):
                try:
                    stat = p.stat()
                    videos.append({
                        "name": p.name,
                        "url": f"/workspace/videos/{p.name}",
                        "size": stat.st_size,
                        "size_formatted": f"{(stat.st_size / (1024*1024)):.2f} MB",
                        "modified": float(stat.st_mtime),
                        "modified_formatted": datetime.fromtimestamp(stat.st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                        "type": "video"
                    })
                except Exception:
                    pass
        videos.sort(key=lambda x: x["modified"], reverse=True)

    return {"status": "success", "images": images, "videos": videos}

@app.post("/api/media/generate-image")
def api_media_generate_image(payload: Dict[str, Any]):
    """Trigger txt2img generation via local SD WebUI Forge."""
    import re
    from ollama_agents.tools import generate_image_sd_forge
    prompt = payload.get("prompt", "")
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")
    api_url = payload.get("api_url", "http://127.0.0.1:7860")
    res = generate_image_sd_forge(
        prompt=prompt,
        negative_prompt=payload.get("negative_prompt", ""),
        width=int(payload.get("width", 1024)),
        height=int(payload.get("height", 1024)),
        steps=int(payload.get("steps", 5)),
        cfg_scale=float(payload.get("cfg_scale", 1.0)),
        api_url=api_url
    )
    if "Error connecting" in res or "Error:" in res or not res.startswith("[SD WebUI Forge Image Generated Successfully]"):
        return {"status": "error", "message": res, "file_path": None, "filename": None, "url": None}
    
    match = re.search(r"/workspace/images/([^)\s]+)", res)
    filename = match.group(1) if match else None
    if not filename:
        match_fn = re.search(r"forge_gen_[0-9_]+\.png", res)
        filename = match_fn.group(0) if match_fn else "generated_image.png"
    
    file_path = str(Path.home() / "ollama_workspace" / "images" / filename)
    url = f"/workspace/images/{filename}"
    return {
        "status": "success",
        "file_path": file_path,
        "filename": filename,
        "url": url,
        "message": res
    }

@app.post("/api/media/edit-image")
def api_media_edit_image(payload: Dict[str, Any]):
    """Trigger img2img transformation via local SD WebUI Forge."""
    import re
    from ollama_agents.tools import edit_image_sd_forge
    filepath = payload.get("image_path", payload.get("filepath", ""))
    
    # Handle optional image_base64 payload
    img_b64 = payload.get("image_base64")
    if img_b64 and not filepath:
        try:
            uploads_dir = Path.home() / "ollama_workspace" / "uploads"
            uploads_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            raw_b64 = img_b64.split(",")[-1] if "," in img_b64 else img_b64
            saved_file = uploads_dir / f"edit_input_{ts}.png"
            saved_file.write_bytes(base64.b64decode(raw_b64))
            filepath = f"uploads/edit_input_{ts}.png"
        except Exception as e:
            return {"status": "error", "message": f"Failed to save base64 input image: {e}", "file_path": None, "filename": None, "url": None}

    prompt = payload.get("prompt", "")
    if not filepath or not prompt:
        raise HTTPException(status_code=400, detail="image_path and prompt are required")
    api_url = payload.get("api_url", "http://127.0.0.1:7860")
    res = edit_image_sd_forge(
        filepath=filepath,
        prompt=prompt,
        negative_prompt=payload.get("negative_prompt", "blurry, low quality, distorted, bad anatomy"),
        denoising_strength=float(payload.get("denoising_strength", 0.75)),
        steps=int(payload.get("steps", 5)),
        api_url=api_url
    )
    if "Error" in res or not res.startswith("[SD WebUI Forge Image Edited Successfully]"):
        return {"status": "error", "message": res, "file_path": None, "filename": None, "url": None}
    
    match = re.search(r"/workspace/images/([^)\s]+)", res)
    filename = match.group(1) if match else None
    if not filename:
        match_fn = re.search(r"forge_edit_[0-9_]+\.png", res)
        filename = match_fn.group(0) if match_fn else "edited_image.png"

    file_path = str(Path.home() / "ollama_workspace" / "images" / filename)
    url = f"/workspace/images/{filename}"
    return {
        "status": "success",
        "file_path": file_path,
        "filename": filename,
        "url": url,
        "message": res
    }

@app.post("/api/media/generate-video")
def api_media_generate_video(payload: Dict[str, Any]):
    """Trigger video generation via local ComfyUI API."""
    import re
    from ollama_agents.tools import generate_video_comfyui
    prompt = payload.get("prompt", "")
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")
    api_url = payload.get("api_url", "http://127.0.0.1:8000")
    res = generate_video_comfyui(
        prompt=prompt,
        negative_prompt=payload.get("negative_prompt", "blurry, low quality, distorted, static, jittery"),
        width=int(payload.get("width", 512)),
        height=int(payload.get("height", 512)),
        frames=int(payload.get("frames", 16)),
        fps=int(payload.get("fps", 8)),
        api_url=api_url,
        init_image=payload.get("init_image", None),
        denoise=float(payload.get("denoise", 0.75))
    )
    if "Error" in res or not res.startswith("[ComfyUI Video Generated Successfully]"):
        return {"status": "error", "message": res, "file_path": None, "filename": None, "url": None}
    
    match = re.search(r"/workspace/videos/([^)\s]+)", res)
    filename = match.group(1) if match else None
    if not filename:
        match_fn = re.search(r"comfy_vid_[^\s\)]+", res)
        filename = match_fn.group(0) if match_fn else "generated_video.mp4"

    file_path = str(Path.home() / "ollama_workspace" / "videos" / filename)
    url = f"/workspace/videos/{filename}"
    return {
        "status": "success",
        "file_path": file_path,
        "filename": filename,
        "url": url,
        "message": res
    }

# ── Serve Dashboard UI & Workspace Media Static Files ────────────────────────
WORKSPACE_DIR = Path.home() / "ollama_workspace"
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/workspace", StaticFiles(directory=str(WORKSPACE_DIR)), name="workspace")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)

@app.get("/", response_class=HTMLResponse)
def index():
    html_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(html_file):
        with open(html_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Ollama Agents Web Dashboard - Front end loading...</h1>"


