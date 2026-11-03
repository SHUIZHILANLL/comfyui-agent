"""Submit workflows to ComfyUI and wait for results."""

from __future__ import annotations

import json
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


def _http_json(method: str, url: str, body: Optional[dict] = None, timeout: float = 60.0) -> Any:
    data = None
    headers = {"Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        if not raw:
            return None
        return json.loads(raw)


def queue_prompt_http(
    base_url: str,
    prompt: Dict[str, Any],
    client_id: Optional[str] = None,
) -> Dict[str, Any]:
    """POST /prompt — works from outside ComfyUI process."""
    base = base_url.rstrip("/")
    payload = {
        "prompt": prompt,
        "client_id": client_id or str(uuid.uuid4()),
    }
    return _http_json("POST", f"{base}/prompt", payload, timeout=120.0)


def get_history(base_url: str, prompt_id: str) -> Dict[str, Any]:
    base = base_url.rstrip("/")
    data = _http_json("GET", f"{base}/history/{urllib.parse.quote(prompt_id)}", timeout=30.0)
    return data or {}


def wait_for_prompt(
    base_url: str,
    prompt_id: str,
    timeout_s: float = 600.0,
    poll_interval: float = 1.0,
) -> Dict[str, Any]:
    """Poll /history/{prompt_id} until outputs appear or timeout."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        hist = get_history(base_url, prompt_id)
        entry = hist.get(prompt_id)
        if entry and entry.get("outputs"):
            return entry
        # Also detect failed status if present
        if entry and entry.get("status", {}).get("status_str") == "error":
            return entry
        time.sleep(poll_interval)
    raise TimeoutError(f"Timed out waiting for prompt_id={prompt_id}")


def extract_image_refs(history_entry: Dict[str, Any]) -> List[Dict[str, str]]:
    """Collect SaveImage / PreviewImage outputs from a history entry."""
    images: List[Dict[str, str]] = []
    outputs = history_entry.get("outputs") or {}
    for _nid, node_out in outputs.items():
        for img in node_out.get("images") or []:
            images.append(
                {
                    "filename": img.get("filename", ""),
                    "subfolder": img.get("subfolder", ""),
                    "type": img.get("type", "output"),
                }
            )
    return images


def image_view_url(base_url: str, ref: Dict[str, str]) -> str:
    base = base_url.rstrip("/")
    q = urllib.parse.urlencode(
        {
            "filename": ref.get("filename", ""),
            "subfolder": ref.get("subfolder", ""),
            "type": ref.get("type", "output"),
        }
    )
    return f"{base}/view?{q}"


def queue_prompt_internal(prompt: Dict[str, Any], client_id: Optional[str] = None) -> Dict[str, Any]:
    """Try in-process PromptServer queue when running inside ComfyUI."""
    try:
        from server import PromptServer  # type: ignore
    except ImportError:
        raise RuntimeError("PromptServer not available (not inside ComfyUI)")

    inst = PromptServer.instance
    if inst is None:
        raise RuntimeError("PromptServer.instance is None")

    cid = client_id or str(uuid.uuid4())
    # Prefer the same path the HTTP handler uses
    number = None
    if hasattr(inst, "number"):
        number = inst.number
        if isinstance(number, int):
            inst.number += 1

    prompt_id = str(uuid.uuid4())
    item = (number if number is not None else float("inf"), prompt_id, prompt, {}, cid)
    # ComfyUI queue_prompt signature varies; use put on prompt_queue when present
    if hasattr(inst, "prompt_queue") and hasattr(inst.prompt_queue, "put"):
        # Standard: (number, prompt_id, prompt, extra_data, outputs_to_execute)
        # Some versions expect validate first — fall back to HTTP if this fails
        try:
            valid = prompt  # already API format
            inst.prompt_queue.put(
                (number if number is not None else time.time(), prompt_id, valid, {"client_id": cid}, [])
            )
            return {"prompt_id": prompt_id, "number": number, "client_id": cid, "via": "internal"}
        except Exception as e:
            raise RuntimeError(f"internal queue failed: {e}") from e
    raise RuntimeError("prompt_queue not available")


def run_generation(
    prompt: Dict[str, Any],
    *,
    base_url: str = "http://127.0.0.1:8188",
    timeout_s: float = 600.0,
    prefer_internal: bool = True,
    wait: bool = True,
) -> Dict[str, Any]:
    """Queue a prompt and optionally wait. Returns status dict with images."""
    client_id = str(uuid.uuid4())
    queued_via = "http"
    prompt_id = None
    number = None

    if prefer_internal:
        try:
            # Internal path is best-effort; most reliable for external agents is HTTP
            result = queue_prompt_http(base_url, prompt, client_id=client_id)
            prompt_id = result.get("prompt_id")
            number = result.get("number")
            queued_via = "http"
        except Exception:
            try:
                result = queue_prompt_internal(prompt, client_id=client_id)
                prompt_id = result.get("prompt_id")
                number = result.get("number")
                queued_via = "internal"
            except Exception as e:
                return {"ok": False, "error": str(e), "via": "none"}
    else:
        try:
            result = queue_prompt_http(base_url, prompt, client_id=client_id)
            prompt_id = result.get("prompt_id")
            number = result.get("number")
        except Exception as e:
            return {"ok": False, "error": str(e), "via": "http"}

    out: Dict[str, Any] = {
        "ok": True,
        "prompt_id": prompt_id,
        "number": number,
        "client_id": client_id,
        "via": queued_via,
        "images": [],
        "image_urls": [],
    }

    if not wait or not prompt_id:
        return out

    try:
        entry = wait_for_prompt(base_url, prompt_id, timeout_s=timeout_s)
        refs = extract_image_refs(entry)
        out["images"] = refs
        out["image_urls"] = [image_view_url(base_url, r) for r in refs]
        status = (entry.get("status") or {}).get("status_str")
        if status == "error":
            out["ok"] = False
            out["error"] = entry.get("status")
        out["history_status"] = status
    except Exception as e:
        out["ok"] = False
        out["error"] = str(e)

    return out
