"""
Generation Parameters

Centralized parameter system for image generation with support for
fine-grained control, iterative refinement, and LoRA integration.
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class GenerationType(Enum):
    """Type of image generation."""
    TXT2IMG = "txt2img"
    IMG2IMG = "img2img"
    VARIATION = "variation"
    INPAINT = "inpaint"
    UPSCALE = "upscale"


class Sampler(Enum):
    """Available samplers."""
    EULER = "euler"
    EULER_ANCESTRAL = "euler_ancestral"
    HEUN = "heun"
    DPM_2 = "dpm_2"
    DPM_2_ANCESTRAL = "dpm_2_ancestral"
    DPMPP_2S_ANCESTRAL = "dpmpp_2s_ancestral"
    DPMPP_2M = "dpmpp_2m"
    DPMPP_2M_SDE = "dpmpp_2m_sde"
    DPMPP_SDE = "dpmpp_sde"
    LCM = "lcm"


class Scheduler(Enum):
    """Available schedulers."""
    NORMAL = "normal"
    KARRAS = "karras"
    EXPONENTIAL = "exponential"
    SGM_UNIFORM = "sgm_uniform"
    SIMPLE = "simple"


@dataclass
class LoRAConfig:
    """Configuration for a LoRA adapter."""
    name: str  # LoRA filename (without extension)
    strength: float = 0.8  # Model strength (0.0 - 1.0)
    clip_strength: float = 0.8  # CLIP strength (0.0 - 1.0)

    def __post_init__(self):
        self.strength = max(0.0, min(1.0, self.strength))
        self.clip_strength = max(0.0, min(1.0, self.clip_strength))


@dataclass
class GenerationParams:
    """
    Complete parameters for image generation.

    This is the central parameter object that flows through the entire
    generation pipeline. It captures everything needed to reproduce
    or refine an image.
    """
    # Core prompt
    prompt: str
    negative_prompt: str = ""

    # Dimensions
    width: int = 1024
    height: int = 1024

    # Sampling
    steps: int = 30
    cfg_scale: float = 7.0
    sampler: str = "euler"  # Use string for ComfyUI compatibility
    scheduler: str = "normal"

    # Reproducibility
    seed: int = -1  # -1 = random

    # Refinement (for img2img/variations)
    denoise: float = 1.0  # < 1.0 for img2img, 1.0 for txt2img

    # LoRA configuration
    loras: list[LoRAConfig] = field(default_factory=list)

    # Source image (for img2img/variations/inpaint)
    source_image_path: Optional[str] = None
    source_image_id: Optional[str] = None

    # Mask (for inpainting)
    mask_path: Optional[str] = None

    # Iteration tracking
    generation_type: GenerationType = GenerationType.TXT2IMG
    iteration_number: int = 1
    parent_id: Optional[str] = None  # Links to previous version

    # Style tracking (for recipe saving)
    style_preset: Optional[str] = None
    mood: Optional[str] = None

    # House style integration
    house_style_applied: bool = False
    house_lora_applied: bool = False

    def __post_init__(self):
        """Validate and normalize parameters."""
        # Ensure dimensions are multiples of 8 (required by most models)
        self.width = (self.width // 8) * 8
        self.height = (self.height // 8) * 8

        # Clamp values to valid ranges
        self.steps = max(1, min(150, self.steps))
        self.cfg_scale = max(1.0, min(30.0, self.cfg_scale))
        self.denoise = max(0.0, min(1.0, self.denoise))

        # Convert string generation_type to enum if needed
        if isinstance(self.generation_type, str):
            self.generation_type = GenerationType(self.generation_type)

    def with_refinement(
        self,
        denoise: float = 0.5,
        prompt: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> "GenerationParams":
        """
        Create a copy configured for img2img refinement.

        Args:
            denoise: Denoising strength (0.1=subtle, 0.8=major)
            prompt: New prompt (or keep existing)
            parent_id: ID of the image being refined

        Returns:
            New GenerationParams configured for img2img
        """
        return GenerationParams(
            prompt=prompt or self.prompt,
            negative_prompt=self.negative_prompt,
            width=self.width,
            height=self.height,
            steps=self.steps,
            cfg_scale=self.cfg_scale,
            sampler=self.sampler,
            scheduler=self.scheduler,
            seed=-1,  # New seed for variation
            denoise=denoise,
            loras=self.loras.copy(),
            source_image_id=parent_id,
            generation_type=GenerationType.IMG2IMG,
            iteration_number=self.iteration_number + 1,
            parent_id=parent_id,
            style_preset=self.style_preset,
            mood=self.mood,
            house_style_applied=self.house_style_applied,
            house_lora_applied=self.house_lora_applied,
        )

    def with_variation(
        self,
        variation_strength: float = 0.3,
        parent_id: Optional[str] = None,
    ) -> "GenerationParams":
        """
        Create a copy configured for generating variations.

        Args:
            variation_strength: How different (0.2=similar, 0.5=moderate)
            parent_id: ID of the source image

        Returns:
            New GenerationParams configured for variation
        """
        return GenerationParams(
            prompt=self.prompt,
            negative_prompt=self.negative_prompt,
            width=self.width,
            height=self.height,
            steps=self.steps,
            cfg_scale=self.cfg_scale,
            sampler=self.sampler,
            scheduler=self.scheduler,
            seed=-1,
            denoise=variation_strength,
            loras=self.loras.copy(),
            source_image_id=parent_id,
            generation_type=GenerationType.VARIATION,
            iteration_number=self.iteration_number,
            parent_id=parent_id,
            style_preset=self.style_preset,
            mood=self.mood,
            house_style_applied=self.house_style_applied,
            house_lora_applied=self.house_lora_applied,
        )

    def to_dict(self) -> dict:
        """Serialize to dictionary for storage."""
        return {
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "width": self.width,
            "height": self.height,
            "steps": self.steps,
            "cfg_scale": self.cfg_scale,
            "sampler": self.sampler,
            "scheduler": self.scheduler,
            "seed": self.seed,
            "denoise": self.denoise,
            "loras": [{"name": l.name, "strength": l.strength, "clip_strength": l.clip_strength} for l in self.loras],
            "source_image_path": self.source_image_path,
            "source_image_id": self.source_image_id,
            "generation_type": self.generation_type.value,
            "iteration_number": self.iteration_number,
            "parent_id": self.parent_id,
            "style_preset": self.style_preset,
            "mood": self.mood,
            "house_style_applied": self.house_style_applied,
            "house_lora_applied": self.house_lora_applied,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GenerationParams":
        """Deserialize from dictionary."""
        loras = [LoRAConfig(**l) for l in data.get("loras", [])]
        gen_type = data.get("generation_type", "txt2img")
        if isinstance(gen_type, str):
            gen_type = GenerationType(gen_type)

        return cls(
            prompt=data["prompt"],
            negative_prompt=data.get("negative_prompt", ""),
            width=data.get("width", 1024),
            height=data.get("height", 1024),
            steps=data.get("steps", 30),
            cfg_scale=data.get("cfg_scale", 7.0),
            sampler=data.get("sampler", "euler"),
            scheduler=data.get("scheduler", "normal"),
            seed=data.get("seed", -1),
            denoise=data.get("denoise", 1.0),
            loras=loras,
            source_image_path=data.get("source_image_path"),
            source_image_id=data.get("source_image_id"),
            generation_type=gen_type,
            iteration_number=data.get("iteration_number", 1),
            parent_id=data.get("parent_id"),
            style_preset=data.get("style_preset"),
            mood=data.get("mood"),
            house_style_applied=data.get("house_style_applied", False),
            house_lora_applied=data.get("house_lora_applied", False),
        )


# Default parameters for different styles (expanded from prompt_builder.py)
STYLE_DEFAULTS = {
    "painterly": GenerationParams(
        prompt="",
        steps=30,
        cfg_scale=7.0,
        sampler="dpmpp_2m",
        scheduler="karras",
    ),
    "sketch": GenerationParams(
        prompt="",
        steps=20,
        cfg_scale=8.0,
        sampler="euler",
        scheduler="normal",
    ),
    "photorealistic": GenerationParams(
        prompt="",
        steps=35,
        cfg_scale=6.0,
        sampler="dpmpp_2m_sde",
        scheduler="karras",
    ),
    "abstract": GenerationParams(
        prompt="",
        steps=25,
        cfg_scale=9.0,
        sampler="euler_ancestral",
        scheduler="normal",
    ),
    "watercolor": GenerationParams(
        prompt="",
        steps=25,
        cfg_scale=7.0,
        sampler="dpmpp_2m",
        scheduler="karras",
    ),
    "digital_art": GenerationParams(
        prompt="",
        steps=30,
        cfg_scale=7.0,
        sampler="dpmpp_2m",
        scheduler="karras",
    ),
    "dreamlike": GenerationParams(
        prompt="",
        steps=35,
        cfg_scale=8.0,
        sampler="dpmpp_2m_sde",
        scheduler="karras",
    ),
    "fine_art": GenerationParams(
        prompt="",
        steps=35,
        cfg_scale=7.5,
        sampler="dpmpp_2m",
        scheduler="karras",
    ),
}


def get_style_defaults(style: str) -> GenerationParams:
    """Get default generation parameters for a style."""
    return STYLE_DEFAULTS.get(style, STYLE_DEFAULTS["digital_art"])
