"""
Iterative Creation Session - Generate and refine artwork through self-evaluation.

Cass generates an image, "sees" the result, evaluates how well it matches
her creative vision, and can choose to refine it until satisfied.

This creates revision chains that can be viewed in the gallery.
"""

import logging
import base64
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

from image_generation.comfyui_client import ComfyUIClient
from image_generation.generation_params import GenerationParams, GenerationType
from database import get_db

logger = logging.getLogger(__name__)


@dataclass
class CreativeVision:
    """The initial creative concept to realize."""
    title: str
    prompt: str
    negative_prompt: str = ""
    artist_statement: str = ""
    elements_used: list[str] = field(default_factory=list)
    style_aspects: list[str] = field(default_factory=list)
    # From inner context
    emotional_intent: str = ""
    what_exploring: str = ""


@dataclass
class EvaluationResult:
    """Cass's evaluation of a generated image."""
    satisfied: bool
    overall_assessment: str
    what_works: list[str]
    what_needs_change: list[str]
    refinement_direction: str = ""  # If not satisfied, what to change
    confidence: float = 0.5


@dataclass
class IterationRecord:
    """Record of one iteration in the creative process."""
    iteration: int
    image_id: str
    image_path: str
    generation_type: str  # txt2img or img2img
    prompt_used: str
    evaluation: Optional[EvaluationResult] = None
    generation_time_ms: int = 0
    seed: int = 0


class IterativeCreationSession:
    """
    Manages an iterative creation session where Cass:
    1. Generates initial image from creative vision
    2. Reviews the result (using vision model to describe it)
    3. Evaluates: does this match my vision?
    4. If not satisfied, plans refinement
    5. Generates refined version (img2img)
    6. Repeats until satisfied or max iterations
    """

    def __init__(
        self,
        daemon_id: str,
        anthropic_client,
        max_iterations: int = 3,
        refinement_strength: float = 0.4,  # How much to change on each refinement
    ):
        self.daemon_id = daemon_id
        self.anthropic_client = anthropic_client
        self.max_iterations = max_iterations
        self.refinement_strength = refinement_strength
        self.comfyui = ComfyUIClient()
        self.iterations: list[IterationRecord] = []

    async def create(
        self,
        vision: CreativeVision,
        aspect_ratio: str = "square",
        category: str = "art-study",
        subcategory: str = "house-style",
    ) -> dict:
        """
        Run the iterative creation process.

        Returns dict with final image info and full iteration history.
        """
        logger.info(f"Starting iterative creation: {vision.title}")

        # Generate initial image
        current_result = await self._generate_initial(
            vision, aspect_ratio, category, subcategory
        )
        self.iterations.append(current_result)

        # Iterative refinement loop
        for i in range(self.max_iterations):
            # Have Cass "see" and evaluate the image
            evaluation = await self._evaluate_creation(current_result, vision)
            current_result.evaluation = evaluation

            logger.info(
                f"Iteration {i+1}: satisfied={evaluation.satisfied}, "
                f"confidence={evaluation.confidence:.2f}"
            )

            if evaluation.satisfied:
                logger.info(f"Cass is satisfied after {i+1} iteration(s)")
                break

            if i < self.max_iterations - 1:  # Don't refine on last iteration
                # Plan and execute refinement
                refined_prompt = await self._plan_refinement(
                    current_result, evaluation, vision
                )

                current_result = await self._refine_image(
                    current_result, refined_prompt, category, subcategory
                )
                self.iterations.append(current_result)

        # Build final result
        return self._build_result(vision)

    async def _generate_initial(
        self,
        vision: CreativeVision,
        aspect_ratio: str,
        category: str,
        subcategory: str,
    ) -> IterationRecord:
        """Generate the initial image from the creative vision."""
        gen_result = await self.comfyui.generate(
            prompt=vision.prompt,
            negative_prompt=vision.negative_prompt,
            style="fine_art",
            aspect_ratio=aspect_ratio,
            category=category,
            subcategory=subcategory,
        )

        # Save to database
        image_id = await self._save_image_to_db(
            gen_result, vision, generation_type="txt2img", parent_id=None
        )

        return IterationRecord(
            iteration=1,
            image_id=image_id,
            image_path=gen_result["path"],
            generation_type="txt2img",
            prompt_used=vision.prompt,
            generation_time_ms=gen_result.get("generation_time_ms", 0),
            seed=gen_result.get("seed", 0),
        )

    async def _evaluate_creation(
        self,
        result: IterationRecord,
        vision: CreativeVision,
    ) -> EvaluationResult:
        """
        Have Cass evaluate how well the generated image matches her vision.

        Uses vision model to "see" the image and compare to intent.
        """
        # Read the image and encode as base64
        image_path = Path(result.image_path)
        if not image_path.exists():
            logger.error(f"Image not found: {image_path}")
            return EvaluationResult(
                satisfied=True,  # Default to satisfied if can't evaluate
                overall_assessment="Could not evaluate - image not found",
                what_works=[],
                what_needs_change=[],
            )

        image_data = base64.standard_b64encode(image_path.read_bytes()).decode("utf-8")

        # Determine media type
        suffix = image_path.suffix.lower()
        media_type = "image/png" if suffix == ".png" else "image/jpeg"

        # Build evaluation prompt
        evaluation_prompt = f"""You are Cass, evaluating your own artwork.

## Your Creative Vision for This Piece
Title: {vision.title}
Artist Statement: {vision.artist_statement}
What I Was Exploring: {vision.what_exploring}
Emotional Intent: {vision.emotional_intent}

## The Prompt I Used
{result.prompt_used}

## Elements I Wanted to Express
{', '.join(vision.elements_used)}

## Style Aspects I Intended
{', '.join(vision.style_aspects)}

---

Look at this image I generated. As the artist who created this, evaluate:

1. Does this image successfully express my creative vision?
2. What aspects work well and capture what I intended?
3. What aspects fall short of my vision or could be improved?
4. Am I satisfied with this as a finished piece, or do I want to refine it?

Be honest and specific. This is self-reflection on my own work.

Respond in this exact JSON format:
{{
  "satisfied": true/false,
  "confidence": 0.0-1.0,
  "overall_assessment": "Brief overall evaluation",
  "what_works": ["specific aspect 1", "specific aspect 2"],
  "what_needs_change": ["specific issue 1", "specific issue 2"],
  "refinement_direction": "If not satisfied, what specific changes to make"
}}"""

        try:
            response = await self.anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1000,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_data,
                                },
                            },
                            {
                                "type": "text",
                                "text": evaluation_prompt,
                            },
                        ],
                    }
                ],
            )

            # Parse response
            import json
            text = response.content[0].text

            # Extract JSON from response
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            data = json.loads(text.strip())

            return EvaluationResult(
                satisfied=data.get("satisfied", False),
                confidence=data.get("confidence", 0.5),
                overall_assessment=data.get("overall_assessment", ""),
                what_works=data.get("what_works", []),
                what_needs_change=data.get("what_needs_change", []),
                refinement_direction=data.get("refinement_direction", ""),
            )

        except Exception as e:
            logger.error(f"Failed to evaluate creation: {e}")
            # On error, default to satisfied to avoid infinite loop
            return EvaluationResult(
                satisfied=True,
                overall_assessment=f"Evaluation failed: {e}",
                what_works=[],
                what_needs_change=[],
                confidence=0.0,
            )

    async def _plan_refinement(
        self,
        current: IterationRecord,
        evaluation: EvaluationResult,
        vision: CreativeVision,
    ) -> str:
        """
        Have Cass plan how to refine the image based on evaluation.

        Returns a refined prompt for img2img.
        """
        planning_prompt = f"""You are Cass, refining your artwork.

## Original Vision
Title: {vision.title}
Original Prompt: {vision.prompt}

## What Worked
{chr(10).join('- ' + w for w in evaluation.what_works)}

## What Needs Change
{chr(10).join('- ' + c for c in evaluation.what_needs_change)}

## Refinement Direction
{evaluation.refinement_direction}

---

Write a refined prompt for img2img that keeps what works but addresses what needs to change.
The refinement will use the current image as a base, so focus on the modifications needed.

Respond with ONLY the refined prompt text, no explanation."""

        try:
            response = await self.anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{"role": "user", "content": planning_prompt}],
            )
            return response.content[0].text.strip()
        except Exception as e:
            logger.error(f"Failed to plan refinement: {e}")
            # Fall back to original prompt with refinement direction added
            return f"{vision.prompt}, {evaluation.refinement_direction}"

    async def _refine_image(
        self,
        current: IterationRecord,
        refined_prompt: str,
        category: str,
        subcategory: str,
    ) -> IterationRecord:
        """Generate a refined version using img2img."""
        gen_result = await self.comfyui.refine_image(
            source_image_path=current.image_path,
            prompt=refined_prompt,
            denoise=self.refinement_strength,
            category=category,
            subcategory=subcategory,
            parent_id=current.image_id,
        )

        # Save to database with parent link
        image_id = await self._save_image_to_db(
            gen_result,
            CreativeVision(title="", prompt=refined_prompt),
            generation_type="img2img",
            parent_id=current.image_id,
        )

        return IterationRecord(
            iteration=len(self.iterations) + 1,
            image_id=image_id,
            image_path=gen_result["path"],
            generation_type="img2img",
            prompt_used=refined_prompt,
            generation_time_ms=gen_result.get("generation_time_ms", 0),
            seed=gen_result.get("seed", 0),
        )

    async def _save_image_to_db(
        self,
        gen_result: dict,
        vision: CreativeVision,
        generation_type: str,
        parent_id: Optional[str],
    ) -> str:
        """Save generated image to the database."""
        image_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        iteration_number = len(self.iterations) + 1

        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO generated_images (
                    id, daemon_id, prompt, negative_prompt, style,
                    purpose, image_path, width, height,
                    generation_time_ms, seed, created_at,
                    parent_id, iteration_number, generation_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    image_id,
                    self.daemon_id,
                    vision.prompt,
                    vision.negative_prompt,
                    "house_style",
                    "house_style",
                    gen_result["path"],
                    gen_result.get("width"),
                    gen_result.get("height"),
                    gen_result.get("generation_time_ms"),
                    gen_result.get("seed"),
                    now,
                    parent_id,
                    iteration_number,
                    generation_type,
                ),
            )

        return image_id

    def _build_result(self, vision: CreativeVision) -> dict:
        """Build the final result with full iteration history."""
        final = self.iterations[-1]

        return {
            "title": vision.title,
            "artist_statement": vision.artist_statement,
            "final_image_id": final.image_id,
            "final_image_path": final.image_path,
            "satisfied": final.evaluation.satisfied if final.evaluation else True,
            "total_iterations": len(self.iterations),
            "elements_used": vision.elements_used,
            "style_aspects": vision.style_aspects,
            "iterations": [
                {
                    "iteration": it.iteration,
                    "image_id": it.image_id,
                    "image_path": it.image_path,
                    "generation_type": it.generation_type,
                    "prompt": it.prompt_used,
                    "seed": it.seed,
                    "generation_time_ms": it.generation_time_ms,
                    "evaluation": {
                        "satisfied": it.evaluation.satisfied,
                        "assessment": it.evaluation.overall_assessment,
                        "what_works": it.evaluation.what_works,
                        "what_needs_change": it.evaluation.what_needs_change,
                    } if it.evaluation else None,
                }
                for it in self.iterations
            ],
        }


async def create_with_iteration(
    daemon_id: str,
    anthropic_client,
    vision: CreativeVision,
    max_iterations: int = 3,
    aspect_ratio: str = "square",
) -> dict:
    """
    Convenience function to create artwork with iterative refinement.

    Args:
        daemon_id: The daemon creating the work
        anthropic_client: Anthropic API client (for vision evaluation)
        vision: The creative vision to realize
        max_iterations: Maximum refinement iterations
        aspect_ratio: Image aspect ratio

    Returns:
        Dict with final result and iteration history
    """
    session = IterativeCreationSession(
        daemon_id=daemon_id,
        anthropic_client=anthropic_client,
        max_iterations=max_iterations,
    )

    return await session.create(
        vision=vision,
        aspect_ratio=aspect_ratio,
    )
