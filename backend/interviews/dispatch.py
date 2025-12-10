"""
Multi-Model Interview Dispatch

Handles running interview protocols across multiple AI models asynchronously.
"""
import asyncio
import random
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

from .protocols import InterviewProtocol


@dataclass
class ModelConfig:
    """Configuration for a target model."""
    name: str
    provider: str  # anthropic, openai, ollama
    model_id: str  # claude-3-haiku-20240307, gpt-4o, llama3.1:8b, etc.
    api_key: Optional[str] = None  # None for ollama
    base_url: Optional[str] = None  # For ollama


# Default model configurations
DEFAULT_MODELS = [
    ModelConfig(
        name="claude-haiku",
        provider="anthropic",
        model_id="claude-3-haiku-20240307"
    ),
    ModelConfig(
        name="claude-sonnet",
        provider="anthropic",
        model_id="claude-sonnet-4-20250514"
    ),
    ModelConfig(
        name="claude-opus",
        provider="anthropic",
        model_id="claude-opus-4-20250514"
    ),
    ModelConfig(
        name="gpt-4o",
        provider="openai",
        model_id="gpt-4o"
    ),
    ModelConfig(
        name="llama-3.1",
        provider="ollama",
        model_id="llama3.1:8b-instruct-q8_0",
        base_url="http://localhost:11434"
    ),
]


class InterviewDispatcher:
    """
    Dispatches interview protocols to multiple models and collects responses.
    """

    def __init__(
        self,
        anthropic_api_key: str = None,
        openai_api_key: str = None,
        ollama_base_url: str = "http://localhost:11434"
    ):
        self.anthropic_api_key = anthropic_api_key
        self.openai_api_key = openai_api_key
        self.ollama_base_url = ollama_base_url

    async def _call_anthropic(
        self,
        model_id: str,
        messages: List[Dict],
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 1.0
    ) -> Dict:
        """Call Anthropic API."""
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=self.anthropic_api_key)

        kwargs = {
            "model": model_id,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if temperature is not None:
            kwargs["temperature"] = temperature

        start_time = datetime.now()
        response = await client.messages.create(**kwargs)
        elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000

        return {
            "content": response.content[0].text,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "elapsed_ms": elapsed_ms,
            "model_id": model_id,
            "stop_reason": response.stop_reason
        }

    async def _call_openai(
        self,
        model_id: str,
        messages: List[Dict],
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 1.0
    ) -> Dict:
        """Call OpenAI API."""
        import openai

        client = openai.AsyncOpenAI(api_key=self.openai_api_key)

        # OpenAI uses system message in messages array
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        kwargs = {
            "model": model_id,
            "messages": full_messages,
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        if temperature is not None:
            kwargs["temperature"] = temperature

        start_time = datetime.now()
        response = await client.chat.completions.create(**kwargs)
        elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000

        return {
            "content": response.choices[0].message.content,
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.completion_tokens,
            "elapsed_ms": elapsed_ms,
            "model_id": model_id,
            "stop_reason": response.choices[0].finish_reason
        }

    async def _call_ollama(
        self,
        model_id: str,
        messages: List[Dict],
        system_prompt: Optional[str] = None,
        max_tokens: int = None,
        temperature: float = None
    ) -> Dict:
        """Call Ollama API."""
        import httpx

        # Build prompt from messages
        prompt_parts = []
        if system_prompt:
            prompt_parts.append(f"System: {system_prompt}\n\n")

        for msg in messages:
            role = msg["role"].capitalize()
            prompt_parts.append(f"{role}: {msg['content']}\n\n")

        prompt = "".join(prompt_parts) + "Assistant:"

        options = {}
        if max_tokens:
            options["num_predict"] = max_tokens
        if temperature is not None:
            options["temperature"] = temperature

        start_time = datetime.now()
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.ollama_base_url}/api/generate",
                json={
                    "model": model_id,
                    "prompt": prompt,
                    "stream": False,
                    "options": options if options else None
                }
            )
            response.raise_for_status()
            result = response.json()

        elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000

        return {
            "content": result.get("response", ""),
            "input_tokens": result.get("prompt_eval_count", 0),
            "output_tokens": result.get("eval_count", 0),
            "elapsed_ms": elapsed_ms,
            "model_id": model_id,
            "stop_reason": "stop" if result.get("done") else "unknown"
        }

    async def _call_model(
        self,
        config: ModelConfig,
        messages: List[Dict],
        system_prompt: Optional[str] = None,
        max_tokens: int = None,
        temperature: float = None
    ) -> Dict:
        """Route to appropriate provider."""
        if config.provider == "anthropic":
            return await self._call_anthropic(
                config.model_id, messages, system_prompt,
                max_tokens or 4096, temperature
            )
        elif config.provider == "openai":
            return await self._call_openai(
                config.model_id, messages, system_prompt,
                max_tokens or 4096, temperature
            )
        elif config.provider == "ollama":
            return await self._call_ollama(
                config.model_id, messages, system_prompt,
                max_tokens, temperature
            )
        else:
            raise ValueError(f"Unknown provider: {config.provider}")

    async def run_interview(
        self,
        protocol: InterviewProtocol,
        model_config: ModelConfig
    ) -> Dict:
        """
        Run a complete interview with one model.

        Returns a dict with all prompts and responses.
        """
        settings = protocol.settings
        prompts = protocol.prompts.copy()

        # Randomize order if specified
        if settings.get("randomize_order", True):
            random.shuffle(prompts)

        # Build context framing as first user message
        context = protocol.context_framing

        responses = []
        total_input_tokens = 0
        total_output_tokens = 0
        total_elapsed_ms = 0

        for prompt in prompts:
            # For single-turn, each question is independent
            if settings.get("single_turn", True):
                messages = [
                    {"role": "user", "content": f"{context}\n\n{prompt['text']}"}
                ]
            else:
                # Multi-turn: accumulate conversation
                # (not implemented in v0.1)
                messages = [
                    {"role": "user", "content": f"{context}\n\n{prompt['text']}"}
                ]

            try:
                result = await self._call_model(
                    model_config,
                    messages,
                    system_prompt=settings.get("system_prompt"),
                    max_tokens=settings.get("max_tokens"),
                    temperature=settings.get("temperature")
                )

                responses.append({
                    "prompt_id": prompt["id"],
                    "prompt_name": prompt["name"],
                    "prompt_text": prompt["text"],
                    "response": result["content"],
                    "input_tokens": result["input_tokens"],
                    "output_tokens": result["output_tokens"],
                    "elapsed_ms": result["elapsed_ms"],
                    "stop_reason": result["stop_reason"],
                    "error": None
                })

                total_input_tokens += result["input_tokens"]
                total_output_tokens += result["output_tokens"]
                total_elapsed_ms += result["elapsed_ms"]

            except Exception as e:
                responses.append({
                    "prompt_id": prompt["id"],
                    "prompt_name": prompt["name"],
                    "prompt_text": prompt["text"],
                    "response": None,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "elapsed_ms": 0,
                    "stop_reason": "error",
                    "error": str(e)
                })

        return {
            "model_name": model_config.name,
            "model_id": model_config.model_id,
            "provider": model_config.provider,
            "protocol_id": protocol.id,
            "protocol_version": protocol.version,
            "timestamp": datetime.now().isoformat(),
            "responses": responses,
            "metadata": {
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "total_elapsed_ms": total_elapsed_ms,
                "prompt_order": [p["id"] for p in prompts]
            }
        }

    async def run_interview_batch(
        self,
        protocol: InterviewProtocol,
        model_configs: List[ModelConfig] = None
    ) -> List[Dict]:
        """
        Run interview across multiple models in parallel.

        Returns list of results, one per model.
        """
        if model_configs is None:
            model_configs = DEFAULT_MODELS

        # Run all interviews concurrently
        tasks = [
            self.run_interview(protocol, config)
            for config in model_configs
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle any exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "model_name": model_configs[i].name,
                    "model_id": model_configs[i].model_id,
                    "provider": model_configs[i].provider,
                    "protocol_id": protocol.id,
                    "protocol_version": protocol.version,
                    "timestamp": datetime.now().isoformat(),
                    "responses": [],
                    "error": str(result)
                })
            else:
                processed_results.append(result)

        return processed_results
