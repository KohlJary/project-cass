"""
Unified LLM Caller

Provides a single interface for making LLM calls that:
1. Reads model assignment from llm_config
2. Handles Anthropic, Ollama, and OpenAI
3. Falls back to configured fallback model on failure
4. Tracks token usage
"""

import json
import os
import httpx
import anthropic
from typing import Optional, Any

from llm_config import get_model_for, ModelAssignment

# Environment config
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_ENABLED = os.environ.get("OLLAMA_ENABLED", "true").lower() == "true"
OPENAI_ENABLED = os.environ.get("OPENAI_ENABLED", "false").lower() == "true"


class LLMResponse:
    """Response from an LLM call."""

    def __init__(
        self,
        content: str,
        provider: str,
        model_id: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        error: Optional[str] = None,
    ):
        self.content = content
        self.provider = provider
        self.model_id = model_id
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.error = error

    @property
    def success(self) -> bool:
        return self.error is None and self.content


async def call_llm(
    call_site: str,
    system_prompt: Optional[str] = None,
    user_prompt: str = "",
    max_tokens: int = 1000,
    temperature: float = 0.7,
    timeout: float = 120.0,
) -> LLMResponse:
    """
    Make an LLM call using the configured model for this call site.

    Args:
        call_site: The call site identifier (e.g., "title_generation")
        system_prompt: Optional system prompt
        user_prompt: The user/input prompt
        max_tokens: Maximum tokens in response
        temperature: Sampling temperature
        timeout: Request timeout in seconds

    Returns:
        LLMResponse with content, provider, model, and token counts
    """
    assignment = get_model_for(call_site)

    # Try primary model
    response = await _call_model(
        assignment.provider,
        assignment.model_id,
        system_prompt,
        user_prompt,
        max_tokens,
        temperature,
        timeout,
    )

    # If failed and fallback configured, try fallback
    if response.error and assignment.fallback_provider and assignment.fallback_model_id:
        response = await _call_model(
            assignment.fallback_provider,
            assignment.fallback_model_id,
            system_prompt,
            user_prompt,
            max_tokens,
            temperature,
            timeout,
        )

    return response


async def _call_model(
    provider: str,
    model_id: str,
    system_prompt: Optional[str],
    user_prompt: str,
    max_tokens: int,
    temperature: float,
    timeout: float,
) -> LLMResponse:
    """Call a specific model."""
    if provider == "ollama":
        return await _call_ollama(model_id, system_prompt, user_prompt, max_tokens, temperature, timeout)
    elif provider == "anthropic":
        return await _call_anthropic(model_id, system_prompt, user_prompt, max_tokens, temperature, timeout)
    elif provider == "openai":
        return await _call_openai(model_id, system_prompt, user_prompt, max_tokens, temperature, timeout)
    else:
        return LLMResponse(
            content="",
            provider=provider,
            model_id=model_id,
            error=f"Unknown provider: {provider}",
        )


async def _call_ollama(
    model_id: str,
    system_prompt: Optional[str],
    user_prompt: str,
    max_tokens: int,
    temperature: float,
    timeout: float,
) -> LLMResponse:
    """Call Ollama model."""
    if not OLLAMA_ENABLED:
        return LLMResponse(
            content="",
            provider="ollama",
            model_id=model_id,
            error="Ollama not enabled",
        )

    # Build prompt
    if system_prompt:
        prompt = f"System: {system_prompt}\n\nUser: {user_prompt}"
    else:
        prompt = user_prompt

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": model_id,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    },
                },
            )

            if response.status_code != 200:
                return LLMResponse(
                    content="",
                    provider="ollama",
                    model_id=model_id,
                    error=f"HTTP {response.status_code}: {response.text[:200]}",
                )

            data = response.json()
            return LLMResponse(
                content=data.get("response", ""),
                provider="ollama",
                model_id=model_id,
                input_tokens=data.get("prompt_eval_count", 0),
                output_tokens=data.get("eval_count", 0),
            )

    except Exception as e:
        return LLMResponse(
            content="",
            provider="ollama",
            model_id=model_id,
            error=str(e),
        )


async def _call_anthropic(
    model_id: str,
    system_prompt: Optional[str],
    user_prompt: str,
    max_tokens: int,
    temperature: float,
    timeout: float,
) -> LLMResponse:
    """Call Anthropic model."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return LLMResponse(
            content="",
            provider="anthropic",
            model_id=model_id,
            error="ANTHROPIC_API_KEY not set",
        )

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            messages = [{"role": "user", "content": user_prompt}]

            body = {
                "model": model_id,
                "max_tokens": max_tokens,
                "messages": messages,
            }

            if system_prompt:
                body["system"] = system_prompt

            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=body,
            )

            if response.status_code != 200:
                return LLMResponse(
                    content="",
                    provider="anthropic",
                    model_id=model_id,
                    error=f"HTTP {response.status_code}: {response.text[:200]}",
                )

            data = response.json()
            content = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    content += block.get("text", "")

            usage = data.get("usage", {})
            return LLMResponse(
                content=content,
                provider="anthropic",
                model_id=model_id,
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
            )

    except Exception as e:
        return LLMResponse(
            content="",
            provider="anthropic",
            model_id=model_id,
            error=str(e),
        )


async def _call_openai(
    model_id: str,
    system_prompt: Optional[str],
    user_prompt: str,
    max_tokens: int,
    temperature: float,
    timeout: float,
) -> LLMResponse:
    """Call OpenAI model."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or not OPENAI_ENABLED:
        return LLMResponse(
            content="",
            provider="openai",
            model_id=model_id,
            error="OpenAI not configured",
        )

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": user_prompt})

            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "content-type": "application/json",
                },
                json={
                    "model": model_id,
                    "max_tokens": max_tokens,
                    "messages": messages,
                    "temperature": temperature,
                },
            )

            if response.status_code != 200:
                return LLMResponse(
                    content="",
                    provider="openai",
                    model_id=model_id,
                    error=f"HTTP {response.status_code}: {response.text[:200]}",
                )

            data = response.json()
            content = data["choices"][0]["message"]["content"]

            usage = data.get("usage", {})
            return LLMResponse(
                content=content,
                provider="openai",
                model_id=model_id,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
            )

    except Exception as e:
        return LLMResponse(
            content="",
            provider="openai",
            model_id=model_id,
            error=str(e),
        )


# Synchronous wrapper for code that can't use async
def call_llm_sync(
    call_site: str,
    system_prompt: Optional[str] = None,
    user_prompt: str = "",
    max_tokens: int = 1000,
    temperature: float = 0.7,
    timeout: float = 120.0,
) -> LLMResponse:
    """Synchronous version of call_llm."""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
        # If we're in an async context, we need to use a different approach
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                asyncio.run,
                call_llm(call_site, system_prompt, user_prompt, max_tokens, temperature, timeout)
            )
            return future.result()
    except RuntimeError:
        # No event loop running, we can use asyncio.run directly
        return asyncio.run(
            call_llm(call_site, system_prompt, user_prompt, max_tokens, temperature, timeout)
        )
