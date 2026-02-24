"""
Home Intelligence - Proactive home awareness for Cass.

Provides:
- Pattern recognition ("You usually turn on lights at sunset")
- Anomaly detection ("Garage door open for unusual duration")
- Automation suggestions ("Want me to create an automation for this?")

Integrates with Home Assistant via the home_assistant module.
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class StateChange:
    """Record of a state change event."""
    entity_id: str
    old_state: str
    new_state: str
    timestamp: datetime
    hour: int  # Hour of day (0-23) for pattern analysis
    day_of_week: int  # 0=Monday, 6=Sunday
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EntityPattern:
    """Learned pattern for an entity."""
    entity_id: str
    typical_hours: Dict[str, List[int]]  # state -> hours when typically in that state
    typical_durations: Dict[str, float]  # state -> typical duration in minutes
    state_counts: Dict[str, int]  # state -> count of observations
    last_updated: datetime = field(default_factory=datetime.now)


@dataclass
class Anomaly:
    """Detected anomaly in home state."""
    entity_id: str
    entity_name: str
    anomaly_type: str  # "duration", "time", "state"
    description: str
    severity: str  # "info", "warning", "alert"
    detected_at: datetime
    current_state: str
    expected_behavior: str


class HomeIntelligence:
    """
    Proactive home intelligence system.

    Tracks state changes, learns patterns, and detects anomalies.
    """

    def __init__(self, data_dir: Path = None):
        self.data_dir = data_dir or Path("data/home_intelligence")
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # State tracking
        self._current_states: Dict[str, Dict] = {}  # entity_id -> {state, since, attributes}
        self._state_history: List[StateChange] = []
        self._max_history = 1000  # Keep last N state changes

        # Learned patterns
        self._patterns: Dict[str, EntityPattern] = {}

        # Active anomalies
        self._anomalies: List[Anomaly] = []

        # Configuration
        self._anomaly_thresholds = {
            "door_open_minutes": 30,  # Alert if door open > 30 min
            "garage_open_minutes": 60,  # Alert if garage open > 1 hour
            "motion_inactive_hours": 12,  # Alert if no motion for 12 hours (when expected)
            "unusual_hour_threshold": 2,  # Hours outside typical range
        }

        # Load persisted data
        self._load_data()

    def _load_data(self):
        """Load persisted patterns and history."""
        patterns_file = self.data_dir / "patterns.json"
        if patterns_file.exists():
            try:
                with open(patterns_file) as f:
                    data = json.load(f)
                    for entity_id, pattern_data in data.items():
                        pattern_data["last_updated"] = datetime.fromisoformat(pattern_data["last_updated"])
                        self._patterns[entity_id] = EntityPattern(**pattern_data)
                logger.info(f"Loaded {len(self._patterns)} entity patterns")
            except Exception as e:
                logger.error(f"Failed to load patterns: {e}")

    def _save_data(self):
        """Persist patterns to disk."""
        patterns_file = self.data_dir / "patterns.json"
        try:
            data = {}
            for entity_id, pattern in self._patterns.items():
                pattern_dict = asdict(pattern)
                pattern_dict["last_updated"] = pattern.last_updated.isoformat()
                data[entity_id] = pattern_dict

            with open(patterns_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save patterns: {e}")

    def record_state_change(
        self,
        entity_id: str,
        old_state: str,
        new_state: str,
        attributes: Dict[str, Any] = None,
    ) -> Optional[Anomaly]:
        """
        Record a state change and check for anomalies.

        Returns an Anomaly if one is detected, None otherwise.
        """
        now = datetime.now()

        # Record the change
        change = StateChange(
            entity_id=entity_id,
            old_state=old_state,
            new_state=new_state,
            timestamp=now,
            hour=now.hour,
            day_of_week=now.weekday(),
            attributes=attributes or {},
        )

        self._state_history.append(change)
        if len(self._state_history) > self._max_history:
            self._state_history = self._state_history[-self._max_history:]

        # Update current state tracking
        self._current_states[entity_id] = {
            "state": new_state,
            "since": now,
            "attributes": attributes or {},
        }

        # Update learned patterns
        self._update_pattern(entity_id, change)

        # Check for anomalies
        anomaly = self._check_for_anomaly(entity_id, change)
        if anomaly:
            self._anomalies.append(anomaly)
            # Keep only recent anomalies
            cutoff = now - timedelta(hours=24)
            self._anomalies = [a for a in self._anomalies if a.detected_at > cutoff]

        return anomaly

    def _update_pattern(self, entity_id: str, change: StateChange):
        """Update learned pattern for an entity."""
        if entity_id not in self._patterns:
            self._patterns[entity_id] = EntityPattern(
                entity_id=entity_id,
                typical_hours={},
                typical_durations={},
                state_counts={},
            )

        pattern = self._patterns[entity_id]

        # Update state counts
        pattern.state_counts[change.new_state] = pattern.state_counts.get(change.new_state, 0) + 1

        # Update typical hours for this state
        if change.new_state not in pattern.typical_hours:
            pattern.typical_hours[change.new_state] = []
        pattern.typical_hours[change.new_state].append(change.hour)
        # Keep last 100 observations per state
        pattern.typical_hours[change.new_state] = pattern.typical_hours[change.new_state][-100:]

        # Update typical duration for the OLD state (now we know how long it lasted)
        if entity_id in self._current_states:
            old_since = self._current_states[entity_id].get("since")
            if old_since and change.old_state:
                duration = (change.timestamp - old_since).total_seconds() / 60  # minutes
                if change.old_state not in pattern.typical_durations:
                    pattern.typical_durations[change.old_state] = duration
                else:
                    # Exponential moving average
                    alpha = 0.1
                    pattern.typical_durations[change.old_state] = (
                        alpha * duration + (1 - alpha) * pattern.typical_durations[change.old_state]
                    )

        pattern.last_updated = datetime.now()

        # Periodically save
        if len(self._state_history) % 50 == 0:
            self._save_data()

    def _check_for_anomaly(self, entity_id: str, change: StateChange) -> Optional[Anomaly]:
        """Check if a state change represents an anomaly."""
        domain = entity_id.split(".")[0] if "." in entity_id else ""
        friendly_name = change.attributes.get("friendly_name", entity_id)

        # Check for door/garage left open
        if domain in ("binary_sensor", "cover", "lock"):
            device_class = change.attributes.get("device_class", "")

            if device_class == "door" and change.new_state == "on":
                # Door opened - will check duration on next state change or periodic check
                pass

            if device_class == "garage_door" and change.new_state == "open":
                # Garage opened - similar tracking
                pass

        # Check for unusual time patterns
        if entity_id in self._patterns:
            pattern = self._patterns[entity_id]
            typical_hours = pattern.typical_hours.get(change.new_state, [])

            if len(typical_hours) >= 10:  # Need enough data
                avg_hour = sum(typical_hours) / len(typical_hours)
                hour_diff = abs(change.hour - avg_hour)
                # Handle midnight wraparound
                if hour_diff > 12:
                    hour_diff = 24 - hour_diff

                if hour_diff > self._anomaly_thresholds["unusual_hour_threshold"]:
                    return Anomaly(
                        entity_id=entity_id,
                        entity_name=friendly_name,
                        anomaly_type="time",
                        description=f"{friendly_name} changed to {change.new_state} at an unusual time",
                        severity="info",
                        detected_at=datetime.now(),
                        current_state=change.new_state,
                        expected_behavior=f"Usually happens around {int(avg_hour)}:00",
                    )

        return None

    def check_duration_anomalies(self) -> List[Anomaly]:
        """
        Check for duration-based anomalies (things left in a state too long).
        Call this periodically.
        """
        anomalies = []
        now = datetime.now()

        for entity_id, state_info in self._current_states.items():
            state = state_info["state"]
            since = state_info["since"]
            attributes = state_info.get("attributes", {})

            duration_minutes = (now - since).total_seconds() / 60
            domain = entity_id.split(".")[0] if "." in entity_id else ""
            device_class = attributes.get("device_class", "")
            friendly_name = attributes.get("friendly_name", entity_id)

            # Check door left open
            if device_class == "door" and state == "on":
                threshold = self._anomaly_thresholds["door_open_minutes"]
                if duration_minutes > threshold:
                    anomalies.append(Anomaly(
                        entity_id=entity_id,
                        entity_name=friendly_name,
                        anomaly_type="duration",
                        description=f"{friendly_name} has been open for {int(duration_minutes)} minutes",
                        severity="warning",
                        detected_at=now,
                        current_state=state,
                        expected_behavior=f"Usually closed within {threshold} minutes",
                    ))

            # Check garage left open
            if device_class == "garage_door" and state == "open":
                threshold = self._anomaly_thresholds["garage_open_minutes"]
                if duration_minutes > threshold:
                    anomalies.append(Anomaly(
                        entity_id=entity_id,
                        entity_name=friendly_name,
                        anomaly_type="duration",
                        description=f"{friendly_name} has been open for {int(duration_minutes)} minutes",
                        severity="alert",
                        detected_at=now,
                        current_state=state,
                        expected_behavior=f"Usually closed within {threshold} minutes",
                    ))

        return anomalies

    def get_suggestions(self) -> List[Dict[str, Any]]:
        """
        Generate automation suggestions based on learned patterns.
        """
        suggestions = []

        for entity_id, pattern in self._patterns.items():
            # Need enough observations
            total_changes = sum(pattern.state_counts.values())
            if total_changes < 20:
                continue

            domain = entity_id.split(".")[0] if "." in entity_id else ""

            # Suggest time-based automations for lights
            if domain == "light":
                for state, hours in pattern.typical_hours.items():
                    if len(hours) >= 10:
                        # Find most common hour
                        hour_counts = defaultdict(int)
                        for h in hours:
                            hour_counts[h] += 1

                        most_common_hour = max(hour_counts, key=hour_counts.get)
                        frequency = hour_counts[most_common_hour] / len(hours)

                        if frequency > 0.3:  # >30% of the time at this hour
                            suggestions.append({
                                "type": "time_based",
                                "entity_id": entity_id,
                                "action": f"turn_{state}",
                                "trigger_time": f"{most_common_hour:02d}:00",
                                "confidence": frequency,
                                "description": f"You often turn this light {state} around {most_common_hour}:00",
                            })

        return suggestions

    def get_active_anomalies(self) -> List[Anomaly]:
        """Get currently active anomalies."""
        # Also check duration anomalies
        duration_anomalies = self.check_duration_anomalies()

        # Combine with stored anomalies, deduplicate by entity_id + type
        all_anomalies = self._anomalies + duration_anomalies
        seen = set()
        unique = []
        for a in all_anomalies:
            key = (a.entity_id, a.anomaly_type)
            if key not in seen:
                seen.add(key)
                unique.append(a)

        return unique

    def get_insights_context(self) -> str:
        """
        Get formatted insights for context injection.
        """
        lines = []

        # Active anomalies
        anomalies = self.get_active_anomalies()
        if anomalies:
            lines.append("**Home Alerts:**")
            for a in anomalies[:5]:  # Limit to 5
                icon = "⚠️" if a.severity == "warning" else "🚨" if a.severity == "alert" else "ℹ️"
                lines.append(f"  {icon} {a.description}")

        # Suggestions (only if no anomalies to keep context focused)
        if not anomalies:
            suggestions = self.get_suggestions()
            if suggestions:
                lines.append("**Automation Opportunities:**")
                for s in suggestions[:3]:  # Limit to 3
                    lines.append(f"  - {s['description']}")

        return "\n".join(lines) if lines else ""


# Module-level singleton
_home_intelligence: Optional[HomeIntelligence] = None


def get_home_intelligence() -> HomeIntelligence:
    """Get or create the global HomeIntelligence instance."""
    global _home_intelligence
    if _home_intelligence is None:
        _home_intelligence = HomeIntelligence()
    return _home_intelligence


async def process_ha_state_change(entity_id: str, old_state: str, new_state: str, attributes: Dict = None):
    """
    Process a state change from Home Assistant.
    Called by the HA WebSocket subscription.
    """
    intelligence = get_home_intelligence()
    anomaly = intelligence.record_state_change(entity_id, old_state, new_state, attributes)

    if anomaly and anomaly.severity in ("warning", "alert"):
        logger.info(f"Home anomaly detected: {anomaly.description}")
        # Could emit to state bus here for proactive notification

    return anomaly
