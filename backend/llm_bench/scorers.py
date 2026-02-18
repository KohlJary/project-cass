"""
Scoring functions for evaluating model outputs.

Provides automated scoring for format compliance, completeness, and quality.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .capture import CapturedInput
from .runner import ModelOutput


@dataclass
class ScoreResult:
    """Scoring result for a single model output."""

    # Core scores (0.0 to 1.0)
    format_compliance: float = 0.0  # Did it follow the expected format?
    completeness: float = 0.0  # Did it include all required elements?
    coherence: float = 0.0  # Is the output internally consistent?

    # Metrics
    output_length: int = 0
    latency_ms: float = 0.0
    tokens_per_second: float = 0.0

    # JSON-specific
    json_valid: Optional[bool] = None
    json_schema_valid: Optional[bool] = None
    json_fields_present: list[str] = field(default_factory=list)
    json_fields_missing: list[str] = field(default_factory=list)

    # Flags
    has_error: bool = False
    error_message: str = ""

    # Overall score (weighted combination)
    overall: float = 0.0

    def to_dict(self) -> dict:
        return {
            "format_compliance": self.format_compliance,
            "completeness": self.completeness,
            "coherence": self.coherence,
            "output_length": self.output_length,
            "latency_ms": self.latency_ms,
            "tokens_per_second": self.tokens_per_second,
            "json_valid": self.json_valid,
            "json_schema_valid": self.json_schema_valid,
            "json_fields_present": self.json_fields_present,
            "json_fields_missing": self.json_fields_missing,
            "has_error": self.has_error,
            "error_message": self.error_message,
            "overall": self.overall,
        }


def _extract_json(text: str) -> Optional[dict | list]:
    """Try to extract JSON from text, handling markdown code blocks."""
    # Try direct parse first
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Try to find JSON in code blocks
    patterns = [
        r"```json\s*([\s\S]*?)\s*```",
        r"```\s*([\s\S]*?)\s*```",
        r"\{[\s\S]*\}",
        r"\[[\s\S]*\]",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                candidate = match.group(1) if "```" in pattern else match.group(0)
                return json.loads(candidate.strip())
            except (json.JSONDecodeError, IndexError):
                continue

    return None


def _check_json_schema(data: Any, schema: dict) -> tuple[bool, list[str], list[str]]:
    """
    Basic JSON schema validation.

    Returns: (valid, fields_present, fields_missing)
    """
    if not isinstance(data, dict):
        return False, [], list(schema.get("required", []))

    fields_present = []
    fields_missing = []

    required = schema.get("required", [])
    properties = schema.get("properties", {})

    for field_name in required:
        if field_name in data:
            fields_present.append(field_name)
        else:
            fields_missing.append(field_name)

    # Check optional fields too
    for field_name in properties:
        if field_name not in required and field_name in data:
            fields_present.append(field_name)

    valid = len(fields_missing) == 0
    return valid, fields_present, fields_missing


def score_json_output(
    output: ModelOutput, capture: CapturedInput
) -> ScoreResult:
    """Score a JSON-expected output."""
    result = ScoreResult(
        output_length=len(output.output),
        latency_ms=output.latency_ms,
    )

    if output.error:
        result.has_error = True
        result.error_message = output.error
        return result

    # Calculate tokens per second
    if output.latency_ms > 0 and output.output_tokens > 0:
        result.tokens_per_second = output.output_tokens / (output.latency_ms / 1000)

    # Try to parse JSON
    parsed = _extract_json(output.output)
    result.json_valid = parsed is not None

    if not result.json_valid:
        result.format_compliance = 0.0
        result.completeness = 0.0
        result.coherence = 0.5  # Might still be coherent text
        result.overall = 0.1
        return result

    result.format_compliance = 1.0

    # Check schema if provided
    if capture.json_schema:
        valid, present, missing = _check_json_schema(parsed, capture.json_schema)
        result.json_schema_valid = valid
        result.json_fields_present = present
        result.json_fields_missing = missing

        if capture.json_schema.get("required"):
            result.completeness = len(present) / len(
                capture.json_schema["required"]
            )
        else:
            result.completeness = 1.0 if valid else 0.5
    else:
        result.completeness = 1.0  # No schema to check against

    # Coherence: check that values are non-empty and reasonable
    if isinstance(parsed, dict):
        non_empty = sum(1 for v in parsed.values() if v not in [None, "", [], {}])
        result.coherence = non_empty / max(len(parsed), 1)
    else:
        result.coherence = 1.0 if parsed else 0.0

    # Overall score
    result.overall = (
        result.format_compliance * 0.4
        + result.completeness * 0.4
        + result.coherence * 0.2
    )

    return result


def score_text_output(
    output: ModelOutput, capture: CapturedInput
) -> ScoreResult:
    """Score a free-text output."""
    result = ScoreResult(
        output_length=len(output.output),
        latency_ms=output.latency_ms,
    )

    if output.error:
        result.has_error = True
        result.error_message = output.error
        return result

    # Calculate tokens per second
    if output.latency_ms > 0 and output.output_tokens > 0:
        result.tokens_per_second = output.output_tokens / (output.latency_ms / 1000)

    text = output.output.strip()

    # Format compliance: did it produce text?
    if not text:
        result.format_compliance = 0.0
        result.completeness = 0.0
        result.coherence = 0.0
        result.overall = 0.0
        return result

    result.format_compliance = 1.0

    # Completeness: reasonable length for the task
    min_expected = 10  # Minimum characters
    max_expected = capture.max_tokens * 4  # Rough chars estimate

    if len(text) < min_expected:
        result.completeness = len(text) / min_expected
    elif len(text) > max_expected * 2:
        result.completeness = 0.8  # Penalize excessive length slightly
    else:
        result.completeness = 1.0

    # Coherence: basic heuristics
    # - Sentences end with punctuation
    # - No obvious truncation
    # - No repeated phrases
    coherence_score = 1.0

    # Check for truncation
    if text[-1] not in ".!?\"')":
        coherence_score -= 0.2

    # Check for repetition (same phrase 3+ times)
    words = text.lower().split()
    if len(words) > 10:
        for i in range(len(words) - 5):
            phrase = " ".join(words[i : i + 3])
            if text.lower().count(phrase) >= 3:
                coherence_score -= 0.3
                break

    result.coherence = max(0.0, coherence_score)

    # Overall score
    result.overall = (
        result.format_compliance * 0.3
        + result.completeness * 0.3
        + result.coherence * 0.4
    )

    return result


def score_output(output: ModelOutput, capture: CapturedInput) -> ScoreResult:
    """
    Score a model output based on the expected format.

    Automatically selects the appropriate scorer based on capture.expected_format.
    """
    if capture.expected_format in ("json", "json_schema"):
        return score_json_output(output, capture)
    else:
        return score_text_output(output, capture)


# =============================================================================
# Call-site specific scorers
# =============================================================================


def score_title_generation(output: ModelOutput, capture: CapturedInput) -> ScoreResult:
    """Score title generation output."""
    result = score_text_output(output, capture)

    text = output.output.strip()

    # Title-specific checks
    word_count = len(text.split())

    # Ideal: 3-6 words
    if 3 <= word_count <= 6:
        result.completeness = 1.0
    elif 2 <= word_count <= 8:
        result.completeness = 0.8
    else:
        result.completeness = 0.5

    # No newlines in title
    if "\n" in text:
        result.format_compliance = 0.5

    # Recalculate overall
    result.overall = (
        result.format_compliance * 0.3
        + result.completeness * 0.4
        + result.coherence * 0.3
    )

    return result


def score_yes_no(output: ModelOutput, capture: CapturedInput) -> ScoreResult:
    """Score yes/no classification output."""
    # Override to expect JSON
    capture.expected_format = "json"
    capture.json_schema = {
        "required": ["answer"],
        "properties": {
            "answer": {"type": "boolean"},
            "reasoning": {"type": "string"},
        },
    }

    result = score_json_output(output, capture)

    # Additional check: answer must be boolean
    parsed = _extract_json(output.output)
    if parsed and isinstance(parsed, dict):
        answer = parsed.get("answer")
        if answer is True or answer is False:
            pass  # Good
        elif isinstance(answer, str) and answer.lower() in ("yes", "no", "true", "false"):
            result.format_compliance = 0.8  # Acceptable but not ideal
        else:
            result.format_compliance = 0.3

    result.overall = (
        result.format_compliance * 0.5
        + result.completeness * 0.3
        + result.coherence * 0.2
    )

    return result


def score_rating(output: ModelOutput, capture: CapturedInput) -> ScoreResult:
    """Score rating output (0.0-1.0 float)."""
    capture.expected_format = "json"
    capture.json_schema = {
        "required": ["rating"],
        "properties": {
            "rating": {"type": "number"},
            "reasoning": {"type": "string"},
        },
    }

    result = score_json_output(output, capture)

    # Additional check: rating must be 0.0-1.0
    parsed = _extract_json(output.output)
    if parsed and isinstance(parsed, dict):
        rating = parsed.get("rating")
        if isinstance(rating, (int, float)):
            if 0.0 <= rating <= 1.0:
                pass  # Perfect
            elif 0 <= rating <= 100:
                result.format_compliance = 0.7  # Used 0-100 scale
            else:
                result.format_compliance = 0.3
        else:
            result.format_compliance = 0.2

    result.overall = (
        result.format_compliance * 0.5
        + result.completeness * 0.3
        + result.coherence * 0.2
    )

    return result


# Registry of call-site specific scorers
CALL_SITE_SCORERS: dict[str, Callable[[ModelOutput, CapturedInput], ScoreResult]] = {
    "title_generation": score_title_generation,
    "grimoire.ask_yes_no": score_yes_no,
    "grimoire.choose": score_json_output,
    "grimoire.rate": score_rating,
}


def get_scorer(call_site: str) -> Callable[[ModelOutput, CapturedInput], ScoreResult]:
    """Get the appropriate scorer for a call site."""
    return CALL_SITE_SCORERS.get(call_site, score_output)
