# Handoff Report: Milestone M1 Iteration 2 Model Routing & Multimodal Strategy

**Agent**: `explorer_m1_iter2_1`  
**Role**: Teamwork Explorer (Read-Only Investigation & Strategy Formulation)  
**Target Milestone**: M1 Iteration 2  
**Date**: 2026-09-26  
**Type**: Hard Handoff  

---

## 1. Observation

Direct observations from codebase inspection, specification review, and failure report audits:

1. **Failure Reports**:
   - `e:\Learning\Python\agent_test\.agents\challenger_m1_2\handoff.md` lines 35–58:
     - Flagged model routing priority defect in `select_best_local_model` where `"qwen2.5"` is checked before `is_multimodal_model` in an `elif` chain.
     - For `qwen2.5vl:latest` and `task_type == "vision"`, score is `50 + 20 = 70`.
     - For `deepseek-r1:8b`, score is `50 + 30 = 80`.
     - Result: `deepseek-r1:8b` beats `qwen2.5vl:latest` for vision tasks.
     - Verdict: `REQUEST_CHANGES`.
   - `e:\Learning\Python\agent_test\.agents\reviewer_m1_2\handoff.md` lines 33–55:
     - Confirmed `qwen2.5vl:latest` is shadowed by the coding condition.
     - Also identified two secondary edge cases:
       - SSE stream generator in `server.py` lines 644–651 immediately returns on `_stream_closed` without checking if a terminal `done` or `error` event was emitted.
       - Anti-hallucination tool call signature serialization in `agent.py` line 663 lacks `default=str`.
     - Verdict: `REQUEST_CHANGES`.
   - `e:\Learning\Python\agent_test\.agents\teamwork_preview_orchestrator_2\GATE_STATUS.md`:
     - Milestone M1 Iteration 1 Gate Result: **FAIL**.

2. **Existing Implementation in `src/ollama_agents/model_selector.py`**:
   - Lines 46–54:
     ```python
     MULTIMODAL_KEYWORDS = ["vision", "vl", "gemma3", "llava", "moondream"]

     def is_multimodal_model(model_name: str) -> bool:
         """Return True if model_name supports multimodal vision (image/video)."""
         if not model_name:
             return False
         m = model_name.lower()
         return any(k in m for k in MULTIMODAL_KEYWORDS)
     ```
     `is_multimodal_model("qwen2.5vl:latest")` returns `True` (matches `"vl"`).
   - Lines 56–88:
     ```python
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
             score = 50  # default base score
             
             if "deepseek-r1" in m_lower:
                 score += 40 if task_type == "reasoning" else 30
             elif any(c in m_lower for c in ["coder", "qwen2.5", "qwen3.5", "qwen3.8"]):
                 score += 45 if task_type == "coding" else 20
             elif is_multimodal_model(m_lower):
                 score += 50 if task_type == "vision" else 15
             elif "llama3" in m_lower:
                 score += 35 if task_type == "general" else 25

             if score > highest_score:
                 highest_score = score
                 best_model = m

         logger.info("Selected best local model '%s' for task_type='%s'", best_model, task_type)
         return best_model
     ```

3. **Orchestrator Caller Pattern (`src/ollama_agents/orchestrator.py` lines 167–168 & 232–233)**:
   ```python
   task_type = self.classify_task_type(task_desc)
   best_model = select_best_local_model(task_type=task_type, preferred=self.default_model)
   ```
   When `self.default_model` is `"deepseek-r1:8b"`, lines 62–63 of `model_selector.py` return `"deepseek-r1:8b"` immediately on vision tasks without evaluating modality.

4. **Missing Test Coverage (`tests/test_m1_empirical_challenges.py`)**:
   - `test_m1_empirical_challenges.py` tested `is_multimodal_model`, `/api/models/installed`, file loops, and SSE streams, but contained **zero** tests for `select_best_local_model()`.

---

## 2. Logic Chain

1. **Requirement Analysis**:
   - `ORIGINAL_REQUEST.md` R1: Ensure every tab and subagent tool works reliably with multimodal models like Gemma 3 and Qwen2.5-VL.
   - `PROJECT.md` Feature 2: Classify multimodal models (`vl`, `vision`, `gemma3`, `llava`, `moondream`).
   - `PROJECT.md` Feature 3: Ingest multimodal payloads and route vision tasks to multimodal models.

2. **Causal Chain of the Routing Flaw**:
   - In `model_selector.py`, models are checked through an `if/elif` chain structured by model name keywords rather than required capability.
   - For `qwen2.5vl:latest`, `"qwen2.5"` matches at line 76 before `is_multimodal_model(m_lower)` at line 78.
   - Under `task_type == "vision"`, line 77 awards `+20` (since `task_type != "coding"`), producing a total score of 70.
   - Line 78 (`is_multimodal_model`, which awards `+50`) is completely bypassed.
   - For `deepseek-r1:8b`, line 74 matches and awards `+30`, producing a total score of 80.
   - For `llama3.1:latest`, line 80 matches and awards `+25`, producing a total score of 75.
   - Because 80 > 70 and 75 > 70, `select_best_local_model("vision")` selects text-only models over `qwen2.5vl:latest`.
   - Furthermore, if `preferred` is text-only (e.g. `deepseek-r1:8b`), lines 62–63 unconditionally return it, bypassing modality scoring entirely.

3. **Remediation Invariance**:
   - The fundamental fix requires a **Task-First Decoupled Scoring Architecture**:
     Branching on `task_type` first ensures that for `task_type == "vision"`, coder and reasoning keyword branches are never executed.
   - Any model satisfying `is_multimodal_model(m_lower)` receives a score >= 105 (base 100 + tier bonuses: +15 for `qwen2.5vl`/`gemma3`/`llama3.2-vision`, +10 for `llava`, +5 for `moondream`).
   - Any model failing `is_multimodal_model(m_lower)` receives a score of 10.
   - The 95-point minimum margin guarantees that text-only models can never win vision routing under any permutation of installed models.
   - `preferred` model handling must verify `is_multimodal_model(preferred)` for vision tasks before taking precedence.

---

## 3. Caveats

- **Ollama CLI Availability**: The scoring algorithm operates on model names returned by `get_installed_ollama_models()`. If local Ollama is offline, the fallback list `["deepseek-r1:8b", "llama3.1:latest"]` is used.
- **Model Quantization Tags**: Model strings can contain variable tags (e.g., `:latest`, `:8b`, `:q4_k_m`, `huihui_ai/...`). Substring parsing with lowercase normalization reliably matches all standard tagging schemes.
- **No Source Modifications Made**: As an Explorer agent, all analysis and remediation proposals are read-only and documented in `.agents/explorer_m1_iter2_1/`. The worker subagent must apply the code edits.

---

## 4. Conclusion

The model routing defect in Milestone M1 Iteration 1 is fully understood and diagnosed. A comprehensive, foolproof remediation strategy has been documented in `remediation_strategy.md`.

### Core Deliverables:
1. `remediation_strategy.md`: Full architectural blueprint, mathematical traces, and exact drop-in code implementations.
2. Production drop-in replacement for `select_best_local_model()` in `src/ollama_agents/model_selector.py`.
3. Secondary hardening fixes for `server.py` (SSE `_stream_closed` fallback) and `agent.py` (`json.dumps(..., default=str)`).
4. Automated verification suite `TestM1ModelSelectorRouting` to be added to `tests/test_m1_empirical_challenges.py`.

---

## 5. Verification Method

Once the worker agent applies the remediation:

1. **Direct Unit Test Execution**:
   Run the following Python assertion script:
   ```bash
   python -c "
   from unittest.mock import patch
   from ollama_agents.model_selector import select_best_local_model

   # Scenario 1: qwen2.5vl vs deepseek-r1 vs llama3.1 on vision
   with patch('ollama_agents.model_selector.get_installed_ollama_models', return_value=['deepseek-r1:8b', 'llama3.1:latest', 'qwen2.5vl:latest']):
       best = select_best_local_model(task_type='vision')
       assert best == 'qwen2.5vl:latest', f'Expected qwen2.5vl:latest, got {best}'

   # Scenario 2: Preferred text model on vision
   with patch('ollama_agents.model_selector.get_installed_ollama_models', return_value=['deepseek-r1:8b', 'qwen2.5vl:latest']):
       best = select_best_local_model(task_type='vision', preferred='deepseek-r1:8b')
       assert best == 'qwen2.5vl:latest', f'Expected qwen2.5vl:latest override, got {best}'

   # Scenario 3: Coding model routing
   with patch('ollama_agents.model_selector.get_installed_ollama_models', return_value=['deepseek-r1:8b', 'qwen2.5-coder:7b', 'llama3.1:latest']):
       best = select_best_local_model(task_type='coding')
       assert best == 'qwen2.5-coder:7b', f'Expected qwen2.5-coder:7b, got {best}'

   # Scenario 4: Reasoning model routing
   with patch('ollama_agents.model_selector.get_installed_ollama_models', return_value=['llama3.1:latest', 'deepseek-r1:8b']):
       best = select_best_local_model(task_type='reasoning')
       assert best == 'deepseek-r1:8b', f'Expected deepseek-r1:8b, got {best}'

   print('ALL UNIT ASSERTIONS PASSED SUCCESSFULLY!')
   "
   ```

2. **Empirical Challenge Test Suite**:
   Run:
   ```bash
   python tests/test_m1_empirical_challenges.py
   ```
   Must exit with status code 0 and report all test cases passing.
