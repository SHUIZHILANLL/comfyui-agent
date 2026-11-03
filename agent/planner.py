"""Rule-based (and optional LLM) natural-language command planner."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from .research import expand_tags, load_tag_hints

DEFAULT_WIDTH = 512
DEFAULT_HEIGHT = 512
DEFAULT_STEPS = 30
DEFAULT_CFG = 12.2

_SIZE_RE = re.compile(
    r"(?:(\d{3,4})\s*[x×X*]\s*(\d{3,4}))|"
    r"(?:宽(?:度)?\s*[:=]?\s*(\d{3,4}).*?高(?:度)?\s*[:=]?\s*(\d{3,4}))|"
    r"(?:width\s*[:=]?\s*(\d{3,4}).*?height\s*[:=]?\s*(\d{3,4}))",
    re.I | re.S,
)
_STEPS_RE = re.compile(r"(?:steps?\s*[:=]?\s*|步数\s*[:=]?\s*)(\d{1,3})", re.I)
_CFG_RE = re.compile(r"(?:cfg\s*[:=]?\s*|引导\s*[:=]?\s*)(\d+(?:\.\d+)?)", re.I)
_SEED_RE = re.compile(r"(?:seed\s*[:=]?\s*|种子\s*[:=]?\s*)(-?\d+)", re.I)
_BATCH_RE = re.compile(
    r"(?:batch(?:[_\s]?size)?\s*[:=]?\s*|批量\s*[:=]?\s*|张数\s*[:=]?\s*)(\d{1,2})",
    re.I,
)

_NSFW_KEYWORDS = (
    "nsfw", "裸体", "裸", "nude", "naked", "色情", "sex", " ent", "hentai",
    "explicit", "裸露", "露出", "下着", "lingerie", "bikini", "泳装",
)
_SFW_FORCE = ("sfw", "全年龄", "健全", "safe")

_ARTIST_AT = re.compile(r"@([\w\u4e00-\u9fff][\w\u4e00-\u9fff\- ]{0,40})")

_SHOT_KEYS = {
    "特写": "close-up", "close-up": "close-up", "closeup": "close-up",
    "半身": "upper body", "upper body": "upper body", "portrait": "upper body",
    "全身": "full body", "full body": "full body", "fullbody": "full body",
    "远景": "wide shot", "wide shot": "wide shot", "scenery": "wide shot",
    "俯视": "from above", "from above": "from above",
    "仰视": "from below", "from below": "from below",
    "侧面": "profile", "profile": "profile",
    "背面": "from behind", "from behind": "from behind",
}

# Common Chinese action / prop phrases → Danbooru-ish tags
_PHRASE_MAP = [
    (r"撑伞|打伞|持伞|拿着伞|撑着伞", "holding umbrella, umbrella"),
    (r"雨中|淋雨", "in the rain"),
    (r"微笑|笑着|浅笑", "smile"),
    (r"回头", "looking back"),
    (r"看向观众|看镜头", "looking at viewer"),
    (r"坐着|坐在", "sitting"),
    (r"站着|站在", "standing"),
    (r"走路|步行", "walking"),
    (r"跑步|奔跑", "running"),
    (r"学校|校服", "school uniform"),
    (r"和服|浴衣", "kimono"),
    (r"女仆装|女仆", "maid"),
    (r"猫耳少女|猫娘|猫耳", "1girl, cat girl, cat ears, animal ears, animal ear fluff"),
    (r"狐耳", "1girl, fox ears, animal ears"),
    (r"兔耳", "1girl, rabbit ears, animal ears"),
    (r"翅膀", "wings"),
    (r"银发蓝瞳", "silver hair, blue eyes"),
    (r"银发", "silver hair"),
    (r"白发", "white hair"),
    (r"黑发", "black hair"),
    (r"金发", "blonde hair"),
    (r"蓝瞳|蓝色眼睛", "blue eyes"),
    (r"红瞳|红色眼睛", "red eyes"),
    (r"长发", "long hair"),
    (r"短发", "short hair"),
    (r"双马尾", "twintails"),
    (r"精致面部|精致脸|漂亮脸", "detailed face, detailed eyes"),
    (r"花瓣飘落|飘落花瓣", "falling petals"),
    (r"柔和逆光|逆光", "backlight, soft lighting"),
    (r"春日阳光|阳光", "sunlight, spring"),
    (r"树下", "under tree"),
    (r"单人", "solo"),
    (r"少女", "1girl"),
    (r"少年", "1boy"),
    (r"海边|沙滩", "beach, ocean"),
    (r"教室", "classroom"),
    (r"屋顶", "on rooftop"),
    (r"窗边|靠窗", "by the window"),
    (r"书店|图书馆", "library"),
    (r"咖啡厅|咖啡馆", "cafe"),
    (r"动漫高质量|高质量|高画质", "masterpiece, best quality, highly detailed"),
]


def _empty_plan(command: str) -> Dict[str, Any]:
    return {
        "command": command.strip(),
        "subject": "",
        "style": "",
        "artists": [],
        "shot": "",
        "mood": "",
        "nsfw": False,
        "width": DEFAULT_WIDTH,
        "height": DEFAULT_HEIGHT,
        "steps": DEFAULT_STEPS,
        "cfg": DEFAULT_CFG,
        "seed": -1,
        "batch_size": 1,
        "extra_tags": [],
        "notes": [],
        "template": "auto",
        "ref_image": "",
        "source": "rules",
    }



_REF_IMAGE_RE = re.compile(
    r"(?:ref_image|参考图|参考)\s*[=:：]?\s*[\"']?([^\s,\"'，]+?\.(?:png|jpg|jpeg|webp|bmp))",
    re.I,
)


def _extract_ref_image(text: str) -> str:
    m = _REF_IMAGE_RE.search(text or "")
    return m.group(1).strip() if m else ""


def _detect_template(text: str) -> str:
    """Pick template preference from command keywords; default auto."""
    low = text.lower()
    # Explicit 原生 / 默认 before aio (「默认」alone is weak — require 默认工作流 or 原生)
    if "原生" in text or "native" in low or "stock_anima" in low or "默认工作流" in text:
        return "stock_anima"
    ref_keys = (
        "参考图", "锁人物", "人物一致", "ip-adapter", "ip adapter", "ip_adapter",
        "ref adapter", "ref_adapter", "anima_ref", "ref_image",
    )
    if any(k in low or k in text for k in ref_keys):
        return "anima_ref_adapter"
    if any(k in low or k in text for k in ("aio", "easyuse", "easy use", "一键")):
        return "easyuse_aio"
    if "spectrum" in low or "频谱采样" in text:
        return "spectrum_ksampler"
    if "默认" in text and "模板" in text:
        return "stock_anima"
    return "auto"


def _detect_nsfw(text: str) -> bool:
    low = text.lower()
    if any(k in low or k in text for k in _SFW_FORCE):
        return False
    return any(k in low or k in text for k in _NSFW_KEYWORDS)


def _match_size(text: str) -> Optional[tuple]:
    m = _SIZE_RE.search(text)
    if not m:
        return None
    groups = m.groups()
    for i in range(0, len(groups), 2):
        if groups[i] and groups[i + 1]:
            return int(groups[i]), int(groups[i + 1])
    return None


def _match_shot(text: str) -> str:
    low = text.lower()
    for key, val in _SHOT_KEYS.items():
        if key in text or key in low:
            return val
    return ""


def _match_from_hints(text: str, category: str) -> tuple:
    hints = load_tag_hints()
    bucket = hints.get(category, {})
    keys = sorted(bucket.keys(), key=len, reverse=True)
    low = text.lower()
    for key in keys:
        if key in text or key.lower() in low:
            return key, bucket[key]
    return "", ""


def _extract_phrases(text: str) -> tuple:
    """Map known CN phrases to tags; return (tags_list, residual_text)."""
    residual = text
    tags = []
    for pattern, tag in _PHRASE_MAP:
        if re.search(pattern, residual):
            tags.append(tag)
            residual = re.sub(pattern, " ", residual)
    return tags, residual


def _clean_residual(text: str, drop_keys: list) -> str:
    cleaned = text
    # Longer keys first
    for key in sorted((k for k in drop_keys if k), key=len, reverse=True):
        cleaned = cleaned.replace(key, " ")
    cleaned = _SIZE_RE.sub(" ", cleaned)
    cleaned = _STEPS_RE.sub(" ", cleaned)
    cleaned = _CFG_RE.sub(" ", cleaned)
    cleaned = _SEED_RE.sub(" ", cleaned)
    cleaned = _BATCH_RE.sub(" ", cleaned)
    cleaned = _ARTIST_AT.sub(" ", cleaned)
    # Drop filler words / punctuation leftovers
    for w in (
        "风格", "的样子", "画风", "请画", "帮我画", "生成", "一张", "一个",
        "的", "了", "着", "在", "里", "中", "和", "与", "以及", "还有",
        "style", "please", "draw", "generate", "an", "a", "the", "of",
    ):
        cleaned = cleaned.replace(w, " ")
    cleaned = re.sub(r"[,，。.!！?？、；;：:\s]+", " ", cleaned).strip()
    # If mostly CJK leftovers shorter than 2 chars each, drop
    tokens = [t for t in cleaned.split() if len(t) >= 2]
    return " ".join(tokens)


def _rule_plan(command: str) -> Dict[str, Any]:
    plan = _empty_plan(command)
    text = command.strip()
    if not text:
        plan["notes"].append("empty command")
        return plan

    plan["nsfw"] = _detect_nsfw(text)
    plan["template"] = _detect_template(text)
    plan["ref_image"] = _extract_ref_image(text)

    size = _match_size(text)
    if size:
        plan["width"], plan["height"] = size

    m = _STEPS_RE.search(text)
    if m:
        plan["steps"] = max(1, min(150, int(m.group(1))))

    m = _CFG_RE.search(text)
    if m:
        plan["cfg"] = float(m.group(1))

    m = _SEED_RE.search(text)
    if m:
        plan["seed"] = int(m.group(1))

    m = _BATCH_RE.search(text)
    if m:
        plan["batch_size"] = max(1, min(8, int(m.group(1))))

    # Ref-adapter defaults when chosen and user did not specify size/cfg
    if plan.get("template") == "anima_ref_adapter":
        if not size:
            plan["width"], plan["height"] = 832, 1216
        if not _CFG_RE.search(text):
            plan["cfg"] = 4.5

    artists = _ARTIST_AT.findall(text)
    if artists:
        plan["artists"] = [a.strip() for a in artists]

    char_key, char_tags = _match_from_hints(text, "characters")
    style_key, style_tags = _match_from_hints(text, "styles")
    mood_key, mood_tags = _match_from_hints(text, "moods")
    shot = _match_shot(text)
    shot_key_for_hint = ""
    shot_tags = ""
    if shot:
        # Prefer hint tags if a CN shot key appears
        for k in load_tag_hints().get("shots", {}):
            if k in text:
                shot_key_for_hint = k
                shot_tags = load_tag_hints()["shots"][k]
                break

    phrase_tags, after_phrases = _extract_phrases(text)

    expanded = expand_tags(text, char_key=char_key, style_key=style_key)

    subject_parts = []
    if char_tags:
        subject_parts.append(char_tags)
        plan["notes"].append(f"character:{char_key}")
    if expanded.get("character_extra"):
        subject_parts.append(expanded["character_extra"])
    if phrase_tags:
        subject_parts.extend(phrase_tags)
        plan["notes"].append("phrases:" + "+".join(phrase_tags))

    residual = _clean_residual(
        after_phrases,
        [char_key, style_key, mood_key, shot_key_for_hint],
    )
    # Only keep residual if it still has useful latin tags or long CJK
    if residual:
        # Avoid dumping pure short CJK crumbs
        if re.search(r"[A-Za-z]{3,}", residual) or len(residual) >= 4:
            # If residual is still mostly CJK without mapping, skip adding raw CJK
            if re.fullmatch(r"[\u4e00-\u9fff\s]+", residual):
                plan["notes"].append(f"unmapped_cn:{residual}")
            else:
                subject_parts.append(residual)

    plan["subject"] = ", ".join(p for p in subject_parts if p)
    plan["style"] = style_tags or expanded.get("style_extra", "")
    if style_key:
        plan["notes"].append(f"style:{style_key}")
    plan["mood"] = mood_tags or expanded.get("mood_extra", "")
    if mood_key:
        plan["notes"].append(f"mood:{mood_key}")
    plan["shot"] = shot_tags or (shot if shot else "")
    if plan["shot"]:
        plan["notes"].append(f"shot:{shot or shot_key_for_hint or 'hint'}")

    if expanded.get("extra_tags"):
        plan["extra_tags"] = list(expanded["extra_tags"])

    if not plan["subject"]:
        plan["subject"] = "1girl, beautiful detailed eyes, looking at viewer"
        plan["notes"].append("fallback subject")

    return plan


def _llm_plan(command: str, fallback: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    base = os.environ.get("AGENT_ANIMA_LLM_BASE", "").rstrip("/")
    key = os.environ.get("AGENT_ANIMA_LLM_KEY", "")
    model = os.environ.get("AGENT_ANIMA_LLM_MODEL", "gpt-4o-mini")
    if not base or not key:
        return None

    system = (
        "You convert anime image generation requests into JSON. "
        "Return ONLY JSON with keys: subject, style, artists (list), shot, mood, "
        "nsfw (bool), template (auto|stock_anima|easyuse_aio|spectrum_ksampler|anima_ref_adapter), "
        "ref_image (filename in ComfyUI input or empty), width, height, steps, cfg, seed, batch_size, extra_tags (list), notes (list). "
        "subject/style/mood/shot should be Danbooru-style English tags when possible. "
        "Defaults: width=512 height=512 steps=30 cfg=12.2 seed=-1 batch_size=1."
    )
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": command},
        ],
        "temperature": 0.3,
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
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        content = raw["choices"][0]["message"]["content"]
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)
        data = json.loads(content)
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        KeyError,
        IndexError,
        json.JSONDecodeError,
        TimeoutError,
        OSError,
    ):
        return None

    plan = dict(fallback)
    for k in (
        "subject", "style", "shot", "mood", "nsfw", "template", "ref_image",
        "width", "height", "steps", "cfg", "seed", "batch_size",
    ):
        if k in data and data[k] is not None and data[k] != "":
            plan[k] = data[k]
    if isinstance(data.get("artists"), list):
        plan["artists"] = data["artists"]
    if isinstance(data.get("extra_tags"), list):
        plan["extra_tags"] = data["extra_tags"]
    if isinstance(data.get("notes"), list):
        plan["notes"] = list(plan.get("notes") or []) + data["notes"]
    plan["source"] = "llm"
    return plan


def plan_command(
    command: str,
    use_llm: bool = True,
    template: Optional[str] = None,
    ref_image: Optional[str] = None,
) -> Dict[str, Any]:
    """Parse NL command into a structured generation plan."""
    plan = _rule_plan(command or "")
    if template:
        plan["template"] = str(template).strip() or plan.get("template") or "auto"
    if ref_image:
        plan["ref_image"] = str(ref_image).strip()
        if plan.get("template") in ("", "auto", None):
            plan["template"] = "anima_ref_adapter"
        # Apply ref-adapter size/cfg defaults if still stock-like
        if plan.get("template") == "anima_ref_adapter":
            if plan.get("width") == DEFAULT_WIDTH and plan.get("height") == DEFAULT_HEIGHT:
                plan["width"], plan["height"] = 832, 1216
            if float(plan.get("cfg", DEFAULT_CFG)) == float(DEFAULT_CFG):
                plan["cfg"] = 4.5
    if use_llm:
        refined = _llm_plan(command or "", plan)
        if refined:
            if template:
                refined["template"] = str(template).strip() or refined.get("template") or "auto"
            if ref_image:
                refined["ref_image"] = str(ref_image).strip()
                if refined.get("template") in ("", "auto", None):
                    refined["template"] = "anima_ref_adapter"
            return refined
    return plan
