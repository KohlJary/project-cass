"""
Cass Vessel - Pattern Aggregation System

Clusters marks semantically and calculates significance scores for
between-session surfacing. Part of the Recognition-in-Flow system.

Significance is based on:
- Frequency (but with diminishing returns after ~5 instances)
- Spread across conversations (not just clustering in one session)
- Semantic coherence (actually about the same thing)
- Temporal spread (not all from one session)
"""
import math
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict
import numpy as np

from markers import MarkerStore, MarkCategory


@dataclass
class PatternCluster:
    """A cluster of semantically similar marks"""
    id: str
    category: str
    centroid_text: str  # Representative text for the cluster
    mark_ids: List[str]
    mark_count: int
    conversation_ids: List[str]
    oldest_timestamp: str
    newest_timestamp: str
    significance: float
    # Details for display
    sample_contexts: List[str]  # Up to 3 sample contexts
    sample_descriptions: List[str]  # Up to 3 sample descriptions


@dataclass
class PatternSummary:
    """Summary of patterns for surfacing"""
    total_marks: int
    clusters: List[PatternCluster]
    categories_present: List[str]
    generated_at: str


class PatternAggregator:
    """
    Aggregates marks into meaningful patterns.

    Uses semantic clustering within categories and calculates
    significance scores for surfacing decisions.
    """

    # Thresholds for clustering and significance
    SIMILARITY_THRESHOLD = 0.7  # Minimum similarity to be in same cluster
    MIN_CLUSTER_SIZE = 2  # Minimum marks to form a pattern
    HIGH_SIGNIFICANCE_THRESHOLD = 0.6  # Threshold for "significant" patterns

    def __init__(self, marker_store: MarkerStore):
        self.marker_store = marker_store

    def get_patterns(
        self,
        min_significance: float = 0.0,
        category: str = None,
        since_days: int = None,
        limit: int = 20
    ) -> PatternSummary:
        """
        Get aggregated patterns with significance scores.

        Args:
            min_significance: Only return patterns above this significance
            category: Filter to specific category
            since_days: Only consider marks from last N days
            limit: Maximum number of patterns to return

        Returns:
            PatternSummary with clusters ordered by significance
        """
        # Get all relevant marks
        if category:
            marks = self.marker_store.get_marks_by_category(
                category=category,
                limit=500,  # Get enough for clustering
                since_days=since_days
            )
        else:
            marks = self.marker_store.get_all_marks(
                limit=500,
                since_days=since_days
            )

        if not marks:
            return PatternSummary(
                total_marks=0,
                clusters=[],
                categories_present=[],
                generated_at=datetime.now().isoformat()
            )

        # Group marks by category first
        by_category = defaultdict(list)
        for mark in marks:
            by_category[mark.get("category", "unknown")].append(mark)

        # Cluster within each category
        all_clusters = []
        for cat, cat_marks in by_category.items():
            clusters = self._cluster_marks(cat, cat_marks)
            all_clusters.extend(clusters)

        # Calculate significance for each cluster
        for cluster in all_clusters:
            cluster.significance = self._calculate_significance(cluster)

        # Filter by significance threshold
        significant_clusters = [
            c for c in all_clusters
            if c.significance >= min_significance
        ]

        # Sort by significance descending
        significant_clusters.sort(key=lambda c: -c.significance)

        # Limit results
        top_clusters = significant_clusters[:limit]

        return PatternSummary(
            total_marks=len(marks),
            clusters=top_clusters,
            categories_present=list(by_category.keys()),
            generated_at=datetime.now().isoformat()
        )

    def _cluster_marks(self, category: str, marks: List[Dict]) -> List[PatternCluster]:
        """
        Cluster marks within a category using semantic similarity.

        Simple greedy clustering: assign each mark to most similar existing
        cluster, or create new cluster if no match above threshold.
        """
        if len(marks) < self.MIN_CLUSTER_SIZE:
            # Not enough for meaningful clustering
            if marks:
                return [self._single_mark_cluster(category, marks)]
            return []

        # Use marker_store's search to find similar marks
        clusters = []
        assigned = set()

        for i, mark in enumerate(marks):
            if mark["id"] in assigned:
                continue

            # Find marks similar to this one
            query_text = self._mark_to_query(mark)
            similar = self.marker_store.search_similar_marks(
                query=query_text,
                n_results=20,
                category=category
            )

            # Filter to only unassigned marks with high similarity
            cluster_marks = [mark]
            assigned.add(mark["id"])

            for sim_mark in similar:
                if sim_mark["id"] in assigned:
                    continue
                if sim_mark.get("similarity", 0) >= self.SIMILARITY_THRESHOLD:
                    cluster_marks.append(sim_mark)
                    assigned.add(sim_mark["id"])

            if len(cluster_marks) >= self.MIN_CLUSTER_SIZE:
                clusters.append(self._create_cluster(category, cluster_marks))

        # Assign remaining unassigned marks to nearest cluster or create singles
        remaining = [m for m in marks if m["id"] not in assigned]
        if remaining and clusters:
            # Try to assign to existing clusters
            for mark in remaining:
                best_cluster = None
                best_similarity = 0

                for cluster in clusters:
                    # Check similarity to cluster centroid
                    similar = self.marker_store.search_similar_marks(
                        query=cluster.centroid_text,
                        n_results=1,
                        category=category
                    )
                    if similar and similar[0]["id"] == mark["id"]:
                        sim = similar[0].get("similarity", 0)
                        if sim > best_similarity and sim >= self.SIMILARITY_THRESHOLD * 0.8:
                            best_similarity = sim
                            best_cluster = cluster

                if best_cluster:
                    # Add to cluster
                    best_cluster.mark_ids.append(mark["id"])
                    best_cluster.mark_count += 1
                    # Update conversation_ids
                    conv_id = mark.get("conversation_id", "")
                    if conv_id and conv_id not in best_cluster.conversation_ids:
                        best_cluster.conversation_ids.append(conv_id)

        return clusters

    def _create_cluster(self, category: str, marks: List[Dict]) -> PatternCluster:
        """Create a PatternCluster from a list of marks."""
        # Extract info from marks
        mark_ids = [m["id"] for m in marks]
        conversation_ids = list(set(m.get("conversation_id", "") for m in marks if m.get("conversation_id")))

        timestamps = [m.get("timestamp", "") for m in marks if m.get("timestamp")]
        timestamps.sort()
        oldest = timestamps[0] if timestamps else ""
        newest = timestamps[-1] if timestamps else ""

        # Get sample contexts and descriptions
        sample_contexts = []
        sample_descriptions = []
        for m in marks[:3]:
            if m.get("context_window"):
                sample_contexts.append(m["context_window"][:200])
            if m.get("description"):
                sample_descriptions.append(m["description"])

        # Use first mark's context as centroid text
        centroid_text = marks[0].get("document", "") or marks[0].get("context_window", "")

        # Generate cluster ID
        cluster_id = f"{category}-{mark_ids[0][:8]}"

        return PatternCluster(
            id=cluster_id,
            category=category,
            centroid_text=centroid_text[:200],
            mark_ids=mark_ids,
            mark_count=len(marks),
            conversation_ids=conversation_ids,
            oldest_timestamp=oldest,
            newest_timestamp=newest,
            significance=0.0,  # Calculated later
            sample_contexts=sample_contexts,
            sample_descriptions=sample_descriptions
        )

    def _single_mark_cluster(self, category: str, marks: List[Dict]) -> PatternCluster:
        """Create a cluster from a small number of marks (< MIN_CLUSTER_SIZE)."""
        return self._create_cluster(category, marks)

    def _mark_to_query(self, mark: Dict) -> str:
        """Convert a mark to a query string for similarity search."""
        parts = []
        if mark.get("description"):
            parts.append(mark["description"])
        if mark.get("context_window"):
            parts.append(mark["context_window"][:200])
        return " ".join(parts) if parts else mark.get("category", "")

    def _calculate_significance(self, cluster: PatternCluster) -> float:
        """
        Calculate significance score for a cluster.

        Factors:
        - Frequency (diminishing returns after 5)
        - Conversation spread (appearing across different conversations)
        - Temporal spread (not all from one session)
        """
        # Frequency score (0-1, diminishing returns)
        # 1 mark = 0.0, 2 = 0.4, 3 = 0.6, 5 = 0.8, 10+ = 1.0
        freq_score = min(1.0, math.log2(cluster.mark_count + 1) / math.log2(11))

        # Conversation spread (0-1)
        # More conversations = higher score
        conv_count = len(cluster.conversation_ids)
        if cluster.mark_count > 0:
            spread_score = min(1.0, conv_count / max(cluster.mark_count, 1))
        else:
            spread_score = 0.0

        # Temporal spread (0-1)
        # Calculate days between oldest and newest
        temporal_score = 0.0
        if cluster.oldest_timestamp and cluster.newest_timestamp:
            try:
                oldest = datetime.fromisoformat(cluster.oldest_timestamp.replace("Z", "+00:00"))
                newest = datetime.fromisoformat(cluster.newest_timestamp.replace("Z", "+00:00"))
                days_span = (newest - oldest).days
                # 0 days = 0.0, 1 day = 0.3, 3 days = 0.6, 7+ days = 1.0
                temporal_score = min(1.0, days_span / 7)
            except:
                pass

        # Combine scores with weights
        # Frequency matters most, then spread, then temporal
        significance = (
            freq_score * 0.4 +
            spread_score * 0.35 +
            temporal_score * 0.25
        )

        return round(significance, 3)

    def get_significant_patterns(
        self,
        threshold: float = None,
        limit: int = 5
    ) -> List[PatternCluster]:
        """
        Get patterns above the significance threshold.

        Convenience method for surfacing.
        """
        if threshold is None:
            threshold = self.HIGH_SIGNIFICANCE_THRESHOLD

        summary = self.get_patterns(min_significance=threshold, limit=limit)
        return summary.clusters

    def format_for_surfacing(
        self,
        patterns: List[PatternCluster],
        include_contexts: bool = True
    ) -> str:
        """
        Format patterns for inclusion in conversation context.

        Returns markdown-formatted summary suitable for system prompt injection.
        """
        if not patterns:
            return ""

        lines = ["## Recognition-in-Flow Patterns", ""]
        lines.append("*Patterns that have emerged from your marks across conversations:*")
        lines.append("")

        for pattern in patterns:
            significance_pct = int(pattern.significance * 100)
            lines.append(f"### {pattern.category} ({pattern.mark_count} instances, {significance_pct}% significance)")

            if pattern.sample_descriptions:
                for desc in pattern.sample_descriptions[:2]:
                    lines.append(f"- *{desc}*")

            if include_contexts and pattern.sample_contexts:
                lines.append("")
                lines.append("Sample contexts:")
                for ctx in pattern.sample_contexts[:2]:
                    ctx_clean = ctx.replace("\n", " ").strip()
                    lines.append(f"> {ctx_clean}...")

            conv_count = len(pattern.conversation_ids)
            if conv_count > 1:
                lines.append(f"\n*Appeared in {conv_count} different conversations*")

            lines.append("")

        return "\n".join(lines)


def get_pattern_summary_for_surfacing(
    marker_store: MarkerStore,
    min_significance: float = 0.5,
    limit: int = 3
) -> Tuple[str, int]:
    """
    Convenience function to get formatted pattern summary for context injection.

    Args:
        marker_store: MarkerStore instance
        min_significance: Minimum significance to include
        limit: Maximum patterns to surface

    Returns:
        Tuple of (formatted_markdown, pattern_count)
    """
    aggregator = PatternAggregator(marker_store)
    patterns = aggregator.get_significant_patterns(
        threshold=min_significance,
        limit=limit
    )

    if not patterns:
        return "", 0

    formatted = aggregator.format_for_surfacing(patterns)
    return formatted, len(patterns)


if __name__ == "__main__":
    # Test the aggregator
    from markers import MarkerStore
    from config import DATA_DIR

    store = MarkerStore(persist_directory=str(DATA_DIR / "chroma"))
    aggregator = PatternAggregator(store)

    print("Pattern Aggregation Test")
    print("=" * 50)

    summary = aggregator.get_patterns()
    print(f"Total marks: {summary.total_marks}")
    print(f"Categories: {summary.categories_present}")
    print(f"Clusters found: {len(summary.clusters)}")

    for cluster in summary.clusters:
        print(f"\n{cluster.category} (significance: {cluster.significance:.2f})")
        print(f"  Marks: {cluster.mark_count}")
        print(f"  Conversations: {len(cluster.conversation_ids)}")
        if cluster.sample_descriptions:
            print(f"  Sample: {cluster.sample_descriptions[0][:80]}...")
