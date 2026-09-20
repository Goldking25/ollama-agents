"""SD WebUI Forge Image Generation Tool for Ollama Agents.

Integrates with local Automatic1111 / SD WebUI Forge API endpoint (default: http://127.0.0.1:7860).
Allows agents to generate images, edit images (img2img), and create visual assets.
"""

import base64
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

WORKSPACE_IMAGES_DIR = Path.home() / "ollama_workspace" / "images"

def generate_image_sd_forge(
    prompt: str,
    negative_prompt: str = "blurry, low quality, distorted, bad anatomy",
    width: int = 512,
    height: int = 512,
    steps: int = 5,
    api_url: str = "http://127.0.0.1:7860"
) -> str:
    """Generate an image using local Stable Diffusion WebUI Forge API and save it to the workspace.

    Args:
        prompt: Positive text prompt describing the desired image (e.g. 'a futuristic cybernetic robot portrait, 8k, detailed').
        negative_prompt: What to avoid in the image (default 'blurry, low quality, distorted, bad anatomy').
        width: Image width in pixels (default 512).
        height: Image height in pixels (default 512).
        steps: Inference sampling steps (default 20).
        api_url: Base URL of running SD WebUI Forge API (default 'http://127.0.0.1:7860').
    """
    try:
        import httpx
    except ImportError:
        return "Error: httpx library is required for SD Forge integration. Run `pip install httpx`."

    endpoint = f"{api_url.rstrip('/')}/sdapi/v1/txt2img"
    payload = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
        "steps": steps,
        "cfg_scale": 7.0,
        "sampler_name": "Euler a",
    }

    try:
        logger.info("Sending txt2img request to SD WebUI Forge API at %s...", endpoint)
        resp = httpx.post(endpoint, json=payload, timeout=360.0)
        if resp.status_code != 200:
            return f"SD WebUI Forge API Error ({resp.status_code}): {resp.text[:300]}. Ensure SD WebUI Forge is launched with '--api'."

        data = resp.json()
        images = data.get("images", [])
        if not images:
            return "SD WebUI Forge API returned no images."

        WORKSPACE_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        img_bytes = base64.b64decode(images[0])
        
        from datetime import datetime, timezone
        filename = f"forge_gen_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.png"
        filepath = WORKSPACE_IMAGES_DIR / filename
        filepath.write_bytes(img_bytes)

        rel_url = f"/workspace/images/{filename}"
        return f"[SD WebUI Forge Image Generated Successfully]:\nSaved to local workspace: ~/ollama_workspace/images/{filename} ({len(img_bytes)} bytes)\n\n![Generated Image]({rel_url})"
    except Exception as e:
        return f"Error connecting to SD WebUI Forge API at '{api_url}': {type(e).__name__}: {e}. Make sure SD WebUI Forge is running with '--api' flag."


def edit_image_sd_forge(
    filepath: str,
    prompt: str,
    negative_prompt: str = "blurry, low quality, distorted, bad anatomy",
    denoising_strength: float = 0.75,
    cfg_scale: float = 1.0,
    distill_cfg: float = 1.0,
    steps: int = 5,
    api_url: str = "http://127.0.0.1:7860"
) -> str:
    """Edit or transform an existing uploaded image (img2img) using local SD WebUI Forge API.

    Args:
        filepath: Relative or absolute path to the input image file in workspace (e.g. 'uploads/my_photo.jpg').
        prompt: Positive text prompt describing the desired image transformation/edits.
        negative_prompt: What to avoid in the edited output (default 'blurry, low quality, distorted, bad anatomy').
        denoising_strength: How much to modify the original image (0.0 = unchanged, 1.0 = completely new image, default 0.75).
        cfg_scale: Classifier-free guidance scale (default 1.0).
        distill_cfg: Distillation CFG scale for Forge / FLUX models (default 1.0).
        steps: Inference sampling steps (default 5).
        api_url: Base URL of running SD WebUI Forge API (default 'http://127.0.0.1:7860').
    """
    try:
        import httpx
    except ImportError:
        return "Error: httpx library is required for SD Forge integration."

    # Resolve input image path
    input_path = Path.home() / "ollama_workspace" / filepath
    if not input_path.exists():
        input_path = Path(filepath)
    if not input_path.exists():
        return f"Image file not found: '{filepath}'. Upload the image first."

    try:
        img_b64 = base64.b64encode(input_path.read_bytes()).decode("utf-8")
    except Exception as e:
        return f"Error reading image '{filepath}': {e}"

    endpoint = f"{api_url.rstrip('/')}/sdapi/v1/img2img"
    payload = {
        "init_images": [img_b64],
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "denoising_strength": denoising_strength,
        "steps": steps,
        "cfg_scale": cfg_scale,
        "distill_cfg": distill_cfg,
        "distill_cfg_scale": distill_cfg,
        "sampler_name": "Euler a",
    }

    try:
        logger.info("Sending img2img edit request for '%s' to SD WebUI Forge API at %s...", filepath, endpoint)
        resp = httpx.post(endpoint, json=payload, timeout=300.0)
        if resp.status_code != 200:
            return (
                f"[SD WebUI Forge API Error {resp.status_code}]: {resp.text[:200]}.\n"
                "Please ensure SD WebUI Forge is launched with the '--api' command line flag."
            )

        data = resp.json()
        images = data.get("images", [])
        if not images:
            return "[SD WebUI Forge API Error]: API returned response but contained no edited images."

        WORKSPACE_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        out_bytes = base64.b64decode(images[0])

        from datetime import datetime, timezone
        filename = f"forge_edit_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.png"
        out_path = WORKSPACE_IMAGES_DIR / filename
        out_path.write_bytes(out_bytes)

        rel_url = f"/workspace/images/{filename}"
        return f"[SD WebUI Forge Image Edited Successfully]:\nSaved edited image to: ~/ollama_workspace/images/{filename} ({len(out_bytes)} bytes)\n\n![Edited Image]({rel_url})"
    except Exception as e:
        return (
            f"[SD WebUI Forge API Offline]: Could not connect to SD WebUI service at '{api_url}'.\n"
            f"Details: {type(e).__name__}: {e}.\n\n"
            "To use AI Diffusion image editing:\n"
            "1. Start SD WebUI Forge / Automatic1111 with the '--api' flag enabled.\n"
            "2. Ensure the web UI server is listening at http://127.0.0.1:7860."
        )

# Alias function wrapper for models calling 'edit_image' instead of 'edit_image_sd_forge'
def edit_image(
    filepath: str,
    prompt: str,
    negative_prompt: str = "blurry, low quality, distorted, bad anatomy",
    denoising_strength: float = 0.75,
    cfg_scale: float = 1.0,
    distill_cfg: float = 1.0,
    steps: int = 5,
    api_url: str = "http://127.0.0.1:7860"
) -> str:
    """Edit or transform an existing uploaded image (img2img) using local SD WebUI Forge API."""
    return edit_image_sd_forge(
        filepath=filepath,
        prompt=prompt,
        negative_prompt=negative_prompt,
        denoising_strength=denoising_strength,
        cfg_scale=cfg_scale,
        distill_cfg=distill_cfg,
        steps=steps,
        api_url=api_url
    )
