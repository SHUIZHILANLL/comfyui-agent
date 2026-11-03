"""HTTP routes for Agent Anima — registered on PromptServer when available."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

from .agent.planner import plan_command, DEFAULT_WIDTH, DEFAULT_HEIGHT, DEFAULT_STEPS, DEFAULT_CFG
from .agent.prompt_writer import write_prompts
from .agent.workflow_builder import (
    build_workflow_smart,
    DEFAULTS as WF_DEFAULTS,
    list_templates,
)
from .agent.runner import run_generation
from .agent.discovery import (
    get_capabilities,
    list_object_info,
)
from .agent.ui_graph import api_to_ui_workflow, ui_workflow_summary

_ROUTES_REGISTERED = False

_REF_TEMPLATE_ALIASES = (
    "anima_ref_adapter",
    "ref",
    "ref_adapter",
    "参考图",
    "锁人物",
    "ip-adapter",
    "ip_adapter",
)


def _json_response(data: Any, status: int = 200):
    from aiohttp import web  # type: ignore

    return web.Response(
        text=json.dumps(data, ensure_ascii=False, indent=2),
        content_type="application/json",
        status=status,
    )


def _resolve_custom_nodes_path() -> Optional[str]:
    try:
        import folder_paths  # type: ignore

        base = getattr(folder_paths, "base_path", None)
        if base:
            return str(base)
    except Exception:
        pass
    return None


def _caps_bundle(base_url: str = "http://127.0.0.1:8188", force: bool = False) -> Dict[str, Any]:
    path = _resolve_custom_nodes_path()
    return get_capabilities(base_url, custom_nodes_path=path, force=force)


def _truthy(val: Any, default: bool = False) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def _ref_image_missing_error(template: Optional[str], plan: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    want_tpl = (template or plan.get("template") or "").strip().lower()
    if want_tpl in _REF_TEMPLATE_ALIASES and not (plan.get("ref_image") or "").strip():
        return {
            "ok": False,
            "error": "ref_image required for template anima_ref_adapter "
            "(put the filename in ComfyUI input folder, e.g. char.png)",
            "plan": plan,
        }
    return None


def _build_graphs(
    plan: Dict[str, Any],
    pos: str,
    neg: str,
    *,
    caps: Dict[str, Any],
    object_info: Dict[str, Any],
    template: Optional[str],
    **kwargs: Any,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Return (built_meta, api_workflow, ui_workflow)."""
    built = build_workflow_smart(
        plan,
        pos,
        neg,
        caps=caps,
        object_info=object_info,
        template=template or plan.get("template"),
        **kwargs,
    )
    api_wf = built.get("workflow") or {}
    title = f"Agent Anima / {built.get('template_used') or built.get('template_id') or 'workflow'}"
    try:
        ui_wf = api_to_ui_workflow(api_wf, title=title)
    except Exception as e:
        ui_wf = {
            "last_node_id": 0,
            "last_link_id": 0,
            "nodes": [],
            "links": [],
            "groups": [],
            "config": {},
            "extra": {"agent_anima": {"error": str(e)}},
            "version": 0.4,
        }
        built = dict(built)
        built["ui_convert_error"] = str(e)
    return built, api_wf, ui_wf


async def health_handler(request):
    base_url = "http://127.0.0.1:8188"
    try:
        caps = _caps_bundle(base_url)
    except Exception as e:
        caps = {"ok": False, "error": str(e)}
    return _json_response(
        {
            "ok": True,
            "service": "agent_anima",
            "defaults": {
                "unet": WF_DEFAULTS["unet_name"],
                "clip": WF_DEFAULTS["clip_name"],
                "vae": WF_DEFAULTS["vae_name"],
                "width": DEFAULT_WIDTH,
                "height": DEFAULT_HEIGHT,
                "steps": DEFAULT_STEPS,
                "cfg": DEFAULT_CFG,
                "sampler": "euler",
                "scheduler": "simple",
            },
            "capabilities": {
                "ok": caps.get("ok"),
                "error": caps.get("error"),
                "has_easyuse_aio": caps.get("has_easyuse_aio"),
                "has_easyuse_anima": caps.get("has_easyuse_anima"),
                "has_spectrum": caps.get("has_spectrum"),
                "has_anima_tools": caps.get("has_anima_tools"),
                "has_anima_ref_adapter": caps.get("has_anima_ref_adapter"),
                "node_count": caps.get("node_count"),
                "templates": list_templates(caps),
            },
        }
    )


async def capabilities_handler(request):
    base_url = (request.rel_url.query.get("comfy_url") or "http://127.0.0.1:8188").rstrip("/")
    force = request.rel_url.query.get("force", "").lower() in ("1", "true", "yes")
    caps = _caps_bundle(base_url, force=force)
    return _json_response(
        {
            "ok": True,
            "capabilities": caps,
            "templates": list_templates(caps),
        }
    )


async def plan_handler(request):
    try:
        body = await request.json()
    except Exception:
        return _json_response({"ok": False, "error": "invalid JSON"}, 400)

    command = (body.get("command") or "").strip()
    if not command:
        return _json_response({"ok": False, "error": "command required"}, 400)

    use_llm = body.get("use_llm", True)
    template = body.get("template")
    ref_image = (body.get("ref_image") or "").strip() or None
    plan = plan_command(
        command, use_llm=bool(use_llm), template=template, ref_image=ref_image
    )
    err = _ref_image_missing_error(template, plan)
    if err:
        return _json_response(err, 400)

    pos, neg, notes = write_prompts(plan)
    if body.get("positive_prompt"):
        pos = str(body["positive_prompt"]).strip() or pos
    if body.get("negative_prompt"):
        neg = str(body["negative_prompt"]).strip() or neg

    base_url = (body.get("comfy_url") or "http://127.0.0.1:8188").rstrip("/")
    caps = _caps_bundle(base_url)
    fetched = list_object_info(base_url)
    object_info = fetched.get("object_info") or {}

    built, api_wf, ui_wf = _build_graphs(
        plan,
        pos,
        neg,
        caps=caps,
        object_info=object_info,
        template=template or plan.get("template"),
        width=int(body.get("width", plan.get("width", DEFAULT_WIDTH))),
        height=int(body.get("height", plan.get("height", DEFAULT_HEIGHT))),
        steps=int(body.get("steps", plan.get("steps", DEFAULT_STEPS))),
        cfg=float(body.get("cfg", plan.get("cfg", DEFAULT_CFG))),
        seed=int(body.get("seed", plan.get("seed", -1))),
        batch_size=int(body.get("batch_size", plan.get("batch_size", 1))),
        unet_name=body.get("unet_name") or WF_DEFAULTS["unet_name"],
        clip_name=body.get("clip_name") or WF_DEFAULTS["clip_name"],
        vae_name=body.get("vae_name") or WF_DEFAULTS["vae_name"],
    )
    if built.get("fallback_reason"):
        notes = (notes + "; " if notes else "") + f"fallback={built['fallback_reason']}"

    return _json_response(
        {
            "ok": True,
            "plan": plan,
            "positive_prompt": pos,
            "negative_prompt": neg,
            "notes": notes,
            "template_used": built.get("template_used") or built.get("template_id"),
            "wanted_template": built.get("wanted_template"),
            "fallback_reason": built.get("fallback_reason"),
            "capabilities_note": built.get("selection_note") or "",
            "templates": list_templates(caps),
            "workflow": api_wf,
            "ui_workflow": ui_wf,
            "ui_summary": ui_workflow_summary(ui_wf),
        }
    )


async def run_handler(request):
    try:
        body = await request.json()
    except Exception:
        return _json_response({"ok": False, "error": "invalid JSON"}, 400)

    command = (body.get("command") or "").strip()
    if not command:
        return _json_response({"ok": False, "error": "command required"}, 400)

    use_llm = body.get("use_llm", True)
    template = body.get("template")
    ref_image = (body.get("ref_image") or "").strip() or None
    plan = plan_command(
        command, use_llm=bool(use_llm), template=template, ref_image=ref_image
    )

    err = _ref_image_missing_error(template, plan)
    if err:
        return _json_response(err, 400)

    width = int(body.get("width", plan.get("width", DEFAULT_WIDTH)))
    height = int(body.get("height", plan.get("height", DEFAULT_HEIGHT)))
    steps = int(body.get("steps", plan.get("steps", DEFAULT_STEPS)))
    cfg = float(body.get("cfg", plan.get("cfg", DEFAULT_CFG)))
    seed = int(body.get("seed", plan.get("seed", -1)))
    batch_size = int(body.get("batch_size", plan.get("batch_size", 1)))
    unet_name = body.get("unet_name") or WF_DEFAULTS["unet_name"]
    clip_name = body.get("clip_name") or WF_DEFAULTS["clip_name"]
    vae_name = body.get("vae_name") or WF_DEFAULTS["vae_name"]
    wait = bool(body.get("wait", True))
    timeout_s = float(body.get("timeout_s", 600))
    base_url = (body.get("comfy_url") or "http://127.0.0.1:8188").rstrip("/")
    # Panel defaults to showing the graph; raw API callers may set false.
    load_to_canvas = _truthy(body.get("load_to_canvas"), default=True)

    pos, neg, notes = write_prompts(plan)
    if body.get("positive_prompt"):
        pos = str(body["positive_prompt"]).strip() or pos
        notes = (notes + "; " if notes else "") + "positive_prompt override"
    if body.get("negative_prompt"):
        neg = str(body["negative_prompt"]).strip() or neg
        notes = (notes + "; " if notes else "") + "negative_prompt override"

    caps = _caps_bundle(base_url)
    fetched = list_object_info(base_url)
    object_info = fetched.get("object_info") or {}

    built, api_wf, ui_wf = _build_graphs(
        plan,
        pos,
        neg,
        caps=caps,
        object_info=object_info,
        template=template or plan.get("template"),
        width=width,
        height=height,
        steps=steps,
        cfg=cfg,
        seed=seed,
        batch_size=batch_size,
        unet_name=unet_name,
        clip_name=clip_name,
        vae_name=vae_name,
    )
    template_used = built.get("template_used") or built.get("template_id")
    capabilities_note = built.get("selection_note") or ""
    if built.get("fallback_reason"):
        capabilities_note = (
            (capabilities_note + "; " if capabilities_note else "")
            + f"fallback: {built['fallback_reason']}"
        )
        notes = (notes + "; " if notes else "") + f"fallback={built['fallback_reason']}"

    result = run_generation(
        api_wf,
        base_url=base_url,
        timeout_s=timeout_s,
        prefer_internal=False,
        wait=wait,
    )

    return _json_response(
        {
            "ok": bool(result.get("ok")),
            "prompt_id": result.get("prompt_id"),
            "images": result.get("images") or [],
            "image_urls": result.get("image_urls") or [],
            "positive_prompt": pos,
            "negative_prompt": neg,
            "notes": notes,
            "plan": plan,
            "template_used": template_used,
            "wanted_template": built.get("wanted_template"),
            "fallback_reason": built.get("fallback_reason"),
            "capabilities_note": capabilities_note,
            "error": result.get("error"),
            "via": result.get("via"),
            "workflow": api_wf,
            "ui_workflow": ui_wf,
            "ui_summary": ui_workflow_summary(ui_wf),
            "load_to_canvas": load_to_canvas,
            "ui_convert_error": built.get("ui_convert_error"),
        },
        status=200 if result.get("ok") else 500,
    )


async def load_ui_handler(request):
    """Return ui_workflow for the frontend to app.loadGraphData.

    Accepts either:
      - { "workflow": <API prompt dict> }
      - same fields as /plan (command, template, ref_image, ...)
    """
    try:
        body = await request.json()
    except Exception:
        return _json_response({"ok": False, "error": "invalid JSON"}, 400)

    # Direct API→UI conversion
    if isinstance(body.get("workflow"), dict) and body["workflow"]:
        try:
            ui_wf = api_to_ui_workflow(
                body["workflow"],
                title=str(body.get("title") or "Agent Anima"),
            )
        except Exception as e:
            return _json_response(
                {"ok": False, "error": f"ui convert failed: {e}"}, 500
            )
        return _json_response(
            {
                "ok": True,
                "workflow": body["workflow"],
                "ui_workflow": ui_wf,
                "ui_summary": ui_workflow_summary(ui_wf),
            }
        )

    command = (body.get("command") or "").strip()
    if not command:
        return _json_response(
            {"ok": False, "error": "command or workflow required"}, 400
        )

    template = body.get("template")
    ref_image = (body.get("ref_image") or "").strip() or None
    plan = plan_command(
        command,
        use_llm=bool(body.get("use_llm", True)),
        template=template,
        ref_image=ref_image,
    )
    err = _ref_image_missing_error(template, plan)
    if err:
        return _json_response(err, 400)

    pos, neg, notes = write_prompts(plan)
    if body.get("positive_prompt"):
        pos = str(body["positive_prompt"]).strip() or pos
    if body.get("negative_prompt"):
        neg = str(body["negative_prompt"]).strip() or neg

    base_url = (body.get("comfy_url") or "http://127.0.0.1:8188").rstrip("/")
    caps = _caps_bundle(base_url)
    object_info = (list_object_info(base_url).get("object_info") or {})

    built, api_wf, ui_wf = _build_graphs(
        plan,
        pos,
        neg,
        caps=caps,
        object_info=object_info,
        template=template or plan.get("template"),
        width=int(body.get("width", plan.get("width", DEFAULT_WIDTH))),
        height=int(body.get("height", plan.get("height", DEFAULT_HEIGHT))),
        steps=int(body.get("steps", plan.get("steps", DEFAULT_STEPS))),
        cfg=float(body.get("cfg", plan.get("cfg", DEFAULT_CFG))),
        seed=int(body.get("seed", plan.get("seed", -1))),
        batch_size=int(body.get("batch_size", plan.get("batch_size", 1))),
        unet_name=body.get("unet_name") or WF_DEFAULTS["unet_name"],
        clip_name=body.get("clip_name") or WF_DEFAULTS["clip_name"],
        vae_name=body.get("vae_name") or WF_DEFAULTS["vae_name"],
    )

    return _json_response(
        {
            "ok": True,
            "plan": plan,
            "positive_prompt": pos,
            "negative_prompt": neg,
            "notes": notes,
            "template_used": built.get("template_used") or built.get("template_id"),
            "wanted_template": built.get("wanted_template"),
            "fallback_reason": built.get("fallback_reason"),
            "capabilities_note": built.get("selection_note") or "",
            "workflow": api_wf,
            "ui_workflow": ui_wf,
            "ui_summary": ui_workflow_summary(ui_wf),
            "ui_convert_error": built.get("ui_convert_error"),
        }
    )


def register_routes():
    """Attach routes to PromptServer.instance. Safe no-op outside ComfyUI."""
    global _ROUTES_REGISTERED
    if _ROUTES_REGISTERED:
        return
    try:
        from server import PromptServer  # type: ignore
    except ImportError:
        return

    inst = getattr(PromptServer, "instance", None)
    if inst is None or not hasattr(inst, "routes"):
        return

    routes = inst.routes
    routes.get("/agent_anima/health")(health_handler)
    routes.get("/agent_anima/capabilities")(capabilities_handler)
    routes.post("/agent_anima/plan")(plan_handler)
    routes.post("/agent_anima/run")(run_handler)
    routes.post("/agent_anima/load_ui")(load_ui_handler)
    _ROUTES_REGISTERED = True
    print(
        "[agent_anima] HTTP routes registered: "
        "/agent_anima/health|capabilities|plan|run|load_ui"
    )
