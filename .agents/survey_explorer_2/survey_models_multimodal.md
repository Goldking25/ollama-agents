# Deep-Dive Investigation: Ollama Integration, Model Discovery, Multimodal Processing, Chat Streaming, and Tool Execution

**Subagent**: `survey_explorer_2`  
**Date**: 2026-09-26  
**Status**: Investigation Complete  
**Scope**: Requirements R1, R3, Acceptance Criteria, and associated backend/frontend modules in the Level 4 Ollama Agents framework.

---

## 1. Executive Summary

An exhaustive code-level audit was conducted across `src/ollama_agents/` (including `agent.py`, `server.py`, `model_selector.py`, `memory.py`, `cluster.py`, `tool.py`, `tools/actions.py`, and `static/index.html`).

Seven critical architectural and functional gaps were discovered:
1. **Critical Multimodal Disconnect**: Although the frontend uploads images to `/api/upload` and forwards `attachment` in the chat request, `server.py` **never** passes the image to `agent.run()`, and `Agent` does not accept or inject images into Ollama's `messages` payload. Furthermore, Ollama's Python library requires absolute paths or base64 strings; passing relative paths like `"uploads/foo.png"` causes an immediate `ValueError: File uploads/foo.png does not exist`. Multimodal models (Gemma 3, Qwen2.5-VL) are thus blind to attached images.
2. **Missing `/api/models/installed` Endpoint**: `server.py` only defines `/api/models`. The mandatory endpoint `/api/models/installed` specified in R1, R4, and the Acceptance Criteria does not exist, returning HTTP 404.
3. **Incomplete Model Capability Scoring**: `model_selector.py` fails to recognize multimodal vision models like `qwen2.5vl:latest` and `gemma3` (it only checks `"vision"` in model strings, missing `"vl"` and `"gemma3"`), and lacks support for `qwen3.5`, `qwen3.8`, and `gemma4`.
4. **Model Selector Synchronization Gaps**: The model dropdown in Chat and Goals are independent and out-of-sync. When switching chat sessions, `chatModelSelect` updates its value but does not trigger `updateModelLabel()`, leaving the UI header badge displaying stale model information. There is no auto-refresh or completion notification when a model is pulled via `/api/models/pull`.
5. **SSE Chat Streaming Bottleneck & Silent Failures**: `Agent.run()` invokes `self.client.chat(...)` synchronously with `stream=False`. No token-by-token streaming occurs; the client waits tens of seconds with no output until the turn ends. If a worker thread crashes or exits unexpectedly, the SSE generator terminates without sending a `done` or `error` event, causing silent UI failures.
6. **Ephemeral Tool Execution Pills**: In `index.html`, tool execution status pills are only displayed inside `#thinkingBubble`. Once the `done` event is received, `#thinkingBubble` is removed from the DOM, erasing all visual records of the tools executed during that turn.
7. **Missing File Hallucination Loops**: When `read_file` cannot find a file, it returns `"File not found: ..."` without an `[Error]` prefix. Consequently, `Agent.run()` treats this as a successful observation (`is_failure=False`), does not trigger replanning, and allows smaller models to fall into infinite hallucination loops repeatedly guessing filenames.

---

## 2. Component Mapping & File Inventory

| Component | Files Involved | Key Classes / Functions |
| :--- | :--- | :--- |
| **Ollama Client Querying** | `src/ollama_agents/agent.py`<br>`src/ollama_agents/server.py`<br>`src/ollama_agents/planner.py` | `ollama.Client(host=host)`, `client.chat()`, `ollama.list()` |
| **Dynamic Model Discovery** | `src/ollama_agents/server.py`<br>`src/ollama_agents/model_selector.py`<br>`src/ollama_agents/cluster.py` | `api_list_models()`, `get_installed_ollama_models()`, `select_best_local_model()`, `refresh_cluster_status()` |
| **Model Synchronization** | `src/ollama_agents/static/index.html` | `fetchInstalledModels()`, `updateModelLabel()`, `switchSession()`, `chatModelSelect`, `goalModelSelect` |
| **Multimodal Payload Pipeline** | `src/ollama_agents/server.py`<br>`src/ollama_agents/agent.py`<br>`src/ollama_agents/static/index.html` | `api_upload_file()`, `api_chat_stream()`, `SingleTaskRequest.attachment`, `Agent.run()`, `self.history` |
| **SSE Chat Streaming** | `src/ollama_agents/server.py`<br>`src/ollama_agents/agent.py` | `api_chat_stream()`, `event_generator()`, `on_event_callback`, `emit()` |
| **Conversation State & Sessions** | `src/ollama_agents/server.py`<br>`src/ollama_agents/memory.py` | `api_get_chat_history()`, `api_list_chat_sessions()`, `api_delete_chat_session()`, `SESSION_AGENTS`, `MemoryStore.save_chat_message()` |
| **Tool Execution & Loop Prevention** | `src/ollama_agents/agent.py`<br>`src/ollama_agents/tool.py`<br>`src/ollama_agents/tools/actions.py` | `Agent._execute_tool()`, `Tool.execute()`, `read_file()`, `list_workspace_files()` |

---

## 3. Detailed Findings & Gap Analysis

### 3.1 Ollama Client Querying & Wrapper Analysis
- **Current Logic**:
  - `agent.py` line 124: `self.client = ollama.Client(host=host)`.
  - `agent.py` line 500: `response = self.client.chat(model=self.model, messages=self.history, tools=tool_schemas, options=options)`.
  - `cluster.py` line 37-97: Secondary laptops communicate via direct HTTP requests (`urllib.request`) to remote Ollama `/api/tags` and `/api/ps` ports.
- **Identified Gaps**:
  - `stream=False` is hardcoded in `agent.py` (line 500). Ollama supports chunk streaming with `stream=True`, but the agent runs in a blocking manner.
  - While `ollama.ResponseError` is caught (line 506) for tool schema errors, network connection dropouts (`httpx.ConnectError`, timeouts) are unhandled and propagate as raw exceptions.
  - When communicating with remote worker nodes, `Agent` is re-instantiated with `host=node.host_url`, which functions correctly, but if the remote node drops offline mid-execution, no failover to localhost or another cluster node is attempted.

### 3.2 Dynamic Model Discovery (`/api/models/installed`)
- **Exact File**: `src/ollama_agents/server.py` (lines 124-141)
- **Current Logic**:
  ```python
  @app.get("/api/models")
  def api_list_models():
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
          return {"models": names if names else ["deepseek-r1:8b", "llama3.1:latest"], "pulling": list(PULLING_MODELS.keys())}
      except Exception as e:
          return {"models": ["deepseek-r1:8b", "llama3.1:latest"], "error": str(e), "pulling": list(PULLING_MODELS.keys())}
  ```
- **Identified Gaps**:
  1. **Endpoint Name Mismatch**: The endpoint is registered as `/api/models`, but `ORIGINAL_REQUEST.md` (R1, R4, Acceptance Criteria) mandates `/api/models/installed`. Any automated test or frontend component hitting `/api/models/installed` receives HTTP 404.
  2. **Cluster Node Model Aggregation**: `/api/models` only inspects the local machine's Ollama instance. If worker nodes are connected via `cluster_manager`, their models are not listed in this endpoint unless queried via `/api/cluster/nodes`.
  3. **Capability Tagging**: The endpoint returns plain strings without identifying which models support vision/multimodal, coding, or reasoning.
- **Model Capability Scoring in `model_selector.py`**:
  - Lines 18-26 (`MODEL_CAPABILITY_SCORES`) and lines 59-75 (`select_best_local_model`):
    ```python
    if "deepseek-r1" in m_lower:
        score += 40 if task_type == "reasoning" else 30
    elif "coder" in m_lower:
        score += 45 if task_type == "coding" else 20
    elif "llama3.1" in m_lower:
        score += 35 if task_type == "general" else 25
    elif "vision" in m_lower:
        score += 45 if task_type == "vision" else 10
    ```
  - **Flaw**: Multimodal models like `qwen2.5vl:latest` have `vl`, NOT `vision`! Incoming models like `gemma3` (multimodal by design) have neither `vision` nor `coder` in their tag. They are completely ignored for vision tasks.

### 3.3 Model Selector Population & Cross-Tab Synchronization
- **Exact File**: `src/ollama_agents/static/index.html` (lines 802-820, 1070-1075)
- **Current Logic**:
  - `fetchInstalledModels()` fetches `${API_BASE}/api/models` once on DOM load and sets the innerHTML of `chatModelSelect` and `goalModelSelect`.
  - When switching chat sessions (`fetchChatHistory` line 1070):
    ```javascript
    if (lastUsedModel) {
        const modelSel = document.getElementById("chatModelSelect");
        if (modelSel && Array.from(modelSel.options).some(o => o.value === lastUsedModel)) {
            modelSel.value = lastUsedModel;
        }
    }
    ```
- **Identified Gaps**:
  1. `updateModelLabel(lastUsedModel)` is **not called** when restoring `lastUsedModel`. The UI badge (`chatModelBadge`) displays the old model name even though `chatModelSelect.value` has changed.
  2. If the user changes `chatModelSelect`, `goalModelSelect` does not update (and vice-versa).
  3. When `pullModel()` is invoked (line 1884), `fetchInstalledModels()` is called immediately while the background thread is still downloading. The model is not yet present, and when the download finishes, the UI never updates because there is no completion notification or polling.
  4. There is no manual "Refresh Models" button on the UI header or Model Hub tab.

### 3.4 Multimodal Payload Handling (Gemma 3, Qwen2.5-VL)
- **Exact Files**:
  - `src/ollama_agents/server.py` (lines 378, 418, 421, 484, 493)
  - `src/ollama_agents/agent.py` (lines 393-416, 456, 500)
  - `.venv/Lib/site-packages/ollama/_types.py` (lines 161-187, 318-328)
  - `src/ollama_agents/static/index.html` (lines 1194-1235)
- **The Flow and Root Cause of the Bug**:
  1. The user uploads an image (e.g. `diagram.png`) via `btnUploadFile`.
  2. `/api/upload` writes the file to `Path.home() / "ollama_workspace" / "uploads" / "diagram.png"`, and returns `filepath: "uploads/diagram.png"`.
  3. The frontend sends:
     ```json
     {
       "prompt": "[Attached File: uploads/diagram.png] What is in this picture?",
       "model": "qwen2.5vl:latest",
       "attachment": "uploads/diagram.png"
     }
     ```
  4. In `server.py` (lines 484-493):
     ```python
     mem.save_chat_message(session_id=session_key, role="user", content=req.prompt, attachment=req.attachment or "", model=req.model)
     ...
     res = agent.run(req.prompt, max_turns=req.max_turns, on_event=on_event_callback)
     ```
     Notice: **`req.attachment` is discarded!** It is stored in SQLite but never passed into `agent.run()`.
  5. In `agent.py`: `Agent.run()` does not have an `images` or `attachment` parameter.
  6. `self.history.append({"role": "user", "content": user_prompt})` — **No `"images"` key exists.**
  7. When `self.client.chat(...)` is called, Ollama receives pure text: `"[Attached File: uploads/diagram.png] What is in this picture?"`. Ollama NEVER receives the image bytes or base64 encoding!
  8. **Ollama Python Library Constraint**: In `ollama/_types.py` line 178-180:
     If a relative path `"uploads/diagram.png"` were passed into `images`, Ollama checks `Path("uploads/diagram.png").exists()`. Since Python's working directory is the project root, this path does not exist. Ollama then throws:
     `ValueError: File uploads/diagram.png does not exist`!
  9. **Text Models vs Multimodal Models**: If a user uploads an image while `deepseek-r1:8b` or `llama3.1:latest` is selected, Ollama returns `400 Bad Request: model "deepseek-r1:8b" does not support images`. The framework needs to either detect this and auto-route image analysis to an installed multimodal model (`qwen2.5vl`, `gemma3`, `llama3.2-vision`), or warn the user.
  10. **Video Attachments**: If a video (`.mp4`, `.webm`, `.mov`) is attached, Ollama models do not process raw MP4 containers directly. Frame sampling (e.g., 2–4 keyframes converted to JPEG base64) must be extracted and injected into the `images` payload.

### 3.5 SSE Chat Streaming (`/api/chat/stream`)
- **Exact Files**:
  - `src/ollama_agents/server.py` (lines 446-525)
  - `src/ollama_agents/agent.py` (lines 419-425, 499-505)
- **Current Logic**:
  - `api_chat_stream` spawns a background `threading.Thread(target=run_worker, daemon=True)`.
  - `run_worker` executes `agent.run(req.prompt, on_event=on_event_callback)`.
  - An `async def event_generator()` loops over `event_queue.get_nowait()` and yields SSE data chunks `data: {"type": ...}\n\n`.
- **Identified Gaps**:
  1. **No Token Streaming**: `agent.py` calls `self.client.chat(..., stream=False)`. It does NOT stream tokens. `agent.run()` only emits `thought` (after the entire turn finishes, if `<think>` tags exist), `tool_start`, `tool_end`, and `answer`. As a result, the user sees no progressive text output during lengthy generations.
  2. **Silent Failure on Worker Abort**:
     ```python
     if not worker_thread.is_alive() and event_queue.empty():
         return
     ```
     If `worker_thread` dies unexpectedly (OOM, unhandled exception before `try`, or thread cancellation), the generator silently closes the HTTP stream. The browser receives no `done` or `error` event, leaving `finalResult = ""` and appending `*(Task execution finished)*`.
  3. **Inconsistent Error Attribution**: The `done` event includes `"model": req.model`, but the `error` event (`event_queue.put({"type": "error", "error": str(err)})`) omits the `model` key.

### 3.6 Stateful Conversation History & Session Management
- **Exact Files**:
  - `src/ollama_agents/server.py` (lines 380-435, 527-560)
  - `src/ollama_agents/memory.py` (lines 76-86, 191-248)
- **Current Logic**:
  - Sessions are tracked in SQLite table `chat_messages(id, session_id, role, content, attachment, model, created)`.
  - In-memory agents are stored in `SESSION_AGENTS[session_key]`.
  - When a message is sent to an existing session with the same model, `SESSION_AGENTS[session_key]` preserves the multi-turn context.
  - When switched to a different model, a new `Agent` is instantiated and the last 30 messages are rehydrated.
- **Identified Gaps**:
  1. **Rehydration Multimodal Loss**: When rehydrating history from `memory.get_chat_history()`, `pm["attachment"]` is ignored; only `pm["content"]` is appended. Context from previous image queries is lost upon model switch or server restart.
  2. **Tool Execution History Ephemeral**: Intermediate tool executions are emitted via SSE during run-time, but are not persisted into `chat_messages`. Only the final answer is stored with `role="agent"`.
  3. **UI Tool Pill Disappearance**: In `index.html`, tool execution is rendered only inside `#thinkingBubble`. As soon as `evt.type === "done"` fires, the thinking bubble is removed:
     ```javascript
     const tb = document.getElementById("thinkingBubble");
     if (tb) tb.remove();
     ```
     The rendered message contains no record of which tools were executed, violating R3 ("live tool execution pills").

### 3.7 Tool Execution Error Handling & Missing File Hallucinations
- **Exact Files**:
  - `src/ollama_agents/tools/actions.py` (lines 171-189)
  - `src/ollama_agents/agent.py` (lines 323-337, 660-690)
- **Current Logic in `actions.py`**:
  ```python
  def read_file(filepath: str, max_chars: int = 8000) -> str:
      try:
          path = _safe_path(filepath)
          if not path.exists():
              return f"File not found: {path}. Do not guess random filenames. Use list_workspace_files to see what files exist."
          ...
  ```
- **Current Logic in `agent.py`**:
  ```python
  is_failure = output.startswith("[Tool Failure]") or output.startswith("[Error]")
  if is_failure and self.planner and remaining_steps:
      ...
  ```
- **The Critical Bug**:
  1. `"File not found: ..."` does **not** start with `[Error]` or `[Tool Failure]`.
  2. `is_failure` is evaluated as `False`.
  3. `agent.py` does not record the error in `errors` and does not call `self.planner.replan()`.
  4. The LLM perceives `"File not found: ..."` as a normal informational response and immediately calls `read_file` again with another guessed filename (e.g. `app.js`, `index.js`, `MainActivity.java`, etc.).
  5. There is no repetition detector in `agent.py`. The model enters an uncontrolled hallucination loop until `max_turns` is reached.

---

## 4. Exact File Paths, Line Numbers, and Proposed Code Fixes

### Fix 1: Add `/api/models/installed` and Dynamic Multimodal Discovery
**Target File**: `src/ollama_agents/server.py` (Line 124)  
**Target File**: `src/ollama_agents/model_selector.py` (Line 18)

#### In `server.py`:
Add `/api/models/installed` endpoint (and keep `/api/models` as an alias):
```python
@app.get("/api/models/installed")
@app.get("/api/models")
def api_list_models():
    """List all available Ollama models installed locally and across cluster nodes."""
    import ollama
    from ollama_agents.model_selector import is_multimodal_model
    from ollama_agents.cluster import cluster_manager
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

        # Include cluster models if any remote nodes are active
        cluster_status = cluster_manager.refresh_cluster_status()
        for cm in cluster_status.get("aggregate_models", []):
            if cm not in names:
                names.append(cm)

        # Fallback if Ollama is empty or initializing
        final_names = names if names else ["deepseek-r1:8b", "llama3.1:latest"]
        
        # Annotate capability metadata
        model_details = [
            {
                "name": name,
                "is_multimodal": is_multimodal_model(name),
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
        return {
            "status": "error",
            "models": ["deepseek-r1:8b", "llama3.1:latest"],
            "error": str(e),
            "pulling": list(PULLING_MODELS.keys())
        }
```

#### In `model_selector.py`:
Add helper `is_multimodal_model` and update `select_best_local_model`:
```python
MULTIMODAL_KEYWORDS = ["vision", "vl", "gemma3", "llava", "moondream", "minicpm-v"]

def is_multimodal_model(model_name: str) -> bool:
    """Return True if model_name supports multimodal vision (image/video)."""
    m = model_name.lower()
    return any(k in m for k in MULTIMODAL_KEYWORDS)

def select_best_local_model(task_type: str = "reasoning", preferred: Optional[str] = None) -> str:
    installed = get_installed_ollama_models()
    if not installed:
        return preferred or "deepseek-r1:8b"
    if preferred and preferred in installed:
        return preferred

    best_model = installed[0]
    highest_score = -1

    for m in installed:
        m_lower = m.lower()
        score = 50
        if "deepseek-r1" in m_lower:
            score += 45 if task_type == "reasoning" else 25
        elif any(c in m_lower for c in ["coder", "qwen2.5", "qwen3.5", "qwen3.8"]):
            score += 45 if task_type == "coding" else 25
        elif is_multimodal_model(m_lower):
            score += 50 if task_type == "vision" else 15
        elif "llama3" in m_lower:
            score += 35 if task_type == "general" else 20

        if score > highest_score:
            highest_score = score
            best_model = m

    return best_model
```

---

### Fix 2: Full Multimodal Payload Pipeline (Gemma 3 & Qwen2.5-VL)
**Target File**: `src/ollama_agents/agent.py` (Lines 393-470, 500)  
**Target File**: `src/ollama_agents/server.py` (Lines 384-435, 446-505)

#### In `agent.py`:
Modify `Agent.run()` to accept `images: Optional[List[str]] = None`:
```python
    def run(
        self,
        user_prompt: str,
        max_turns: Optional[int] = None,
        task_id: Optional[str] = None,
        on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
        images: Optional[List[str]] = None,
    ) -> str:
        ...
        user_msg: Dict[str, Any] = {"role": "user", "content": user_prompt}
        if images:
            user_msg["images"] = images
        self.history.append(user_msg)
```

#### In `server.py`:
Implement a helper to resolve and base64-encode attachments (images & video keyframes):
```python
import base64

def resolve_multimodal_images(attachment_path: str) -> List[str]:
    """Resolve workspace file attachment and return base64-encoded image strings for Ollama payload."""
    if not attachment_path:
        return []

    workspace_dir = Path.home() / "ollama_workspace"
    target = workspace_dir / attachment_path
    if not target.exists():
        target = Path(attachment_path)
    if not target.exists() or not target.is_file():
        return []

    ext = target.suffix.lower().lstrip(".")
    image_exts = {"png", "jpg", "jpeg", "webp", "bmp", "gif"}
    video_exts = {"mp4", "webm", "mov", "avi", "mkv"}

    if ext in image_exts:
        try:
            b64_str = base64.b64encode(target.read_bytes()).decode("utf-8")
            return [b64_str]
        except Exception as e:
            logger.error("Failed to read image %s: %s", target, e)
            return []

    elif ext in video_exts:
        # Extract 2-4 representative keyframes from video for multimodal models
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
```
Pass `resolved_images` into `agent.run(req.prompt, images=resolved_images, ...)` in both `api_run_single_task` and `api_chat_stream`.

If the requested model is NOT multimodal, either:
- Automatically route the visual analysis through an installed multimodal model (e.g. `qwen2.5vl:latest` or `gemma3`), or
- Strip the `images` argument and append a note in the prompt: `"[Note: Attached image was uploaded to {attachment_path}. Switch to Gemma 3 or Qwen2.5-VL for direct image comprehension.]"`.

---

### Fix 3: Resilient SSE Chat Streaming & Model Attribution
**Target File**: `src/ollama_agents/server.py` (Lines 490-525)

1. Ensure the worker catches all exceptions and guarantees a concluding event:
```python
    def run_worker():
        try:
            res = agent.run(req.prompt, max_turns=req.max_turns, on_event=on_event_callback, images=images)
            mem.save_chat_message(session_id=session_key, role="agent", content=res, model=req.model)
            event_queue.put({"type": "done", "result": res, "model": req.model})
        except MaxTurnsExceeded as mte:
            last_out = getattr(mte, 'last_output', '') or ''
            res = (
                f"{last_out}\n\n"
                f"*(Note: Reached turn limit of {mte.turns}. You can ask me to continue or expand on any step above.)*"
            )
            mem.save_chat_message(session_id=session_key, role="agent", content=res, model=req.model)
            event_queue.put({"type": "done", "result": res, "model": req.model})
        except Exception as err:
            logger.exception("Chat worker failed: %s", err)
            event_queue.put({"type": "error", "error": str(err), "model": req.model})
        finally:
            event_queue.put({"type": "_stream_closed"})
```
2. In `event_generator()`:
```python
    async def event_generator():
        while True:
            try:
                while not event_queue.empty():
                    item = event_queue.get_nowait()
                    if item.get("type") == "_stream_closed":
                        return
                    yield f"data: {json.dumps(item)}\n\n"
                    if item.get("type") in ("done", "error"):
                        return
                if not worker_thread.is_alive() and event_queue.empty():
                    # Fallback guard against silent thread death
                    yield f"data: {json.dumps({'type': 'error', 'error': 'Worker terminated unexpectedly', 'model': req.model})}\n\n"
                    return
                await asyncio.sleep(0.08)
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'error': str(e), 'model': req.model})}\n\n"
                return
```

---

### Fix 4: Persistent Tool Execution Pills & Cross-Tab Dropdown Sync
**Target File**: `src/ollama_agents/static/index.html` (Lines 802-820, 1070-1075, 1260-1290)

1. **Persistent Tool Execution Pills**:
   - Collect executed tools in an array `executedToolsThisTurn = []` during `tool_start` and `tool_end` SSE events.
   - When calling `appendMessage(role, content, fileAttachment, modelName, toolsUsed)`, render a persistent tool badge row at the top or bottom of the bubble:
     ```html
     <div class="tool-pills-row">
         ${toolsUsed.map(t => `<span class="tool-pill">✓ ${t}</span>`).join('')}
     </div>
     ```
2. **Auto-Synchronized Model Selectors & Label**:
   - When `fetchChatHistory` updates `modelSel.value = lastUsedModel`, add `updateModelLabel(lastUsedModel)`.
   - Add a bidirectional `syncModelSelection(model)` helper so changing the model in Chat or Goals propagates across tabs.
   - Add a manual `🔄 Refresh Models` button to the header and Model Hub tab.

---

### Fix 5: Tool Execution Error Formatting & Anti-Hallucination Guard
**Target File**: `src/ollama_agents/tools/actions.py` (Line 180)  
**Target File**: `src/ollama_agents/agent.py` (Lines 646-665)

1. In `actions.py`:
   ```python
   def read_file(filepath: str, max_chars: int = 8000) -> str:
       try:
           path = _safe_path(filepath)
           if not path.exists():
               # Prepend [Error] so agent detects failure and triggers replanning/listing
               workspace = Path.home() / "ollama_workspace"
               existing = [str(p.relative_to(workspace)) for p in workspace.rglob("*") if p.is_file()][:10]
               existing_str = ", ".join(existing) if existing else "None"
               return f"[Error] File not found: '{filepath}'. Do not guess filenames! Files currently in workspace: [{existing_str}]. Call list_workspace_files() for full directory."
           ...
   ```
2. In `agent.py`:
   Add a repetition detector to prevent the agent from repeatedly calling the same tool with identical arguments when it fails:
   ```python
   # Anti-hallucination loop guard:
   call_sig = f"{fn_name}:{json.dumps(fn_args, sort_keys=True)}"
   recent_calls = getattr(self, "_recent_tool_signatures", [])
   recent_calls.append(call_sig)
   self._recent_tool_signatures = recent_calls[-10:]

   if recent_calls.count(call_sig) >= 3:
       output = (
           f"[Tool Failure] Repeated identical tool call detected ({fn_name}). "
           "You are repeating failed actions. Stop guessing and use list_workspace_files or provide Final Answer."
       )
   else:
       output = self._execute_tool(fn_name, fn_args)
   ```

---

## 5. Verification Checklist

To independently verify these findings:
1. **Ollama Multimodal Payload**: Run a script that sends an image attachment to `/api/chat/stream` with `model: "qwen2.5vl:latest"` or `"gemma3"`. Verify whether the model correctly describes the contents of the image or claims it cannot see the file.
2. **Missing Endpoint**: Run `curl -i http://localhost:8100/api/models/installed`. Confirm it currently returns HTTP 404.
3. **SSE Truncation**: Terminate the worker thread or simulate an unhandled exception during SSE streaming. Confirm that the stream currently terminates abruptly with no `done` or `error` frame.
4. **Missing File Loop**: Ask the agent to read `nonexistent_file_xyz.txt`. Observe that `read_file` returns `"File not found: ..."` without `[Error]`, causing the agent to repeatedly guess filenames without triggering replanning.
