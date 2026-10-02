import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ollama_agents.agent import Agent, _is_text_tool_model
from ollama_agents.tools.actions import write_file, run_terminal
from ollama_agents.tools.android_builder import build_android_apk


class TestModelToolCalling(unittest.TestCase):
    def setUp(self):
        self.agent = Agent(
            model="qwen2.5-coder:14b",
            tools=[write_file, run_terminal, build_android_apk]
        )

    def test_model_classification(self):
        # Qwen models (including Qwen Coder) support native tools
        self.assertFalse(_is_text_tool_model("qwen2.5-coder:14b"))
        self.assertFalse(_is_text_tool_model("qwen2.5-coder:32b"))
        self.assertFalse(_is_text_tool_model("qwen2.5:latest"))
        self.assertFalse(_is_text_tool_model("qwen3.5-abliterated"))

        # Gemma 3 and Gemma 4 support native tools
        self.assertFalse(_is_text_tool_model("gemma4:e4b"))
        self.assertFalse(_is_text_tool_model("gemma3:8b"))

        # DeepSeek and older models use text tools
        self.assertTrue(_is_text_tool_model("deepseek-coder-v2:16b"))
        self.assertTrue(_is_text_tool_model("deepseek-r1:8b"))
        self.assertTrue(_is_text_tool_model("codellama:13b"))
        self.assertTrue(_is_text_tool_model("starcoder:latest"))

    def test_qwen_xml_tool_call(self):
        text = '''
<tool_call>
{"name": "write_file", "arguments": {"filepath": "main.py", "content": "print('hello')"}}
</tool_call>
'''
        calls = self.agent._parse_text_tool_calls(text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["function"]["name"], "write_file")
        self.assertEqual(calls[0]["function"]["arguments"]["filepath"], "main.py")

    def test_qwen_coder_special_tokens(self):
        text = '<|tool_call_begin|> >write_file: {"filepath": "test.py", "content": "x = 1"} <|tool_call_end|>'
        calls = self.agent._parse_text_tool_calls(text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["function"]["name"], "write_file")
        self.assertEqual(calls[0]["function"]["arguments"]["filepath"], "test.py")

    def test_gemma_call_format(self):
        text = 'call:run_terminal{"command": "python test.py"}'
        calls = self.agent._parse_text_tool_calls(text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["function"]["name"], "run_terminal")
        self.assertEqual(calls[0]["function"]["arguments"]["command"], "python test.py")

    def test_deepseek_and_general_coder_ipython_commands(self):
        text = '''
### Action: Compile the Android APK
```python
!build_android_apk ~/ollama_workspace/2048_game_application
```
'''
        calls = self.agent._parse_text_tool_calls(text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["function"]["name"], "build_android_apk")
        self.assertEqual(calls[0]["function"]["arguments"]["output_filename"], "2048_game_application.apk")


if __name__ == "__main__":
    unittest.main()
