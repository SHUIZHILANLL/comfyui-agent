"""Anima Ref Adapter template — lock character identity from a reference image."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from . import stock_anima

TEMPLATE_ID = "anima_ref_adapter"
TEMPLATE_TITLE = "Anima Ref Adapter（参考图锁人物）"
REQUIRED_NODES: List[str] = [
    "UNETLoader",
    "CLIPLoader",
    "VAELoader",
    "LoadImage",
    "AnimaRefAdapter",
    "CLIPTextEncode",
    "EmptyLatentImage",
    "KSampler",
    "VAEDecode",
    "SaveImage",
]

DEFAULTS = {
    "unet_name": "anima-aesthetic-v1.1.safetensors",
    "clip_name": "qwen_3_06b_base.safetensors",
    "clip_type": "stable_diffusion",
    "vae_name": "qwen_image_vae.safetensors",
    "lora_name": "anima_ref_adapter_v2_r64.safetensors",
    "ref_guidance": 4.5,
    "correction": "apg",
    "strength": 1.0,
    "ref_end": 1.0,
    "ref_megapixels": 1.0,
    "width": 832,
    "height": 1216,
    "batch_size": 1,
    "steps": 30,
    "cfg": 4.5,
    "sampler_name": "euler",
    "scheduler": "simple",
    "denoise": 1.0,
    "filename_prefix": "agent_anima_ref",
}


def _fallback(plan, prompts, caps, reason: str, **kwargs) -> Dict[str, Any]:
    stock = stock_anima.build(plan, prompts, caps, **kwargs)
    stock["wanted_template"] = TEMPLATE_ID
    stock["template_used"] = stock_anima.TEMPLATE_ID
    stock["fallback_reason"] = reason
    return stock


def build(
    plan: Dict[str, Any],
    prompts: Dict[str, str],
    caps: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    caps = caps or {}
    object_info = kwargs.get("object_info") or {}

    if object_info and "AnimaRefAdapter" not in object_info:
        return _fallback(
            plan,
            prompts,
            caps,
            "AnimaRefAdapter not present in object_info",
            **kwargs,
        )
    if not caps.get("has_anima_ref_adapter") and (
        not object_info or "AnimaRefAdapter" not in object_info
    ):
        return _fallback(
            plan,
            prompts,
            caps,
            "Anima Ref Adapter not discovered",
            **kwargs,
        )

    ref_image = (
        kwargs.get("ref_image")
        or plan.get("ref_image")
        or ""
    )
    ref_image = str(ref_image).strip()
    if not ref_image:
        return _fallback(
            plan,
            prompts,
            caps,
            "ref_image required for anima_ref_adapter",
            **kwargs,
        )

    positive = prompts.get("positive") or ""
    negative = prompts.get("negative") or ""

    # Prefer 832x1216 / cfg 4.5 when size/cfg still look like stock defaults
    plan_w = int(plan.get("width") or 0)
    plan_h = int(plan.get("height") or 0)
    kw_w = kwargs.get("width")
    kw_h = kwargs.get("height")
    stock_w, stock_h = int(stock_anima.DEFAULTS["width"]), int(stock_anima.DEFAULTS["height"])
    looks_stock_size = (
        (kw_w is None or int(kw_w) == stock_w)
        and (kw_h is None or int(kw_h) == stock_h)
        and plan_w in (0, stock_w)
        and plan_h in (0, stock_h)
    )
    if looks_stock_size:
        width, height = int(DEFAULTS["width"]), int(DEFAULTS["height"])
    else:
        width = int(kw_w if kw_w is not None else (plan_w or DEFAULTS["width"]))
        height = int(kw_h if kw_h is not None else (plan_h or DEFAULTS["height"]))

    plan_cfg = plan.get("cfg")
    kw_cfg = kwargs.get("cfg")
    stock_cfg = float(stock_anima.DEFAULTS["cfg"])
    looks_stock_cfg = (
        (kw_cfg is None or float(kw_cfg) == stock_cfg)
        and (plan_cfg is None or float(plan_cfg) == stock_cfg)
    )
    cfg = float(DEFAULTS["cfg"] if looks_stock_cfg else (kw_cfg if kw_cfg is not None else plan_cfg))
    steps = int(kwargs.get("steps", plan.get("steps", DEFAULTS["steps"])))
    seed = kwargs.get("seed", plan.get("seed", -1))
    batch_size = int(kwargs.get("batch_size", plan.get("batch_size", 1)))
    unet_name = kwargs.get("unet_name") or DEFAULTS["unet_name"]
    clip_name = kwargs.get("clip_name") or DEFAULTS["clip_name"]
    vae_name = kwargs.get("vae_name") or DEFAULTS["vae_name"]
    sampler_name = kwargs.get("sampler_name") or DEFAULTS["sampler_name"]
    scheduler = kwargs.get("scheduler") or DEFAULTS["scheduler"]
    filename_prefix = kwargs.get("filename_prefix") or DEFAULTS["filename_prefix"]
    lora_name = kwargs.get("lora_name") or plan.get("ref_lora") or DEFAULTS["lora_name"]
    ref_guidance = float(
        kwargs.get("ref_guidance", plan.get("ref_guidance", DEFAULTS["ref_guidance"]))
    )
    correction = kwargs.get("correction") or plan.get("correction") or DEFAULTS["correction"]
    strength = float(kwargs.get("strength", plan.get("ref_strength", DEFAULTS["strength"])))
    ref_end = float(kwargs.get("ref_end", plan.get("ref_end", DEFAULTS["ref_end"])))
    ref_megapixels = float(
        kwargs.get("ref_megapixels", plan.get("ref_megapixels", DEFAULTS["ref_megapixels"]))
    )

    if seed is None or int(seed) < 0:
        seed = random.randint(0, 2**63 - 1)
    else:
        seed = int(seed)

    # API node ids (sample):
    # 1 UNET → 5 AnimaRefAdapter ← 3 VAE, 4 LoadImage
    # 2 CLIP → 6/7 Encode; 8 EmptyLatent; 9 KSampler(model from 5); 10 Decode; 11 Save
    wf: Dict[str, Any] = {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": unet_name, "weight_dtype": "default"},
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": clip_name,
                "type": DEFAULTS["clip_type"],
                "device": "default",
            },
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": vae_name},
        },
        "4": {
            "class_type": "LoadImage",
            "inputs": {"image": ref_image},
        },
        "5": {
            "class_type": "AnimaRefAdapter",
            "inputs": {
                "model": ["1", 0],
                "vae": ["3", 0],
                "image": ["4", 0],
                "lora_name": lora_name,
                "ref_guidance": ref_guidance,
                "correction": correction,
                "strength": strength,
                "ref_end": ref_end,
                "ref_megapixels": ref_megapixels,
            },
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": positive, "clip": ["2", 0]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative, "clip": ["2", 0]},
        },
        "8": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": width,
                "height": height,
                "batch_size": max(1, batch_size),
            },
        },
        "9": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": DEFAULTS["denoise"],
                "model": ["5", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["8", 0],
            },
        },
        "10": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["9", 0], "vae": ["3", 0]},
        },
        "11": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": filename_prefix,
                "images": ["10", 0],
            },
        },
    }

    return {
        "workflow": wf,
        "template_id": TEMPLATE_ID,
        "template_used": TEMPLATE_ID,
        "wanted_template": TEMPLATE_ID,
        "fallback_reason": None,
        "meta": {
            "seed": seed,
            "ref_image": ref_image,
            "lora_name": lora_name,
            "width": width,
            "height": height,
            "cfg": cfg,
        },
    }
