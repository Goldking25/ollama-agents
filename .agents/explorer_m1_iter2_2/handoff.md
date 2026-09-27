# Milestone M1 Iteration 2 Explorer Handoff: SSE Stream Fallback & Agent JSON Serialization Safety

**Agent**: `explorer_m1_iter2_2`  
**Working Directory**: `e:\Learning\Python\agent_test\.agents\explorer_m1_iter2_2`  
**Milestone**: M1 (Iteration 2)  
**Target Subagents**: `worker_m1_1` (implementer), `reviewer_m1_2` (reviewer), `parent` (orchestrator)  
**Date**: 2026-09-26  

---

## 1. Observation

Direct observations and quotes from the codebase and reference artifacts:

### Observation 1: Sentinel `_stream_closed` & Dead Code in `src/ollama_agents/server.py`
In `src/ollama_agents/server.py` lines 633–656:
```python
633:         finally:
634:             event_queue.put({"type": "_stream_closed"})
635: 
636:     worker_thread = threading.Thread(target=run_worker, daemon=True)
637:     worker_thread.start()
638: 
639:     async def event_generator():
640:         while True:
641:             try:
642:                 while not event_queue.empty():
643:                     item = event_queue.get_nowait()
644:                     if item.get("type") == "_stream_closed":
645:                         return
646:                     yield f"data: {json.dumps(item)}\n\n"
647:                     if item.get("type") in ("done", "error"):
648:                         return
649:                 if not worker_thread.is_alive() and event_queue.empty():
650:                     yield f"data: {json.dumps({'type': 'error', 'error': 'Worker terminated unexpectedly', 'message': 'Worker terminated unexpectedly', 'model': req.model})}\n\n"
651:                     return
652:                 await asyncio.sleep(0.08)
653:             except Exception as e:
654:                 yield f"data: {json.dumps({'type': 'error', 'error': str(e), 'message': str(e), 'model': req.model})}\n\n"
655:                 return
```
- Line 634 enqueues `{"type": "_stream_closed"}` unconditionally inside the `finally:` block of `run_worker()`.
- When `event_generator()` drains the queue at line 642, line 644 checks `if item.get("type") == "_stream_closed": return`.
- Popping `_stream_closed` triggers an immediate `return` at line 645.
- Therefore, lines 649–651 (`if not worker_thread.is_alive() and event_queue.empty():`) are **unreachable dead code** because any terminating worker thread places `_stream_closed` in the queue, which causes line 645 to return before line 649 can ever be evaluated with an empty queue.
- If `run_worker()` terminates without placing `done` or `error` in `event_queue` (e.g. due to an unhandled `BaseException`, database logging exception, or thread cancellation), the stream exits silently with 0 terminal events.

### Observation 2: UI Silent Failure on Stream Termination Without `done`/`error`
In `src/ollama_agents/static/index.html` lines 1288–1292:
```javascript
1288:                 if (finalResult) {
1289:                     appendMessage("agent", finalResult, "", model);
1290:                 } else {
1291:                     appendMessage("agent", "*(Task execution finished)*", "", model);
1292:                 }
```
- If the stream completes without a `done` or `error` event, `finalResult` is empty string.
- The UI prints `*(Task execution finished)*` rather than surfacing an error to the user.

### Observation 3: `json.dumps` Crash on Non-Serializable Tool Arguments
In `src/ollama_agents/agent.py` lines 662–666:
```python
662:                 # Anti-hallucination loop guard:
663:                 call_sig = f"{fn_name}:{json.dumps(fn_args, sort_keys=True)}"
664:                 recent_calls = getattr(self, "_recent_tool_signatures", [])
665:                 recent_calls.append(call_sig)
666:                 self._recent_tool_signatures = recent_calls[-10:]
```
- Line 663 executes `json.dumps(fn_args, sort_keys=True)` without a `default` handler or `try...except` guard.
- If `fn_args` contains a `pathlib.Path`, `datetime`, `bytes`, `set`, or other non-serializable object, `json.dumps` raises `TypeError: Object of type ... is not JSON serializable`.
- Because line 663 runs in the main loop before `_execute_tool`, this unhandled `TypeError` crashes `agent.run()`, terminating the turn and session.

---

## 2. Logic Chain

1. **SSE Fallback Failure Mechanism**:
   - From Observation 1, `_stream_closed` is enqueued in the `finally` block of `run_worker()`.
   - If an unhandled failure occurs in `run_worker()` prior to line 621 (`event_queue.put({"type": "done", ...})`) or line 632 (`event_queue.put({"type": "error", ...})`), the only terminal marker on the queue is `_stream_closed`.
   - In `event_generator()`, the queue draining loop pops `_stream_closed` and immediately executes `return` at line 645.
   - Lines 649–651 (the fallback designed to emit `'Worker terminated unexpectedly'` when the worker thread is dead) are bypassed because `return` has already exited the generator.
   - The stream terminates without emitting `done` or `error`.
   - Per Observation 2, the UI displays `*(Task execution finished)*`, masking the worker thread crash.
   - By tracking a generator-scoped boolean `terminal_event_sent = False`, whenever `_stream_closed` is encountered and `not terminal_event_sent`, the generator can yield the fallback error event with `model: req.model` before returning.

2. **JSON Serialization Failure Mechanism**:
   - From Observation 3, line 663 computes `call_sig = f"{fn_name}:{json.dumps(fn_args, sort_keys=True)}"`.
   - Standard Python `json.dumps` does not serialize `Path`, `datetime`, `bytes`, or `set`.
   - Supplying `default=str` to `json.dumps(fn_args, sort_keys=True, default=str)` guarantees that any non-serializable Python object is coerced to a deterministic string representation.
   - Wrapping in a defensive `try...except Exception` block further protects against edge cases like circular references.

---

## 3. Caveats

- **Scope Boundary**: As an explorer subagent, this analysis is read-only. Source code in `src/ollama_agents/` was not directly modified.
- **Thread Abort Semantics**: In Python, a daemon thread terminating due to `BaseException` will still run its `finally` block unless the whole process is killed via SIGKILL. Tracking `terminal_event_sent` handles both cases: when `_stream_closed` is received and when the thread terminates without draining.
- No other caveats.

---

## 4. Conclusion

Both secondary resilience defects identified in Milestone M1 reviews are confirmed and have actionable, drop-in solutions:

1. **`server.py` SSE Fallback Fix**:
   Track `terminal_event_sent = False` in `event_generator()`. If `_stream_closed` is popped and `not terminal_event_sent`, emit:
   `f"data: {json.dumps({'type': 'error', 'error': 'Worker terminated unexpectedly', 'message': 'Worker terminated unexpectedly', 'model': req.model})}\n\n"`
   and mark `terminal_event_sent = True` before returning.
2. **`agent.py` Serialization Fix**:
   Update line 663 to:
   ```python
   try:
       call_sig = f"{fn_name}:{json.dumps(fn_args, sort_keys=True, default=str)}"
   except Exception:
       call_sig = f"{fn_name}:{str(fn_args)}"
   ```

Detailed analysis and complete before/after diffs are documented in:
`e:\Learning\Python\agent_test\.agents\explorer_m1_iter2_2\stream_and_agent_resilience.md`.

---

## 5. Verification Method

### Test 1: SSE Premature Worker Exit Emits Fallback Error
Run this verification snippet:
```python
from unittest.mock import patch
import json
from fastapi.testclient import TestClient
from ollama_agents.server import app

client = TestClient(app)
with patch("ollama_agents.agent.Agent.run") as mock_run:
    # Simulate unhandled BaseException escaping Exception catches
    mock_run.side_effect = BaseException("Fatal thread abort")
    with client.stream("POST", "/api/chat/stream", json={"prompt": "hi", "model": "test-model"}) as resp:
        events = [json.loads(line[6:].strip()) for line in resp.iter_lines() if line.startswith("data: ")]
        err_evt = next((e for e in events if e.get("type") == "error"), None)
        assert err_evt is not None, "Failed: Stream exited without terminal error event!"
        assert err_evt.get("model") == "test-model", "Failed: Missing model attribution!"
        assert "Worker terminated unexpectedly" in err_evt.get("message", "")
```

### Test 2: Non-Serializable Tool Arguments
```python
from pathlib import Path
import json
from ollama_agents.agent import Agent

args = {"file_path": Path("/test/path"), "data": b"abc"}
call_sig = f"my_tool:{json.dumps(args, sort_keys=True, default=str)}"
assert "/test/path" in call_sig
assert "b'abc'" in call_sig or "abc" in call_sig
```

### Test 3: Existing Empirical Suite
Run the full M1 challenge suite:
`python tests/test_m1_empirical_challenges.py`
All tests must pass with 0 failures.
