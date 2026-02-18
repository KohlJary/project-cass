"""
LLM Benchmarking Harness

Compare model performance across internal LLM call sites to find the best
model for each function. Supports Haiku, Sonnet, and local Ollama models.

Usage:
    # Capture inputs from production
    python -m llm_bench capture --days 7

    # Run benchmark across models
    python -m llm_bench run --call-site title_generation --models haiku,llama3.1:8b,qwen2.5:14b

    # Generate comparison report
    python -m llm_bench report --output results/
"""

from .models import ModelConfig, get_model_configs, RECOMMENDED_MODELS
from .capture import CaptureStore, capture_llm_call
from .runner import BenchmarkRunner
from .scorers import score_output, ScoreResult

__all__ = [
    "ModelConfig",
    "get_model_configs",
    "RECOMMENDED_MODELS",
    "CaptureStore",
    "capture_llm_call",
    "BenchmarkRunner",
    "score_output",
    "ScoreResult",
]
