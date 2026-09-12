"""
Model Selector & Hugging Face Explorer helper for Planner.

Features:
1. Smart Model Selection: Evaluates local Ollama models and selects the best fit for task planning or execution (coding, reasoning, vision, general).
2. Hugging Face Search & Download Request: Searches Hugging Face GGUF models for specialized tasks, asking the user to approve adding new models via Ollama (`ollama run hf.co/...`).
"""

import logging
import urllib.request
import json
from typing import List, Dict, Optional, Tuple, Any
import ollama

logger = logging.getLogger(__name__)

# Capability priorities
MODEL_CAPABILITY_SCORES = {
    "deepseek-r1:8b": {"reasoning": 95, "coding": 90, "general": 90},
    "deepseek-r1:7b": {"reasoning": 92, "coding": 88, "general": 88},
    "deepseek-r1:latest": {"reasoning": 90, "coding": 88, "general": 88},
    "deepseek-coder-v2:16b": {"reasoning": 85, "coding": 98, "general": 85},
    "llama3.1:latest": {"reasoning": 85, "coding": 80, "general": 92},
    "llama3.2-vision:11b": {"reasoning": 80, "coding": 75, "general": 85, "vision": 95},
    "huihui_ai/qwen2.5-abliterate:7b-instruct": {"reasoning": 88, "coding": 85, "general": 88},
}

def get_installed_ollama_models() -> List[str]:
    """Get list of installed model names on local machine."""
    try:
        data = ollama.list()
        raw_models = getattr(data, "models", data.get("models", []))
        names = []
        for m in raw_models:
            n = getattr(m, "model", getattr(m, "name", None))
            if not n and isinstance(m, dict):
                n = m.get("model", m.get("name"))
            if n:
                names.append(str(n))
        return names
    except Exception as e:
        logger.error("Failed to list installed Ollama models: %s", e)
        return ["deepseek-r1:8b", "llama3.1:latest"]


def select_best_local_model(task_type: str = "reasoning", preferred: Optional[str] = None) -> str:
    """Select the highest-scoring installed local model for a given task type."""
    installed = get_installed_ollama_models()
    if not installed:
        return preferred or "deepseek-r1:8b"

    if preferred and preferred in installed:
        return preferred

    # Score installed models
    best_model = installed[0]
    highest_score = -1

    for m in installed:
        # Match base name
        m_lower = m.lower()
        score = 50  # default base score
        
        if "deepseek-r1" in m_lower:
            score += 40 if task_type == "reasoning" else 30
        elif "coder" in m_lower:
            score += 45 if task_type == "coding" else 20
        elif "llama3.1" in m_lower:
            score += 35 if task_type == "general" else 25
        elif "vision" in m_lower:
            score += 45 if task_type == "vision" else 10

        if score > highest_score:
            highest_score = score
            best_model = m

    logger.info("Selected best local model '%s' for task_type='%s'", best_model, task_type)
    return best_model


def search_huggingface_models(query: str, limit: int = 5) -> List[Dict[str, str]]:
    """Search Hugging Face Hub API for Ollama-compatible GGUF models matching query."""
    url = f"https://huggingface.co/api/models?search={urllib.parse.quote(query)}&filter=gguf&sort=downloads&direction=-1&limit={limit}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "OllamaAgents/0.6.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = []
            for item in data:
                model_id = item.get("id", "")
                downloads = item.get("downloads", 0)
                likes = item.get("likes", 0)
                results.append({
                    "id": model_id,
                    "ollama_tag": f"hf.co/{model_id}",
                    "downloads": downloads,
                    "likes": likes
                })
            return results
    except Exception as e:
        logger.error("Hugging Face API search error: %s", e)
        return []


def fetch_trending_hf_models(limit: int = 8) -> List[Dict[str, Any]]:
    """Fetch daily trending GGUF models sorted by recent activity/likes on Hugging Face Hub."""
    url = f"https://huggingface.co/api/models?filter=gguf&sort=trendingScore&direction=-1&limit={limit}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "OllamaAgents/0.6.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = []
            for item in data:
                model_id = item.get("id", "")
                results.append({
                    "id": model_id,
                    "ollama_tag": f"hf.co/{model_id}",
                    "downloads": item.get("downloads", 0),
                    "likes": item.get("likes", 0),
                    "pipeline_tag": item.get("pipeline_tag", "text-generation"),
                    "updated_at": str(item.get("lastModified", ""))[:10]
                })
            return results
    except Exception as e:
        logger.error("Failed to fetch trending Hugging Face models: %s", e)
        return []
