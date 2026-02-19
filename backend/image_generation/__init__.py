"""
Image Generation Module

Provides local image generation via ComfyUI with SDXL.
Supports fine-grained parameter control, iterative refinement,
LoRA integration, and recipe management.
"""

from .comfyui_client import ComfyUIClient
from .prompt_builder import build_image_prompt, STYLE_PRESETS
from .generation_params import (
    GenerationParams,
    GenerationType,
    LoRAConfig,
    Sampler,
    Scheduler,
    STYLE_DEFAULTS,
    get_style_defaults,
)
from .param_resolver import ParamResolver
from .workflows import WorkflowBuilder
from .lora_manager import LoRAManager, LoRAInfo, get_lora_manager
from .recipes import Recipe, RecipeManager, get_recipe_manager

__all__ = [
    # Core client
    "ComfyUIClient",
    # Prompt building
    "build_image_prompt",
    "STYLE_PRESETS",
    # Generation parameters
    "GenerationParams",
    "GenerationType",
    "LoRAConfig",
    "Sampler",
    "Scheduler",
    "STYLE_DEFAULTS",
    "get_style_defaults",
    # Parameter resolution
    "ParamResolver",
    # Workflows
    "WorkflowBuilder",
    # LoRA management
    "LoRAManager",
    "LoRAInfo",
    "get_lora_manager",
    # Recipe management
    "Recipe",
    "RecipeManager",
    "get_recipe_manager",
]
