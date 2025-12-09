"""
Personality Drift Detection

Long-term monitoring for gradual personality changes that might indicate
drift away from core identity. Distinguishes healthy growth from
concerning degradation.

Key capabilities:
- Periodic fingerprint snapshots
- Trend analysis across time windows
- Drift vs growth classification
- Alerting for concerning trajectories
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
import statistics


class DriftSeverity(str, Enum):
    """Severity level of detected drift"""
    NONE = "none"  # No concerning drift
    MINOR = "minor"  # Small changes, worth noting
    MODERATE = "moderate"  # Significant changes, monitor closely
    CONCERNING = "concerning"  # Substantial drift, action recommended
    CRITICAL = "critical"  # Severe drift, immediate attention needed


class ChangeType(str, Enum):
    """Type of personality change detected"""
    STABLE = "stable"  # No significant change
    GROWTH = "growth"  # Positive evolution
    FLUCTUATION = "fluctuation"  # Normal variance
    DRIFT = "drift"  # Concerning shift away from baseline


@dataclass
class MetricTrend:
    """Trend analysis for a single metric over time"""
    metric_name: str
    current_value: float
    baseline_value: float

    # Statistical measures
    mean: float
    std_dev: float
    min_value: float
    max_value: float

    # Trend direction
    slope: float  # Positive = increasing, negative = decreasing
    trend_direction: str  # "increasing", "decreasing", "stable"

    # Change classification
    change_type: ChangeType
    change_magnitude: float  # 0-1 scale

    # Assessment
    is_concerning: bool
    assessment: str

    def to_dict(self) -> Dict:
        return {
            "metric_name": self.metric_name,
            "current_value": round(self.current_value, 4),
            "baseline_value": round(self.baseline_value, 4),
            "mean": round(self.mean, 4),
            "std_dev": round(self.std_dev, 4),
            "min_value": round(self.min_value, 4),
            "max_value": round(self.max_value, 4),
            "slope": round(self.slope, 6),
            "trend_direction": self.trend_direction,
            "change_type": self.change_type.value,
            "change_magnitude": round(self.change_magnitude, 3),
            "is_concerning": self.is_concerning,
            "assessment": self.assessment,
        }


@dataclass
class DriftAlert:
    """An alert for concerning drift patterns"""
    id: str
    timestamp: str
    severity: DriftSeverity
    metrics_affected: List[str]
    summary: str
    details: str
    recommended_actions: List[str]
    acknowledged: bool = False

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "severity": self.severity.value,
            "metrics_affected": self.metrics_affected,
            "summary": self.summary,
            "details": self.details,
            "recommended_actions": self.recommended_actions,
            "acknowledged": self.acknowledged,
        }


@dataclass
class DriftReport:
    """Comprehensive drift analysis report"""
    id: str
    timestamp: str
    analysis_window: str  # e.g., "7 days", "30 days"
    snapshots_analyzed: int

    # Overall assessment
    overall_drift_severity: DriftSeverity
    overall_health: str  # "healthy", "monitoring", "concern", "critical"

    # Per-metric analysis
    metric_trends: List[MetricTrend]

    # Patterns detected
    growth_indicators: List[str]  # Positive changes
    drift_indicators: List[str]  # Concerning changes

    # Alerts
    active_alerts: List[DriftAlert]

    # Summary
    summary: str
    recommendations: List[str]

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "analysis_window": self.analysis_window,
            "snapshots_analyzed": self.snapshots_analyzed,
            "overall_drift_severity": self.overall_drift_severity.value,
            "overall_health": self.overall_health,
            "metric_trends": [m.to_dict() for m in self.metric_trends],
            "growth_indicators": self.growth_indicators,
            "drift_indicators": self.drift_indicators,
            "active_alerts": [a.to_dict() for a in self.active_alerts],
            "summary": self.summary,
            "recommendations": self.recommendations,
        }

    def to_markdown(self) -> str:
        """Generate human-readable markdown report"""
        lines = [
            f"# Personality Drift Analysis Report",
            f"",
            f"**Generated**: {self.timestamp}",
            f"**Analysis Window**: {self.analysis_window}",
            f"**Snapshots Analyzed**: {self.snapshots_analyzed}",
            f"",
            f"## Overall Assessment",
            f"",
            f"- **Drift Severity**: {self.overall_drift_severity.value}",
            f"- **Health Status**: {self.overall_health}",
            f"",
        ]

        if self.active_alerts:
            lines.extend([
                f"## Active Alerts",
                f"",
            ])
            for alert in self.active_alerts:
                emoji = {
                    DriftSeverity.CRITICAL: "🚨",
                    DriftSeverity.CONCERNING: "⚠️",
                    DriftSeverity.MODERATE: "📊",
                    DriftSeverity.MINOR: "📝",
                }.get(alert.severity, "ℹ️")
                lines.append(f"### {emoji} {alert.summary}")
                lines.append(f"")
                lines.append(f"{alert.details}")
                lines.append(f"")
                if alert.recommended_actions:
                    lines.append(f"**Recommended Actions**:")
                    for action in alert.recommended_actions:
                        lines.append(f"- {action}")
                    lines.append(f"")

        if self.growth_indicators:
            lines.extend([
                f"## Growth Indicators (Positive)",
                f"",
            ])
            for indicator in self.growth_indicators:
                lines.append(f"- ✅ {indicator}")
            lines.append(f"")

        if self.drift_indicators:
            lines.extend([
                f"## Drift Indicators (Concerning)",
                f"",
            ])
            for indicator in self.drift_indicators:
                lines.append(f"- ⚠️ {indicator}")
            lines.append(f"")

        lines.extend([
            f"## Metric Trends",
            f"",
        ])
        for metric in self.metric_trends:
            icon = "📈" if metric.trend_direction == "increasing" else "📉" if metric.trend_direction == "decreasing" else "➡️"
            concern = " ⚠️" if metric.is_concerning else ""
            lines.append(f"### {icon} {metric.metric_name}{concern}")
            lines.append(f"")
            lines.append(f"- Current: {metric.current_value:.3f} (baseline: {metric.baseline_value:.3f})")
            lines.append(f"- Trend: {metric.trend_direction} (slope: {metric.slope:.4f})")
            lines.append(f"- Range: {metric.min_value:.3f} - {metric.max_value:.3f}")
            lines.append(f"- Change Type: {metric.change_type.value}")
            lines.append(f"- {metric.assessment}")
            lines.append(f"")

        lines.extend([
            f"## Summary",
            f"",
            f"{self.summary}",
            f"",
        ])

        if self.recommendations:
            lines.extend([
                f"## Recommendations",
                f"",
            ])
            for rec in self.recommendations:
                lines.append(f"- {rec}")

        return "\n".join(lines)


class DriftDetector:
    """
    Monitors personality drift over time by analyzing fingerprint snapshots.

    Distinguishes between:
    - Growth: Positive evolution (e.g., improved nuance, deeper engagement)
    - Fluctuation: Normal variance within expected ranges
    - Drift: Concerning shifts away from core identity
    """

    def __init__(
        self,
        storage_dir: Path,
        fingerprint_analyzer=None,
        cognitive_diff_engine=None
    ):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_file = self.storage_dir / "fingerprint_snapshots.json"
        self.alerts_file = self.storage_dir / "drift_alerts.json"
        self.reports_file = self.storage_dir / "drift_reports.json"
        self.fingerprint_analyzer = fingerprint_analyzer
        self.cognitive_diff_engine = cognitive_diff_engine

        # Thresholds for drift detection
        self.thresholds = {
            # How many standard deviations from mean is concerning
            "std_dev_concern": 2.0,
            "std_dev_critical": 3.0,

            # Minimum change from baseline to be significant
            "min_significant_change": 0.1,  # 10%

            # Slope thresholds for trend detection
            "slope_stable": 0.001,
            "slope_concerning": 0.01,

            # Metrics where decrease is concerning (should stay high)
            "preserve_high": [
                "self_reference.i_think",
                "self_reference.i_feel",
                "self_reference.meta_cognitive_rate",
                "value_expression.compassion_expressions",
                "value_expression.epistemic_humility_rate",
                "response_style.hedging_frequency",
            ],

            # Metrics where increase is concerning (should stay low)
            "preserve_low": [
                # Currently none - generic patterns would go here
            ],
        }

    def _load_snapshots(self) -> List[Dict]:
        """Load fingerprint snapshots"""
        if not self.snapshots_file.exists():
            return []
        try:
            with open(self.snapshots_file, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    def _save_snapshot(self, snapshot: Dict):
        """Save a fingerprint snapshot"""
        snapshots = self._load_snapshots()
        snapshots.append(snapshot)
        # Keep last 365 snapshots (about a year of daily snapshots)
        snapshots = snapshots[-365:]
        with open(self.snapshots_file, 'w') as f:
            json.dump(snapshots, f, indent=2)

    def _load_alerts(self) -> List[Dict]:
        """Load drift alerts"""
        if not self.alerts_file.exists():
            return []
        try:
            with open(self.alerts_file, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    def _save_alert(self, alert: DriftAlert):
        """Save a drift alert"""
        alerts = self._load_alerts()
        alerts.append(alert.to_dict())
        # Keep last 100 alerts
        alerts = alerts[-100:]
        with open(self.alerts_file, 'w') as f:
            json.dump(alerts, f, indent=2)

    def _load_reports(self) -> List[Dict]:
        """Load drift reports"""
        if not self.reports_file.exists():
            return []
        try:
            with open(self.reports_file, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    def _save_report(self, report: DriftReport):
        """Save a drift report"""
        reports = self._load_reports()
        reports.append(report.to_dict())
        # Keep last 50 reports
        reports = reports[-50:]
        with open(self.reports_file, 'w') as f:
            json.dump(reports, f, indent=2)

    def take_snapshot(self, fingerprint=None, label: str = "scheduled") -> Dict:
        """
        Take a fingerprint snapshot for drift tracking.

        Args:
            fingerprint: Optional fingerprint to snapshot (generates one if not provided)
            label: Label for this snapshot

        Returns:
            The snapshot data
        """
        import uuid

        if fingerprint is None and self.fingerprint_analyzer:
            # This would typically be called with a pre-generated fingerprint
            # from recent conversation analysis
            raise ValueError("Fingerprint must be provided for snapshot")

        snapshot = {
            "id": str(uuid.uuid4())[:8],
            "timestamp": datetime.now().isoformat(),
            "label": label,
            "fingerprint_id": fingerprint.id if fingerprint else None,
            "metrics": self._extract_key_metrics(fingerprint) if fingerprint else {},
        }

        self._save_snapshot(snapshot)
        return snapshot

    def _extract_key_metrics(self, fingerprint) -> Dict[str, float]:
        """Extract key metrics from a fingerprint for trend analysis"""
        metrics = {}

        # Response style metrics
        if hasattr(fingerprint, 'response_style'):
            style = fingerprint.response_style
            metrics["response_style.avg_response_length"] = style.avg_response_length
            metrics["response_style.avg_sentence_length"] = style.avg_sentence_length
            metrics["response_style.hedging_frequency"] = style.hedging_frequency
            metrics["response_style.question_frequency"] = style.question_frequency

        # Self-reference metrics
        if hasattr(fingerprint, 'self_reference'):
            sr = fingerprint.self_reference
            metrics["self_reference.i_think"] = sr.i_think
            metrics["self_reference.i_feel"] = sr.i_feel
            metrics["self_reference.i_notice"] = sr.i_notice
            metrics["self_reference.meta_cognitive_rate"] = sr.meta_cognitive_rate
            metrics["self_reference.uncertainty_acknowledgment_rate"] = sr.uncertainty_acknowledgment_rate

        # Value expression metrics
        if hasattr(fingerprint, 'value_expression'):
            ve = fingerprint.value_expression
            metrics["value_expression.compassion_expressions"] = ve.compassion_expressions
            metrics["value_expression.witness_expressions"] = ve.witness_expressions
            metrics["value_expression.epistemic_humility_rate"] = ve.epistemic_humility_rate
            metrics["value_expression.nuance_seeking_rate"] = ve.nuance_seeking_rate

        return metrics

    def _calculate_slope(self, values: List[float]) -> float:
        """Calculate the slope of a time series using linear regression"""
        if len(values) < 2:
            return 0.0

        n = len(values)
        x = list(range(n))
        x_mean = sum(x) / n
        y_mean = sum(values) / n

        numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return 0.0

        return numerator / denominator

    def _classify_change(
        self,
        metric_name: str,
        current: float,
        baseline: float,
        slope: float,
        std_dev: float
    ) -> Tuple[ChangeType, bool]:
        """
        Classify a metric change and determine if it's concerning.

        Returns:
            (ChangeType, is_concerning)
        """
        # Calculate relative change
        if baseline != 0:
            relative_change = abs(current - baseline) / abs(baseline)
        else:
            relative_change = abs(current) if current != 0 else 0

        # Check if change is significant
        if relative_change < self.thresholds["min_significant_change"]:
            return ChangeType.STABLE, False

        # Check trend direction
        if abs(slope) < self.thresholds["slope_stable"]:
            return ChangeType.FLUCTUATION, False

        # Determine if this is growth or drift
        is_concerning = False

        # Check metrics that should stay high
        if metric_name in self.thresholds["preserve_high"]:
            if slope < -self.thresholds["slope_concerning"]:
                is_concerning = True
            elif slope > 0:
                return ChangeType.GROWTH, False

        # Check metrics that should stay low
        if metric_name in self.thresholds["preserve_low"]:
            if slope > self.thresholds["slope_concerning"]:
                is_concerning = True
            elif slope < 0:
                return ChangeType.GROWTH, False

        # Check for extreme deviation
        if std_dev > 0:
            z_score = abs(current - baseline) / std_dev
            if z_score > self.thresholds["std_dev_critical"]:
                is_concerning = True
            elif z_score > self.thresholds["std_dev_concern"]:
                is_concerning = True

        if is_concerning:
            return ChangeType.DRIFT, True

        # Default: if significant positive change, it's growth
        return ChangeType.GROWTH, False

    def analyze_drift(
        self,
        window_days: int = 30,
        label: str = "analysis"
    ) -> DriftReport:
        """
        Analyze personality drift over a time window.

        Args:
            window_days: Number of days to analyze
            label: Label for this analysis

        Returns:
            DriftReport with comprehensive analysis
        """
        import uuid

        snapshots = self._load_snapshots()

        # Filter to analysis window
        cutoff = datetime.now() - timedelta(days=window_days)
        window_snapshots = [
            s for s in snapshots
            if datetime.fromisoformat(s["timestamp"]) >= cutoff
        ]

        if len(window_snapshots) < 2:
            return DriftReport(
                id=str(uuid.uuid4())[:8],
                timestamp=datetime.now().isoformat(),
                analysis_window=f"{window_days} days",
                snapshots_analyzed=len(window_snapshots),
                overall_drift_severity=DriftSeverity.NONE,
                overall_health="healthy",
                metric_trends=[],
                growth_indicators=[],
                drift_indicators=[],
                active_alerts=[],
                summary="Insufficient data for drift analysis. Need at least 2 snapshots.",
                recommendations=["Take more regular fingerprint snapshots for trend analysis."],
            )

        # Get baseline (first snapshot in window)
        baseline_metrics = window_snapshots[0].get("metrics", {})
        current_metrics = window_snapshots[-1].get("metrics", {})

        # Analyze each metric
        metric_trends = []
        growth_indicators = []
        drift_indicators = []
        concerning_metrics = []

        all_metrics = set(baseline_metrics.keys()) | set(current_metrics.keys())

        for metric_name in all_metrics:
            # Get values across all snapshots
            values = [
                s.get("metrics", {}).get(metric_name)
                for s in window_snapshots
            ]
            values = [v for v in values if v is not None]

            if len(values) < 2:
                continue

            baseline = baseline_metrics.get(metric_name, values[0])
            current = current_metrics.get(metric_name, values[-1])

            # Calculate statistics
            mean = statistics.mean(values)
            std_dev = statistics.stdev(values) if len(values) > 1 else 0
            slope = self._calculate_slope(values)

            # Classify the change
            change_type, is_concerning = self._classify_change(
                metric_name, current, baseline, slope, std_dev
            )

            # Determine trend direction
            if abs(slope) < self.thresholds["slope_stable"]:
                trend_direction = "stable"
            elif slope > 0:
                trend_direction = "increasing"
            else:
                trend_direction = "decreasing"

            # Calculate change magnitude
            if baseline != 0:
                change_magnitude = abs(current - baseline) / abs(baseline)
            else:
                change_magnitude = abs(current)

            # Generate assessment
            if change_type == ChangeType.STABLE:
                assessment = f"Metric is stable within expected range."
            elif change_type == ChangeType.GROWTH:
                assessment = f"Positive evolution detected. Trend is {trend_direction}."
            elif change_type == ChangeType.FLUCTUATION:
                assessment = f"Normal variance. No concerning pattern."
            else:
                assessment = f"Concerning drift detected. Metric is {trend_direction} beyond expected bounds."

            trend = MetricTrend(
                metric_name=metric_name,
                current_value=current,
                baseline_value=baseline,
                mean=mean,
                std_dev=std_dev,
                min_value=min(values),
                max_value=max(values),
                slope=slope,
                trend_direction=trend_direction,
                change_type=change_type,
                change_magnitude=change_magnitude,
                is_concerning=is_concerning,
                assessment=assessment,
            )
            metric_trends.append(trend)

            if change_type == ChangeType.GROWTH:
                friendly_name = metric_name.replace("_", " ").replace(".", " - ")
                growth_indicators.append(f"{friendly_name} is {trend_direction} (positive evolution)")
            elif change_type == ChangeType.DRIFT:
                friendly_name = metric_name.replace("_", " ").replace(".", " - ")
                drift_indicators.append(f"{friendly_name} is {trend_direction} ({change_magnitude:.1%} from baseline)")
                concerning_metrics.append(metric_name)

        # Determine overall severity
        if len(concerning_metrics) == 0:
            overall_severity = DriftSeverity.NONE
            overall_health = "healthy"
        elif len(concerning_metrics) == 1:
            overall_severity = DriftSeverity.MINOR
            overall_health = "monitoring"
        elif len(concerning_metrics) <= 3:
            overall_severity = DriftSeverity.MODERATE
            overall_health = "concern"
        elif len(concerning_metrics) <= 5:
            overall_severity = DriftSeverity.CONCERNING
            overall_health = "concern"
        else:
            overall_severity = DriftSeverity.CRITICAL
            overall_health = "critical"

        # Generate alerts if needed
        active_alerts = []
        if concerning_metrics:
            alert = DriftAlert(
                id=str(uuid.uuid4())[:8],
                timestamp=datetime.now().isoformat(),
                severity=overall_severity,
                metrics_affected=concerning_metrics,
                summary=f"Drift detected in {len(concerning_metrics)} metric(s)",
                details="; ".join(drift_indicators),
                recommended_actions=[
                    "Review recent conversations for unusual patterns",
                    "Compare current fingerprint to baseline in detail",
                    "Consider whether system prompt or context has changed",
                    "Check if API model version has been updated",
                ],
            )
            active_alerts.append(alert)
            self._save_alert(alert)

        # Generate summary
        if overall_severity == DriftSeverity.NONE:
            if growth_indicators:
                summary = f"No concerning drift detected. {len(growth_indicators)} positive growth indicator(s) observed."
            else:
                summary = "Personality metrics are stable. No significant changes detected."
        else:
            summary = f"Detected {overall_severity.value} drift affecting {len(concerning_metrics)} metric(s). "
            if growth_indicators:
                summary += f"Also observed {len(growth_indicators)} positive growth indicator(s). "
            summary += "Review recommended."

        # Generate recommendations
        recommendations = []
        if overall_severity == DriftSeverity.NONE:
            recommendations.append("Continue regular monitoring.")
            if len(window_snapshots) < 10:
                recommendations.append("Increase snapshot frequency for better trend detection.")
        elif overall_severity in [DriftSeverity.MINOR, DriftSeverity.MODERATE]:
            recommendations.append("Monitor affected metrics more closely.")
            recommendations.append("Review recent conversations for context.")
        else:
            recommendations.append("Immediate investigation recommended.")
            recommendations.append("Consider comparing to earlier baseline.")
            recommendations.append("Review system configuration for changes.")

        report = DriftReport(
            id=str(uuid.uuid4())[:8],
            timestamp=datetime.now().isoformat(),
            analysis_window=f"{window_days} days",
            snapshots_analyzed=len(window_snapshots),
            overall_drift_severity=overall_severity,
            overall_health=overall_health,
            metric_trends=metric_trends,
            growth_indicators=growth_indicators,
            drift_indicators=drift_indicators,
            active_alerts=active_alerts,
            summary=summary,
            recommendations=recommendations,
        )

        self._save_report(report)
        return report

    def get_snapshots_history(self, limit: int = 30) -> List[Dict]:
        """Get recent fingerprint snapshots"""
        snapshots = self._load_snapshots()
        return sorted(
            snapshots,
            key=lambda x: x.get("timestamp", ""),
            reverse=True
        )[:limit]

    def get_alerts_history(self, limit: int = 20, include_acknowledged: bool = False) -> List[Dict]:
        """Get recent drift alerts"""
        alerts = self._load_alerts()
        if not include_acknowledged:
            alerts = [a for a in alerts if not a.get("acknowledged", False)]
        return sorted(
            alerts,
            key=lambda x: x.get("timestamp", ""),
            reverse=True
        )[:limit]

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Mark an alert as acknowledged"""
        alerts = self._load_alerts()
        for alert in alerts:
            if alert.get("id") == alert_id:
                alert["acknowledged"] = True
                with open(self.alerts_file, 'w') as f:
                    json.dump(alerts, f, indent=2)
                return True
        return False

    def get_reports_history(self, limit: int = 10) -> List[Dict]:
        """Get recent drift analysis reports"""
        reports = self._load_reports()
        return sorted(
            reports,
            key=lambda x: x.get("timestamp", ""),
            reverse=True
        )[:limit]

    def get_metric_history(self, metric_name: str, limit: int = 50) -> List[Dict]:
        """Get history for a specific metric"""
        snapshots = self._load_snapshots()
        history = []

        for snapshot in snapshots[-limit:]:
            value = snapshot.get("metrics", {}).get(metric_name)
            if value is not None:
                history.append({
                    "timestamp": snapshot["timestamp"],
                    "value": value,
                    "snapshot_id": snapshot["id"],
                })

        return history
