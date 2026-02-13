"""
Image Generation Module

Provides local image generation via ComfyUI with SDXL.
"""

from .comfyui_client import ComfyUIClient
from .prompt_builder import build_image_prompt, STYLE_PRESETS

__all__ = [
    "ComfyUIClient",
    "build_image_prompt",
    "STYLE_PRESETS",
]
