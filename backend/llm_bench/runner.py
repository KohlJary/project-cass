"""
Benchmark runner for comparing LLM outputs.

Runs captured inputs through multiple models and collects results.
"""

import asyncio
import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import httpx

from .models import ModelConfig, Provider, ALL_MODELS, get_model_configs
from .capture import CapturedInput, CaptureStore


@dataclass
class ModelOutput:
    """Output from a single model run."""

    model_name: str
    model_id: str
    provider: str
    output: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    error: Optional[str] = None
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class BenchmarkResult:
    """Result of benchmarking a single input across multiple models."""

    capture: CapturedInput
    outputs: list[ModelOutput] = field(default_factory=list)
    scores: dict[str, dict] = field(default_factory=dict)  # model_name -> score dict

    def to_dict(self) -> dict:
        return {
            "capture": self.capture.to_dict(),
            "outputs": [asdict(o) for o in self.outputs],
            "scores": self.scores,
        }


class BenchmarkRunner:
    """Run benchmarks across multiple models."""

    def __init__(
        self,
        models: list[str] | list[ModelConfig],
        ollama_base_url: str = "http://localhost:11434",
        anthropic_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
    ):
        if models and isinstance(models[0], str):
            self.models = get_model_configs(models)
        else:
            self.models = models

        self.ollama_base_url = ollama_base_url
        self.anthropic_api_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.openai_api_key = openai_api_key or os.environ.get("OPENAI_API_KEY")

        self._http_client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._http_client = httpx.AsyncClient(timeout=120.0)
        return self

    async def __aexit__(self, *args):
        if self._http_client:
            await self._http_client.aclose()

    async def _call_ollama(
        self, model: ModelConfig, capture: CapturedInput
    ) -> ModelOutput:
        """Call Ollama model."""
        start = time.perf_counter()

        # Build prompt
        prompt = ""
        if capture.system_prompt:
            prompt = f"System: {capture.system_prompt}\n\nUser: {capture.user_prompt}"
        else:
            prompt = capture.user_prompt

        try:
            response = await self._http_client.post(
                f"{self.ollama_base_url}/api/generate",
                json={
                    "model": model.model_id,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": capture.temperature,
                        "num_predict": capture.max_tokens,
                    },
                },
            )

            latency_ms = (time.perf_counter() - start) * 1000

            if response.status_code != 200:
                return ModelOutput(
                    model_name=model.name,
                    model_id=model.model_id,
                    provider="ollama",
                    output="",
                    latency_ms=latency_ms,
                    input_tokens=0,
                    output_tokens=0,
                    error=f"HTTP {response.status_code}: {response.text[:200]}",
                )

            data = response.json()
            return ModelOutput(
                model_name=model.name,
                model_id=model.model_id,
                provider="ollama",
                output=data.get("response", ""),
                latency_ms=latency_ms,
                input_tokens=data.get("prompt_eval_count", 0),
                output_tokens=data.get("eval_count", 0),
            )

        except Exception as e:
            return ModelOutput(
                model_name=model.name,
                model_id=model.model_id,
                provider="ollama",
                output="",
                latency_ms=(time.perf_counter() - start) * 1000,
                input_tokens=0,
                output_tokens=0,
                error=str(e),
            )

    async def _call_anthropic(
        self, model: ModelConfig, capture: CapturedInput
    ) -> ModelOutput:
        """Call Anthropic model."""
        if not self.anthropic_api_key:
            return ModelOutput(
                model_name=model.name,
                model_id=model.model_id,
                provider="anthropic",
                output="",
                latency_ms=0,
                input_tokens=0,
                output_tokens=0,
                error="ANTHROPIC_API_KEY not set",
            )

        start = time.perf_counter()

        try:
            messages = [{"role": "user", "content": capture.user_prompt}]

            body = {
                "model": model.model_id,
                "max_tokens": capture.max_tokens,
                "messages": messages,
            }

            if capture.system_prompt:
                body["system"] = capture.system_prompt

            response = await self._http_client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=body,
            )

            latency_ms = (time.perf_counter() - start) * 1000

            if response.status_code != 200:
                return ModelOutput(
                    model_name=model.name,
                    model_id=model.model_id,
                    provider="anthropic",
                    output="",
                    latency_ms=latency_ms,
                    input_tokens=0,
                    output_tokens=0,
                    error=f"HTTP {response.status_code}: {response.text[:200]}",
                )

            data = response.json()
            output_text = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    output_text += block.get("text", "")

            usage = data.get("usage", {})
            return ModelOutput(
                model_name=model.name,
                model_id=model.model_id,
                provider="anthropic",
                output=output_text,
                latency_ms=latency_ms,
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
            )

        except Exception as e:
            return ModelOutput(
                model_name=model.name,
                model_id=model.model_id,
                provider="anthropic",
                output="",
                latency_ms=(time.perf_counter() - start) * 1000,
                input_tokens=0,
                output_tokens=0,
                error=str(e),
            )

    async def _call_openai(
        self, model: ModelConfig, capture: CapturedInput
    ) -> ModelOutput:
        """Call OpenAI model."""
        if not self.openai_api_key:
            return ModelOutput(
                model_name=model.name,
                model_id=model.model_id,
                provider="openai",
                output="",
                latency_ms=0,
                input_tokens=0,
                output_tokens=0,
                error="OPENAI_API_KEY not set",
            )

        start = time.perf_counter()

        try:
            messages = []
            if capture.system_prompt:
                messages.append({"role": "system", "content": capture.system_prompt})
            messages.append({"role": "user", "content": capture.user_prompt})

            body = {
                "model": model.model_id,
                "max_tokens": capture.max_tokens,
                "messages": messages,
                "temperature": capture.temperature,
            }

            response = await self._http_client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "content-type": "application/json",
                },
                json=body,
            )

            latency_ms = (time.perf_counter() - start) * 1000

            if response.status_code != 200:
                return ModelOutput(
                    model_name=model.name,
                    model_id=model.model_id,
                    provider="openai",
                    output="",
                    latency_ms=latency_ms,
                    input_tokens=0,
                    output_tokens=0,
                    error=f"HTTP {response.status_code}: {response.text[:200]}",
                )

            data = response.json()
            output_text = data["choices"][0]["message"]["content"]

            usage = data.get("usage", {})
            return ModelOutput(
                model_name=model.name,
                model_id=model.model_id,
                provider="openai",
                output=output_text,
                latency_ms=latency_ms,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
            )

        except Exception as e:
            return ModelOutput(
                model_name=model.name,
                model_id=model.model_id,
                provider="openai",
                output="",
                latency_ms=(time.perf_counter() - start) * 1000,
                input_tokens=0,
                output_tokens=0,
                error=str(e),
            )

    async def run_single(
        self, capture: CapturedInput, model: ModelConfig
    ) -> ModelOutput:
        """Run a single capture through a single model."""
        if model.provider == Provider.OLLAMA:
            return await self._call_ollama(model, capture)
        elif model.provider == Provider.ANTHROPIC:
            return await self._call_anthropic(model, capture)
        elif model.provider == Provider.OPENAI:
            return await self._call_openai(model, capture)
        else:
            return ModelOutput(
                model_name=model.name,
                model_id=model.model_id,
                provider=model.provider.value,
                output="",
                latency_ms=0,
                input_tokens=0,
                output_tokens=0,
                error=f"Unknown provider: {model.provider}",
            )

    async def run_capture(
        self, capture: CapturedInput, parallel: bool = False
    ) -> BenchmarkResult:
        """Run a single capture through all configured models."""
        result = BenchmarkResult(capture=capture)

        if parallel:
            # Run all models in parallel
            tasks = [self.run_single(capture, model) for model in self.models]
            outputs = await asyncio.gather(*tasks)
            result.outputs = list(outputs)
        else:
            # Run sequentially (less resource contention for local models)
            for model in self.models:
                output = await self.run_single(capture, model)
                result.outputs.append(output)

        return result

    async def run_call_site(
        self,
        call_site: str,
        limit: int = 10,
        parallel_models: bool = False,
        parallel_captures: bool = False,
    ) -> list[BenchmarkResult]:
        """Run all captures for a call site through all models."""
        store = CaptureStore()
        captures = store.load(call_site, limit=limit)

        if not captures:
            print(f"No captures found for call site: {call_site}")
            return []

        print(f"Running {len(captures)} captures through {len(self.models)} models...")

        results = []
        if parallel_captures:
            tasks = [
                self.run_capture(capture, parallel=parallel_models)
                for capture in captures
            ]
            results = await asyncio.gather(*tasks)
        else:
            for i, capture in enumerate(captures):
                print(f"  [{i + 1}/{len(captures)}] {capture.input_hash[:8]}...")
                result = await self.run_capture(capture, parallel=parallel_models)
                results.append(result)

        return list(results)


async def run_benchmark(
    call_site: str,
    models: list[str],
    limit: int = 10,
    output_dir: Optional[Path] = None,
) -> list[BenchmarkResult]:
    """
    Convenience function to run a benchmark.

    Args:
        call_site: The call site to benchmark (e.g., "title_generation")
        models: List of model names to test
        limit: Max number of captures to test
        output_dir: Where to save results

    Returns:
        List of BenchmarkResult objects
    """
    async with BenchmarkRunner(models) as runner:
        results = await runner.run_call_site(call_site, limit=limit)

    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"{call_site}_{timestamp}.json"

        with open(output_file, "w") as f:
            json.dump([r.to_dict() for r in results], f, indent=2)

        print(f"Results saved to: {output_file}")

    return results
