#!/usr/bin/env python3
"""Self-test without a live ComfyUI server."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

# Import as package submodule style when copied under custom_nodes,
# or flat when run from inside the folder.
sys.path.insert(0, str(ROOT))
from agent import discovery  # type: ignore
from agent.templates import registry, stock_anima, easyuse_aio  # type: ignore
from agent.workflow_builder import build_workflow, build_workflow_smart  # type: ignore
from agent.planner import plan_command  # type: ignore
from agent.prompt_writer import write_prompts  # type: ignore
from agent.ui_graph import api_to_ui_workflow, ui_workflow_summary  # type: ignore


def mock_object_info_stock_only():
    nodes = {
        "UNETLoader": {"input": {"required": {}}},
        "CLIPLoader": {"input": {"required": {}}},
        "VAELoader": {"input": {"required": {}}},
        "EmptyLatentImage": {"input": {"required": {}}},
        "CLIPTextEncode": {"input": {"required": {}}},
        "KSampler": {"input": {"required": {}}},
        "VAEDecode": {"input": {"required": {}}},
        "SaveImage": {"input": {"required": {}}},
        "LoadImage": {"input": {"required": {}}},
    }
    return nodes


def mock_object_info_with_easyuse_safe():
    info = mock_object_info_stock_only()
    info["EasyUseAnimaAIOGenerator"] = {
        "input": {
            "required": {
                "prompt": ["STRING", {"default": ""}],
                "negative": ["STRING", {"default": ""}],
                "width": ["INT", {"default": 512}],
                "height": ["INT", {"default": 512}],
                "steps": ["INT", {"default": 30}],
                "cfg": ["FLOAT", {"default": 12.2}],
                "seed": ["INT", {"default": 0}],
            }
        }
    }
    return info


def mock_object_info_with_easyuse_unsafe():
    info = mock_object_info_stock_only()
    info["EasyUseAnimaAIOGenerator"] = {
        "input": {
            "required": {
                "model": ["MODEL"],
                "positive": ["CONDITIONING"],
                "negative": ["CONDITIONING"],
                "latent_image": ["LATENT"],
            }
        }
    }
    return info


def mock_object_info_with_ref_adapter():
    info = mock_object_info_stock_only()
    info["AnimaRefAdapter"] = {
        "input": {
            "required": {
                "model": ["MODEL"],
                "vae": ["VAE"],
                "image": ["IMAGE"],
                "lora_name": [["anima_ref_adapter_v2_r64.safetensors"]],
                "ref_guidance": ["FLOAT", {"default": 4.5}],
                "correction": [["apg", "rescale", "none"]],
                "strength": ["FLOAT", {"default": 1.0}],
                "ref_end": ["FLOAT", {"default": 1.0}],
                "ref_megapixels": ["FLOAT", {"default": 1.0}],
            }
        }
    }
    return info


def main() -> int:
    errors = []

    # discovery graceful when ComfyUI down
    fetched = discovery.list_object_info("http://127.0.0.1:9", force=True, timeout=1.0)
    if fetched.get("ok"):
        errors.append("expected object_info fail on closed port")
    caps_empty = discovery.available_capabilities({}, discovery_error=fetched.get("error"))
    if caps_empty.get("has_easyuse_aio"):
        errors.append("empty caps should not claim easyuse")
    if caps_empty.get("has_anima_ref_adapter"):
        errors.append("empty caps should not claim anima_ref_adapter")

    # stock build via legacy API
    wf = build_workflow("1girl, cat ears", "lowres", width=768, height=1152, seed=42)
    assert wf["5"]["inputs"]["text"].startswith("1girl")
    assert wf["7"]["class_type"] == "KSampler"
    assert wf["7"]["inputs"]["seed"] == 42
    print("OK stock build_workflow")

    # planner template keywords
    p1 = plan_command("用 easyuse aio 画猫耳少女", use_llm=False)
    if p1.get("template") != "easyuse_aio":
        errors.append(f"expected easyuse_aio template, got {p1.get('template')}")
    p2 = plan_command("原生工作流画风景", use_llm=False)
    if p2.get("template") != "stock_anima":
        errors.append(f"expected stock_anima, got {p2.get('template')}")
    p3 = plan_command("spectrum 采样出一张", use_llm=False)
    if p3.get("template") != "spectrum_ksampler":
        errors.append(f"expected spectrum_ksampler, got {p3.get('template')}")
    p4 = plan_command("用参考图锁人物，咖啡馆坐着", use_llm=False)
    if p4.get("template") != "anima_ref_adapter":
        errors.append(f"expected anima_ref_adapter, got {p4.get('template')}")
    if p4.get("width") != 832 or float(p4.get("cfg")) != 4.5:
        errors.append(f"ref adapter defaults size/cfg, got {p4.get('width')} cfg={p4.get('cfg')}")
    p5 = plan_command("咖啡馆", use_llm=False, ref_image="char.png")
    if p5.get("template") != "anima_ref_adapter" or p5.get("ref_image") != "char.png":
        errors.append(f"ref_image arg should force template, got {p5}")
    p6 = plan_command("参考图:hero.webp 人物一致站在雨里", use_llm=False)
    if p6.get("ref_image") != "hero.webp":
        errors.append(f"extract ref_image failed: {p6.get('ref_image')}")
    print("OK planner template keywords")

    # selection without easyuse → stock
    caps_no = discovery.available_capabilities(mock_object_info_stock_only())
    sel, note = registry.select_template({"template": "easyuse_aio"}, caps_no)
    if sel != "stock_anima":
        errors.append(f"select without install should stock, got {sel}")
    print("OK select fallback when missing:", note)

    # selection with flag
    caps_yes = discovery.available_capabilities(mock_object_info_with_easyuse_safe())
    if not caps_yes.get("has_easyuse_aio"):
        errors.append("caps should detect EasyUseAnimaAIOGenerator")
    sel2, _ = registry.select_template({"template": "easyuse_aio"}, caps_yes)
    if sel2 != "easyuse_aio":
        errors.append(f"expected select easyuse_aio, got {sel2}")
    print("OK select easyuse when present")

    plan = {"width": 512, "height": 512, "steps": 20, "cfg": 7.0, "seed": 1, "batch_size": 1, "template": "easyuse_aio"}
    prompts = {"positive": "1girl", "negative": "lowres"}

    # safe AiO builds real easyuse graph
    built = build_workflow_smart(
        plan,
        prompts["positive"],
        prompts["negative"],
        caps=caps_yes,
        object_info=mock_object_info_with_easyuse_safe(),
        template="easyuse_aio",
        seed=1,
    )
    if built.get("template_used") != "easyuse_aio":
        errors.append(f"safe aio should use easyuse, got {built}")
    if built["workflow"]["1"]["class_type"] != "EasyUseAnimaAIOGenerator":
        errors.append("expected AiO class_type")
    print("OK easyuse safe build")

    # unsafe AiO falls back
    built2 = build_workflow_smart(
        plan,
        prompts["positive"],
        prompts["negative"],
        caps=discovery.available_capabilities(mock_object_info_with_easyuse_unsafe()),
        object_info=mock_object_info_with_easyuse_unsafe(),
        template="easyuse_aio",
        seed=1,
    )
    if built2.get("template_used") != "stock_anima":
        errors.append(f"unsafe aio should fallback stock, got {built2.get('template_used')}")
    if not built2.get("fallback_reason"):
        errors.append("expected fallback_reason")
    if built2["workflow"]["7"]["class_type"] != "KSampler":
        errors.append("fallback workflow should be stock KSampler")
    print("OK easyuse unsafe fallback:", built2.get("fallback_reason"))

    # auto → stock
    built3 = build_workflow_smart(
        {"template": "auto", "width": 512, "height": 512, "steps": 30, "cfg": 12.2, "seed": 2},
        "solo, 1girl",
        "lowres",
        caps=caps_yes,
        object_info=mock_object_info_with_easyuse_safe(),
    )
    if built3.get("template_used") != "stock_anima":
        errors.append("auto should prefer stock")
    print("OK auto → stock")

    # --- Anima Ref Adapter ---
    caps_ref_absent = discovery.available_capabilities(mock_object_info_stock_only())
    if caps_ref_absent.get("has_anima_ref_adapter"):
        errors.append("stock-only should not have has_anima_ref_adapter")
    sel_miss, note_miss = registry.select_template(
        {"template": "anima_ref_adapter", "ref_image": "a.png"}, caps_ref_absent
    )
    if sel_miss != "stock_anima":
        errors.append(f"ref adapter absent should select stock, got {sel_miss}")
    print("OK ref adapter absent → stock:", note_miss)

    # folder-name detection
    caps_folder = discovery.available_capabilities(
        {},
        folders=["ComfyUI-Anima-Ref-Adapter", "other"],
        discovery_error="offline",
    )
    if not caps_folder.get("has_anima_ref_adapter"):
        errors.append("folder scan should set has_anima_ref_adapter")

    caps_ref = discovery.available_capabilities(mock_object_info_with_ref_adapter())
    if not caps_ref.get("has_anima_ref_adapter"):
        errors.append("caps should detect AnimaRefAdapter")
    sel_ref, note_ref = registry.select_template(
        {"template": "anima_ref_adapter", "ref_image": "char.png"}, caps_ref
    )
    if sel_ref != "anima_ref_adapter":
        errors.append(f"expected select anima_ref_adapter, got {sel_ref}")
    # auto + ref_image
    sel_auto, note_auto = registry.select_template(
        {"template": "auto", "ref_image": "char.png"}, caps_ref
    )
    if sel_auto != "anima_ref_adapter":
        errors.append(f"auto+ref_image should pick ref adapter, got {sel_auto}")
    print("OK select ref adapter:", note_ref, "/", note_auto)

    ref_plan = {
        "template": "anima_ref_adapter",
        "ref_image": "char.png",
        "width": 512,
        "height": 512,
        "steps": 30,
        "cfg": 12.2,
        "seed": 7,
        "batch_size": 1,
        "subject": "1girl, silver hair, blue eyes, cafe",
        "shot": "cowboy shot",
        "mood": "warm light",
    }
    pos, neg, notes = write_prompts(ref_plan)
    if "silver hair" in pos.lower() or "blue eyes" in pos.lower():
        errors.append(f"scene-only prompt should strip appearance, got: {pos}")
    if "1girl" not in pos.lower():
        errors.append(f"scene-only should keep 1girl: {pos}")
    if "ref_adapter_scene_only" not in notes:
        errors.append(f"expected scene_only note: {notes}")
    print("OK prompt_writer scene-only:", pos[:120])

    built_ref = build_workflow_smart(
        ref_plan,
        pos,
        neg,
        caps=caps_ref,
        object_info=mock_object_info_with_ref_adapter(),
        template="anima_ref_adapter",
        seed=7,
    )
    if built_ref.get("template_used") != "anima_ref_adapter":
        errors.append(f"ref build should use anima_ref_adapter, got {built_ref.get('template_used')}")
    wf_ref = built_ref["workflow"]
    class_types = {n["class_type"] for n in wf_ref.values()}
    if "AnimaRefAdapter" not in class_types:
        errors.append("workflow missing AnimaRefAdapter")
    if "LoadImage" not in class_types:
        errors.append("workflow missing LoadImage")
    # sample API node ids
    if wf_ref.get("4", {}).get("class_type") != "LoadImage":
        errors.append("node 4 should be LoadImage")
    if wf_ref.get("5", {}).get("class_type") != "AnimaRefAdapter":
        errors.append("node 5 should be AnimaRefAdapter")
    if wf_ref["5"]["inputs"].get("model") != ["1", 0]:
        errors.append("adapter model should wire from UNET 1")
    if wf_ref["9"]["inputs"].get("model") != ["5", 0]:
        errors.append("KSampler model should wire from adapter 5")
    if wf_ref["4"]["inputs"].get("image") != "char.png":
        errors.append("LoadImage should use ref_image filename")
    if abs(float(wf_ref["9"]["inputs"]["cfg"]) - 4.5) > 1e-6:
        errors.append(f"expected cfg 4.5 for stock-like plan, got {wf_ref['9']['inputs']['cfg']}")
    if wf_ref["8"]["inputs"]["width"] != 832 or wf_ref["8"]["inputs"]["height"] != 1216:
        errors.append(
            f"expected 832x1216 when stock size unset, got "
            f"{wf_ref['8']['inputs']['width']}x{wf_ref['8']['inputs']['height']}"
        )
    print("OK ref adapter workflow node ids 1..11")

    # missing ref_image → fallback stock
    built_nofile = build_workflow_smart(
        {"template": "anima_ref_adapter", "width": 512, "height": 512, "steps": 30, "cfg": 12.2, "seed": 3},
        "1girl, cafe",
        "lowres",
        caps=caps_ref,
        object_info=mock_object_info_with_ref_adapter(),
        template="anima_ref_adapter",
        seed=3,
    )
    if built_nofile.get("template_used") != "stock_anima":
        errors.append("missing ref_image should fallback stock")
    if "ref_image" not in (built_nofile.get("fallback_reason") or ""):
        errors.append(f"expected ref_image fallback reason: {built_nofile.get('fallback_reason')}")
    print("OK ref adapter missing image → stock")

    # --- API → UI workflow ---
    stock_api = build_workflow("1girl, cafe", "lowres", width=512, height=512, seed=11)
    ui_stock = api_to_ui_workflow(stock_api, title="stock test")
    types_stock = {n["type"] for n in ui_stock["nodes"]}
    for need in ("UNETLoader", "CLIPLoader", "VAELoader", "KSampler", "VAEDecode", "SaveImage", "CLIPTextEncode", "EmptyLatentImage"):
        if need not in types_stock:
            errors.append(f"stock UI missing {need}")
    if not ui_stock.get("links"):
        errors.append("stock UI should have links")
    # KSampler widgets include control_after_generate
    ks = next(n for n in ui_stock["nodes"] if n["type"] == "KSampler")
    if len(ks.get("widgets_values") or []) < 7:
        errors.append(f"KSampler widgets_values too short: {ks.get('widgets_values')}")
    print("OK api→ui stock:", ui_workflow_summary(ui_stock))

    # ref adapter API→UI
    info_ref = mock_object_info_with_ref_adapter()
    caps_ref_ui = discovery.available_capabilities(info_ref)
    built_ref_ui = build_workflow_smart(
        {
            "template": "anima_ref_adapter",
            "ref_image": "char.png",
            "width": 832,
            "height": 1216,
            "steps": 30,
            "cfg": 4.5,
            "seed": 9,
        },
        "1girl, solo, cafe",
        "lowres",
        caps=caps_ref_ui,
        object_info=info_ref,
        template="anima_ref_adapter",
        seed=9,
    )
    ui_ref = api_to_ui_workflow(built_ref_ui["workflow"], title="ref test")
    types_ref = {n["type"] for n in ui_ref["nodes"]}
    for need in ("AnimaRefAdapter", "LoadImage", "UNETLoader", "KSampler", "SaveImage"):
        if need not in types_ref:
            errors.append(f"ref UI missing {need}")
    adapter = next(n for n in ui_ref["nodes"] if n["type"] == "AnimaRefAdapter")
    if not adapter.get("inputs") or adapter["inputs"][0].get("link") is None:
        errors.append("AnimaRefAdapter model input should be linked")
    load = next(n for n in ui_ref["nodes"] if n["type"] == "LoadImage")
    if not (load.get("widgets_values") or [None])[0]:
        errors.append("LoadImage widgets_values should include filename")
    print("OK api→ui anima_ref_adapter:", ui_workflow_summary(ui_ref))

    # folder scan on missing path
    scan = discovery.scan_custom_node_folders("/tmp/does-not-exist-agent-anima")
    if scan.get("ok"):
        errors.append("scan missing path should fail")
    print("OK folder scan miss")

    if errors:
        print("FAILED:")
        for e in errors:
            print(" -", e)
        return 1
    print("ALL SELF-CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
