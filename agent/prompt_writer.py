"""Turn a plan dict into Anima / Danbooru-style positive & negative prompts."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from .research import load_tag_hints

DEFAULT_NEGATIVE = (
    "mutated hands and fingers,mutated,mutated hands,lowres,bad anatomy,bad hands,"
    "text,error,missing fingers,extra digit,fewer digits,cropped,worst quality,"
    "low quality,normal quality,jpeg artifacts,signature,watermark,username,blurry,"
    "missing arms,long neck,Humpbacked,（Q version）,mesugaki, blurry image, blurry, "
    "extra fingers, oversaturated, overexposed, bad lighting"
)

REF_ADAPTER_NEGATIVE = (
    "worst quality, low quality, score_1, score_2, score_3, artist name, blurry, "
    "jpeg artifacts, chromatic aberration"
)

NSFW_POS = "(((nsfw))), breasts, detailed body"
SFW_EXTRA_NEG = ", nsfw, nude, nipples, explicit"

# Appearance / outfit / named-character tags to drop for ref-adapter scene prompts
_APPEARANCE_DROP = re.compile(
    r"^(?:"
    r".*\b(?:hair|eyes|bangs|ponytail|twintails|braid|ahoge)\b|"
    r".*\b(?:dress|skirt|shirt|jacket|uniform|kimono|hoodie|coat|boots|shoes|hat|ribbon|bow)\b|"
    r".*\b(?:breasts|cleavage|thighs|bare\s+shoulders)\b|"
    r"artist:.*|"
    r"(?:silver|white|black|blonde|brown|red|blue|pink|purple|green|orange|gray|grey)\s+hair|"
    r"(?:blue|red|green|brown|purple|pink|yellow|heterochromia)\s+eyes|"
    r"long hair|short hair|very long hair|medium hair|"
    r"cat ears|fox ears|rabbit ears|animal ears|animal ear fluff|"
    r"cat girl|fox girl|"
    r"rem\b|ram\b|asuka|rei\b|miku|hutao|hu tao|ganyu|yelan"
    r")$",
    re.I,
)

_KEEP_SUBJECT = re.compile(
    r"^(?:1girl|1boy|2girls|2boys|solo|multiple girls|multiple boys|"
    r"smile|smiling|looking at viewer|looking back|sitting|standing|walking|running|"
    r"holding(?:\s+\w+)?|cowboy shot|close-up|upper body|full body|from above|from below|"
    r"profile|from behind|outdoors|indoors|day|night|window|cafe|beach|ocean|classroom|"
    r"under tree|in the rain|falling petals|sunlight|spring|cherry blossoms|"
    r"dynamic pose|dynamic angle)$",
    re.I,
)


def _join(*parts: str) -> str:
    items = []
    seen = set()
    for part in parts:
        if not part:
            continue
        for tag in part.split(","):
            t = tag.strip()
            if not t:
                continue
            key = t.lower()
            if key in seen:
                continue
            seen.add(key)
            items.append(t)
    return ", ".join(items)


def _split_tags(text: str) -> List[str]:
    return [t.strip() for t in (text or "").split(",") if t.strip()]


def _scene_only_positive(plan: Dict[str, Any], quality: str) -> Tuple[str, List[str]]:
    """Build ref-adapter prompt: quality + 1girl/solo + scene/pose/shot/mood."""
    notes: List[str] = []
    kept: List[str] = []
    dropped: List[str] = []

    subject_tags = _split_tags(plan.get("subject") or "")
    for t in subject_tags:
        low = t.lower()
        if _KEEP_SUBJECT.match(t) or low in ("1girl", "1boy", "solo"):
            kept.append(t)
        elif _APPEARANCE_DROP.match(t) or _APPEARANCE_DROP.match(low):
            dropped.append(t)
        elif re.search(r"\b(hair|eyes|dress|skirt|uniform|kimono)\b", low):
            dropped.append(t)
        else:
            # Keep likely scene/action crumbs
            kept.append(t)

    # Ensure subject count tags
    low_joined = ", ".join(kept).lower()
    if "1boy" not in low_joined and "1girl" not in low_joined and "2girls" not in low_joined:
        kept.insert(0, "1girl")
        notes.append("ref_adapter_added=1girl")
    if "solo" not in low_joined and "multiple" not in low_joined:
        # insert after 1girl/1boy if present
        if kept and kept[0].lower() in ("1girl", "1boy"):
            kept.insert(1, "solo")
        else:
            kept.insert(0, "solo")

    # Prefer official-ish quality line for ref adapter
    ref_quality = "masterpiece, best quality, score_7, safe"
    if "score_7" not in (quality or ""):
        quality_use = ref_quality
    else:
        quality_use = quality

    # Do not attach artists / heavy style / character extras for ref adapter
    positive = _join(
        quality_use,
        ", ".join(kept),
        plan.get("shot") or "",
        plan.get("mood") or "",
        # light style ok if it looks like lighting/scene, not artist
        "" if (plan.get("style") or "").lower().startswith("artist") else (plan.get("style") or ""),
    )
    if dropped:
        notes.append("ref_adapter_stripped=" + "+".join(dropped[:12]))
    notes.append("ref_adapter_scene_only=1")
    notes.append("advise: prefer scene/pose only; identity comes from reference image")
    return positive, notes


def write_prompts(plan: Dict[str, Any]) -> Tuple[str, str, str]:
    """Return (positive, negative, notes)."""
    hints = load_tag_hints()
    quality = hints.get("quality", "masterpiece, best quality, highres")

    artists = plan.get("artists") or []
    artist_tags = ", ".join(
        f"artist:{a}" if not a.startswith("artist:") else a for a in artists
    )

    nsfw = bool(plan.get("nsfw"))
    nsfw_bit = NSFW_POS if nsfw else ""

    extra = plan.get("extra_tags") or []
    extra_str = ", ".join(extra) if isinstance(extra, list) else str(extra or "")

    notes_list = list(plan.get("notes") or [])
    template = (plan.get("template") or "").strip().lower()

    if template == "anima_ref_adapter":
        positive, ref_notes = _scene_only_positive(plan, quality)
        if nsfw:
            positive = _join(positive, nsfw_bit)
        notes_list.extend(ref_notes)
        negative = REF_ADAPTER_NEGATIVE
        if not nsfw:
            negative = negative + SFW_EXTRA_NEG
    else:
        positive = _join(
            quality,
            plan.get("subject") or "",
            plan.get("shot") or "",
            plan.get("mood") or "",
            plan.get("style") or "",
            artist_tags,
            nsfw_bit,
            extra_str,
            "dynamic pose, dynamic angle",
        )
        negative = DEFAULT_NEGATIVE
        if not nsfw:
            negative = negative + SFW_EXTRA_NEG

    notes_list.append(f"source={plan.get('source', 'rules')}")
    notes_list.append(f"nsfw={nsfw}")
    if plan.get("ref_image"):
        notes_list.append(f"ref_image={plan.get('ref_image')}")
    notes = "; ".join(str(n) for n in notes_list)
    return positive, negative, notes
