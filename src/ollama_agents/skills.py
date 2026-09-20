"""Skills & Capabilities Engine for Ollama Agents.

Provides persistent, reusable skill definitions that couple specialized domain prompts,
required tool suites, and target sub-agent models.
Supports self-improvement updates so agents can evolve skill definitions over time.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

_SKILLS_DIR = Path.home() / ".ollama_agents" / "skills"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Skill:
    """A reusable capability blueprint coupling instructions, tools, and model preferences."""
    name: str
    description: str
    instructions: str
    required_tools: List[str] = field(default_factory=list)
    preferred_model: str = "deepseek-r1:8b"
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    version: int = 1
    execution_count: int = 0
    refinements: List[str] = field(default_factory=list)


class SkillRegistry:
    """Manages creation, persistence, retrieval, and self-improvement refinement of Skills."""

    def __init__(self) -> None:
        _SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        self._seed_default_skills()

    def _path(self, skill_name: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in skill_name).lower()
        return _SKILLS_DIR / f"{safe}.json"

    def _seed_default_skills(self) -> None:
        """Seed initial default skills if not present."""
        defaults = [
            Skill(
                name="FinancialAnalysisSkill",
                description="Fetch real-time stock market data, analyze financials, and summarize news.",
                instructions="Use get_realtime_market_quote for stock prices. Use web_search for financial news and analyst ratings.",
                required_tools=["get_realtime_market_quote", "web_search"],
                preferred_model="deepseek-r1:8b"
            ),
            Skill(
                name="PythonCodingSkill",
                description="Write, execute, and debug Python scripts safely in a sandbox.",
                instructions="Write clean Python code. Use run_python or write_file to save scripts into workspace. Verify execution outputs.",
                required_tools=["run_python", "write_file", "read_file"],
                preferred_model="huihui_ai/qwen2.5-abliterate:7b-instruct"
            ),
            Skill(
                name="RAGKnowledgeSkill",
                description="Embed and query documents from long-term vector memory.",
                instructions="Use rag_add_knowledge to store important findings into vector memory. Use rag_search to perform semantic retrieval.",
                required_tools=["rag_add_knowledge", "rag_search"],
                preferred_model="deepseek-r1:8b"
            ),
            Skill(
                name="SubAgentDelegationSkill",
                description="Delegate specialized tasks to dedicated sub-agent models.",
                instructions="Use delegate_subagent to spawn specialized sub-agents (e.g. Coder, Researcher) with dedicated Ollama models.",
                required_tools=["delegate_subagent"],
                preferred_model="llama3.1:latest"
            )
        ]
        for s in defaults:
            path = self._path(s.name)
            if not path.exists():
                self.save(s)

    def save(self, skill: Skill) -> None:
        skill.updated_at = _now()
        data = asdict(skill)
        self._path(skill.name).write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.debug("Skill saved: '%s' (v%d)", skill.name, skill.version)

    def load(self, skill_name: str) -> Optional[Skill]:
        path = self._path(skill_name)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Skill(**data)
        except Exception as e:
            logger.error("Failed to load skill '%s': %s", skill_name, e)
            return None

    def list_skills(self) -> List[Skill]:
        skills = []
        for path in sorted(_SKILLS_DIR.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                skills.append(Skill(**data))
            except Exception:
                pass
        return skills

    def ensure_skill_for_goal(self, goal: str, model: str = "deepseek-r1:8b") -> Skill:
        """Check if a matching skill file exists for *goal*; if not, generate & create a new skill file before planning starts."""
        goal_lower = goal.lower().strip()

        # Skip skill generation entirely for short conversational greetings / casual messages
        conversational_words = {"hello", "hi", "hey", "greetings", "good morning", "good evening", "thanks", "thank you", "who are you"}
        if len(goal_lower.split()) <= 3 and any(w in goal_lower for w in conversational_words):
            return Skill(
                name="ConversationalSkill",
                description="General conversational response",
                instructions="Respond politely to conversational greetings or casual queries.",
                required_tools=[],
                preferred_model=model,
            )

        skills = self.list_skills()

        # Check if an existing skill matches the goal keywords or required tools
        for skill in skills:
            if any(tool.lower() in goal_lower for tool in skill.required_tools) or skill.name.lower() in goal_lower:
                logger.info("Found existing skill '%s' for goal.", skill.name)
                return skill

        # No skill file exists for this specific goal -> Invoke Skill Generator
        logger.info("[Skill Generator] No existing skill file found for goal. Generating new skill file before planning...")
        import re
        words = [w.capitalize() for w in re.findall(r"\w+", goal)[:3]]
        skill_name = "".join(words) + "Skill" if words else "CustomGoalSkill"

        # Attempt LLM generation or structured fallback
        skill = None
        try:
            import ollama
            client = ollama.Client(timeout=4.0)
            prompt = (
                f"Goal: '{goal}'\n"
                "You are a Skill Generator. Generate a specialized Skill JSON definition for this goal.\n"
                "Output ONLY a valid JSON object matching this schema:\n"
                "{\n"
                f'  "name": "{skill_name}",\n'
                '  "description": "Short description of the skill",\n'
                '  "instructions": "Step-by-step guidance and tool usage instructions for this skill",\n'
                '  "required_tools": ["run_python", "write_file", "web_search"],\n'
                f'  "preferred_model": "{model}"\n'
                "}"
            )
            res = client.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.2, "num_ctx": 2048},
            )
            content = res.message.content if hasattr(res, "message") else res.get("message", {}).get("content", "")
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                skill = Skill(
                    name=data.get("name", skill_name),
                    description=data.get("description", f"Skill for: {goal[:60]}"),
                    instructions=data.get("instructions", f"Execute task: {goal}"),
                    required_tools=data.get("required_tools", ["run_python", "write_file", "web_search"]),
                    preferred_model=data.get("preferred_model", model),
                )
        except Exception as e:
            logger.warning("[Skill Generator] LLM generation fallback: %s", e)

        if not skill:
            skill = Skill(
                name=skill_name,
                description=f"Generated skill for: {goal[:60]}",
                instructions=f"Analyze requirements, select appropriate tools, and execute task: {goal}",
                required_tools=["run_python", "write_file", "web_search"],
                preferred_model=model,
            )

        self.save(skill)
        logger.info("[Skill Generator] Created & saved new skill file: '%s.json'", skill.name)
        return skill

    def refine_skill(self, skill_name: str, lesson_learned: str, new_instruction: str = "") -> Optional[Skill]:
        """Self-improvement update: refine a skill definition based on runtime experience."""
        skill = self.load(skill_name)
        if not skill:
            return None

        skill.version += 1
        skill.execution_count += 1
        skill.refinements.append(f"[{_now()}] {lesson_learned}")

        if new_instruction.strip():
            skill.instructions += f"\n- Self-Improvement Note (v{skill.version}): {new_instruction.strip()}"

        self.save(skill)
        logger.info("Skill '%s' refined to v%d with new self-improvement lesson.", skill_name, skill.version)
        return skill
