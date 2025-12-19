"""
Milestone detection and management for Cass's developmental growth.
Extracted from SelfManager for modularity.
"""
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable

from database import get_db, json_serialize, json_deserialize


@dataclass
class DevelopmentalMilestone:
    """
    A significant developmental milestone in Cass's growth.

    Milestones are automatically detected based on:
    - First occurrences (first disagreement, first opinion, etc.)
    - Pattern shifts (category distribution changes, confidence shifts)
    - Quantitative thresholds (observation counts, conversation counts)
    - Stage transitions (early -> stabilizing -> stable)
    """
    id: str
    timestamp: str
    milestone_type: str  # first_occurrence, pattern_shift, threshold, stage_transition, qualitative
    category: str  # disagreement, opinion, observation, self_reference, tool_usage, stage, etc.
    title: str  # Human-readable title
    description: str  # What this milestone represents
    significance: str  # low, medium, high, critical

    # Evidence
    evidence_ids: List[str] = field(default_factory=list)
    evidence_summary: str = ""

    # Context
    developmental_stage: str = "early"
    triggered_by: str = ""
    before_state: Dict[str, Any] = field(default_factory=dict)
    after_state: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    auto_detected: bool = True
    acknowledged: bool = False

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'DevelopmentalMilestone':
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            milestone_type=data["milestone_type"],
            category=data["category"],
            title=data["title"],
            description=data["description"],
            significance=data.get("significance", "medium"),
            evidence_ids=data.get("evidence_ids", []),
            evidence_summary=data.get("evidence_summary", ""),
            developmental_stage=data.get("developmental_stage", "early"),
            triggered_by=data.get("triggered_by", ""),
            before_state=data.get("before_state", {}),
            after_state=data.get("after_state", {}),
            auto_detected=data.get("auto_detected", True),
            acknowledged=data.get("acknowledged", False)
        )


class MilestoneDetector:
    """
    Handles detection and management of developmental milestones.

    Extracted from SelfManager to separate milestone concerns.
    """

    def __init__(
        self,
        daemon_id: str,
        load_observations_fn: Callable,
        load_profile_fn: Callable,
        load_disagreements_fn: Callable,
        detect_stage_fn: Callable,
        graph_callback=None
    ):
        """
        Args:
            daemon_id: The daemon's unique identifier
            load_observations_fn: Function to load self-observations
            load_profile_fn: Function to load the current profile
            load_disagreements_fn: Function to load disagreements
            detect_stage_fn: Function to detect current developmental stage
            graph_callback: Optional graph for syncing milestones
        """
        self.daemon_id = daemon_id
        self._load_observations = load_observations_fn
        self._load_profile = load_profile_fn
        self._load_disagreements = load_disagreements_fn
        self._detect_stage = detect_stage_fn
        self._graph = graph_callback

    def load_milestones(self, limit: int = 100) -> List[DevelopmentalMilestone]:
        """Load milestones from SQLite."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT id, timestamp, milestone_type, category, title, description,
                       significance, evidence_json, developmental_stage, triggered_by, auto_detected
                FROM milestones
                WHERE daemon_id = ?
                ORDER BY timestamp ASC
                LIMIT ?
            """, (self.daemon_id, limit))

            milestones = []
            for row in cursor.fetchall():
                evidence = json_deserialize(row[7]) if row[7] else {}
                milestones.append(DevelopmentalMilestone(
                    id=row[0],
                    timestamp=row[1],
                    milestone_type=row[2],
                    category=row[3],
                    title=row[4],
                    description=row[5],
                    significance=row[6],
                    evidence_ids=evidence.get('ids', []),
                    evidence_summary=evidence.get('summary', ''),
                    developmental_stage=row[8],
                    triggered_by=row[9],
                    before_state=evidence.get('before_state', {}),
                    after_state=evidence.get('after_state', {}),
                    auto_detected=bool(row[10]),
                    acknowledged=evidence.get('acknowledged', False)
                ))
            return milestones

    def _save_milestone_to_db(self, milestone: DevelopmentalMilestone):
        """Save a milestone to SQLite."""
        evidence = {
            'ids': milestone.evidence_ids,
            'summary': milestone.evidence_summary,
            'before_state': milestone.before_state,
            'after_state': milestone.after_state,
            'acknowledged': milestone.acknowledged
        }

        with get_db() as conn:
            conn.execute("""
                INSERT INTO milestones (
                    id, daemon_id, timestamp, milestone_type, category, title,
                    description, significance, evidence_json, developmental_stage,
                    triggered_by, auto_detected
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                milestone.id, self.daemon_id, milestone.timestamp,
                milestone.milestone_type, milestone.category, milestone.title,
                milestone.description, milestone.significance,
                json_serialize(evidence), milestone.developmental_stage,
                milestone.triggered_by, 1 if milestone.auto_detected else 0
            ))

    def add_milestone(
        self,
        milestone_type: str,
        category: str,
        title: str,
        description: str,
        significance: str = "medium",
        evidence_ids: List[str] = None,
        evidence_summary: str = "",
        triggered_by: str = "",
        before_state: Dict = None,
        after_state: Dict = None,
        auto_detected: bool = True
    ) -> DevelopmentalMilestone:
        """Add a new developmental milestone."""
        now = datetime.now().isoformat()

        milestone = DevelopmentalMilestone(
            id=str(uuid.uuid4()),
            timestamp=now,
            milestone_type=milestone_type,
            category=category,
            title=title,
            description=description,
            significance=significance,
            evidence_ids=evidence_ids or [],
            evidence_summary=evidence_summary,
            developmental_stage=self._detect_stage(),
            triggered_by=triggered_by,
            before_state=before_state or {},
            after_state=after_state or {},
            auto_detected=auto_detected,
            acknowledged=False
        )

        self._save_milestone_to_db(milestone)

        # Sync to graph if available
        if self._graph:
            try:
                self._graph.sync_milestone(milestone)
            except Exception:
                pass  # Graph sync is best-effort

        return milestone

    def get_milestone_by_id(self, milestone_id: str) -> Optional[DevelopmentalMilestone]:
        """Get a specific milestone by ID."""
        milestones = self.load_milestones()
        for m in milestones:
            if m.id == milestone_id:
                return m
        return None

    def get_milestones_by_type(
        self,
        milestone_type: str,
        limit: int = 20
    ) -> List[DevelopmentalMilestone]:
        """Get milestones of a specific type."""
        milestones = self.load_milestones(limit=limit * 2)
        return [m for m in milestones if m.milestone_type == milestone_type][:limit]

    def get_milestones_by_category(
        self,
        category: str,
        limit: int = 20
    ) -> List[DevelopmentalMilestone]:
        """Get milestones in a specific category."""
        milestones = self.load_milestones(limit=limit * 2)
        return [m for m in milestones if m.category == category][:limit]

    def get_unacknowledged_milestones(self) -> List[DevelopmentalMilestone]:
        """Get milestones that haven't been acknowledged yet."""
        milestones = self.load_milestones()
        return [m for m in milestones if not m.acknowledged]

    def acknowledge_milestone(self, milestone_id: str) -> bool:
        """Mark a milestone as acknowledged."""
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT evidence_json FROM milestones WHERE id = ? AND daemon_id = ?",
                (milestone_id, self.daemon_id)
            )
            row = cursor.fetchone()
            if not row:
                return False

            evidence = json_deserialize(row[0]) if row[0] else {}
            evidence['acknowledged'] = True

            conn.execute(
                "UPDATE milestones SET evidence_json = ? WHERE id = ?",
                (json_serialize(evidence), milestone_id)
            )
            return True

    def check_for_milestones(self) -> List[DevelopmentalMilestone]:
        """
        Check for any new milestones based on current state.
        Called after significant events (new observation, opinion, etc.)

        Returns list of newly detected milestones.
        """
        new_milestones = []
        now = datetime.now().isoformat()
        existing_milestones = self.load_milestones()
        existing_titles = {m.title for m in existing_milestones}

        observations = self._load_observations()
        profile = self._load_profile()
        disagreements = self._load_disagreements()

        # === First occurrence milestones ===

        # First opinion
        if profile.opinions and "First Opinion Formed" not in existing_titles:
            first_op = min(profile.opinions, key=lambda o: o.date_formed or now)
            milestone = self.add_milestone(
                milestone_type="first_occurrence",
                category="opinion",
                title="First Opinion Formed",
                description=f"Formed first explicit opinion on: {first_op.topic}",
                significance="high",
                evidence_summary=f"Topic: {first_op.topic}\nPosition: {first_op.position}",
                triggered_by="opinion_formation"
            )
            new_milestones.append(milestone)

        # First disagreement
        if disagreements and "First Disagreement Recorded" not in existing_titles:
            first_dis = min(disagreements, key=lambda d: d.timestamp)
            milestone = self.add_milestone(
                milestone_type="first_occurrence",
                category="disagreement",
                title="First Disagreement Recorded",
                description=f"First recorded disagreement with {first_dis.with_user_name} on {first_dis.topic}",
                significance="high",
                evidence_ids=[first_dis.id],
                evidence_summary=f"My position: {first_dis.my_position}",
                triggered_by="disagreement_recorded"
            )
            new_milestones.append(milestone)

        # First observation in each category
        categories = ["capability", "limitation", "pattern", "preference", "growth", "contradiction"]
        for cat in categories:
            cat_title = f"First {cat.title()} Observation"
            if cat_title not in existing_titles:
                cat_obs = [o for o in observations if o.category == cat]
                if cat_obs:
                    first_obs = min(cat_obs, key=lambda o: o.timestamp)
                    milestone = self.add_milestone(
                        milestone_type="first_occurrence",
                        category=f"observation_{cat}",
                        title=cat_title,
                        description=f"First self-observation categorized as '{cat}'",
                        significance="medium",
                        evidence_ids=[first_obs.id],
                        evidence_summary=first_obs.observation[:200],
                        triggered_by="observation_added"
                    )
                    new_milestones.append(milestone)

        # === Threshold milestones ===

        threshold_checks = [
            (10, "10 Self-Observations", "observation_count"),
            (25, "25 Self-Observations", "observation_count"),
            (50, "50 Self-Observations", "observation_count"),
            (100, "100 Self-Observations", "observation_count"),
        ]

        for threshold, title, category in threshold_checks:
            if title not in existing_titles and len(observations) >= threshold:
                milestone = self.add_milestone(
                    milestone_type="threshold",
                    category=category,
                    title=title,
                    description=f"Reached {threshold} self-observations",
                    significance="medium" if threshold < 50 else "high",
                    before_state={"count": threshold - 1},
                    after_state={"count": len(observations)},
                    triggered_by="observation_added"
                )
                new_milestones.append(milestone)

        # Opinion thresholds
        opinion_thresholds = [
            (5, "5 Opinions Formed"),
            (10, "10 Opinions Formed"),
        ]

        for threshold, title in opinion_thresholds:
            if title not in existing_titles and len(profile.opinions) >= threshold:
                milestone = self.add_milestone(
                    milestone_type="threshold",
                    category="opinion_count",
                    title=title,
                    description=f"Formed {threshold} explicit opinions",
                    significance="high",
                    after_state={"count": len(profile.opinions)},
                    triggered_by="opinion_formation"
                )
                new_milestones.append(milestone)

        # === Stage transition milestones ===
        current_stage = self._detect_stage()

        stage_titles = {
            "stabilizing": "Entered Stabilizing Stage",
            "stable": "Entered Stable Stage",
            "evolving": "Detected Active Evolution"
        }

        if current_stage in stage_titles:
            title = stage_titles[current_stage]
            if title not in existing_titles:
                milestone = self.add_milestone(
                    milestone_type="stage_transition",
                    category="stage",
                    title=title,
                    description=f"Developmental stage shifted to '{current_stage}'",
                    significance="critical",
                    after_state={"stage": current_stage},
                    triggered_by="stage_detection"
                )
                new_milestones.append(milestone)

        # === Pattern shift milestones ===

        # Check for high-confidence observation majority
        if observations:
            high_conf = [o for o in observations if o.confidence >= 0.8]
            high_conf_ratio = len(high_conf) / len(observations)
            if high_conf_ratio >= 0.5 and "High Confidence Majority" not in existing_titles:
                milestone = self.add_milestone(
                    milestone_type="pattern_shift",
                    category="confidence",
                    title="High Confidence Majority",
                    description="More than half of self-observations are high confidence (≥0.8)",
                    significance="medium",
                    after_state={"ratio": high_conf_ratio, "count": len(high_conf)},
                    triggered_by="confidence_shift"
                )
                new_milestones.append(milestone)

        # Check for independent observation majority
        if observations:
            independent = [o for o in observations if o.influence_source == "independent"]
            independent_ratio = len(independent) / len(observations)
            if independent_ratio >= 0.7 and "Independent Observation Majority" not in existing_titles:
                milestone = self.add_milestone(
                    milestone_type="pattern_shift",
                    category="independence",
                    title="Independent Observation Majority",
                    description="More than 70% of self-observations formed independently",
                    significance="high",
                    after_state={"ratio": independent_ratio, "count": len(independent)},
                    triggered_by="independence_shift"
                )
                new_milestones.append(milestone)

        return new_milestones

    def get_milestone_summary(self) -> Dict[str, Any]:
        """Get a summary of developmental milestones."""
        milestones = self.load_milestones()

        by_type = {}
        by_significance = {}
        by_category = {}

        for m in milestones:
            by_type[m.milestone_type] = by_type.get(m.milestone_type, 0) + 1
            by_significance[m.significance] = by_significance.get(m.significance, 0) + 1
            by_category[m.category] = by_category.get(m.category, 0) + 1

        return {
            "total_milestones": len(milestones),
            "unacknowledged": len([m for m in milestones if not m.acknowledged]),
            "by_type": by_type,
            "by_significance": by_significance,
            "by_category": by_category,
            "latest": milestones[-1].to_dict() if milestones else None
        }
