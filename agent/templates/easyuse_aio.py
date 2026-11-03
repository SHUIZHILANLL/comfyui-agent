"""EasyUse Anima AiO template — only uses class_types present in object_info.

If AiO wiring is uncertain (missing node or incomplete required inputs),
falls back to stock_anima and records wanted_template + fallback_reason.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from . import stock_anima

TEMPLATE_ID = "easyuse_aio"
TEMPLATE_TITLE = "EasyUse Anima AiO"
# Soft requirements: any of these is enough to *attempt*; exact id chosen at build time
REQUIRED_NODES: List[str] = ["EasyUseAnimaAIOGenerator"]

_AIO_CANDIDATES = (
    "EasyUseAnimaAIOGenerator",
    "EasyUseAnimaAIO",
)


def _pick_aio_class(object_info: Dict[str, Any]) -> Optional[str]:
    for name in _AIO_CANDIDATES:
        if name in object_info:
            return name
    # Any EasyUseAnima* with AIO in the name
    for name in sorted(object_info.keys()):
        if name.startswith("EasyUseAnima") and "AIO" in name.upper():
            return name
    return None


def _required_input_names(node_def: Dict[str, Any]) -> List[str]:
    req = (node_def.get("input") or {}).get("required") or {}
    return list(req.keys())


def _looks_safe_for_minimal(node_def: Dict[str, Any]) -> Tuple[bool, str]:
    """Heuristic: AiO is only 'safe' if required inputs are mostly scalars/strings
    we can fill from plan/prompts (no dangling MODEL/CLIP/CONDITIONING links).
    """
    req = (node_def.get("input") or {}).get("required") or {}
    hard_types = {
        "MODEL",
        "CLIP",
        "VAE",
        "CONDITIONING",
        "LATENT",
        "IMAGE",
        "MASK",
    }
    blockers = []
    for name, spec in req.items():
        # ComfyUI object_info: [type, opts] or [type]
        typ = spec[0] if isinstance(spec, (list, tuple)) and spec else None
        if isinstance(typ, str) and typ.upper() in hard_types:
            blockers.append(f"{name}:{typ}")
    if blockers:
        return False, "AiO required linked inputs: " + ", ".join(blockers)
    # Must at least accept some prompt-like field
    keys_l = {k.lower() for k in req.keys()}
    opt = (node_def.get("input") or {}).get("optional") or {}
    keys_l |= {k.lower() for k in opt.keys()}
    promptish = any(
        k in keys_l
        for k in (
            "prompt",
            "positive",
            "positive_prompt",
            "text",
            "pos",
            "prompt_text",
        )
    )
    if not promptish and req:
        # Some AiO nodes embed prompts under different names — still too uncertain
        return False, "no clear prompt input on AiO node"
    if not req and not opt:
        return False, "empty input schema for AiO node"
    return True, ""


def _fill_scalar_inputs(
    node_def: Dict[str, Any],
    plan: Dict[str, Any],
    prompts: Dict[str, str],
    kwargs: Dict[str, Any],
) -> Dict[str, Any]:
    """Map plan/prompts into AiO scalar inputs by common name heuristics."""
    inputs: Dict[str, Any] = {}
    sections = []
    for section in ("required", "optional"):
        block = (node_def.get("input") or {}).get(section) or {}
        sections.append(block)

    width = int(kwargs.get("width", plan.get("width", 512)))
    height = int(kwargs.get("height", plan.get("height", 512)))
    steps = int(kwargs.get("steps", plan.get("steps", 30)))
    cfg = float(kwargs.get("cfg", plan.get("cfg", 12.2)))
    seed = kwargs.get("seed", plan.get("seed", -1))
    positive = prompts.get("positive") or ""
    negative = prompts.get("negative") or ""
    unet_name = kwargs.get("unet_name") or stock_anima.DEFAULTS["unet_name"]

    aliases = {
        "width": width,
        "height": height,
        "steps": steps,
        "cfg": cfg,
        "seed": seed if seed is not None and int(seed) >= 0 else 0,
        "prompt": positive,
        "positive": positive,
        "positive_prompt": positive,
        "text": positive,
        "pos": positive,
        "negative": negative,
        "negative_prompt": negative,
        "neg": negative,
        "unet_name": unet_name,
        "model_name": unet_name,
        "checkpoint": unet_name,
        "batch_size": int(kwargs.get("batch_size", plan.get("batch_size", 1))),
    }

    for block in sections:
        for name, spec in block.items():
            key = name.lower()
            if key in aliases:
                inputs[name] = aliases[key]
                continue
            # Keep object_info default when present
            if isinstance(spec, (list, tuple)) and len(spec) >= 2 and isinstance(spec[1], dict):
                if "default" in spec[1]:
                    inputs[name] = spec[1]["default"]
    return inputs


def build(
    plan: Dict[str, Any],
    prompts: Dict[str, str],
    caps: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    caps = caps or {}
    object_info = kwargs.get("object_info") or {}
    # Allow caps to carry a hint list of easyuse node names even without full schemas
    easy_names = list(caps.get("easyuse_nodes") or [])

    aio_class = _pick_aio_class(object_info) if object_info else None
    if aio_class is None and caps.get("has_easyuse_aio") and easy_names:
        for n in easy_names:
            if "AIO" in n.upper():
                aio_class = n
                break

    def _fallback(reason: str) -> Dict[str, Any]:
        stock = stock_anima.build(plan, prompts, caps, **kwargs)
        stock["wanted_template"] = TEMPLATE_ID
        stock["template_used"] = stock_anima.TEMPLATE_ID
        stock["fallback_reason"] = reason
        return stock

    if not caps.get("has_easyuse_aio") and aio_class is None:
        return _fallback("EasyUse Anima AiO nodes not discovered")

    if not object_info or aio_class is None or aio_class not in object_info:
        return _fallback(
            "AiO node schema unavailable in object_info; refusing to invent inputs"
        )

    node_def = object_info[aio_class]
    safe, why = _looks_safe_for_minimal(node_def)
    if not safe:
        return _fallback(why or "AiO graph too uncertain")

    aio_inputs = _fill_scalar_inputs(node_def, plan, prompts, kwargs)
    # Minimal graph: AiO (assumed IMAGE out 0) → SaveImage
    # Only emit SaveImage + AiO — both must exist
    if "SaveImage" not in object_info:
        return _fallback("SaveImage missing from object_info")

    prefix = kwargs.get("filename_prefix") or "agent_anima_aio"
    wf = {
        "1": {"class_type": aio_class, "inputs": aio_inputs},
        "2": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": prefix,
                "images": ["1", 0],
            },
        },
    }
    return {
        "workflow": wf,
        "template_id": TEMPLATE_ID,
        "template_used": TEMPLATE_ID,
        "wanted_template": TEMPLATE_ID,
        "fallback_reason": None,
        "meta": {"aio_class": aio_class, "aio_inputs": list(aio_inputs.keys())},
    }
