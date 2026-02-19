"""
ComfyUI Workflow Builders

Generates dynamic ComfyUI workflow definitions for different
generation types: txt2img, img2img, variations, inpainting, upscaling.
"""

import logging
from typing import Optional

from .generation_params import GenerationParams, LoRAConfig, GenerationType

logger = logging.getLogger(__name__)


class WorkflowBuilder:
    """
    Builds ComfyUI workflow definitions from GenerationParams.

    Each method returns a workflow dict that can be submitted to
    ComfyUI's /prompt endpoint.
    """

    def __init__(self, model: str = "sd_xl_base_1.0.safetensors"):
        """
        Initialize the workflow builder.

        Args:
            model: Checkpoint model filename
        """
        self.model = model

    def build(self, params: GenerationParams) -> dict:
        """
        Build the appropriate workflow based on generation type.

        Args:
            params: Generation parameters

        Returns:
            ComfyUI workflow dict
        """
        if params.generation_type == GenerationType.TXT2IMG:
            return self.txt2img(params)
        elif params.generation_type == GenerationType.IMG2IMG:
            return self.img2img(params)
        elif params.generation_type == GenerationType.VARIATION:
            return self.variations(params)
        elif params.generation_type == GenerationType.UPSCALE:
            return self.upscale(params)
        elif params.generation_type == GenerationType.INPAINT:
            return self.inpaint(params)
        else:
            raise ValueError(f"Unknown generation type: {params.generation_type}")

    def txt2img(self, params: GenerationParams) -> dict:
        """
        Build a text-to-image workflow.

        Args:
            params: Generation parameters

        Returns:
            ComfyUI workflow dict
        """
        workflow = {}
        node_id = 1

        # 1. Checkpoint Loader
        ckpt_node = str(node_id)
        workflow[ckpt_node] = {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": self.model
            }
        }
        model_out = [ckpt_node, 0]
        clip_out = [ckpt_node, 1]
        vae_out = [ckpt_node, 2]
        node_id += 1

        # 2. LoRA Loaders (if any)
        for lora in params.loras:
            lora_node = str(node_id)
            workflow[lora_node] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "lora_name": f"{lora.name}.safetensors",
                    "strength_model": lora.strength,
                    "strength_clip": lora.clip_strength,
                    "model": model_out,
                    "clip": clip_out,
                }
            }
            model_out = [lora_node, 0]
            clip_out = [lora_node, 1]
            node_id += 1

        # 3. CLIP Text Encode (Positive)
        pos_node = str(node_id)
        workflow[pos_node] = {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": clip_out,
                "text": params.prompt
            }
        }
        node_id += 1

        # 4. CLIP Text Encode (Negative)
        neg_node = str(node_id)
        workflow[neg_node] = {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": clip_out,
                "text": params.negative_prompt
            }
        }
        node_id += 1

        # 5. Empty Latent Image
        latent_node = str(node_id)
        workflow[latent_node] = {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "batch_size": 1,
                "height": params.height,
                "width": params.width
            }
        }
        node_id += 1

        # 6. KSampler
        sampler_node = str(node_id)
        workflow[sampler_node] = {
            "class_type": "KSampler",
            "inputs": {
                "cfg": params.cfg_scale,
                "denoise": params.denoise,
                "latent_image": [latent_node, 0],
                "model": model_out,
                "negative": [neg_node, 0],
                "positive": [pos_node, 0],
                "sampler_name": params.sampler,
                "scheduler": params.scheduler,
                "seed": params.seed if params.seed >= 0 else self._random_seed(),
                "steps": params.steps,
            }
        }
        node_id += 1

        # 7. VAE Decode
        decode_node = str(node_id)
        workflow[decode_node] = {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": [sampler_node, 0],
                "vae": vae_out
            }
        }
        node_id += 1

        # 8. Save Image
        save_node = str(node_id)
        workflow[save_node] = {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "comfyui_api",
                "images": [decode_node, 0]
            }
        }

        return workflow

    def img2img(self, params: GenerationParams) -> dict:
        """
        Build an image-to-image refinement workflow.

        Requires params.source_image_path to be set.

        Args:
            params: Generation parameters (must have source_image_path)

        Returns:
            ComfyUI workflow dict
        """
        if not params.source_image_path:
            raise ValueError("img2img requires source_image_path")

        workflow = {}
        node_id = 1

        # 1. Checkpoint Loader
        ckpt_node = str(node_id)
        workflow[ckpt_node] = {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": self.model
            }
        }
        model_out = [ckpt_node, 0]
        clip_out = [ckpt_node, 1]
        vae_out = [ckpt_node, 2]
        node_id += 1

        # 2. LoRA Loaders
        for lora in params.loras:
            lora_node = str(node_id)
            workflow[lora_node] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "lora_name": f"{lora.name}.safetensors",
                    "strength_model": lora.strength,
                    "strength_clip": lora.clip_strength,
                    "model": model_out,
                    "clip": clip_out,
                }
            }
            model_out = [lora_node, 0]
            clip_out = [lora_node, 1]
            node_id += 1

        # 3. Load Image
        load_node = str(node_id)
        workflow[load_node] = {
            "class_type": "LoadImage",
            "inputs": {
                "image": params.source_image_path
            }
        }
        node_id += 1

        # 4. VAE Encode (image to latent)
        encode_node = str(node_id)
        workflow[encode_node] = {
            "class_type": "VAEEncode",
            "inputs": {
                "pixels": [load_node, 0],
                "vae": vae_out
            }
        }
        node_id += 1

        # 5. CLIP Text Encode (Positive)
        pos_node = str(node_id)
        workflow[pos_node] = {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": clip_out,
                "text": params.prompt
            }
        }
        node_id += 1

        # 6. CLIP Text Encode (Negative)
        neg_node = str(node_id)
        workflow[neg_node] = {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": clip_out,
                "text": params.negative_prompt
            }
        }
        node_id += 1

        # 7. KSampler (with denoise < 1.0 for img2img)
        sampler_node = str(node_id)
        workflow[sampler_node] = {
            "class_type": "KSampler",
            "inputs": {
                "cfg": params.cfg_scale,
                "denoise": params.denoise,  # Key difference: < 1.0
                "latent_image": [encode_node, 0],
                "model": model_out,
                "negative": [neg_node, 0],
                "positive": [pos_node, 0],
                "sampler_name": params.sampler,
                "scheduler": params.scheduler,
                "seed": params.seed if params.seed >= 0 else self._random_seed(),
                "steps": params.steps,
            }
        }
        node_id += 1

        # 8. VAE Decode
        decode_node = str(node_id)
        workflow[decode_node] = {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": [sampler_node, 0],
                "vae": vae_out
            }
        }
        node_id += 1

        # 9. Save Image
        save_node = str(node_id)
        workflow[save_node] = {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "comfyui_api_img2img",
                "images": [decode_node, 0]
            }
        }

        return workflow

    def variations(self, params: GenerationParams) -> dict:
        """
        Build a variations workflow.

        Similar to img2img but optimized for creating variations
        of an existing image.

        Args:
            params: Generation parameters (must have source_image_path)

        Returns:
            ComfyUI workflow dict
        """
        # Variations use the same workflow as img2img
        # The key difference is typically a lower denoise value (0.2-0.4)
        return self.img2img(params)

    def inpaint(self, params: GenerationParams) -> dict:
        """
        Build an inpainting workflow.

        Requires both source_image_path and mask_path.

        Args:
            params: Generation parameters (must have source_image_path and mask_path)

        Returns:
            ComfyUI workflow dict
        """
        if not params.source_image_path:
            raise ValueError("inpaint requires source_image_path")
        if not params.mask_path:
            raise ValueError("inpaint requires mask_path")

        workflow = {}
        node_id = 1

        # 1. Checkpoint Loader
        ckpt_node = str(node_id)
        workflow[ckpt_node] = {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": self.model
            }
        }
        model_out = [ckpt_node, 0]
        clip_out = [ckpt_node, 1]
        vae_out = [ckpt_node, 2]
        node_id += 1

        # 2. LoRA Loaders
        for lora in params.loras:
            lora_node = str(node_id)
            workflow[lora_node] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "lora_name": f"{lora.name}.safetensors",
                    "strength_model": lora.strength,
                    "strength_clip": lora.clip_strength,
                    "model": model_out,
                    "clip": clip_out,
                }
            }
            model_out = [lora_node, 0]
            clip_out = [lora_node, 1]
            node_id += 1

        # 3. Load Image
        load_node = str(node_id)
        workflow[load_node] = {
            "class_type": "LoadImage",
            "inputs": {
                "image": params.source_image_path
            }
        }
        node_id += 1

        # 4. Load Mask
        mask_node = str(node_id)
        workflow[mask_node] = {
            "class_type": "LoadImage",
            "inputs": {
                "image": params.mask_path
            }
        }
        node_id += 1

        # 5. VAE Encode for Inpaint
        encode_node = str(node_id)
        workflow[encode_node] = {
            "class_type": "VAEEncodeForInpaint",
            "inputs": {
                "pixels": [load_node, 0],
                "vae": vae_out,
                "mask": [mask_node, 0],
                "grow_mask_by": 6
            }
        }
        node_id += 1

        # 6. CLIP Text Encode (Positive)
        pos_node = str(node_id)
        workflow[pos_node] = {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": clip_out,
                "text": params.prompt
            }
        }
        node_id += 1

        # 7. CLIP Text Encode (Negative)
        neg_node = str(node_id)
        workflow[neg_node] = {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": clip_out,
                "text": params.negative_prompt
            }
        }
        node_id += 1

        # 8. KSampler
        sampler_node = str(node_id)
        workflow[sampler_node] = {
            "class_type": "KSampler",
            "inputs": {
                "cfg": params.cfg_scale,
                "denoise": params.denoise,
                "latent_image": [encode_node, 0],
                "model": model_out,
                "negative": [neg_node, 0],
                "positive": [pos_node, 0],
                "sampler_name": params.sampler,
                "scheduler": params.scheduler,
                "seed": params.seed if params.seed >= 0 else self._random_seed(),
                "steps": params.steps,
            }
        }
        node_id += 1

        # 9. VAE Decode
        decode_node = str(node_id)
        workflow[decode_node] = {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": [sampler_node, 0],
                "vae": vae_out
            }
        }
        node_id += 1

        # 10. Save Image
        save_node = str(node_id)
        workflow[save_node] = {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "comfyui_api_inpaint",
                "images": [decode_node, 0]
            }
        }

        return workflow

    def upscale(self, params: GenerationParams, scale: float = 2.0) -> dict:
        """
        Build an upscaling workflow using a Real-ESRGAN model.

        Args:
            params: Generation parameters (must have source_image_path)
            scale: Upscale factor (2.0 or 4.0)

        Returns:
            ComfyUI workflow dict
        """
        if not params.source_image_path:
            raise ValueError("upscale requires source_image_path")

        # Select upscale model based on scale factor
        upscale_model = "RealESRGAN_x4plus.pth" if scale >= 4.0 else "RealESRGAN_x2plus.pth"

        workflow = {}
        node_id = 1

        # 1. Load Upscale Model
        model_node = str(node_id)
        workflow[model_node] = {
            "class_type": "UpscaleModelLoader",
            "inputs": {
                "model_name": upscale_model
            }
        }
        node_id += 1

        # 2. Load Image
        load_node = str(node_id)
        workflow[load_node] = {
            "class_type": "LoadImage",
            "inputs": {
                "image": params.source_image_path
            }
        }
        node_id += 1

        # 3. Upscale Image
        upscale_node = str(node_id)
        workflow[upscale_node] = {
            "class_type": "ImageUpscaleWithModel",
            "inputs": {
                "upscale_model": [model_node, 0],
                "image": [load_node, 0]
            }
        }
        node_id += 1

        # 4. Save Image
        save_node = str(node_id)
        workflow[save_node] = {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "comfyui_api_upscale",
                "images": [upscale_node, 0]
            }
        }

        return workflow

    def _random_seed(self) -> int:
        """Generate a random seed."""
        import time
        return int(time.time() * 1000) % (2**32)


# Module-level builder instance
_builder = None


def get_workflow_builder(model: Optional[str] = None) -> WorkflowBuilder:
    """Get a workflow builder instance."""
    global _builder
    if _builder is None or (model and _builder.model != model):
        _builder = WorkflowBuilder(model=model or "sd_xl_base_1.0.safetensors")
    return _builder


def build_workflow(params: GenerationParams, model: Optional[str] = None) -> dict:
    """
    Convenience function to build a workflow.

    Args:
        params: Generation parameters
        model: Optional checkpoint model override

    Returns:
        ComfyUI workflow dict
    """
    builder = get_workflow_builder(model)
    return builder.build(params)
