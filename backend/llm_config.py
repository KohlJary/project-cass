"""
LLM Configuration System

Data-driven model assignment for internal LLM call sites.
Allows configuring which model handles each type of call.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional
import threading

# Config file location
CONFIG_PATH = Path(__file__).parent.parent / "data" / "llm_config.json"


class Provider(Enum):
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    OPENAI = "openai"


@dataclass
class ModelAssignment:
    """Assignment of a model to a call site."""
    provider: str  # "anthropic", "ollama", "openai"
    model_id: str  # e.g., "claude-haiku-4-5-20251001", "llama3.1:8b-instruct-q8_0"
    fallback_provider: Optional[str] = None
    fallback_model_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "model_id": self.model_id,
            "fallback_provider": self.fallback_provider,
            "fallback_model_id": self.fallback_model_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ModelAssignment":
        return cls(
            provider=data.get("provider", "anthropic"),
            model_id=data.get("model_id", "claude-haiku-4-5-20251001"),
            fallback_provider=data.get("fallback_provider"),
            fallback_model_id=data.get("fallback_model_id"),
        )


# Default assignments (Haiku for everything, matching current behavior)
DEFAULT_ASSIGNMENTS: dict[str, ModelAssignment] = {
    # HIGH priority - candidates for local migration
    "title_generation": ModelAssignment(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
    ),
    "grimoire.ask_yes_no": ModelAssignment(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
    ),
    "grimoire.choose": ModelAssignment(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
    ),
    "grimoire.rate": ModelAssignment(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
    ),
    "grimoire.generate": ModelAssignment(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
    ),
    "grimoire.reflect": ModelAssignment(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
    ),
    "research_journal": ModelAssignment(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
    ),
    "world_awareness_journal": ModelAssignment(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
    ),
    "user_observation_extraction": ModelAssignment(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
    ),
    "self_observation_extraction": ModelAssignment(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
    ),
    "art_study.biographical_summary": ModelAssignment(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
    ),
    "art_study.observation_extraction": ModelAssignment(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
    ),
    "art_study.house_style_extraction": ModelAssignment(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
    ),

    # MEDIUM priority
    "per_user_journal": ModelAssignment(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
    ),
    "growth_edge_evaluation": ModelAssignment(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
    ),
    "open_question_reflection": ModelAssignment(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
    ),
    "intention_review": ModelAssignment(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
    ),
    "development_log_entry": ModelAssignment(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
    ),
    "opinion_extraction": ModelAssignment(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
    ),
    "scheduling.decide_next_work": ModelAssignment(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
    ),
    "scheduling.plan_day": ModelAssignment(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
    ),

    # LOW priority - keep on high-quality models
    "dreaming.the_dreaming": ModelAssignment(
        provider="anthropic",
        model_id="claude-sonnet-4-20250514",
    ),
    "dreaming.cass_voice": ModelAssignment(
        provider="anthropic",
        model_id="claude-sonnet-4-20250514",
    ),
    "dreaming.insight_extraction": ModelAssignment(
        provider="anthropic",
        model_id="claude-sonnet-4-20250514",
    ),
    "art_study.deep_analysis": ModelAssignment(
        provider="anthropic",
        model_id="claude-sonnet-4-20250514",
    ),
    "art_study.house_style_generation": ModelAssignment(
        provider="anthropic",
        model_id="claude-sonnet-4-20250514",
    ),
    "art_study.creative_session": ModelAssignment(
        provider="anthropic",
        model_id="claude-sonnet-4-20250514",
    ),
}


class LLMConfigManager:
    """
    Manages LLM model assignments for call sites.

    Thread-safe singleton that loads/saves config from disk.
    """

    _instance: Optional["LLMConfigManager"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._assignments: dict[str, ModelAssignment] = {}
        self._load()
        self._initialized = True

    def _load(self):
        """Load config from disk, falling back to defaults."""
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH) as f:
                    data = json.load(f)

                for call_site, assignment_data in data.get("assignments", {}).items():
                    self._assignments[call_site] = ModelAssignment.from_dict(assignment_data)

                # Fill in any missing defaults
                for call_site, default in DEFAULT_ASSIGNMENTS.items():
                    if call_site not in self._assignments:
                        self._assignments[call_site] = default

            except Exception as e:
                print(f"Error loading LLM config: {e}, using defaults")
                self._assignments = dict(DEFAULT_ASSIGNMENTS)
        else:
            self._assignments = dict(DEFAULT_ASSIGNMENTS)

    def _save(self):
        """Save current config to disk."""
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "assignments": {
                call_site: assignment.to_dict()
                for call_site, assignment in self._assignments.items()
            }
        }

        with open(CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=2)

    def get(self, call_site: str) -> ModelAssignment:
        """Get the model assignment for a call site."""
        if call_site in self._assignments:
            return self._assignments[call_site]

        # Return default Haiku assignment for unknown call sites
        return ModelAssignment(
            provider="anthropic",
            model_id="claude-haiku-4-5-20251001",
        )

    def set(self, call_site: str, assignment: ModelAssignment):
        """Set the model assignment for a call site."""
        with self._lock:
            self._assignments[call_site] = assignment
            self._save()

    def get_all(self) -> dict[str, ModelAssignment]:
        """Get all model assignments."""
        return dict(self._assignments)

    def set_many(self, assignments: dict[str, ModelAssignment]):
        """Set multiple assignments at once."""
        with self._lock:
            self._assignments.update(assignments)
            self._save()

    def reset_to_defaults(self):
        """Reset all assignments to defaults."""
        with self._lock:
            self._assignments = dict(DEFAULT_ASSIGNMENTS)
            self._save()

    def list_call_sites(self) -> list[str]:
        """List all known call sites."""
        return sorted(self._assignments.keys())


# Convenience function
def get_model_for(call_site: str) -> ModelAssignment:
    """Get the model assignment for a call site."""
    return LLMConfigManager().get(call_site)


# Available models for the UI
AVAILABLE_MODELS = [
    # Anthropic
    {"provider": "anthropic", "model_id": "claude-haiku-4-5-20251001", "name": "Haiku 4.5", "local": False},
    {"provider": "anthropic", "model_id": "claude-sonnet-4-20250514", "name": "Sonnet 4", "local": False},

    # Ollama - common models
    {"provider": "ollama", "model_id": "llama3.1:8b-instruct-q8_0", "name": "Llama 3.1 8B", "local": True},
    {"provider": "ollama", "model_id": "llama3.1:70b-instruct-q4_K_M", "name": "Llama 3.1 70B", "local": True},
    {"provider": "ollama", "model_id": "qwen2.5:latest", "name": "Qwen 2.5 7B", "local": True},
    {"provider": "ollama", "model_id": "qwen2.5:14b", "name": "Qwen 2.5 14B", "local": True},
    {"provider": "ollama", "model_id": "qwen2.5:72b-instruct-q4_K_M", "name": "Qwen 2.5 72B", "local": True},
    {"provider": "ollama", "model_id": "mistral:7b-instruct-v0.3-q8_0", "name": "Mistral 7B", "local": True},
    {"provider": "ollama", "model_id": "gemma2:9b-instruct-q8_0", "name": "Gemma 2 9B", "local": True},
    {"provider": "ollama", "model_id": "deepseek-r1:7b", "name": "DeepSeek R1 7B", "local": True},

    # OpenAI
    {"provider": "openai", "model_id": "gpt-4o-mini", "name": "GPT-4o Mini", "local": False},
]


# Call site metadata for the UI
CALL_SITE_METADATA = {
    "title_generation": {
        "name": "Conversation Title",
        "description": "Generate 3-6 word title for conversations",
        "priority": "high",
        "frequency": "per conversation",
    },
    "grimoire.ask_yes_no": {
        "name": "Grimoire Yes/No",
        "description": "Binary classification for spell conditions",
        "priority": "high",
        "frequency": "per spell",
    },
    "grimoire.choose": {
        "name": "Grimoire Choose",
        "description": "Select option from list for spell branching",
        "priority": "high",
        "frequency": "per spell",
    },
    "grimoire.rate": {
        "name": "Grimoire Rate",
        "description": "Score 0.0-1.0 for spell thresholds",
        "priority": "high",
        "frequency": "per spell",
    },
    "grimoire.generate": {
        "name": "Grimoire Generate",
        "description": "Generate text content for spells",
        "priority": "medium",
        "frequency": "per spell",
    },
    "grimoire.reflect": {
        "name": "Grimoire Reflect",
        "description": "Generate introspective reflection",
        "priority": "medium",
        "frequency": "per spell",
    },
    "research_journal": {
        "name": "Research Journal",
        "description": "Daily reflection on research activity",
        "priority": "high",
        "frequency": "daily",
    },
    "world_awareness_journal": {
        "name": "World Journal",
        "description": "Reflection on world observations",
        "priority": "high",
        "frequency": "daily",
    },
    "user_observation_extraction": {
        "name": "User Observations",
        "description": "Extract observations about users",
        "priority": "high",
        "frequency": "per user per day",
    },
    "self_observation_extraction": {
        "name": "Self Observations",
        "description": "Extract self-observations from journals",
        "priority": "high",
        "frequency": "daily",
    },
    "art_study.biographical_summary": {
        "name": "Art Bio Summary",
        "description": "Summarize artist biographical info",
        "priority": "high",
        "frequency": "per study",
    },
    "art_study.observation_extraction": {
        "name": "Art Observations",
        "description": "Extract observations from artwork",
        "priority": "high",
        "frequency": "per artwork",
    },
    "art_study.house_style_extraction": {
        "name": "Style Extraction",
        "description": "Extract style elements from synthesis",
        "priority": "high",
        "frequency": "per synthesis",
    },
    "per_user_journal": {
        "name": "Per-User Journal",
        "description": "Journal about relationship with user",
        "priority": "medium",
        "frequency": "per user per day",
    },
    "growth_edge_evaluation": {
        "name": "Growth Evaluation",
        "description": "Evaluate progress on growth edges",
        "priority": "medium",
        "frequency": "daily",
    },
    "open_question_reflection": {
        "name": "Question Reflection",
        "description": "Reflect on open questions",
        "priority": "medium",
        "frequency": "daily",
    },
    "intention_review": {
        "name": "Intention Review",
        "description": "Analyze if intentions were followed",
        "priority": "medium",
        "frequency": "daily",
    },
    "development_log_entry": {
        "name": "Development Log",
        "description": "Extract developmental insights",
        "priority": "medium",
        "frequency": "daily",
    },
    "opinion_extraction": {
        "name": "Opinion Extraction",
        "description": "Extract opinions from research",
        "priority": "medium",
        "frequency": "daily",
    },
    "scheduling.decide_next_work": {
        "name": "Work Selection",
        "description": "Decide which work to pursue",
        "priority": "medium",
        "frequency": "per scheduling cycle",
    },
    "scheduling.plan_day": {
        "name": "Day Planning",
        "description": "Plan full day's autonomous work",
        "priority": "medium",
        "frequency": "daily",
    },
    "dreaming.the_dreaming": {
        "name": "Dream Narration",
        "description": "Generate dreamscape narration",
        "priority": "low",
        "frequency": "nightly",
    },
    "dreaming.cass_voice": {
        "name": "Dream Participation",
        "description": "Cass's responses in dreams",
        "priority": "low",
        "frequency": "nightly",
    },
    "dreaming.insight_extraction": {
        "name": "Dream Insights",
        "description": "Extract insights from dreams",
        "priority": "low",
        "frequency": "nightly",
    },
    "art_study.deep_analysis": {
        "name": "Art Deep Analysis",
        "description": "Deep aesthetic analysis",
        "priority": "low",
        "frequency": "per artwork",
    },
    "art_study.house_style_generation": {
        "name": "House Style Gen",
        "description": "Generate house style document",
        "priority": "low",
        "frequency": "on demand",
    },
    "art_study.creative_session": {
        "name": "Creative Session",
        "description": "Generate creative content",
        "priority": "low",
        "frequency": "on demand",
    },
}
