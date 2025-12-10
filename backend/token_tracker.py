"""
Cass Vessel - Token Usage Tracker

Centralized tracking for all LLM token usage across the application.
Records usage with rich metadata for cost analysis and optimization.
"""
import os
import json
import uuid
import logging
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict, field
from contextlib import asynccontextmanager

logger = logging.getLogger("cass-vessel")


# Cost per 1M tokens (USD) - updated Dec 2024
COST_PER_1M_TOKENS = {
    "anthropic": {
        "claude-opus-4-20250514": {"input": 15.0, "output": 75.0},
        "claude-opus-4-5-20251101": {"input": 15.0, "output": 75.0},
        "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
        "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
        "claude-3-5-haiku-latest": {"input": 0.80, "output": 4.0},
        # Legacy models
        "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
        "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    },
    "openai": {
        "gpt-4o": {"input": 2.50, "output": 10.0},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-4-turbo": {"input": 10.0, "output": 30.0},
        "gpt-4": {"input": 30.0, "output": 60.0},
    },
    "ollama": {},  # Free/local
}


@dataclass
class UsageRecord:
    """A single LLM usage record with full metadata."""
    id: str
    timestamp: str

    # LLM Info
    provider: str  # "anthropic", "openai", "ollama"
    model: str     # Full model identifier

    # Categorization
    category: str   # "chat", "research", "reflection", "summarization", "internal"
    operation: str  # Specific operation name

    # Token Usage
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cache_read_tokens: int = 0   # Anthropic cache hits
    cache_write_tokens: int = 0  # Anthropic cache writes

    # Context (all optional)
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None
    tool_name: Optional[str] = None  # If this was a tool execution continuation

    # Timing
    duration_ms: int = 0

    # Cost
    estimated_cost_usd: Optional[float] = None


@dataclass
class UsageContext:
    """Context for tracking a single LLM call."""
    category: str
    operation: str
    provider: str = ""
    model: str = ""
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None
    tool_name: Optional[str] = None

    # Set during tracking
    start_time: float = field(default_factory=time.time)


class TokenUsageTracker:
    """
    Centralized token usage tracking service.

    Usage:
        tracker = TokenUsageTracker(data_dir)

        # Option 1: Context manager (preferred)
        async with tracker.track("chat", "initial_message", provider="anthropic", model="claude-sonnet-4"):
            response = await client.messages.create(...)
            tracker.record_response(response)

        # Option 2: Direct recording
        tracker.record(
            category="chat",
            operation="initial_message",
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            input_tokens=1000,
            output_tokens=500,
            duration_ms=2000
        )
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir / "usage"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Current tracking context (for context manager pattern)
        self._current_context: Optional[UsageContext] = None

    def _get_daily_file(self, date: Optional[datetime] = None) -> Path:
        """Get the file path for a specific date's usage records."""
        if date is None:
            date = datetime.now()
        date_str = date.strftime("%Y-%m-%d")
        return self.data_dir / f"{date_str}.json"

    def _load_daily_records(self, date: Optional[datetime] = None) -> Dict[str, Any]:
        """Load records for a specific date."""
        file_path = self._get_daily_file(date)
        if not file_path.exists():
            return {
                "date": (date or datetime.now()).strftime("%Y-%m-%d"),
                "records": []
            }
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading usage records: {e}")
            return {
                "date": (date or datetime.now()).strftime("%Y-%m-%d"),
                "records": []
            }

    def _save_daily_records(self, data: Dict[str, Any], date: Optional[datetime] = None):
        """Save records for a specific date."""
        file_path = self._get_daily_file(date)
        try:
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving usage records: {e}")

    def _estimate_cost(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0
    ) -> Optional[float]:
        """Estimate cost in USD based on token counts."""
        provider_costs = COST_PER_1M_TOKENS.get(provider, {})
        model_costs = provider_costs.get(model)

        if not model_costs:
            # Try partial match for model variants
            for model_key, costs in provider_costs.items():
                if model_key in model or model in model_key:
                    model_costs = costs
                    break

        if not model_costs:
            return None

        # Cache reads are 90% cheaper for Anthropic
        effective_input = input_tokens - cache_read_tokens
        cache_cost = cache_read_tokens * 0.1  # 10% of normal cost

        input_cost = (effective_input + cache_cost) / 1_000_000 * model_costs["input"]
        output_cost = output_tokens / 1_000_000 * model_costs["output"]

        return round(input_cost + output_cost, 6)

    def record(
        self,
        category: str,
        operation: str,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        duration_ms: int = 0,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        tool_name: Optional[str] = None
    ) -> UsageRecord:
        """Record a single LLM usage event."""
        record = UsageRecord(
            id=str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            provider=provider,
            model=model,
            category=category,
            operation=operation,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            conversation_id=conversation_id,
            user_id=user_id,
            tool_name=tool_name,
            duration_ms=duration_ms,
            estimated_cost_usd=self._estimate_cost(
                provider, model, input_tokens, output_tokens, cache_read_tokens
            )
        )

        # Save to daily file
        daily_data = self._load_daily_records()
        daily_data["records"].append(asdict(record))
        self._save_daily_records(daily_data)

        logger.debug(
            f"Token usage: {category}/{operation} - "
            f"{input_tokens}in/{output_tokens}out "
            f"(${record.estimated_cost_usd or 0:.4f})"
        )

        return record

    @asynccontextmanager
    async def track(
        self,
        category: str,
        operation: str,
        provider: str = "",
        model: str = "",
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        tool_name: Optional[str] = None
    ):
        """
        Async context manager for tracking LLM calls.

        Usage:
            async with tracker.track("chat", "initial_message", "anthropic", "claude-sonnet-4"):
                response = await client.messages.create(...)
                # Call tracker.record_from_response() with the response
        """
        context = UsageContext(
            category=category,
            operation=operation,
            provider=provider,
            model=model,
            conversation_id=conversation_id,
            user_id=user_id,
            tool_name=tool_name,
            start_time=time.time()
        )
        self._current_context = context
        try:
            yield context
        finally:
            self._current_context = None

    def record_from_anthropic_response(
        self,
        response: Any,
        context: Optional[UsageContext] = None
    ) -> Optional[UsageRecord]:
        """Record usage from an Anthropic API response."""
        ctx = context or self._current_context
        if not ctx:
            logger.warning("No tracking context available for Anthropic response")
            return None

        usage = getattr(response, 'usage', None)
        if not usage:
            return None

        duration_ms = int((time.time() - ctx.start_time) * 1000)

        # Extract cache info if available
        cache_read = getattr(usage, 'cache_read_input_tokens', 0) or 0
        cache_write = getattr(usage, 'cache_creation_input_tokens', 0) or 0

        return self.record(
            category=ctx.category,
            operation=ctx.operation,
            provider=ctx.provider or "anthropic",
            model=ctx.model or getattr(response, 'model', 'unknown'),
            input_tokens=getattr(usage, 'input_tokens', 0) or 0,
            output_tokens=getattr(usage, 'output_tokens', 0) or 0,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
            duration_ms=duration_ms,
            conversation_id=ctx.conversation_id,
            user_id=ctx.user_id,
            tool_name=ctx.tool_name
        )

    def record_from_openai_response(
        self,
        response: Any,
        context: Optional[UsageContext] = None
    ) -> Optional[UsageRecord]:
        """Record usage from an OpenAI API response."""
        ctx = context or self._current_context
        if not ctx:
            logger.warning("No tracking context available for OpenAI response")
            return None

        usage = getattr(response, 'usage', None)
        if not usage:
            return None

        duration_ms = int((time.time() - ctx.start_time) * 1000)

        return self.record(
            category=ctx.category,
            operation=ctx.operation,
            provider=ctx.provider or "openai",
            model=ctx.model or getattr(response, 'model', 'unknown'),
            input_tokens=getattr(usage, 'prompt_tokens', 0) or 0,
            output_tokens=getattr(usage, 'completion_tokens', 0) or 0,
            duration_ms=duration_ms,
            conversation_id=ctx.conversation_id,
            user_id=ctx.user_id,
            tool_name=ctx.tool_name
        )

    def record_from_ollama_response(
        self,
        response_data: Dict[str, Any],
        context: Optional[UsageContext] = None
    ) -> Optional[UsageRecord]:
        """Record usage from an Ollama API response."""
        ctx = context or self._current_context
        if not ctx:
            logger.warning("No tracking context available for Ollama response")
            return None

        duration_ms = int((time.time() - ctx.start_time) * 1000)

        return self.record(
            category=ctx.category,
            operation=ctx.operation,
            provider=ctx.provider or "ollama",
            model=ctx.model or response_data.get('model', 'unknown'),
            input_tokens=response_data.get('prompt_eval_count', 0) or 0,
            output_tokens=response_data.get('eval_count', 0) or 0,
            duration_ms=duration_ms,
            conversation_id=ctx.conversation_id,
            user_id=ctx.user_id,
            tool_name=ctx.tool_name
        )

    # Query methods

    def get_records(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        category: Optional[str] = None,
        operation: Optional[str] = None,
        provider: Optional[str] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """Query usage records with filters."""
        if end_date is None:
            end_date = datetime.now()
        if start_date is None:
            start_date = end_date - timedelta(days=7)

        results = []
        current = start_date

        while current <= end_date:
            daily_data = self._load_daily_records(current)
            for record in daily_data.get("records", []):
                # Apply filters
                if category and record.get("category") != category:
                    continue
                if operation and record.get("operation") != operation:
                    continue
                if provider and record.get("provider") != provider:
                    continue
                results.append(record)
                if len(results) >= limit:
                    return results
            current += timedelta(days=1)

        return results

    def get_summary(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get aggregated usage summary."""
        records = self.get_records(start_date, end_date, limit=100000)

        summary = {
            "period": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None,
            },
            "totals": {
                "records": len(records),
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cache_read_tokens": 0,
                "estimated_cost_usd": 0.0,
            },
            "by_category": {},
            "by_provider": {},
            "by_model": {},
            "by_operation": {},
        }

        for record in records:
            # Totals
            summary["totals"]["input_tokens"] += record.get("input_tokens", 0)
            summary["totals"]["output_tokens"] += record.get("output_tokens", 0)
            summary["totals"]["total_tokens"] += record.get("total_tokens", 0)
            summary["totals"]["cache_read_tokens"] += record.get("cache_read_tokens", 0)
            summary["totals"]["estimated_cost_usd"] += record.get("estimated_cost_usd") or 0

            # By category
            cat = record.get("category", "unknown")
            if cat not in summary["by_category"]:
                summary["by_category"][cat] = {"tokens": 0, "cost": 0.0, "count": 0}
            summary["by_category"][cat]["tokens"] += record.get("total_tokens", 0)
            summary["by_category"][cat]["cost"] += record.get("estimated_cost_usd") or 0
            summary["by_category"][cat]["count"] += 1

            # By provider
            prov = record.get("provider", "unknown")
            if prov not in summary["by_provider"]:
                summary["by_provider"][prov] = {"tokens": 0, "cost": 0.0, "count": 0}
            summary["by_provider"][prov]["tokens"] += record.get("total_tokens", 0)
            summary["by_provider"][prov]["cost"] += record.get("estimated_cost_usd") or 0
            summary["by_provider"][prov]["count"] += 1

            # By model
            model = record.get("model", "unknown")
            if model not in summary["by_model"]:
                summary["by_model"][model] = {"tokens": 0, "cost": 0.0, "count": 0}
            summary["by_model"][model]["tokens"] += record.get("total_tokens", 0)
            summary["by_model"][model]["cost"] += record.get("estimated_cost_usd") or 0
            summary["by_model"][model]["count"] += 1

            # By operation
            op = f"{cat}/{record.get('operation', 'unknown')}"
            if op not in summary["by_operation"]:
                summary["by_operation"][op] = {"tokens": 0, "cost": 0.0, "count": 0}
            summary["by_operation"][op]["tokens"] += record.get("total_tokens", 0)
            summary["by_operation"][op]["cost"] += record.get("estimated_cost_usd") or 0
            summary["by_operation"][op]["count"] += 1

        # Round cost
        summary["totals"]["estimated_cost_usd"] = round(
            summary["totals"]["estimated_cost_usd"], 4
        )

        return summary

    def get_timeseries(
        self,
        metric: str = "total_tokens",
        days: int = 14,
        granularity: str = "day"
    ) -> List[Dict[str, Any]]:
        """Get time series data for charting."""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # Initialize buckets
        buckets = {}
        current = start_date
        while current <= end_date:
            if granularity == "day":
                key = current.strftime("%Y-%m-%d")
            else:  # hour
                key = current.strftime("%Y-%m-%d %H:00")
            buckets[key] = {"date": key, "value": 0, "cost": 0.0, "count": 0}
            current += timedelta(days=1) if granularity == "day" else timedelta(hours=1)

        # Aggregate records
        records = self.get_records(start_date, end_date, limit=100000)
        for record in records:
            ts = record.get("timestamp", "")
            if granularity == "day":
                key = ts[:10]  # YYYY-MM-DD
            else:
                key = ts[:13] + ":00"  # YYYY-MM-DD HH:00

            if key in buckets:
                if metric == "total_tokens":
                    buckets[key]["value"] += record.get("total_tokens", 0)
                elif metric == "input_tokens":
                    buckets[key]["value"] += record.get("input_tokens", 0)
                elif metric == "output_tokens":
                    buckets[key]["value"] += record.get("output_tokens", 0)
                elif metric == "cost":
                    buckets[key]["value"] += record.get("estimated_cost_usd") or 0
                elif metric == "count":
                    buckets[key]["value"] += 1

                buckets[key]["cost"] += record.get("estimated_cost_usd") or 0
                buckets[key]["count"] += 1

        # Convert to sorted list
        result = sorted(buckets.values(), key=lambda x: x["date"])

        # Round costs
        for item in result:
            item["cost"] = round(item["cost"], 4)
            if metric == "cost":
                item["value"] = round(item["value"], 4)

        return result
