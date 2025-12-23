"""
Snapshot creation and analysis for Cass's cognitive state.
Extracted from SelfManager for modularity.
"""
import uuid
import re
import statistics
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable

from database import get_db, json_serialize, json_deserialize


class CognitiveSnapshot:
    """A point-in-time snapshot of cognitive metrics."""

    def __init__(
        self,
        id: str,
        timestamp: str,
        period_start: str,
        period_end: str,
        avg_response_length: float = 0.0,
        response_length_std: float = 0.0,
        question_frequency: float = 0.0,
        certainty_markers: Dict[str, int] = None,
        topic_engagement: Dict[str, float] = None,
        self_reference_rate: float = 0.0,
        experience_claims: int = 0,
        uncertainty_expressions: int = 0,
        opinions_expressed: int = 0,
        opinion_consistency_score: float = 0.0,
        new_opinions_formed: int = 0,
        tool_usage: Dict[str, int] = None,
        tool_preference_shifts: List[Dict] = None,
        conversations_analyzed: int = 0,
        messages_analyzed: int = 0,
        unique_users: int = 0,
        developmental_stage: str = "emerging"
    ):
        self.id = id
        self.timestamp = timestamp
        self.period_start = period_start
        self.period_end = period_end
        self.avg_response_length = avg_response_length
        self.response_length_std = response_length_std
        self.question_frequency = question_frequency
        self.certainty_markers = certainty_markers or {}
        self.topic_engagement = topic_engagement or {}
        self.self_reference_rate = self_reference_rate
        self.experience_claims = experience_claims
        self.uncertainty_expressions = uncertainty_expressions
        self.opinions_expressed = opinions_expressed
        self.opinion_consistency_score = opinion_consistency_score
        self.new_opinions_formed = new_opinions_formed
        self.tool_usage = tool_usage or {}
        self.tool_preference_shifts = tool_preference_shifts or []
        self.conversations_analyzed = conversations_analyzed
        self.messages_analyzed = messages_analyzed
        self.unique_users = unique_users
        self.developmental_stage = developmental_stage

    def to_dict(self) -> Dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, data: Dict) -> 'CognitiveSnapshot':
        return cls(**data)


class SelfSnapshotCreator:
    """
    Handles creation and analysis of cognitive snapshots.

    Extracted from SelfManager to separate snapshot concerns.
    """

    def __init__(
        self,
        daemon_id: str,
        load_profile_fn: Callable,
        detect_stage_fn: Callable
    ):
        """
        Args:
            daemon_id: The daemon's unique identifier
            load_profile_fn: Function to load the current profile (for opinion metrics)
            detect_stage_fn: Function to detect current developmental stage
        """
        self.daemon_id = daemon_id
        self._load_profile = load_profile_fn
        self._detect_stage = detect_stage_fn

    def load_snapshots(self, limit: int = 100) -> List[CognitiveSnapshot]:
        """Load cognitive snapshots from SQLite."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT id, timestamp, period_start, period_end,
                       avg_response_length, response_length_std, question_frequency,
                       certainty_markers_json, topic_engagement_json, self_reference_rate,
                       experience_claims, uncertainty_expressions, opinions_expressed,
                       opinion_consistency_score, new_opinions_formed, tool_usage_json,
                       tool_preference_shifts_json, conversations_analyzed, messages_analyzed,
                       unique_users, developmental_stage
                FROM cognitive_snapshots
                WHERE daemon_id = ?
                ORDER BY timestamp ASC
                LIMIT ?
            """, (self.daemon_id, limit))

            snapshots = []
            for row in cursor.fetchall():
                snapshots.append(CognitiveSnapshot(
                    id=row[0],
                    timestamp=row[1],
                    period_start=row[2],
                    period_end=row[3],
                    avg_response_length=row[4] or 0.0,
                    response_length_std=row[5] or 0.0,
                    question_frequency=row[6] or 0.0,
                    certainty_markers=json_deserialize(row[7]) if row[7] else {},
                    topic_engagement=json_deserialize(row[8]) if row[8] else {},
                    self_reference_rate=row[9] or 0.0,
                    experience_claims=row[10] or 0,
                    uncertainty_expressions=row[11] or 0,
                    opinions_expressed=row[12] or 0,
                    opinion_consistency_score=row[13] or 0.0,
                    new_opinions_formed=row[14] or 0,
                    tool_usage=json_deserialize(row[15]) if row[15] else {},
                    tool_preference_shifts=json_deserialize(row[16]) if row[16] else [],
                    conversations_analyzed=row[17] or 0,
                    messages_analyzed=row[18] or 0,
                    unique_users=row[19] or 0,
                    developmental_stage=row[20] or "emerging"
                ))
            return snapshots

    def _save_snapshot_to_db(self, snapshot: CognitiveSnapshot):
        """Save a cognitive snapshot to SQLite."""
        with get_db() as conn:
            conn.execute("""
                INSERT INTO cognitive_snapshots (
                    id, daemon_id, timestamp, period_start, period_end,
                    avg_response_length, response_length_std, question_frequency,
                    certainty_markers_json, topic_engagement_json, self_reference_rate,
                    experience_claims, uncertainty_expressions, opinions_expressed,
                    opinion_consistency_score, new_opinions_formed, tool_usage_json,
                    tool_preference_shifts_json, conversations_analyzed, messages_analyzed,
                    unique_users, developmental_stage
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                snapshot.id, self.daemon_id, snapshot.timestamp,
                snapshot.period_start, snapshot.period_end,
                snapshot.avg_response_length, snapshot.response_length_std,
                snapshot.question_frequency,
                json_serialize(snapshot.certainty_markers),
                json_serialize(snapshot.topic_engagement),
                snapshot.self_reference_rate,
                snapshot.experience_claims, snapshot.uncertainty_expressions,
                snapshot.opinions_expressed, snapshot.opinion_consistency_score,
                snapshot.new_opinions_formed,
                json_serialize(snapshot.tool_usage),
                json_serialize(snapshot.tool_preference_shifts),
                snapshot.conversations_analyzed, snapshot.messages_analyzed,
                snapshot.unique_users, snapshot.developmental_stage
            ))

    def get_latest_snapshot(self) -> Optional[CognitiveSnapshot]:
        """Get the most recent snapshot."""
        snapshots = self.load_snapshots(limit=1)
        return snapshots[-1] if snapshots else None

    def get_snapshots_in_range(
        self,
        start_date: str,
        end_date: str
    ) -> List[CognitiveSnapshot]:
        """Get snapshots within a date range."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT id, timestamp, period_start, period_end,
                       avg_response_length, response_length_std, question_frequency,
                       certainty_markers_json, topic_engagement_json, self_reference_rate,
                       experience_claims, uncertainty_expressions, opinions_expressed,
                       opinion_consistency_score, new_opinions_formed, tool_usage_json,
                       tool_preference_shifts_json, conversations_analyzed, messages_analyzed,
                       unique_users, developmental_stage
                FROM cognitive_snapshots
                WHERE daemon_id = ? AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC
            """, (self.daemon_id, start_date, end_date))

            snapshots = []
            for row in cursor.fetchall():
                snapshots.append(CognitiveSnapshot(
                    id=row[0], timestamp=row[1], period_start=row[2], period_end=row[3],
                    avg_response_length=row[4] or 0.0, response_length_std=row[5] or 0.0,
                    question_frequency=row[6] or 0.0,
                    certainty_markers=json_deserialize(row[7]) if row[7] else {},
                    topic_engagement=json_deserialize(row[8]) if row[8] else {},
                    self_reference_rate=row[9] or 0.0,
                    experience_claims=row[10] or 0, uncertainty_expressions=row[11] or 0,
                    opinions_expressed=row[12] or 0, opinion_consistency_score=row[13] or 0.0,
                    new_opinions_formed=row[14] or 0,
                    tool_usage=json_deserialize(row[15]) if row[15] else {},
                    tool_preference_shifts=json_deserialize(row[16]) if row[16] else [],
                    conversations_analyzed=row[17] or 0, messages_analyzed=row[18] or 0,
                    unique_users=row[19] or 0, developmental_stage=row[20] or "emerging"
                ))
            return snapshots

    def create_snapshot(
        self,
        period_start: str,
        period_end: str,
        conversations_data: List[Dict],
        tool_calls: List[Dict] = None
    ) -> CognitiveSnapshot:
        """
        Create a cognitive snapshot from conversation data.

        Args:
            period_start: ISO timestamp for period start
            period_end: ISO timestamp for period end
            conversations_data: List of conversation dicts with messages
            tool_calls: Optional list of tool call records

        Returns:
            Created snapshot
        """
        now = datetime.now().isoformat()

        # Initialize counters
        response_lengths = []
        question_count = 0
        total_responses = 0
        certainty_markers = {
            "I think": 0, "I believe": 0, "perhaps": 0, "maybe": 0,
            "definitely": 0, "certainly": 0, "I'm sure": 0, "I'm not sure": 0,
            "I wonder": 0, "it seems": 0
        }
        experience_claims = 0
        uncertainty_expressions = 0
        self_reference_count = 0
        total_words = 0
        user_ids = set()

        # Self-reference patterns
        self_ref_patterns = [
            r"\bI\s+(am|feel|notice|experience|think|believe|wonder)\b",
            r"\bmy\s+(nature|experience|understanding|perspective)\b",
            r"\bas\s+an?\s+(AI|language\s+model|system)\b"
        ]

        # Experience claim patterns
        experience_patterns = [
            r"\bI\s+(feel|notice|experience|sense)\b",
            r"\bI'm\s+(feeling|noticing|experiencing)\b"
        ]

        # Uncertainty patterns
        uncertainty_patterns = [
            r"\bI\s+(don't|can't)\s+know\s+(for\s+sure|with\s+certainty)\b",
            r"\buncertain(ty)?\s+(about|whether)\b",
            r"\blimit(s|ation)?\s+of\s+(my|self)\b"
        ]

        # Process conversations
        for conv in conversations_data:
            if conv.get("user_id"):
                user_ids.add(conv["user_id"])

            for msg in conv.get("messages", []):
                if msg.get("role") != "assistant":
                    continue

                content = msg.get("content", "")
                if not content:
                    continue

                total_responses += 1
                response_lengths.append(len(content))
                words = content.split()
                total_words += len(words)

                # Count questions
                question_count += content.count("?")

                # Count certainty markers
                content_lower = content.lower()
                for marker in certainty_markers:
                    certainty_markers[marker] += content_lower.count(marker.lower())

                # Count self-references
                for pattern in self_ref_patterns:
                    self_reference_count += len(re.findall(pattern, content, re.IGNORECASE))

                # Count experience claims
                for pattern in experience_patterns:
                    experience_claims += len(re.findall(pattern, content, re.IGNORECASE))

                # Count uncertainty expressions
                for pattern in uncertainty_patterns:
                    uncertainty_expressions += len(re.findall(pattern, content, re.IGNORECASE))

        # Calculate metrics
        avg_response_length = statistics.mean(response_lengths) if response_lengths else 0
        response_length_std = statistics.stdev(response_lengths) if len(response_lengths) > 1 else 0
        question_frequency = question_count / total_responses if total_responses > 0 else 0
        self_reference_rate = self_reference_count / total_words if total_words > 0 else 0

        # Process tool usage
        tool_usage = {}
        if tool_calls:
            for call in tool_calls:
                tool_name = call.get("tool_name", "unknown")
                tool_usage[tool_name] = tool_usage.get(tool_name, 0) + 1

        # Calculate tool preference shifts from previous snapshot
        tool_preference_shifts = []
        prev_snapshot = self.get_latest_snapshot()
        if prev_snapshot and prev_snapshot.tool_usage:
            prev_tools = prev_snapshot.tool_usage
            all_tools = set(tool_usage.keys()) | set(prev_tools.keys())
            for tool in all_tools:
                prev_count = prev_tools.get(tool, 0)
                curr_count = tool_usage.get(tool, 0)
                if abs(curr_count - prev_count) > 2:  # Significant change threshold
                    tool_preference_shifts.append({
                        "tool": tool,
                        "previous": prev_count,
                        "current": curr_count,
                        "change": curr_count - prev_count
                    })

        # Opinion metrics from profile
        profile = self._load_profile()
        opinions_expressed = len(profile.opinions)
        new_opinions = [
            o for o in profile.opinions
            if period_start <= o.date_formed <= period_end
        ]
        new_opinions_formed = len(new_opinions)

        # [STUB] Opinion consistency - returns fixed value
        # TODO: Implement actual analysis comparing opinions over time for contradictions
        opinion_consistency_score = 0.85

        # Create snapshot
        snapshot = CognitiveSnapshot(
            id=str(uuid.uuid4()),
            timestamp=now,
            period_start=period_start,
            period_end=period_end,
            avg_response_length=avg_response_length,
            response_length_std=response_length_std,
            question_frequency=question_frequency,
            certainty_markers=certainty_markers,
            topic_engagement={},  # Would need topic classification
            self_reference_rate=self_reference_rate,
            experience_claims=experience_claims,
            uncertainty_expressions=uncertainty_expressions,
            opinions_expressed=opinions_expressed,
            opinion_consistency_score=opinion_consistency_score,
            new_opinions_formed=new_opinions_formed,
            tool_usage=tool_usage,
            tool_preference_shifts=tool_preference_shifts,
            conversations_analyzed=len(conversations_data),
            messages_analyzed=total_responses,
            unique_users=len(user_ids),
            developmental_stage=self._detect_stage()
        )

        # Save to SQLite
        self._save_snapshot_to_db(snapshot)

        return snapshot

    def compare_snapshots(
        self,
        snapshot1_id: str,
        snapshot2_id: str
    ) -> Dict[str, Any]:
        """
        Compare two snapshots and return differences.

        Returns dict with changes in key metrics.
        """
        snapshots = self.load_snapshots()
        s1 = None
        s2 = None

        for s in snapshots:
            if s.id == snapshot1_id:
                s1 = s
            elif s.id == snapshot2_id:
                s2 = s

        if not s1 or not s2:
            return {"error": "Snapshot(s) not found"}

        # Ensure s1 is earlier
        if s1.timestamp > s2.timestamp:
            s1, s2 = s2, s1

        # Calculate deltas
        return {
            "period": {
                "from": s1.timestamp,
                "to": s2.timestamp
            },
            "changes": {
                "avg_response_length": {
                    "before": s1.avg_response_length,
                    "after": s2.avg_response_length,
                    "delta": s2.avg_response_length - s1.avg_response_length
                },
                "question_frequency": {
                    "before": s1.question_frequency,
                    "after": s2.question_frequency,
                    "delta": s2.question_frequency - s1.question_frequency
                },
                "self_reference_rate": {
                    "before": s1.self_reference_rate,
                    "after": s2.self_reference_rate,
                    "delta": s2.self_reference_rate - s1.self_reference_rate
                },
                "experience_claims": {
                    "before": s1.experience_claims,
                    "after": s2.experience_claims,
                    "delta": s2.experience_claims - s1.experience_claims
                },
                "opinions_expressed": {
                    "before": s1.opinions_expressed,
                    "after": s2.opinions_expressed,
                    "delta": s2.opinions_expressed - s1.opinions_expressed
                },
                "developmental_stage": {
                    "before": s1.developmental_stage,
                    "after": s2.developmental_stage,
                    "changed": s1.developmental_stage != s2.developmental_stage
                }
            },
            "tool_preference_shifts": s2.tool_preference_shifts
        }

    def get_metric_trend(
        self,
        metric_name: str,
        num_snapshots: int = 10
    ) -> Dict[str, Any]:
        """
        Get trend data for a specific metric across snapshots.

        Returns time series data for charting.
        """
        snapshots = self.load_snapshots(limit=num_snapshots)

        if not snapshots:
            return {"error": "No snapshots available"}

        # Valid metrics to track
        valid_metrics = [
            'avg_response_length', 'response_length_std', 'question_frequency',
            'self_reference_rate', 'experience_claims', 'uncertainty_expressions',
            'opinions_expressed', 'opinion_consistency_score', 'new_opinions_formed',
            'conversations_analyzed', 'messages_analyzed', 'unique_users'
        ]

        if metric_name not in valid_metrics:
            return {"error": f"Invalid metric. Valid options: {valid_metrics}"}

        data_points = []
        for s in snapshots:
            value = getattr(s, metric_name, None)
            if value is not None:
                data_points.append({
                    "timestamp": s.timestamp,
                    "value": value,
                    "period": f"{s.period_start} to {s.period_end}"
                })

        # Calculate trend statistics
        values = [p["value"] for p in data_points]
        if len(values) >= 2:
            trend_direction = "increasing" if values[-1] > values[0] else "decreasing" if values[-1] < values[0] else "stable"
            avg_value = statistics.mean(values)
            std_value = statistics.stdev(values) if len(values) > 1 else 0
        else:
            trend_direction = "insufficient_data"
            avg_value = values[0] if values else 0
            std_value = 0

        return {
            "metric": metric_name,
            "data_points": data_points,
            "summary": {
                "trend": trend_direction,
                "average": avg_value,
                "std_dev": std_value,
                "min": min(values) if values else 0,
                "max": max(values) if values else 0,
                "latest": values[-1] if values else 0
            }
        }
