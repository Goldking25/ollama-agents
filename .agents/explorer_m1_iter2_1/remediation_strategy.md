# Comprehensive Remediation Strategy: Model Routing Priority & Multimodal Selection

**Document**: `remediation_strategy.md`  
**Author**: `explorer_m1_iter2_1` (Teamwork Explorer)  
**Target Milestone**: Milestone M1 (Iteration 2)  
**Date**: 2026-09-26  
**Status**: APPROVED_STRATEGY  

---

## 1. Executive Summary

During Milestone M1 Iteration 1, the gate review failed due to a critical defect in `select_best_local_model()` located in `src/ollama_agents/model_selector.py` (flagged by both `challenger_m1_2` and `reviewer_m1_2`). 

When `select_best_local_model(task_type="vision")` evaluated installed models in an environment containing `["qwen2.5vl:latest", "deepseek-r1:8b", "llama3.1:latest"]`, it returned `"deepseek-r1:8b"` (or `"llama3.1:latest"`), routing multimodal vision workloads to a text-only reasoning model that cannot process image payloads.

This document provides:
1. Root cause verification with exact line-by-line mathematical score traces.
2. Comprehensive evaluation of all four task types (`vision`, `coding`, `reasoning`, `general`).
3. Analysis of the secondary `preferred` model bypass vulnerability.
4. A foolproof **Task-First Decoupled Scoring Architecture** that guarantees any installed multimodal model (`qwen2.5vl`, `gemma3`, `llava`, `moondream`) defeats all text-only models on vision tasks by an unbridgeable margin.
5. Complete drop-in code implementations for `model_selector.py`, secondary fixes for `server.py` and `agent.py`, and comprehensive automated test suites.

---

## 2. Diagnostic Analysis of Iteration 1 Failure

### 2.1 The Vulnerable Implementation (`model_selector.py` lines 56–88)

```python
def select_best_local_model(task_type: str = "reasoning", preferred: Optional[str] = None) -> str:
    """Select the highest-scoring installed local model for a given task type."""
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

### 2.2 Why `qwen2.5vl:latest` Failed: Step-by-Step Execution Trace

Consider `installed = ["qwen2.5vl:latest", "deepseek-r1:8b", "llama3.1:latest"]` and `task_type = "vision"`:

#### Model 1: `m = "qwen2.5vl:latest"`
- Base score: `score = 50`.
- Branch 1: `if "deepseek-r1" in m_lower:` -> `False`.
- Branch 2: `elif any(c in m_lower for c in ["coder", "qwen2.5", "qwen3.5", "qwen3.8"]):`
  - `"qwen2.5"` is checked. Because `"qwen2.5"` is a substring of `"qwen2.5vl:latest"`, the condition evaluates to **`True`**!
  - `score += 45 if task_type == "coding" else 20`.
  - Since `task_type == "vision"` (not `"coding"`), `score += 20`.
  - **Total score for `qwen2.5vl:latest` = 50 + 20 = 70.**
  - **Crucial consequence**: Branch 3 (`elif is_multimodal_model(m_lower):`) is **never reached or evaluated** due to Python's sequential `if/elif` short-circuiting!

#### Model 2: `m = "deepseek-r1:8b"`
- Base score: `score = 50`.
- Branch 1: `if "deepseek-r1" in m_lower:` -> **`True`**.
- `score += 40 if task_type == "reasoning" else 30`.
- Since `task_type == "vision"` (not `"reasoning"`), `score += 30`.
- **Total score for `deepseek-r1:8b` = 50 + 30 = 80.**

#### Model 3: `m = "llama3.1:latest"`
- Base score: `score = 50`.
- Branch 1: `False`.
- Branch 2: `False`.
- Branch 3: `is_multimodal_model("llama3.1:latest")` -> `False`.
- Branch 4: `elif "llama3" in m_lower:` -> **`True`**.
- `score += 35 if task_type == "general" else 25`.
- Since `task_type == "vision"` (not `"general"`), `score += 25`.
- **Total score for `llama3.1:latest` = 50 + 25 = 75.**

#### Selection Outcome for `task_type == "vision"`:
| Model | Branch Entered | Scoring Logic | Total Score | Result |
|---|---|---|---|---|
| `deepseek-r1:8b` | Branch 1 (`deepseek-r1`) | 50 + 30 | **80** | **WINNER (Selected)** |
| `llama3.1:latest` | Branch 4 (`llama3`) | 50 + 25 | **75** | Runner-up |
| `qwen2.5vl:latest` | Branch 2 (`qwen2.5`) | 50 + 20 | **70** | **LAST PLACE (Eliminated)** |

`select_best_local_model` returns `"deepseek-r1:8b"`. A pure text-only reasoning model is selected for a vision workflow!

---

## 3. Evaluation of All Task Types Under Current Code

| Model | `task_type == "vision"` | `task_type == "coding"` | `task_type == "reasoning"` | `task_type == "general"` |
|---|---|---|---|---|
| `qwen2.5vl:latest` | **70 (Defect: trapped in coder)** | 95 | 70 | 70 |
| `gemma3:latest` | **100 (multimodal branch)** | 65 | 65 | 65 |
| `llava:7b` | **100 (multimodal branch)** | 65 | 65 | 65 |
| `moondream:latest` | **100 (multimodal branch)** | 65 | 65 | 65 |
| `deepseek-r1:8b` | **80** | 80 | **90 (Winner)** | 80 |
| `qwen2.5-coder:7b` | 70 | **95 (Winner)** | 70 | 70 |
| `llama3.1:latest` | 75 | 75 | 75 | **85 (Winner)** |
| `huihui_ai/qwen3.5-abliterated:9b` | 70 | 95 | 70 | 70 |

### Key Observations:
1. **Asymmetry in Vision Handling**: Models like `gemma3`, `llava`, and `moondream` happened to receive 100 because they did not match "deepseek-r1" or "qwen". But `qwen2.5vl`—one of the primary target multimodal models in R1—was crippled.
2. **Text Models Over-Rewarded on Incompatible Modalities**: Non-vision models received 75–80 points on vision tasks simply for having well-known brand names ("deepseek", "llama"), despite possessing **zero** ability to ingest image bytes.
3. **The `preferred` Parameter Vulnerability (Lines 62–63)**:
   ```python
   if preferred and preferred in installed:
       return preferred
   ```
   In `src/ollama_agents/orchestrator.py` lines 168 and 233:
   `best_model = select_best_local_model(task_type=task_type, preferred=self.default_model)`
   If `self.default_model` is `"deepseek-r1:8b"`, `select_best_local_model` unconditionally returns `"deepseek-r1:8b"` even when `task_type == "vision"`! The entire model scoring logic was completely bypassed.

---

## 4. Foolproof Remediation Architecture

To make model routing completely robust, deterministic, and immune to string collisions or shadowing, we implement four architectural principles:

### Principle 1: Task-First Decoupled Scoring (Eliminate Branch Shadowing)
Instead of matching model family keywords first in an `if/elif` chain and querying `task_type` inside, the scoring function must switch on `task_type` **first**:
```python
if task_type == "vision":
    # Vision-specific evaluation
elif task_type == "coding":
    # Coding-specific evaluation
elif task_type == "reasoning":
    # Reasoning-specific evaluation
else:
    # General / fallback evaluation
```
When `task_type == "vision"`, coder and reasoning branches are **never executed**. No model can be trapped in a coding branch during a vision query.

### Principle 2: Absolute Modality Enforcement
For `task_type == "vision"`:
- Any model where `is_multimodal_model(m)` is `True` receives a base score of **100+**.
- Any model where `is_multimodal_model(m)` is `False` receives a base score of **10** (with zero bonuses).
- The minimum multimodal score (105) is **95 points higher** than the maximum text-only score (10). A text-only model can **never** beat a multimodal model on a vision task under any condition.

### Principle 3: Tiered Multimodal Scoring
When multiple multimodal models are installed, we rank them according to capability tier:
- **Tier 1 (State-of-the-Art Vision-Language Models)**: `qwen2.5vl`, `qwen2.5-vl`, `gemma3`, `llama3.2-vision` -> **Score: 115** (100 base + 15 bonus).
- **Tier 2 (Standard Multimodal Models)**: `llava`, `bakllava` -> **Score: 110** (100 base + 10 bonus).
- **Tier 3 (Compact / Lightweight Vision Models)**: `moondream` -> **Score: 105** (100 base + 5 bonus).
- **Non-multimodal models**: **Score: 10**.

### Principle 4: Preferred-Model Modality Awareness
If `preferred` is specified:
- If `task_type == "vision"`: `preferred` is only honored if `is_multimodal_model(preferred)` is `True`, OR if no installed model is multimodal (graceful fallback).
- If `task_type != "vision"`: `preferred` is honored directly if present in `installed`.

---

## 5. Complete Code Implementations

### 5.1 Primary Fix: `src/ollama_agents/model_selector.py`

Replace `select_best_local_model()` in `src/ollama_agents/model_selector.py` (lines 56–89) with the following production implementation:

```python
def select_best_local_model(task_type: str = "reasoning", preferred: Optional[str] = None) -> str:
    """Select the highest-scoring installed local model for a given task type.
    
    Guarantees:
    - For task_type == 'vision': Any multimodal model (qwen2.5vl, gemma3, llava, moondream)
      strictly outscores all text-only models (e.g. deepseek-r1, llama3).
    - If preferred is specified for a vision task, it is only honored if it is multimodal
      or if no multimodal model is installed.
    """
    installed = get_installed_ollama_models()
    if not installed:
        return preferred or "deepseek-r1:8b"

    # Modality-aware preference handling
    if preferred and preferred in installed:
        if task_type == "vision":
            has_multimodal = any(is_multimodal_model(m) for m in installed)
            if is_multimodal_model(preferred) or not has_multimodal:
                return preferred
        else:
            return preferred

    best_model = installed[0]
    highest_score = -1

    for m in installed:
        if not m:
            continue
        m_lower = m.lower()

        # Task-First Scoring Architecture
        if task_type == "vision":
            if is_multimodal_model(m_lower):
                score = 100
                if any(k in m_lower for k in ["qwen2.5vl", "qwen2.5-vl", "gemma3", "llama3.2-vision"]):
                    score += 15
                elif "llava" in m_lower:
                    score += 10
                elif "moondream" in m_lower:
                    score += 5
            else:
                score = 10  # Text-only models strictly disqualified from vision priority

        elif task_type == "coding":
            if any(c in m_lower for c in ["coder", "deepseek-coder", "qwen2.5-coder", "starcoder"]):
                score = 110
            elif any(c in m_lower for c in ["qwen2.5", "qwen3.5", "qwen3.8"]):
                score = 95
            elif "deepseek-r1" in m_lower:
                score = 90
            elif "llama3" in m_lower:
                score = 80
            elif is_multimodal_model(m_lower):
                score = 70
            else:
                score = 50

        elif task_type == "reasoning":
            if any(r in m_lower for r in ["deepseek-r1", "qwq", "-r1"]):
                score = 110
            elif any(c in m_lower for c in ["qwen2.5", "qwen3.5", "qwen3.8"]):
                score = 95
            elif "llama3" in m_lower:
                score = 85
            elif is_multimodal_model(m_lower):
                score = 75
            else:
                score = 50

        else:  # "general" or fallback
            if "llama3" in m_lower:
                score = 95
            elif any(c in m_lower for c in ["qwen2.5", "qwen3.5", "qwen3.8"]):
                score = 90
            elif "deepseek-r1" in m_lower:
                score = 85
            elif is_multimodal_model(m_lower):
                score = 80
            else:
                score = 50

        if score > highest_score:
            highest_score = score
            best_model = m

    logger.info("Selected best local model '%s' (score=%d) for task_type='%s'", best_model, highest_score, task_type)
    return best_model
```

### 5.2 Secondary Fix 1: `src/ollama_agents/server.py` SSE Stream Termination

In `src/ollama_agents/server.py` lines 639–656, ensure `_stream_closed` emits a fallback error event if no terminal event (`done` or `error`) was previously yielded:

```python
    async def event_generator():
        terminal_event_sent = False
        while True:
            try:
                while not event_queue.empty():
                    item = event_queue.get_nowait()
                    if item.get("type") == "_stream_closed":
                        if not terminal_event_sent:
                            yield f"data: {json.dumps({'type': 'error', 'error': 'Worker terminated unexpectedly', 'message': 'Worker terminated unexpectedly', 'model': req.model})}\n\n"
                        return
                    yield f"data: {json.dumps(item)}\n\n"
                    if item.get("type") in ("done", "error"):
                        terminal_event_sent = True
                        return
                if not worker_thread.is_alive() and event_queue.empty():
                    if not terminal_event_sent:
                        yield f"data: {json.dumps({'type': 'error', 'error': 'Worker terminated unexpectedly', 'message': 'Worker terminated unexpectedly', 'model': req.model})}\n\n"
                    return
                await asyncio.sleep(0.08)
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'error': str(e), 'message': str(e), 'model': req.model})}\n\n"
                return
```

### 5.3 Secondary Fix 2: `src/ollama_agents/agent.py` Serialization Guard

In `src/ollama_agents/agent.py` line 663, add `default=str` to prevent `TypeError` when tool arguments contain arbitrary non-JSON types:

```python
call_sig = f"{fn_name}:{json.dumps(fn_args, sort_keys=True, default=str)}"
```

---

## 6. Verification Suite Specification

Add `TestM1ModelSelectorRouting` to `tests/test_m1_empirical_challenges.py`:

```python
class TestM1ModelSelectorRouting(unittest.TestCase):
    """Rigorous verification of task-based model routing and multimodal priority."""

    def test_01_vision_routing_prioritizes_qwen25vl_over_deepseek_and_llama(self):
        """qwen2.5vl:latest beats deepseek-r1 and llama3.1 on vision tasks."""
        installed = ["deepseek-r1:8b", "llama3.1:latest", "qwen2.5vl:latest"]
        with patch("ollama_agents.model_selector.get_installed_ollama_models", return_value=installed):
            best = select_best_local_model(task_type="vision")
            self.assertEqual(best, "qwen2.5vl:latest")

    def test_02_vision_routing_all_multimodal_variants(self):
        """Gemma 3, LLaVA, and Moondream all beat deepseek-r1 on vision tasks."""
        variants = ["gemma3:latest", "gemma3:4b", "llava:7b", "moondream:latest", "llama3.2-vision:11b"]
        for mm in variants:
            installed = ["deepseek-r1:8b", "llama3.1:latest", mm]
            with patch("ollama_agents.model_selector.get_installed_ollama_models", return_value=installed):
                best = select_best_local_model(task_type="vision")
                self.assertEqual(best, mm, f"Failed for multimodal model: {mm}")

    def test_03_vision_routing_multimodal_tier_ranking(self):
        """qwen2.5vl and gemma3 rank above moondream and llava."""
        installed = ["moondream:latest", "llava:7b", "qwen2.5vl:latest"]
        with patch("ollama_agents.model_selector.get_installed_ollama_models", return_value=installed):
            best = select_best_local_model(task_type="vision")
            self.assertEqual(best, "qwen2.5vl:latest")

    def test_04_preferred_model_not_allowed_to_override_vision_if_text_only(self):
        """Text-only preferred model does NOT override installed multimodal model on vision."""
        installed = ["deepseek-r1:8b", "qwen2.5vl:latest"]
        with patch("ollama_agents.model_selector.get_installed_ollama_models", return_value=installed):
            best = select_best_local_model(task_type="vision", preferred="deepseek-r1:8b")
            self.assertEqual(best, "qwen2.5vl:latest")

    def test_05_preferred_model_honored_for_vision_if_multimodal(self):
        """Multimodal preferred model is honored on vision."""
        installed = ["gemma3:latest", "qwen2.5vl:latest"]
        with patch("ollama_agents.model_selector.get_installed_ollama_models", return_value=installed):
            best = select_best_local_model(task_type="vision", preferred="gemma3:latest")
            self.assertEqual(best, "gemma3:latest")

    def test_06_coding_routing_selects_coder_or_qwen(self):
        """Coding tasks route to dedicated coder models."""
        installed = ["deepseek-r1:8b", "llama3.1:latest", "qwen2.5-coder:7b"]
        with patch("ollama_agents.model_selector.get_installed_ollama_models", return_value=installed):
            best = select_best_local_model(task_type="coding")
            self.assertEqual(best, "qwen2.5-coder:7b")

    def test_07_reasoning_routing_selects_deepseek_r1(self):
        """Reasoning tasks route to deepseek-r1."""
        installed = ["llama3.1:latest", "deepseek-r1:8b", "qwen2.5vl:latest"]
        with patch("ollama_agents.model_selector.get_installed_ollama_models", return_value=installed):
            best = select_best_local_model(task_type="reasoning")
            self.assertEqual(best, "deepseek-r1:8b")

    def test_08_general_routing_selects_llama3(self):
        """General tasks route to llama3."""
        installed = ["llama3.1:latest", "qwen2.5vl:latest", "deepseek-r1:8b"]
        with patch("ollama_agents.model_selector.get_installed_ollama_models", return_value=installed):
            best = select_best_local_model(task_type="general")
            self.assertEqual(best, "llama3.1:latest")
```

---

## 7. Step-by-Step Implementation Roadmap for Worker

1. **Step 1 (`model_selector.py`)**:
   Apply Section 5.1 changes to `src/ollama_agents/model_selector.py`.
2. **Step 2 (`server.py`)**:
   Apply Section 5.2 changes to `src/ollama_agents/server.py`.
3. **Step 3 (`agent.py`)**:
   Apply Section 5.3 changes to `src/ollama_agents/agent.py`.
4. **Step 4 (`tests/test_m1_empirical_challenges.py`)**:
   Add `TestM1ModelSelectorRouting` test class from Section 6 and register it in `run_empirical_suite()`.
5. **Step 5 (Empirical Execution)**:
   Run `python tests/test_m1_empirical_challenges.py` and confirm all tests pass cleanly with exit code 0.
6. **Step 6 (Handoff)**:
   Publish handoff report and notify reviewer and challenger for re-audit.

---

## 8. Verification & Approval Checklist for Quality Gates

- [ ] `select_best_local_model(task_type="vision")` returns `"qwen2.5vl:latest"` when `installed = ["deepseek-r1:8b", "llama3.1:latest", "qwen2.5vl:latest"]`.
- [ ] `select_best_local_model(task_type="vision")` returns `"gemma3:latest"` when `installed = ["deepseek-r1:8b", "gemma3:latest"]`.
- [ ] `select_best_local_model(task_type="vision")` returns `"llava:7b"` when `installed = ["deepseek-r1:8b", "llava:7b"]`.
- [ ] `select_best_local_model(task_type="vision")` returns `"moondream:latest"` when `installed = ["llama3.1:latest", "moondream:latest"]`.
- [ ] `select_best_local_model(task_type="vision", preferred="deepseek-r1:8b")` returns `"qwen2.5vl:latest"`.
- [ ] `select_best_local_model(task_type="coding")` returns `"qwen2.5-coder:7b"`.
- [ ] `select_best_local_model(task_type="reasoning")` returns `"deepseek-r1:8b"`.
- [ ] `select_best_local_model(task_type="general")` returns `"llama3.1:latest"`.
- [ ] SSE `event_generator` emits error event if worker terminates without `done`/`error`.
- [ ] `json.dumps` in `agent.py` includes `default=str`.
- [ ] `python tests/test_m1_empirical_challenges.py` exits with status code 0.
