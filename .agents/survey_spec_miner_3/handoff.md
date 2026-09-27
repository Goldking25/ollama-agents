# Handoff Report: Specification Mining for Media Studio, Core Tab APIs, and Test Suite

**Agent Name:** `survey_spec_miner_3`  
**Handoff Type:** Hard  
**Working Directory:** `e:\Learning\Python\agent_test\.agents\survey_spec_miner_3`  
**Date:** 2026-09-26  

---

## 1. Observation

Direct observations from inspecting `ORIGINAL_REQUEST.md`, `src/ollama_agents/`, and the repository root:

1. **User Request & Acceptance Criteria**:
   - `ORIGINAL_REQUEST.md:53-58`: Follow-up R2 demands a dedicated Media Studio tab for image generation/editing via Stable Diffusion WebUI Forge API (ports 7860/default) and video generation via ComfyUI API (ports 8188/8000/default), with live visual connection health indicators, direct txt2img/img2img/video generation, saving to `~/ollama_workspace/images/` and `~/ollama_workspace/videos/`, and in-browser playback/gallery.
   - `ORIGINAL_REQUEST.md:74`: *"Every tab in the header (chat, goals, files, cluster, reflections, hfmodels, and media) renders its view pane without JavaScript errors or broken layout states."*
   - `ORIGINAL_REQUEST.md:80-82`: *"Integration test suite tests/test_all_tabs_and_endpoints.py exits with status code 0. All FastAPI endpoints (/api/chat/history, /api/chat/sessions, /api/workspace/files, /api/goals, /api/cluster/nodes, /api/models/installed, /api/reflections, /api/system/stats) return HTTP 200 with valid JSON payloads. Real-time SSE streaming (/api/chat/stream) completes with done event and proper model attribution."*

2. **Frontend UI State (`src/ollama_agents/static/index.html`)**:
   - Lines 361–368: `.tab-switcher` header contains buttons for `chat`, `goals`, `files`, `cluster`, `reflections`, and `hfmodels`. There is **no** `media` button.
   - Lines 383–644: Tab panes exist for `#tab-chat`, `#tab-goals`, `#tab-cluster`, `#tab-reflections`, `#tab-hfmodels`, and `#tab-files`. There is **no** `#tab-media` pane.
   - Lines 822–847: `openTab(tabName)` has handlers for `goals`, `reflections`, `hfmodels`, `files`, but **no** handler for `media`.

3. **Backend Server State (`src/ollama_agents/server.py`)**:
   - **Duplicate Endpoint Defect**:
     - Line 88: `@app.get("/api/workspace/files")` returns `{"workspace_path": str(workspace_dir), "files": files_list}` where each item has `{name, relative_path, full_path, url, size_bytes}`.
     - Line 561: `@app.get("/api/workspace/files")` returns `{"status": "success", "workspace_path": str(workspace), "files": files}` where each item has `{name, relative_path, size, size_formatted, modified, type, extension, download_url}`.
     - Line 88 is registered first and shadows line 561. This breaks `renderWorkspaceFiles` in `index.html` (lines 1341–1374), which expects `f.type`, `f.size_formatted`, `f.modified`, and `f.download_url`.
   - **Missing Endpoint Defect**:
     - Line 124 defines `@app.get("/api/models")`. Endpoint `@app.get("/api/models/installed")` does **not** exist in `server.py`, violating Acceptance Criteria line 81.
   - **Missing Media Studio REST Endpoints**:
     - No REST endpoints exist for `/api/media/status`, `/api/media/generate-image`, `/api/media/edit-image`, `/api/media/generate-video`, or `/api/media/gallery`.

4. **Underlying Tools State (`src/ollama_agents/tools/`)**:
   - `src/ollama_agents/tools/image_gen.py:16`: `generate_image_sd_forge` posts to `{api_url}/sdapi/v1/txt2img` (default `http://127.0.0.1:7860`), decodes `images[0]`, saves to `~/ollama_workspace/images/forge_gen_*.png`, and returns a markdown preview.
   - `src/ollama_agents/tools/image_gen.py:86`: `edit_image_sd_forge` posts to `{api_url}/sdapi/v1/img2img`, decodes `images[0]`, saves to `~/ollama_workspace/images/forge_edit_*.png`.
   - `src/ollama_agents/tools/comfyui.py:17`: `generate_video_comfyui` posts workflow to `{api_url}/prompt` (default `http://127.0.0.1:8000`), polls `{api_url}/history/{prompt_id}` for up to 360s, fetches from `{api_url}/view`, and saves to `~/ollama_workspace/videos/comfy_vid_*.mp4`.
   - `src/ollama_agents/tools/android_builder.py:21`: `build_android_apk` compiles Android Java projects into `app-debug.apk` in workspace.

5. **Multimodal Disconnect (`src/ollama_agents/agent.py` & `server.py`)**:
   - `server.py:378,418`: `SingleTaskRequest` receives `attachment`, which is recorded in SQLite chat messages, but `req.attachment` is **never** passed into `agent.run(req.prompt)`.
   - `agent.py:393,456`: `Agent.run` only accepts `user_prompt: str`. `self.history.append({"role": "user", "content": user_prompt})` never populates the `images` field required by Ollama for multimodal models (Gemma 3, Qwen2.5-VL).

6. **Test Suite State**:
   - No `tests/` directory exists in the workspace.
   - `tests/test_all_tabs_and_endpoints.py` does not exist.

---

## 2. Logic Chain

1. From Observation 1, the user's specification requires a dedicated Media Studio tab (`data-tab="media"`), live status indicators for SD Forge and ComfyUI, direct image/video generation forms, in-browser playback/gallery, and programmatic verification passing with code 0 on `tests/test_all_tabs_and_endpoints.py`.
2. From Observation 2, while the other tabs (`chat`, `goals`, `files`, `cluster`, `reflections`, `hfmodels`) exist in `index.html`, the `media` tab button, tab pane, and openTab routing logic are completely absent from the frontend.
3. From Observation 4, the low-level tool functions `generate_image_sd_forge`, `edit_image_sd_forge`, and `generate_video_comfyui` are implemented and functional, but from Observation 3, there are no FastAPI REST endpoints exposing them directly to the Web UI or providing health check diagnostics.
4. From Observation 3, the duplicate route `@app.get("/api/workspace/files")` causes FastAPI to route exclusively to line 88, which omits the rich metadata fields (`type`, `size_formatted`, `modified`, `download_url`) expected by `index.html:1341-1374`.
5. From Observation 3 and Acceptance Criteria 81, `/api/models/installed` is an explicit requirement that currently returns 404 because only `/api/models` exists.
6. From Observation 5, multimodal models cannot receive images because neither `server.py` passes attachments to `Agent.run` nor does `Agent.run` construct the `images` list in the Ollama message payload.
7. From Observation 6, the required integration test script `tests/test_all_tabs_and_endpoints.py` is absent and must be implemented from scratch to cover all REST endpoints, SSE streaming, WebSockets, attachments, tools, and file management functions.

---

## 3. Caveats

1. **Live Local Services**: Local instances of SD WebUI Forge (port 7860) and ComfyUI (port 8000/8188) may or may not be active in the user's background during test runs. All tools and endpoints must therefore support graceful offline degradation (informative offline badge / diagnostic messages without crashing).
2. **Local Ollama Daemon**: In test environments where local Ollama models may not be pre-pulled or daemon is offline, tests must use mock fallbacks or robust error handling to guarantee exit code 0.

---

## 4. Conclusion

The framework's core libraries are well-structured, but full alignment with `ORIGINAL_REQUEST.md` requires 5 targeted fixes:
1. **Add Media Studio Tab & REST Endpoints**: Add `<button data-tab="media">` and `<div id="tab-media">` to `index.html` with connection health badges, generation forms, and gallery; add `/api/media/status`, `/api/media/generate-image`, `/api/media/edit-image`, `/api/media/generate-video`, and `/api/media/gallery` to `server.py`.
2. **Fix Duplicate `/api/workspace/files` Route**: Remove lines 88–104 in `server.py` so line 561 provides full metadata to the Files explorer.
3. **Add `/api/models/installed` Alias**: Route `/api/models/installed` to `api_list_models`.
4. **Bridge Multimodal Attachments**: Pass attachment image bytes/paths into `Agent.run()` and include `images` in Ollama chat payloads.
5. **Create Automated Integration Test Suite**: Create `tests/test_all_tabs_and_endpoints.py` testing all endpoints, SSE, WebSockets, tools, and file management.

All detailed findings, schemas, and specifications have been recorded in `e:\Learning\Python\agent_test\.agents\survey_spec_miner_3\survey_media_and_core_apis.md`.

---

## 5. Verification Method

To verify these findings:
1. **Inspect UI Tabs**:
   - Check `src/ollama_agents/static/index.html` lines 361–368 and verify absence of `data-tab="media"`.
2. **Inspect Server Endpoints**:
   - Check `src/ollama_agents/server.py` lines 88 vs 561 to confirm duplicate definition of `/api/workspace/files`.
   - Check `src/ollama_agents/server.py` line 124 to confirm absence of `/api/models/installed`.
3. **Inspect Multimodal Flow**:
   - Check `src/ollama_agents/server.py:384,446` and `agent.py:393,456` to confirm attachments are never injected into the Ollama payload.
4. **Inspect Test Suite**:
   - Verify that directory `tests/` and file `tests/test_all_tabs_and_endpoints.py` do not exist.
