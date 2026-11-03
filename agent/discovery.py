"""Discover installed ComfyUI nodes and custom_node folders."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

DEFAULT_BASE_URL = "http://127.0.0.1:8188"
_CACHE_TTL_S = 30.0

_object_info_cache: Dict[str, Any] = {
    "ts": 0.0,
    "base_url": "",
    "data": None,
    "error": None,
}


def list_object_info(
    base_url: str = DEFAULT_BASE_URL,
    *,
    force: bool = False,
    timeout: float = 60.0,
) -> Dict[str, Any]:
    """GET /object_info with a short in-memory cache.

    Returns {"ok": bool, "object_info": dict, "error": str|None, "cached": bool}.
    """
    base = (base_url or DEFAULT_BASE_URL).rstrip("/")
    now = time.time()
    if (
        not force
        and _object_info_cache["data"] is not None
        and _object_info_cache["base_url"] == base
        and (now - float(_object_info_cache["ts"])) < _CACHE_TTL_S
    ):
        return {
            "ok": _object_info_cache["error"] is None,
            "object_info": _object_info_cache["data"] or {},
            "error": _object_info_cache["error"],
            "cached": True,
        }

    url = f"{base}/object_info"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("object_info is not a dict")
        _object_info_cache.update(
            {"ts": now, "base_url": base, "data": data, "error": None}
        )
        return {"ok": True, "object_info": data, "error": None, "cached": False}
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as e:
        err = str(e)
        # Keep last good cache if present for this base
        if (
            _object_info_cache["data"] is not None
            and _object_info_cache["base_url"] == base
        ):
            return {
                "ok": False,
                "object_info": _object_info_cache["data"] or {},
                "error": err,
                "cached": True,
            }
        _object_info_cache.update(
            {"ts": now, "base_url": base, "data": {}, "error": err}
        )
        return {"ok": False, "object_info": {}, "error": err, "cached": False}


def clear_object_info_cache() -> None:
    _object_info_cache.update(
        {"ts": 0.0, "base_url": "", "data": None, "error": None}
    )


def scan_custom_node_folders(
    comfy_root_or_custom_nodes_path: Optional[str] = None,
) -> Dict[str, Any]:
    """List top-level folder names under custom_nodes (optional FS scan)."""
    if not comfy_root_or_custom_nodes_path:
        return {"ok": False, "folders": [], "error": "path not provided", "path": None}

    p = Path(comfy_root_or_custom_nodes_path)
    if p.name != "custom_nodes":
        candidate = p / "custom_nodes"
        if candidate.is_dir():
            p = candidate
    if not p.is_dir():
        return {
            "ok": False,
            "folders": [],
            "error": f"not a directory: {p}",
            "path": str(p),
        }

    folders: List[str] = []
    try:
        for child in sorted(p.iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                folders.append(child.name)
    except OSError as e:
        return {"ok": False, "folders": [], "error": str(e), "path": str(p)}

    return {"ok": True, "folders": folders, "error": None, "path": str(p)}


def class_types(object_info: Optional[Dict[str, Any]]) -> Set[str]:
    if not object_info:
        return set()
    return set(object_info.keys())


def has_node(object_info: Optional[Dict[str, Any]], class_type: str) -> bool:
    return bool(object_info) and class_type in object_info


def find_nodes_by_prefix(
    object_info: Optional[Dict[str, Any]], prefix: str
) -> List[str]:
    if not object_info:
        return []
    return sorted(k for k in object_info if k.startswith(prefix))


def available_capabilities(
    object_info: Optional[Dict[str, Any]] = None,
    *,
    base_url: str = DEFAULT_BASE_URL,
    folders: Optional[List[str]] = None,
    discovery_error: Optional[str] = None,
) -> Dict[str, Any]:
    """Summarize installed capabilities for template selection."""
    err = discovery_error
    info = object_info
    if info is None:
        fetched = list_object_info(base_url)
        info = fetched.get("object_info") or {}
        if not fetched.get("ok"):
            err = fetched.get("error") or err

    types = class_types(info)
    easyuse_nodes = find_nodes_by_prefix(info, "EasyUseAnima")
    anima_tool_nodes = [
        k
        for k in sorted(types)
        if "anima" in k.lower() and not k.startswith("EasyUseAnima")
        and k not in ("UNETLoader",)  # noise filter
    ]
    # Prefer explicit anima-tools-ish names
    anima_tools_hits = [
        k
        for k in anima_tool_nodes
        if any(
            s in k.lower()
            for s in ("animatool", "anima_tool", "animaguide", "animamod", "anima")
        )
    ]

    spectrum_nodes = [
        k
        for k in sorted(types)
        if "spectrum" in k.lower()
    ]

    folder_set = {f.lower() for f in (folders or [])}

    caps: Dict[str, Any] = {
        "ok": err is None and bool(types),
        "error": err,
        "node_count": len(types),
        "has_easyuse_aio": any(
            n in types
            for n in (
                "EasyUseAnimaAIOGenerator",
                "EasyUseAnimaAIO",
                "easyuseAnimaAIOGenerator",
            )
        )
        or any("AIO" in n.upper() for n in easyuse_nodes),
        "has_easyuse_anima": bool(easyuse_nodes)
        or "comfyui-easyuse-anima" in folder_set,
        "has_anima_tools": bool(anima_tools_hits)
        or "comfyui-anima-tools" in folder_set,
        "has_spectrum": bool(spectrum_nodes)
        or "comfyui-spectrum-ksampler" in folder_set,
        "has_anima_ref_adapter": (
            "AnimaRefAdapter" in types
            or any("animarefadapter" == k.lower() for k in types)
            or "comfyui-anima-ref-adapter" in folder_set
            or any("anima-ref-adapter" in f or "anima_ref_adapter" in f for f in folder_set)
        ),
        "has_gguf": any("gguf" in k.lower() for k in types)
        or "comfyui-gguf" in folder_set,
        "has_kjnodes": any(k.startswith("KJ") or "kjnode" in k.lower() for k in types)
        or "comfyui-kjnodes" in folder_set,
        "easyuse_nodes": easyuse_nodes,
        "spectrum_nodes": spectrum_nodes,
        "anima_related_nodes": anima_tools_hits[:40],
        "stock_nodes_ok": all(
            n in types
            for n in (
                "UNETLoader",
                "CLIPLoader",
                "VAELoader",
                "EmptyLatentImage",
                "CLIPTextEncode",
                "KSampler",
                "VAEDecode",
                "SaveImage",
            )
        )
        if types
        else True,  # assume stock ok when offline / empty
        "folders": list(folders or []),
        "class_types_sample": sorted(types)[:30] if types else [],
    }
    return caps


def get_capabilities(
    base_url: str = DEFAULT_BASE_URL,
    *,
    custom_nodes_path: Optional[str] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Convenience: fetch object_info + optional folder scan → capabilities."""
    fetched = list_object_info(base_url, force=force)
    folders_result = None
    folders: List[str] = []
    if custom_nodes_path:
        folders_result = scan_custom_node_folders(custom_nodes_path)
        folders = folders_result.get("folders") or []

    caps = available_capabilities(
        fetched.get("object_info") or {},
        base_url=base_url,
        folders=folders,
        discovery_error=None if fetched.get("ok") else fetched.get("error"),
    )
    caps["object_info_ok"] = bool(fetched.get("ok"))
    caps["object_info_cached"] = bool(fetched.get("cached"))
    if folders_result is not None:
        caps["folders_scan"] = {
            "ok": folders_result.get("ok"),
            "path": folders_result.get("path"),
            "error": folders_result.get("error"),
            "count": len(folders),
        }
    return caps
