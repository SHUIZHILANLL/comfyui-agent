"""Pluggable ComfyUI workflow templates for Agent Anima."""

from .registry import (
    TEMPLATES,
    get_template,
    list_templates,
    select_template,
    build_with_template,
)

__all__ = [
    "TEMPLATES",
    "get_template",
    "list_templates",
    "select_template",
    "build_with_template",
]
