"""Stock Anima API workflow: UNET + CLIP + VAE + KSampler (native nodes only)."""

from __future__ import annotations

import copy
import json
import random
from pathlib import Path
from typing import Any, Dict, Optional

TEMPLATE_ID = "stock_anima"
TEMPLATE_TITLE = "原生 Anima（UNET+CLIP+VAE）"
REQUIRED_NODES = [
    "UNETLoader",
    "CLIPLoader",
    "VAELoader",
    "EmptyLatentImage",
    "CLIPTextEncode",
    "KSampler",
    "VAEDecode",
    "SaveImage",
]

_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "workflows"
    / "anima_agent_api_template.json"
)

DEFAULTS = {
    "unet_name": "anima-aesthetic-v1.1.safetensors",
    "clip_name": "qwen_3_06b_base.safetensors",
    "clip_type": "stable_diffusion",
    "vae_name": "qwen_image_vae.safetensors",
    "width": 512,
    "height": 512,
    "batch_size": 1,
    "steps": 30,
    "cfg": 12.2,
    "sampler_name": "euler",
    "scheduler": "simple",
    "denoise": 1.0,
    "filename_prefix": "agent_anima",
}


def _inline_template() -> Dict[str, Any]:
    return {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": DEFAULTS["unet_name"],
                "weight_dtype": "default",
            },
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": DEFAULTS["clip_name"],
                "type": DEFAULTS["clip_type"],
                "device": "default",
            },
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": DEFAULTS["vae_name"]},
        },
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": DEFAULTS["width"],
                "height": DEFAULTS["height"],
                "batch_size": DEFAULTS["batch_size"],
            },
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "", "clip": ["2", 0]},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "", "clip": ["2", 0]},
        },
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 0,
                "steps": DEFAULTS["steps"],
                "cfg": DEFAULTS["cfg"],
                "sampler_name": DEFAULTS["sampler_name"],
                "scheduler": DEFAULTS["scheduler"],
                "denoise": DEFAULTS["denoise"],
                "model": ["1", 0],
                "positive": ["5", 0],
                "negative": ["6", 0],
                "latent_image": ["4", 0],
            },
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["7", 0], "vae": ["3", 0]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": DEFAULTS["filename_prefix"],
                "images": ["8", 0],
            },
        },
    }


def _load_template() -> Dict[str, Any]:
    if _TEMPLATE_PATH.is_file():
        with open(_TEMPLATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return _inline_template()


def build(
    plan: Dict[str, Any],
    prompts: Dict[str, str],
    caps: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Build stock Anima workflow. Always uses native node class_types."""
    del caps  # stock path does not require discovery
    wf = copy.deepcopy(_load_template())

    positive = prompts.get("positive") or ""
    negative = prompts.get("negative") or ""

    width = int(kwargs.get("width", plan.get("width", DEFAULTS["width"])))
    height = int(kwargs.get("height", plan.get("height", DEFAULTS["height"])))
    steps = int(kwargs.get("steps", plan.get("steps", DEFAULTS["steps"])))
    cfg = float(kwargs.get("cfg", plan.get("cfg", DEFAULTS["cfg"])))
    seed = kwargs.get("seed", plan.get("seed", -1))
    batch_size = int(kwargs.get("batch_size", plan.get("batch_size", 1)))
    unet_name = kwargs.get("unet_name") or DEFAULTS["unet_name"]
    clip_name = kwargs.get("clip_name") or DEFAULTS["clip_name"]
    vae_name = kwargs.get("vae_name") or DEFAULTS["vae_name"]
    sampler_name = kwargs.get("sampler_name") or DEFAULTS["sampler_name"]
    scheduler = kwargs.get("scheduler") or DEFAULTS["scheduler"]
    filename_prefix = kwargs.get("filename_prefix") or DEFAULTS["filename_prefix"]

    if seed is None or int(seed) < 0:
        seed = random.randint(0, 2**63 - 1)
    else:
        seed = int(seed)

    wf["1"]["inputs"]["unet_name"] = unet_name
    wf["2"]["inputs"]["clip_name"] = clip_name
    wf["2"]["inputs"]["type"] = DEFAULTS["clip_type"]
    wf["3"]["inputs"]["vae_name"] = vae_name
    wf["4"]["inputs"]["width"] = width
    wf["4"]["inputs"]["height"] = height
    wf["4"]["inputs"]["batch_size"] = max(1, batch_size)
    wf["5"]["inputs"]["text"] = positive
    wf["6"]["inputs"]["text"] = negative
    wf["7"]["inputs"]["seed"] = seed
    wf["7"]["inputs"]["steps"] = steps
    wf["7"]["inputs"]["cfg"] = cfg
    wf["7"]["inputs"]["sampler_name"] = sampler_name
    wf["7"]["inputs"]["scheduler"] = scheduler
    wf["9"]["inputs"]["filename_prefix"] = filename_prefix

    return {
        "workflow": wf,
        "template_id": TEMPLATE_ID,
        "template_used": TEMPLATE_ID,
        "wanted_template": TEMPLATE_ID,
        "fallback_reason": None,
        "meta": {"seed": seed},
    }
