# Comprehensive Investigation & Architectural Survey: Web Dashboard UI, Tabs, Assets & UI Routing

**Date:** 2026-09-26  
**Auditor / Subagent:** `survey_explorer_1` (Teamwork Explorer)  
**Target System:** Level 4 Ollama Agents Framework  
**Project Root:** `e:\Learning\Python\agent_test`  
**Reference Document:** `e:\Learning\Python\agent_test\ORIGINAL_REQUEST.md`

---

## 1. Executive Summary & Architecture Overview

The Level 4 Ollama Agents Web Dashboard is designed as a centralized, browser-based control center for conversational AI, multi-session autonomous goals, file management, distributed cluster node monitoring, model exploration, self-reflections, and visual media generation.

### Key Architectural Findings:
1. **Server Backend (`src/ollama_agents/server.py`):**
   - Built on **FastAPI** (`version="0.6.0"`).
   - Serves the frontend as a Single-Page Application (SPA) from `src/ollama_agents/static/index.html` via the root route `@app.get("/", response_class=HTMLResponse)`.
   - Mounts the workspace directory `~/ollama_workspace` at `/workspace` using FastAPI `StaticFiles`.
   - Employs **WebSocket** at `/ws/cluster` for zero-latency cluster telemetry and node status broadcasts.
   - Employs **Server-Sent Events (SSE)** at `/api/chat/stream` for streaming token output, thought process drawers, and real-time tool execution badges.
2. **Frontend UI (`src/ollama_agents/static/index.html`):**
   - A single comprehensive HTML5 document (2,093 lines, ~118.8 KB) containing inline styles, Google Fonts (`Outfit`, `JetBrains Mono`), responsive CSS media queries, and vanilla JavaScript controllers.
3. **Critical Deficiencies & Regressions Identified:**
   - **Critical Blocking Bug in Files & Artifacts Explorer:** `fetchWorkspaceFiles` is declared twice in `index.html` (lines 1321 and 1838). JavaScript function declaration hoisting causes the second declaration (an alert popup) to overwrite the table rendering function. The file table remains permanently stuck on *"Loading workspace files..."*.
   - **Duplicate Backend Route:** `@app.get("/api/workspace/files")` is defined twice in `server.py` (lines 88 and 561) with mismatched response schemas (`size_bytes` vs `size`/`size_formatted`).
   - **Completely Missing Media Studio Tab:** Despite Requirement R2 and Acceptance Criteria explicitly mandating a dedicated Media Studio tab for SD WebUI Forge image editing and ComfyUI video generation with live health indicators and workspace galleries, **no Media Studio tab exists in the HTML, CSS, JavaScript, or FastAPI routes**.
   - **Multimodal Payload Ingestion Defect (Gemma 3, Qwen2.5-VL):** While users can upload images via the UI, the image bytes/base64 are **never** injected into the Ollama chat payload `images` field in `server.py` or `agent.py`. The model only receives the text string `[Attached File: uploads/...]`, completely preventing visual reasoning and OCR.
   - **Missing Endpoint `/api/models/installed`:** Acceptance Criteria specifies `/api/models/installed`, but the server only implements `/api/models` (which returns only plain string arrays with no model metadata).
   - **Model Selector Stale Badges & Hardcoded Options:** Auto-syncing model selection on session switch fails to update the visual model badge `#chatModelBadge`.

---

## 2. Web Server, App Routing & Static Assets

### 2.1 Server Entry Point & Launch Chain
- **Batch Launcher:** `start_agent.bat`
  - Step 1: Health checks Ollama on port 11434 (`http://localhost:11434/api/tags`).
  - Step 2: Health checks SD WebUI Forge on port 7860 (`http://127.0.0.1:7860/sdapi/v1/options`).
  - Step 3: Health checks ComfyUI on port 8000 (`http://127.0.0.1:8000/system_stats`).
  - Step 5: Discovers Tailscale IPv4 address for remote access.
  - Step 6 (Lines 94–95): Launches web server via:
    ```cmd
    %PYTHON_CMD% -m ollama_agents.cli serve --host 0.0.0.0 --port 8100
    ```
- **CLI Command (`src/ollama_agents/cli.py:233-242`):**
  - Defines `@app.command(name="serve")`:
    ```python
    @app.command(name="serve")
    def serve_web(host: str = "127.0.0.1", port: int = 8000):
        import uvicorn
        uvicorn.run("ollama_agents.server:app", host=host, port=port, reload=False)
    ```
- **FastAPI Core (`src/ollama_agents/server.py`):**
  - Root template serving (`server.py:641-647`):
    ```python
    @app.get("/", response_class=HTMLResponse)
    def index():
        html_file = os.path.join(STATIC_DIR, "index.html")
        if os.path.exists(html_file):
            with open(html_file, "r", encoding="utf-8") as f:
                return f.read()
        return "<h1>Ollama Agents Web Dashboard - Front end loading...</h1>"
    ```
  - Workspace Static Mount (`server.py:633-635`):
    ```python
    WORKSPACE_DIR = Path.home() / "ollama_workspace"
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/workspace", StaticFiles(directory=str(WORKSPACE_DIR)), name="workspace")
    ```

### 2.2 Complete Backend REST API Route Inventory

| Route | Method | File & Line | Status / Notes |
|---|---|---|---|
| `/` | `GET` | `server.py:641` | Serves `index.html` SPA |
| `/workspace/*` | Static | `server.py:635` | Serves static artifacts from `~/ollama_workspace` |
| `/ws/cluster` | `WebSocket` | `server.py:59` | Real-time cluster status & node heartbeats |
| `/api/cluster/nodes` | `GET` | `server.py:74` | Returns active/inactive cluster nodes & models |
| `/api/cluster/nodes/add` | `POST` | `server.py:80` | Adds manual secondary laptop node |
| `/api/workspace/files` | `GET` | `server.py:88` | **DUPLICATE 1** (Returns `size_bytes`, `url`) |
| `/api/workspace/files` | `GET` | `server.py:561` | **DUPLICATE 2** (Overrides Duplicate 1; returns `size_formatted`, `type`) |
| `/api/workspace/file` | `GET` | `server.py:591` | Reads file text content preview (< 2 MB) |
| `/api/workspace/file` | `DELETE` | `server.py:610` | Deletes file or directory from workspace |
| `/api/upload` | `POST` | `server.py:193` | Uploads file/image into `~/ollama_workspace/uploads/` |
| `/api/goals` | `GET` | `server.py:219` | Lists all long-horizon goals with tasks |
| `/api/goals/create` | `POST` | `server.py:235` | Decomposes and registers a new goal |
| `/api/goals/{id}/run` | `POST` | `server.py:245` | Runs goal subtasks in background (`auto_continue=True`) |
| `/api/goals/{id}/kill` | `POST` | `server.py:330` | Stops active goal execution and marks task failed |
| `/api/goals/{id}` | `DELETE` | `server.py:345` | Permanently deletes goal from disk |
| `/api/goals/{id}/followup` | `POST` | `server.py:106` | Appends follow-up question/subtask to existing goal |
| `/api/tasks/kill-all` | `POST` | `server.py:357` | Emergency Kill Switch for all running tasks |
| `/api/task/run` | `POST` | `server.py:383` | Synchronous execution for single chat task |
| `/api/chat/stream` | `POST` | `server.py:445` | SSE streaming endpoint for chat tokens & tool events |
| `/api/chat/history` | `GET` | `server.py:527` | Retrieves stored chat history from SQLite |
| `/api/chat/sessions` | `GET` | `server.py:535` | Lists saved chat sessions with message counts |
| `/api/chat/sessions/{id}`| `DELETE` | `server.py:542` | Deletes a chat session |
| `/api/chat/clear` | `POST` | `server.py:551` | Clears messages for a session |
| `/api/models` | `GET` | `server.py:124` | Lists installed local models (returns `{"models": [...]}`) |
| `/api/models/installed` | `GET` | **MISSING** | **Mandated by Acceptance Criteria; does not exist** |
| `/api/models/pull` | `POST` | `server.py:154` | Triggers background pull of Ollama / HF model |
| `/api/models/search-hf` | `GET` | `server.py:179` | Searches Hugging Face Hub for GGUF models |
| `/api/models/trending-hf`| `GET` | `server.py:187` | Fetches trending daily GGUF models |
| `/api/system/stats` | `GET` | `server.py:142` | Returns CPU, RAM, GPU VRAM, active agent count |
| `/api/system/gc` | `POST` | `server.py:148` | Forces garbage collection to release RAM |
| `/api/reflections` | `GET` | `server.py:626` | Retrieves agent self-reflections from SQLite |
| `/api/media/*` | Any | **MISSING** | **No Media Studio endpoints exist** |

---

## 3. Exhaustive Tab-by-Tab Inspection

### 3.1 Tab 1: Interactive Chat Tab (`#tab-chat`)
- **Header Button:** `index.html:362` (`<button type="button" class="tab-btn active" data-tab="chat">💬 Interactive Chat</button>`)
- **Container:** `index.html:383-456` (`<div id="tab-chat" class="tab-pane active">`)
- **Current Implementation:**
  - **Session Selector (`#chatSessionSelect`):** Loaded via `loadSessionsList()` (`index.html:964`), fetching `/api/chat/sessions`. Supports "+ New Chat" (`createNewSession()`) and "Delete Session" (`deleteCurrentSession()`).
  - **Model Selector (`#chatModelSelect`):** Populated dynamically via `fetchInstalledModels()` from `/api/models`. Options update correctly on load.
  - **Turn Limit Selector (`#chatMaxTurnsSelect`):** Provides 25, 50, 75, 100 turns.
  - **Real-Time Streaming (SSE):** `sendMessage()` connects to `POST /api/chat/stream`. Decodes SSE events:
    - `tool_start`: Renders glowing tool badge (`⚡ Executing Tool: <tool>`).
    - `tool_end`: Displays completion checkmark.
    - `thought`: Renders live thought preview.
    - `done`: Emits final markdown formatted text.
  - **Thinking Accordion Drawer:** Thoughts wrapped in `<think>...</think>` (from models like DeepSeek-R1) are automatically folded into collapsible HTML `<details><summary>💭 Thought Process</summary>...</details>` blocks (`index.html:1134-1138`).
  - **Voice Input:** Continuous speech-to-text integration using `window.SpeechRecognition` / `webkitSpeechRecognition` (`index.html:865-942`).
  - **Automatic APK Artifact Detection:** If the response contains an `.apk` filename and success message, a prominent green "📱 Generated Android APK File" card with a direct download button is rendered (`index.html:1162-1179`).
- **Deficiencies Relative to ORIGINAL_REQUEST.md:**
  1. **Image Visual Payload Omission (R1):** When a user attaches an image via `#btnUploadFile`, the file is uploaded to `uploads/<file>`. The prompt is prefixed with `[Attached File: uploads/<file>]`, but the image bytes are **never** base64 encoded or passed to `self.client.chat(messages=[{"role": "user", "content": ..., "images": [...]})` in `server.py:383-525` or `agent.py:456`. Multimodal models (Qwen2.5-VL, Gemma 3, LLaVA) therefore cannot see the image.
  2. **Model Label Badge Desynchronization:** In `fetchChatHistory()` (`index.html:1071-1075`), when `lastUsedModel` is found for a session, `chatModelSelect.value = lastUsedModel;` is executed, but `updateModelLabel(lastUsedModel)` is **not called**, leaving the header label `#chatModelBadge` stuck displaying `Model: deepseek-r1:8b`.
  3. **No Vision Indicator in Selector:** Models with vision capabilities (e.g., `qwen2.5vl:latest`, `gemma3`) are not visually designated in `#chatModelSelect` with a `[Vision]` badge.

---

### 3.2 Tab 2: Autonomous Goals Tab (`#tab-goals`)
- **Header Button:** `index.html:363` (`<button type="button" class="tab-btn" data-tab="goals">🎯 Multi-Session Goals</button>`)
- **Container:** `index.html:459-501` (`<div id="tab-goals" class="tab-pane">`)
- **Current Implementation:**
  - **Layout:** Two-column grid (`.grid-2`).
    - Left: Goal Creation panel (prompt textarea `#goalPrompt`, execution model select `#goalModelSelect`, file uploader `#goalFileInput`, dictate button `#btnVoiceGoal`, decompose button `createGoal()`).
    - Right: Active Autonomous Goals panel (`#goalsList`, scroll-preserved refresh `fetchGoals()`).
  - **Decomposition & Storage:** Calls `POST /api/goals/create`, invoking `GoalRegistry.create_goal()` with `Planner.hierarchical_decompose()` (`goal.py:165-215`).
  - **Execution Engine:** `POST /api/goals/{id}/run?auto_continue=true` runs subtasks sequentially in background threads (`server.py:245-328`).
  - **Sub-task Cards:** Shows progress bar percentage, collapsible sessions breakdown, per-task status pills (`completed`, `in_progress`, `failed`), and output boxes (`index.html:1557-1599`).
  - **Interactive Follow-ups:** Each goal card contains an interactive follow-up question input with file upload (`index.html:1641-1659`), hitting `POST /api/goals/{id}/followup`.
  - **Kill Switches:** Per-goal kill button (`killGoal()`, `server.py:330`) and emergency kill switch (`emergencyKillAll()`, `server.py:357`).
- **Deficiencies Relative to ORIGINAL_REQUEST.md:**
  1. **Hardcoded APK Download Link:** Lines 1645–1647 in `index.html` hardcode the download URL to `/workspace/NearbyShare-debug.apk`:
     ```javascript
     ${(g.title.toLowerCase().includes("apk") || (g.final_summary && g.final_summary.toLowerCase().includes(".apk"))) ? `
         <a href="/workspace/NearbyShare-debug.apk" download target="_blank" ...>📱 Download APK</a>
     ` : ''}
     ```
     If the user builds a 2048 game (`android_2048_game-debug.apk`), this button erroneously downloads `NearbyShare-debug.apk`.
  2. **Fallback APK Name Inconsistency:** Line 1571 falls back to `"HelloWorld-debug.apk"`, while line 1626 falls back to `"NearbyShare-debug.apk"`.
  3. **No Multimodal Support in Goal Decomposition:** Goal file uploads only attach text paths, without passing image frames for multimodal analysis.

---

### 3.3 Tab 3: Files & Artifacts Explorer Tab (`#tab-files`)
- **Header Button:** `index.html:364` (`<button type="button" class="tab-btn" data-tab="files">📁 Files & Artifacts</button>`)
- **Container:** `index.html:612-643` (`<div id="tab-files" class="tab-pane">`)
- **Intended Implementation:**
  - Table `#workspaceFilesContainer` displaying File Name, Type badge (`📱 APK`, `🖼️ Image`, `💻 Code`, `📄 File`), Size, Modified timestamp, and Actions (Preview, Download, Delete).
  - Search filter input `#workspaceSearchInput` executing `filterWorkspaceFiles()`.
  - Code/text preview modal `#filePreviewModal` (`index.html:647-657`).
- **CRITICAL DEFICIENCIES & BUGS (SHOWSTOPPERS):**
  1. **JavaScript Function Hoisting Name Collision:**
     - In `index.html` at **line 1321**:
       ```javascript
       async function fetchWorkspaceFiles() {
           try {
               const res = await fetch(`${API_BASE}/api/workspace/files`);
               const data = await res.json();
               allWorkspaceFiles = data.files || [];
               renderWorkspaceFiles(allWorkspaceFiles);
           } catch (err) { ... }
       }
       ```
     - In `index.html` at **line 1838**:
       ```javascript
       async function fetchWorkspaceFiles() {
           try {
               const res = await fetch(`${API_BASE}/api/workspace/files`);
               const data = await res.json();
               if (!data.files || data.files.length === 0) {
                   return alert(`📁 Workspace is empty at '${data.workspace_path}'...`);
               }
               const fileListStr = data.files.map(f => `• ${f.relative_path} (${(f.size_bytes / 1024).toFixed(1)} KB)`).join("\n");
               alert(`📁 Files in Workspace (${data.workspace_path}):\n\n${fileListStr}\n\n...`);
           } catch (err) { alert("Error fetching workspace files: " + err.message); }
       }
       ```
     - **Impact:** Due to JavaScript hoisting, the second definition overwrites the first. Clicking the tab or calling `fetchWorkspaceFiles()` spawns a disruptive modal alert box (`alert()`) instead of populating the DOM table. The file explorer table remains permanently stuck on *"Loading workspace files..."*.
  2. **Schema Mismatch in Alert Popup:**
     - The second `fetchWorkspaceFiles` accesses `f.size_bytes`. However, the active backend route `server.py:561` returns `f.size` and `f.size_formatted`. `(f.size_bytes / 1024)` results in `NaN KB` in the popup.
  3. **Duplicate FastAPI Route in `server.py`:**
     - Line 88 defines `@app.get("/api/workspace/files")` returning `{ "workspace_path": ..., "files": [...] }` with `size_bytes` and `url`.
     - Line 561 defines `@app.get("/api/workspace/files")` returning `{ "status": "success", "workspace_path": ..., "files": [...] }` with `size`, `size_formatted`, `type`, `extension`, `download_url`.
  4. **Lack of Inline Media/Binary Preview in Modal:**
     - Line 1350 restricts preview to code and plain text extensions. Images (`png`, `jpg`, `webp`) and videos (`mp4`) cannot be viewed in the preview modal. The modal only contains `<pre id="previewModalContent">` and has no `<img>` or `<video>` player support.

---

### 3.4 Tab 4: Cluster Nodes Tab (`#tab-cluster`)
- **Header Button:** `index.html:365` (`<button type="button" class="tab-btn" data-tab="cluster">🖥️ Cluster Nodes <span id="clusterNodeCountBadge" ...>1 Node</span></button>`)
- **Container:** `index.html:504-555` (`<div id="tab-cluster" class="tab-pane">`)
- **Current Implementation:**
  - **Metrics Summary Grid:** Displays Connected Nodes (`#statTotalNodes`), Active Healthy Nodes (`#statActiveNodes`), Aggregated Model Pool (`#statAggModels`), Cluster Model Memory (`#statClusterVRAM`), and Auto-Discovery Status.
  - **Manual Node Connection:** Input `#addNodeUrlInput` + button calling `addClusterNodeFromUI()`, posting to `/api/cluster/nodes/add`.
  - **Active Nodes List:** Renders node cards showing host URL, discovery method (`manual` or `mdns`), latency in ms, active memory VRAM gauge, loaded models summary, and pills of all installed models on that node.
  - **WebSocket Telemetry:** `initClusterWebSocket()` (`index.html:663-688`) establishes a WebSocket channel to `/ws/cluster`, refreshing status every 2.5 seconds.
  - **Distributed Compute Routing:** `cluster_manager.select_best_node_for_model(model_name)` in `cluster.py` routes inference to the node holding the required model.
- **Deficiencies Relative to ORIGINAL_REQUEST.md:**
  - Generally robust. Minor deficiency: No visual indicator if the WebSocket disconnects; node ping latency could show color-coded thresholds (green < 50ms, amber < 200ms, red > 200ms).

---

### 3.5 Tab 5: Model Hub Tab (`#tab-hfmodels`)
- **Header Button:** `index.html:367` (`<button type="button" class="tab-btn" data-tab="hfmodels">🤗 Hugging Face Models</button>`)
- **Container:** `index.html:571-609` (`<div id="tab-hfmodels" class="tab-pane">`)
- **Current Implementation:**
  - Educational explanation banner on GGUF quantizations and recommended laptop RAM sizes.
  - Search input `#hfSearchInput` querying `/api/models/search-hf`.
  - Daily Trending releases fetched via `/api/models/trending-hf`.
  - Model action buttons: `❤️ Like & Pull`, `📥 Pull` (triggering `/api/models/pull`), and `📋 Copy` (copies `ollama run <tag>`).
- **Deficiencies Relative to ORIGINAL_REQUEST.md:**
  1. **Missing Local Installed Models Section:**
     - The tab exclusively displays remote Hugging Face GGUF models. It **completely lacks a local model manager view** showing models already installed on the machine, their parameter sizes, quantizations, disk usage, or delete/unload options.
  2. **Missing Endpoint `/api/models/installed`:**
     - Acceptance Criteria states:
       > *"All FastAPI endpoints (/api/chat/history, /api/chat/sessions, /api/workspace/files, /api/goals, /api/cluster/nodes, /api/models/installed, /api/reflections, /api/system/stats) return HTTP 200 with valid JSON payloads."*
     - The existing endpoint is `/api/models`, which only returns a flat list of strings. `/api/models/installed` does not exist in `server.py`.
  3. **No Pull Progress Tracking:**
     - Clicking `Pull` issues a background task, but there is no progress bar or percentage indicator in the UI to track active downloads.

---

### 3.6 Tab 6: Self-Reflections Tab (`#tab-reflections`)
- **Header Button:** `index.html:366` (`<button type="button" class="tab-btn" data-tab="reflections">🧠 Self-Improvement</button>`)
- **Container:** `index.html:557-569` (`<div id="tab-reflections" class="tab-pane">`)
- **Current Implementation:**
  - Refresh button calling `fetchReflections()`.
  - Container `#reflectionsList` rendering cards with key title and reflection content.
  - Backend endpoint `GET /api/reflections` calls `MemoryStore.get_reflections(limit=10)` (`memory.py:287-298`).
  - Reflections are generated at the end of agent runs via `Agent._reflect_on_run()` (`agent.py:348-388`) and stored in SQLite.
- **Deficiencies Relative to ORIGINAL_REQUEST.md:**
  - Basic functionality is intact. Deficiencies include lack of search/filter, inability to clear old reflections, and lack of timestamp badges on individual reflection cards.

---

### 3.7 Tab 7: Media Studio Tab (SD Forge & ComfyUI)
- **Status:** **COMPLETELY MISSING FROM WEB DASHBOARD**
- **Detailed Gap Analysis:**
  1. **Header Navigation:**
     - `index.html` lines 361–368 contain 6 tabs. There is **no tab button for Media Studio** (e.g. `<button type="button" class="tab-btn" data-tab="media">🎨 Media Studio</button>`).
  2. **Tab Pane:**
     - There is **no `<div id="tab-media" class="tab-pane">`** in `index.html`.
  3. **Frontend Controllers:**
     - There are **no JavaScript functions** for checking SD Forge status, ComfyUI status, triggering image generation/editing, triggering video generation, or rendering the media gallery.
  4. **Backend REST Endpoints in `server.py`:**
     - There are **no REST endpoints** for direct user-facing media operations.
     - While agent tools exist in `src/ollama_agents/tools/image_gen.py` (`generate_image_sd_forge`, `edit_image_sd_forge`) and `src/ollama_agents/tools/comfyui.py` (`generate_video_comfyui`), these are only callable by the LLM as ReAct tools. A user cannot directly click, prompt, edit, or generate images/videos from the UI!
  5. **ORIGINAL_REQUEST.md Requirements (R2 & Acceptance Criteria):**
     - R2 explicitly requires:
       > *"Provide a dedicated, fully functional Media Studio tab in the Web Dashboard UI for image generation/editing via Stable Diffusion WebUI Forge API (ports 7860/default) and video generation via ComfyUI API (ports 8188/8000/default)."*
       > *"Include live visual connection health indicators (Online / Offline diagnostic badges with configurable API URL inputs) for both SD Forge and ComfyUI."*
       > *"Support direct txt2img generation, image-to-image editing with uploaded image references, and prompt-driven video generation."*
       > *"Save all generated visual media directly into ~/ollama_workspace/images/ and ~/ollama_workspace/videos/ with immediate in-browser playback, downloads, and interactive gallery views."*
     - Acceptance Criteria explicitly requires:
       > *"- [ ] Every tab in the header (chat, goals, files, cluster, reflections, hfmodels, and media) renders its view pane without JavaScript errors or broken layout states."*
       > *"- [ ] Media Studio displays live status for SD Forge and ComfyUI, accepts generation and edit prompts, and renders generated images and videos in the workspace gallery."*

---

## 4. Deep-Dive on Multimodal Pipeline (Gemma 3 & Qwen2.5-VL)

### Current Architecture Flaw:
In Ollama, multimodal visual reasoning requires the `images` parameter in the chat completion request payload:
```python
response = client.chat(
    model="qwen2.5vl:latest",  # or gemma3
    messages=[{
        "role": "user",
        "content": "Describe this image in detail.",
        "images": ["<base64_encoded_image_bytes>"]  # OR local file path / bytes
    }]
)
```

### Trace of What Currently Happens in the Codebase:
1. User clicks `📁 Upload File` (`#btnUploadFile`) in the Interactive Chat tab.
2. `handleFileUpload(event)` posts the file to `/api/upload`.
3. `api_upload_file()` in `server.py:193` writes the file to `~/ollama_workspace/uploads/{safe_filename}` and returns `filepath: "uploads/{safe_filename}"`.
4. In `index.html:1197`, when `sendMessage()` executes:
   ```javascript
   if (attachedFile && !prompt.includes(attachedFile)) {
       prompt = `[Attached File: ${attachedFile}] ${prompt}`;
   }
   ```
5. `POST /api/chat/stream` receives `req.prompt` (containing string `"[Attached File: uploads/...]"`) and `req.attachment` (`"uploads/..."`).
6. In `server.py:484`, `mem.save_chat_message(...)` records the text and attachment path.
7. In `server.py:493`, `agent.run(req.prompt, max_turns=req.max_turns, ...)` is called.
8. In `agent.py:456`:
   ```python
   self.history.append({"role": "user", "content": user_prompt})
   ```
   **Notice:** There is NO `images` field appended!
9. In `agent.py:500`:
   ```python
   response = self.client.chat(
       model=self.model,
       messages=self.history,
       tools=tool_schemas if tool_schemas else None,
       options=options,
   )
   ```
   **The image data is NEVER transmitted to Ollama!**
10. The multimodal model (e.g. `qwen2.5vl:latest` or `gemma3`) only sees the text string `"[Attached File: uploads/cat.jpg] What is in this picture?"`. It responds with text hallucination or explains that it cannot view files without visual input!

---

## 5. UI Elements, Selectors, Uploaders & Badges Audit

### 5.1 Model Selectors
- **Interactive Chat (`#chatModelSelect`):**
  - Rendered at `index.html:399-403`.
  - Populated dynamically by `fetchInstalledModels()` (`index.html:802`).
  - Defect: When switching between saved sessions (`index.html:1071`), `chatModelSelect.value` is updated, but `#chatModelBadge` is not refreshed, creating UI desynchronization.
- **Autonomous Goals (`#goalModelSelect`):**
  - Rendered at `index.html:483-486`.
  - Populated dynamically by `fetchInstalledModels()`.
- **Subagent Delegation:**
  - In `src/ollama_agents/tools/actions.py:239`, `delegate_subagent` takes a `model` parameter defaulting to `deepseek-r1:8b`.
  - Currently no dynamic check verifies if the requested model is actually installed before spinning up the subagent.

### 5.2 File Uploaders & Attachments
- **Chat Uploader:** `#btnUploadFile` + hidden `#fileInput` (`index.html:442-445`). Previews attachment via `#fileUploadPreview` with dismiss button.
- **Goal Uploader:** `#btnUploadGoalFile` + hidden `#goalFileInput` (`index.html:467-477`). Previews attachment via `#goalFileUploadPreview`.
- **Follow-up Uploader:** Per-goal hidden input `#followup_file_${g.goal_id}` (`index.html:1652`).
- **Deficiencies:**
  - No drag-and-drop file upload zones.
  - No visual progress percentage during large file uploads.

### 5.3 Status Badges & Indicators
- **Header RAM / VRAM Utilization Badge (`#memoryBadge`, `index.html:371`):**
  - Polls `/api/system/stats` every 5 seconds.
  - Updates RAM percentage (`#ramPct`), GPU VRAM percentage (`#vramPct`), and active agent count (`#activeAgents`).
  - Correctly changes border and text color to red (`#ef4444`) when RAM >= 85% or VRAM >= 90%.
- **Node Count Badge (`#clusterNodeCountBadge`, `index.html:365`):**
  - Inside the "Cluster Nodes" tab header button; displays active node count live via WebSocket.
- **Level 4 Autonomous Badge (`.badge-l4`, `index.html:376`):**
  - Static styling badge.
- **Missing Badges:**
  - No SD Forge Online/Offline status badge in the header or UI.
  - No ComfyUI Online/Offline status badge in the header or UI.

---

## 6. Concrete Recommendations & Implementation Blueprint

To achieve 100% compliance with `ORIGINAL_REQUEST.md` (R1, R2, R3, R4) and pass all Acceptance Criteria, the following concrete modifications are recommended:

### 1. Fix Files & Artifacts Explorer (Resolve Hoisting Collision & Duplicate Routes)
1. In `src/ollama_agents/static/index.html`:
   - **Delete or rename the duplicate `fetchWorkspaceFiles()` at line 1838** (which is merely an alert helper).
   - Retain the table-rendering `fetchWorkspaceFiles()` at line 1321.
   - Update `openTab('files')`, page load, and the "Refresh Files" button to call the table renderer.
2. In `src/ollama_agents/server.py`:
   - Remove duplicate `@app.get("/api/workspace/files")` at line 88.
   - Standardize on the enriched version at line 561, ensuring it returns `files` containing `name`, `relative_path`, `full_path`, `size`, `size_formatted`, `modified`, `type`, `extension`, and `download_url`.
3. In `index.html`:
   - Upgrade `#filePreviewModal` to inspect file type. If the file is an image (`png`, `jpg`, `webp`), render an `<img src="${download_url}">`. If it is a video (`mp4`, `webm`), render a `<video src="${download_url}" controls autoplay>`. If text/code, render in the `<pre>` block.

### 2. Implement Missing Media Studio Tab (`data-tab="media"`)
1. In `src/ollama_agents/static/index.html`:
   - Add `<button type="button" class="tab-btn" data-tab="media">🎨 Media Studio</button>` to `.tab-switcher` in `<header>`.
   - Add `<div id="tab-media" class="tab-pane">` to `.main-content`.
   - Build three panels:
     - **Service Diagnostics & Health Indicators:** Configurable API URLs for SD Forge (default `http://127.0.0.1:7860`) and ComfyUI (default `http://127.0.0.1:8000`), with live Online / Offline ping badges.
     - **Generation & Editing Controls:**
       - Tabbed sub-views: `🎨 Text-to-Image (Forge)`, `🖼️ Image-to-Image / Edit (Forge)`, and `🎬 Prompt-to-Video (ComfyUI)`.
       - Inputs for positive prompt, negative prompt, steps, CFG scale, image dimensions, reference image uploader for img2img, and video frame count.
     - **Workspace Media Gallery:** Real-time grid displaying generated images from `~/ollama_workspace/images/` and videos from `~/ollama_workspace/videos/` with in-browser playback, zoom modals, and download links.
   - Implement JavaScript functions: `openTab('media')`, `checkMediaServicesHealth()`, `generateMediaImage()`, `editMediaImage()`, `generateMediaVideo()`, and `fetchMediaGallery()`.
2. In `src/ollama_agents/server.py`:
   - Add REST API endpoints:
     - `GET /api/media/health` -> Pings both Forge (`/sdapi/v1/options`) and ComfyUI (`/system_stats`).
     - `POST /api/media/image/generate` -> Direct call to `generate_image_sd_forge()`.
     - `POST /api/media/image/edit` -> Direct call to `edit_image_sd_forge()`.
     - `POST /api/media/video/generate` -> Direct call to `generate_video_comfyui()`.
     - `GET /api/media/gallery` -> Returns all images and videos in `~/ollama_workspace/images/` and `~/ollama_workspace/videos/`.

### 3. Implement Full Multimodal Pipeline (Gemma 3 & Qwen2.5-VL)
1. In `src/ollama_agents/server.py`:
   - In `/api/chat/stream` and `/api/task/run`, when `req.attachment` is provided and represents an image (`.png`, `.jpg`, `.jpeg`, `.webp`), read the file from `~/ollama_workspace/uploads/{filename}`, encode it to base64, and pass it to `agent.run(..., images=[img_b64])`.
2. In `src/ollama_agents/agent.py`:
   - Update `Agent.run(user_prompt, ..., images: Optional[List[str]] = None)`.
   - When `images` is provided, append:
     ```python
     user_msg = {"role": "user", "content": user_prompt}
     if images:
         user_msg["images"] = images
     self.history.append(user_msg)
     ```
   - This ensures Ollama's `client.chat()` sends the image payload directly to Gemma 3 and Qwen2.5-VL for visual processing.

### 4. Implement `/api/models/installed` & Enhance Model Hub
1. In `src/ollama_agents/server.py`:
   - Add endpoint `@app.get("/api/models/installed")`:
     - Calls `ollama.list()` and returns detailed metadata for each model: `name`, `model`, `size`, `size_gb`, `modified_at`, `family`, `parameter_size`, `quantization_level`, and `is_multimodal` (checking for vision families/tags like `qwen2.5vl`, `gemma3`, `llava`).
   - Alias `@app.get("/api/models")` to return the same or ensure backwards compatibility.
2. In `src/ollama_agents/static/index.html`:
   - In `#tab-hfmodels`, add a sub-section or toggle: **"Installed Local Models"** displaying a table of all local models with their parameter sizes, VRAM footprint, and a `[Vision / Multimodal]` badge.
   - When populating `#chatModelSelect` and `#goalModelSelect`, append `[Vision]` to multimodal models.
   - In `fetchChatHistory()`, ensure `updateModelLabel(lastUsedModel)` is called when auto-syncing the model select.

### 5. Fix Dynamic APK Link in Goals Tab
1. In `index.html:1645-1647`:
   - Replace the hardcoded `NearbyShare-debug.apk` with dynamic regex extraction from `g.final_summary` or `g.tasks`, falling back to the first `.apk` found in workspace files.

---

## 7. Acceptance Criteria Verification Matrix

| Requirement / Acceptance Criteria Item | Current Status | Cause / Location | Remediation Plan |
|---|---|---|---|
| **Every tab in header renders view pane without JS errors or broken layout** | ❌ **FAIL** | 1. Media Studio tab missing from header & DOM.<br>2. Files tab broken by JS function hoisting collision at line 1838. | 1. Add Media Studio tab button & pane.<br>2. Remove duplicate alert function at line 1838. |
| **Model dropdowns reflect all local models & support multimodal (Gemma 3, Qwen2.5-VL)** | ⚠️ **PARTIAL** | Models populate names, but image bytes are never sent in Ollama `images` payload. | Ingest image base64 in `server.py` and pass to `agent.run(..., images=[...])`. |
| **Chat streaming and tool execution work reliably** | ✅ **PASS** | SSE endpoint `/api/chat/stream` streams events and renders thinking drawer properly. | Maintain existing implementation; fix model badge sync. |
| **Media Studio displays live status for Forge/ComfyUI, accepts prompts, renders gallery** | ❌ **FAIL** | Entire Media Studio tab and backend media endpoints are missing. | Implement tab pane, health checks, generation endpoints, and gallery grid. |
| **FastAPI endpoints return HTTP 200 with valid JSON (including `/api/models/installed`)** | ⚠️ **PARTIAL** | `/api/models/installed` is missing; duplicate `/api/workspace/files` exists. | Implement `/api/models/installed`; clean up route duplicates. |
| **Real-time SSE streaming completes with `done` event and proper model attribution** | ✅ **PASS** | Implemented at `server.py:445-525`. | Maintain existing implementation. |

---

*End of Survey Report. Ready for synthesis into handoff protocol.*
