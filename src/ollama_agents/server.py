"""
FastAPI Server Backend for Ollama Agents Web Dashboard.
"""

import os
import json
import asyncio
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ollama_agents import Agent, GoalRegistry, MemoryStore

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
    max_turns: int = 25

class CreateGoalRequest(BaseModel):
    prompt: str
    model: str = "deepseek-r1:8b"

# ── API Endpoints ─────────────────────────────────────────────────────────────
@app.get("/api/models")
def api_list_models():
    """List all available Ollama models installed locally on the machine."""
    import ollama
    try:
        models_data = ollama.list()
        raw_models = getattr(models_data, 'models', models_data.get('models', []))
        names = []
        for m in raw_models:
            name = getattr(m, 'model', getattr(m, 'name', None))
            if not name and isinstance(m, dict):
                name = m.get('model', m.get('name'))
            if name:
                names.append(str(name))
        return {"models": names if names else ["deepseek-r1:8b", "llama3.1:latest"]}
    except Exception as e:
        return {"models": ["deepseek-r1:8b", "llama3.1:latest"], "error": str(e)}

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
        "tasks_count": len(g.tasks),
        "tasks": [t.__dict__ for t in g.tasks]
    } for g in goals]

@app.post("/api/goals/create")
def api_create_goal(req: CreateGoalRequest):
    """Decompose and save a new goal."""
    registry = GoalRegistry()
    goal = registry.create_goal(req.prompt, model=req.model)
    return {"status": "success", "goal": goal.__dict__, "tasks": [t.__dict__ for t in goal.tasks]}

@app.post("/api/goals/{goal_id}/run")
def api_run_goal_task(goal_id: str, background_tasks: BackgroundTasks):
    """Trigger the next task of a goal in the background."""
    registry = GoalRegistry()
    goal = registry.get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    def _execute():
        from ollama_agents.tools import web_search, get_realtime_market_quote, write_file, read_file, run_terminal, run_python
        model_name = getattr(goal, 'agent_name', getattr(goal, 'model', 'deepseek-r1:8b'))
        if model_name == "AutonomousAgent" or not model_name:
            model_name = "deepseek-r1:8b"
        agent = Agent(
            model=model_name,
            tools=[write_file, read_file, run_terminal, run_python, web_search, get_realtime_market_quote],
            max_turns=25
        )
        agent.run_goal(goal_id)

    background_tasks.add_task(_execute)
    return {"status": "started", "message": f"Execution started for goal {goal_id}"}

@app.post("/api/task/run")
def api_run_single_task(req: SingleTaskRequest):
    """Run a single task synchronously and return the result."""
    try:
        from ollama_agents.tools import web_search, get_realtime_market_quote, write_file, read_file, run_terminal, run_python
        agent = Agent(
            model=req.model,
            tools=[write_file, read_file, run_terminal, run_python, web_search, get_realtime_market_quote],
            max_turns=req.max_turns
        )
        result = agent.run(req.prompt)
        return {"status": "completed", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/reflections")
def api_get_reflections(limit: int = 10):
    """Get stored agent self-reflections."""
    mem = MemoryStore()
    return mem.get_reflections(limit=limit)

# ── Serve Dashboard UI ────────────────────────────────────────────────────────
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
