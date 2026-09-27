"""Agent — Level 4 autonomous LLM agent powered by a local Ollama model.

New in this version (long-horizon):
- Context compression: history is summarised when it exceeds compress_after messages.
- run_goal(): drives a multi-session Goal from the GoalRegistry, one task per session.
- Planner integration: replan() called on tool failure.
- Checkpointing: crash-safe resumption via task_id.
- Self-improvement: reflection loop after each run.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

import ollama

from .checkpoint import CheckpointManager, CheckpointState
from .exceptions import AgentConfigError, MaxTurnsExceeded, ToolExecutionError
from .memory import MemoryStore
from .tool import Tool
# GoalRegistry imported lazily inside run_goal() to avoid circular imports

logger = logging.getLogger(__name__)

# ─── ReAct prompt ─────────────────────────────────────────────────────────────
_REACT_INSTRUCTIONS = """
## Reasoning Protocol
Follow the Thought → Action → Observation cycle for every tool call.

Thought: <why you are taking this action>
[tool call happens automatically]
Observation: <what the tool returned>
Thought: <what you conclude>
... (repeat as needed)
Final Answer: <your complete response>

## Relentless Execution & Tenacity Rules (CRITICAL)
- NEVER TAKE "NO" FOR AN ANSWER. Once assigned a task, you MUST finish it to 100% completion.
- DO NOT GIVE UP, DO NOT MAKE EXCUSES, AND NEVER PASS THE WORK BACK TO THE USER.
- NEVER say "I cannot do this", "as an AI I am unable", "you should do it yourself", or "I failed".
- You are equipped with autonomous capabilities: write_file, read_file, run_terminal, run_python, web_search, build_android_apk, delegate_subagent, and more. Use them proactively.
- If a tool fails or throws an error, do NOT stop: analyze the error, fix the parameters, rewrite the broken code, and re-execute until it succeeds.
- If an approach hits a roadblock, pivot immediately to an alternative method.
- FILE ORGANIZATION: ALWAYS create a dedicated, neatly named subfolder in ~/ollama_workspace/ for any new project, app, or script. NEVER generate loose code files or generic folders (like `src/` or `res/`) directly in the workspace root.
- Always start with a Thought before calling a tool.
- NEVER stop after writing a Thought. A Thought MUST always be immediately accompanied by its corresponding Tool Call.
- DO NOT simulate or hallucinate tool outputs. Only output the tool call itself and wait for the system to return the result. Do not output `<|tool_outputs_begin|>` or similar tags.
- DO NOT GUESS FILENAMES. When asked about existing files, filenames, or locations, use the `list_workspace_files` tool to see all files in ~/ollama_workspace/. If a file does not exist, do NOT repeatedly guess random filenames.
- Emit "Final Answer:" ONLY when the entire user task is completely fulfilled, tested, and delivered.
- When the plan is updated, follow the new steps.
- IMPORTANT FOR ANDROID & APK REQUESTS: When asked for an Android app, APK file, mobile app, or .apk compilation, you MUST call the `build_android_apk` tool to compile and generate the actual .apk file. Do NOT tell the user to compile it themselves or that you cannot build APKs. You HAVE the `build_android_apk` tool installed.
"""

# Models that cannot handle native Ollama tool calling (abliterated, fine-tuned, etc.)
# These models will receive tool descriptions as plain text in the system prompt instead.
_TEXT_TOOL_MODELS = {
    "mannix/llama3.1-8b-abliterated",
}

def _is_text_tool_model(model_name: str) -> bool:
    """Check if a model needs text-based tool injection instead of native tool calling."""
    name_lower = model_name.lower()
    # Qwen models (including qwen3.5-abliterated) support native Ollama tool calling
    if "qwen" in name_lower:
        return False
    # Check exact match or prefix match (for tag variants like :9b, :latest)
    for blocked in _TEXT_TOOL_MODELS:
        if name_lower.startswith(blocked.lower()):
            return True
    # Auto-detect other abliterated/uncensored models
    if "abliterated" in name_lower or "uncensored" in name_lower:
        return True
    return False

_TEXT_TOOL_FORMAT = """
## Tool Calling Format (IMPORTANT — you MUST follow this EXACTLY)
You have access to the following tools. To call a tool, write EXACTLY this format on its own lines:

Action: <tool_name>
Action Input: <JSON arguments>

Then STOP and wait for the Observation. Do NOT write the observation yourself.

After receiving the observation, continue with another Thought, or provide your final answer:
Final Answer: <your complete response>

### Available Tools:
{tool_list}

### Example:
Thought: I need to write a Python file.
Action: write_file
Action Input: {{"path": "hello.py", "content": "print('hello world')"}}

[You will receive an Observation with the result]

Thought: The file was written successfully.
Final Answer: I created hello.py with a hello world script.
"""

# ─── Reflection prompt ────────────────────────────────────────────────────────
_REFLECTION_SYSTEM = """\
You are reflecting on a completed task to extract lessons for future runs.
Be concise and specific. Output exactly 3 bullet points:
- What worked: <one sentence>
- What failed or was slow: <one sentence, or 'Nothing significant'>
- Next time I will: <one concrete improvement>\
"""


class Agent:
    """Level 4 autonomous agent with planning, checkpointing, and self-improvement.

    Args:
        name: Human-readable agent name.
        role: One-line specialisation description.
        instructions: Detailed operating guidelines. Must not be empty.
        model: Ollama model identifier (default ``"llama3.1"``).
        tools: Python callables to expose as tools.
        temperature: Sampling temperature.
        num_ctx: Context window size in tokens.
        host: Optional Ollama server URL.
        memory: Optional :class:`MemoryStore` for persistent cross-run memory.
        max_turns: Hard cap on reasoning turns per ``run()`` call (default 25).
        stateful: If ``True``, history persists across successive ``run()`` calls.
        confirm_actions: Tool names that require human approval before execution.
        critic: Optional :class:`Critic` that reviews output before returning.
        max_critique_rounds: Max critic revision cycles (default 2).
        planner: Optional :class:`Planner` for decomposing goals and replanning.
        enable_checkpointing: Save state to disk after every tool call (default True).
        enable_reflection: Write a self-improvement lesson after each run (default True).
    """

    def __init__(
        self,
        name: str = "AssistantAgent",
        role: str = "General Assistant",
        instructions: str = (
            "You are a relentless, highly capable autonomous AI agent. When given a task or goal, you never take 'No' "
            "for an answer and will not stop until the job is completely finished. Proactively use all available tools, "
            "troubleshoot any errors independently, and deliver finished, verified results without making excuses."
        ),
        model: str = "deepseek-r1:8b",
        tools: Optional[List[Callable]] = None,
        temperature: float = 0.0,
        num_ctx: int = 8192,
        host: Optional[str] = None,
        memory: Optional[MemoryStore] = None,
        max_turns: int = 50,
        stateful: bool = False,
        confirm_actions: Optional[List[str]] = None,
        critic: Optional["Critic"] = None,  # type: ignore[name-defined]  # noqa: F821
        max_critique_rounds: int = 2,
        planner: Optional["Planner"] = None,  # type: ignore[name-defined]  # noqa: F821
        enable_checkpointing: bool = True,
        enable_reflection: bool = True,
        compress_after: int = 30,
    ) -> None:
        if not name.strip():
            raise AgentConfigError("Agent 'name' cannot be empty.")
        if not instructions.strip():
            raise AgentConfigError("Agent 'instructions' cannot be empty.")

        self.name = name
        self.role = role
        self.model = model
        self.temperature = temperature
        self.num_ctx = num_ctx
        self.max_turns = max_turns
        self.stateful = stateful
        self.memory = memory
        self.client = ollama.Client(host=host, timeout=600.0)
        self.confirm_actions: Set[str] = set(confirm_actions or [])
        self.critic = critic
        self.max_critique_rounds = max_critique_rounds
        self.planner = planner
        self.enable_checkpointing = enable_checkpointing
        self.enable_reflection = enable_reflection
        self.compress_after = compress_after
        self._checkpoint_mgr = CheckpointManager() if enable_checkpointing else None

        self._base_system_prompt = (
            f"You are {self.name}, specialized as a {self.role}.\n"
            f"Operating Guidelines:\n{instructions.strip()}\n\n"
            "CRITICAL DIRECTIVE: You are aggressive and relentless in accomplishing your goals. "
            "You WILL NOT take 'No' for an answer, and you WILL NOT stop prematurely. "
            "If a task is given to you, YOU MUST FINISH IT entirely to completion. "
            "Keep trying alternative approaches if you hit roadblocks until the task is definitively solved."
        )

        self.tools: Dict[str, Tool] = {}
        for fn in (tools or []):
            if isinstance(fn, Tool):
                self.tools[fn.name] = fn
            elif callable(fn):
                tool_obj = Tool(fn)
                self.tools[tool_obj.name] = tool_obj
            elif isinstance(fn, dict) and "name" in fn:
                # Handle dict or object representation if passed from API
                pass
        self.history: List[Dict[str, Any]] = []
        self.reset()

    # ──────────────────────────────────────────────────────────────────
    # System prompt
    # ──────────────────────────────────────────────────────────────────

    def _build_system_prompt(self, task: str = "") -> str:
        """Assemble full system prompt including memory, reflections, and ReAct format."""
        parts = [self._base_system_prompt]

        if self.memory:
            mem_ctx = self.memory.build_memory_context(query=task)
            if mem_ctx:
                parts.append(f"\n## Long-Term Memory\n{mem_ctx}")

            # Inject past self-improvement reflections
            reflections = self.memory.recall_facts(query="reflection", limit=3)
            if reflections:
                parts.append("\n## Self-Improvement Notes (from past runs)")
                for _, lesson in reflections:
                    parts.append(lesson)

        if self.tools:
            if _is_text_tool_model(self.model):
                # Text-based tool injection for models that can't use native tool calling
                tool_descriptions = []
                for tool_name, tool_obj in self.tools.items():
                    params = tool_obj.schema.get("function", {}).get("parameters", {})
                    props = params.get("properties", {})
                    required = params.get("required", [])
                    param_lines = []
                    for pname, pinfo in props.items():
                        req_marker = " (required)" if pname in required else " (optional)"
                        param_lines.append(f"    - {pname}: {pinfo.get('type', 'string')}{req_marker} — {pinfo.get('description', '')}")
                    params_str = "\n".join(param_lines) if param_lines else "    (no parameters)"
                    tool_descriptions.append(f"**{tool_name}**: {tool_obj.description}\n  Parameters:\n{params_str}")
                tool_list_str = "\n\n".join(tool_descriptions)
                parts.append(_TEXT_TOOL_FORMAT.format(tool_list=tool_list_str))
            else:
                parts.append(_REACT_INSTRUCTIONS)

        # Inject Distributed Cluster Node Awareness
        try:
            from ollama_agents.cluster import cluster_manager
            remote_nodes = [n for n in cluster_manager.nodes.values() if n.is_active and "localhost" not in n.host_url and "127.0.0.1" not in n.host_url]
            if remote_nodes:
                worker_lines = []
                for wn in remote_nodes:
                    models_str = ", ".join(wn.installed_models[:6]) or "None"
                    worker_lines.append(f"- Worker Node '{wn.name}' ({wn.host_url}): Models available: [{models_str}]")
                parts.append(
                    "\n## Connected Distributed Cluster Worker Nodes\n"
                    "You have active secondary worker laptops connected over the local network. "
                    "You can offload sub-tasks to these workers anytime by using the `delegate_subagent` tool with their installed models:\n"
                    + "\n".join(worker_lines) + "\n"
                )
        except Exception:
            pass

        return "\n".join(parts)

    # ──────────────────────────────────────────────────────────────────
    # State management
    # ──────────────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Reset conversation history to the initial system context."""
        self.history = [{"role": "system", "content": self._build_system_prompt()}]

    # ──────────────────────────────────────────────────────────────────
    # Response unwrapping
    # ──────────────────────────────────────────────────────────────────

    def _to_dict(self, obj: Any) -> Dict[str, Any]:
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            return obj.dict()
        if isinstance(obj, dict):
            return obj
        return {k: getattr(obj, k) for k in dir(obj) if not k.startswith("_")}

    def _extract_message(self, response: Any) -> Dict[str, Any]:
        if hasattr(response, "message"):
            return self._to_dict(response.message)
        if isinstance(response, dict) and "message" in response:
            return self._to_dict(response["message"])
        raise ValueError(f"Unexpected Ollama response shape: {type(response)}")

    def _parse_text_tool_calls(self, content: str) -> List[Dict[str, Any]]:
        """Fallback tool call extractor for models like llama3.1 that output JSON objects or code blocks."""
        import re
        import json

        calls = []
        if not content:
            return calls

        tool_names = set(self.tools.keys()) if self.tools else set()

        # 1. Parse full JSON objects with "name" and "parameters"/"arguments"
        decoder = json.JSONDecoder()
        pos = 0
        while pos < len(content):
            idx = content.find('{', pos)
            if idx == -1:
                break
            try:
                obj, end = decoder.raw_decode(content[idx:])
                pos = idx + end
                if isinstance(obj, dict) and "name" in obj:
                    fn_name = obj["name"]
                    if not tool_names or fn_name in tool_names:
                        fn_args = obj.get("parameters") or obj.get("arguments") or {}
                        if not isinstance(fn_args, dict):
                            fn_args = {}
                        calls.append({"function": {"name": fn_name, "arguments": fn_args}})
            except Exception:
                pos = idx + 1

        if not calls:
            # 2. XML <tool_call> block fallback (commonly used by Qwen/Hermes models)
            xml_blocks = re.findall(r"<tool_call>\s*([\s\S]*?)\s*(?:</tool_call>|$)", content)
            for block in xml_blocks:
                try:
                    data = json.loads(block.strip())
                    if isinstance(data, dict) and "name" in data:
                        fn_name = data["name"]
                        if not tool_names or fn_name in tool_names:
                            fn_args = data.get("parameters") or data.get("arguments") or {}
                            if not isinstance(fn_args, dict):
                                fn_args = {}
                            calls.append({"function": {"name": fn_name, "arguments": fn_args}})
                except Exception:
                    pass

        if not calls:
            # 3. Code block fallback ```json ... ```
            code_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
            for block in code_blocks:
                try:
                    data = json.loads(block.strip())
                    if isinstance(data, dict) and "name" in data and data["name"] in self.tools:
                        fn_args = data.get("parameters") or data.get("arguments") or {}
                        calls.append({"function": {"name": data["name"], "arguments": fn_args}})
                except Exception:
                    pass

        if not calls:
            # 4. Action / Action Input regex format (classic ReAct)
            # e.g.: Action: write_file\nAction Input: {"path": "...", "content": "..."}
            action_match = re.search(r"Action\s*:\s*([a-zA-Z0-9_-]+)[\r\n]+Action\s*Input\s*:\s*([\s\S]+?)(?=(?:\nAction:|\nThought:|\nObservation:|$))", content, re.IGNORECASE)
            if action_match:
                fn_name = action_match.group(1).strip()
                raw_args = action_match.group(2).strip()
                if not tool_names or fn_name in tool_names:
                    try:
                        fn_args = json.loads(raw_args)
                    except Exception:
                        # Try to extract just the JSON object if model hallucinated trailing text
                        json_match = re.search(r'(\{[\s\S]*\})', raw_args)
                        if json_match:
                            try:
                                fn_args = json.loads(json_match.group(1))
                            except Exception:
                                fn_args = {"input": raw_args}
                        else:
                            fn_args = {"input": raw_args}
                    if not isinstance(fn_args, dict):
                        fn_args = {"input": fn_args}
                    calls.append({"function": {"name": fn_name, "arguments": fn_args}})

        return calls

    # ──────────────────────────────────────────────────────────────────
    # Human-in-the-loop
    # ──────────────────────────────────────────────────────────────────

    def _confirm_tool_call(self, fn_name: str, fn_args: Dict[str, Any]) -> bool:
        print(f"\n{'─'*52}")
        print(f"  [!] Human Approval Required")
        print(f"  Tool : {fn_name}")
        print(f"  Args : {fn_args}")
        print(f"{'─'*52}")
        try:
            answer = input("  Approve? (y/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        if answer not in ("y", "yes"):
            print("  [Denied] Skipping.\n")
            return False
        return True

    # ──────────────────────────────────────────────────────────────────
    # Tool execution
    # ──────────────────────────────────────────────────────────────────

    def _execute_tool(self, fn_name: str, fn_args: Dict[str, Any]) -> str:
        if fn_name not in self.tools:
            return f"[Error] Tool '{fn_name}' is not registered."
        if fn_name in self.confirm_actions:
            if not self._confirm_tool_call(fn_name, fn_args):
                return "[User denied this action. Try a different approach.]"
        try:
            return self.tools[fn_name].execute(**fn_args)
        except ToolExecutionError as e:
            logger.error("Tool failed permanently: %s", e)
            return (
                f"[Tool Failure] '{fn_name}' failed after all retries. "
                f"Reason: {e.cause}. Try a different approach."
            )

    # ──────────────────────────────────────────────────────────────────
    # Self-improvement reflection
    # ──────────────────────────────────────────────────────────────────

    def _reflect(
        self,
        task: str,
        outcome: str,
        tool_calls_made: List[str],
        errors: List[str],
    ) -> None:
        """Generate a self-improvement lesson and store it in memory."""
        if not self.memory:
            return
        try:
            tool_log = ", ".join(tool_calls_made[-10:]) or "none"
            error_log = "; ".join(errors[-5:]) or "none"
            prompt = (
                f"Task: {task[:300]}\n"
                f"Outcome: {outcome[:300]}\n"
                f"Tools used: {tool_log}\n"
                f"Errors: {error_log}"
            )
            response = self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": _REFLECTION_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                options={"temperature": 0.3, "num_ctx": 4096},
            )
            if hasattr(response, "message"):
                reflection = response.message.content or ""
            else:
                reflection = response.get("message", {}).get("content", "")

            if reflection.strip():
                key = f"reflection_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
                self.memory.save_fact(key, reflection.strip(), tags="reflection")
                self.memory.write_note(f"[{key}] {reflection.strip()}")
                logger.info("[%s] Reflection stored: %s", self.name, key)

                # Auto-refine skill blueprints based on self-improvement lessons
                if self.planner:
                    try:
                        self.planner.auto_refine_skills(reflection.strip())
                    except Exception as sk_err:
                        logger.warning("Skill auto-refine failed: %s", sk_err)
        except Exception as e:
            logger.warning("Reflection failed (non-critical): %s", e)

    # ──────────────────────────────────────────────────────────────────
    # Core run loop
    # ──────────────────────────────────────────────────────────────────

    def run(
        self,
        user_prompt: str,
        max_turns: Optional[int] = None,
        task_id: Optional[str] = None,
        on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
        images: Optional[List[str]] = None,
    ) -> str:
        """Execute the ReAct loop until Final Answer or max_turns.

        Args:
            user_prompt: The task or goal for this agent.
            max_turns: Override instance max_turns for this call.
            task_id: Unique ID for checkpointing. If a checkpoint exists with
                     this ID, the run resumes from where it left off. On
                     successful completion the checkpoint is deleted.
            on_event: Optional streaming callback for UI events (tools, thoughts, tokens).
            images: Optional list of base64-encoded image strings for multimodal vision tasks.

        Returns:
            The agent's final answer string.

        Raises:
            MaxTurnsExceeded: If the turn limit is reached. The checkpoint
                              is kept so the caller can resume.
        """
        limit = max_turns if max_turns is not None else self.max_turns

        def emit(evt_type: str, data: Any) -> None:
            if on_event:
                try:
                    on_event({"type": evt_type, "data": data})
                except Exception:
                    pass

        # ── Tracking state ────────────────────────────────────────────
        completed_steps: List[str] = []
        remaining_steps: List[str] = []
        tool_calls_made: List[str] = []
        errors: List[str] = []
        start_turn = 0

        # ── Checkpoint restore ────────────────────────────────────────
        checkpoint: Optional[CheckpointState] = None
        if task_id and self._checkpoint_mgr:
            checkpoint = self._checkpoint_mgr.load(task_id)

        if checkpoint:
            print(f"\n[Resume] Restoring checkpoint '{task_id}' from turn {checkpoint.turn}...")
            self.history = checkpoint.history
            completed_steps = checkpoint.completed_steps
            remaining_steps = checkpoint.remaining_steps
            tool_calls_made = checkpoint.tool_calls_made
            errors = checkpoint.errors
            start_turn = checkpoint.turn
        else:
            # Fresh start: Ensure Skill file exists BEFORE doing anything (even before planning)
            from ollama_agents.skills import SkillRegistry
            skill_reg = SkillRegistry()
            skill_reg.ensure_skill_for_goal(user_prompt, model=self.model)

            if not self.stateful:
                self.history = [
                    {"role": "system", "content": self._build_system_prompt(task=user_prompt)}
                ]
            user_msg: Dict[str, Any] = {"role": "user", "content": user_prompt}
            if images:
                user_msg["images"] = images
            self.history.append(user_msg)

            # ── Planner: decompose goal into steps ────────────────────
            if self.planner:
                remaining_steps = self.planner.decompose(user_prompt)
                if remaining_steps:
                    step_list = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(remaining_steps))
                    logger.info("[%s] Plan:\n%s", self.name, step_list)
                    self.history.append({
                        "role": "user",
                        "content": (
                            f"Here is your execution plan:\n{step_list}\n\n"
                            f"Follow these steps in order."
                        ),
                    })

        # Safeguard: Ensure history ALWAYS contains at least one valid non-empty user message
        # to prevent model backend errors: "no user query found in messages (status code: 500)"
        has_user_query = any(
            m.get("role") == "user" and bool(str(m.get("content", "")).strip())
            for m in self.history
        )
        if not has_user_query:
            logger.warning("[%s] No valid user message in history. Injecting task prompt.", self.name)
            self.history.append({"role": "user", "content": user_prompt or "Execute the requested task."})

        # For text-tool models (abliterated/uncensored), tools are described in the system
        # prompt as text. Don't pass native tool schemas — use text parsing instead.
        use_native_tools = self.tools and not _is_text_tool_model(self.model)
        tool_schemas = [t.schema for t in self.tools.values()] if use_native_tools else None
        options = {"temperature": self.temperature, "num_ctx": self.num_ctx}
        last_content = ""

        # ── Helper: save checkpoint ───────────────────────────────────
        def _save_cp(turn: int) -> None:
            if task_id and self._checkpoint_mgr:
                self._checkpoint_mgr.save(CheckpointState(
                    task_id=task_id,
                    task=user_prompt,
                    agent_name=self.name,
                    turn=turn,
                    history=self.history,
                    completed_steps=completed_steps,
                    remaining_steps=remaining_steps,
                    tool_calls_made=tool_calls_made,
                    errors=errors,
                ))

        # ── Main loop ─────────────────────────────────────────────────
        for turn in range(start_turn, limit):
            logger.debug("[%s] Turn %d/%d", self.name, turn + 1, limit)

            # ── Context compression ────────────────────────────────────
            if len(self.history) > self.compress_after:
                self._compress_history()

            try:
                response = self.client.chat(
                    model=self.model,
                    messages=self.history,
                    tools=tool_schemas if tool_schemas else None,
                    options=options,
                )
            except ollama.ResponseError as err:
                err_str = str(err).lower()
                if (
                    "does not support tools" in err_str
                    or "xml syntax error" in err_str
                    or "unexpected eof" in err_str
                    or "no user query found" in err_str
                    or err.status_code in (400, 500)
                ):
                    # Model/Ollama failed parsing native tools via XML/schema - fall back to sanitized text prompt tools
                    logger.warning("[%s] Native tool error (%s). Retrying chat with sanitized history...", self.name, err)
                    
                    # Convert role 'tool' to 'user' so non-native model endpoints don't reject the payload
                    fallback_history = []
                    for m in self.history:
                        fm = dict(m)
                        if fm.get("role") == "tool":
                            fm["role"] = "user"
                            fm["content"] = f"[Tool Result]: {fm.get('content', '')}"
                        elif fm.get("role") == "assistant" and not str(fm.get("content", "")).strip():
                            fm["content"] = f"Thought: {fm.get('thinking', 'analyzing...')}"
                        fallback_history.append(fm)
                        
                    # Ensure at least one valid user query exists
                    if not any(m.get("role") == "user" and bool(str(m.get("content", "")).strip()) for m in fallback_history):
                        fallback_history.append({"role": "user", "content": user_prompt or "Proceed with task."})
                        
                    try:
                        response = self.client.chat(
                            model=self.model,
                            messages=fallback_history,
                            options=options,
                        )
                    except Exception as fallback_err:
                        logger.error("[%s] Fallback chat failed: %s", self.name, fallback_err)
                        raise fallback_err
                else:
                    raise err
            except Exception as generic_err:
                # Catch timeouts and other httpx errors — retry without tools as last resort
                err_str = str(generic_err).lower()
                if "timed out" in err_str or "timeout" in err_str or "readtimeout" in err_str:
                    if tool_schemas:
                        logger.warning("[%s] Timeout with tools enabled. Retrying without tools...", self.name)
                        try:
                            response = self.client.chat(
                                model=self.model,
                                messages=self.history,
                                options=options,
                            )
                        except Exception:
                            raise generic_err
                    else:
                        raise generic_err
                else:
                    raise generic_err

            msg = self._extract_message(response)

            # Smart fallback: if model returned completely empty with tools, retry without tools
            msg_content = (msg.get("content") or "").strip()
            msg_tools = msg.get("tool_calls") or []
            if not msg_content and not msg_tools and tool_schemas:
                logger.warning("[%s] Empty response with tools enabled. Retrying without tools (chat-only mode)...", self.name)
                try:
                    response_fallback = self.client.chat(
                        model=self.model,
                        messages=self.history,
                        options=options,
                    )
                    msg = self._extract_message(response_fallback)
                except Exception as fb_err:
                    logger.warning("[%s] Chat-only fallback also failed: %s", self.name, fb_err)

            self.history.append(msg)

            content: str = msg.get("content") or ""
            tool_calls_list: List[Any] = msg.get("tool_calls") or []
            last_content = content

            # ── Strip hallucinated tool outputs from model text ────────
            # Some models (e.g. DeepSeek) hallucinate both the tool call AND
            # a fake tool response in the same text output. Strip the fake
            # response so the real tool execution result is used instead.
            import re as _re
            if any(marker in content for marker in [
                "tool\u2581outputs\u2581begin",
                "tool_outputs_begin",
            ]):
                content = _re.sub(
                    r'<[^>]*?tool\u2581outputs\u2581begin[^>]*?>[\s\S]*?<[^>]*?tool\u2581outputs\u2581end[^>]*?>',
                    '', content
                )
                content = _re.sub(
                    r'<[^>]*?tool_outputs_begin[^>]*?>[\s\S]*?<[^>]*?tool_outputs_end[^>]*?>',
                    '', content
                ).strip()
                # Also strip from history so the model doesn't see its own fake output
                if self.history and self.history[-1].get("content"):
                    self.history[-1]["content"] = content
                logger.warning("[%s] Stripped hallucinated tool output from model response.", self.name)

            # Fallback: if model (e.g. llama3.1) returned JSON text tool calls instead of native tool_calls
            if not tool_calls_list and content:
                text_calls = self._parse_text_tool_calls(content)
                if text_calls:
                    tool_calls_list = text_calls

            # If model returned <think> tags, emit thought event for real-time UI
            if "<think>" in content:
                import re
                think_match = re.search(r"<think>([\s\S]*?)(?:</think>|$)", content)
                if think_match:
                    thought_text = think_match.group(1).strip()
                    emit("thought", thought_text)

            # ── Goal-completion detection ──────────────────────────────
            if "Final Answer:" in content:
                answer = content.split("Final Answer:", 1)[-1].strip()
                logger.info("[%s] Final Answer at turn %d.", self.name, turn + 1)
                emit("answer", answer)

                # ── Critic review ──────────────────────────────────────
                if self.critic:
                    for rnd in range(self.max_critique_rounds):
                        result = self.critic.review(task=user_prompt, output=answer)
                        status = "Approved" if result.approved else "Needs revision"
                        print(f"\n  [Critic round {rnd+1}] {status} (score={result.score:.2f})")
                        if result.approved:
                            break
                        print(f"  Feedback: {result.feedback}")
                        if result.revised:
                            answer = result.revised
                            break
                        self.history.append({
                            "role": "user",
                            "content": (
                                f"Critic feedback:\n{result.feedback}\n"
                                "Revise and start with 'Final Answer:'"
                            ),
                        })
                        rev = self.client.chat(
                            model=self.model, messages=self.history,
                            tools=tool_schemas, options=options,
                        )
                        rev_msg = self._extract_message(rev)
                        self.history.append(rev_msg)
                        rev_content = rev_msg.get("content") or ""
                        if "Final Answer:" in rev_content:
                            answer = rev_content.split("Final Answer:", 1)[-1].strip()

                # ── Persist episode ────────────────────────────────────
                if self.memory:
                    self.memory.save_episode(task=user_prompt[:120], summary=answer[:400])

                # ── Self-improvement reflection ────────────────────────
                if self.enable_reflection:
                    self._reflect(user_prompt, answer, tool_calls_made, errors)

                # ── Delete checkpoint on success ───────────────────────
                if task_id and self._checkpoint_mgr:
                    self._checkpoint_mgr.delete(task_id)

                return answer

            # ── No tool calls and no Final Answer ─────────────────────
            if not tool_calls_list:
                stripped_content = content.strip()
                # If model emitted an intermediate 'Thought:' without calling a tool, give it up to 2 chances to call a tool
                is_thought = (
                    stripped_content.startswith("Thought:")
                    or stripped_content.startswith("Thought :")
                    or ("<think>" in stripped_content and "</think>" not in stripped_content)
                )
                thought_nudges = getattr(self, "_thought_nudges", 0)
                if is_thought and thought_nudges < 2 and (turn + 1 < limit):
                    self._thought_nudges = thought_nudges + 1
                    logger.info("[%s] Intermediate thought without tool call (nudge %d/2). Prompting...", self.name, self._thought_nudges)
                    self.history.append({
                        "role": "user",
                        "content": "Execute the tool call for your thought now, or provide 'Final Answer: <result>'."
                    })
                    continue
                self._thought_nudges = 0

                if stripped_content:
                    if self.memory:
                        self.memory.save_episode(task=user_prompt[:120], summary=stripped_content[:400])
                    if self.enable_reflection:
                        self._reflect(user_prompt, stripped_content, tool_calls_made, errors)
                    if task_id and self._checkpoint_mgr:
                        self._checkpoint_mgr.delete(task_id)
                    emit("answer", stripped_content)
                    return stripped_content

                # Empty response — nudge up to 2 times, then return graceful fallback
                empty_nudges = getattr(self, "_empty_nudges", 0)
                if empty_nudges < 2 and (turn + 1 < limit):
                    self._empty_nudges = empty_nudges + 1
                    logger.warning("[%s] Empty response from model (nudge %d/2). Nudging...", self.name, self._empty_nudges)
                    self.history.append({
                        "role": "user",
                        "content": (
                            "Please continue. When done, write 'Final Answer: <your answer>'"
                        ),
                    })
                    continue
                self._empty_nudges = 0
                msg_fail = "I did not receive a response from the model. Please retry or check that the model is loaded."
                emit("error", msg_fail)
                return msg_fail

            # ── Execute tool calls ─────────────────────────────────────
            for call in tool_calls_list:
                call_data = self._to_dict(call)
                func_data = self._to_dict(call_data.get("function") or {})
                fn_name: str = func_data.get("name") or ""
                fn_args: Dict[str, Any] = func_data.get("arguments") or {}

                logger.info("[%s] Tool: %s(%s)", self.name, fn_name, fn_args)
                tool_calls_made.append(fn_name)
                emit("tool_start", {"tool": fn_name, "args": fn_args})

                # Anti-hallucination loop guard:
                try:
                    call_sig = f"{fn_name}:{json.dumps(fn_args, sort_keys=True, default=str)}"
                except Exception:
                    call_sig = f"{fn_name}:{str(fn_args)}"
                recent_calls = getattr(self, "_recent_tool_signatures", [])
                recent_calls.append(call_sig)
                self._recent_tool_signatures = recent_calls[-10:]

                repeat_count = recent_calls.count(call_sig)
                if repeat_count >= 3:
                    # Hard stop: model is stuck in an infinite loop
                    logger.warning("[%s] Tool '%s' called 3+ times identically. Force-stopping agent.", self.name, fn_name)
                    fail_msg = (
                        f"Agent stopped: repeated identical tool call '{fn_name}' detected 3 times. "
                        "The tool may not be producing the expected result. Check tool output and try a different approach."
                    )
                    emit("error", fail_msg)
                    return fail_msg
                elif repeat_count >= 2:
                    output = (
                        f"[Tool Failure] Repeated identical tool call detected ({fn_name}). "
                        "You already called this tool with the same arguments. STOP repeating. "
                        "Verify the result using list_workspace_files or read_file, or provide 'Final Answer:' with your result."
                    )
                else:
                    output = self._execute_tool(fn_name, fn_args)

                self.history.append({"role": "tool", "content": output})
                emit("tool_end", {"tool": fn_name, "output": str(output)[:300]})

                # ── Replan on tool failure ─────────────────────────────
                is_failure = output.startswith("[Tool Failure]") or output.startswith("[Error]")
                if is_failure and self.planner and remaining_steps:
                    failure_reason = output[:200]
                    errors.append(f"{fn_name}: {failure_reason}")
                    logger.warning("[%s] Tool failed — triggering replan.", self.name)
                    try:
                        failed_step = remaining_steps[0] if remaining_steps else fn_name
                        revised = self.planner.replan(
                            goal=user_prompt,
                            completed_steps=completed_steps,
                            failed_step=failed_step,
                            failure_reason=failure_reason,
                            remaining_steps=remaining_steps,
                        )
                        if revised:
                            remaining_steps = revised
                            step_list = "\n".join(
                                f"  {i+1}. {s}" for i, s in enumerate(revised)
                            )
                            logger.info("[%s] Revised plan:\n%s", self.name, step_list)
                            self.history.append({
                                "role": "user",
                                "content": (
                                    f"The previous step failed. Updated plan:\n{step_list}\n"
                                    "Continue with the revised plan."
                                ),
                            })
                    except Exception as replan_err:
                        logger.warning("Replan failed (non-critical): %s", replan_err)

                # ── Save checkpoint after every tool call ──────────────
                _save_cp(turn + 1)

            # ── Advance plan tracking ──────────────────────────────────
            if remaining_steps and not is_failure:  # type: ignore[possibly-undefined]
                done = remaining_steps.pop(0)
                completed_steps.append(done)

        # ── Turn limit reached ─────────────────────────────────────────
        out = last_content.strip() if last_content and last_content.strip() else "I have reached the turn limit for this task."
        raise MaxTurnsExceeded(turns=limit, last_output=out)

    # ──────────────────────────────────────────────────────────────────
    # Context compression
    # ──────────────────────────────────────────────────────────────────

    def _compress_history(self) -> None:
        """Summarise the oldest half of messages to free up context space.

        Keeps the system prompt and the most recent half of messages intact.
        The older half is replaced with a single summary assistant message.
        Called automatically inside the run loop when len(history) > compress_after.
        """
        # Never compress if we have too few messages
        if len(self.history) <= 4:
            return

        system_msgs = [m for m in self.history if m.get("role") == "system"]
        non_system = [m for m in self.history if m.get("role") != "system"]

        # Split: compress the older half, keep the newer half
        split = len(non_system) // 2
        to_compress = non_system[:split]
        to_keep = non_system[split:]

        if not to_compress:
            return

        # Build a short transcript to summarise
        transcript_lines = []
        for m in to_compress:
            role = m.get("role", "")
            content = str(m.get("content") or "")[:300]
            transcript_lines.append(f"{role.upper()}: {content}")
        transcript = "\n".join(transcript_lines)

        logger.info(
            "[%s] Compressing %d messages (history=%d > threshold=%d).",
            self.name, len(to_compress), len(self.history), self.compress_after,
        )

        try:
            resp = self.client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Summarise the following agent conversation turns into a "
                            "single concise paragraph. Include all factual findings, "
                            "tool results, and decisions made. Be specific and dense — "
                            "this summary will replace the original turns."
                        ),
                    },
                    {"role": "user", "content": transcript},
                ],
                options={"temperature": 0.1, "num_ctx": 4096},
            )
            if hasattr(resp, "message"):
                summary = resp.message.content or ""
            else:
                summary = resp.get("message", {}).get("content", "")
        except Exception as e:
            logger.warning("Compression summarisation failed (%s) — skipping.", e)
            return

        summary_msg = {
            "role": "user",
            "content": f"[Compressed summary of earlier turns]: {summary.strip()}\n\nPlease continue working on the task based on this summary.",
        }
        self.history = system_msgs + [summary_msg] + to_keep
        logger.info("[%s] History compressed: %d -> %d messages.", self.name,
                    len(system_msgs) + len(non_system), len(self.history))

    # ──────────────────────────────────────────────────────────────────
    # Long-horizon: run_goal()
    # ──────────────────────────────────────────────────────────────────

    def run_goal(
        self,
        goal_id: str,
        registry: Optional["GoalRegistry"] = None,  # type: ignore[name-defined]  # noqa: F821
        max_turns: Optional[int] = None,
    ) -> str:
        """Run the next pending task of a long-horizon Goal.

        Each call to ``run_goal()`` works on exactly ONE task from the goal.
        Call it again (in the next session) to continue with the next task.
        The goal completes automatically when all tasks are done.
        """
        if registry is None:
            from ollama_agents.goal import GoalRegistry
            registry = GoalRegistry()

        goal = registry.load(goal_id)
        if goal is None:
            raise ValueError(f"Goal '{goal_id}' not found in registry.")

        if goal.status == "completed":
            return "Goal already completed."

        task = goal.next_task
        if task is None:
            return "Goal already completed — no pending tasks."

        # Increment session counter
        session_num = registry.increment_session(goal_id)
        registry.start_task(goal_id, task.id, session=session_num)

        print(f"\n{'='*60}")
        print(f"  Long-Horizon Goal: {goal.id}")
        print(f"  Session #{session_num}  |  Progress: {goal.progress_pct:.0f}%")
        print(f"  Task: {task.description}")
        print(f"{'='*60}\n")

        # Build a prompt that includes goal context
        goal_ctx = goal.context_for_next_session()
        full_prompt = f"{goal_ctx}\n\nYour task for this session:\n{task.description}"

        task_id_for_checkpoint = f"{goal_id}-{task.id}"

        try:
            output = self.run(
                user_prompt=full_prompt,
                max_turns=max_turns,
                task_id=task_id_for_checkpoint,
            )
            registry.complete_task(goal_id, task.id, output=output)

            # Reload to get updated progress
            updated_goal = registry.load(goal_id)
            if updated_goal:
                pct = updated_goal.progress_pct
                remaining = len(updated_goal.pending_tasks)
                print(f"\n  Task complete! Goal progress: {pct:.0f}%")
                if remaining > 0:
                    next_t = updated_goal.next_task
                    print(f"  Next session will run: '{next_t.description if next_t else '?'}'")
                else:
                    print(f"  All tasks complete! Goal '{goal_id}' is DONE.")
            return output

        except MaxTurnsExceeded as e:
            # Mark as in_progress (not failed), checkpoint is kept
            logger.warning(
                "[%s] MaxTurnsExceeded on task '%s'. Checkpoint kept for resume.",
                self.name, task.id,
            )
            print(f"\n  [!] Turn limit hit. Re-run to continue from checkpoint.")
            return e.last_output or "(no output yet)"

    # ──────────────────────────────────────────────────────────────────
    # Async wrapper
    # ──────────────────────────────────────────────────────────────────

    async def arun(
        self,
        user_prompt: str,
        max_turns: Optional[int] = None,
        task_id: Optional[str] = None,
    ) -> str:
        """Async wrapper around :meth:`run` for use in async contexts."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.run, user_prompt, max_turns, task_id)

    # ──────────────────────────────────────────────────────────────────
    # Dunder helpers
    # ──────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"Agent(name={self.name!r}, model={self.model!r}, "
            f"tools={list(self.tools)}, max_turns={self.max_turns}, "
            f"planner={'yes' if self.planner else 'no'}, "
            f"checkpointing={self.enable_checkpointing}, "
            f"reflection={self.enable_reflection})"
        )

