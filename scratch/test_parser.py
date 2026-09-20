from ollama_agents import Agent
from ollama_agents.tools import edit_image_sd_forge

a = Agent(model='llama3.1:latest', tools=[edit_image_sd_forge])
sample_text = """To answer this question, I will use the edit_image_sd_forge function. Here is a JSON object with its proper arguments:

{"name": "edit_image_sd_forge", "parameters": {"filepath": "uploads/IMG20251122111.jpg", "prompt": "change background"}}"""

res = a._parse_text_tool_calls(sample_text)
print("Parsed tool calls:", res)
