"""Build ComfyUI API-format prompt dicts via pluggable templates."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from .templates import build_with_template, select_template, list_templates
from .templates.stock_anima import DEFAULTS, build as stock_build

# Re-export defaults for routes / nodes
__all__ = [
    "DEFAULTS",
    "build_workflow",
    "build_workflow_smart",
    "select_template",
    "list_templates",
    "workflow_to_json",
]


def build_workflow(
    positive: str,
    negative: str,
    *,
    width: int = 512,
    height: int = 512,
    steps: int = 30,
    cfg: float = 12.2,
    seed: int = -1,
    batch_size: int = 1,
    unet_name: Optional[str] = None,
    clip_name: Optional[str] = None,
    vae_name: Optional[str] = None,
    sampler_name: str = "euler",
    scheduler: str = "simple",
    filename_prefix: str = "agent_anima",
) -> Dict[str, Any]:
    """Backward-compatible stock Anima builder (API-format prompt dict only)."""
    plan = {
        "width": width,
        "height": height,
        "steps": steps,
        "cfg": cfg,
        "seed": seed,
        "batch_size": batch_size,
    }
    prompts = {"positive": positive or "", "negative": negative or ""}
    result = stock_build(
        plan,
        prompts,
        None,
        width=width,
        height=height,
        steps=steps,
        cfg=cfg,
        seed=seed,
        batch_size=batch_size,
        unet_name=unet_name,
        clip_name=clip_name,
        vae_name=vae_name,
        sampler_name=sampler_name,
        scheduler=scheduler,
        filename_prefix=filename_prefix,
    )
    return result["workflow"]


def build_workflow_smart(
    plan: Dict[str, Any],
    positive: str,
    negative: str,
    *,
    caps: Optional[Dict[str, Any]] = None,
    object_info: Optional[Dict[str, Any]] = None,
    template: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    steps: Optional[int] = None,
    cfg: Optional[float] = None,
    seed: Optional[int] = None,
    batch_size: Optional[int] = None,
    unet_name: Optional[str] = None,
    clip_name: Optional[str] = None,
    vae_name: Optional[str] = None,
    sampler_name: Optional[str] = None,
    scheduler: Optional[str] = None,
    filename_prefix: Optional[str] = None,
) -> Dict[str, Any]:
    """Select template from plan/caps and build. Returns full result dict."""
    kwargs: Dict[str, Any] = {}
    if width is not None:
        kwargs["width"] = width
    if height is not None:
        kwargs["height"] = height
    if steps is not None:
        kwargs["steps"] = steps
    if cfg is not None:
        kwargs["cfg"] = cfg
    if seed is not None:
        kwargs["seed"] = seed
    if batch_size is not None:
        kwargs["batch_size"] = batch_size
    if unet_name:
        kwargs["unet_name"] = unet_name
    if clip_name:
        kwargs["clip_name"] = clip_name
    if vae_name:
        kwargs["vae_name"] = vae_name
    if sampler_name:
        kwargs["sampler_name"] = sampler_name
    if scheduler:
        kwargs["scheduler"] = scheduler
    if filename_prefix:
        kwargs["filename_prefix"] = filename_prefix

    return build_with_template(
        plan,
        {"positive": positive or "", "negative": negative or ""},
        caps,
        object_info=object_info,
        template_id=template,
        **kwargs,
    )


def workflow_to_json(workflow: Dict[str, Any], indent: int = 2) -> str:
    return json.dumps(workflow, ensure_ascii=False, indent=indent)
