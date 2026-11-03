"""Template registry and selection."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from . import anima_ref_adapter, easyuse_aio, spectrum_ksampler, stock_anima

Builder = Callable[..., Dict[str, Any]]

TEMPLATES: Dict[str, Dict[str, Any]] = {
    stock_anima.TEMPLATE_ID: {
        "id": stock_anima.TEMPLATE_ID,
        "title": stock_anima.TEMPLATE_TITLE,
        "required_nodes": list(stock_anima.REQUIRED_NODES),
        "builder": stock_anima.build,
        "always_available": True,
    },
    easyuse_aio.TEMPLATE_ID: {
        "id": easyuse_aio.TEMPLATE_ID,
        "title": easyuse_aio.TEMPLATE_TITLE,
        "required_nodes": list(easyuse_aio.REQUIRED_NODES),
        "builder": easyuse_aio.build,
        "always_available": False,
        "cap_flag": "has_easyuse_aio",
    },
    spectrum_ksampler.TEMPLATE_ID: {
        "id": spectrum_ksampler.TEMPLATE_ID,
        "title": spectrum_ksampler.TEMPLATE_TITLE,
        "required_nodes": list(spectrum_ksampler.REQUIRED_NODES),
        "builder": spectrum_ksampler.build,
        "always_available": False,
        "cap_flag": "has_spectrum",
    },
    anima_ref_adapter.TEMPLATE_ID: {
        "id": anima_ref_adapter.TEMPLATE_ID,
        "title": anima_ref_adapter.TEMPLATE_TITLE,
        "required_nodes": list(anima_ref_adapter.REQUIRED_NODES),
        "builder": anima_ref_adapter.build,
        "always_available": False,
        "cap_flag": "has_anima_ref_adapter",
    },
}


def get_template(template_id: str) -> Optional[Dict[str, Any]]:
    return TEMPLATES.get(template_id)


def list_templates(caps: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Return template descriptors; mark which ones look installed."""
    caps = caps or {}
    out: List[Dict[str, Any]] = []
    for tid, meta in TEMPLATES.items():
        available = bool(meta.get("always_available"))
        flag = meta.get("cap_flag")
        if flag and caps.get(flag):
            available = True
        # stock always listed available
        if tid == stock_anima.TEMPLATE_ID:
            available = True
        out.append(
            {
                "id": tid,
                "title": meta["title"],
                "required_nodes": list(meta.get("required_nodes") or []),
                "available": available,
            }
        )
    return out


def _template_installed(tid: str, caps: Dict[str, Any]) -> bool:
    meta = TEMPLATES.get(tid)
    if not meta:
        return False
    if meta.get("always_available"):
        return True
    flag = meta.get("cap_flag")
    if flag and caps.get(flag):
        return True
    # Also check required_nodes against easyuse/spectrum name lists
    req = meta.get("required_nodes") or []
    known = set(caps.get("easyuse_nodes") or []) | set(caps.get("spectrum_nodes") or [])
    if caps.get("has_anima_ref_adapter"):
        known.add("AnimaRefAdapter")
    known |= set(caps.get("anima_related_nodes") or [])
    if req and any(r in known for r in req):
        return True
    return False


def select_template(
    plan: Dict[str, Any],
    caps: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """Choose template id from plan preference + installed caps.

    Returns (selected_id, reason_note).
    """
    caps = caps or {}
    pref = (plan.get("template") or plan.get("template_preference") or "").strip()
    pref_l = pref.lower()

    # Explicit / keyword prefs
    if pref_l in ("", "auto", "自动"):
        pref_l = "auto"

    alias = {
        "stock": stock_anima.TEMPLATE_ID,
        "stock_anima": stock_anima.TEMPLATE_ID,
        "native": stock_anima.TEMPLATE_ID,
        "default": stock_anima.TEMPLATE_ID,
        "默认": stock_anima.TEMPLATE_ID,
        "原生": stock_anima.TEMPLATE_ID,
        "aio": easyuse_aio.TEMPLATE_ID,
        "easyuse": easyuse_aio.TEMPLATE_ID,
        "easyuse_aio": easyuse_aio.TEMPLATE_ID,
        "easyuse-anima": easyuse_aio.TEMPLATE_ID,
        "spectrum": spectrum_ksampler.TEMPLATE_ID,
        "spectrum_ksampler": spectrum_ksampler.TEMPLATE_ID,
        "anima_ref_adapter": anima_ref_adapter.TEMPLATE_ID,
        "ref": anima_ref_adapter.TEMPLATE_ID,
        "ref_adapter": anima_ref_adapter.TEMPLATE_ID,
        "参考图": anima_ref_adapter.TEMPLATE_ID,
        "锁人物": anima_ref_adapter.TEMPLATE_ID,
        "ip-adapter": anima_ref_adapter.TEMPLATE_ID,
        "ip_adapter": anima_ref_adapter.TEMPLATE_ID,
    }
    if pref_l in alias:
        want = alias[pref_l]
        if want == stock_anima.TEMPLATE_ID or _template_installed(want, caps):
            return want, f"explicit preference={pref or want}"
        return (
            stock_anima.TEMPLATE_ID,
            f"wanted {want} but not installed; using stock_anima",
        )

    if pref_l != "auto" and pref in TEMPLATES:
        if _template_installed(pref, caps):
            return pref, f"explicit template={pref}"
        return (
            stock_anima.TEMPLATE_ID,
            f"wanted {pref} but not installed; using stock_anima",
        )

    # Auto: if ref_image is set, prefer anima_ref_adapter when installed
    if plan.get("ref_image") and _template_installed(anima_ref_adapter.TEMPLATE_ID, caps):
        return anima_ref_adapter.TEMPLATE_ID, "auto → anima_ref_adapter (ref_image set)"
    # Conservative otherwise: stock
    return stock_anima.TEMPLATE_ID, "auto → stock_anima (safe default)"


def build_with_template(
    plan: Dict[str, Any],
    prompts: Dict[str, str],
    caps: Optional[Dict[str, Any]] = None,
    *,
    object_info: Optional[Dict[str, Any]] = None,
    template_id: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Select (or force) a template and build workflow + metadata."""
    caps = caps or {}
    if template_id:
        plan = dict(plan)
        plan["template"] = template_id

    selected, note = select_template(plan, caps)
    meta = TEMPLATES.get(selected) or TEMPLATES[stock_anima.TEMPLATE_ID]
    builder: Builder = meta["builder"]
    result = builder(
        plan,
        prompts,
        caps,
        object_info=object_info or {},
        **kwargs,
    )
    result["selection_note"] = note
    result.setdefault("template_id", selected)
    result.setdefault("wanted_template", plan.get("template") or selected)
    return result
