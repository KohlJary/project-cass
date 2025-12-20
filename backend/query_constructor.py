"""
Query Constructor - Natural Language to StateQuery Translation

Uses local Ollama LLM to translate natural language intents into
structured StateQuery objects for the unified state query interface.

Follows patterns from:
- capability_registry.py (Ollama async httpx pattern)
- memory/summaries.py (temperature 0.3 for deterministic extraction)
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from config import OLLAMA_ENABLED, OLLAMA_BASE_URL, OLLAMA_MODEL
from query_models import StateQuery, TimeRange, Aggregation
from capability_registry import CapabilityMatch


logger = logging.getLogger(__name__)


@dataclass
class ConstructionResult:
    """Result of query construction attempt."""
    success: bool
    query: Optional[StateQuery] = None
    raw_output: Optional[str] = None
    error: Optional[str] = None
    confidence: float = 0.0
    fallback_used: bool = False


class QueryConstructor:
    """
    Translates natural language intents into StateQuery objects.

    Uses Ollama for structured extraction with:
    - Temperature 0.3 for deterministic output
    - JSON output format
    - Capability context injection for grounding
    - Fallback to heuristic matching if Ollama fails
    """

    def __init__(
        self,
        ollama_base_url: str = None,
        ollama_model: str = None,
    ):
        self._base_url = ollama_base_url or OLLAMA_BASE_URL
        self._model = ollama_model or OLLAMA_MODEL

    async def construct_query(
        self,
        intent: str,
        capabilities: List[CapabilityMatch],
        available_sources: List[str],
    ) -> ConstructionResult:
        """
        Construct a StateQuery from natural language intent.

        Args:
            intent: Natural language query like "how much have we spent on tokens?"
            capabilities: Relevant capabilities from semantic search
            available_sources: List of registered source IDs

        Returns:
            ConstructionResult with query or error
        """
        if not OLLAMA_ENABLED:
            logger.debug("Ollama disabled, using heuristic construction")
            return await self._heuristic_construct(intent, capabilities, available_sources)

        try:
            return await self._ollama_construct(intent, capabilities, available_sources)
        except Exception as e:
            logger.warning(f"Ollama construction failed, using heuristic: {e}")
            result = await self._heuristic_construct(intent, capabilities, available_sources)
            result.fallback_used = True
            return result

    async def _ollama_construct(
        self,
        intent: str,
        capabilities: List[CapabilityMatch],
        available_sources: List[str],
    ) -> ConstructionResult:
        """Use Ollama to construct query via structured extraction."""

        prompt = self._build_prompt(intent, capabilities, available_sources)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 200,
                    }
                }
            )

            if response.status_code != 200:
                return ConstructionResult(
                    success=False,
                    error=f"Ollama request failed: {response.status_code}",
                    raw_output=response.text,
                )

            result = response.json()
            raw_output = result.get("response", "").strip()

            return self._parse_llm_output(raw_output)

    def _build_prompt(
        self,
        intent: str,
        capabilities: List[CapabilityMatch],
        available_sources: List[str],
    ) -> str:
        """Build the prompt for query construction."""

        cap_text = self._format_capabilities(capabilities)
        sources_text = ", ".join(available_sources)

        return f"""You are a query constructor. Given a natural language intent, output a JSON object that specifies how to query data.

Available data sources: {sources_text}

Relevant capabilities (from semantic search):
{cap_text}

Time presets: today, yesterday, last_24h, last_7d, last_30d, this_week, this_month, all_time
Aggregations: sum, avg, count, max, min, latest
Group by options: day, hour, week, provider, category

User intent: "{intent}"

Output ONLY a valid JSON object with these fields (omit optional fields if not needed):
{{
  "source": "<source_id>",
  "metric": "<metric_name or 'all'>",
  "time_preset": "<optional time preset>",
  "aggregation": "<optional aggregation function>",
  "group_by": "<optional grouping dimension>"
}}

JSON:"""

    def _format_capabilities(self, capabilities: List[CapabilityMatch]) -> str:
        """Format capability matches for prompt context."""
        if not capabilities:
            return "No specific capabilities matched. Use 'all' metric for general queries."

        lines = []
        for cap in capabilities:
            lines.append(f"- {cap.source_id}:{cap.metric_name} - {cap.description}")
        return "\n".join(lines)

    def _parse_llm_output(self, raw_output: str) -> ConstructionResult:
        """Parse LLM output into StateQuery."""

        try:
            # Try to extract JSON from response (handle markdown wrapping)
            json_match = re.search(r'\{[^{}]*\}', raw_output, re.DOTALL)
            if not json_match:
                return ConstructionResult(
                    success=False,
                    error="No JSON object found in response",
                    raw_output=raw_output,
                )

            data = json.loads(json_match.group())

            # Validate required field
            if "source" not in data:
                return ConstructionResult(
                    success=False,
                    error="Missing required 'source' field",
                    raw_output=raw_output,
                )

            # Build TimeRange
            time_range = None
            if data.get("time_preset"):
                time_range = TimeRange(preset=data["time_preset"])

            # Build Aggregation
            aggregation = None
            if data.get("aggregation"):
                aggregation = Aggregation(function=data["aggregation"])

            # Build StateQuery
            query = StateQuery(
                source=data["source"],
                metric=data.get("metric", "all"),
                time_range=time_range,
                aggregation=aggregation,
                group_by=data.get("group_by"),
                filters=data.get("filters"),
            )

            return ConstructionResult(
                success=True,
                query=query,
                raw_output=raw_output,
                confidence=0.9,
            )

        except json.JSONDecodeError as e:
            return ConstructionResult(
                success=False,
                error=f"JSON parse error: {e}",
                raw_output=raw_output,
            )

    async def _heuristic_construct(
        self,
        intent: str,
        capabilities: List[CapabilityMatch],
        available_sources: List[str],
    ) -> ConstructionResult:
        """
        Fallback heuristic construction when Ollama is unavailable.

        Uses keyword matching and capability scores to infer query.
        """
        intent_lower = intent.lower()

        # Time range heuristics
        time_preset = None
        if "today" in intent_lower:
            time_preset = "today"
        elif "yesterday" in intent_lower:
            time_preset = "yesterday"
        elif "this week" in intent_lower:
            time_preset = "this_week"
        elif "this month" in intent_lower:
            time_preset = "this_month"
        elif "last 7" in intent_lower or "past week" in intent_lower:
            time_preset = "last_7d"
        elif "last 30" in intent_lower or "past month" in intent_lower:
            time_preset = "last_30d"
        elif "last 24" in intent_lower:
            time_preset = "last_24h"

        # Source/metric from best capability match
        if capabilities:
            best = capabilities[0]
            source = best.source_id
            metric = best.metric_name
        else:
            # Keyword fallbacks
            if any(kw in intent_lower for kw in ["cost", "spend", "spent", "token", "usage", "dollar", "$"]):
                source = "tokens"
                metric = "all"
            elif any(kw in intent_lower for kw in ["star", "fork", "clone", "view", "github", "repo"]):
                source = "github"
                metric = "all"
            elif any(kw in intent_lower for kw in ["conversation", "chat", "message"]):
                source = "conversations"
                metric = "all"
            elif any(kw in intent_lower for kw in ["memory", "journal", "thread", "question"]):
                source = "memory"
                metric = "all"
            elif any(kw in intent_lower for kw in ["goal", "objective", "plan"]):
                source = "goals"
                metric = "all"
            elif any(kw in intent_lower for kw in ["self", "observation", "identity"]):
                source = "self"
                metric = "all"
            else:
                return ConstructionResult(
                    success=False,
                    error="Could not determine source from intent",
                    confidence=0.0,
                    fallback_used=True,
                )

        # Build query
        query = StateQuery(
            source=source,
            metric=metric,
            time_range=TimeRange(preset=time_preset) if time_preset else None,
        )

        return ConstructionResult(
            success=True,
            query=query,
            confidence=0.5,
            fallback_used=True,
        )


# Module-level singleton
_query_constructor: Optional[QueryConstructor] = None


def get_query_constructor() -> QueryConstructor:
    """Get or create the query constructor singleton."""
    global _query_constructor
    if _query_constructor is None:
        _query_constructor = QueryConstructor()
    return _query_constructor
