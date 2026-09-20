import json
from ollama_agents.tools import edit_image, edit_image_sd_forge
from ollama_agents import Agent

a = Agent(model="llama3.1:latest", tools=[edit_image, edit_image_sd_forge])
sample_text = """It seems like the edit_image_sd_forge function call failed due to a timeout. This could be because the model is taking too long to process the request.

Let me try an alternative approach using the edit_image function with a more specific prompt:

{"name": "edit_image", "parameters": {"filepath": "uploads/image.png", "prompt": "add a western dress to this image, with a cowboy hat and boots"}}"""

res = a._parse_text_tool_calls(sample_text)
print("TEST PARSED SUCCESSFULLY:", res)
