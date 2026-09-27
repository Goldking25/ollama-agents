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
    workflow_json: Optional[str] = None,
    init_image: Optional[str] = None,
    denoise: float = 0.75,
    ckpt_name: str = "ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors"
) -> str:
    """Generate a video using local ComfyUI API endpoint and save the output MP4/GIF to the workspace."""
    try:
        import httpx
    except ImportError:
        return "Error: httpx library is required for ComfyUI integration. Run `pip install httpx`."

    base = api_url.rstrip('/')
    prompt_endpoint = f"{base}/prompt"
    history_endpoint = f"{base}/history"
    view_endpoint = f"{base}/view"

    if workflow_json:
        try:
            payload = json.loads(workflow_json)
        except Exception as e:
            return f"Error parsing provided workflow_json: {e}"
    else:
        # Determine denoise and sampling steps for crisp, distortion-free output
        effective_denoise = float(denoise) if init_image else 1.0
        # If init_image is provided, default denoise to 0.65 to avoid destroying initial image structure
        if init_image and denoise == 1.0:
            effective_denoise = 0.65

        nodes = {
            "1": {
                "class_type": "UNETLoader",
                "inputs": {"unet_name": ckpt_name, "weight_dtype": "default"}
            },
            "2": {
                "class_type": "CLIPLoader",
                "inputs": {"clip_name": "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors", "type": "ltxv"}
            },
            "3": {
                "class_type": "VAELoader",
                "inputs": {"vae_name": "ltx-2.5-video-vae-bf16.safetensors"}
            },
            "4": {
                "class_type": "CLIPTextEncode",
                "inputs": {"clip": ["2", 0], "text": prompt}
            },
            "5": {
                "class_type": "CLIPTextEncode",
                "inputs": {"clip": ["2", 0], "text": negative_prompt}
            },
            "6": {
                "class_type": "LTXVConditioning",
                "inputs": {"positive": ["4", 0], "negative": ["5", 0], "frame_rate": float(fps)}
            },
            "7": {
                "class_type": "EmptyLTXVLatentVideo",
                "inputs": {"width": width, "height": height, "length": frames, "batch_size": 1}
            },
            "8": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["1", 0],
                    "positive": ["6", 0],
                    "negative": ["6", 1],
                    "latent_image": ["7", 0],
                    "seed": int(time.time()),
                    "steps": 20, # 20 steps prevents blurry noise & motion distortion
                    "cfg": 3.5,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": effective_denoise
                }
            },
            "9": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["8", 0], "vae": ["3", 0]}
            },
            "10": {
                "class_type": "VHS_VideoCombine",
                "inputs": {
                    "images": ["9", 0],
                    "frame_rate": fps,
                    "loop_count": 0,
                    "filename_prefix": "comfy_video",
                    "format": "video/h264-mp4",
                    "pingpong": False,
                    "save_output": True
                }
            }
        }

        # If init_image is specified, hook up LoadImage node
        if init_image:
            img_name = Path(init_image).name if "/" in init_image or "\\" in init_image else init_image
            nodes["11"] = {
                "class_type": "LoadImage",
                "inputs": {"image": img_name}
            }

        payload = {"prompt": nodes}

    try:
        logger.info("Submitting video generation prompt to ComfyUI at %s...", prompt_endpoint)
        resp = httpx.post(prompt_endpoint, json=payload, timeout=30.0)
        if resp.status_code != 200:
            return f"ComfyUI API Error ({resp.status_code}): {resp.text[:1000]}. Ensure ComfyUI is running at '{api_url}'."

        res_data = resp.json()
        prompt_id = res_data.get("prompt_id")
        if not prompt_id:
            return f"ComfyUI response did not return a prompt_id: {res_data}"

        logger.info("ComfyUI prompt queued with ID: %s. Waiting for rendering to complete...", prompt_id)

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
                    
                    # If it is in history, it is completely done (success or error).
                    # We break regardless of whether we found outputs, to avoid a 6-minute infinite loop.
                    break

        if not output_file_info:
            # Check if it's actually in history but failed
            hist_check = httpx.get(f"{history_endpoint}/{prompt_id}", timeout=10.0).json()
            if prompt_id in hist_check:
                status = hist_check[prompt_id].get("status", {})
                
                # Extract error from messages or dump the status
                messages = status.get("messages", [])
                error_texts = []
                for msg in messages:
                    if isinstance(msg, list) and len(msg) >= 2:
                        error_texts.append(str(msg[1]))
                    else:
                        error_texts.append(str(msg))
                        
                if error_texts:
                    error = " | ".join(error_texts)
                else:
                    error = str(status)
                    
                return f"ComfyUI generation failed. No video was output. Error: {error}"
            return f"[ComfyUI Task Queued]: Prompt ID '{prompt_id}' was submitted to ComfyUI at {api_url}. Rendering is still in progress."

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
