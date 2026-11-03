"""Convert ComfyUI API-format prompt dicts into LiteGraph / UI workflow JSON.

Enough for app.loadGraphData to show stock_anima and anima_ref_adapter graphs.
Unknown nodes fall back to a heuristic (links = list values, rest = widgets).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

# Per class_type: linked input slots (name, type) then widget API keys in widgets_values order.
# Keys starting with "_" are UI-only (not read from API inputs).
NodeSpec = Dict[str, Any]

NODE_SPECS: Dict[str, NodeSpec] = {
    "UNETLoader": {
        "outputs": [("MODEL", "MODEL")],
        "link_inputs": [],
        "widgets": ["unet_name", "weight_dtype"],
        "size": [320, 90],
    },
    "CLIPLoader": {
        "outputs": [("CLIP", "CLIP")],
        "link_inputs": [],
        "widgets": ["clip_name", "type", "device"],
        "size": [320, 110],
    },
    "VAELoader": {
        "outputs": [("VAE", "VAE")],
        "link_inputs": [],
        "widgets": ["vae_name"],
        "size": [320, 60],
    },
    "LoadImage": {
        "outputs": [("IMAGE", "IMAGE"), ("MASK", "MASK")],
        "link_inputs": [],
        "widgets": ["image", "_upload"],
        "size": [320, 314],
        "defaults": {"_upload": "image"},
    },
    "AnimaRefAdapter": {
        "outputs": [("MODEL", "MODEL")],
        "link_inputs": [("model", "MODEL"), ("vae", "VAE"), ("image", "IMAGE")],
        "widgets": [
            "lora_name",
            "ref_guidance",
            "correction",
            "strength",
            "ref_end",
            "ref_megapixels",
        ],
        "size": [320, 220],
    },
    "CLIPTextEncode": {
        "outputs": [("CONDITIONING", "CONDITIONING")],
        "link_inputs": [("clip", "CLIP")],
        "widgets": ["text"],
        "size": [400, 200],
    },
    "EmptyLatentImage": {
        "outputs": [("LATENT", "LATENT")],
        "link_inputs": [],
        "widgets": ["width", "height", "batch_size"],
        "size": [320, 110],
    },
    "KSampler": {
        "outputs": [("LATENT", "LATENT")],
        "link_inputs": [
            ("model", "MODEL"),
            ("positive", "CONDITIONING"),
            ("negative", "CONDITIONING"),
            ("latent_image", "LATENT"),
        ],
        "widgets": [
            "seed",
            "_control_after_generate",
            "steps",
            "cfg",
            "sampler_name",
            "scheduler",
            "denoise",
        ],
        "size": [320, 262],
        "defaults": {"_control_after_generate": "fixed"},
    },
    "VAEDecode": {
        "outputs": [("IMAGE", "IMAGE")],
        "link_inputs": [("samples", "LATENT"), ("vae", "VAE")],
        "widgets": [],
        "size": [210, 46],
    },
    "SaveImage": {
        "outputs": [],
        "link_inputs": [("images", "IMAGE")],
        "widgets": ["filename_prefix"],
        "size": [320, 270],
    },
}

# Rough left-to-right layout columns by role
_COLUMN_X = {
    "UNETLoader": 40,
    "CLIPLoader": 40,
    "VAELoader": 40,
    "LoadImage": 40,
    "AnimaRefAdapter": 400,
    "CLIPTextEncode": 760,
    "EmptyLatentImage": 760,
    "KSampler": 1220,
    "VAEDecode": 1220,
    "SaveImage": 1580,
}


def _is_link(value: Any) -> bool:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        a, b = value
        if isinstance(a, (str, int)) and isinstance(b, int):
            return True
    return False


def _spec_for(class_type: str, inputs: Dict[str, Any]) -> NodeSpec:
    if class_type in NODE_SPECS:
        return NODE_SPECS[class_type]
    # Heuristic: linked vs widget by value shape
    link_inputs: List[Tuple[str, str]] = []
    widgets: List[str] = []
    for name, val in inputs.items():
        if _is_link(val):
            link_inputs.append((name, "*"))
        else:
            widgets.append(name)
    return {
        "outputs": [("*", "*")],
        "link_inputs": link_inputs,
        "widgets": widgets,
        "size": [280, 80],
    }


def _widget_values(spec: NodeSpec, inputs: Dict[str, Any]) -> List[Any]:
    defaults = spec.get("defaults") or {}
    out: List[Any] = []
    for key in spec.get("widgets") or []:
        if key.startswith("_"):
            out.append(defaults.get(key, "fixed" if key == "_control_after_generate" else ""))
            continue
        if key in inputs:
            out.append(inputs[key])
        elif key in defaults:
            out.append(defaults[key])
        else:
            out.append(None)
    return out


def _layout_positions(ordered_ids: Sequence[int], types: Dict[int, str]) -> Dict[int, List[float]]:
    """Place nodes in columns; stack vertically within a column."""
    columns: Dict[int, List[int]] = {}
    for nid in ordered_ids:
        ctype = types[nid]
        x = int(_COLUMN_X.get(ctype, 40 + 360 * (len(columns) % 5)))
        columns.setdefault(x, []).append(nid)

    pos: Dict[int, List[float]] = {}
    for x, ids in columns.items():
        y = 40.0
        for nid in ids:
            pos[nid] = [float(x), y]
            h = float((NODE_SPECS.get(types[nid], {}).get("size") or [280, 100])[1])
            y += h + 40.0
    return pos


def api_to_ui_workflow(
    api_workflow: Dict[str, Any],
    *,
    title: str = "Agent Anima",
) -> Dict[str, Any]:
    """Convert API prompt graph → ComfyUI UI workflow (nodes + links)."""
    if not isinstance(api_workflow, dict) or not api_workflow:
        return {
            "last_node_id": 0,
            "last_link_id": 0,
            "nodes": [],
            "links": [],
            "groups": [],
            "config": {},
            "extra": {"agent_anima": {"title": title}},
            "version": 0.4,
        }

    # Stable numeric order
    raw_ids = sorted(api_workflow.keys(), key=lambda k: int(k) if str(k).isdigit() else str(k))
    id_map: Dict[str, int] = {}
    for k in raw_ids:
        id_map[str(k)] = int(k) if str(k).isdigit() else (len(id_map) + 1)

    types: Dict[int, str] = {}
    input_maps: Dict[int, Dict[str, Any]] = {}
    specs: Dict[int, NodeSpec] = {}
    for k in raw_ids:
        node = api_workflow[k] or {}
        nid = id_map[str(k)]
        ctype = str(node.get("class_type") or "Unknown")
        inputs = dict(node.get("inputs") or {})
        types[nid] = ctype
        input_maps[nid] = inputs
        specs[nid] = _spec_for(ctype, inputs)

    ordered = [id_map[str(k)] for k in raw_ids]
    positions = _layout_positions(ordered, types)

    links: List[List[Any]] = []
    link_id = 0
    # target_nid -> input_slot_index -> link_id
    incoming: Dict[int, Dict[int, int]] = {nid: {} for nid in ordered}
    # source_nid -> output_slot -> [link_ids]
    outgoing: Dict[int, Dict[int, List[int]]] = {nid: {} for nid in ordered}

    for nid in ordered:
        spec = specs[nid]
        inputs = input_maps[nid]
        for slot_i, (iname, itype) in enumerate(spec.get("link_inputs") or []):
            val = inputs.get(iname)
            if not _is_link(val):
                continue
            src_key, src_slot = val[0], int(val[1])
            src_nid = id_map.get(str(src_key))
            if src_nid is None:
                continue
            link_id += 1
            # Prefer declared output type from source spec
            src_outs = specs[src_nid].get("outputs") or []
            if 0 <= src_slot < len(src_outs):
                link_type = src_outs[src_slot][1]
            else:
                link_type = itype if itype != "*" else "*"
            links.append([link_id, src_nid, src_slot, nid, slot_i, link_type])
            incoming[nid][slot_i] = link_id
            outgoing.setdefault(src_nid, {}).setdefault(src_slot, []).append(link_id)

    nodes: List[Dict[str, Any]] = []
    for order_i, nid in enumerate(ordered):
        ctype = types[nid]
        spec = specs[nid]
        inputs_ui: List[Dict[str, Any]] = []
        for slot_i, (iname, itype) in enumerate(spec.get("link_inputs") or []):
            entry: Dict[str, Any] = {
                "name": iname,
                "type": itype if itype != "*" else "*",
                "link": incoming[nid].get(slot_i),
            }
            inputs_ui.append(entry)

        outputs_ui: List[Dict[str, Any]] = []
        for slot_i, (oname, otype) in enumerate(spec.get("outputs") or []):
            outs_links = outgoing.get(nid, {}).get(slot_i)
            outputs_ui.append(
                {
                    "name": oname if oname != "*" else "OUT",
                    "type": otype if otype != "*" else "*",
                    "slot_index": slot_i,
                    "links": outs_links if outs_links else None,
                }
            )

        node_obj: Dict[str, Any] = {
            "id": nid,
            "type": ctype,
            "pos": positions.get(nid, [40.0, 40.0]),
            "size": list(spec.get("size") or [280, 80]),
            "flags": {},
            "order": order_i,
            "mode": 0,
            "inputs": inputs_ui,
            "outputs": outputs_ui,
            "properties": {"Node name for S&R": ctype},
            "widgets_values": _widget_values(spec, input_maps[nid]),
        }
        nodes.append(node_obj)

    last_node_id = max(ordered) if ordered else 0
    return {
        "last_node_id": last_node_id,
        "last_link_id": link_id,
        "nodes": nodes,
        "links": links,
        "groups": [],
        "config": {},
        "extra": {
            "agent_anima": {"title": title},
            "ds": {"scale": 0.75, "offset": [0, 0]},
        },
        "version": 0.4,
    }


def ui_workflow_summary(ui: Dict[str, Any]) -> Dict[str, Any]:
    types = [n.get("type") for n in (ui.get("nodes") or [])]
    return {
        "node_count": len(types),
        "link_count": len(ui.get("links") or []),
        "types": types,
        "last_node_id": ui.get("last_node_id"),
        "last_link_id": ui.get("last_link_id"),
    }
