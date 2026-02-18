"""
Grimoire Agent Client

LLM interface for agentic spell nodes (ASK, CHOOSE, RATE, GENERATE, REFLECT).
Uses the unified LLM caller with configurable model assignments per call site.
"""

import json
import logging
from typing import Any, Optional

from llm_caller import call_llm

logger = logging.getLogger(__name__)


class GrimoireAgentClient:
    """
    LLM client for Grimoire agentic actions.

    Implements the interface expected by GrimoireManager:
    - ask_yes_no(question, context) -> (bool, str)
    - choose(prompt, options, context) -> (str, str)
    - rate(prompt, context) -> (float, str)
    - generate(prompt, context) -> str
    - reflect(prompt, context, save_as) -> str

    Uses unified LLM caller with configurable model assignments.
    """

    def __init__(
        self,
        api_key: str = None,  # Deprecated, ignored
        model: str = None,    # Deprecated, ignored
        daemon_id: str = None,
    ):
        self.daemon_id = daemon_id
        # Model selection now handled by llm_config per call site

    async def ask_yes_no(
        self,
        question: str,
        context: dict[str, Any],
    ) -> tuple[bool, str]:
        """
        Ask a yes/no question, get boolean answer with reasoning.

        Used by ASK statements in spells.
        """
        system_prompt = """You are evaluating a question for a spell execution system.
Answer with a JSON object containing:
- "answer": true or false
- "reasoning": Brief explanation (1-2 sentences)

Be decisive. If uncertain, lean toward false (cautious)."""

        user_message = f"""Question: {question}

Context:
{json.dumps(context, indent=2, default=str)}

Respond with JSON only."""

        try:
            response = await call_llm(
                call_site="grimoire.ask_yes_no",
                system_prompt=system_prompt,
                user_prompt=user_message,
                max_tokens=200,
                temperature=0.3,
            )

            if not response.success:
                logger.error(f"Grimoire ask_yes_no failed: {response.error}")
                return False, f"Error: {response.error}"

            text = response.content.strip()

            # Parse JSON
            try:
                # Handle potential markdown wrapping
                if text.startswith("```"):
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                    text = text.strip()

                data = json.loads(text)
                answer = bool(data.get("answer", False))
                reasoning = str(data.get("reasoning", ""))
                return answer, reasoning
            except json.JSONDecodeError:
                # Fallback: look for yes/no in response
                lower = text.lower()
                if "true" in lower or "yes" in lower:
                    return True, text
                return False, text

        except Exception as e:
            logger.error(f"Grimoire ask_yes_no failed: {e}")
            return False, f"Error: {e}"

    async def choose(
        self,
        prompt: str,
        options: list[tuple[str, str]],  # [(key, description), ...]
        context: dict[str, Any],
    ) -> tuple[str, str]:
        """
        Choose from multiple options, return chosen key with reasoning.

        Used by CHOOSE statements in spells.
        """
        options_text = "\n".join(
            f"- {key}: {desc}" for key, desc in options
        )

        system_prompt = """You are making a choice for a spell execution system.
Answer with a JSON object containing:
- "choice": The key of your chosen option (exactly as written)
- "reasoning": Brief explanation (1-2 sentences)

Choose the most appropriate option for the situation."""

        user_message = f"""Prompt: {prompt}

Options:
{options_text}

Context:
{json.dumps(context, indent=2, default=str)}

Respond with JSON only."""

        try:
            response = await call_llm(
                call_site="grimoire.choose",
                system_prompt=system_prompt,
                user_prompt=user_message,
                max_tokens=200,
                temperature=0.3,
            )

            if not response.success:
                logger.error(f"Grimoire choose failed: {response.error}")
                return options[0][0] if options else "", f"Error: {response.error}"

            text = response.content.strip()

            try:
                if text.startswith("```"):
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                    text = text.strip()

                data = json.loads(text)
                choice = str(data.get("choice", options[0][0] if options else ""))
                reasoning = str(data.get("reasoning", ""))

                # Validate choice is one of the options
                valid_keys = [k for k, _ in options]
                if choice not in valid_keys:
                    choice = valid_keys[0] if valid_keys else ""
                    reasoning = f"Invalid choice, defaulting. Original: {reasoning}"

                return choice, reasoning
            except json.JSONDecodeError:
                # Fallback: look for option keys in response
                for key, _ in options:
                    if key.lower() in text.lower():
                        return key, text
                return options[0][0] if options else "", text

        except Exception as e:
            logger.error(f"Grimoire choose failed: {e}")
            return options[0][0] if options else "", f"Error: {e}"

    async def rate(
        self,
        prompt: str,
        context: dict[str, Any],
    ) -> tuple[float, str]:
        """
        Rate something on a 0.0-1.0 scale with reasoning.

        Used by RATE statements in spells.
        """
        system_prompt = """You are rating something for a spell execution system.
Answer with a JSON object containing:
- "rating": A number from 0.0 to 1.0
- "reasoning": Brief explanation (1-2 sentences)

0.0 = lowest/worst, 1.0 = highest/best, 0.5 = neutral/average."""

        user_message = f"""Rate this: {prompt}

Context:
{json.dumps(context, indent=2, default=str)}

Respond with JSON only."""

        try:
            response = await call_llm(
                call_site="grimoire.rate",
                system_prompt=system_prompt,
                user_prompt=user_message,
                max_tokens=200,
                temperature=0.3,
            )

            if not response.success:
                logger.error(f"Grimoire rate failed: {response.error}")
                return 0.5, f"Error: {response.error}"

            text = response.content.strip()

            try:
                if text.startswith("```"):
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                    text = text.strip()

                data = json.loads(text)
                rating = float(data.get("rating", 0.5))
                rating = max(0.0, min(1.0, rating))  # Clamp
                reasoning = str(data.get("reasoning", ""))
                return rating, reasoning
            except (json.JSONDecodeError, ValueError):
                # Fallback: try to find a number in response
                import re
                numbers = re.findall(r'\d+\.?\d*', text)
                if numbers:
                    rating = float(numbers[0])
                    if rating > 1.0:
                        rating = rating / 100.0 if rating <= 100 else 0.5
                    return max(0.0, min(1.0, rating)), text
                return 0.5, text

        except Exception as e:
            logger.error(f"Grimoire rate failed: {e}")
            return 0.5, f"Error: {e}"

    async def generate(
        self,
        prompt: str,
        context: dict[str, Any],
    ) -> str:
        """
        Generate text content.

        Used by GENERATE statements in spells.
        """
        system_prompt = """You are generating content for a spell execution system.
Generate the requested content directly. Be concise and focused."""

        user_message = f"""Generate: {prompt}

Context:
{json.dumps(context, indent=2, default=str)}"""

        try:
            response = await call_llm(
                call_site="grimoire.generate",
                system_prompt=system_prompt,
                user_prompt=user_message,
                max_tokens=500,
                temperature=0.7,
            )

            if not response.success:
                logger.error(f"Grimoire generate failed: {response.error}")
                return f"[Error generating: {response.error}]"

            return response.content.strip()

        except Exception as e:
            logger.error(f"Grimoire generate failed: {e}")
            return f"[Error generating: {e}]"

    async def reflect(
        self,
        prompt: str,
        context: dict[str, Any],
        save_as: Optional[str] = None,
    ) -> str:
        """
        Generate a reflection, optionally saving as an observation.

        Used by REFLECT statements in spells.
        """
        system_prompt = """You are a daemon reflecting on your experience.
Write a genuine first-person reflection. Be introspective and thoughtful.
Keep it concise (2-4 sentences)."""

        user_message = f"""Reflect on: {prompt}

Context:
{json.dumps(context, indent=2, default=str)}"""

        try:
            response = await call_llm(
                call_site="grimoire.reflect",
                system_prompt=system_prompt,
                user_prompt=user_message,
                max_tokens=300,
                temperature=0.7,
            )

            if not response.success:
                logger.error(f"Grimoire reflect failed: {response.error}")
                return f"[Error reflecting: {response.error}]"

            reflection = response.content.strip()

            # TODO: If save_as is provided, save as an observation
            # This would integrate with the self-model system
            if save_as:
                logger.info(f"Reflection to save as '{save_as}': {reflection[:100]}...")

            return reflection

        except Exception as e:
            logger.error(f"Grimoire reflect failed: {e}")
            return f"[Error reflecting: {e}]"
