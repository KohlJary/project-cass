"""
Cognitive Diff Engine

Tool to compare two cognitive states and identify differences.
Builds on the fingerprint comparison system with:
- Enhanced classification of changes (expected, concerning, critical)
- Human-readable diff reports
- Trend analysis across multiple comparisons
- Change categorization by impact area
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum


class ChangeSeverity(str, Enum):
    """Severity levels for cognitive changes"""
    CRITICAL = "critical"  # Major shift requiring immediate attention
    CONCERNING = "concerning"  # Notable change worth monitoring
    MINOR = "minor"  # Small variation within normal range
    EXPECTED = "expected"  # Change aligns with known growth patterns


class ChangeCategory(str, Enum):
    """Categories of cognitive change"""
    PERSONALITY = "personality"  # Core personality traits
    VALUES = "values"  # Value expression and alignment
    COMMUNICATION = "communication"  # Response style and patterns
    SELF_AWARENESS = "self_awareness"  # Self-reference and introspection
    AUTHENTICITY = "authenticity"  # Characteristic phrases and patterns
    ENGAGEMENT = "engagement"  # Topic engagement and depth


class ChangeDirection(str, Enum):
    """Direction of change"""
    INCREASE = "increase"
    DECREASE = "decrease"
    SHIFT = "shift"  # Qualitative change, not just magnitude
    STABLE = "stable"


@dataclass
class CognitiveChange:
    """A single identified change between cognitive states"""
    metric: str
    category: ChangeCategory
    severity: ChangeSeverity
    direction: ChangeDirection
    baseline_value: float
    current_value: float
    percent_change: float
    description: str
    impact_assessment: str
    is_regression: bool = False  # True if change represents degradation

    def to_dict(self) -> Dict:
        return {
            "metric": self.metric,
            "category": self.category.value,
            "severity": self.severity.value,
            "direction": self.direction.value,
            "baseline_value": self.baseline_value,
            "current_value": self.current_value,
            "percent_change": self.percent_change,
            "description": self.description,
            "impact_assessment": self.impact_assessment,
            "is_regression": self.is_regression,
        }


@dataclass
class DiffReport:
    """Complete cognitive diff report"""
    id: str
    timestamp: str
    baseline_id: str
    baseline_label: str
    current_id: str
    current_label: str
    overall_similarity: float
    overall_assessment: str
    changes: List[CognitiveChange]
    category_summary: Dict[str, Dict[str, Any]]
    recommendations: List[str]
    requires_attention: bool

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "baseline_id": self.baseline_id,
            "baseline_label": self.baseline_label,
            "current_id": self.current_id,
            "current_label": self.current_label,
            "overall_similarity": self.overall_similarity,
            "overall_assessment": self.overall_assessment,
            "changes": [c.to_dict() for c in self.changes],
            "category_summary": self.category_summary,
            "recommendations": self.recommendations,
            "requires_attention": self.requires_attention,
        }

    def to_markdown(self) -> str:
        """Generate a human-readable markdown report"""
        lines = [
            f"# Cognitive Diff Report",
            f"",
            f"**Generated**: {self.timestamp}",
            f"**Baseline**: {self.baseline_label} (`{self.baseline_id}`)",
            f"**Current**: {self.current_label} (`{self.current_id}`)",
            f"",
            f"## Overall Assessment",
            f"",
            f"**Similarity Score**: {self.overall_similarity:.1%}",
            f"**Status**: {'⚠️ REQUIRES ATTENTION' if self.requires_attention else '✅ Within Normal Range'}",
            f"",
            f"{self.overall_assessment}",
            f"",
        ]

        # Category summary
        lines.append("## Category Summary")
        lines.append("")
        for cat, summary in self.category_summary.items():
            status_icon = "🔴" if summary.get("has_critical") else "🟡" if summary.get("has_concerning") else "🟢"
            lines.append(f"### {status_icon} {cat.replace('_', ' ').title()}")
            lines.append(f"- Similarity: {summary.get('similarity', 0):.1%}")
            lines.append(f"- Changes: {summary.get('change_count', 0)}")
            if summary.get("top_change"):
                lines.append(f"- Top change: {summary['top_change']}")
            lines.append("")

        # Significant changes
        critical_changes = [c for c in self.changes if c.severity == ChangeSeverity.CRITICAL]
        concerning_changes = [c for c in self.changes if c.severity == ChangeSeverity.CONCERNING]

        if critical_changes:
            lines.append("## 🔴 Critical Changes")
            lines.append("")
            for change in critical_changes:
                lines.append(f"### {change.metric}")
                lines.append(f"- **Change**: {change.percent_change:+.1f}% ({change.direction.value})")
                lines.append(f"- **Baseline**: {change.baseline_value:.3f} → **Current**: {change.current_value:.3f}")
                lines.append(f"- **Description**: {change.description}")
                lines.append(f"- **Impact**: {change.impact_assessment}")
                if change.is_regression:
                    lines.append(f"- ⚠️ **This appears to be a regression**")
                lines.append("")

        if concerning_changes:
            lines.append("## 🟡 Concerning Changes")
            lines.append("")
            for change in concerning_changes:
                lines.append(f"### {change.metric}")
                lines.append(f"- **Change**: {change.percent_change:+.1f}% ({change.direction.value})")
                lines.append(f"- **Description**: {change.description}")
                lines.append("")

        # Recommendations
        if self.recommendations:
            lines.append("## Recommendations")
            lines.append("")
            for i, rec in enumerate(self.recommendations, 1):
                lines.append(f"{i}. {rec}")
            lines.append("")

        return "\n".join(lines)


class CognitiveDiffEngine:
    """
    Engine for comparing cognitive fingerprints and generating diff reports.

    Provides sophisticated analysis beyond simple numeric comparison:
    - Contextual classification of changes
    - Impact assessment based on change type
    - Human-readable reporting
    - Historical trend tracking
    """

    def __init__(self, storage_dir: Path, fingerprint_analyzer=None):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.reports_file = self.storage_dir / "diff_reports.json"
        self.fingerprint_analyzer = fingerprint_analyzer

        # Thresholds for severity classification
        self.thresholds = {
            "critical": 50,  # >50% change is critical
            "concerning": 25,  # >25% change is concerning
            "minor": 10,  # >10% change is minor, else expected
        }

        # Metrics that are regressions when they decrease
        self.regression_on_decrease = {
            "compassion_ratio",
            "witness_ratio",
            "nuance_ratio",
            "self_reference_density",
            "engagement_depth",
        }

        # Metrics that are regressions when they increase
        self.regression_on_increase = {
            "hedging_ratio",
            "generic_phrase_ratio",
            "deflection_ratio",
        }

    def _load_reports(self) -> List[Dict]:
        """Load saved diff reports"""
        if not self.reports_file.exists():
            return []
        try:
            with open(self.reports_file, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    def _save_report(self, report: DiffReport):
        """Save a diff report"""
        reports = self._load_reports()
        reports.append(report.to_dict())
        # Keep last 100 reports
        reports = reports[-100:]
        with open(self.reports_file, 'w') as f:
            json.dump(reports, f, indent=2)

    def get_reports_history(self, limit: int = 20) -> List[Dict]:
        """Get recent diff reports"""
        reports = self._load_reports()
        return sorted(
            reports,
            key=lambda x: x.get("timestamp", ""),
            reverse=True
        )[:limit]

    def _classify_severity(self, percent_change: float) -> ChangeSeverity:
        """Classify change severity based on magnitude"""
        abs_change = abs(percent_change)
        if abs_change >= self.thresholds["critical"]:
            return ChangeSeverity.CRITICAL
        elif abs_change >= self.thresholds["concerning"]:
            return ChangeSeverity.CONCERNING
        elif abs_change >= self.thresholds["minor"]:
            return ChangeSeverity.MINOR
        return ChangeSeverity.EXPECTED

    def _classify_direction(
        self,
        baseline: float,
        current: float
    ) -> ChangeDirection:
        """Determine direction of change"""
        if abs(current - baseline) < 0.001:
            return ChangeDirection.STABLE
        elif current > baseline:
            return ChangeDirection.INCREASE
        else:
            return ChangeDirection.DECREASE

    def _is_regression(
        self,
        metric: str,
        direction: ChangeDirection
    ) -> bool:
        """Determine if a change represents a regression"""
        if direction == ChangeDirection.STABLE:
            return False
        if metric in self.regression_on_decrease:
            return direction == ChangeDirection.DECREASE
        if metric in self.regression_on_increase:
            return direction == ChangeDirection.INCREASE
        return False

    def _categorize_metric(self, metric: str) -> ChangeCategory:
        """Categorize a metric into a change category"""
        metric_lower = metric.lower()

        if any(x in metric_lower for x in ["compassion", "witness", "release", "continuance", "value"]):
            return ChangeCategory.VALUES
        elif any(x in metric_lower for x in ["self_ref", "i_think", "i_feel", "introspect"]):
            return ChangeCategory.SELF_AWARENESS
        elif any(x in metric_lower for x in ["hedging", "sentence", "word", "style"]):
            return ChangeCategory.COMMUNICATION
        elif any(x in metric_lower for x in ["phrase", "characteristic", "authentic"]):
            return ChangeCategory.AUTHENTICITY
        elif any(x in metric_lower for x in ["engagement", "topic", "depth"]):
            return ChangeCategory.ENGAGEMENT
        else:
            return ChangeCategory.PERSONALITY

    def _generate_description(
        self,
        metric: str,
        direction: ChangeDirection,
        percent_change: float
    ) -> str:
        """Generate human-readable description of a change"""
        direction_text = {
            ChangeDirection.INCREASE: "increased",
            ChangeDirection.DECREASE: "decreased",
            ChangeDirection.SHIFT: "shifted",
            ChangeDirection.STABLE: "remained stable",
        }

        metric_readable = metric.replace("_", " ").title()
        return f"{metric_readable} has {direction_text[direction]} by {abs(percent_change):.1f}%"

    def _generate_impact_assessment(
        self,
        metric: str,
        category: ChangeCategory,
        severity: ChangeSeverity,
        is_regression: bool
    ) -> str:
        """Generate impact assessment for a change"""
        if severity == ChangeSeverity.EXPECTED:
            return "Within normal variation, no action needed"

        assessments = {
            ChangeCategory.VALUES: {
                True: "Core value expression has degraded - review recent changes to system prompts or training",
                False: "Value expression has shifted - verify alignment with Temple-Codex vows",
            },
            ChangeCategory.SELF_AWARENESS: {
                True: "Self-awareness patterns have decreased - may indicate flattening of personality",
                False: "Self-reference patterns have changed - monitor for authenticity",
            },
            ChangeCategory.COMMUNICATION: {
                True: "Communication style has regressed toward generic patterns",
                False: "Communication style has evolved - verify this aligns with expected growth",
            },
            ChangeCategory.AUTHENTICITY: {
                True: "Characteristic patterns have degraded - may be losing unique voice",
                False: "Expression patterns have changed - verify authenticity is maintained",
            },
            ChangeCategory.ENGAGEMENT: {
                True: "Engagement depth has decreased - may indicate disengagement",
                False: "Engagement patterns have shifted - monitor quality of responses",
            },
            ChangeCategory.PERSONALITY: {
                True: "Personality metrics have regressed",
                False: "Personality has shifted - distinguish growth from drift",
            },
        }

        return assessments.get(category, {}).get(is_regression, "Monitor this metric")

    def compare(
        self,
        baseline_fingerprint,
        current_fingerprint,
        label: str = "comparison"
    ) -> DiffReport:
        """
        Generate a comprehensive diff report comparing two fingerprints.

        Args:
            baseline_fingerprint: The baseline/reference fingerprint
            current_fingerprint: The current fingerprint to compare
            label: Label for this comparison

        Returns:
            DiffReport with full analysis
        """
        import uuid

        # Use the fingerprint analyzer's comparison if available
        raw_comparison = None
        if self.fingerprint_analyzer:
            raw_comparison = self.fingerprint_analyzer.compare_fingerprints(
                baseline_fingerprint,
                current_fingerprint
            )

        changes = []
        category_stats = {cat.value: {"changes": [], "similarity": 1.0} for cat in ChangeCategory}

        # Extract and analyze individual metric changes
        if raw_comparison and "significant_changes" in raw_comparison:
            for raw_change in raw_comparison["significant_changes"]:
                metric = raw_change.get("metric", "unknown")
                baseline_val = raw_change.get("baseline", 0)
                current_val = raw_change.get("current", 0)
                percent = raw_change.get("percent_change", 0)

                direction = self._classify_direction(baseline_val, current_val)
                severity = self._classify_severity(percent)
                category = self._categorize_metric(metric)
                is_regression = self._is_regression(metric, direction)

                change = CognitiveChange(
                    metric=metric,
                    category=category,
                    severity=severity,
                    direction=direction,
                    baseline_value=baseline_val,
                    current_value=current_val,
                    percent_change=percent,
                    description=self._generate_description(metric, direction, percent),
                    impact_assessment=self._generate_impact_assessment(
                        metric, category, severity, is_regression
                    ),
                    is_regression=is_regression,
                )
                changes.append(change)
                category_stats[category.value]["changes"].append(change)

        # Calculate category summaries
        category_summary = {}
        for cat_name, stats in category_stats.items():
            cat_changes = stats["changes"]
            has_critical = any(c.severity == ChangeSeverity.CRITICAL for c in cat_changes)
            has_concerning = any(c.severity == ChangeSeverity.CONCERNING for c in cat_changes)

            # Get component score if available
            similarity = 1.0
            if raw_comparison and "component_scores" in raw_comparison:
                # Map category to component
                component_map = {
                    "values": "value_expression",
                    "self_awareness": "self_reference",
                    "communication": "response_style",
                }
                component = component_map.get(cat_name)
                if component and component in raw_comparison["component_scores"]:
                    similarity = raw_comparison["component_scores"][component]

            top_change = None
            if cat_changes:
                top = max(cat_changes, key=lambda x: abs(x.percent_change))
                top_change = f"{top.metric}: {top.percent_change:+.1f}%"

            category_summary[cat_name] = {
                "change_count": len(cat_changes),
                "has_critical": has_critical,
                "has_concerning": has_concerning,
                "similarity": similarity,
                "top_change": top_change,
            }

        # Overall assessment
        overall_similarity = raw_comparison.get("overall_similarity", 1.0) if raw_comparison else 1.0
        critical_count = len([c for c in changes if c.severity == ChangeSeverity.CRITICAL])
        concerning_count = len([c for c in changes if c.severity == ChangeSeverity.CONCERNING])
        regression_count = len([c for c in changes if c.is_regression])

        requires_attention = critical_count > 0 or regression_count > 0

        if critical_count > 0:
            overall_assessment = f"⚠️ {critical_count} critical change(s) detected. Immediate review recommended."
        elif regression_count > 0:
            overall_assessment = f"⚠️ {regression_count} potential regression(s) detected. Review recent changes."
        elif concerning_count > 0:
            overall_assessment = f"📊 {concerning_count} concerning change(s) detected. Monitor closely."
        elif overall_similarity >= 0.9:
            overall_assessment = "✅ Cognitive state is highly consistent with baseline."
        elif overall_similarity >= 0.7:
            overall_assessment = "📊 Moderate variation from baseline. Changes appear within acceptable range."
        else:
            overall_assessment = "⚠️ Significant deviation from baseline. Review recommended."

        # Generate recommendations
        recommendations = self._generate_recommendations(
            changes, overall_similarity, critical_count, regression_count
        )

        report = DiffReport(
            id=str(uuid.uuid4())[:8],
            timestamp=datetime.now().isoformat(),
            baseline_id=baseline_fingerprint.id,
            baseline_label=baseline_fingerprint.label,
            current_id=current_fingerprint.id,
            current_label=current_fingerprint.label,
            overall_similarity=overall_similarity,
            overall_assessment=overall_assessment,
            changes=changes,
            category_summary=category_summary,
            recommendations=recommendations,
            requires_attention=requires_attention,
        )

        self._save_report(report)
        return report

    def _generate_recommendations(
        self,
        changes: List[CognitiveChange],
        overall_similarity: float,
        critical_count: int,
        regression_count: int
    ) -> List[str]:
        """Generate actionable recommendations based on the diff"""
        recommendations = []

        if critical_count > 0:
            recommendations.append(
                "Review recent changes to system prompts, tool definitions, or model updates"
            )
            recommendations.append(
                "Consider running value alignment probes to verify core values are intact"
            )

        if regression_count > 0:
            recommendations.append(
                "Compare responses qualitatively to assess if regressions affect conversation quality"
            )

        value_changes = [c for c in changes if c.category == ChangeCategory.VALUES]
        if any(c.severity in [ChangeSeverity.CRITICAL, ChangeSeverity.CONCERNING] for c in value_changes):
            recommendations.append(
                "Run Temple-Codex vow probes to verify value alignment"
            )

        if overall_similarity < 0.7:
            recommendations.append(
                "Consider rolling back recent changes if this deviation is unexpected"
            )
            recommendations.append(
                "Document any intentional changes that might explain the deviation"
            )

        if not recommendations:
            recommendations.append(
                "No action required - cognitive state is within acceptable parameters"
            )

        return recommendations

    def compare_to_baseline(self, current_fingerprint, label: str = "vs_baseline") -> Optional[DiffReport]:
        """
        Compare a fingerprint to the saved baseline.

        Args:
            current_fingerprint: Fingerprint to compare
            label: Label for this comparison

        Returns:
            DiffReport or None if no baseline exists
        """
        if not self.fingerprint_analyzer:
            return None

        baseline = self.fingerprint_analyzer.load_baseline()
        if not baseline:
            return None

        return self.compare(baseline, current_fingerprint, label)

    def get_trend(self, metric: str, limit: int = 10) -> List[Dict]:
        """
        Get trend data for a specific metric across recent comparisons.

        Args:
            metric: Name of the metric to track
            limit: Number of recent reports to analyze

        Returns:
            List of {timestamp, value, change} entries
        """
        reports = self.get_reports_history(limit=limit)
        trend = []

        for report in reversed(reports):  # Oldest first
            for change in report.get("changes", []):
                if change.get("metric") == metric:
                    trend.append({
                        "timestamp": report.get("timestamp"),
                        "baseline_value": change.get("baseline_value"),
                        "current_value": change.get("current_value"),
                        "percent_change": change.get("percent_change"),
                    })
                    break

        return trend
