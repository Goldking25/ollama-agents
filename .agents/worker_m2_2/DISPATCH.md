## 2026-09-26T13:40:23Z
You are worker_m2_2, a teamwork_preview_worker subagent.
Working Directory: e:\Learning\Python\agent_test\.agents\worker_m2_2
Authoritative User Request: e:\Learning\Python\agent_test\ORIGINAL_REQUEST.md
Scope Document: e:\Learning\Python\agent_test\PROJECT.md
Specification Report: e:\Learning\Python\agent_test\.agents\survey_spec_miner_3\survey_media_and_core_apis.md
Predecessor Progress: e:\Learning\Python\agent_test\.agents\worker_m2_1\progress.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

MISSION:
Implement Milestone M2: Dedicated Media Studio Tab & Resilient Forge/ComfyUI Pipelines (Features 7 to 12).

INSTRUCTIONS:
1. Read ORIGINAL_REQUEST.md (Requirement R2 and Acceptance Criteria lines 74 & 77), PROJECT.md (Features 7-12 & Interface Contracts), and survey_media_and_core_apis.md.
2. In src/ollama_agents/server.py, implement the Media Studio REST API endpoints:
   - GET /api/media/status: Query SD Forge (default http://127.0.0.1:7860) and ComfyUI (default http://127.0.0.1:8000 or 8188) with configurable url params and short timeout. Return {"forge": {"online": bool, "url": str, "error": str | None}, "comfy": {"online": bool, "url": str, "error": str | None}}.
   - POST /api/media/generate-image: Use generate_image_sd_forge from src/ollama_agents/tools/image_gen.py. Save to ~/ollama_workspace/images/, return {"status": "success", "file_path": str, "filename": str, "url": f"/workspace/images/{filename}"}. Handle offline service cleanly (return 503 or error dict).
   - POST /api/media/edit-image: Use edit_image_sd_forge from src/ollama_agents/tools/image_gen.py with image reference. Save to ~/ollama_workspace/images/, return {"status": "success", "file_path": str, "filename": str, "url": f"/workspace/images/{filename}"}.
   - POST /api/media/generate-video: Use generate_video_comfyui from src/ollama_agents/tools/comfyui.py. Save to ~/ollama_workspace/videos/, return {"status": "success", "file_path": str, "filename": str, "url": f"/workspace/videos/{filename}"}.
   - GET /api/media/gallery: Ensure ~/ollama_workspace/images/ and ~/ollama_workspace/videos/ exist. Return {"images": [{"name": str, "url": str, "size": int, "modified": float}], "videos": [{"name": str, "url": str, "size": int, "modified": float}]}.
3. In src/ollama_agents/static/index.html:
   - Header tab switcher: Add <button class="tab-btn" data-tab="media" onclick="openTab('media')">🎨 Media Studio</button>.
   - View pane: Add <div id="tab-media" class="tab-pane"> with:
     * Diagnostic Badges for SD Forge (7860) and ComfyUI (8000/8188) with Online/Offline indicators, configurable URL inputs, and "Check Health" button.
     * Direct Txt2Img generation form (prompt, negative prompt, width, height, steps, cfg scale, Generate button).
     * Img2Img image editing form (reference image upload/path, prompt, denoising strength, Edit button).
     * Prompt-driven video generation form (prompt, negative prompt, steps, frames, Generate Video button).
     * Interactive Workspace Gallery displaying images and videos with thumbnail previews, modal viewing for images, <video controls> inline playback for videos, and download links.
   - JS controllers:
     * Update openTab('media') to activate the pane and call loadMediaStudio().
     * Implement loadMediaStudio(), checkMediaHealth(), generateMediaImage(), editMediaImage(), generateMediaVideo(), loadMediaGallery().
4. Verify by running:
   python tests/test_all_tabs_and_endpoints.py
   Confirm all tests exit with status code 0.
5. Write your handoff report to e:\Learning\Python\agent_test\.agents\worker_m2_2\handoff.md and notify parent via send_message.

FILE OWNERSHIP:
You exclusively own:
- src/ollama_agents/server.py
- src/ollama_agents/static/index.html
DO NOT modify tests/ or files outside your ownership scope.
