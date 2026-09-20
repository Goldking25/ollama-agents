"""ComfyUI Video & Image Generation Tool for Ollama Agents.

Integrates with local ComfyUI API endpoint (default: http://127.0.0.1:8000).
Allows agents to queue video generation prompts and fetch generated video/animated WEBP outputs into the safe workspace (~/ollama_workspace/videos/).
"""

import json
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

WORKSPACE_VIDEOS_DIR = Path.home() / "ollama_workspace" / "videos"

def generate_video_comfyui(
    prompt: str,
    negative_prompt: str = "blurry, low quality, distorted, static, jittery",
    width: int = 512,
    height: int = 512,
    frames: int = 16,
    fps: int = 8,
    api_url: str = "http://127.0.0.1:8000",
    workflow_json: Optional[str] = None
) -> str:
    """Generate a video using local ComfyUI API endpoint and save the output MP4/GIF to the workspace.

    Args:
        prompt: Text prompt describing the desired video scene and motion (e.g. 'a cinematic drone shot of a glowing futuristic neon city with flying cars').
        negative_prompt: What to avoid in the video (default 'blurry, low quality, distorted, static, jittery').
        width: Video width in pixels (default 512).
        height: Video height in pixels (default 512).
        frames: Number of video frames to render (default 16).
        fps: Frames per second for output video playback (default 8).
        api_url: Base URL of running local ComfyUI instance (default 'http://127.0.0.1:8000').
        workflow_json: Optional custom API prompt JSON payload string. If not provided, a standard video generation workflow payload is sent.
    """
    try:
        import httpx
    except ImportError:
        return "Error: httpx library is required for ComfyUI integration. Run `pip install httpx`."

    base = api_url.rstrip('/')
    prompt_endpoint = f"{base}/prompt"
    history_endpoint = f"{base}/history"
    view_endpoint = f"{base}/view"

    # Default API Prompt format for ComfyUI
    if workflow_json:
        try:
            payload = json.loads(workflow_json)
        except Exception as e:
            return f"Error parsing provided workflow_json: {e}"
    else:
        # Standard video generation workflow prompt structure
        payload = {
            "prompt": {
                "3": {
                    "class_type": "KSampler",
                    "inputs": {
                        "cfg": 6.0,
                        "denoise": 1.0,
                        "latent_image": ["5", 0],
                        "model": ["4", 0],
                        "negative": ["7", 0],
                        "positive": ["6", 0],
                        "sampler_name": "euler",
                        "scheduler": "normal",
                        "seed": int(time.time()),
                        "steps": 20
                    }
                },
                "4": {
                    "class_type": "CheckpointLoaderSimple",
                    "inputs": {
                        "ckpt_name": "v1-5-pruned-emaonly.safetensors"
                    }
                },
                "5": {
                    "class_type": "EmptyLatentImage",
                    "inputs": {
                        "batch_size": frames,
                        "height": height,
                        "width": width
                    }
                },
                "6": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {
                        "clip": ["4", 1],
                        "text": prompt
                    }
                },
                "7": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {
                        "clip": ["4", 1],
                        "text": negative_prompt
                    }
                },
                "8": {
                    "class_type": "VAEDecode",
                    "inputs": {
                        "samples": ["3", 0],
                        "vae": ["4", 2]
                    }
                },
                "9": {
                    "class_type": "VHS_VideoCombine",
                    "inputs": {
                        "images": ["8", 0],
                        "frame_rate": fps,
                        "loop_count": 0,
                        "filename_prefix": "comfy_video",
                        "format": "video/h264-mp4"
                    }
                }
            }
        }

    try:
        logger.info("Submitting video generation prompt to ComfyUI at %s...", prompt_endpoint)
        resp = httpx.post(prompt_endpoint, json=payload, timeout=30.0)
        if resp.status_code != 200:
            return f"ComfyUI API Error ({resp.status_code}): {resp.text[:300]}. Ensure ComfyUI is running at '{api_url}'."

        res_data = resp.json()
        prompt_id = res_data.get("prompt_id")
        if not prompt_id:
            return f"ComfyUI response did not return a prompt_id: {res_data}"

        logger.info("ComfyUI prompt queued with ID: %s. Waiting for rendering to complete...", prompt_id)

        # Poll history endpoint for output video completion (up to 360 seconds / 6 minutes)
        start_time = time.time()
        output_file_info = None

        while time.time() - start_time < 360.0:
            time.sleep(3.0)
            hist_resp = httpx.get(f"{history_endpoint}/{prompt_id}", timeout=10.0)
            if hist_resp.status_code == 200:
                hist_data = hist_resp.json()
                if prompt_id in hist_data:
                    outputs = hist_data[prompt_id].get("outputs", {})
                    for node_id, node_out in outputs.items():
                        if "gifs" in node_out:
                            output_file_info = node_out["gifs"][0]
                            break
                        if "videos" in node_out:
                            output_file_info = node_out["videos"][0]
                            break
                        if "images" in node_out:
                            output_file_info = node_out["images"][0]
                            break
                    if output_file_info:
                        break

        if not output_file_info:
            return f"[ComfyUI Task Queued]: Prompt ID '{prompt_id}' was submitted to ComfyUI at {api_url}. Rendering is still in progress."

        # Fetch rendered file from ComfyUI /view endpoint
        filename = output_file_info.get("filename")
        subfolder = output_file_info.get("subfolder", "")
        file_type = output_file_info.get("type", "output")

        view_url = f"{view_endpoint}?filename={filename}&subfolder={subfolder}&type={file_type}"
        file_resp = httpx.get(view_url, timeout=60.0)

        if file_resp.status_code != 200:
            return f"Failed to download rendered video from ComfyUI: HTTP {file_resp.status_code}"

        WORKSPACE_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
        from datetime import datetime, timezone
        out_filename = f"comfy_vid_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{filename}"
        out_path = WORKSPACE_VIDEOS_DIR / out_filename
        out_path.write_bytes(file_resp.content)

        rel_url = f"/workspace/videos/{out_filename}"
        return f"[ComfyUI Video Generated Successfully]:\nSaved to local workspace: ~/ollama_workspace/videos/{out_filename} ({len(file_resp.content)} bytes)\n\n![Generated Video]({rel_url})"

    except Exception as e:
        return f"Error connecting to ComfyUI API at '{api_url}': {type(e).__name__}: {e}. Make sure ComfyUI Desktop is running on port 8000."
