"""
Input capture system for LLM calls.

Captures real production inputs for later benchmarking.
"""

import json
import os
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional
from functools import wraps

# Default capture directory
CAPTURE_DIR = Path(__file__).parent.parent.parent / "data" / "llm_bench" / "captures"


@dataclass
class CapturedInput:
    """A captured LLM call input."""

    call_site: str  # e.g., "title_generation", "grimoire.ask_yes_no"
    timestamp: str
    system_prompt: Optional[str] = None
    user_prompt: str = ""
    context: dict = field(default_factory=dict)  # Additional context passed to the call
    expected_format: str = "text"  # "text", "json", "json_schema"
    json_schema: Optional[dict] = None  # If expecting structured JSON
    max_tokens: int = 1000
    temperature: float = 0.7
    # Metadata
    input_hash: str = ""  # For deduplication
    production_model: str = ""  # What model produced the original output
    production_output: str = ""  # The actual output from production (for comparison)

    def __post_init__(self):
        if not self.input_hash:
            # Hash the inputs for deduplication
            content = f"{self.call_site}:{self.system_prompt}:{self.user_prompt}:{json.dumps(self.context, sort_keys=True)}"
            self.input_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CapturedInput":
        return cls(**data)


class CaptureStore:
    """Storage for captured LLM inputs."""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or CAPTURE_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _call_site_dir(self, call_site: str) -> Path:
        """Get directory for a call site."""
        dir_path = self.base_dir / call_site.replace(".", "/")
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    def save(self, capture: CapturedInput) -> Path:
        """Save a captured input."""
        dir_path = self._call_site_dir(capture.call_site)
        filename = f"{capture.timestamp}_{capture.input_hash}.json"
        filepath = dir_path / filename

        with open(filepath, "w") as f:
            json.dump(capture.to_dict(), f, indent=2)

        return filepath

    def load(self, call_site: str, limit: int = 100) -> list[CapturedInput]:
        """Load captured inputs for a call site."""
        dir_path = self._call_site_dir(call_site)
        if not dir_path.exists():
            return []

        captures = []
        files = sorted(dir_path.glob("*.json"), reverse=True)[:limit]

        for filepath in files:
            try:
                with open(filepath) as f:
                    data = json.load(f)
                captures.append(CapturedInput.from_dict(data))
            except Exception as e:
                print(f"Error loading {filepath}: {e}")

        return captures

    def load_all(self, limit_per_site: int = 50) -> dict[str, list[CapturedInput]]:
        """Load all captured inputs grouped by call site."""
        result = {}

        for call_site_dir in self.base_dir.iterdir():
            if call_site_dir.is_dir():
                call_site = call_site_dir.name
                captures = self.load(call_site, limit=limit_per_site)
                if captures:
                    result[call_site] = captures

        return result

    def list_call_sites(self) -> list[str]:
        """List all call sites with captured data."""
        sites = []
        for path in self.base_dir.iterdir():
            if path.is_dir():
                sites.append(path.name)
        return sorted(sites)

    def count(self, call_site: Optional[str] = None) -> int:
        """Count captured inputs."""
        if call_site:
            dir_path = self._call_site_dir(call_site)
            return len(list(dir_path.glob("*.json")))
        else:
            total = 0
            for site in self.list_call_sites():
                total += self.count(site)
            return total

    def deduplicate(self, call_site: str) -> int:
        """Remove duplicate captures (same input_hash)."""
        captures = self.load(call_site, limit=10000)
        seen_hashes = set()
        removed = 0

        dir_path = self._call_site_dir(call_site)
        for filepath in dir_path.glob("*.json"):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                input_hash = data.get("input_hash", "")
                if input_hash in seen_hashes:
                    filepath.unlink()
                    removed += 1
                else:
                    seen_hashes.add(input_hash)
            except Exception:
                pass

        return removed


# Global capture store instance
_capture_store: Optional[CaptureStore] = None
_capture_enabled = os.environ.get("LLM_BENCH_CAPTURE", "false").lower() == "true"


def get_capture_store() -> CaptureStore:
    """Get the global capture store."""
    global _capture_store
    if _capture_store is None:
        _capture_store = CaptureStore()
    return _capture_store


def enable_capture(enabled: bool = True):
    """Enable or disable capture globally."""
    global _capture_enabled
    _capture_enabled = enabled


def capture_llm_call(
    call_site: str,
    system_prompt: Optional[str] = None,
    user_prompt: str = "",
    context: Optional[dict] = None,
    expected_format: str = "text",
    json_schema: Optional[dict] = None,
    max_tokens: int = 1000,
    temperature: float = 0.7,
    production_model: str = "",
    production_output: str = "",
) -> Optional[CapturedInput]:
    """
    Capture an LLM call input for later benchmarking.

    Call this at LLM call sites to record inputs.
    Only captures when LLM_BENCH_CAPTURE=true environment variable is set.
    """
    if not _capture_enabled:
        return None

    capture = CapturedInput(
        call_site=call_site,
        timestamp=datetime.now().isoformat(),
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        context=context or {},
        expected_format=expected_format,
        json_schema=json_schema,
        max_tokens=max_tokens,
        temperature=temperature,
        production_model=production_model,
        production_output=production_output,
    )

    store = get_capture_store()
    store.save(capture)

    return capture


def with_capture(call_site: str, expected_format: str = "text"):
    """
    Decorator to capture LLM call inputs.

    Usage:
        @with_capture("title_generation")
        def generate_title(system_prompt, user_prompt, **kwargs):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extract prompts from args/kwargs
            system_prompt = kwargs.get("system_prompt") or (args[0] if args else None)
            user_prompt = kwargs.get("user_prompt") or (args[1] if len(args) > 1 else "")

            # Call the original function
            result = func(*args, **kwargs)

            # Capture if enabled
            if _capture_enabled:
                capture_llm_call(
                    call_site=call_site,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    context=kwargs.get("context", {}),
                    expected_format=expected_format,
                    max_tokens=kwargs.get("max_tokens", 1000),
                    temperature=kwargs.get("temperature", 0.7),
                    production_model=kwargs.get("model", "unknown"),
                    production_output=str(result) if result else "",
                )

            return result

        return wrapper

    return decorator
