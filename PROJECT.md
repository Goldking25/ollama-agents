# Project: Level 4 Ollama Agents Hardening & End-to-End Verification

## Architecture
- **Web UI & Server**: FastAPI server (`src/ollama_agents/server.py`) serving Single Page Application (`src/ollama_agents/static/index.html`) on port 8100, mounting workspace (`~/ollama_workspace`) at `/workspace`.
- **Agent Core & Execution**: `Agent` class (`src/ollama_agents/agent.py`) executing ReAct tool loops, communicating with Ollama client (`ollama`), and managing conversation history and ephemeral memory.
- **Model Dynamic Discovery & Routing**: `model_selector.py` dynamically discovering installed models via Ollama API (`/api/models/installed` and `/api/tags`), scoring capabilities (code, reasoning, vision/multimodal, general).
- **Multimodal Pipeline**: Base64 image payload ingestion supporting vision-capable models (Gemma 3, Qwen2.5-VL, LLaVA), attached through chat upload and passed into Ollama payload `images` list.
- **Media Studio Tab & Generative Pipelines**:
  - Direct UI Tab (`#tab-media`) in `index.html`.
  - Stable Diffusion WebUI Forge API integration (`src/ollama_agents/tools/image_gen.py`, port 7860 default) for txt2img and img2img.
  - ComfyUI API integration (`src/ollama_agents/tools/comfyui.py`, port 8000/8188 default) for prompt-driven video generation.
  - Server endpoints: `/api/media/status`, `/api/media/generate-image`, `/api/media/edit-image`, `/api/media/generate-video`, `/api/media/gallery`.
  - Storage: `~/ollama_workspace/images/` and `~/ollama_workspace/videos/` with gallery view, downloads, and in-browser playback.
- **Core Tabs & Endpoints**:
  - Interactive Chat (`/api/chat/stream`, `/api/chat/history`, `/api/chat/sessions`, `/api/upload`).
  - Autonomous Goals (`/api/goals`, multi-session decomposition, sub-task tracking, follow-ups, APK build triggers).
  - Files & Artifacts Explorer (`/api/workspace/files`, recursive browsing, code/markdown preview modal, media playback, binary downloads).
  - Cluster Nodes (`/api/cluster/nodes`, `/ws/cluster` WebSocket heartbeat, latency monitoring, model routing).
  - Self-Reflections (`/api/reflections`, episodic memory SQLite storage, querying, skill refinement).
  - Model Hub (`/api/models`, `/api/models/installed`, `/api/models/pull`, Hugging Face GGUF discovery).
  - System Stats (`/api/system/stats`, CPU/RAM/GPU telemetry).
- **Automated Verification Suite**: `tests/test_all_tabs_and_endpoints.py` exercising all REST endpoints, WebSocket streams, SSE chat completion, multimodal attachments, tool executions, and file management functions with exit code 0.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Dynamic Model Listing (/api/models/installed) | Add `/api/models/installed` endpoint returning installed models, status, and capabilities | M1 | survey_2, AC 81 |
| 2 | Multimodal Model Classification | Extend `is_multimodal_model` to recognize `vl`, `vision`, `gemma3`, `llava`, `moondream` | M1 | survey_2, R1 |
| 3 | Multimodal Attachment Payload Ingestion | Resolve attachments to absolute paths, encode base64, pass to `agent.run()`, and inject `images` list into Ollama payload | M1 | survey_1, survey_2, R1 |
| 4 | Chat SSE Stream Reliability & Attribution | Ensure SSE generator reliably completes with `done` or `error` event and accurate model attribution without truncation | M1 | survey_2, AC 82 |
| 5 | UI Model Selector & Badge Synchronization | Ensure model selector dropdown reflects all installed models across all tabs and header badge stays synchronized on session switch | M1 | survey_2, AC 75 |
| 6 | Tool Execution Error Handling & Loop Prevention | Prefix missing file errors with `[Error]`, return workspace directory hints, and prevent infinite filename hallucination loops | M1 | survey_2, AC 76 |
| 7 | Media Studio Header Tab & View Pane | Add `data-tab="media"` button and `#tab-media` pane with styles and navigation handling in `index.html` | M2 | survey_1, survey_3, R2 |
| 8 | Media Studio Connection Health Badges | Live visual Online/Offline diagnostic badges with configurable API URL inputs for SD Forge (7860) and ComfyUI (8000/8188) | M2 | survey_3, R2 |
| 9 | Media Studio REST Endpoints | Implement `/api/media/status`, `/api/media/generate-image`, `/api/media/edit-image`, `/api/media/generate-video`, `/api/media/gallery` in `server.py` | M2 | survey_3, R2 |
| 10 | SD Forge txt2img & img2img Generation | Direct UI controls for txt2img and img2img with uploaded reference images, saving to `~/ollama_workspace/images/` | M2 | survey_3, R2 |
| 11 | ComfyUI Video Generation | Direct UI controls for prompt-driven video generation, polling workflow status, saving to `~/ollama_workspace/videos/` | M2 | survey_3, R2 |
| 12 | Media Studio In-Browser Gallery & Playback | Immediate gallery rendering, image modal view, `<video controls>` playback, and direct downloads | M2 | survey_3, R2, AC 77 |
| 13 | Files Tab JavaScript Hoisting Fix | Remove duplicate `fetchWorkspaceFiles` declaration at line 1838 in `index.html` so table renders properly | M3 | survey_1, AC 74 |
| 14 | Duplicate `/api/workspace/files` Endpoint Fix | Consolidate `/api/workspace/files` in `server.py` to return full metadata (`size_formatted`, `type`, `download_url`, `modified`) | M3 | survey_1, survey_3, AC 81 |
| 15 | Autonomous Goals Hardening & Dynamic APK Link | Fix dynamic detection of generated APKs in goals follow-up header, robust multi-task continuation | M3 | survey_1, survey_3, R3 |
| 16 | Cluster Nodes & Telemetry Hardening | Ensure `/api/cluster/nodes` and `/ws/cluster` handle heartbeat telemetry and offline fallbacks cleanly | M3 | survey_3, R3, AC 81 |
| 17 | Self-Reflections Tab & Memory Hardening | Ensure `/api/reflections` properly persists, filters, and displays episodic memory and refinement suggestions | M3 | survey_3, R3, AC 81 |
| 18 | Model Hub Discovery & Pull Hardening | Ensure `/api/models` and `/api/hf/search` handle Ollama tags and Hugging Face GGUF catalog searches with live progress | M3 | survey_3, R3, AC 81 |
| 19 | System Stats Endpoint (/api/system/stats) | Verify `/api/system/stats` returns HTTP 200 with valid CPU, RAM, disk, and GPU telemetry JSON | M3 | survey_3, AC 81 |
| 20 | E2E Integration Test Suite Infrastructure | Create `tests/test_all_tabs_and_endpoints.py` testing all REST API endpoints, WebSocket streams, SSE chat completion, multimodal attachments, tools, and file management | M4 | survey_3, R4, AC 80 |
| 21 | Adversarial Coverage Hardening (Tier 5) | White-box adversarial testing, boundary inputs, offline service fallbacks, and regression verification | M5 | Project Pattern Phase 2 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Dynamic Model Availability & Multimodal Support | Features 1, 2, 3, 4, 5, 6: `/api/models/installed`, multimodal payload injection (Gemma 3, Qwen2.5-VL), SSE stream completion with attribution, UI badge sync, missing-file loop prevention | none | DONE |
| M2 | Media Studio Tab & Generative Pipelines | Features 7, 8, 9, 10, 11, 12: `#tab-media` UI, connection diagnostics, SD Forge txt2img/img2img, ComfyUI video gen, `/api/media/*` endpoints, workspace gallery/player | none | PLANNED |
| M3 | Core Tabs Functional Hardening & Route Fixes | Features 13, 14, 15, 16, 17, 18, 19: Files tab hoisting fix, duplicate `/api/workspace/files` removal, Goals dynamic APK link, Cluster/Reflections/Hub/Stats hardening | M1 | PLANNED |
| M4 | E2E Integration Test Suite & Verification | Feature 20: Comprehensive `tests/test_all_tabs_and_endpoints.py` covering all REST endpoints, WebSockets, SSE streams, multimodal payloads, tools, with exit code 0 | M1, M2, M3 | PLANNED |
| M5 | Adversarial Coverage Hardening (Tier 5) | Feature 21: White-box challenger stress tests, offline service resilience, boundary condition verification | M4 | PLANNED |

## Code Layout
- `src/ollama_agents/server.py`: FastAPI backend, REST routes, SSE streams, WebSocket endpoints, static asset mounting.
- `src/ollama_agents/agent.py`: Autonomous agent execution loop, message history, Ollama payload assembly, tool invocation.
- `src/ollama_agents/model_selector.py`: Model capability analysis, multimodal detection, model routing.
- `src/ollama_agents/static/index.html`: Web Dashboard SPA, tab panes (`#tab-chat`, `#tab-goals`, `#tab-files`, `#tab-cluster`, `#tab-reflections`, `#tab-hfmodels`, `#tab-media`), JS controllers, CSS.
- `src/ollama_agents/tools/`: Tool implementations (`image_gen.py`, `comfyui.py`, `actions.py`, `android_builder.py`, `web_search.py`).
- `tests/test_all_tabs_and_endpoints.py`: Integration test suite verifying all tabs, endpoints, streams, and pipelines.

## Interface Contracts
### Media Studio UI ↔ Backend (`server.py`)
- `GET /api/media/status`:
  - Request: Optional `forge_url`, `comfy_url` query params.
  - Response: `{"forge": {"online": bool, "url": str, "error": str | null}, "comfy": {"online": bool, "url": str, "error": str | null}}`
- `POST /api/media/generate-image`:
  - Request: `{"prompt": str, "negative_prompt": str, "steps": int, "cfg_scale": float, "width": int, "height": int, "api_url": str}`
  - Response: `{"status": "success", "file_path": str, "filename": str, "url": str}`
- `POST /api/media/edit-image`:
  - Request: `{"prompt": str, "image_base64": str | null, "image_path": str | null, "denoising_strength": float, "api_url": str}`
  - Response: `{"status": "success", "file_path": str, "filename": str, "url": str}`
- `POST /api/media/generate-video`:
  - Request: `{"prompt": str, "negative_prompt": str, "steps": int, "frames": int, "api_url": str}`
  - Response: `{"status": "success", "file_path": str, "filename": str, "url": str}`
- `GET /api/media/gallery`:
  - Request: `?media_type=all|images|videos`
  - Response: `{"images": [{"name": str, "url": str, "size": int, "modified": float}], "videos": [{"name": str, "url": str, "size": int, "modified": float}]}`

### Models API ↔ Client
- `GET /api/models/installed`:
  - Request: None
  - Response: `{"status": "success", "models": [str], "details": [{"name": str, "is_multimodal": bool, "capabilities": [str]}]}`

### Chat Streaming & Multimodal Payload
- `POST /api/chat/stream`:
  - Request: `{"prompt": str, "session_id": str, "model": str, "attachment": str | null, "max_turns": int}`
  - Multimodal Behavior: If `attachment` is an image (`.png`, `.jpg`, `.jpeg`, `.webp`), `server.py` resolves to absolute path in `~/ollama_workspace/uploads/` or workspace, reads bytes, base64-encodes, and passes to `agent.run(prompt, images=[base64_data])`.
  - SSE Events:
    - `data: {"type": "token", "content": str, "model": str}`
    - `data: {"type": "tool_start", "tool": str, "input": any}`
    - `data: {"type": "tool_done", "tool": str, "output": str}`
    - `data: {"type": "done", "response": str, "model": str}`
    - `data: {"type": "error", "message": str, "model": str}`
