"""
Dashboard builder for research progress.
Extracted from routes/wiki.py for reusability and testability.
"""
from datetime import datetime
from typing import Dict, Any, Optional, List


class DashboardBuilder:
    """
    Builds research progress dashboards.

    Extracted from routes/wiki.py to enable:
    - Independent testing
    - Reuse in other contexts (CLI, reports, etc.)
    - Cleaner route code
    """

    def __init__(
        self,
        scheduler: Any = None,
        wiki_storage: Any = None,
        self_manager: Any = None
    ):
        """
        Args:
            scheduler: ResearchScheduler instance
            wiki_storage: WikiStorage instance
            self_manager: SelfManager instance
        """
        self._scheduler = scheduler
        self._wiki_storage = wiki_storage
        self._self_manager = self_manager

    def build(self) -> Dict[str, Any]:
        """
        Build a comprehensive research progress dashboard.

        Aggregates data from multiple sources into a unified view:
        - Research activity (queue stats, history, completion rates)
        - Wiki growth metrics (pages, links, coverage)
        - Knowledge graph health (connectivity, orphans, clusters)
        - Self-model integration (developmental stage, growth edges, recent observations)
        - Cross-context consistency (if available)

        Returns:
            Dashboard dictionary suitable for visualization
        """
        dashboard = {
            "generated_at": datetime.now().isoformat(),
            "research": {},
            "wiki": {},
            "graph": {},
            "self_model": {},
            "cross_context": {},
        }

        # Build each section
        dashboard["research"] = self._build_research_section()
        dashboard["graph"] = self._build_graph_section()
        dashboard["wiki"] = self._build_wiki_section()
        dashboard["self_model"] = self._build_self_model_section()
        dashboard["cross_context"] = self._build_cross_context_section()

        return dashboard

    def _build_research_section(self) -> Dict[str, Any]:
        """Build research activity section."""
        if not self._scheduler:
            return {}

        queue_stats = self._scheduler.queue.get_stats()
        result = {
            "queue": {
                "total": queue_stats.get("total", 0),
                "queued": queue_stats.get("by_status", {}).get("queued", 0),
                "in_progress": queue_stats.get("by_status", {}).get("in_progress", 0),
                "completed": queue_stats.get("by_status", {}).get("completed", 0),
                "failed": queue_stats.get("by_status", {}).get("failed", 0),
            },
            "by_type": queue_stats.get("by_type", {}),
            "mode": self._scheduler.config.mode.value,
            "last_refresh": self._scheduler._last_refresh.isoformat() if self._scheduler._last_refresh else None,
        }

        # Recent history - last 30 days completion
        history = self._scheduler.queue.get_history(limit=100)
        if history:
            by_date = {}
            for task in history:
                completed_at = task.get("completed_at", "")[:10]  # YYYY-MM-DD
                if completed_at:
                    by_date[completed_at] = by_date.get(completed_at, 0) + 1

            result["history"] = {
                "total_completed_30d": len(history),
                "by_date": by_date,
                "avg_daily": len(history) / 30 if len(by_date) > 0 else 0,
            }

        return result

    def _build_graph_section(self) -> Dict[str, Any]:
        """Build knowledge graph health section."""
        if not self._scheduler:
            return {}

        graph_stats = self._scheduler.get_graph_stats()
        return {
            "node_count": graph_stats.get("node_count", 0),
            "edge_count": graph_stats.get("edge_count", 0),
            "avg_connectivity": graph_stats.get("avg_connectivity", 0),
            "most_connected": graph_stats.get("most_connected", [])[:5],
            "orphan_count": graph_stats.get("orphan_count", 0),
            "sparse_count": graph_stats.get("sparse_count", 0),
        }

    def _build_wiki_section(self) -> Dict[str, Any]:
        """Build wiki growth metrics section."""
        if not self._wiki_storage:
            return {}

        maturity_stats = self._wiki_storage.get_maturity_stats()
        pages = self._wiki_storage.list_pages()
        graph = self._wiki_storage.get_link_graph()

        # Count pages by type
        by_type = {}
        for page in pages:
            ptype = page.page_type.value if hasattr(page.page_type, 'value') else str(page.page_type)
            by_type[ptype] = by_type.get(ptype, 0) + 1

        # Count total links and red links
        all_links = set()
        existing_pages = {p.name.lower() for p in pages}
        for targets in graph.values():
            all_links.update(targets)
        red_links = [link for link in all_links if link.lower() not in existing_pages]

        return {
            "total_pages": len(pages),
            "total_links": len(all_links),
            "red_links": len(red_links),
            "by_type": by_type,
            "maturity": {
                "avg_depth_score": maturity_stats.get("avg_depth_score", 0),
                "by_level": maturity_stats.get("by_level", {}),
                "deepening_candidates": maturity_stats.get("deepening_candidates", 0),
            },
        }

    def _build_self_model_section(self) -> Dict[str, Any]:
        """Build self-model integration section."""
        if not self._self_manager:
            return {}

        try:
            profile = self._self_manager.load_profile()

            # Growth edges
            growth_edges = [
                {
                    "area": edge.area,
                    "current_state": edge.current_state,
                    "desired_state": edge.desired_state,
                }
                for edge in profile.growth_edges[:5]
            ]

            # Recent observations (last 10)
            observations = self._self_manager.get_recent_observations(limit=10)
            recent_observations = [
                {
                    "observation": obs.observation[:200] + "..." if len(obs.observation) > 200 else obs.observation,
                    "category": obs.category,
                    "confidence": obs.confidence,
                    "timestamp": obs.timestamp,
                }
                for obs in observations
            ]

            # Developmental stage
            stage = self._self_manager._detect_developmental_stage()

            # Latest cognitive snapshot
            latest_snapshot = self._self_manager.get_latest_snapshot()
            snapshot_summary = None
            if latest_snapshot:
                snapshot_summary = {
                    "timestamp": latest_snapshot.timestamp,
                    "period": f"{latest_snapshot.period_start} to {latest_snapshot.period_end}",
                    "avg_authenticity_score": latest_snapshot.avg_authenticity_score,
                    "avg_agency_score": latest_snapshot.avg_agency_score,
                    "conversations_analyzed": latest_snapshot.conversations_analyzed,
                    "opinions_expressed": latest_snapshot.opinions_expressed,
                    "new_opinions_formed": latest_snapshot.new_opinions_formed,
                }

            # Development summary
            dev_summary = self._self_manager.get_recent_development_summary(days=7)

            return {
                "developmental_stage": stage,
                "growth_edges": growth_edges,
                "growth_edges_count": len(profile.growth_edges),
                "opinions_count": len(profile.opinions),
                "open_questions_count": len(profile.open_questions),
                "recent_observations": recent_observations,
                "observations_count": len(self._self_manager.load_observations()),
                "latest_snapshot": snapshot_summary,
                "development_summary_7d": {
                    "days_with_logs": dev_summary.get("days_with_logs", 0),
                    "growth_indicators": dev_summary.get("total_growth_indicators", 0),
                    "pattern_shifts": dev_summary.get("total_pattern_shifts", 0),
                    "milestones_triggered": dev_summary.get("total_milestones_triggered", 0),
                },
            }
        except Exception as e:
            return {"error": str(e)}

    def _build_cross_context_section(self) -> Dict[str, Any]:
        """Build cross-context consistency section."""
        try:
            from testing.cross_context_analyzer import CrossContextAnalyzer
            from config import DATA_DIR

            analyzer = CrossContextAnalyzer(str(DATA_DIR / "testing" / "cross_context"))
            consistency = analyzer.analyze_consistency()

            return {
                "overall_consistency": consistency.overall_score,
                "consistency_grade": consistency.grade,
                "samples_analyzed": consistency.total_samples,
                "context_coverage": consistency.context_coverage,
                "anomaly_count": len(consistency.anomalies),
                "key_findings": consistency.key_findings[:3] if consistency.key_findings else [],
            }
        except Exception as e:
            return {"error": str(e), "available": False}
