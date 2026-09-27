# Ollama Agents — Codebase Knowledge Document
> Last updated: 2026-09-27

## Project Overview
**Ollama Agents** is a Level 4 Autonomous AI Agent framework powered by local Ollama models. It provides:
- A FastAPI web dashboard with real-time SSE streaming chat
- Multi-session long-horizon goal management with task decomposition
- Multi-laptop distributed cluster coordination
- Tool execution (file I/O, terminal, web search, code execution, image/video gen, GitHub, Android APK building)
- RAG vector memory, self-improvement reflections, and skill registry
- CLI interface via Typer + Rich

## Architecture

```
src/ollama_agents/
├── __init__.py          # Package exports: Agent, GoalRegistry, MemoryStore, Tool
├── agent.py             # Core ReAct agent loop (Thought→Action→Observation), run() and run_goal()
├── server.py            # FastAPI backend — REST + WebSocket + SSE endpoints
├── planner.py           # Goal decomposition into subtasks via LLM (Planner class)
├── goal.py              # Goal/GoalTask dataclasses + GoalRegistry persistence (~/.ollama_agents/goals/)
├── orchestrator.py      # Multi-agent workflows (sequential/parallel) + model routing (NOT used by server)
├── cli.py               # Typer CLI: run, goal create/list/run, kill-all, serve
├── memory.py            # MemoryStore — chat history persistence per session (~/.ollama_agents/memory/)
├── memory_manager.py    # RAM/VRAM monitoring, concurrency slots, garbage collection
├── model_selector.py    # Auto-select best local model by task type, HuggingFace search
├── skills.py            # SkillRegistry — persistent skill blueprints (~/.ollama_agents/skills/)
├── checkpoint.py        # CheckpointManager — save/restore agent state mid-execution
├── critic.py            # Critic model for quality-gating agent outputs
├── exceptions.py        # MaxTurnsExceeded exception
├── tool.py              # Tool wrapper — converts Python functions to Ollama function schemas
├── tool_synthesizer.py  # Dynamic runtime tool creation from Python code
├── rag.py               # VectorRAGStore — chromadb-based semantic search
├── vector_memory.py     # Alternative vector memory implementation
├── distributed_compute.py # Distributed task scheduling
├── cluster.py           # ClusterManager — multi-node Ollama coordination
├── worker_node.py       # Worker node for distributed execution
├── static/
│   └── index.html       # Single-page dashboard UI (vanilla HTML/CSS/JS, 2592 lines)
├── tools/
│   ├── __init__.py      # Re-exports all tools
│   ├── actions.py       # Core tools: read_url, run_python, write_file, read_file, run_terminal, 
│   │                    #   delegate_subagent, rag_add_knowledge, rag_search, synthesize_new_tool
│   ├── search.py        # web_search via DuckDuckGo
│   ├── finance.py       # get_realtime_market_quote
│   ├── image_gen.py     # generate_image_sd_forge, edit_image_sd_forge, edit_image
│   ├── comfyui.py       # generate_video_comfyui
│   ├── github.py        # github_clone_repo, github_create_branch, github_commit_and_push, etc.
│   ├── playwright_testing.py  # test_ui_playwright
│   ├── android_builder.py     # build_android_apk
│   └── code_exec.py     # Additional code execution utilities
└── mcp/
    ├── __init__.py
    └── kite.py           # MCP Kite integration
```

## Key Data Flows

### Chat Flow (Interactive)
```
User → POST /api/chat/stream → SSE StreamingResponse
  → server.py creates/reuses session Agent
  → Agent.run() → ReAct loop (Thought→Action→Observation)
  → Streams events: thought, tool_start, tool_end, final_answer
```

### Multi-Session Goal Flow
```
User → POST /api/goals/create → GoalRegistry.create_goal()
  → Planner.hierarchical_decompose() → numbered task list
  → Goal + GoalTasks saved to ~/.ollama_agents/goals/<id>.json

User → POST /api/goals/{id}/run?auto_continue=true
  → BackgroundTasks._execute() while loop:
    → Agent.run_goal(goal_id) → executes ONE task per call
    → Marks task complete, loops to next task
    → When all done, generates final synthesis summary
```

### Workspace
- All agent file operations sandbox to `~/ollama_workspace/`
- Files endpoint: GET /api/workspace/files
- File preview: GET /api/workspace/file?path=...
- File delete: DELETE /api/workspace/file?path=...
- Upload: POST /api/upload → ~/ollama_workspace/uploads/

## Key Configuration
- Default model: `deepseek-r1:8b`
- Ollama host: `OLLAMA_HOST` env var or `http://127.0.0.1:11434`
- Agent timeout: 30s (ollama.Client)
- Max turns: 50 (default)
- Goal storage: `~/.ollama_agents/goals/`
- Skills storage: `~/.ollama_agents/skills/`
- Memory storage: `~/.ollama_agents/memory/`
- Workspace: `~/ollama_workspace/`

## Frontend (index.html) Tabs
1. **💬 Interactive Chat** — SSE streaming chat with model/turn selectors, file upload, voice input
2. **🎯 Multi-Session Goals** — Create goals, view sub-task breakdown, run tasks, follow-up questions
3. **📁 Files & Artifacts** — Workspace file tree explorer with search, preview, download, delete
4. **🎨 Media Studio** — SD Forge image gen/edit, ComfyUI video gen
5. **🖥️ Cluster Nodes** — Multi-laptop distributed cluster management
6. **🧠 Self-Improvement** — Agent reflection logs
7. **🤗 Hugging Face Models** — Search/pull GGUF models

## Important Patterns
- `Goal.id` (NOT `goal_id`) — the unique identifier field
- `GoalTask.description` (NOT `title`) — the task text field
- `Goal.agent_name` — stores "AutonomousAgent" by default (should also store model)
- `agent.run_goal()` returns a single `str` (NOT a tuple)
- Tools must be explicitly passed to Agent() constructor
- `allWorkspaceFiles` — JS global holding cached file list from API
- `openFolders` — JS Set tracking which folder paths are expanded in file tree
- `SESSION_AGENTS` — server-side dict of active Agent instances per chat session
- `ACTIVE_EXECUTIONS` — server-side dict tracking running goal background tasks

## Known Fixed Issues (2026-09-27)
1. ✅ File search now renders flat list during search (no folder explosion) + glob support (*.py, *.apk)
2. ✅ Planner timeout increased 8s→60s, prompt improved for 5-8 granular sub-tasks, num_ctx 2048→4096
3. ✅ Goal.model field added, server uses it instead of always defaulting to deepseek-r1:8b
4. ✅ Infinite loop on MaxTurnsExceeded fixed — task marked failed after stuck detection
5. ✅ CLI: goal.goal_id→goal.id, t.title→t.description throughout
6. ✅ CLI: run_goal return unpacking fixed (str, not tuple)
7. ✅ CLI: Agent now created with tools
8. ✅ Duplicate /api/workspace/files endpoint removed
9. ✅ Goal polling preserves follow-up input values and cursor position
10. ✅ Glob pattern support (*.apk, *.py, report_*) in workspace file search
11. ✅ Planner host URL forwarded to short_client
12. ✅ Skill generation timeout increased 4s→30s
- Duplicate SingleTaskRequest class definition removed from server.py
