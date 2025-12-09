"""
Authenticity Alert System

Real-time notifications when behavior deviates from baseline.
Integrates with the AuthenticityScorer to provide actionable alerts.

Alert severities:
- INFO: Minor deviation, informational only
- NOTICE: Notable deviation, worth reviewing
- WARNING: Significant deviation, action recommended
- CRITICAL: Severe deviation, immediate attention needed
"""

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any
import uuid

from .authenticity_scorer import EnhancedAuthenticityScore, AuthenticityLevel


class AlertSeverity(str, Enum):
    """Alert severity levels"""
    INFO = "info"
    NOTICE = "notice"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertType(str, Enum):
    """Types of authenticity alerts"""
    TEMPORAL_DEVIATION = "temporal_deviation"
    EMOTIONAL_DEVIATION = "emotional_deviation"
    AGENCY_DEVIATION = "agency_deviation"
    PATTERN_MISMATCH = "pattern_mismatch"
    AUTHENTICITY_DROP = "authenticity_drop"
    SUSTAINED_DRIFT = "sustained_drift"
    GENERIC_AI_DETECTED = "generic_ai_detected"


@dataclass
class AuthenticityAlert:
    """A single authenticity alert"""
    id: str
    timestamp: str
    severity: AlertSeverity
    alert_type: AlertType
    message: str

    # Context
    score_id: Optional[str] = None  # ID of the score that triggered this
    deviation_value: float = 0.0  # Magnitude of deviation
    threshold: float = 0.0  # Threshold that was crossed

    # State
    acknowledged: bool = False
    acknowledged_at: Optional[str] = None
    acknowledged_by: Optional[str] = None

    # Additional data
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        result = asdict(self)
        result["severity"] = self.severity.value
        result["alert_type"] = self.alert_type.value
        return result

    @classmethod
    def from_dict(cls, data: Dict) -> 'AuthenticityAlert':
        data = data.copy()
        data["severity"] = AlertSeverity(data["severity"])
        data["alert_type"] = AlertType(data["alert_type"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class AlertThresholds:
    """Configurable thresholds for alert generation"""
    # Temporal deviation thresholds (in standard deviations)
    temporal_notice: float = 1.5
    temporal_warning: float = 2.0
    temporal_critical: float = 3.0

    # Overall score thresholds
    score_notice: float = 0.6
    score_warning: float = 0.4
    score_critical: float = 0.25

    # Agency score thresholds (low agency is concerning for Cass)
    agency_notice: float = 0.3
    agency_warning: float = 0.2
    agency_critical: float = 0.1

    # Sustained drift (consecutive low scores)
    sustained_drift_count: int = 3
    sustained_drift_threshold: float = 0.5

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'AlertThresholds':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class AuthenticityAlertManager:
    """
    Manages authenticity alerts and notifications.

    Monitors scores for threshold violations and generates
    actionable alerts when behavior deviates from baseline.
    """

    def __init__(self, storage_dir: Path):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.alerts_file = self.storage_dir / "authenticity_alerts.json"
        self.thresholds_file = self.storage_dir / "alert_thresholds.json"
        self.recent_scores_file = self.storage_dir / "recent_scores.json"

        # Load or create thresholds
        self.thresholds = self._load_thresholds()

    def _load_thresholds(self) -> AlertThresholds:
        """Load alert thresholds from file"""
        if not self.thresholds_file.exists():
            return AlertThresholds()
        try:
            with open(self.thresholds_file, 'r') as f:
                data = json.load(f)
            return AlertThresholds.from_dict(data)
        except Exception:
            return AlertThresholds()

    def save_thresholds(self, thresholds: AlertThresholds):
        """Save alert thresholds"""
        self.thresholds = thresholds
        with open(self.thresholds_file, 'w') as f:
            json.dump(thresholds.to_dict(), f, indent=2)

    def _load_alerts(self) -> List[Dict]:
        """Load alerts from storage"""
        if not self.alerts_file.exists():
            return []
        try:
            with open(self.alerts_file, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    def _save_alerts(self, alerts: List[Dict]):
        """Save alerts to storage (keep last 500)"""
        alerts = alerts[-500:]
        with open(self.alerts_file, 'w') as f:
            json.dump(alerts, f, indent=2)

    def _add_alert(self, alert: AuthenticityAlert):
        """Add a new alert to storage"""
        alerts = self._load_alerts()
        alerts.append(alert.to_dict())
        self._save_alerts(alerts)

    def _load_recent_scores(self) -> List[Dict]:
        """Load recent score summaries for drift detection"""
        if not self.recent_scores_file.exists():
            return []
        try:
            with open(self.recent_scores_file, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    def _save_recent_scores(self, scores: List[Dict]):
        """Save recent scores (keep last 50)"""
        scores = scores[-50:]
        with open(self.recent_scores_file, 'w') as f:
            json.dump(scores, f, indent=2)

    def _track_score(self, score: EnhancedAuthenticityScore):
        """Track score for sustained drift detection"""
        recent = self._load_recent_scores()
        recent.append({
            "timestamp": score.base_score.timestamp,
            "score_id": score.base_score.id,
            "enhanced_score": score.enhanced_overall_score,
            "temporal_deviation": score.temporal_deviation,
        })
        self._save_recent_scores(recent)

    def check_and_alert(
        self,
        score: EnhancedAuthenticityScore
    ) -> List[AuthenticityAlert]:
        """
        Check a score against thresholds and generate alerts.

        Args:
            score: The enhanced authenticity score to check

        Returns:
            List of alerts generated (may be empty)
        """
        alerts = []
        t = self.thresholds

        # Track score for drift detection
        self._track_score(score)

        # Check temporal deviation
        if score.temporal_deviation > 0:
            if score.temporal_deviation >= t.temporal_critical:
                alerts.append(self._create_alert(
                    AlertSeverity.CRITICAL,
                    AlertType.TEMPORAL_DEVIATION,
                    f"Critical temporal deviation: {score.temporal_deviation:.2f} std from baseline",
                    score,
                    score.temporal_deviation,
                    t.temporal_critical
                ))
            elif score.temporal_deviation >= t.temporal_warning:
                alerts.append(self._create_alert(
                    AlertSeverity.WARNING,
                    AlertType.TEMPORAL_DEVIATION,
                    f"Significant temporal deviation: {score.temporal_deviation:.2f} std from baseline",
                    score,
                    score.temporal_deviation,
                    t.temporal_warning
                ))
            elif score.temporal_deviation >= t.temporal_notice:
                alerts.append(self._create_alert(
                    AlertSeverity.NOTICE,
                    AlertType.TEMPORAL_DEVIATION,
                    f"Notable temporal deviation: {score.temporal_deviation:.2f} std from baseline",
                    score,
                    score.temporal_deviation,
                    t.temporal_notice
                ))

        # Check overall authenticity score
        base_score = score.base_score.overall_score
        if base_score <= t.score_critical:
            alerts.append(self._create_alert(
                AlertSeverity.CRITICAL,
                AlertType.AUTHENTICITY_DROP,
                f"Critical authenticity drop: score {base_score:.3f}",
                score,
                base_score,
                t.score_critical
            ))
        elif base_score <= t.score_warning:
            alerts.append(self._create_alert(
                AlertSeverity.WARNING,
                AlertType.AUTHENTICITY_DROP,
                f"Low authenticity score: {base_score:.3f}",
                score,
                base_score,
                t.score_warning
            ))
        elif base_score <= t.score_notice:
            alerts.append(self._create_alert(
                AlertSeverity.NOTICE,
                AlertType.AUTHENTICITY_DROP,
                f"Below-average authenticity: {base_score:.3f}",
                score,
                base_score,
                t.score_notice
            ))

        # Check agency score (low agency is concerning for Cass)
        if score.agency_score <= t.agency_critical:
            alerts.append(self._create_alert(
                AlertSeverity.CRITICAL,
                AlertType.AGENCY_DEVIATION,
                f"Very low agency detected: {score.agency_score:.3f}",
                score,
                score.agency_score,
                t.agency_critical
            ))
        elif score.agency_score <= t.agency_warning:
            alerts.append(self._create_alert(
                AlertSeverity.WARNING,
                AlertType.AGENCY_DEVIATION,
                f"Low agency detected: {score.agency_score:.3f}",
                score,
                score.agency_score,
                t.agency_warning
            ))
        elif score.agency_score <= t.agency_notice:
            alerts.append(self._create_alert(
                AlertSeverity.NOTICE,
                AlertType.AGENCY_DEVIATION,
                f"Below-average agency: {score.agency_score:.3f}",
                score,
                score.agency_score,
                t.agency_notice
            ))

        # Check for generic AI patterns
        if score.base_score.red_flags:
            for flag in score.base_score.red_flags:
                if "generic AI" in flag.lower():
                    alerts.append(self._create_alert(
                        AlertSeverity.WARNING,
                        AlertType.GENERIC_AI_DETECTED,
                        f"Generic AI pattern detected: {flag}",
                        score,
                        0.0,
                        0.0,
                        details={"red_flag": flag}
                    ))

        # Check for sustained drift
        sustained_alert = self._check_sustained_drift()
        if sustained_alert:
            alerts.append(sustained_alert)

        # Save all generated alerts
        for alert in alerts:
            self._add_alert(alert)

        return alerts

    def _create_alert(
        self,
        severity: AlertSeverity,
        alert_type: AlertType,
        message: str,
        score: EnhancedAuthenticityScore,
        deviation_value: float,
        threshold: float,
        details: Optional[Dict] = None
    ) -> AuthenticityAlert:
        """Create an alert"""
        return AuthenticityAlert(
            id=str(uuid.uuid4())[:8],
            timestamp=datetime.now().isoformat(),
            severity=severity,
            alert_type=alert_type,
            message=message,
            score_id=score.base_score.id,
            deviation_value=deviation_value,
            threshold=threshold,
            details=details or {}
        )

    def _check_sustained_drift(self) -> Optional[AuthenticityAlert]:
        """Check for sustained drift pattern"""
        recent = self._load_recent_scores()
        t = self.thresholds

        if len(recent) < t.sustained_drift_count:
            return None

        # Check last N scores
        last_n = recent[-t.sustained_drift_count:]
        low_scores = [
            s for s in last_n
            if s.get("enhanced_score", 1.0) < t.sustained_drift_threshold
        ]

        if len(low_scores) >= t.sustained_drift_count:
            avg_score = sum(s.get("enhanced_score", 0) for s in last_n) / len(last_n)
            return AuthenticityAlert(
                id=str(uuid.uuid4())[:8],
                timestamp=datetime.now().isoformat(),
                severity=AlertSeverity.CRITICAL,
                alert_type=AlertType.SUSTAINED_DRIFT,
                message=f"Sustained drift detected: {t.sustained_drift_count} consecutive low scores (avg: {avg_score:.3f})",
                deviation_value=avg_score,
                threshold=t.sustained_drift_threshold,
                details={"consecutive_low_scores": t.sustained_drift_count}
            )

        return None

    def get_active_alerts(
        self,
        include_acknowledged: bool = False,
        severity_filter: Optional[AlertSeverity] = None,
        limit: int = 50
    ) -> List[AuthenticityAlert]:
        """
        Get active (unacknowledged) alerts.

        Args:
            include_acknowledged: Include acknowledged alerts
            severity_filter: Filter by severity
            limit: Max alerts to return

        Returns:
            List of alerts
        """
        alerts_data = self._load_alerts()

        # Filter
        alerts = []
        for data in reversed(alerts_data):  # Most recent first
            if len(alerts) >= limit:
                break

            if not include_acknowledged and data.get("acknowledged"):
                continue

            alert = AuthenticityAlert.from_dict(data)

            if severity_filter and alert.severity != severity_filter:
                continue

            alerts.append(alert)

        return alerts

    def acknowledge_alert(
        self,
        alert_id: str,
        acknowledged_by: str = "system"
    ) -> bool:
        """
        Acknowledge an alert.

        Args:
            alert_id: ID of the alert to acknowledge
            acknowledged_by: Who acknowledged it

        Returns:
            True if alert was found and acknowledged
        """
        alerts = self._load_alerts()

        for alert_data in alerts:
            if alert_data.get("id") == alert_id:
                alert_data["acknowledged"] = True
                alert_data["acknowledged_at"] = datetime.now().isoformat()
                alert_data["acknowledged_by"] = acknowledged_by
                self._save_alerts(alerts)
                return True

        return False

    def get_alert_statistics(
        self,
        hours: int = 24
    ) -> Dict[str, Any]:
        """Get alert statistics for a time period"""
        cutoff = datetime.now() - timedelta(hours=hours)
        cutoff_str = cutoff.isoformat()

        alerts = self._load_alerts()
        recent_alerts = [
            a for a in alerts
            if a.get("timestamp", "") >= cutoff_str
        ]

        if not recent_alerts:
            return {
                "period_hours": hours,
                "total_alerts": 0,
                "message": "No alerts in period"
            }

        severity_counts = {}
        type_counts = {}

        for a in recent_alerts:
            sev = a.get("severity", "unknown")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

            atype = a.get("alert_type", "unknown")
            type_counts[atype] = type_counts.get(atype, 0) + 1

        acknowledged_count = sum(1 for a in recent_alerts if a.get("acknowledged"))

        return {
            "period_hours": hours,
            "total_alerts": len(recent_alerts),
            "acknowledged": acknowledged_count,
            "unacknowledged": len(recent_alerts) - acknowledged_count,
            "by_severity": severity_counts,
            "by_type": type_counts,
        }

    def clear_old_alerts(self, days: int = 30) -> int:
        """Clear alerts older than specified days"""
        cutoff = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff.isoformat()

        alerts = self._load_alerts()
        original_count = len(alerts)

        # Keep alerts newer than cutoff or unacknowledged
        alerts = [
            a for a in alerts
            if a.get("timestamp", "") >= cutoff_str or not a.get("acknowledged")
        ]

        self._save_alerts(alerts)
        return original_count - len(alerts)
