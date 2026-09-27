"""
Milestone M1 Empirical Challenge Suite
File: tests/test_m1_empirical_challenges.py

Empirical stress tests and adversarial verification for Milestone M1:
- Dynamic Model Availability (/api/models/installed and /api/models)
- Multimodal Model Classification & Capability Tagging
- Multimodal Payload Resolution & Injection (Gemma 3, Qwen2.5-VL, etc.)
- Missing-File Loop Prevention & Anti-Hallucination Repetition Guard
- SSE Stream Terminal Reliability & Model Attribution

Can be executed directly via:
    python tests/test_m1_empirical_challenges.py
or with pytest / unittest.
"""

import os
import sys
import json
import base64
import time
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Dict, Any, List, Optional
from unittest.mock import MagicMock, patch

# Ensure src/ is on Python search path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Import TestClient
try:
    from fastapi.testclient import TestClient
except ImportError:
    from starlette.testclient import TestClient

# Import Application & Modules under test
from ollama_agents.server import app, resolve_multimodal_images, SESSION_AGENTS
from ollama_agents.model_selector import is_multimodal_model, MULTIMODAL_KEYWORDS, select_best_local_model
from ollama_agents.tools.actions import read_file, WORKSPACE_ROOT
from ollama_agents.agent import Agent
from ollama_agents.exceptions import MaxTurnsExceeded


class TestM1ModelsInstalledEndpoint(unittest.TestCase):
    """Stress tests for /api/models/installed and model capability detection."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_01_installed_models_endpoint_returns_200_and_valid_schema(self):
        """GET /api/models/installed returns HTTP 200 with valid JSON schema."""
        resp = self.client.get("/api/models/installed")
        self.assertEqual(resp.status_code, 200, f"Expected 200, got {resp.status_code}: {resp.text}")
        data = resp.json()

        self.assertIn("status", data)
        self.assertIn("models", data)
        self.assertIn("details", data)
        self.assertIn("pulling", data)

        self.assertIsInstance(data["models"], list)
        self.assertIsInstance(data["details"], list)
        self.assertIsInstance(data["pulling"], list)

        # Verify details structure
        for item in data["details"]:
            self.assertIn("name", item)
            self.assertIn("is_multimodal", item)
            self.assertIn("capabilities", item)
            self.assertIsInstance(item["name"], str)
            self.assertIsInstance(item["is_multimodal"], bool)
            self.assertIsInstance(item["capabilities"], list)
            self.assertIn("general", item["capabilities"])

    def test_02_multimodal_classification_comprehensive(self):
        """Verify is_multimodal_model accurately classifies known vision and non-vision models."""
        multimodal_positives = [
            "gemma3",
            "gemma3:latest",
            "gemma3:4b",
            "gemma3:12b",
            "gemma3:27b",
            "qwen2.5vl:latest",
            "qwen2.5-vl:7b",
            "qwen2.5-vl:72b",
            "llava:7b",
            "llava:13b",
            "llava-llama3:8b",
            "moondream:latest",
            "moondream:1.8b",
            "llama3.2-vision:11b",
            "llama3.2-vision:90b",
            "custom-vision-model:v1",
            "docker.io/library/gemma3:latest",
        ]
        for model in multimodal_positives:
            self.assertTrue(
                is_multimodal_model(model),
                f"Model '{model}' should be classified as multimodal."
            )

        multimodal_negatives = [
            "deepseek-r1:8b",
            "deepseek-r1:7b",
            "deepseek-coder-v2:16b",
            "llama3.1:latest",
            "llama3.1:8b",
            "llama3.3:70b",
            "mistral:7b",
            "qwen2.5-coder:7b",
            "qwen2.5:14b",
            "phi3:mini",
            "gemma2:9b",  # gemma2 is text-only
            "starcoder2:7b",
        ]
        for model in multimodal_negatives:
            self.assertFalse(
                is_multimodal_model(model),
                f"Model '{model}' should NOT be classified as multimodal."
            )

    def test_03_multimodal_classification_edge_cases(self):
        """Verify is_multimodal_model handles empty, null, and adversarial casing."""
        self.assertFalse(is_multimodal_model(""))
        self.assertFalse(is_multimodal_model(None))
        # Case insensitivity
        self.assertTrue(is_multimodal_model("GEMMA3:LATEST"))
        self.assertTrue(is_multimodal_model("Qwen2.5VL:7B"))
        self.assertTrue(is_multimodal_model("LlaVA:Latest"))
        self.assertTrue(is_multimodal_model("MoonDream:Latest"))

    def test_04_installed_models_resilience_when_ollama_fails(self):
        """Verify /api/models/installed returns HTTP 200 with fallback data if Ollama service is unreachable."""
        with patch("ollama.list") as mock_list:
            mock_list.side_effect = Exception("Ollama daemon unreachable: connection refused")
            resp = self.client.get("/api/models/installed")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIn("models", data)
            self.assertIn("details", data)
            self.assertIn("deepseek-r1:8b", data["models"])
            self.assertIn("llama3.1:latest", data["models"])

    def test_05_api_models_endpoint_parity(self):
        """Verify /api/models returns identical payload to /api/models/installed."""
        resp_installed = self.client.get("/api/models/installed")
        resp_models = self.client.get("/api/models")
        self.assertEqual(resp_installed.status_code, 200)
        self.assertEqual(resp_models.status_code, 200)
        self.assertEqual(resp_installed.json().get("models"), resp_models.json().get("models"))


class TestM1MultimodalPayloadResolution(unittest.TestCase):
    """Stress tests for resolve_multimodal_images and payload assembly."""

    @classmethod
    def setUpClass(cls):
        cls.workspace = Path.home() / "ollama_workspace"
        cls.workspace.mkdir(parents=True, exist_ok=True)
        cls.uploads = cls.workspace / "uploads"
        cls.uploads.mkdir(parents=True, exist_ok=True)

    def test_01_resolve_valid_png_in_uploads(self):
        """Verify resolve_multimodal_images correctly reads and base64-encodes PNG in uploads/."""
        probe_file = self.uploads / "probe_test_img.png"
        raw_bytes = b"\x89PNG\r\n\x1a\nTestImageDataPayload12345"
        probe_file.write_bytes(raw_bytes)
        try:
            # Test 1: Just filename
            res1 = resolve_multimodal_images("probe_test_img.png")
            self.assertEqual(len(res1), 1)
            decoded1 = base64.b64decode(res1[0])
            self.assertEqual(decoded1, raw_bytes)

            # Test 2: uploads/filename
            res2 = resolve_multimodal_images("uploads/probe_test_img.png")
            self.assertEqual(len(res2), 1)
            decoded2 = base64.b64decode(res2[0])
            self.assertEqual(decoded2, raw_bytes)

            # Test 3: Absolute path
            res3 = resolve_multimodal_images(str(probe_file.resolve()))
            self.assertEqual(len(res3), 1)
            self.assertEqual(base64.b64decode(res3[0]), raw_bytes)
        finally:
            if probe_file.exists():
                probe_file.unlink()

    def test_02_resolve_various_image_extensions(self):
        """Verify support for jpg, jpeg, webp, gif, bmp."""
        image_extensions = ["jpg", "jpeg", "webp", "gif", "bmp"]
        for ext in image_extensions:
            fname = f"probe_fmt_test.{ext}"
            file_path = self.uploads / fname
            dummy_data = f"Simulated-{ext}-bytes".encode("utf-8")
            file_path.write_bytes(dummy_data)
            try:
                res = resolve_multimodal_images(fname)
                self.assertEqual(len(res), 1, f"Failed resolving .{ext}")
                self.assertEqual(base64.b64decode(res[0]), dummy_data)
            finally:
                if file_path.exists():
                    file_path.unlink()

    def test_03_resolve_missing_file_returns_empty_safely(self):
        """Missing files return empty list without raising exceptions."""
        res = resolve_multimodal_images("totally_missing_file_0000.png")
        self.assertEqual(res, [])

    def test_04_resolve_empty_and_none_inputs(self):
        """Empty string or None attachment returns empty list."""
        self.assertEqual(resolve_multimodal_images(""), [])
        self.assertEqual(resolve_multimodal_images(None), [])

    def test_05_resolve_non_media_files_ignored(self):
        """Non-image non-video files are ignored and return empty list."""
        probe_txt = self.uploads / "probe_notes.txt"
        probe_txt.write_text("Hello world", encoding="utf-8")
        try:
            res = resolve_multimodal_images("probe_notes.txt")
            self.assertEqual(res, [])
        finally:
            if probe_txt.exists():
                probe_txt.unlink()

    def test_06_agent_run_images_injection_into_history(self):
        """Verify Agent.run() injects 'images' field into the user message in self.history."""
        agent = Agent(model="qwen2.5vl:latest", stateful=False, tools=[])
        fake_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="

        with patch.object(agent.client, "chat") as mock_chat:
            mock_chat.return_value = {
                "message": {"role": "assistant", "content": "I see a 1x1 black pixel in the image."}
            }
            res = agent.run("What is in this image?", max_turns=1, images=[fake_b64])
            self.assertIn("1x1 black pixel", res)

            # Verify history contains user message with images
            user_msg = next((m for m in agent.history if m.get("role") == "user"), None)
            self.assertIsNotNone(user_msg, "User message not found in agent history")
            self.assertIn("images", user_msg)
            self.assertEqual(user_msg["images"], [fake_b64])

            # Verify call args to client.chat passed messages containing images
            call_kwargs = mock_chat.call_args[1]
            messages_sent = call_kwargs["messages"]
            sent_user_msg = next((m for m in messages_sent if m.get("role") == "user"), None)
            self.assertIsNotNone(sent_user_msg)
            self.assertIn("images", sent_user_msg)
            self.assertEqual(sent_user_msg["images"], [fake_b64])


class TestM1MissingFileLoopPrevention(unittest.TestCase):
    """Stress tests for read_file error formatting, replanning trigger, and repetition guards."""

    def test_01_read_file_nonexistent_file_returns_error_prefix(self):
        """read_file returns string with [Error] prefix and directory hints when file is missing."""
        result = read_file("definitely_non_existent_file_abc123.json")
        self.assertTrue(
            result.startswith("[Error]"),
            f"Expected result to start with [Error], got: {result[:50]}"
        )
        self.assertIn("File not found", result)
        self.assertIn("Files currently in workspace:", result)
        self.assertIn("list_workspace_files", result)

    def test_02_read_file_existing_file_returns_content(self):
        """read_file returns actual text content for existing workspace file."""
        test_file = WORKSPACE_ROOT / "m1_test_file.txt"
        test_file.write_text("Hello from M1 challenge test!", encoding="utf-8")
        try:
            content = read_file("m1_test_file.txt")
            self.assertEqual(content, "Hello from M1 challenge test!")
        finally:
            if test_file.exists():
                test_file.unlink()

    def test_03_read_file_truncates_large_files_safely(self):
        """read_file truncates files exceeding max_chars with clean notice."""
        test_file = WORKSPACE_ROOT / "m1_large_file.txt"
        large_text = "A" * 12000
        test_file.write_text(large_text, encoding="utf-8")
        try:
            content = read_file("m1_large_file.txt", max_chars=8000)
            self.assertTrue(len(content) > 8000)  # max_chars + truncation notice
            self.assertIn("[Truncated", content)
        finally:
            if test_file.exists():
                test_file.unlink()

    def test_04_anti_hallucination_repetition_guard_in_agent(self):
        """Agent intercepts identical repeated failing tool calls after 3 attempts."""
        agent = Agent(model="deepseek-r1:8b", stateful=False, tools=[read_file])

        # Simulate 3 identical tool calls
        call_turns = [
            # Turn 1: model calls read_file
            {"message": {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "read_file", "arguments": {"filepath": "ghost_file.txt"}}}
            ]}},
            # Turn 2: model calls read_file again
            {"message": {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "read_file", "arguments": {"filepath": "ghost_file.txt"}}}
            ]}},
            # Turn 3: model calls read_file 3rd time
            {"message": {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "read_file", "arguments": {"filepath": "ghost_file.txt"}}}
            ]}},
            # Turn 4: model acknowledges failure
            {"message": {"role": "assistant", "content": "The file does not exist, so I am concluding the task."}}
        ]

        turn_idx = 0
        def fake_chat(*args, **kwargs):
            nonlocal turn_idx
            resp = call_turns[turn_idx]
            turn_idx += 1
            return resp

        with patch.object(agent.client, "chat", side_effect=fake_chat):
            res = agent.run("Find ghost_file.txt", max_turns=5)
            self.assertIn("concluding the task", res)

            # Inspect tool responses in history
            tool_msgs = [m for m in agent.history if m.get("role") == "tool"]
            self.assertEqual(len(tool_msgs), 3)
            # The 1st and 2nd should be "[Error] File not found..."
            self.assertTrue(tool_msgs[0]["content"].startswith("[Error] File not found"))
            self.assertTrue(tool_msgs[1]["content"].startswith("[Error] File not found"))
            # The 3rd should be "[Tool Failure] Repeated identical tool call detected"
            self.assertTrue(
                tool_msgs[2]["content"].startswith("[Tool Failure] Repeated identical tool call detected"),
                f"Expected repetition intercept, got: {tool_msgs[2]['content']}"
            )


class TestM1SSEStreamRobustness(unittest.TestCase):
    """Stress tests for SSE chat stream completion, error recovery, and model attribution."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_01_stream_normal_completion_with_attribution(self):
        """SSE stream emits done event containing proper model attribution."""
        with patch("ollama_agents.agent.Agent.run") as mock_run:
            mock_run.return_value = "Verified normal answer."
            payload = {
                "prompt": "Hello world",
                "model": "gemma3:latest",
                "max_turns": 3,
                "session_id": "m1_stream_sess_1"
            }
            with cls.client.stream("POST", "/api/chat/stream", json=payload) as resp:
                self.assertEqual(resp.status_code, 200)
                events = []
                for line in resp.iter_lines():
                    if line.startswith("data: "):
                        raw = line[6:].strip()
                        if raw:
                            events.append(json.loads(raw))

                self.assertTrue(len(events) > 0)
                done_evt = next((e for e in events if e.get("type") == "done"), None)
                self.assertIsNotNone(done_evt, "Stream missing 'done' event")
                self.assertEqual(done_evt.get("model"), "gemma3:latest")
                self.assertIn("result", done_evt)
                self.assertIn("response", done_evt)
                self.assertEqual(done_evt["result"], "Verified normal answer.")

    def test_02_stream_worker_exception_emits_error_with_attribution(self):
        """SSE stream emits error event with model attribution when worker raises exception."""
        with patch("ollama_agents.agent.Agent.run") as mock_run:
            mock_run.side_effect = RuntimeError("Fatal LLM context memory corruption")
            payload = {
                "prompt": "Trigger crash",
                "model": "qwen2.5vl:latest",
                "max_turns": 2,
                "session_id": "m1_stream_sess_err"
            }
            with cls.client.stream("POST", "/api/chat/stream", json=payload) as resp:
                self.assertEqual(resp.status_code, 200)
                events = []
                for line in resp.iter_lines():
                    if line.startswith("data: "):
                        raw = line[6:].strip()
                        if raw:
                            events.append(json.loads(raw))

                err_evt = next((e for e in events if e.get("type") == "error"), None)
                self.assertIsNotNone(err_evt, "Stream missing 'error' event on worker exception")
                self.assertEqual(err_evt.get("model"), "qwen2.5vl:latest")
                self.assertIn("Fatal LLM context", err_evt.get("error", ""))
                self.assertIn("Fatal LLM context", err_evt.get("message", ""))

    def test_03_stream_max_turns_exceeded_emits_done_with_attribution(self):
        """SSE stream emits done event with model attribution when max turns is exceeded."""
        with patch("ollama_agents.agent.Agent.run") as mock_run:
            mte = MaxTurnsExceeded(turns=2)
            mte.last_output = "Partial progress completed."
            mock_run.side_effect = mte

            payload = {
                "prompt": "Perform multi-step research",
                "model": "deepseek-r1:8b",
                "max_turns": 2,
                "session_id": "m1_stream_mte_sess"
            }
            with cls.client.stream("POST", "/api/chat/stream", json=payload) as resp:
                self.assertEqual(resp.status_code, 200)
                events = []
                for line in resp.iter_lines():
                    if line.startswith("data: "):
                        raw = line[6:].strip()
                        if raw:
                            events.append(json.loads(raw))

                done_evt = next((e for e in events if e.get("type") == "done"), None)
                self.assertIsNotNone(done_evt, "Stream missing 'done' event on MaxTurnsExceeded")
                self.assertEqual(done_evt.get("model"), "deepseek-r1:8b")
                self.assertIn("Reached turn limit", done_evt.get("result", ""))


# ──────────────────────────────────────────────────────────────────────────────
# TEST CLASS 5: MODEL ROUTING & MULTIMODAL SELECTION (Milestone M1 Iteration 2)
# ──────────────────────────────────────────────────────────────────────────────

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
    suite.addTests(loader.loadTestsFromTestCase(TestM1ModelRoutingAndSelection))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("=" * 80)
    if result.wasSuccessful():
        print(f"ALL EMPIRICAL CHALLENGE TESTS PASSED ({result.testsRun} tests)")
        return 0
    else:
        print(f"EMPIRICAL CHALLENGE TESTS FAILED: {len(result.failures)} failures, {len(result.errors)} errors")
        return 1


if __name__ == "__main__":
    sys.exit(run_empirical_suite())
