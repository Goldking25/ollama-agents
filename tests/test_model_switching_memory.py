"""Unit and Integration tests for Smart Model Unloading & Switching Memory Safety.
File: tests/test_model_switching_memory.py
"""

import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from ollama_agents.memory_manager import MemorySafetyManager
from ollama_agents.server import app
from ollama_agents.agent import Agent


class TestModelSwitchingMemory(unittest.TestCase):
    """Test suite for memory-safe model unloading and switching."""

    def setUp(self):
        self.mgr = MemorySafetyManager(max_concurrent_agents=3, auto_unload_on_switch=True)
        self.client = TestClient(app)

    @patch("httpx.get")
    def test_get_loaded_models(self, mock_get):
        """get_loaded_models correctly queries Ollama /api/ps and parses memory sizes."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "models": [
                {
                    "name": "qwen3.8:27b",
                    "model": "qwen3.8:27b",
                    "size": 18506967937,
                    "size_vram": 4513469561,
                    "expires_at": "2026-10-02T17:18:51Z"
                }
            ]
        }
        mock_get.return_value = mock_resp

        loaded = self.mgr.get_loaded_models()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["name"], "qwen3.8:27b")
        self.assertEqual(loaded[0]["size_gb"], 17.24)
        self.assertEqual(loaded[0]["size_vram_gb"], 4.2)

    @patch("httpx.post")
    def test_unload_model_success(self, mock_post):
        """unload_model sends keep_alive: 0 to /api/generate."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"done": true, "done_reason": "unload"}'
        mock_post.return_value = mock_resp

        success = self.mgr.unload_model("qwen3.8:27b")
        self.assertTrue(success)
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        self.assertEqual(call_kwargs["json"], {"model": "qwen3.8:27b", "keep_alive": 0})

    @patch.object(MemorySafetyManager, "unload_model", return_value=True)
    @patch.object(MemorySafetyManager, "get_loaded_models")
    def test_prepare_model_switch_unloads_different_model(self, mock_get_loaded, mock_unload):
        """When switching to a different model, the currently resident model is unloaded."""
        mock_get_loaded.return_value = [
            {"name": "qwen3.8:27b", "model": "qwen3.8:27b", "size_gb": 17.24}
        ]

        unloaded = self.mgr.prepare_model_switch(target_model="deepseek-r1:8b")
        self.assertEqual(unloaded, ["qwen3.8:27b"])
        mock_unload.assert_called_once_with("qwen3.8:27b", host=None)

    @patch.object(MemorySafetyManager, "unload_model", return_value=True)
    @patch.object(MemorySafetyManager, "get_loaded_models")
    def test_prepare_model_switch_preserves_same_model(self, mock_get_loaded, mock_unload):
        """When executing the already loaded model, it is preserved in memory for speed."""
        mock_get_loaded.return_value = [
            {"name": "deepseek-r1:8b", "model": "deepseek-r1:8b", "size_gb": 5.0}
        ]

        # Same model requested
        unloaded = self.mgr.prepare_model_switch(target_model="deepseek-r1:8b")
        self.assertEqual(unloaded, [])
        mock_unload.assert_not_called()

        # Tag-variant match (e.g. llama3.1 vs llama3.1:latest)
        mock_get_loaded.return_value = [
            {"name": "llama3.1:latest", "model": "llama3.1:latest", "size_gb": 5.0}
        ]
        unloaded_variant = self.mgr.prepare_model_switch(target_model="llama3.1")
        self.assertEqual(unloaded_variant, [])
        mock_unload.assert_not_called()

    @patch("httpx.get")
    def test_api_models_loaded_endpoint(self, mock_get):
        """GET /api/models/loaded returns HTTP 200 with list of resident models."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "models": [{"name": "deepseek-r1:8b", "size": 5368709120, "size_vram": 5368709120}]
        }
        mock_get.return_value = mock_resp

        res = self.client.get("/api/models/loaded")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("loaded_models", data)
        self.assertIn("count", data)

    @patch("httpx.post")
    def test_api_models_unload_endpoint(self, mock_post):
        """POST /api/models/unload returns HTTP 200 and unloads specified model."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"done": true}'
        mock_post.return_value = mock_resp

        res = self.client.post("/api/models/unload", json={"model": "deepseek-r1:8b"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("unloaded"), ["deepseek-r1:8b"])

    @patch.object(MemorySafetyManager, "prepare_model_switch")
    def test_agent_run_triggers_prepare_model_switch(self, mock_switch):
        """Agent.run proactively triggers prepare_model_switch before turn execution."""
        from ollama_agents.exceptions import MaxTurnsExceeded
        agent = Agent(name="TestAgent", instructions="Perform task", model="deepseek-r1:8b", max_turns=1)
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.message = MagicMock()
        mock_resp.message.content = "Final Answer: Done"
        mock_resp.message.tool_calls = None
        mock_client.chat.return_value = mock_resp
        agent.client = mock_client

        try:
            agent.run("Test task")
        except MaxTurnsExceeded:
            pass
        mock_switch.assert_called_once_with("deepseek-r1:8b", host=None)


if __name__ == "__main__":
    unittest.main()
