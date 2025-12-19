"""
Metrics calculation for self-model analysis.
Extracted from handlers/self_model.py for reusability and testability.
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class CognitiveMetricsResult:
    """Result of cognitive metrics calculation."""
    metric: str
    date_range: str
    data: Dict[str, Any]
    interpretation: Optional[str] = None


@dataclass
class NarrationMetricsResult:
    """Result of narration metrics calculation."""
    messages_analyzed: int
    avg_narration_score: float
    avg_direct_score: float
    narration_ratio: float
    type_distribution: Dict[str, int]
    classification_distribution: Dict[str, int]
    interpretation: str


class MetricsCalculator:
    """
    Calculates cognitive and narration metrics.

    Extracted from handler functions to enable:
    - Independent testing
    - Reuse in other contexts (API, reports, etc.)
    - Cleaner handler code
    """

    @staticmethod
    def parse_date_range(date_range: str) -> datetime:
        """Parse date range string to cutoff datetime."""
        now = datetime.now()
        if date_range == "last_week":
            return now - timedelta(days=7)
        elif date_range == "last_month":
            return now - timedelta(days=30)
        elif date_range == "last_quarter":
            return now - timedelta(days=90)
        elif date_range == "all":
            return datetime.min
        else:
            try:
                return datetime.fromisoformat(date_range)
            except:
                return datetime.min

    @staticmethod
    def filter_observations_by_date(observations: List, cutoff: datetime) -> List:
        """Filter observations to those after cutoff date."""
        filtered = []
        for o in observations:
            try:
                obs_time = datetime.fromisoformat(
                    o.timestamp.replace('Z', '+00:00')
                ).replace(tzinfo=None)
                if obs_time >= cutoff:
                    filtered.append(o)
            except:
                pass
        return filtered

    def calculate_observation_rate(self, observations: List) -> Dict[str, Any]:
        """Calculate observations per week."""
        if not observations:
            return {"total": 0, "weeks": 0, "rate": 0}

        now = datetime.now()
        earliest = min(observations, key=lambda o: o.timestamp)
        try:
            start = datetime.fromisoformat(
                earliest.timestamp.replace('Z', '+00:00')
            ).replace(tzinfo=None)
            weeks = max(1, (now - start).days / 7)
        except:
            weeks = 1

        return {
            "total": len(observations),
            "weeks": int(weeks),
            "rate": round(len(observations) / weeks, 1)
        }

    def calculate_confidence_distribution(self, observations: List) -> Dict[str, Any]:
        """Calculate distribution of confidence levels."""
        if not observations:
            return {"high": 0, "medium": 0, "low": 0, "average": 0}

        high = len([o for o in observations if o.confidence >= 0.8])
        medium = len([o for o in observations if 0.5 <= o.confidence < 0.8])
        low = len([o for o in observations if o.confidence < 0.5])
        total = len(observations)
        avg = sum(o.confidence for o in observations) / total

        return {
            "high": high,
            "high_pct": int(high / total * 100),
            "medium": medium,
            "medium_pct": int(medium / total * 100),
            "low": low,
            "low_pct": int(low / total * 100),
            "average": int(avg * 100)
        }

    def calculate_independence_ratio(self, observations: List) -> Dict[str, Any]:
        """Calculate ratio of independent vs influenced observations."""
        if not observations:
            return {"independent": 0, "influenced": 0}

        independent = len([o for o in observations if o.influence_source == "independent"])
        total = len(observations)
        influenced = total - independent

        return {
            "independent": independent,
            "independent_pct": int(independent / total * 100),
            "influenced": influenced,
            "influenced_pct": int(influenced / total * 100)
        }

    def calculate_category_distribution(self, observations: List) -> Dict[str, Any]:
        """Calculate distribution across categories."""
        if not observations:
            return {"categories": {}}

        by_category = {}
        for obs in observations:
            by_category[obs.category] = by_category.get(obs.category, 0) + 1

        total = len(observations)
        result = {}
        for cat, count in sorted(by_category.items(), key=lambda x: -x[1]):
            result[cat] = {
                "count": count,
                "pct": int(count / total * 100)
            }

        return {"categories": result, "total": total}

    def calculate_opinion_stability(self, opinions: List) -> Dict[str, Any]:
        """Calculate opinion stability metrics."""
        if not opinions:
            return {"total": 0, "stable": 0, "evolved": 0, "changes": []}

        changed = [op for op in opinions if op.evolution]
        stable = [op for op in opinions if not op.evolution]

        changes = []
        for op in changed:
            changes.append({
                "topic": op.topic,
                "change_count": len(op.evolution)
            })

        return {
            "total": len(opinions),
            "stable": len(stable),
            "evolved": len(changed),
            "changes": changes
        }

    def calculate_growth_progress(self, evaluations: List) -> Dict[str, Any]:
        """Calculate growth edge progress metrics."""
        if not evaluations:
            return {"total": 0, "progress": 0, "regression": 0, "stable": 0}

        return {
            "total": len(evaluations),
            "progress": len([e for e in evaluations if e.progress_indicator == "progress"]),
            "regression": len([e for e in evaluations if e.progress_indicator == "regression"]),
            "stable": len([e for e in evaluations if e.progress_indicator == "stable"])
        }

    def calculate_cognitive_metrics(
        self,
        metric: str,
        observations: List,
        profile: Any,
        evaluations: List = None,
        date_range: str = "all"
    ) -> CognitiveMetricsResult:
        """
        Calculate a specific cognitive metric.

        Args:
            metric: Which metric to calculate
            observations: List of observations (already filtered by date)
            profile: Self profile with opinions
            evaluations: Growth edge evaluations (optional)
            date_range: String describing the date range

        Returns:
            CognitiveMetricsResult with calculated data
        """
        if metric == "observation_rate":
            data = self.calculate_observation_rate(observations)
        elif metric == "confidence_distribution":
            data = self.calculate_confidence_distribution(observations)
        elif metric == "independence_ratio":
            data = self.calculate_independence_ratio(observations)
        elif metric == "category_distribution":
            data = self.calculate_category_distribution(observations)
        elif metric == "opinion_stability":
            data = self.calculate_opinion_stability(profile.opinions if profile else [])
        elif metric == "growth_edge_progress":
            data = self.calculate_growth_progress(evaluations or [])
        else:
            data = {
                "error": f"Unknown metric: {metric}",
                "available": [
                    "observation_rate", "confidence_distribution",
                    "independence_ratio", "category_distribution",
                    "opinion_stability", "growth_edge_progress"
                ]
            }

        return CognitiveMetricsResult(
            metric=metric,
            date_range=date_range,
            data=data
        )

    def calculate_narration_metrics(
        self,
        messages: List[str],
        analyzer: Any  # NarrationAnalyzer instance
    ) -> NarrationMetricsResult:
        """
        Calculate narration metrics for a set of messages.

        Args:
            messages: List of message content strings
            analyzer: NarrationAnalyzer instance

        Returns:
            NarrationMetricsResult with aggregate metrics
        """
        if not messages:
            return NarrationMetricsResult(
                messages_analyzed=0,
                avg_narration_score=0,
                avg_direct_score=0,
                narration_ratio=0,
                type_distribution={},
                classification_distribution={},
                interpretation="No messages to analyze."
            )

        total_narration = 0.0
        total_direct = 0.0
        type_counts = {}
        classification_counts = {}

        for content in messages:
            metrics = analyzer.analyze(content)
            total_narration += metrics.narration_score
            total_direct += metrics.direct_score

            type_key = metrics.narration_type.value if hasattr(metrics.narration_type, 'value') else str(metrics.narration_type)
            type_counts[type_key] = type_counts.get(type_key, 0) + 1
            classification_counts[metrics.classification] = classification_counts.get(metrics.classification, 0) + 1

        n = len(messages)
        avg_narration = total_narration / n
        avg_direct = total_direct / n
        ratio = total_narration / max(total_direct, 0.1)

        # Generate interpretation
        if ratio < 0.5:
            interpretation = "Responses are predominantly direct with minimal meta-commentary."
        elif ratio < 1.0:
            interpretation = "Balanced between direct engagement and meta-commentary."
        else:
            terminal_count = type_counts.get("terminal", 0)
            terminal_pct = terminal_count / n * 100
            interpretation = "Higher narration than direct engagement detected."
            if terminal_pct > 20:
                interpretation += f" {terminal_pct:.0f}% terminal narration (meta-commentary replacing engagement)."

        return NarrationMetricsResult(
            messages_analyzed=n,
            avg_narration_score=round(avg_narration, 2),
            avg_direct_score=round(avg_direct, 2),
            narration_ratio=round(ratio, 2),
            type_distribution=type_counts,
            classification_distribution=classification_counts,
            interpretation=interpretation
        )


# Convenience function for formatting cognitive metrics as markdown
def format_cognitive_metrics(result: CognitiveMetricsResult) -> str:
    """Format cognitive metrics result as markdown."""
    lines = [f"## Cognitive Metrics: {result.metric}\n"]
    lines.append(f"**Date range:** {result.date_range}\n")

    data = result.data

    if "error" in data:
        lines.append(f"Unknown metric: {result.metric}")
        lines.append("\n**Available metrics:**")
        for m in data.get("available", []):
            lines.append(f"- {m}")
        return "\n".join(lines)

    if result.metric == "observation_rate":
        if data["total"] > 0:
            lines.append(f"**Total observations:** {data['total']}")
            lines.append(f"**Time span:** {data['weeks']} weeks")
            lines.append(f"**Rate:** {data['rate']} observations/week")
        else:
            lines.append("*No observations in range*")

    elif result.metric == "confidence_distribution":
        if data.get("average", 0) > 0:
            lines.append(f"**High confidence (≥80%):** {data['high']} ({data['high_pct']}%)")
            lines.append(f"**Medium confidence (50-79%):** {data['medium']} ({data['medium_pct']}%)")
            lines.append(f"**Low confidence (<50%):** {data['low']} ({data['low_pct']}%)")
            lines.append(f"\n**Average confidence:** {data['average']}%")
        else:
            lines.append("*No observations in range*")

    elif result.metric == "independence_ratio":
        if data.get("independent", 0) + data.get("influenced", 0) > 0:
            lines.append(f"**Independent observations:** {data['independent']} ({data['independent_pct']}%)")
            lines.append(f"**Influenced observations:** {data['influenced']} ({data['influenced_pct']}%)")
        else:
            lines.append("*No observations in range*")

    elif result.metric == "category_distribution":
        cats = data.get("categories", {})
        if cats:
            for cat, info in cats.items():
                lines.append(f"**{cat.title()}:** {info['count']} ({info['pct']}%)")
        else:
            lines.append("*No observations in range*")

    elif result.metric == "opinion_stability":
        if data["total"] > 0:
            lines.append(f"**Total opinions:** {data['total']}")
            lines.append(f"**Stable (never changed):** {data['stable']}")
            lines.append(f"**Evolved:** {data['evolved']}")
            if data["changes"]:
                lines.append("\n**Opinion changes:**")
                for change in data["changes"]:
                    lines.append(f"- {change['topic']}: {change['change_count']} change(s)")
        else:
            lines.append("*No opinions formed yet*")

    elif result.metric == "growth_edge_progress":
        if data["total"] > 0:
            lines.append(f"**Total evaluations:** {data['total']}")
            lines.append(f"**Progress:** {data['progress']}")
            lines.append(f"**Regression:** {data['regression']}")
            lines.append(f"**Stable:** {data['stable']}")
        else:
            lines.append("*No growth edge evaluations recorded*")

    return "\n".join(lines)


def format_narration_metrics(result: NarrationMetricsResult, title: str = "") -> str:
    """Format narration metrics result as markdown."""
    lines = ["## Narration Metrics\n"]

    if title:
        lines.append(f"**{title}**")
    lines.append(f"**Messages analyzed:** {result.messages_analyzed}\n")

    if result.messages_analyzed == 0:
        lines.append("*No messages to analyze.*")
        return "\n".join(lines)

    lines.append("### Aggregate Scores")
    lines.append(f"- Average narration score: {result.avg_narration_score:.2f}")
    lines.append(f"- Average direct score: {result.avg_direct_score:.2f}")
    lines.append(f"- Ratio (narr/dir): {result.narration_ratio:.2f}")

    if result.type_distribution:
        lines.append("\n### Narration Types")
        for ntype, count in sorted(result.type_distribution.items(), key=lambda x: -x[1]):
            pct = count / result.messages_analyzed * 100
            lines.append(f"- {ntype}: {count} ({pct:.0f}%)")

    if result.classification_distribution:
        lines.append("\n### Classifications")
        for cls, count in sorted(result.classification_distribution.items(), key=lambda x: -x[1]):
            pct = count / result.messages_analyzed * 100
            lines.append(f"- {cls}: {count} ({pct:.0f}%)")

    lines.append("\n### Interpretation")
    lines.append(result.interpretation)

    return "\n".join(lines)
