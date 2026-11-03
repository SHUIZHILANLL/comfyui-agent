"""comfyui-agent-anima — NL command → Anima workflow + prompts + queue."""

from __future__ import annotations

WEB_DIRECTORY = "./web"

from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

# Register HTTP routes when loaded inside ComfyUI
try:
    from .routes import register_routes

    register_routes()
except Exception as e:
    print(f"[agent_anima] routes not registered: {e}")

__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
]
