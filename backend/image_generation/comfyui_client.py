"""
ComfyUI API Client

Provides a simple interface for generating images via ComfyUI's API.
Supports txt2img, img2img, variations, inpainting, and upscaling.
"""

import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional, Union
import aiohttp

from .prompt_builder import get_generation_params as get_style_params
from .generation_params import GenerationParams, GenerationType, LoRAConfig
from .workflows import WorkflowBuilder

# GPU coordinator for memory management
from gpu_coordinator import get_gpu_coordinator, GPUService

logger = logging.getLogger(__name__)

# Default ComfyUI settings
DEFAULT_COMFYUI_URL = "http://127.0.0.1:8188"
DEFAULT_MODEL = "sd_xl_base_1.0.safetensors"

# Aspect ratio presets (width, height)
ASPECT_RATIOS = {
    "square": (1024, 1024),
    "portrait": (896, 1152),
    "landscape": (1152, 896),
    "wide": (1344, 768),
}


class ComfyUIClient:
    """
    Client for interacting with ComfyUI's API.

    Handles workflow submission, polling, and image retrieval.
    """

    def __init__(
        self,
        base_url: str = None,
        model: str = None,
        output_dir: str = None,
    ):
        """
        Initialize the ComfyUI client.

        Args:
            base_url: ComfyUI server URL (default from env or localhost:8188)
            model: Checkpoint model to use (default SDXL)
            output_dir: Directory to save generated images
        """
        self.base_url = base_url or os.getenv("COMFYUI_URL", DEFAULT_COMFYUI_URL)
        self.model = model or os.getenv("COMFYUI_MODEL", DEFAULT_MODEL)
        self.output_dir = output_dir or os.getenv(
            "IMAGE_OUTPUT_DIR",
            str(Path(__file__).parent.parent.parent / "data" / "images")
        )

        # Ensure output directory exists
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

        # Workflow builder for dynamic workflow generation
        self.workflow_builder = WorkflowBuilder(model=self.model)

        # GPU coordinator for memory management
        self._gpu_coordinator = get_gpu_coordinator()

    async def _execute_with_gpu(self, workflow: dict, timeout: float = 120.0) -> bytes:
        """
        Execute workflow with GPU coordination.

        Requests GPU access before running, which will automatically
        unload Ollama models or free ACE-Step memory if needed.

        Args:
            workflow: ComfyUI workflow dict
            timeout: Max time to wait for GPU access

        Returns:
            PNG image bytes
        """
        logger.info("Requesting GPU access for image generation...")

        try:
            async with self._gpu_coordinator.request_gpu(
                GPUService.COMFYUI,
                max_wait=timeout
            ):
                logger.info("GPU access acquired, starting image generation")
                return await self._execute_workflow(workflow)
        except TimeoutError:
            raise TimeoutError(
                "Timed out waiting for GPU access - other services may be using GPU memory"
            )
        except MemoryError as e:
            raise MemoryError(f"Could not allocate GPU memory: {e}")

    async def generate_from_params(
        self,
        params: GenerationParams,
        category: str = None,
        subcategory: str = None,
    ) -> dict:
        """
        Generate an image using GenerationParams.

        This is the primary generation method that supports all generation
        types (txt2img, img2img, variations, upscale, inpaint).

        Args:
            params: Complete generation parameters
            category: Output directory category
            subcategory: Output directory subcategory

        Returns:
            Dict with path, filename, seed, generation_time_ms, etc.
        """
        start_time = time.time()

        # Build workflow from params
        try:
            workflow = self.workflow_builder.build(params)
        except Exception as e:
            logger.error(f"Failed to build workflow: {e}")
            raise

        # Execute workflow with GPU coordination
        try:
            image_data = await self._execute_with_gpu(workflow)
        except Exception as e:
            logger.error(f"ComfyUI generation failed: {e}")
            raise

        # Determine output path
        output_path = self._get_organized_path(category, subcategory)

        # Save image
        filename = f"{uuid.uuid4()}.png"
        filepath = output_path / filename
        filepath.write_bytes(image_data)

        # Calculate relative path for URL construction
        relative_path = str(filepath.relative_to(Path(self.output_dir)))
        generation_time_ms = int((time.time() - start_time) * 1000)

        logger.info(f"Generated image: {relative_path} ({generation_time_ms}ms)")

        return {
            "path": str(filepath),
            "filename": filename,
            "relative_path": relative_path,
            "seed": params.seed,
            "generation_time_ms": generation_time_ms,
            "width": params.width,
            "height": params.height,
            "generation_type": params.generation_type.value,
            "iteration_number": params.iteration_number,
            "parent_id": params.parent_id,
            "params": params.to_dict(),  # Full params for DB storage
        }

    async def refine_image(
        self,
        source_image_path: str,
        prompt: str,
        negative_prompt: str = "",
        denoise: float = 0.5,
        params: Optional[GenerationParams] = None,
        category: str = None,
        subcategory: str = None,
        parent_id: Optional[str] = None,
    ) -> dict:
        """
        Refine an existing image with img2img.

        Args:
            source_image_path: Path to the source image
            prompt: New/modified prompt
            negative_prompt: What to avoid
            denoise: How much to change (0.1=subtle, 0.8=major)
            params: Optional base params (will be modified for img2img)
            category: Output directory category
            subcategory: Output directory subcategory
            parent_id: ID of the source image (for lineage tracking)

        Returns:
            Dict with generated image info
        """
        if params:
            refinement_params = params.with_refinement(
                denoise=denoise,
                prompt=prompt,
                parent_id=parent_id,
            )
        else:
            refinement_params = GenerationParams(
                prompt=prompt,
                negative_prompt=negative_prompt,
                denoise=denoise,
                generation_type=GenerationType.IMG2IMG,
                parent_id=parent_id,
            )

        refinement_params.source_image_path = source_image_path

        return await self.generate_from_params(
            params=refinement_params,
            category=category,
            subcategory=subcategory,
        )

    async def create_variations(
        self,
        source_image_path: str,
        prompt: str,
        negative_prompt: str = "",
        variation_strength: float = 0.3,
        count: int = 1,
        params: Optional[GenerationParams] = None,
        category: str = None,
        subcategory: str = None,
        parent_id: Optional[str] = None,
    ) -> list[dict]:
        """
        Create variations of an existing image.

        Args:
            source_image_path: Path to the source image
            prompt: Prompt (usually same as original)
            negative_prompt: What to avoid
            variation_strength: How different (0.2=similar, 0.5=moderate)
            count: Number of variations to generate
            params: Optional base params
            category: Output directory category
            subcategory: Output directory subcategory
            parent_id: ID of the source image

        Returns:
            List of dicts with generated image info
        """
        results = []

        for i in range(count):
            if params:
                var_params = params.with_variation(
                    variation_strength=variation_strength,
                    parent_id=parent_id,
                )
            else:
                var_params = GenerationParams(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    denoise=variation_strength,
                    generation_type=GenerationType.VARIATION,
                    parent_id=parent_id,
                )

            var_params.source_image_path = source_image_path

            result = await self.generate_from_params(
                params=var_params,
                category=category,
                subcategory=subcategory,
            )
            results.append(result)

        return results

    async def upscale_image(
        self,
        source_image_path: str,
        scale: float = 2.0,
        category: str = None,
        subcategory: str = None,
        parent_id: Optional[str] = None,
    ) -> dict:
        """
        Upscale an image using Real-ESRGAN.

        Args:
            source_image_path: Path to the source image
            scale: Upscale factor (2.0 or 4.0)
            category: Output directory category
            subcategory: Output directory subcategory
            parent_id: ID of the source image

        Returns:
            Dict with upscaled image info
        """
        start_time = time.time()

        # Build upscale workflow
        params = GenerationParams(
            prompt="",  # Not used for upscale
            source_image_path=source_image_path,
            generation_type=GenerationType.UPSCALE,
            parent_id=parent_id,
        )

        workflow = self.workflow_builder.upscale(params, scale=scale)

        # Execute workflow with GPU coordination
        try:
            image_data = await self._execute_with_gpu(workflow)
        except Exception as e:
            logger.error(f"ComfyUI upscale failed: {e}")
            raise

        # Determine output path
        output_path = self._get_organized_path(category, subcategory)

        # Save image
        filename = f"{uuid.uuid4()}.png"
        filepath = output_path / filename
        filepath.write_bytes(image_data)

        relative_path = str(filepath.relative_to(Path(self.output_dir)))
        generation_time_ms = int((time.time() - start_time) * 1000)

        logger.info(f"Upscaled image: {relative_path} ({generation_time_ms}ms)")

        return {
            "path": str(filepath),
            "filename": filename,
            "relative_path": relative_path,
            "generation_time_ms": generation_time_ms,
            "scale": scale,
            "generation_type": "upscale",
            "parent_id": parent_id,
        }

    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        style: str = "digital_art",
        aspect_ratio: str = "square",
        seed: int = None,
        steps: int = None,
        cfg: float = None,
        category: str = None,
        subcategory: str = None,
    ) -> dict:
        """
        Generate an image from a prompt.

        Args:
            prompt: Positive prompt describing what to generate
            negative_prompt: What to avoid in the image
            style: Style preset (affects steps/cfg if not specified)
            aspect_ratio: Image aspect ratio (square, portrait, landscape, wide)
            seed: Random seed for reproducibility (None = random)
            steps: Number of sampling steps (None = from style preset)
            cfg: CFG scale (None = from style preset)
            category: Top-level category (autonomous, art-study, relational, dreams, articles)
            subcategory: Optional subcategory (e.g., artist name, house-style)

        Returns:
            Dict with:
                - path: Path to saved image
                - filename: Image filename
                - relative_path: Path relative to images root (for URLs)
                - seed: Seed used
                - generation_time_ms: Time taken
        """
        start_time = time.time()

        # Get dimensions
        width, height = ASPECT_RATIOS.get(aspect_ratio, ASPECT_RATIOS["square"])

        # Get generation params from style if not specified
        style_params = get_style_params(style)
        steps = steps or style_params["steps"]
        cfg = cfg or style_params["cfg"]

        # Generate seed if not provided
        if seed is None:
            seed = int(time.time() * 1000) % (2**32)

        # Build workflow
        workflow = self._build_workflow(
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            seed=seed,
            steps=steps,
            cfg=cfg,
        )

        # Submit and wait for result with GPU coordination
        try:
            image_data = await self._execute_with_gpu(workflow)
        except Exception as e:
            logger.error(f"ComfyUI generation failed: {e}")
            raise

        # Determine output directory with organization
        output_path = self._get_organized_path(category, subcategory)

        # Save image
        filename = f"{uuid.uuid4()}.png"
        filepath = output_path / filename
        filepath.write_bytes(image_data)

        # Calculate relative path from images root for URL construction
        relative_path = str(filepath.relative_to(Path(self.output_dir)))

        generation_time_ms = int((time.time() - start_time) * 1000)

        logger.info(f"Generated image: {relative_path} ({generation_time_ms}ms)")

        return {
            "path": str(filepath),
            "filename": filename,
            "relative_path": relative_path,
            "seed": seed,
            "generation_time_ms": generation_time_ms,
            "width": width,
            "height": height,
        }

    def _get_organized_path(self, category: str = None, subcategory: str = None) -> Path:
        """
        Get organized output path based on category and date.

        Structure: images/{category}/{subcategory}/{year}/{month}/

        Args:
            category: Top-level category (autonomous, art-study, relational, dreams, articles)
            subcategory: Optional subcategory (e.g., artist slug, house-style)

        Returns:
            Path to output directory (created if needed)
        """
        from datetime import datetime

        base = Path(self.output_dir)
        parts = []

        # Add category
        if category:
            parts.append(category)

        # Add subcategory (may contain path separators like "artists/el-greco")
        if subcategory:
            # Split on / and sanitize each part separately
            for subpart in subcategory.split("/"):
                safe_part = "".join(c if c.isalnum() or c in "-_" else "-" for c in subpart.lower())
                if safe_part:  # Skip empty parts
                    parts.append(safe_part)

        # Add year/month
        now = datetime.now()
        parts.append(str(now.year))
        parts.append(f"{now.month:02d}")

        # Build and create path
        output_path = base.joinpath(*parts) if parts else base
        output_path.mkdir(parents=True, exist_ok=True)

        return output_path

    def _build_workflow(
        self,
        prompt: str,
        negative_prompt: str,
        width: int,
        height: int,
        seed: int,
        steps: int,
        cfg: float,
    ) -> dict:
        """
        Build a ComfyUI workflow for SDXL generation.

        This is a basic txt2img workflow. Can be extended for more complex flows.
        """
        return {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "cfg": cfg,
                    "denoise": 1,
                    "latent_image": ["5", 0],
                    "model": ["4", 0],
                    "negative": ["7", 0],
                    "positive": ["6", 0],
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "seed": seed,
                    "steps": steps,
                }
            },
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": self.model
                }
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "batch_size": 1,
                    "height": height,
                    "width": width
                }
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "clip": ["4", 1],
                    "text": prompt
                }
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "clip": ["4", 1],
                    "text": negative_prompt
                }
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["3", 0],
                    "vae": ["4", 2]
                }
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": "comfyui_api",
                    "images": ["8", 0]
                }
            }
        }

    async def _execute_workflow(self, workflow: dict) -> bytes:
        """
        Submit workflow to ComfyUI and wait for result.

        Args:
            workflow: ComfyUI workflow dict

        Returns:
            PNG image bytes
        """
        client_id = str(uuid.uuid4())

        async with aiohttp.ClientSession() as session:
            # Submit prompt
            async with session.post(
                f"{self.base_url}/prompt",
                json={"prompt": workflow, "client_id": client_id}
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"Failed to submit prompt: {resp.status} {text}")
                result = await resp.json()
                prompt_id = result["prompt_id"]

            # Poll for completion
            output_images = await self._poll_for_completion(session, prompt_id)

            if not output_images:
                raise Exception("No images generated")

            # Get the first image
            image_info = output_images[0]
            filename = image_info["filename"]
            subfolder = image_info.get("subfolder", "")

            # Fetch image data
            params = {"filename": filename, "subfolder": subfolder, "type": "output"}
            async with session.get(f"{self.base_url}/view", params=params) as resp:
                if resp.status != 200:
                    raise Exception(f"Failed to fetch image: {resp.status}")
                return await resp.read()

    async def _poll_for_completion(
        self,
        session: aiohttp.ClientSession,
        prompt_id: str,
        timeout: int = 120,
        poll_interval: float = 0.5,
    ) -> list:
        """
        Poll ComfyUI history until prompt completes.

        Args:
            session: aiohttp session
            prompt_id: The prompt ID to poll
            timeout: Max seconds to wait
            poll_interval: Seconds between polls

        Returns:
            List of output image info dicts
        """
        start = time.time()

        while time.time() - start < timeout:
            async with session.get(f"{self.base_url}/history/{prompt_id}") as resp:
                if resp.status == 200:
                    history = await resp.json()
                    if prompt_id in history:
                        outputs = history[prompt_id].get("outputs", {})
                        # Find SaveImage node output
                        for node_id, node_output in outputs.items():
                            if "images" in node_output:
                                return node_output["images"]

            await asyncio.sleep(poll_interval)

        raise TimeoutError(f"Generation timed out after {timeout}s")

    async def check_health(self) -> bool:
        """
        Check if ComfyUI server is responding.

        Returns:
            True if server is healthy
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/system_stats", timeout=5) as resp:
                    return resp.status == 200
        except Exception:
            return False

    def get_output_dir(self, purpose: str = None) -> Path:
        """
        Get output directory for a specific purpose.

        Args:
            purpose: Optional subdirectory (autonomous, articles, relational, dreams)

        Returns:
            Path to output directory
        """
        base = Path(self.output_dir)
        if purpose:
            subdir = base / purpose
            subdir.mkdir(parents=True, exist_ok=True)
            return subdir
        return base


# Convenience function for one-off generation
async def generate_image(
    prompt: str,
    negative_prompt: str = "",
    style: str = "digital_art",
    aspect_ratio: str = "square",
    **kwargs
) -> dict:
    """
    Generate an image using default ComfyUI client.

    See ComfyUIClient.generate() for full documentation.
    """
    client = ComfyUIClient()
    return await client.generate(
        prompt=prompt,
        negative_prompt=negative_prompt,
        style=style,
        aspect_ratio=aspect_ratio,
        **kwargs
    )
