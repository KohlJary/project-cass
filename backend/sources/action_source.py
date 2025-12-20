"""
Actions Queryable Source

Wraps ActionRegistry as a queryable source for the unified state query interface.
Provides access to action definitions, categories, and execution history.

Refresh strategy: LAZY (definitions are static, read from JSON)
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from query_models import (
    StateQuery,
    QueryResult,
    QueryResultData,
    SourceSchema,
    MetricDefinition,
)
from queryable_source import QueryableSource, RefreshStrategy, RollupConfig


logger = logging.getLogger(__name__)


class ActionQueryableSource(QueryableSource):
    """
    Atomic actions as a queryable source.

    Wraps ActionRegistry and exposes action definitions through the unified query interface.
    Uses LAZY refresh since action definitions are mostly static (loaded from JSON).
    """

    def __init__(self, daemon_id: str):
        """
        Initialize the action queryable source.

        Args:
            daemon_id: The daemon this source belongs to
        """
        super().__init__(daemon_id)
        self._registry = None  # Lazy-load to avoid circular imports

    def _get_registry(self):
        """Get the action registry, lazy-loading if needed."""
        if self._registry is None:
            from scheduler.actions import get_action_registry
            self._registry = get_action_registry()
        return self._registry

    @property
    def source_id(self) -> str:
        return "actions"

    @property
    def refresh_strategy(self) -> RefreshStrategy:
        return RefreshStrategy.LAZY

    @property
    def rollup_config(self) -> RollupConfig:
        return RollupConfig(
            strategy=RefreshStrategy.LAZY,
            cache_ttl_seconds=300,  # Cache for 5 minutes (definitions rarely change)
            rollup_types=["summary"],
        )

    @property
    def schema(self) -> SourceSchema:
        return SourceSchema(
            metrics=[
                MetricDefinition(
                    name="all",
                    description="All action definitions in one response",
                    data_type="object",
                    supports_delta=False,
                    supports_timeseries=False,
                ),
                MetricDefinition(
                    name="total_actions",
                    description="Total number of registered actions",
                    data_type="int",
                    supports_delta=False,
                    supports_timeseries=False,
                    unit="actions",
                ),
                MetricDefinition(
                    name="by_category",
                    description="Actions grouped by category",
                    data_type="object",
                    supports_delta=False,
                    supports_timeseries=False,
                ),
                MetricDefinition(
                    name="categories",
                    description="List of all action categories",
                    data_type="list",
                    supports_delta=False,
                    supports_timeseries=False,
                ),
                MetricDefinition(
                    name="action_list",
                    description="List of all action IDs",
                    data_type="list",
                    supports_delta=False,
                    supports_timeseries=False,
                ),
                MetricDefinition(
                    name="action_details",
                    description="Details for a specific action (use filter action_id)",
                    data_type="object",
                    supports_delta=False,
                    supports_timeseries=False,
                ),
            ],
            aggregations=["count", "latest"],  # "latest" is default in StateQuery
            group_by_options=["category", "priority"],
            filter_keys=["action_id", "category", "priority", "requires_idle"],
            rollups=["summary"],
        )

    async def execute_query(self, query: StateQuery) -> QueryResult:
        """
        Execute a query against action data.

        Args:
            query: The StateQuery to execute

        Returns:
            QueryResult with action metrics
        """
        registry = self._get_registry()
        metric = query.metric
        filters = query.filters or {}
        group_by = query.group_by

        # Get all definitions
        all_defs = registry.get_all_definitions()

        # Build result based on requested metric
        if metric == "total_actions":
            value = len(all_defs)

        elif metric == "categories":
            categories = set()
            for defn in all_defs.values():
                categories.add(defn.category)
            value = sorted(list(categories))

        elif metric == "action_list":
            # Apply filters if any
            action_ids = []
            for action_id, defn in all_defs.items():
                if self._matches_filters(defn, filters):
                    action_ids.append(action_id)
            value = sorted(action_ids)

        elif metric == "by_category":
            by_cat: Dict[str, List[Dict]] = {}
            for action_id, defn in all_defs.items():
                if self._matches_filters(defn, filters):
                    cat = defn.category
                    if cat not in by_cat:
                        by_cat[cat] = []
                    by_cat[cat].append(self._defn_to_dict(action_id, defn))
            value = by_cat

        elif metric == "action_details":
            action_id = filters.get("action_id")
            if action_id and action_id in all_defs:
                value = self._defn_to_dict(action_id, all_defs[action_id])
            else:
                value = None

        elif metric == "all":
            # Return all definitions grouped by category
            by_cat: Dict[str, List[Dict]] = {}
            for action_id, defn in all_defs.items():
                cat = defn.category
                if cat not in by_cat:
                    by_cat[cat] = []
                by_cat[cat].append(self._defn_to_dict(action_id, defn))

            value = {
                "total": len(all_defs),
                "categories": sorted(by_cat.keys()),
                "by_category": by_cat,
            }

        else:
            # Unknown metric - return summary
            value = {
                "total": len(all_defs),
                "categories": list(set(d.category for d in all_defs.values())),
            }

        # Handle group_by
        if group_by == "category":
            by_cat = {}
            for action_id, defn in all_defs.items():
                cat = defn.category
                if cat not in by_cat:
                    by_cat[cat] = []
                by_cat[cat].append(action_id)
            value = {cat: len(actions) for cat, actions in by_cat.items()}

        elif group_by == "priority":
            by_priority = {}
            for action_id, defn in all_defs.items():
                priority = defn.priority
                if priority not in by_priority:
                    by_priority[priority] = []
                by_priority[priority].append(action_id)
            value = {p: len(actions) for p, actions in by_priority.items()}

        # Build result
        data = QueryResultData(value=value)

        return QueryResult(
            source=self.source_id,
            query=query,
            data=data,
            metadata={
                "total_actions": len(all_defs),
                "category_count": len(set(d.category for d in all_defs.values())),
            },
            timestamp=datetime.now(),
        )

    def _matches_filters(self, defn, filters: Dict) -> bool:
        """Check if a definition matches the given filters."""
        if not filters:
            return True

        if "category" in filters and defn.category != filters["category"]:
            return False
        if "priority" in filters and defn.priority != filters["priority"]:
            return False
        if "requires_idle" in filters and defn.requires_idle != filters["requires_idle"]:
            return False

        return True

    def _defn_to_dict(self, action_id: str, defn) -> Dict[str, Any]:
        """Convert an ActionDefinition to a dict."""
        return {
            "id": action_id,
            "name": defn.name,
            "description": defn.description,
            "category": defn.category,
            "handler": defn.handler,
            "estimated_cost_usd": defn.estimated_cost_usd,
            "default_duration_minutes": defn.default_duration_minutes,
            "priority": defn.priority,
            "requires_idle": defn.requires_idle,
            "runner_key": defn.runner_key,
        }

    async def compute_rollups(self, rollup_type: str) -> Dict[str, Any]:
        """
        Compute rollup aggregations for actions.

        Args:
            rollup_type: "summary"

        Returns:
            Dict with rollup data
        """
        registry = self._get_registry()
        all_defs = registry.get_all_definitions()

        by_cat = {}
        by_priority = {}

        for action_id, defn in all_defs.items():
            # By category
            cat = defn.category
            by_cat[cat] = by_cat.get(cat, 0) + 1

            # By priority
            priority = defn.priority
            by_priority[priority] = by_priority.get(priority, 0) + 1

        return {
            "rollup_type": rollup_type,
            "computed_at": datetime.now().isoformat(),
            "total_actions": len(all_defs),
            "category_count": len(by_cat),
            "by_category": by_cat,
            "by_priority": by_priority,
        }

    async def ensure_rollups_fresh(self) -> None:
        """Ensure rollups are computed (for LAZY strategy)."""
        if self._rollups is None or self._last_rollup_refresh is None:
            await self.refresh_rollups()
        else:
            elapsed = (datetime.now() - self._last_rollup_refresh).total_seconds()
            if elapsed > self.rollup_config.cache_ttl_seconds:
                await self.refresh_rollups()

    def get_precomputed_rollups(self) -> Dict[str, Any]:
        """Return currently cached rollup aggregates."""
        if self._rollups is None:
            return {}
        return self._rollups

    async def refresh_rollups(self) -> None:
        """Recompute rolling aggregates."""
        registry = self._get_registry()
        all_defs = registry.get_all_definitions()

        by_cat = {}
        by_priority = {}
        total_cost = 0.0

        for action_id, defn in all_defs.items():
            cat = defn.category
            by_cat[cat] = by_cat.get(cat, 0) + 1

            priority = defn.priority
            by_priority[priority] = by_priority.get(priority, 0) + 1

            total_cost += defn.estimated_cost_usd

        self._rollups = {
            "total_actions": len(all_defs),
            "category_count": len(by_cat),
            "by_category": by_cat,
            "by_priority": by_priority,
            "total_estimated_cost_usd": total_cost,
        }
        self._last_rollup_refresh = datetime.now()

    def get_current_summary(self) -> str:
        """Get a human-readable summary of available actions."""
        registry = self._get_registry()
        all_defs = registry.get_all_definitions()

        by_cat = {}
        for defn in all_defs.values():
            cat = defn.category
            by_cat[cat] = by_cat.get(cat, 0) + 1

        parts = [f"{len(all_defs)} atomic actions"]
        cat_summary = ", ".join(f"{cat}: {count}" for cat, count in sorted(by_cat.items()))
        if cat_summary:
            parts.append(f"({cat_summary})")

        return " ".join(parts)
