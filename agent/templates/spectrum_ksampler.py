"""Spectrum KSampler template — swap KSampler when Spectrum* exists in object_info."""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from . import stock_anima

TEMPLATE_ID = "spectrum_ksampler"
TEMPLATE_TITLE = "Spectrum KSampler"
REQUIRED_NODES: List[str] = ["SpectrumKSampler"]


def _pick_spectrum_class(object_info: Dict[str, Any], caps: Dict[str, Any]) -> Optional[str]:
    for name in ("SpectrumKSampler", "Spectrum_KSampler", "KSamplerSpectrum"):
        if name in object_info:
            return name
    for name in caps.get("spectrum_nodes") or []:
        if name in object_info:
            return name
    for name in sorted(object_info.keys()):
        if "spectrum" in name.lower() and "sampler" in name.lower():
            return name
    return None


def build(
    plan: Dict[str, Any],
    prompts: Dict[str, str],
    caps: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    caps = caps or {}
    object_info = kwargs.get("object_info") or {}

    def _fallback(reason: str) -> Dict[str, Any]:
        stock = stock_anima.build(plan, prompts, caps, **kwargs)
        stock["wanted_template"] = TEMPLATE_ID
        stock["template_used"] = stock_anima.TEMPLATE_ID
        stock["fallback_reason"] = reason
        return stock

    if not caps.get("has_spectrum") and not object_info:
        return _fallback("Spectrum sampler not discovered")

    spec_class = _pick_spectrum_class(object_info, caps) if object_info else None
    if not spec_class or spec_class not in object_info:
        return _fallback(
            "Spectrum sampler class_type not present in object_info; "
            "refusing to invent node"
        )

    stock = stock_anima.build(plan, prompts, caps, **kwargs)
    wf = copy.deepcopy(stock["workflow"])
    # Node "7" is KSampler in stock template — only swap class_type if
    # Spectrum accepts the same core inputs (seed/steps/cfg/model/…).
    node_def = object_info[spec_class]
    req = (node_def.get("input") or {}).get("required") or {}
    req_keys = set(req.keys())
    stock_keys = set(wf["7"]["inputs"].keys())
    # Need at least model + latent + positive + negative + steps
    needed = {"model", "positive", "negative", "latent_image", "steps"}
    # Some variants rename latent_image → latent
    if "latent" in req_keys and "latent_image" not in req_keys:
        needed = {"model", "positive", "negative", "latent", "steps"}
        if "latent_image" in wf["7"]["inputs"]:
            wf["7"]["inputs"]["latent"] = wf["7"]["inputs"].pop("latent_image")

    if not needed.issubset(req_keys | stock_keys):
        missing = sorted(needed - (req_keys | stock_keys))
        return _fallback(f"Spectrum sampler missing compatible inputs: {missing}")

    # Drop inputs Spectrum does not declare (required+optional)
    opt = (node_def.get("input") or {}).get("optional") or {}
    allowed = set(req.keys()) | set(opt.keys())
    if allowed:
        wf["7"]["inputs"] = {
            k: v for k, v in wf["7"]["inputs"].items() if k in allowed
        }
    wf["7"]["class_type"] = spec_class

    return {
        "workflow": wf,
        "template_id": TEMPLATE_ID,
        "template_used": TEMPLATE_ID,
        "wanted_template": TEMPLATE_ID,
        "fallback_reason": None,
        "meta": {"spectrum_class": spec_class},
    }
