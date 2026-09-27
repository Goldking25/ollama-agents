# Detailed Specification & Status Survey: Media Studio, Core Tab APIs, and Integration Test Suite

**Document Version:** 1.0.0  
**Author:** survey_spec_miner_3 (Teamwork Specification Miner)  
**Date:** 2026-09-26  
**Reference Document:** `ORIGINAL_REQUEST.md` (Follow-up R1, R2, R3, R4, Acceptance Criteria)  
**Workspace:** `e:\Learning\Python\agent_test`

---

## 1. Executive Summary

This specification survey investigates the architecture, authoritative interface contracts, current implementation state, and concrete technical gaps across three critical pillars of the Level 4 Ollama Agents framework:
1. **Media Studio (SD Forge & ComfyUI Pipelines)**: Stable Diffusion WebUI Forge (ports 7860/default) and ComfyUI (ports 8188/8000/default) image generation/editing and prompt-driven video generation, connection diagnostic indicators, storage in `~/ollama_workspace/images/` and `~/ollama_workspace/videos/`, and interactive in-browser playback/gallery.
2. **Core Tab APIs**: `/api/goals` (multi-session decomposition, sub-task tracking, APK build triggers), `/api/workspace/files` (recursive browsing, preview modal, binary downloads), `/api/cluster/nodes` & `/ws/cluster` (WebSocket heartbeat, node health, latency pinging, routing), `/api/reflections` (episodic memory, storage, query), `/api/system/stats`, and model discovery endpoints.
3. **Automated Integration Test Suite**: Verification requirements and gap analysis for `tests/test_all_tabs_and_endpoints.py` covering all REST endpoints, WebSockets, SSE streams, multimodal attachments, and tool executions.

---

## 2. Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | Media Studio | SD Forge Txt2Img Tool | Generates FLUX/SDXL images using local SD WebUI Forge txt2img API | `prompt`, `negative_prompt`, `width` (1024), `height` (1024), `steps` (5), `cfg_scale` (1.0), `distill_cfg` (1.0), `sampler_name` ('Euler'), `scheduler` ('Beta'), `api_url` ('http://127.0.0.1:7860') | Markdown string with local file path `~/ollama_workspace/images/forge_gen_*.png` and relative URL `/workspace/images/...` | Returns error message string if `httpx` missing, HTTP != 200, no images, or connection refused | `src/ollama_agents/tools/image_gen.py:16` |
| 2 | Media Studio | SD Forge Img2Img Tool | Transforms existing uploaded image using SD WebUI Forge img2img API | `filepath` (relative or absolute), `prompt`, `negative_prompt`, `denoising_strength` (0.75), `cfg_scale` (1.0), `distill_cfg` (1.0), `steps` (5), `api_url` ('http://127.0.0.1:7860') | Markdown string with local file path `~/ollama_workspace/images/forge_edit_*.png` and relative URL `/workspace/images/...` | Returns error if input file not found or if Forge API is unreachable (HTTP error or connection timeout) | `src/ollama_agents/tools/image_gen.py:86` |
| 3 | Media Studio | ComfyUI Video Gen Tool | Submits workflow graph to ComfyUI, polls history for completion, downloads rendered MP4/GIF | `prompt`, `negative_prompt`, `width` (512), `height` (512), `frames` (16), `fps` (8), `api_url` ('http://127.0.0.1:8000'), `workflow_json` (optional) | Markdown string with file path `~/ollama_workspace/videos/comfy_vid_*.mp4` and relative URL `/workspace/videos/...` | Returns error if `httpx` missing, prompt submit fails, rendering times out (>360s), or download fails | `src/ollama_agents/tools/comfyui.py:17` |
| 4 | Media Studio | Media Studio Tab UI | Dedicated UI tab for image/video generation with live status badges and gallery | User inputs: URLs, prompts, dimensions, uploaded files | Interactive view pane with status badges, generation forms, and media gallery | Currently **MISSING** from `src/ollama_agents/static/index.html` | `ORIGINAL_REQUEST.md:53-58,74,77` |
| 5 | Media Studio | Media Backend REST APIs | Direct REST endpoints for health check, txt2img, img2img, and video generation from UI | HTTP POST/GET payloads with generation parameters and API URLs | JSON response with job status, output path, and media URL | Currently **MISSING** from `src/ollama_agents/server.py` | `ORIGINAL_REQUEST.md:53-58,77` |
| 6 | Core Tab: Goals | List Goals (`GET /api/goals`) | Returns list of persistent long-horizon goals with subtasks, progress, and summaries | None (HTTP GET) | JSON Array of objects: `goal_id`, `title`, `model`, `created_at`, `progress_pct`, `final_summary`, `tasks_count`, `tasks` | Returns empty array `[]` if no goals exist | `src/ollama_agents/server.py:219`, `goal.py:360` |
| 7 | Core Tab: Goals | Create Goal (`POST /api/goals/create`) | Decomposes prompt into ordered atomic subtasks via `Planner` and saves to registry | `CreateGoalRequest(prompt, model)` | `{"status": "success", "goal": {...}, "tasks": [...]}` | Falls back to default 3-stage breakdown if LLM decomposition fails | `src/ollama_agents/server.py:235`, `goal.py:385` |
| 8 | Core Tab: Goals | Run Goal (`POST /api/goals/{goal_id}/run`) | Executes goal subtasks sequentially in background; auto-continues across tasks | Path `goal_id`, Query `auto_continue` (bool, default True) | `{"status": "started", "message": "..."}` or `{"status": "already_running"}` | HTTP 404 if goal not found; fails task with reason on unhandled exception | `src/ollama_agents/server.py:245` |
| 9 | Core Tab: Goals | Followup Task (`POST /api/goals/{goal_id}/followup`) | Appends a follow-up subtask to an existing goal and optionally executes immediately | Path `goal_id`, Body `FollowupRequest(prompt, auto_run)` | `{"status": "success", "task": {...}, "execution": ...}` | HTTP 404 if goal not found, HTTP 500 if append fails | `src/ollama_agents/server.py:106`, `goal.py:189` |
| 10 | Core Tab: Goals | Kill Goal (`POST /api/goals/{goal_id}/kill`) | Halts active background execution loop for a specific goal; resets in-progress tasks | Path `goal_id` | `{"status": "killed", "message": "..."}` | Removes goal from active execution registry; safe no-op if idle | `src/ollama_agents/server.py:330` |
| 11 | Core Tab: Goals | Delete Goal (`DELETE /api/goals/{goal_id}`) | Terminates active execution and permanently deletes goal JSON storage | Path `goal_id` | `{"status": "success", "message": "..."}` | HTTP 404 if goal not found or cannot be deleted | `src/ollama_agents/server.py:345` |
| 12 | Core Tab: Goals | Emergency Kill All (`POST /api/tasks/kill-all`) | Halts all active background tasks across all goals | None (HTTP POST) | `{"status": "success", "message": "Cleared X active tasks."}` | Iterates all goals, marks `in_progress` tasks as failed, clears registry | `src/ollama_agents/server.py:357` |
| 13 | Core Tab: Goals | Android APK Compilation Tool | Compiles Android Java app via Gradle in `~/ollama_workspace/HelloWorldAndroidApp` | `app_name`, `main_activity_code`, `package_name`, `output_filename` ('app-debug.apk') | Markdown with file path, size, download URL `/workspace/app-debug.apk` | Returns error message with stdout/stderr on exit code != 0 or missing tools | `src/ollama_agents/tools/android_builder.py:21` |
| 14 | Core Tab: Files | Workspace Files Listing (`GET /api/workspace/files`) | Lists files and generated artifacts in `~/ollama_workspace/` recursively | None (HTTP GET) | `{"status": "success", "workspace_path": "...", "files": [{name, relative_path, size, size_formatted, modified, type, extension, download_url}]}` | Duplicate route bug in `server.py`: line 88 shadows line 561! | `src/ollama_agents/server.py:88,561` |
| 15 | Core Tab: Files | File Preview (`GET /api/workspace/file`) | Reads text preview of workspace files (code, json, md) under 2MB | Query `path` (relative workspace path) | `{"filename": "...", "path": "...", "is_binary": bool, "content": "..."}` | HTTP 403 if path traverses outside workspace; HTTP 404 if file missing | `src/ollama_agents/server.py:591` |
| 16 | Core Tab: Files | Delete File (`DELETE /api/workspace/file`) | Deletes workspace file or directory | Query `path` (relative workspace path) | `{"status": "success", "message": "Deleted ..."}` | HTTP 403 if path outside workspace; HTTP 404 if file missing | `src/ollama_agents/server.py:610` |
| 17 | Core Tab: Files | File Upload (`POST /api/upload`) | Uploads file/image to `~/ollama_workspace/uploads/` for multimodal or editing use | Multipart Form `file` | `{"status": "success", "filename": "...", "filepath": "uploads/...", "full_path": "...", "size": ...}` | HTTP 500 on filesystem write failure | `src/ollama_agents/server.py:193` |
| 18 | Core Tab: Cluster | Cluster Nodes Status (`GET /api/cluster/nodes`) | Pings all nodes, queries `/api/tags` and `/api/ps`, aggregates active models & VRAM | None (HTTP GET) | `{"total_nodes": int, "active_nodes": int, "aggregate_models": [...], "nodes": [...]}` | Unreachable nodes marked `active: false`, latency set to 0 | `src/ollama_agents/server.py:74`, `cluster.py:164` |
| 19 | Core Tab: Cluster | Add Cluster Node (`POST /api/cluster/nodes/add`) | Adds a remote laptop/computer running Ollama by IP/URL and discovers models | Body `AddNodeRequest(host_url, name)` | `{"status": "success"|"warning", "message": "...", "node": {...}}` | Returns warning status if host unreachable but registers node | `src/ollama_agents/server.py:80`, `cluster.py:115` |
| 20 | Core Tab: Cluster | WebSocket Heartbeat (`/ws/cluster`) | Bidirectional WebSocket broadcasting live cluster telemetry every 2.5s | None (WebSocket connect) | Stream of JSON messages: `{"type": "cluster_status", "data": {...}}` | Gracefully closes on `WebSocketDisconnect` or client drop | `src/ollama_agents/server.py:59` |
| 21 | Core Tab: Cluster | mDNS Auto-Discovery | Background UDP listener on port 9999 receiving `OLLAMA_WORKER_ANNOUNCE` packets | UDP Broadcast packets | Automatically registers remote workers into `DistributedClusterManager` | Logs warning if port 9999 cannot be bound; runs in daemon thread | `src/ollama_agents/cluster.py:129` |
| 22 | Core Tab: Reflections | Get Reflections (`GET /api/reflections`) | Retrieves episodic memory reflections and scratchpad notes | Query `limit` (default 10) | JSON Array of objects: `[{"key": "...", "content": "..."}]` | Returns empty array if no reflections exist | `src/ollama_agents/server.py:626`, `memory.py:287` |
| 23 | Core Tab: Reflections | Auto-Reflection & Skill Refinement | Post-run loop generating lessons and auto-updating skill definitions | Agent execution result & prompt | Saves to `facts` (tag='reflection') and updates `SkillRegistry` instructions | Non-critical: failure logged without breaking agent run | `src/ollama_agents/agent.py:339`, `planner.py:253` |
| 24 | Core Tab: System | System Stats (`GET /api/system/stats`) | Returns real-time RAM %, CPU %, active subagents count, and NVIDIA GPU VRAM | None (HTTP GET) | `{"ram_total_gb": float, "ram_available_gb": float, "ram_used_pct": float, "cpu_used_pct": float, "active_agents": int, "max_concurrent": int, "gpu": {...}}` | Safe fallback if `nvidia-smi` is not installed or errors | `src/ollama_agents/server.py:142`, `memory_manager.py:95` |
| 25 | Core Tab: System | Force GC (`POST /api/system/gc`) | Explicitly invokes Python garbage collection and returns freed memory metrics | None (HTTP POST) | `{"collected_objects": int, "free_ram_gb": float, "vram_free_gb": float}` | Safe synchronous execution | `src/ollama_agents/server.py:148`, `memory_manager.py:153` |
| 26 | Core Tab: Chat | SSE Chat Streaming (`POST /api/chat/stream`) | Server-Sent Events stream for agent thoughts, tool execution events, and final answers | `SingleTaskRequest(prompt, model, max_turns, session_id, attachment)` | SSE event stream: `data: {"type": "thought"|"tool_call"|"done"|"error", ...}` | Yields error event on exception; terminates on done event | `src/ollama_agents/server.py:445` |
| 27 | Core Tab: Chat | Chat History (`GET /api/chat/history`) | Fetches persistent chat history for a session from SQLite | Query `session_id`, `limit` | `{"status": "success", "session_id": "...", "messages": [...]}` | Returns empty messages list if new session | `src/ollama_agents/server.py:527`, `memory.py:199` |
| 28 | Core Tab: Chat | Chat Sessions (`GET /api/chat/sessions`) | Lists all saved chat sessions with message counts and timestamps | None (HTTP GET) | `{"status": "success", "sessions": [...]}` | Returns empty list if no sessions | `src/ollama_agents/server.py:535`, `memory.py:224` |
| 29 | Core Tab: Chat | Delete Session (`DELETE /api/chat/sessions/{session_id}`) | Deletes chat history and unloads cached agent from memory | Path `session_id` | `{"status": "success", "message": "..."}` | Removes session agent from memory cache and rows from SQLite | `src/ollama_agents/server.py:542` |
| 30 | Core Tab: Models | Models List (`GET /api/models` vs `/api/models/installed`) | Lists local Ollama models; acceptance criteria requires `/api/models/installed` | None (HTTP GET) | `{"models": [...], "pulling": [...]}` | Falls back to default models if local Ollama daemon unreachable | `src/ollama_agents/server.py:124`, `ORIGINAL_REQUEST.md:81` |
| 31 | Test Suite | Integration Test Suite | Comprehensive automated integration test covering all endpoints & workflows | Test runners (`pytest` or standalone `python tests/...`) | Exit code 0, all tests pass | Currently **MISSING**: neither `tests/` nor `test_all_tabs_and_endpoints.py` exists | `ORIGINAL_REQUEST.md:68,80` |

---

## 3. Edge Cases

| # | Feature | Input | Observed Behavior |
|---|---------|-------|-------------------|
| 1 | Media Studio (SD Forge) | Port 7860 offline or SD Forge not running with `--api` | `generate_image_sd_forge` catches `httpx.ConnectError` and returns: `"Error connecting to SD WebUI Forge API at 'http://127.0.0.1:7860': ConnectError: ... Make sure SD WebUI Forge is running with '--api' flag."` |
| 2 | Media Studio (SD Forge Img2Img) | Non-existent input image path (e.g. `'uploads/missing.png'`) | Validates local existence before making API call, returning immediately: `"Image file not found: 'uploads/missing.png'. Upload the image first."` |
| 3 | Media Studio (ComfyUI) | Port 8000/8188 offline or ComfyUI service unavailable | `generate_video_comfyui` catches connection error and returns: `"Error connecting to ComfyUI API at 'http://127.0.0.1:8000': ... Make sure ComfyUI Desktop is running on port 8000."` |
| 4 | Media Studio (ComfyUI) | Prompt accepted but workflow rendering takes >360s | History polling times out at 360 seconds, returning: `"[ComfyUI Task Queued]: Prompt ID '...' was submitted to ComfyUI at ... Rendering is still in progress."` |
| 5 | Workspace Files | Client requests `GET /api/workspace/files` | FastAPI executes the first defined route at line 88 rather than line 561. Line 88 returns `{ "workspace_path": "...", "files": [{ "name": ..., "relative_path": ..., "full_path": ..., "url": ..., "size_bytes": ... }] }`, missing `status`, `type`, `size_formatted`, `modified`, and `download_url`. The frontend file table receives `undefined` for type and modified time. |
| 6 | Workspace Preview | Path traversal attempt (e.g. `GET /api/workspace/file?path=../../etc/passwd` or `../secrets.env`) | Path is resolved and compared against `workspace.resolve()`. If outside workspace, returns HTTP 403 with `{"detail": "Access denied: outside workspace"}`. |
| 7 | Workspace Preview | File exceeds 2MB size limit | Returns HTTP 200 with `{"filename": "...", "path": "...", "is_binary": True, "content": "(File exceeds preview size limit 2MB. Please download directly.)"}`. |
| 8 | Goals Decomposition | Ollama model times out or returns non-numbered list | `Planner.hierarchical_decompose` catches timeout/exception after 8.0s and returns a guaranteed 3-stage actionable plan fallback, preventing UI freeze. |
| 9 | Goals Execution | Goal task fails midway through execution | `fail_task` records failure reason (first 300 chars) into SQLite/JSON registry, halts further execution loop, and logs error. |
| 10 | Goals Kill Switch | User hits Kill Switch while goal is running | `ACTIVE_EXECUTIONS.pop(goal_id)` terminates execution loop on next iteration and marks in-progress tasks as cancelled. |
| 11 | Cluster WebSocket | Client closes browser tab or network drops | `websocket_cluster_stream` catches `WebSocketDisconnect` and silently exits loop without crashing FastAPI. |
| 12 | Cluster Node Ping | Secondary node IP specified without protocol or port (e.g. `192.168.1.50`) | `DistributedClusterManager.add_node` sanitizes URL, prepends `http://` and appends `:11434`, then pings node with 3.5s timeout. |
| 13 | Chat Stream (SSE) | Model exceeds max turn reasoning limit without Final Answer | `MaxTurnsExceeded` exception is caught, user is returned partial answer plus continuation notice, and SSE stream emits `{"type": "done", "result": ..., "model": ...}`. |
| 14 | Model Listing | Acceptance criteria tests `/api/models/installed` | FastAPI returns HTTP 404 because currently only `/api/models` is routed. |
| 15 | Multimodal Chat | User attaches image file to chat message | Attachment path is recorded in SQLite chat history, but `agent.run(req.prompt)` does NOT receive image bytes/path, and Ollama chat payload does not populate the `images` field. |

---

## 4. Deep-Dive: Media Studio (SD Forge & ComfyUI)

### 4.1. Requirements & Spec Source
From `ORIGINAL_REQUEST.md`:
- **R2. Dedicated Media Studio Tab & Resilient Forge/ComfyUI Pipelines**:
  - Dedicated, fully functional Media Studio tab in the Web Dashboard UI (`index.html`).
  - Image generation and editing via Stable Diffusion WebUI Forge API (default port 7860).
  - Video generation via ComfyUI API (ports 8188 / 8000 / default).
  - Live visual connection health indicators: Online / Offline diagnostic badges with configurable API URL inputs for both SD Forge and ComfyUI.
  - Support direct txt2img generation, image-to-image editing with uploaded image references, and prompt-driven video generation.
  - Save all generated visual media directly into `~/ollama_workspace/images/` and `~/ollama_workspace/videos/`.
  - Immediate in-browser playback, downloads, and interactive gallery views.
- **Acceptance Criteria**:
  - Every tab in the header (`chat`, `goals`, `files`, `cluster`, `reflections`, `hfmodels`, and `media`) renders its view pane without JavaScript errors or broken layout states.
  - Media Studio displays live status for SD Forge and ComfyUI, accepts generation and edit prompts, and renders generated images and videos in the workspace gallery.

### 4.2. Existing Codebase Implementation

#### A. Stable Diffusion WebUI Forge Tool (`src/ollama_agents/tools/image_gen.py`)
- **`generate_image_sd_forge`**:
  - HTTP POST to `{api_url}/sdapi/v1/txt2img` with JSON payload:
    ```json
    {
      "prompt": "...",
      "negative_prompt": "...",
      "width": 1024,
      "height": 1024,
      "steps": 5,
      "cfg_scale": 1.0,
      "distill_cfg": 1.0,
      "distill_cfg_scale": 1.0,
      "sampler_name": "Euler",
      "scheduler": "Beta"
    }
    ```
  - Receives base64 encoded image string in `images[0]`.
  - Decodes and saves to `~/ollama_workspace/images/forge_gen_{YYYYMMDD_HHMMSS}.png`.
  - Returns formatted markdown linking to `/workspace/images/{filename}`.
- **`edit_image_sd_forge`** (aliased as `edit_image`):
  - Resolves input image path from `~/ollama_workspace/{filepath}` or absolute path.
  - Encodes input image to base64.
  - HTTP POST to `{api_url}/sdapi/v1/img2img` with JSON payload:
    ```json
    {
      "init_images": ["<base64_data>"],
      "prompt": "...",
      "negative_prompt": "blurry, low quality, distorted, bad anatomy",
      "denoising_strength": 0.75,
      "steps": 5,
      "cfg_scale": 1.0,
      "distill_cfg": 1.0,
      "distill_cfg_scale": 1.0,
      "sampler_name": "Euler a"
    }
    ```
  - Decodes edited output from `images[0]` and saves to `~/ollama_workspace/images/forge_edit_{YYYYMMDD_HHMMSS}.png`.
  - Returns markdown preview linking to `/workspace/images/{filename}`.

#### B. ComfyUI Video Generation Tool (`src/ollama_agents/tools/comfyui.py`)
- **`generate_video_comfyui`**:
  - Submits workflow payload to `{api_url}/prompt`.
  - Built-in workflow graph:
    - Node 3: `KSampler` (steps: 20, cfg: 6.0, denoise: 1.0)
    - Node 4: `CheckpointLoaderSimple` (`ckpt_name: "v1-5-pruned-emaonly.safetensors"`)
    - Node 5: `EmptyLatentImage` (`batch_size: frames`, `width: width`, `height: height`)
    - Node 6: `CLIPTextEncode` (positive prompt)
    - Node 7: `CLIPTextEncode` (negative prompt)
    - Node 8: `VAEDecode`
    - Node 9: `VHS_VideoCombine` (`format: "video/h264-mp4"`, `frame_rate: fps`)
  - Polls `{api_url}/history/{prompt_id}` every 3.0 seconds up to 360 seconds.
  - Downloads output binary from `{api_url}/view?filename={filename}&subfolder={subfolder}&type={file_type}`.
  - Saves to `~/ollama_workspace/videos/comfy_vid_{timestamp}_{filename}`.
  - Returns markdown preview linking to `/workspace/videos/{out_filename}`.

### 4.3. Identified Gaps in Media Studio
1. **Missing Media Studio Tab in Header (`index.html`)**:
   - The `.tab-switcher` bar has 6 buttons: `chat`, `goals`, `files`, `cluster`, `reflections`, `hfmodels`.
   - Missing: `<button type="button" class="tab-btn" data-tab="media">🎨 Media Studio</button>`.
2. **Missing Media Studio Pane (`#tab-media`) in `index.html`**:
   - There is no `<div id="tab-media" class="tab-pane">` container.
   - Missing UI elements:
     - **Service Status & Config Header**:
       - SD Forge API URL input (default `http://127.0.0.1:7860`) + Live Status Badge (ONLINE / OFFLINE / CHECKING) + Check button.
       - ComfyUI API URL input (default `http://127.0.0.1:8000`, supports `8188`) + Live Status Badge (ONLINE / OFFLINE / CHECKING) + Check button.
     - **Interactive Generation Forms**:
       - Tab / Segmented selector: `Txt2Img (Forge)`, `Img2Img (Forge)`, `Video Gen (ComfyUI)`.
       - Txt2Img form: Prompt, Negative Prompt, Width/Height, Steps, CFG Scale, Generate button with loading spinner.
       - Img2Img form: File selector / uploaded image preview, Prompt, Denoising Strength (slider 0.0 - 1.0), Steps, Edit button.
       - Video Gen form: Prompt, Negative Prompt, Width/Height, Frames (e.g. 16), FPS (e.g. 8), Generate Video button.
     - **Media Workspace Gallery**:
       - Live grid displaying media files in `~/ollama_workspace/images/` and `~/ollama_workspace/videos/`.
       - In-browser modal/lightbox for full-resolution images.
       - Inline `<video controls loop>` player for videos.
       - Download and delete buttons for each media asset.
3. **Missing Backend REST Endpoints in `server.py`**:
   - Direct frontend calls to external ports (7860, 8188) from the browser can fail due to CORS or browser security restrictions. A backend proxy/handler ensures robust execution and offline status reporting:
     - `GET /api/media/status`: Accepts `forge_url` and `comfyui_url` query parameters; pings Forge (`/sdapi/v1/options` or `/sdapi/v1/sd-models`) and ComfyUI (`/system_stats` or `/prompt`) and returns connectivity status and latency.
     - `POST /api/media/generate-image`: Calls `generate_image_sd_forge` with request body.
     - `POST /api/media/edit-image`: Calls `edit_image_sd_forge` with request body.
     - `POST /api/media/generate-video`: Calls `generate_video_comfyui` with request body.
     - `GET /api/media/gallery`: Returns sorted list of images and videos in `~/ollama_workspace/images/` and `~/ollama_workspace/videos/`.

---

## 5. Deep-Dive: Core Tab APIs

### 5.1. Goals Management (`/api/goals`)
- **Storage**: `~/.ollama_agents/goals/<goal_id>.json`.
- **Data Models**:
  - `GoalTask`: `id`, `description`, `status` (`pending`, `in_progress`, `completed`, `failed`), `output`, `created`, `updated`, `session`.
  - `Goal`: `id`, `description`, `agent_name`, `tasks: List[GoalTask]`, `status` (`active`, `completed`, `failed`, `paused`), `session_count`, `created`, `updated`, `notes`, `final_summary`.
- **Decomposition**: `Planner.hierarchical_decompose` calls Ollama with an 8.0s timeout and falls back to a deterministic 3-stage plan if Ollama is unavailable or times out.
- **APK Build Triggers**: In `api_run_goal_task`, `build_android_apk` is supplied in the agent tools. The agent can compile Java code into a debug APK (`app-debug.apk`) in `~/ollama_workspace/`.
- **Follow-up Tasks**: `POST /api/goals/{goal_id}/followup` appends new sub-tasks dynamically and triggers execution if `auto_run=True`.
- **Kill Switches**: Per-goal kill (`POST /api/goals/{goal_id}/kill`) and global kill (`POST /api/tasks/kill-all`).

### 5.2. Files & Artifacts Explorer (`/api/workspace/files` & `/api/workspace/file`)
- **Storage**: `~/ollama_workspace/` mounted at `/workspace` via `StaticFiles`.
- **CRITICAL DEFECT IDENTIFIED**:
  In `src/ollama_agents/server.py`, `@app.get("/api/workspace/files")` is defined **twice**:
  - **First definition (Line 88)**:
    ```python
    @app.get("/api/workspace/files")
    def api_list_workspace_files():
        workspace_dir = Path.home() / "ollama_workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        files_list = []
        for path in sorted(workspace_dir.rglob("*")):
            if path.is_file():
                rel = str(path.relative_to(workspace_dir)).replace("\\", "/")
                files_list.append({
                    "name": path.name,
                    "relative_path": rel,
                    "full_path": str(path),
                    "url": f"/workspace/{rel}",
                    "size_bytes": path.stat().st_size,
                })
        return {"workspace_path": str(workspace_dir), "files": files_list}
    ```
  - **Second definition (Line 561)**:
    ```python
    @app.get("/api/workspace/files")
    def api_list_workspace_files():
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
    ```
  - **Root Cause & Impact**: FastAPI routes to the *first* matching handler encountered. Because line 88 is registered first, clients receive the partial payload (lacking `"status"`, `"type"`, `"size_formatted"`, `"modified"`, and `"download_url"`). This breaks the frontend `renderWorkspaceFiles()` in `index.html`, which relies on `f.type` for APK/Image/Code badges and `f.download_url` for downloads.
  - **Fix**: Remove the redundant line 88 implementation and keep the comprehensive line 561 implementation.

### 5.3. Cluster Nodes (`/api/cluster/nodes` & `/ws/cluster`)
- **`DistributedClusterManager`**:
  - Maintains `nodes: Dict[str, ClusterNode]`.
  - Pings nodes with `urllib.request` against `/api/tags` and `/api/ps`.
  - Extracts model tags, context length, active model VRAM (`size_vram`), and calculates latency in milliseconds.
  - Implements mDNS/Zeroconf listener on UDP port 9999 for automatic discovery.
  - Implements `select_best_node_for_model(model_name)`: selects node with lowest `(active_jobs, latency_ms)` hosting the requested model.
- **WebSocket `/ws/cluster`**:
  - Broadcasts cluster state every 2.5 seconds.
  - Handles client disconnects cleanly.

### 5.4. Self-Reflections (`/api/reflections`)
- **Backend Storage**: SQLite database `~/.ollama_agents/assistantagent.db`.
- **Query Logic**: `MemoryStore.get_reflections(limit)` checks `facts` table for query `"reflection"` and `scratchpad` table for notes, returning:
  ```json
  [
    { "key": "reflection_20260926_120000", "content": "Learned to check for file existence before reading." }
  ]
  ```
- **Post-Run Loop**: When an agent finishes a task, `Agent._reflect_and_store` generates a self-improvement lesson and writes it to memory and calls `Planner.auto_refine_skills`.

### 5.5. System Stats (`/api/system/stats` & `/api/system/gc`)
- **`MemorySafetyManager`**:
  - Returns `ram_total_gb`, `ram_available_gb`, `ram_used_pct`, `cpu_used_pct`, `active_agents`, `max_concurrent`, and GPU VRAM stats from `nvidia-smi`.
  - Enforces concurrency semaphore (default 3 concurrent agents) and memory headroom thresholds.
  - `POST /api/system/gc` forces `gc.collect()` and returns collected object counts and freed RAM.

### 5.6. Model Discovery & Installed Models Gap (`/api/models/installed`)
- **Acceptance Criteria Requirement**:
  Line 81 of `ORIGINAL_REQUEST.md` states:
  > *"All FastAPI endpoints (/api/chat/history, /api/chat/sessions, /api/workspace/files, /api/goals, /api/cluster/nodes, /api/models/installed, /api/reflections, /api/system/stats) return HTTP 200 with valid JSON payloads."*
- **Current State**:
  In `server.py`, the endpoint is `@app.get("/api/models")` (line 124). `/api/models/installed` does **not** exist!
- **Fix**: Add `@app.get("/api/models/installed")` (or an alias route decorator on `api_list_models`) returning HTTP 200 with the installed models list.

### 5.7. Multimodal Support Gap (Gemma 3 & Qwen2.5-VL)
- **Requirement (R1)**:
  Multimodal models like Gemma 3 and Qwen2.5-VL must receive image bytes/paths directly into the Ollama chat payload (`images` field) for visual reasoning and OCR.
- **Current State**:
  - In `src/ollama_agents/server.py`: `SingleTaskRequest` has `attachment: Optional[str] = ""`, but in `api_run_single_task` and `api_chat_stream`, `req.attachment` is only stored in SQLite; it is **never** passed into `agent.run()`.
  - In `src/ollama_agents/agent.py`: `Agent.run(user_prompt: str, ...)` only accepts text. The `self.history.append({"role": "user", "content": user_prompt})` does not support or append the `"images"` field into the Ollama payload.
- **Fix**:
  Update `Agent.run()` to accept an optional `images: Optional[List[str]] = None` parameter (file paths or base64 strings). If provided, populate `{"role": "user", "content": user_prompt, "images": encoded_images}` so Ollama multimodal models receive image data.

---

## 6. Deep-Dive: Automated Integration Test Suite (`tests/test_all_tabs_and_endpoints.py`)

### 6.1. Status of Test Suite
- **Current Directory State**:
  - There is **no** `tests/` directory at the repository root `e:\Learning\Python\agent_test\`.
  - `tests/test_all_tabs_and_endpoints.py` does not exist.
  - Acceptance Criteria 80 explicitly requires:
    > *"Integration test suite tests/test_all_tabs_and_endpoints.py exits with status code 0."*

### 6.2. Test Coverage Requirements Matrix

To satisfy R4 and Acceptance Criteria 80–82, `tests/test_all_tabs_and_endpoints.py` must provide comprehensive automated coverage across the following 6 domains:

```
+---------------------------------------------------------------------------------------+
|                 tests/test_all_tabs_and_endpoints.py Test Architecture                |
+---------------------------------------------------------------------------------------+
|  1. REST API Endpoints Verification (HTTP 200 + Schema Validation)                    |
|     - /api/chat/history                                                               |
|     - /api/chat/sessions                                                              |
|     - /api/workspace/files                                                            |
|     - /api/workspace/file (GET preview & DELETE)                                      |
|     - /api/goals (GET list, POST create, POST run, POST kill, POST followup, DELETE)  |
|     - /api/cluster/nodes & /api/cluster/nodes/add                                     |
|     - /api/models & /api/models/installed                                             |
|     - /api/models/search-hf & /api/models/trending-hf                                 |
|     - /api/reflections                                                                |
|     - /api/system/stats & /api/system/gc                                              |
|     - /api/upload                                                                     |
|     - Media Studio endpoints: /api/media/status, generate-image, edit-image, video    |
+---------------------------------------------------------------------------------------+
|  2. Real-Time Server-Sent Events (SSE) Stream Verification                            |
|     - /api/chat/stream receives prompt                                                |
|     - Streams data chunks formatted as 'data: {...}\n\n'                              |
|     - Emits final 'done' event with non-empty 'result' and proper 'model' attribution |
+---------------------------------------------------------------------------------------+
|  3. WebSocket Real-Time Stream Verification                                           |
|     - /ws/cluster connection handshake                                                |
|     - Receives {"type": "cluster_status", "data": {...}} payload                      |
|     - Validates cluster status fields (total_nodes, active_nodes, aggregate_models)   |
+---------------------------------------------------------------------------------------+
|  4. Multimodal Attachments & Media Pipeline                                           |
|     - Multipart image upload via /api/upload                                          |
|     - Verification that uploaded file is stored in ~/ollama_workspace/uploads/        |
|     - Multimodal message execution with attachment                                    |
+---------------------------------------------------------------------------------------+
|  5. Tool Executions & Media Fallbacks                                                 |
|     - Tool: generate_image_sd_forge (txt2img) graceful offline handling               |
|     - Tool: edit_image_sd_forge (img2img) graceful offline handling                   |
|     - Tool: generate_video_comfyui graceful offline handling                          |
|     - Tool: build_android_apk build trigger verification                              |
|     - Tool: run_python and write_file/read_file execution                             |
+---------------------------------------------------------------------------------------+
|  6. File Management Functions                                                         |
|     - File listing in ~/ollama_workspace/                                             |
|     - Preview reading of code / markdown files                                        |
|     - File deletion                                                                   |
+---------------------------------------------------------------------------------------+
```

### 6.3. Testing Strategy & Offline Resilience
Because integration tests may run in CI or environments where external GPUs, SD WebUI Forge (port 7860), ComfyUI (port 8000/8188), or secondary cluster laptops are offline:
- Tests must verify **both** live functionality and **graceful offline degradation** (proper error status codes, informative offline messages, and no unhandled crashes).
- Using `fastapi.testclient.TestClient(app)` allows synchronous testing of all HTTP routes and WebSockets in-process.
- For SSE testing, `TestClient.stream("POST", "/api/chat/stream", json=...)` reads line-by-line event chunks.
- For tests that interact with external Ollama instances, mock responses or local Ollama client mocking should ensure 100% test reliability and zero hangs even if the local Ollama daemon is busy.
- The test script must execute via `pytest tests/test_all_tabs_and_endpoints.py` and `python tests/test_all_tabs_and_endpoints.py` and exit with status code 0.

---

## 7. Gap Analysis & Actionable Specification Matrix

| Component | Required Specification | Current Status | Specific File & Location | Required Action |
|-----------|------------------------|----------------|--------------------------|-----------------|
| **Media Studio Tab** | Navigation button in header: `<button data-tab="media">🎨 Media Studio</button>` | Missing in `.tab-switcher` | `src/ollama_agents/static/index.html:361` | Add media tab button to header nav |
| **Media Studio Pane** | `<div id="tab-media" class="tab-pane">` with status badges, URL configs, generation forms, and gallery | Missing | `src/ollama_agents/static/index.html` (after `#tab-files`) | Create full Media Studio view pane with live status indicators, txt2img/img2img/video forms, and gallery |
| **Media Status API** | `GET /api/media/status` returning online/offline diagnostics for Forge & ComfyUI | Missing | `src/ollama_agents/server.py` | Implement endpoint checking ports 7860 & 8000/8188 |
| **Media Gen APIs** | `POST /api/media/generate-image`, `/api/media/edit-image`, `/api/media/generate-video` | Missing | `src/ollama_agents/server.py` | Implement REST endpoints wrapping tools |
| **Media Gallery API** | `GET /api/media/gallery` listing visual media in `images/` & `videos/` | Missing (or relies on files tab) | `src/ollama_agents/server.py` | Add dedicated endpoint or filter on `/api/workspace/files` |
| **Files Endpoint Duplication** | Single authoritative `GET /api/workspace/files` returning full metadata | Defined twice (lines 88 and 561); line 88 shadows line 561 | `src/ollama_agents/server.py:88,561` | Delete lines 88–104; retain line 561 with complete file types and download URLs |
| **Installed Models Endpoint** | `GET /api/models/installed` returning HTTP 200 with installed models list | Only `/api/models` exists; `/api/models/installed` returns 404 | `src/ollama_agents/server.py:124` | Add route decorator `@app.get("/api/models/installed")` |
| **Multimodal Ollama Chat** | Pass attachment image bytes/paths to Ollama chat payload `images` field | Attachment ignored by `Agent.run()` | `src/ollama_agents/server.py:384,446`, `agent.py:393,456` | Update `Agent.run` to accept `images` and populate message `images` list |
| **Integration Test Suite** | `tests/test_all_tabs_and_endpoints.py` exiting with code 0 | Neither `tests/` nor `test_all_tabs_and_endpoints.py` exists | Root directory `e:\Learning\Python\agent_test\` | Create `tests/test_all_tabs_and_endpoints.py` covering all tabs, REST endpoints, SSE, WebSocket, and tools |

---

## 8. Conclusion

The framework possesses strong foundation libraries (Forge tool, ComfyUI tool, Android APK builder, cluster manager, memory store, and streaming SSE chat), but suffers from several critical integration voids:
1. **Media Studio**: The UI tab and REST API endpoints are entirely absent, despite the underlying tool functions existing in `image_gen.py` and `comfyui.py`.
2. **Duplicate Route Defect**: `GET /api/workspace/files` at line 88 shadows the rich metadata endpoint at line 561, crippling file type badges and download links.
3. **Endpoint Contract Gap**: `/api/models/installed` is required by acceptance criteria but missing in `server.py`.
4. **Multimodal Disconnect**: Uploaded attachments are saved to disk but never forwarded to Ollama's `images` chat payload for Gemma 3 or Qwen2.5-VL.
5. **Missing Test Suite**: `tests/test_all_tabs_and_endpoints.py` must be authored from scratch to provide end-to-end test validation.
