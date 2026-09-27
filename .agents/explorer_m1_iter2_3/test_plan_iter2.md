# Milestone M1 Iteration 2: Comprehensive Test Coverage & Regression Verification Plan

**Document**: `test_plan_iter2.md`  
**Author**: `explorer_m1_iter2_3` (Teamwork Explorer)  
**Milestone**: Milestone M1 (Dynamic Model Availability & Multimodal Support) — Iteration 2  
**Target Implementer**: `worker_m1_2`  
**Target Quality Gates**: `challenger_m1_3`, `reviewer_m1_3`, Orchestrator  
**Date**: 2026-09-26  
**Status**: AUTHORITATIVE_TEST_PLAN  

---

## 1. Executive Summary

Milestone M1 Iteration 1 delivered 6 core features covering dynamic model listing, multimodal image encoding, SSE chat streaming with attribution, anti-hallucination loop interruption, and UI badge synchronization. However, the iteration failed its quality gate review due to a critical model routing defect in `src/ollama_agents/model_selector.py`:
- `select_best_local_model("vision")` selected `deepseek-r1:8b` (score 80) over `qwen2.5vl:latest` (score 70) due to branch ordering in an `elif` ladder where `"qwen2.5"` shadowed the multimodal classification check `is_multimodal_model()`.
- Furthermore, the existing empirical test suite (`tests/test_m1_empirical_challenges.py`, 17 tests) tested `is_multimodal_model()` in isolation but lacked any test cases for `select_best_local_model()`, allowing this regression to escape the initial test suite.

This document establishes the **authoritative test specification** for Milestone M1 Iteration 2. It provides:
1. **Root cause & mathematical proof** of the Iteration 1 failure.
2. **Exact verification test cases** for `qwen2.5vl:latest`, `gemma3:latest`, and all multimodal variants.
3. **Complete drop-in test suite expansion** (`TestM1ModelRoutingAndSelection`, 10 test methods) for `tests/test_m1_empirical_challenges.py`.
4. **Secondary resilience test cases** for SSE terminal event guarantees and JSON serialization safety.
5. **Full regression matrix** confirming that all 39 tests in `tests/test_all_tabs_and_endpoints.py` pass cleanly with zero regressions.
6. **Step-by-step execution protocol** for `worker_m1_2` and gate reviewers.

---

## 2. Test Suite Audit & Coverage Gap Analysis

### 2.1 Current State of `tests/test_m1_empirical_challenges.py` (17 Tests)

The suite created by `challenger_m1_1` covers four areas:

| Test Class | Tests | Focus Areas | Limitations / Coverage Gaps |
|---|---|---|---|
| `TestM1ModelsInstalledEndpoint` | 5 | `/api/models/installed` schema, `is_multimodal_model()` matching, edge cases (casing, null), offline daemon fallback, `/api/models` parity | Tests classification strings only; **never calls `select_best_local_model()`**. |
| `TestM1MultimodalPayloadResolution` | 6 | `resolve_multimodal_images()` (PNG, JPG, WebP, GIF, BMP), missing files, empty inputs, non-media filtering, `Agent.run()` history injection | Verifies payload resolution; does not verify model routing decision. |
| `TestM1MissingFileLoopPrevention` | 4 | `read_file()` missing file `[Error]` prefix, file read, truncation notice, 3-attempt repetition intercept | Verifies tool failure and loop intercept; does not test non-serializable arguments. |
| `TestM1SSEStreamRobustness` | 3 | Normal completion with model attribution, worker exception error event with attribution, `MaxTurnsExceeded` done event with attribution | Verifies streaming; does not test premature worker death without terminal event. |
| **Total** | **17** | | **Major Gap: Model routing (`select_best_local_model`) completely unverified.** |

### 2.2 Current State of `tests/test_all_tabs_and_endpoints.py` (39 Tests)

The 4-tier integration test suite exercises end-to-end REST endpoints, WebSocket streams, and UI flows:

| Tier | Tests | Endpoints & Features Covered | Status & Risk Assessment |
|---|---|---|---|
| **Tier 1: Feature Coverage** | 21 | `/api/chat/history`, `/api/chat/sessions`, `/api/workspace/files`, `/api/workspace/file`, `/api/goals`, `/api/goals/create`, `/api/cluster/nodes`, `/api/cluster/nodes/add`, `/api/models/installed`, `/api/models`, `/api/models/search-hf`, `/api/models/trending-hf`, `/api/reflections`, `/api/system/stats`, `/api/system/gc`, `/api/media/status`, `/api/media/gallery`, `/api/upload`, `GET /`, `/api/chat/stream`, `/ws/cluster` | **Zero Risk**: All endpoints use standard contracts. M1 Iteration 2 fixes in `model_selector.py` do not break any of these interfaces. |
| **Tier 2: Boundary & Corner Cases** | 11 | Empty prompts, empty pull tags (400), nonexistent sessions, missing files (404), path traversal (403), 2MB file size cap, offline media status (clean error), offline cluster nodes (warning), max turns limit, invalid goal IDs (404), kill-all tasks | **Zero Risk**: Boundary checks verify defensive guards. |
| **Tier 3: Cross-Feature Combinations** | 3 | Upload -> chat stream -> history persistence; Goal decomposition -> followup -> kill -> delete; Upload -> file list -> preview -> delete -> 404 | **Zero Risk**: Multi-step workflows rely on `server.py` and `Agent.run`. |
| **Tier 4: Real-World Scenarios** | 4 | Developer session flow (models, cluster, stats, HF search, reflections, clear); Media Studio flow (status, gallery, txt2img, video gen); Cluster WebSocket telemetry stream; Telemetry & GC memory reclamation | **Zero Risk**: End-to-end developer workflows. |
| **Total** | **39** | | **All 39 tests must exit with code 0.** |

---

## 3. Mathematical Verification of the Model Routing Defect

### 3.1 Defect Mechanism in `src/ollama_agents/model_selector.py` (Lines 69–85)

```python
    for m in installed:
        m_lower = m.lower()
        score = 50  # default base score
        
        if "deepseek-r1" in m_lower:
            score += 40 if task_type == "reasoning" else 30
        elif any(c in m_lower for c in ["coder", "qwen2.5", "qwen3.5", "qwen3.8"]):
            score += 45 if task_type == "coding" else 20
        elif is_multimodal_model(m_lower):
            score += 50 if task_type == "vision" else 15
        elif "llama3" in m_lower:
            score += 35 if task_type == "general" else 25
```

### 3.2 Evaluation Matrix for `task_type == "vision"`

Given installed models: `["deepseek-r1:8b", "llama3.1:latest", "qwen2.5vl:latest"]`:

1. **`deepseek-r1:8b`**:
   - Matches `if "deepseek-r1" in m_lower`.
   - `score = 50 + 30 = 80`.
2. **`llama3.1:latest`**:
   - Matches `elif "llama3" in m_lower`.
   - `score = 50 + 25 = 75`.
3. **`qwen2.5vl:latest`**:
   - Matches `elif any(c in m_lower for c in ["coder", "qwen2.5", ...])` because `"qwen2.5"` is a substring of `"qwen2.5vl:latest"`.
   - `score = 50 + 20 = 70`.
   - `elif is_multimodal_model(m_lower)` is **skipped**.
4. **Outcome**:
   - `deepseek-r1:8b` (80) > `llama3.1:latest` (75) > `qwen2.5vl:latest` (70).
   - **Winner**: `deepseek-r1:8b` (text-only model). **FAILED**.

### 3.3 Evaluation Matrix for `gemma3:latest`

Given installed models: `["deepseek-r1:8b", "llama3.1:latest", "gemma3:latest"]`:
1. `deepseek-r1:8b` -> `score = 80`.
2. `llama3.1:latest` -> `score = 75`.
3. `gemma3:latest`:
   - Does not match `deepseek-r1`.
   - Does not match `coder` or `qwen`.
   - Matches `is_multimodal_model("gemma3:latest")` -> `True`.
   - `score = 50 + 50 = 100`.
4. **Outcome**:
   - `gemma3:latest` (100) > `deepseek-r1:8b` (80).
   - **Winner**: `gemma3:latest` (multimodal model). **PASSED**.

**Root Cause Summary**: The bug was an **asymmetric substring collision** affecting only models whose name contains `"qwen2.5"` while also being multimodal (specifically `qwen2.5vl` / `qwen2.5-vl`).

---

## 4. Authoritative Verification Test Cases for M1 Iteration 2

The following 10 exact test cases must be implemented in `tests/test_m1_empirical_challenges.py` under a new test class `TestM1ModelRoutingAndSelection`:

### Case 1: Vision Routing Selects `qwen2.5vl:latest` Over Text Models
- **Input Fixture**: `installed = ["deepseek-r1:8b", "llama3.1:latest", "qwen2.5vl:latest"]`
- **Call**: `select_best_local_model(task_type="vision")`
- **Expected Return**: `"qwen2.5vl:latest"`
- **Assertion**:
  ```python
  self.assertEqual(select_best_local_model(task_type="vision"), "qwen2.5vl:latest")
  ```
- **Rationale**: Direct verification of the Iteration 1 defect fix.

### Case 2: Vision Routing Selects `gemma3:latest` When Installed
- **Input Fixture**: `installed = ["deepseek-r1:8b", "llama3.1:latest", "gemma3:latest"]`
- **Call**: `select_best_local_model(task_type="vision")`
- **Expected Return**: `"gemma3:latest"`
- **Assertion**:
  ```python
  self.assertEqual(select_best_local_model(task_type="vision"), "gemma3:latest")
  ```
- **Rationale**: Verifies Gemma 3 vision prioritization as required by R1 and follow-up prompt.

### Case 3: Vision Routing With Diverse Multimodal Variants
- **Input Fixture**: Multiple individual test runs pairing `["deepseek-r1:8b", "llama3.1:latest"]` with each of:
  - `"gemma3:latest"`
  - `"gemma3:4b"`
  - `"gemma3:12b"`
  - `"qwen2.5vl:latest"`
  - `"qwen2.5-vl:7b"`
  - `"llava:7b"`
  - `"llava:13b"`
  - `"moondream:latest"`
  - `"llama3.2-vision:11b"`
- **Call**: `select_best_local_model(task_type="vision")`
- **Expected Return**: The respective multimodal model in each iteration.
- **Assertion**:
  ```python
  for mm in variants:
      with patch("ollama_agents.model_selector.get_installed_ollama_models", return_value=["deepseek-r1:8b", "llama3.1:latest", mm]):
          self.assertEqual(select_best_local_model(task_type="vision"), mm)
  ```

### Case 4: Vision Multimodal Tier Precedence
- **Input Fixture**: `installed = ["moondream:latest", "llava:7b", "qwen2.5vl:latest"]`
- **Call**: `select_best_local_model(task_type="vision")`
- **Expected Return**: `"qwen2.5vl:latest"` (Tier 1 model outscores Tier 2 `llava` and Tier 3 `moondream`).
- **Assertion**:
  ```python
  self.assertEqual(select_best_local_model(task_type="vision"), "qwen2.5vl:latest")
  ```

### Case 5: Text-Only Preferred Model Cannot Override Vision When Multimodal Model Exists
- **Input Fixture**: `installed = ["deepseek-r1:8b", "llama3.1:latest", "qwen2.5vl:latest"]`
- **Call**: `select_best_local_model(task_type="vision", preferred="deepseek-r1:8b")`
- **Expected Return**: `"qwen2.5vl:latest"`
- **Assertion**:
  ```python
  self.assertEqual(select_best_local_model(task_type="vision", preferred="deepseek-r1:8b"), "qwen2.5vl:latest")
  ```
- **Rationale**: Prevents text-only orchestrator defaults (`self.default_model = "deepseek-r1:8b"`) from hijacking vision workflows.

### Case 6: Multimodal Preferred Model Is Honored for Vision
- **Input Fixture**: `installed = ["gemma3:latest", "qwen2.5vl:latest"]`
- **Call**: `select_best_local_model(task_type="vision", preferred="gemma3:latest")`
- **Expected Return**: `"gemma3:latest"`
- **Assertion**:
  ```python
  self.assertEqual(select_best_local_model(task_type="vision", preferred="gemma3:latest"), "gemma3:latest")
  ```

### Case 7: Graceful Fallback When No Multimodal Model Is Installed
- **Input Fixture**: `installed = ["deepseek-r1:8b", "llama3.1:latest"]`
- **Call**: `select_best_local_model(task_type="vision")`
- **Expected Return**: Must return one of the installed models (`"deepseek-r1:8b"` or `"llama3.1:latest"`) without raising `IndexError`, `KeyError`, or `TypeError`.

### Case 8: Coding Task Routing Preserves Coder Model Priority
- **Input Fixture**: `installed = ["deepseek-r1:8b", "llama3.1:latest", "qwen2.5vl:latest", "qwen2.5-coder:7b"]`
- **Call**: `select_best_local_model(task_type="coding")`
- **Expected Return**: `"qwen2.5-coder:7b"`
- **Assertion**:
  ```python
  self.assertEqual(select_best_local_model(task_type="coding"), "qwen2.5-coder:7b")
  ```
- **Rationale**: Confirms that multimodal fixes do not degrade coding model routing.

### Case 9: Reasoning Task Routing Preserves DeepSeek-R1 Priority
- **Input Fixture**: `installed = ["deepseek-r1:8b", "llama3.1:latest", "qwen2.5vl:latest"]`
- **Call**: `select_best_local_model(task_type="reasoning")`
- **Expected Return**: `"deepseek-r1:8b"`
- **Assertion**:
  ```python
  self.assertEqual(select_best_local_model(task_type="reasoning"), "deepseek-r1:8b")
  ```

### Case 10: General Task Routing Preserves LLaMA 3 Priority
- **Input Fixture**: `installed = ["deepseek-r1:8b", "llama3.1:latest", "qwen2.5vl:latest"]`
- **Call**: `select_best_local_model(task_type="general")`
- **Expected Return**: `"llama3.1:latest"`
- **Assertion**:
  ```python
  self.assertEqual(select_best_local_model(task_type="general"), "llama3.1:latest")
  ```

---

## 5. Secondary Resilience Test Cases

In addition to model routing, the following two secondary defensive enhancements must be verified:

### 5.1 SSE Stream Terminal Event Guarantee (`TestM1SSEStreamRobustness`)
- **Test**: `test_04_stream_premature_worker_death_emits_terminal_fallback`
- **Scenario**: When worker thread abruptly terminates without enqueuing `done` or `error`, the generator must emit a terminal `error` event with `"Worker terminated unexpectedly"` and `"model": req.model`.

### 5.2 Tool Argument Serialization Safety (`TestM1MissingFileLoopPrevention`)
- **Test**: `test_05_repetition_guard_handles_non_serializable_args_safely`
- **Scenario**: When tool arguments contain non-JSON types (e.g., `Path` instances, sets, byte buffers), the repetition detector in `Agent.run()` (`call_sig`) must use `json.dumps(..., default=str)` without raising `TypeError`.

---

## 6. Complete Python Implementation for Test Suite Expansion

Below is the complete, drop-in Python code to be appended to `tests/test_m1_empirical_challenges.py`:

```python
# ──────────────────────────────────────────────────────────────────────────────
# TEST CLASS 5: MODEL ROUTING & MULTIMODAL SELECTION (Milestone M1 Iteration 2)
# ──────────────────────────────────────────────────────────────────────────────
from ollama_agents.model_selector import select_best_local_model


class TestM1ModelRoutingAndSelection(unittest.TestCase):
    """Rigorous empirical verification of task-based model routing and multimodal priority."""

    def test_01_vision_routing_prioritizes_qwen25vl_over_deepseek_and_llama(self):
        """qwen2.5vl:latest strictly beats deepseek-r1 and llama3.1 on vision tasks."""
        installed = ["deepseek-r1:8b", "llama3.1:latest", "qwen2.5vl:latest"]
        with patch("ollama_agents.model_selector.get_installed_ollama_models", return_value=installed):
            best = select_best_local_model(task_type="vision")
            self.assertEqual(
                best,
                "qwen2.5vl:latest",
                f"Expected 'qwen2.5vl:latest' for vision, but got '{best}'."
            )

    def test_02_vision_routing_selects_gemma3_when_installed(self):
        """gemma3:latest strictly beats deepseek-r1 and llama3.1 on vision tasks."""
        installed = ["deepseek-r1:8b", "llama3.1:latest", "gemma3:latest"]
        with patch("ollama_agents.model_selector.get_installed_ollama_models", return_value=installed):
            best = select_best_local_model(task_type="vision")
            self.assertEqual(
                best,
                "gemma3:latest",
                f"Expected 'gemma3:latest' for vision, but got '{best}'."
            )

    def test_03_vision_routing_all_multimodal_variants(self):
        """All supported vision models (gemma3, qwen2.5vl, llava, moondream, llama3.2-vision) beat text models."""
        variants = [
            "gemma3:latest",
            "gemma3:4b",
            "gemma3:12b",
            "qwen2.5vl:latest",
            "qwen2.5-vl:7b",
            "llava:7b",
            "llava:13b",
            "moondream:latest",
            "llama3.2-vision:11b",
        ]
        for mm in variants:
            installed = ["deepseek-r1:8b", "llama3.1:latest", mm]
            with patch("ollama_agents.model_selector.get_installed_ollama_models", return_value=installed):
                best = select_best_local_model(task_type="vision")
                self.assertEqual(
                    best, mm,
                    f"Multimodal model '{mm}' failed to win vision task over text models; got '{best}'."
                )

    def test_04_vision_routing_multimodal_tier_ranking(self):
        """Tier 1 vision models (qwen2.5vl, gemma3) rank higher than Tier 2/3 (llava, moondream)."""
        installed = ["moondream:latest", "llava:7b", "qwen2.5vl:latest"]
        with patch("ollama_agents.model_selector.get_installed_ollama_models", return_value=installed):
            best = select_best_local_model(task_type="vision")
            self.assertEqual(
                best, "qwen2.5vl:latest",
                f"Expected Tier 1 model 'qwen2.5vl:latest', got '{best}'."
            )

    def test_05_preferred_model_not_allowed_to_override_vision_if_text_only(self):
        """Text-only preferred model does NOT override installed multimodal model on vision tasks."""
        installed = ["deepseek-r1:8b", "llama3.1:latest", "qwen2.5vl:latest"]
        with patch("ollama_agents.model_selector.get_installed_ollama_models", return_value=installed):
            best = select_best_local_model(task_type="vision", preferred="deepseek-r1:8b")
            self.assertEqual(
                best, "qwen2.5vl:latest",
                f"Text-only preferred model hijacked vision routing! Got '{best}'."
            )

    def test_06_preferred_model_honored_for_vision_if_multimodal(self):
        """Multimodal preferred model is honored on vision tasks."""
        installed = ["gemma3:latest", "qwen2.5vl:latest"]
        with patch("ollama_agents.model_selector.get_installed_ollama_models", return_value=installed):
            best = select_best_local_model(task_type="vision", preferred="gemma3:latest")
            self.assertEqual(
                best, "gemma3:latest",
                f"Multimodal preferred model was not honored! Got '{best}'."
            )

    def test_07_vision_routing_fallback_when_no_multimodal_installed(self):
        """When no multimodal model is installed, vision routing safely returns an installed fallback."""
        installed = ["deepseek-r1:8b", "llama3.1:latest"]
        with patch("ollama_agents.model_selector.get_installed_ollama_models", return_value=installed):
            best = select_best_local_model(task_type="vision")
            self.assertIn(best, installed, f"Expected fallback from installed, got '{best}'.")

    def test_08_coding_routing_preserves_coder_model(self):
        """Coding tasks route to qwen2.5-coder over vision or reasoning models."""
        installed = ["deepseek-r1:8b", "llama3.1:latest", "qwen2.5vl:latest", "qwen2.5-coder:7b"]
        with patch("ollama_agents.model_selector.get_installed_ollama_models", return_value=installed):
            best = select_best_local_model(task_type="coding")
            self.assertEqual(
                best, "qwen2.5-coder:7b",
                f"Expected coder model 'qwen2.5-coder:7b' for coding, got '{best}'."
            )

    def test_09_reasoning_routing_preserves_deepseek_r1(self):
        """Reasoning tasks route to deepseek-r1 over coder and vision models."""
        installed = ["deepseek-r1:8b", "llama3.1:latest", "qwen2.5vl:latest", "qwen2.5-coder:7b"]
        with patch("ollama_agents.model_selector.get_installed_ollama_models", return_value=installed):
            best = select_best_local_model(task_type="reasoning")
            self.assertEqual(
                best, "deepseek-r1:8b",
                f"Expected reasoning model 'deepseek-r1:8b', got '{best}'."
            )

    def test_10_general_routing_preserves_llama3(self):
        """General tasks route to llama3 over reasoning or vision models."""
        installed = ["deepseek-r1:8b", "llama3.1:latest", "qwen2.5vl:latest"]
        with patch("ollama_agents.model_selector.get_installed_ollama_models", return_value=installed):
            best = select_best_local_model(task_type="general")
            self.assertEqual(
                best, "llama3.1:latest",
                f"Expected general model 'llama3.1:latest', got '{best}'."
            )
```

### 6.2 Updated Test Runner Harness in `tests/test_m1_empirical_challenges.py`

```python
def run_empirical_suite() -> int:
    """Run all empirical challenge tests with detailed output."""
    print("=" * 80)
    print(" MILESTONE M1 EMPIRICAL CHALLENGE SUITE (ITERATION 2)")
    print(" Verifying Dynamic Model Availability, Multimodal Routing & Stream Resilience")
    print("=" * 80)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestM1ModelsInstalledEndpoint))
    suite.addTests(loader.loadTestsFromTestCase(TestM1MultimodalPayloadResolution))
    suite.addTests(loader.loadTestsFromTestCase(TestM1MissingFileLoopPrevention))
    suite.addTests(loader.loadTestsFromTestCase(TestM1SSEStreamRobustness))
    suite.addTests(loader.loadTestsFromTestCase(TestM1ModelRoutingAndSelection))  # Iteration 2 Expansion

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("=" * 80)
    if result.wasSuccessful():
        print(f"ALL EMPIRICAL CHALLENGE TESTS PASSED ({result.testsRun} tests)")
        return 0
    else:
        print(f"EMPIRICAL CHALLENGE TESTS FAILED: {len(result.failures)} failures, {len(result.errors)} errors")
        return 1
```

---

## 7. Complete Regression Inventory: `tests/test_all_tabs_and_endpoints.py` (39 Tests)

| # | Tier | Test Method | Functionality Verified | Expected Code / Behavior |
|---|---|---|---|---|
| 1 | Tier 1 | `test_01_chat_history_endpoint` | `GET /api/chat/history` | HTTP 200, JSON: `status="success"`, `messages: list` |
| 2 | Tier 1 | `test_02_chat_sessions_endpoint` | `GET /api/chat/sessions` | HTTP 200, JSON: `status="success"`, `sessions: list` |
| 3 | Tier 1 | `test_03_workspace_files_endpoint` | `GET /api/workspace/files` | HTTP 200, JSON: `workspace_path`, `files: list` |
| 4 | Tier 1 | `test_04_workspace_file_preview_endpoint` | `GET /api/workspace/file?path=...` | HTTP 200, JSON: `content`, `is_binary=False` |
| 5 | Tier 1 | `test_05_goals_list_endpoint` | `GET /api/goals` | HTTP 200, JSON array of active/past goals |
| 6 | Tier 1 | `test_06_goals_create_endpoint` | `POST /api/goals/create` | HTTP 200, JSON: `goal.id`, subtasks list |
| 7 | Tier 1 | `test_07_cluster_nodes_endpoint` | `GET /api/cluster/nodes` | HTTP 200, JSON: `total_nodes`, `active_nodes`, `nodes` |
| 8 | Tier 1 | `test_08_cluster_add_node_endpoint` | `POST /api/cluster/nodes/add` | HTTP 200, JSON: `status in ["success", "warning"]` |
| 9 | Tier 1 | `test_09_models_installed_endpoint` | `GET /api/models/installed` | HTTP 200, JSON: `status="success"`, `models: list` |
| 10 | Tier 1 | `test_10_models_list_endpoint` | `GET /api/models` | HTTP 200, JSON: `models: list` |
| 11 | Tier 1 | `test_11_models_search_hf_endpoint` | `GET /api/models/search-hf` | HTTP 200, JSON: `query`, `results: list` |
| 12 | Tier 1 | `test_12_models_trending_hf_endpoint` | `GET /api/models/trending-hf` | HTTP 200, JSON: `results: list` |
| 13 | Tier 1 | `test_13_reflections_endpoint` | `GET /api/reflections` | HTTP 200, JSON array of episodic reflections |
| 14 | Tier 1 | `test_14_system_stats_endpoint` | `GET /api/system/stats` | HTTP 200, JSON: `cpu_used_pct`, `ram_used_pct` |
| 15 | Tier 1 | `test_15_system_gc_endpoint` | `POST /api/system/gc` | HTTP 200, JSON: `collected_objects: int` |
| 16 | Tier 1 | `test_16_media_status_endpoint` | `GET /api/media/status` | HTTP 200, JSON: `forge.online`, `comfy.online` |
| 17 | Tier 1 | `test_17_media_gallery_endpoint` | `GET /api/media/gallery` | HTTP 200, JSON: `images: list`, `videos: list` |
| 18 | Tier 1 | `test_18_upload_endpoint` | `POST /api/upload` | HTTP 200, JSON: `filepath` starting with `uploads/` |
| 19 | Tier 1 | `test_19_dashboard_root_html` | `GET /` | HTTP 200, Content-Type: `text/html` |
| 20 | Tier 1 | `test_20_sse_chat_stream_protocol` | `POST /api/chat/stream` | HTTP 200, SSE data lines with terminal event |
| 21 | Tier 1 | `test_21_cluster_websocket_handshake` | `WebSocket /ws/cluster` | Handshake accepted, frame: `type="cluster_status"` |
| 22 | Tier 2 | `test_01_empty_prompt_goal_creation` | `POST /api/goals/create` (empty) | HTTP 200, handles empty string gracefully |
| 23 | Tier 2 | `test_02_empty_model_tag_pull_rejection` | `POST /api/models/pull` ("   ") | HTTP 400, detail rejects empty tag |
| 24 | Tier 2 | `test_03_nonexistent_session_queries` | `GET/DELETE /api/chat/sessions/x` | HTTP 200, empty list / success status |
| 25 | Tier 2 | `test_04_nonexistent_workspace_file_not_found` | `GET /api/workspace/file?path=ghost` | HTTP 404, detail: "File not found" |
| 26 | Tier 2 | `test_05_workspace_path_traversal_forbidden` | `GET/DELETE ../../etc/passwd` | HTTP 403, detail: "Access denied" |
| 27 | Tier 2 | `test_06_workspace_large_file_preview_protection` | File > 2MB preview | HTTP 200, `is_binary=True`, preview size cap message |
| 28 | Tier 2 | `test_07_offline_media_status_clean_diagnostic` | Closed ports (59998/59999) | HTTP 200, `online=False`, clean error diagnostic |
| 29 | Tier 2 | `test_08_offline_cluster_node_warning` | Unreachable node IP | HTTP 200, `status="warning"`, `is_active=False` |
| 30 | Tier 2 | `test_09_max_turns_limit_stream_resilience` | `MaxTurnsExceeded` exception | HTTP 200, SSE `done` event with turn limit notice |
| 31 | Tier 2 | `test_10_goal_run_nonexistent_id_handled` | `POST /api/goals/ghost/run` | HTTP 404, handles invalid goal cleanly |
| 32 | Tier 2 | `test_11_kill_all_tasks_when_idle` | `POST /api/tasks/kill-all` | HTTP 200, `status="success"` when no tasks run |
| 33 | Tier 3 | `test_01_chat_session_upload_stream_and_history_flow` | End-to-end multimodal chat flow | Upload -> Stream with attachment -> History check -> Delete |
| 34 | Tier 3 | `test_02_goal_lifecycle_decomposition_followup_and_deletion` | End-to-end goal lifecycle | Decompose -> Followup task -> Kill -> Delete |
| 35 | Tier 3 | `test_03_workspace_file_upload_preview_and_delete_lifecycle` | End-to-end file lifecycle | Upload markdown -> List -> Preview -> Delete -> 404 |
| 36 | Tier 4 | `test_01_developer_interactive_session_flow` | Full developer journey | Models -> Cluster -> Stats -> HF -> Reflections -> Clear |
| 37 | Tier 4 | `test_02_media_studio_diagnostics_and_generation_flow` | Creative studio pipeline | Status -> Gallery -> txt2img (200/503) -> video (200/503) |
| 38 | Tier 4 | `test_03_cluster_websocket_telemetry_monitoring` | Live telemetry stream | WebSocket receive `cluster_status` -> clean close |
| 39 | Tier 4 | `test_04_system_telemetry_and_memory_reclamation` | Telemetry & GC trigger | Pre-stats -> `POST /api/system/gc` -> Verify freed objects |

---

## 8. Verification Protocol & Execution Instructions

### Phase 1: Code Modifications by `worker_m1_2`

1. **Implement Task-First Scoring** in `src/ollama_agents/model_selector.py`:
   - Replace lines 56–89 with the task-first decoupled architecture from `explorer_m1_iter2_1`'s `remediation_strategy.md`.
2. **Implement SSE Stream Terminal Fallback** in `src/ollama_agents/server.py`:
   - Ensure `_stream_closed` yields fallback terminal error event if none was sent.
3. **Implement Serialization Guard** in `src/ollama_agents/agent.py`:
   - Update `call_sig = f"{fn_name}:{json.dumps(fn_args, sort_keys=True, default=str)}"` at line 663.
4. **Append `TestM1ModelRoutingAndSelection`** to `tests/test_m1_empirical_challenges.py`:
   - Add the 10 test methods specified in Section 6.
   - Update `run_empirical_suite()` to register the new test class.

### Phase 2: Execution & Validation by `worker_m1_2`

Run the following test commands:

```powershell
# 1. Run Empirical Challenge Suite (Expected: 27/27 tests pass)
python tests/test_m1_empirical_challenges.py

# 2. Run Comprehensive Integration Test Suite (Expected: 39/39 tests pass, Exit Code: 0)
python tests/test_all_tabs_and_endpoints.py
```

### Phase 3: Quality Gate Verification by `challenger_m1_3` and `reviewer_m1_3`

1. Verify that `python tests/test_m1_empirical_challenges.py` logs:
   ```
   ALL EMPIRICAL CHALLENGE TESTS PASSED (27 tests)
   ```
2. Verify that `python tests/test_all_tabs_and_endpoints.py` logs:
   ```
   [SUCCESS] ALL INTEGRATION TESTS PASSED (EXIT CODE: 0)
   ```
3. Run Python REPL verification for explicit models:
   ```python
   from unittest.mock import patch
   from ollama_agents.model_selector import select_best_local_model

   # Check 1: qwen2.5vl vs deepseek-r1 and llama3.1
   with patch("ollama_agents.model_selector.get_installed_ollama_models") as m:
       m.return_value = ["deepseek-r1:8b", "llama3.1:latest", "qwen2.5vl:latest"]
       assert select_best_local_model("vision") == "qwen2.5vl:latest"

   # Check 2: gemma3 vs deepseek-r1 and llama3.1
   with patch("ollama_agents.model_selector.get_installed_ollama_models") as m:
       m.return_value = ["deepseek-r1:8b", "llama3.1:latest", "gemma3:latest"]
       assert select_best_local_model("vision") == "gemma3:latest"
   ```
