"""Light local tag research — JSON knowledge base + optional LLM expansion."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "tag_hints.json"


@lru_cache(maxsize=1)
def load_tag_hints() -> Dict[str, Any]:
    try:
        with open(_DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {
            "characters": {},
            "styles": {},
            "shots": {},
            "moods": {},
            "quality": "masterpiece, best quality, highres",
        }


def _llm_expand(command: str, context: Dict[str, str]) -> Optional[Dict[str, Any]]:
    base = os.environ.get("AGENT_ANIMA_LLM_BASE", "").rstrip("/")
    key = os.environ.get("AGENT_ANIMA_LLM_KEY", "")
    model = os.environ.get("AGENT_ANIMA_LLM_MODEL", "gpt-4o-mini")
    if not base or not key:
        return None

    system = (
        "Expand anime image prompts into Danbooru-style English tags. "
        "Return ONLY JSON: {character_extra, style_extra, mood_extra, extra_tags (list)}. "
        "Keep tags short and comma-separated. No commentary."
    )
    user = json.dumps({"command": command, "matched": context}, ensure_ascii=False)
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
    }
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        content = raw["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)
        data = json.loads(content)
        return {
            "character_extra": data.get("character_extra") or "",
            "style_extra": data.get("style_extra") or "",
            "mood_extra": data.get("mood_extra") or "",
            "extra_tags": list(data.get("extra_tags") or []),
        }
    except Exception:
        return None


def expand_tags(
    command: str,
    char_key: str = "",
    style_key: str = "",
) -> Dict[str, Any]:
    """Expand tags from local DB; optionally ask LLM. Never fabricates web scrapes."""
    hints = load_tag_hints()
    result: Dict[str, Any] = {
        "character_extra": "",
        "style_extra": "",
        "mood_extra": "",
        "extra_tags": [],
        "quality": hints.get("quality", "masterpiece, best quality, highres"),
    }

    # Local extras already applied by planner via keys; here we only add LLM polish
    context = {"character": char_key, "style": style_key}
    llm = _llm_expand(command, context)
    if llm:
        for k in ("character_extra", "style_extra", "mood_extra"):
            if llm.get(k):
                result[k] = llm[k]
        if llm.get("extra_tags"):
            result["extra_tags"] = list(llm["extra_tags"])

    return result


def lookup_character(name: str) -> str:
    hints = load_tag_hints()
    chars = hints.get("characters", {})
    if name in chars:
        return chars[name]
    low = name.lower()
    for k, v in chars.items():
        if k.lower() == low:
            return v
    return ""


def lookup_style(name: str) -> str:
    hints = load_tag_hints()
    styles = hints.get("styles", {})
    if name in styles:
        return styles[name]
    low = name.lower()
    for k, v in styles.items():
        if k.lower() == low:
            return v
    return ""
