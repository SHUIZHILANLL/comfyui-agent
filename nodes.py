"""ComfyUI nodes for Agent Anima."""

from __future__ import annotations

import json
from typing import Any, Dict, Tuple

from .agent.planner import plan_command
from .agent.prompt_writer import write_prompts
from .agent.workflow_builder import build_workflow, workflow_to_json

# Optional folder_paths for model dropdowns
try:
    import folder_paths  # type: ignore
except ImportError:
    folder_paths = None  # type: ignore


def _list_or_default(kind: str, default: str) -> list:
    if folder_paths is None:
        return [default]
    try:
        if kind == "unet":
            names = folder_paths.get_filename_list("diffusion_models") or []
            if not names:
                names = folder_paths.get_filename_list("unet") or []
        elif kind == "clip":
            names = folder_paths.get_filename_list("text_encoders") or []
            if not names:
                names = folder_paths.get_filename_list("clip") or []
        elif kind == "vae":
            names = folder_paths.get_filename_list("vae") or []
        else:
            names = []
        if default not in names:
            names = [default] + list(names)
        return names or [default]
    except Exception:
        return [default]


class AgentAnimaPromptWriter:
    """Command → positive / negative / notes."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "command": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "雨夜里撑伞的银发少女，新海诚风格",
                    },
                ),
            },
            "optional": {
                "use_llm": ("BOOLEAN", {"default": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("positive_prompt", "negative_prompt", "notes")
    FUNCTION = "write"
    CATEGORY = "Agent Anima"

    def write(self, command: str, use_llm: bool = True):
        plan = plan_command(command, use_llm=use_llm)
        pos, neg, notes = write_prompts(plan)
        return (pos, neg, notes)


class AgentAnimaCommand:
    """NL command → prompts + API workflow JSON + status.

    Does not block on GPU. Set run_now=True to queue via localhost HTTP
    (ComfyUI must be serving). Otherwise only builds prompts/workflow.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "command": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "雨夜里撑伞的银发少女，新海诚风格",
                    },
                ),
                "width": ("INT", {"default": 512, "min": 64, "max": 4096, "step": 8}),
                "height": ("INT", {"default": 512, "min": 64, "max": 4096, "step": 8}),
                "steps": ("INT", {"default": 30, "min": 1, "max": 150}),
                "cfg": ("FLOAT", {"default": 12.2, "min": 0.0, "max": 30.0, "step": 0.1}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 0xFFFFFFFFFFFFFFFF}),
                "batch_size": ("INT", {"default": 1, "min": 1, "max": 8}),
                "unet_name": (_list_or_default("unet", "anima-aesthetic-v1.1.safetensors"),),
                "clip_name": (_list_or_default("clip", "qwen_3_06b_base.safetensors"),),
                "vae_name": (_list_or_default("vae", "qwen_image_vae.safetensors"),),
                "run_now": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "use_llm": ("BOOLEAN", {"default": True}),
                "comfy_url": (
                    "STRING",
                    {"default": "http://127.0.0.1:8188", "multiline": False},
                ),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("positive_prompt", "negative_prompt", "workflow_json", "status")
    FUNCTION = "execute"
    CATEGORY = "Agent Anima"
    OUTPUT_NODE = True

    def execute(
        self,
        command: str,
        width: int = 512,
        height: int = 512,
        steps: int = 30,
        cfg: float = 12.2,
        seed: int = -1,
        batch_size: int = 1,
        unet_name: str = "anima-aesthetic-v1.1.safetensors",
        clip_name: str = "qwen_3_06b_base.safetensors",
        vae_name: str = "qwen_image_vae.safetensors",
        run_now: bool = False,
        use_llm: bool = True,
        comfy_url: str = "http://127.0.0.1:8188",
    ):
        plan = plan_command(command, use_llm=use_llm)
        # Node widget overrides beat plan defaults when provided
        plan["width"] = width
        plan["height"] = height
        plan["steps"] = steps
        plan["cfg"] = cfg
        plan["seed"] = seed
        plan["batch_size"] = batch_size

        pos, neg, notes = write_prompts(plan)
        wf = build_workflow(
            pos,
            neg,
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
        wf_json = workflow_to_json(wf)

        status_parts = [f"planned ok; {notes}"]
        if run_now:
            try:
                from .agent.runner import run_generation

                result = run_generation(
                    wf,
                    base_url=comfy_url or "http://127.0.0.1:8188",
                    prefer_internal=False,
                    wait=True,
                    timeout_s=600.0,
                )
                if result.get("ok"):
                    imgs = result.get("images") or []
                    status_parts.append(
                        f"queued via {result.get('via')}; prompt_id={result.get('prompt_id')}; "
                        f"images={len(imgs)}"
                    )
                    if imgs:
                        status_parts.append(
                            "files=" + ", ".join(i.get("filename", "") for i in imgs)
                        )
                else:
                    status_parts.append(f"run failed: {result.get('error')}")
            except Exception as e:
                status_parts.append(f"run exception: {e}")
        else:
            status_parts.append(
                "run_now=false — use HTTP POST /agent_anima/run or set run_now=true"
            )

        status = " | ".join(status_parts)
        return {
            "ui": {"text": [status, pos[:500]]},
            "result": (pos, neg, wf_json, status),
        }


NODE_CLASS_MAPPINGS = {
    "AgentAnimaCommand": AgentAnimaCommand,
    "AgentAnimaPromptWriter": AgentAnimaPromptWriter,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "AgentAnimaCommand": "Anima Agent Command",
    "AgentAnimaPromptWriter": "Anima Agent Prompt Writer",
}
