import json
from ollama_agents.tools import edit_image, edit_image_sd_forge
from ollama_agents import Agent

a = Agent(model="llama3.1:latest", tools=[edit_image, edit_image_sd_forge])
print("Registered tool names in agent:", list(a.tools.keys()))
sample_text = '{"name": "edit_image", "parameters": {"filepath": "uploads/image.png", "prompt": "add a western dress"}}'

res = a._parse_text_tool_calls(sample_text)
print("TEST RESULT:", res)
