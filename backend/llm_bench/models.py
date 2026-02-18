"""
Model configurations for benchmarking.

Defines available models across providers and their characteristics.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Provider(Enum):
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    OPENAI = "openai"


@dataclass
class ModelConfig:
    """Configuration for a model to benchmark."""

    name: str  # Display name
    provider: Provider
    model_id: str  # API model identifier
    context_window: int = 8192
    output_limit: int = 4096
    cost_per_1k_input: float = 0.0  # USD per 1k input tokens
    cost_per_1k_output: float = 0.0  # USD per 1k output tokens
    supports_json_mode: bool = False
    notes: str = ""
    # For Ollama models that need to be pulled
    pull_command: Optional[str] = None

    @property
    def is_local(self) -> bool:
        return self.provider == Provider.OLLAMA

    @property
    def is_free(self) -> bool:
        return self.cost_per_1k_input == 0 and self.cost_per_1k_output == 0


# =============================================================================
# Anthropic Models (baseline comparison)
# =============================================================================

HAIKU = ModelConfig(
    name="Haiku 4.5",
    provider=Provider.ANTHROPIC,
    model_id="claude-haiku-4-5-20251001",
    context_window=200000,
    output_limit=8192,
    cost_per_1k_input=0.001,  # $1/MTok
    cost_per_1k_output=0.005,  # $5/MTok
    supports_json_mode=False,
    notes="Current production model for internal tasks. Fast, cheap, reliable.",
)

SONNET = ModelConfig(
    name="Sonnet 4",
    provider=Provider.ANTHROPIC,
    model_id="claude-sonnet-4-20250514",
    context_window=200000,
    output_limit=16384,
    cost_per_1k_input=0.003,  # $3/MTok
    cost_per_1k_output=0.015,  # $15/MTok
    supports_json_mode=False,
    notes="High-quality model for creative/complex tasks. 3x input, 3x output cost vs Haiku.",
)

# =============================================================================
# Ollama Models - Currently Installed
# =============================================================================

LLAMA_3_1_8B = ModelConfig(
    name="Llama 3.1 8B",
    provider=Provider.OLLAMA,
    model_id="llama3.1:8b-instruct-q8_0",
    context_window=128000,
    output_limit=4096,
    supports_json_mode=True,
    notes="Meta's Llama 3.1 8B quantized. Good general purpose, already installed.",
)

QWEN_2_5_7B = ModelConfig(
    name="Qwen 2.5 7B",
    provider=Provider.OLLAMA,
    model_id="qwen2.5:latest",
    context_window=32768,
    output_limit=4096,
    supports_json_mode=True,
    notes="Alibaba's Qwen 2.5 7B. Excellent at structured output and JSON.",
)

QWEN_2_5_14B = ModelConfig(
    name="Qwen 2.5 14B",
    provider=Provider.OLLAMA,
    model_id="qwen2.5:14b",
    context_window=32768,
    output_limit=4096,
    supports_json_mode=True,
    notes="Larger Qwen. Better reasoning, still fits in VRAM.",
)

# =============================================================================
# Ollama Models - Recommended to Pull
# =============================================================================

MISTRAL_7B = ModelConfig(
    name="Mistral 7B",
    provider=Provider.OLLAMA,
    model_id="mistral:7b-instruct-v0.3-q8_0",
    context_window=32768,
    output_limit=4096,
    supports_json_mode=True,
    notes="Mistral's 7B. Fast, good at following instructions.",
    pull_command="ollama pull mistral:7b-instruct-v0.3-q8_0",
)

MIXTRAL_8X7B = ModelConfig(
    name="Mixtral 8x7B",
    provider=Provider.OLLAMA,
    model_id="mixtral:8x7b-instruct-v0.1-q4_K_M",
    context_window=32768,
    output_limit=4096,
    supports_json_mode=True,
    notes="MoE model. Uses ~26GB VRAM. Strong reasoning.",
    pull_command="ollama pull mixtral:8x7b-instruct-v0.1-q4_K_M",
)

PHI_3_MEDIUM = ModelConfig(
    name="Phi-3 Medium",
    provider=Provider.OLLAMA,
    model_id="phi3:medium-128k",
    context_window=128000,
    output_limit=4096,
    supports_json_mode=True,
    notes="Microsoft's Phi-3 14B. Good at reasoning, long context.",
    pull_command="ollama pull phi3:medium-128k",
)

GEMMA_2_9B = ModelConfig(
    name="Gemma 2 9B",
    provider=Provider.OLLAMA,
    model_id="gemma2:9b-instruct-q8_0",
    context_window=8192,
    output_limit=4096,
    supports_json_mode=True,
    notes="Google's Gemma 2 9B. Good balance of speed and quality.",
    pull_command="ollama pull gemma2:9b-instruct-q8_0",
)

LLAMA_3_2_3B = ModelConfig(
    name="Llama 3.2 3B",
    provider=Provider.OLLAMA,
    model_id="llama3.2:3b-instruct-q8_0",
    context_window=128000,
    output_limit=4096,
    supports_json_mode=True,
    notes="Smallest Llama 3.2. Very fast, good for simple tasks.",
    pull_command="ollama pull llama3.2:3b-instruct-q8_0",
)

DEEPSEEK_R1_7B = ModelConfig(
    name="DeepSeek R1 7B",
    provider=Provider.OLLAMA,
    model_id="deepseek-r1:7b",
    context_window=65536,
    output_limit=4096,
    supports_json_mode=True,
    notes="DeepSeek's reasoning model. Chain-of-thought built-in.",
    pull_command="ollama pull deepseek-r1:7b",
)

DEEPSEEK_R1_14B = ModelConfig(
    name="DeepSeek R1 14B",
    provider=Provider.OLLAMA,
    model_id="deepseek-r1:14b",
    context_window=65536,
    output_limit=4096,
    supports_json_mode=True,
    notes="Larger DeepSeek reasoning model.",
    pull_command="ollama pull deepseek-r1:14b",
)

# =============================================================================
# OpenAI Models (optional comparison)
# =============================================================================

GPT_4O_MINI = ModelConfig(
    name="GPT-4o Mini",
    provider=Provider.OPENAI,
    model_id="gpt-4o-mini",
    context_window=128000,
    output_limit=16384,
    cost_per_1k_input=0.00015,  # $0.15/MTok
    cost_per_1k_output=0.0006,  # $0.60/MTok
    supports_json_mode=True,
    notes="OpenAI's small model. Very cheap, good at JSON.",
)

# =============================================================================
# Model Collections
# =============================================================================

# All available models
ALL_MODELS: dict[str, ModelConfig] = {
    # Anthropic
    "haiku": HAIKU,
    "sonnet": SONNET,
    # Ollama - installed
    "llama3.1:8b": LLAMA_3_1_8B,
    "qwen2.5:7b": QWEN_2_5_7B,
    "qwen2.5:14b": QWEN_2_5_14B,
    # Ollama - to pull
    "mistral:7b": MISTRAL_7B,
    "mixtral:8x7b": MIXTRAL_8X7B,
    "phi3:medium": PHI_3_MEDIUM,
    "gemma2:9b": GEMMA_2_9B,
    "llama3.2:3b": LLAMA_3_2_3B,
    "deepseek-r1:7b": DEEPSEEK_R1_7B,
    "deepseek-r1:14b": DEEPSEEK_R1_14B,
    # OpenAI
    "gpt-4o-mini": GPT_4O_MINI,
}

# Recommended models for comprehensive testing
RECOMMENDED_MODELS = [
    "haiku",  # Baseline
    "llama3.1:8b",  # Current local default
    "qwen2.5:14b",  # Best installed local
    "mistral:7b",  # Fast, good at instructions
    "gemma2:9b",  # Google's offering
    "deepseek-r1:7b",  # Reasoning specialist
]

# Models good for structured JSON output
JSON_SPECIALISTS = [
    "qwen2.5:14b",
    "qwen2.5:7b",
    "mistral:7b",
    "gpt-4o-mini",
]

# Models good for creative/narrative tasks
CREATIVE_MODELS = [
    "sonnet",  # Best but expensive
    "qwen2.5:14b",
    "mixtral:8x7b",
    "deepseek-r1:14b",
]

# Fastest models (for high-frequency calls)
FAST_MODELS = [
    "llama3.2:3b",
    "mistral:7b",
    "qwen2.5:7b",
    "haiku",
]


def get_model_configs(model_names: list[str]) -> list[ModelConfig]:
    """Get ModelConfig objects for a list of model names."""
    configs = []
    for name in model_names:
        if name in ALL_MODELS:
            configs.append(ALL_MODELS[name])
        else:
            raise ValueError(f"Unknown model: {name}. Available: {list(ALL_MODELS.keys())}")
    return configs


def get_models_to_pull() -> list[ModelConfig]:
    """Get list of models that need to be pulled."""
    return [m for m in ALL_MODELS.values() if m.pull_command is not None]


def check_ollama_models() -> dict[str, bool]:
    """Check which Ollama models are installed."""
    import subprocess

    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=10
        )
        installed = set()
        for line in result.stdout.strip().split("\n")[1:]:  # Skip header
            if line.strip():
                model_id = line.split()[0]
                installed.add(model_id)

        return {
            name: config.model_id in installed or any(
                config.model_id.startswith(m.split(":")[0]) for m in installed
            )
            for name, config in ALL_MODELS.items()
            if config.provider == Provider.OLLAMA
        }
    except Exception:
        return {}
