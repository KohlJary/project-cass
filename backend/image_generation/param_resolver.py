"""
Parameter Resolver

Resolves final generation parameters from multiple sources:
- Base params (explicit user/tool input)
- Style presets
- House style preferences
- Saved recipes

Priority (highest to lowest):
1. Explicit overrides in base_params
2. Recipe settings (if specified)
3. House style defaults (if active)
4. Style preset defaults
5. Global defaults
"""

import logging
from typing import Optional

from .generation_params import (
    GenerationParams,
    LoRAConfig,
    get_style_defaults,
)

logger = logging.getLogger(__name__)


class ParamResolver:
    """
    Resolves final generation parameters from multiple sources.

    This ensures consistent parameter handling across all generation
    entry points (tools, art study, spells, etc.).
    """

    def resolve(
        self,
        prompt: str,
        negative_prompt: str = "",
        style: Optional[str] = None,
        mood: Optional[str] = None,
        daemon_id: Optional[str] = None,
        use_house_style: bool = True,
        use_house_lora: bool = False,
        recipe_name: Optional[str] = None,
        # Explicit overrides (highest priority)
        width: Optional[int] = None,
        height: Optional[int] = None,
        steps: Optional[int] = None,
        cfg_scale: Optional[float] = None,
        sampler: Optional[str] = None,
        scheduler: Optional[str] = None,
        seed: int = -1,
        denoise: float = 1.0,
        loras: Optional[list[LoRAConfig]] = None,
        # Source tracking
        source_image_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        iteration_number: int = 1,
    ) -> GenerationParams:
        """
        Resolve final generation parameters.

        Args:
            prompt: The generation prompt
            negative_prompt: What to avoid
            style: Style preset name
            mood: Mood modifier
            daemon_id: Daemon ID for house style lookup
            use_house_style: Whether to apply house style preferences
            use_house_lora: Whether to apply house style LoRA
            recipe_name: Name of saved recipe to load
            width, height, steps, etc.: Explicit overrides

        Returns:
            Fully resolved GenerationParams
        """
        # Start with global defaults
        params = GenerationParams(prompt=prompt)

        # Layer 1: Style preset defaults
        if style:
            style_defaults = get_style_defaults(style)
            params.steps = style_defaults.steps
            params.cfg_scale = style_defaults.cfg_scale
            params.sampler = style_defaults.sampler
            params.scheduler = style_defaults.scheduler
            params.style_preset = style

        # Layer 2: House style preferences (if available)
        house_lora = None
        if use_house_style and daemon_id:
            house_prefs = self._get_house_style_prefs(daemon_id)
            if house_prefs:
                if house_prefs.get("preferred_steps") and not steps:
                    params.steps = house_prefs["preferred_steps"]
                if house_prefs.get("preferred_cfg") and not cfg_scale:
                    params.cfg_scale = house_prefs["preferred_cfg"]
                if house_prefs.get("preferred_sampler") and not sampler:
                    params.sampler = house_prefs["preferred_sampler"]
                if house_prefs.get("preferred_scheduler") and not scheduler:
                    params.scheduler = house_prefs["preferred_scheduler"]
                params.house_style_applied = True

                # Check for house LoRA
                if use_house_lora and house_prefs.get("house_lora_name"):
                    house_lora = LoRAConfig(
                        name=house_prefs["house_lora_name"],
                        strength=house_prefs.get("house_lora_strength", 0.7),
                        clip_strength=house_prefs.get("house_lora_strength", 0.7),
                    )

        # Layer 3: Recipe overrides
        if recipe_name and daemon_id:
            recipe_params = self._load_recipe(daemon_id, recipe_name)
            if recipe_params:
                # Recipe provides complete parameter set
                params = recipe_params
                params.prompt = prompt  # Always use provided prompt
                params.negative_prompt = negative_prompt or params.negative_prompt

        # Layer 4: Explicit overrides (highest priority)
        params.negative_prompt = negative_prompt
        if width is not None:
            params.width = width
        if height is not None:
            params.height = height
        if steps is not None:
            params.steps = steps
        if cfg_scale is not None:
            params.cfg_scale = cfg_scale
        if sampler is not None:
            params.sampler = sampler
        if scheduler is not None:
            params.scheduler = scheduler

        params.seed = seed
        params.denoise = denoise
        params.mood = mood

        # Handle LoRAs
        if loras is not None:
            params.loras = loras
        if house_lora and use_house_lora:
            # Prepend house LoRA if not already present
            existing_names = {l.name for l in params.loras}
            if house_lora.name not in existing_names:
                params.loras = [house_lora] + params.loras
                params.house_lora_applied = True

        # Iteration tracking
        params.source_image_id = source_image_id
        params.parent_id = parent_id
        params.iteration_number = iteration_number

        return params

    def _get_house_style_prefs(self, daemon_id: str) -> Optional[dict]:
        """
        Get house style generation preferences.

        Returns dict with:
        - preferred_steps
        - preferred_cfg
        - preferred_sampler
        - preferred_scheduler
        - house_lora_name
        - house_lora_strength
        """
        try:
            from art_study.persistence import get_personal_style

            style = get_personal_style(daemon_id)
            if not style:
                return None

            prefs = {}

            # Use generation_prefs from the style if available
            if style.generation_prefs:
                prefs["preferred_steps"] = style.generation_prefs.steps
                prefs["preferred_cfg"] = style.generation_prefs.cfg_scale
                prefs["preferred_sampler"] = style.generation_prefs.sampler
                prefs["preferred_scheduler"] = style.generation_prefs.scheduler
            elif style.style_manifesto:
                # Fallback defaults if house style exists but no explicit prefs
                prefs["preferred_steps"] = 35
                prefs["preferred_cfg"] = 7.5
                prefs["preferred_sampler"] = "dpmpp_2m"
                prefs["preferred_scheduler"] = "karras"

            # House LoRA settings
            if style.house_lora_name:
                prefs["house_lora_name"] = style.house_lora_name
                prefs["house_lora_strength"] = style.house_lora_strength

            return prefs if prefs else None

        except Exception as e:
            logger.debug(f"Could not get house style prefs: {e}")
            return None

    def _load_recipe(self, daemon_id: str, recipe_name: str) -> Optional[GenerationParams]:
        """
        Load a saved recipe by name.

        Returns GenerationParams from the recipe or None if not found.
        """
        try:
            from database import get_db
            import json

            with get_db() as conn:
                cursor = conn.execute(
                    """
                    SELECT params_json FROM generation_recipes
                    WHERE daemon_id = ? AND name = ?
                    """,
                    (daemon_id, recipe_name)
                )
                row = cursor.fetchone()
                if row and row[0]:
                    params_dict = json.loads(row[0])
                    return GenerationParams.from_dict(params_dict)
            return None
        except Exception as e:
            logger.warning(f"Could not load recipe {recipe_name}: {e}")
            return None


# Module-level resolver instance
_resolver = None


def get_resolver() -> ParamResolver:
    """Get the singleton param resolver."""
    global _resolver
    if _resolver is None:
        _resolver = ParamResolver()
    return _resolver


def resolve_params(
    prompt: str,
    **kwargs
) -> GenerationParams:
    """
    Convenience function to resolve parameters.

    See ParamResolver.resolve() for full documentation.
    """
    return get_resolver().resolve(prompt, **kwargs)
