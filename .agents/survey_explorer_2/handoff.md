# Handoff Report: Survey Explorer 2 (Ollama Integration, Models & Multimodal Pipeline)

**Agent ID**: `survey_explorer_2`  
**Date**: 2026-09-26  
**Type**: Hard Handoff (Investigation Complete)  
**Detailed Findings Document**: `e:\Learning\Python\agent_test\.agents\survey_explorer_2\survey_models_multimodal.md`

---

## 1. Observation

1. **Missing `/api/models/installed` Endpoint**:
   - In `src/ollama_agents/server.py`: Line 124 defines `@app.get("/api/models")`. A search across `server.py` for `/api/models/installed` returned 0 matches.
   - Requirement in `ORIGINAL_REQUEST.md` (Line 81): *"All FastAPI endpoints (/api/chat/history, /api/chat/sessions, /api/workspace/files, /api/goals, /api/cluster/nodes, /api/models/installed, /api/reflections, /api/system/stats) return HTTP 200 with valid JSON payloads."*
   - Calling `/api/models/installed` on the existing server results in HTTP 404 Not Found.

2. **Multimodal Disconnect (Gemma 3 & Qwen2.5-VL)**:
   - In `src/ollama_agents/server.py`: Lines 418 & 484 save the attachment to database: `mem.save_chat_message(session_id=session_key, role="user", content=req.prompt, attachment=req.attachment or "", model=req.model)`.
   - In `src/ollama_agents/server.py`: Lines 421 & 493 call `agent.run(req.prompt, max_turns=req.max_turns, ...)` — `req.attachment` is discarded and not passed to `agent.run()`.
   - In `src/ollama_agents/agent.py`: Lines 393-416 define `run(self, user_prompt: str, ...)`. There is no `images` or `attachment` parameter.
   - In `src/ollama_agents/agent.py`: Line 456 does `self.history.append({"role": "user", "content": user_prompt})`. No `images` field is included.
   - In `.venv/Lib/site-packages/ollama/_types.py`: Lines 161-187 show that Ollama requires either an absolute existing path or a base64 string. If a relative path such as `"uploads/photo.png"` is supplied, Ollama checks `Path(self.value).exists()` relative to the Python process CWD. Because uploads are saved to `~/ollama_workspace/uploads/`, this relative path fails and raises `ValueError: File uploads/photo.png does not exist`.

3. **Model Capability Classification Incompleteness**:
   - In `src/ollama_agents/model_selector.py`: Lines 70-71 check `elif "vision" in m_lower: score += 45 if task_type == "vision" else 10`.
   - Models like `qwen2.5vl:latest` contain `vl` (not `vision`), and `gemma3` contains neither. They are not recognized as vision models for visual tasks.

4. **SSE Chat Streaming Bottlenecks**:
   - In `src/ollama_agents/agent.py`: Line 500 calls `self.client.chat(model=self.model, messages=self.history, ...)` synchronously with `stream=False`. No token streaming events (`chunk` or `token`) are emitted to the client.
   - In `src/ollama_agents/server.py`: Lines 518-520 handle silent worker death: `if not worker_thread.is_alive() and event_queue.empty(): return`. If the thread crashes before enqueueing `done` or `error`, the stream terminates abruptly with no payload, causing the frontend to report `*(Task execution finished)*`.

5. **Model Label Desynchronization in UI**:
   - In `src/ollama_agents/static/index.html`: Line 1070 sets `modelSel.value = lastUsedModel;` upon session switch, but does not call `updateModelLabel(lastUsedModel)`. The header badge `chatModelBadge` remains stuck on the prior model name.

6. **Missing File Hallucination Loops**:
   - In `src/ollama_agents/tools/actions.py`: Line 181 returns `f"File not found: {path}. Do not guess random filenames. Use list_workspace_files to see what files exist."`.
   - In `src/ollama_agents/agent.py`: Line 661 checks `is_failure = output.startswith("[Tool Failure]") or output.startswith("[Error]")`.
   - Because `read_file`'s return value does not start with `[Error]`, `is_failure` evaluates to `False`. The planner's `replan()` is bypassed, and the agent enters an uninhibited hallucination loop repeatedly guessing filenames.

---

## 2. Logic Chain

1. **From Observation 1**: The client/test suite expects `GET /api/models/installed`, but the server only implements `/api/models`.  
   *Inference*: `/api/models/installed` must be added as an endpoint in `server.py` (either aliasing or superseding `/api/models`) returning HTTP 200 with model list and status.

2. **From Observation 2**: User attaches an image → Frontend sends `attachment: "uploads/foo.png"` → `server.py` receives it → `server.py` does not pass it to `agent.run()` → `agent.py` does not inject it into the message payload → Ollama receives pure text. Furthermore, if a relative path were passed, Ollama's `Image.serialize_model()` would raise `ValueError` because the path is relative to the workspace, not the project CWD.  
   *Inference*: `server.py` must resolve the attachment to an absolute path, verify existence, encode to base64, and pass `images=[base64_str]` to `agent.run()`. `Agent.run()` must accept `images` and append `{"role": "user", "content": ..., "images": [...]}` to `self.history`.

3. **From Observation 3**: Vision scoring checks `"vision" in m_lower`. Neither `qwen2.5vl` nor `gemma3` match this condition.  
   *Inference*: `is_multimodal_model()` must check `["vision", "vl", "gemma3", "llava", "moondream"]` to correctly identify and score vision models.

4. **From Observation 4**: `self.client.chat` is invoked synchronously and worker thread death exits the SSE generator without sending terminal events.  
   *Inference*: The SSE generator must guard against abrupt worker termination by yielding a fallback error event with model attribution, and ensure `event_queue.put` is enclosed in a bulletproof `try...finally` block.

5. **From Observation 5**: `chatModelSelect` updates value but does not call `updateModelLabel`.  
   *Inference*: `updateModelLabel()` must be invoked inside `fetchChatHistory` whenever `lastUsedModel` is set.

6. **From Observation 6**: `read_file` returns `"File not found: ..."` without `[Error]`, causing `is_failure` to be `False`.  
   *Inference*: Prefixing missing file outputs with `[Error]` and providing immediate listings of actual workspace files will trigger `is_failure`, activate `replan()`, and eliminate filename hallucination loops.

---

## 3. Caveats

- Physical GPU memory limits (VRAM) during simultaneous model loading of 16B/27B models on single laptops were not bench-tested; memory manager slot acquisition was analyzed statically.
- Video keyframe extraction requires `opencv-python` (`cv2`) or fallback image decoding. If `cv2` is not installed in `.venv`, a fallback frame extractor or image-only constraint must be observed.
- External Ollama server network connectivity assumes the local Ollama instance or secondary laptops on LAN respond within specified timeouts.

---

## 4. Conclusion

The Level 4 Ollama Agents framework possesses a solid foundation for local autonomous workflows, but suffers from broken multimodal data pipelines, a missing endpoint (`/api/models/installed`), silent SSE streaming failures, model label desynchronization, and a missing-file loop trigger in `read_file`.

All six issues have been diagnosed to exact lines of code with corresponding drop-in fixes detailed in `survey_models_multimodal.md`. Implementing these fixes will satisfy Requirements R1, R3, and their Acceptance Criteria.

---

## 5. Verification Method

1. **FastAPI Endpoint Check**:
   - Inspect `server.py` lines 124-141. Ensure `@app.get("/api/models/installed")` exists and returns HTTP 200.
   - Run integration check against `http://localhost:8100/api/models/installed`.
2. **Multimodal Flow Verification**:
   - Inspect `server.py` `api_chat_stream` and `agent.py` `Agent.run`. Confirm `images` parameter is passed and attached as base64 to `self.history[-1]["images"]`.
   - Verify that models such as `qwen2.5vl:latest` and `gemma3` receive image data and return visual descriptions.
3. **Error Handling & Loop Test**:
   - Inspect `actions.py` line 181. Ensure missing files return `[Error] File not found: ...`.
   - Test `Agent.run("Read nonexistent.txt")` and confirm `is_failure` is detected and replanning or a graceful halt occurs without spinning for 50 turns.
4. **SSE Streaming & Attribution**:
   - Test `/api/chat/stream` with an SSE consumer and verify that every stream terminates with either `{"type": "done", ..., "model": ...}` or `{"type": "error", ..., "model": ...}`.
