# 🤖 `ollama-agents` (v0.6.0)

> **Level 4 & 5 Autonomous Multi-Agent Workstation & Multi-Node Cluster Engine for Local LLMs (Ollama)**

`ollama-agents` is a powerful, privacy-first, fully local multi-agent orchestration framework. It runs on consumer laptops and desktop GPUs using Ollama GGUF models. It features long-horizon goal decomposition, auto-checkpoint recovery, dynamic skill generation, Hugging Face model hot-swapping, Stable Diffusion / ComfyUI media generation, and a multi-laptop distributed compute cluster with zero-configuration mDNS auto-discovery.

---

## 🌟 Key Features

- 🎯 **Long-Horizon Multi-Session Goals**: Automatically decomposes complex intent into session-sized subtasks with resumable state and context memory.
- 🖥️ **Distributed Multi-Laptop Cluster**: Connect secondary laptops over Wi-Fi / Tailscale. Features **mDNS UDP Auto-Discovery** and zero-latency WebSocket node streaming.
- 🐙 **GitHub Automated Workflows**: Autonomous Git cloning, feature branch creation, commit & push, and Pull Request generation via GitHub CLI (`gh`).
- 🎨 **Multimodal Media Generation**: Built-in tools for Stable Diffusion WebUI Forge (Image Gen & Editing) and ComfyUI (Video Gen).
- 🤗 **Hugging Face Model Hub**: Search, inspect, and pull trending GGUF models directly into local Ollama storage from the Web Dashboard.
- 🛡️ **Memory Safety Guard**: Real-time RAM/VRAM resource monitoring and garbage collection to prevent out-of-memory (OOM) crashes.
- 🧪 **Playwright Automated UAT Testing**: Built-in User Acceptance Testing tool (`test_ui_playwright`) for automatic end-to-end web browser validation, form interaction, and visual screenshot verification at the end of development.
- 📱 **Mobile-Responsive Control Center**: Sleek indigo glassmorphism Web Dashboard fully optimized for desktop, tablet, and mobile screens (`http://localhost:8100`).

---

## 📦 Installation & Setup

### Option 1: Direct `pip` Installation (Recommended)

Install `ollama-agents` directly on your main machine or secondary cluster workers:

```bash
pip install git+https://github.com/Goldking25/ollama-agents.git
```

This installs two global executable CLI commands:
- `ollama-agents` — Launches the Web Control Center and Agent Backend.
- `ollama-agents-worker` — Starts the distributed worker server on secondary laptops.

---

### Option 2: Clone & Development Setup

```bash
# 1. Clone repository
git clone https://github.com/Goldking25/ollama-agents.git
cd ollama-agents

# 2. Install dependencies
pip install -e .

# 3. Launch Control Center & Backend
start_agent.bat
```

---

## 🖥️ Setting Up a Secondary Worker Laptop (Multi-Node Cluster)

You can offload heavy sub-agent tasks and model inference to secondary laptops on your local network:

### Step 1: Install `ollama-agents` on the Secondary Laptop
```bash
pip install git+https://github.com/Goldking25/ollama-agents.git
```

### Step 2: Set `OLLAMA_HOST=0.0.0.0`
On the secondary laptop, allow Ollama to accept local network requests:
```cmd
setx OLLAMA_HOST "0.0.0.0"
```

### Step 3: Run Worker Node
On the secondary laptop, run either:
```cmd
ollama-agents-worker
```
*(Or double-click `start_worker_node.bat` inside the cloned repo).*

> 📡 **Auto-Discovery**: The primary laptop's Web Dashboard will automatically detect the secondary laptop via mDNS UDP broadcast (Port 9999) and list its GPUs and GGUF models under the **🖥️ Cluster Nodes** tab!

---

## 🚀 Quick Usage Examples

### Python API

```python
from ollama_agents import Agent, GoalRegistry
from ollama_agents.tools import web_search, write_file, github_clone_repo

# 1. Create a Level 4 Autonomous Agent
agent = Agent(
    model="deepseek-r1:8b",
    tools=[web_search, write_file, github_clone_repo]
)

# 2. Run a task
response = agent.run("Research top 3 Python web frameworks and write a report to summary.md")
print(response)
```

### Command Line Interface (CLI)

```bash
# Start Web UI server on port 8100
python -m ollama_agents.server

# Or run interactive CLI agent
ollama-agents chat --model deepseek-r1:8b
```

---

## 📜 License

MIT License © 2026 Manigandan Maharajan
