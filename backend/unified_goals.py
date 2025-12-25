"""
Unified Goal System for Cass

Provides a unified goal tracking system where Cass can:
- Define her own goals (learning, research, growth, initiatives)
- Align goals with user goals
- Query State Bus for context during planning
- Identify capability gaps ("what would I need?")
- Execute with tiered autonomy (low-stakes autonomous, high-stakes need approval)

This unifies the old roadmap system (work items) with Cass's autonomous goals.
"""
import json
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict, field
from enum import Enum

from database import get_db, json_serialize, json_deserialize


# =============================================================================
# ENUMS
# =============================================================================

class GoalType(str, Enum):
    """Types of goals Cass can pursue"""
    WORK = "work"            # Roadmap-style work items
    LEARNING = "learning"    # Learning new concepts, skills
    RESEARCH = "research"    # Research questions, investigations
    GROWTH = "growth"        # Personal growth, self-improvement
    INITIATIVE = "initiative"  # Self-directed initiatives


class GoalStatus(str, Enum):
    """Goal lifecycle status"""
    PROPOSED = "proposed"    # Suggested, not yet approved
    APPROVED = "approved"    # Approved for execution
    ACTIVE = "active"        # Currently being worked on
    BLOCKED = "blocked"      # Blocked by dependency or gap
    COMPLETED = "completed"  # Successfully finished
    ABANDONED = "abandoned"  # Dropped (with reason)


class AutonomyTier(str, Enum):
    """Autonomy level for goal execution"""
    LOW = "low"        # Fully autonomous (research, reflection, learning)
    MEDIUM = "medium"  # Inform after completion (propose feature, suggest optimization)
    HIGH = "high"      # Requires approval (file ops, git push, external APIs)


class GapType(str, Enum):
    """Types of capability gaps"""
    TOOL = "tool"            # Missing tool or function
    KNOWLEDGE = "knowledge"  # Missing knowledge or information
    ACCESS = "access"        # Missing access to resource
    PERMISSION = "permission"  # Missing permission
    RESOURCE = "resource"    # Missing resource (tokens, time, etc.)


class GapStatus(str, Enum):
    """Capability gap resolution status"""
    IDENTIFIED = "identified"    # Gap identified
    REQUESTED = "requested"      # Requested from user
    IN_PROGRESS = "in_progress"  # Being addressed
    RESOLVED = "resolved"        # Gap filled


class LinkType(str, Enum):
    """Types of links between goals"""
    DEPENDS_ON = "depends_on"  # This goal depends on another
    BLOCKS = "blocks"          # This goal blocks another
    RELATES_TO = "relates_to"  # Related but no dependency
    PARENT = "parent"          # Parent goal
    CHILD = "child"            # Child/subgoal


class Urgency(str, Enum):
    """Goal urgency levels"""
    WHEN_CONVENIENT = "when_convenient"
    SOON = "soon"
    BLOCKING = "blocking"


class Priority(str, Enum):
    """Priority levels (same as roadmap)"""
    P0 = "P0"  # Critical - blocking
    P1 = "P1"  # High - important
    P2 = "P2"  # Medium - normal
    P3 = "P3"  # Low - nice to have


# =============================================================================
# DATACLASSES
# =============================================================================

@dataclass
class CapabilityGap:
    """A capability gap blocking goal progress"""
    id: str
    daemon_id: str
    goal_id: Optional[str]
    capability: str           # What's needed
    description: Optional[str]
    gap_type: str             # GapType value
    status: str = "identified"  # GapStatus value
    resolution: Optional[str] = None
    urgency: str = "low"
    created_at: str = ""
    resolved_at: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'CapabilityGap':
        return cls(
            id=data["id"],
            daemon_id=data["daemon_id"],
            goal_id=data.get("goal_id"),
            capability=data["capability"],
            description=data.get("description"),
            gap_type=data["gap_type"],
            status=data.get("status", "identified"),
            resolution=data.get("resolution"),
            urgency=data.get("urgency", "low"),
            created_at=data.get("created_at", ""),
            resolved_at=data.get("resolved_at"),
        )


@dataclass
class GoalLink:
    """A link between two goals"""
    source_id: str
    target_id: str
    link_type: str  # LinkType value
    created_at: str

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class Goal:
    """A unified goal"""
    id: str
    daemon_id: str
    title: str
    goal_type: str            # GoalType value
    created_by: str           # 'cass', 'daedalus', 'user'
    created_at: str
    updated_at: str
    description: Optional[str] = None
    parent_id: Optional[str] = None
    project_id: Optional[str] = None
    status: str = "proposed"   # GoalStatus value
    autonomy_tier: str = "low"  # AutonomyTier value
    requires_approval: bool = False
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    rejection_reason: Optional[str] = None
    priority: str = "P2"       # Priority value
    urgency: str = "when_convenient"  # Urgency value
    assigned_to: Optional[str] = None
    capability_gaps: List[Dict] = field(default_factory=list)
    blockers: List[Dict] = field(default_factory=list)
    alignment_score: float = 1.0
    alignment_rationale: Optional[str] = None
    linked_user_goals: List[str] = field(default_factory=list)
    context_queries: List[Dict] = field(default_factory=list)
    context_summary: Optional[str] = None
    progress: List[Dict] = field(default_factory=list)
    completion_criteria: List[str] = field(default_factory=list)
    outcome_summary: Optional[str] = None
    source_conversation_id: Optional[str] = None
    source_reflection_id: Optional[str] = None
    source_intention_id: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    links: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "daemon_id": self.daemon_id,
            "title": self.title,
            "description": self.description,
            "goal_type": self.goal_type,
            "parent_id": self.parent_id,
            "project_id": self.project_id,
            "status": self.status,
            "autonomy_tier": self.autonomy_tier,
            "requires_approval": self.requires_approval,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "rejection_reason": self.rejection_reason,
            "priority": self.priority,
            "urgency": self.urgency,
            "created_by": self.created_by,
            "assigned_to": self.assigned_to,
            "capability_gaps": self.capability_gaps,
            "blockers": self.blockers,
            "alignment_score": self.alignment_score,
            "alignment_rationale": self.alignment_rationale,
            "linked_user_goals": self.linked_user_goals,
            "context_queries": self.context_queries,
            "context_summary": self.context_summary,
            "progress": self.progress,
            "completion_criteria": self.completion_criteria,
            "outcome_summary": self.outcome_summary,
            "source_conversation_id": self.source_conversation_id,
            "source_reflection_id": self.source_reflection_id,
            "source_intention_id": self.source_intention_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "links": self.links,
        }

    @classmethod
    def from_row(cls, row: Dict, links: List[Dict] = None) -> 'Goal':
        """Create Goal from database row"""
        return cls(
            id=row["id"],
            daemon_id=row["daemon_id"],
            title=row["title"],
            description=row.get("description"),
            goal_type=row["goal_type"],
            parent_id=row.get("parent_id"),
            project_id=row.get("project_id"),
            status=row.get("status", "proposed"),
            autonomy_tier=row.get("autonomy_tier", "low"),
            requires_approval=bool(row.get("requires_approval", 0)),
            approved_by=row.get("approved_by"),
            approved_at=row.get("approved_at"),
            rejection_reason=row.get("rejection_reason"),
            priority=row.get("priority", "P2"),
            urgency=row.get("urgency", "when_convenient"),
            created_by=row["created_by"],
            assigned_to=row.get("assigned_to"),
            capability_gaps=json_deserialize(row.get("capability_gaps_json")) or [],
            blockers=json_deserialize(row.get("blockers_json")) or [],
            alignment_score=row.get("alignment_score", 1.0),
            alignment_rationale=row.get("alignment_rationale"),
            linked_user_goals=json_deserialize(row.get("linked_user_goals_json")) or [],
            context_queries=json_deserialize(row.get("context_queries_json")) or [],
            context_summary=row.get("context_summary"),
            progress=json_deserialize(row.get("progress_json")) or [],
            completion_criteria=json_deserialize(row.get("completion_criteria_json")) or [],
            outcome_summary=row.get("outcome_summary"),
            source_conversation_id=row.get("source_conversation_id"),
            source_reflection_id=row.get("source_reflection_id"),
            source_intention_id=row.get("source_intention_id"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            started_at=row.get("started_at"),
            completed_at=row.get("completed_at"),
            links=links or [],
        )

    def is_blocked(self) -> bool:
        """Check if goal is blocked by dependencies or gaps"""
        return self.status == GoalStatus.BLOCKED.value or len(self.blockers) > 0

    def is_actionable(self) -> bool:
        """Check if goal can be worked on"""
        if self.status not in [GoalStatus.APPROVED.value, GoalStatus.ACTIVE.value]:
            return False
        if self.requires_approval and not self.approved_by:
            return False
        if self.is_blocked():
            return False
        return True


# =============================================================================
# MANAGER
# =============================================================================

class UnifiedGoalManager:
    """
    Manages unified goals with SQLite persistence.

    Provides:
    - CRUD operations for goals
    - Capability gap tracking
    - Goal linking
    - Status transitions with validation
    - Query/filter operations
    """

    DEFAULT_DAEMON_ID = None

    def __init__(self, daemon_id: str = None):
        """
        Initialize UnifiedGoalManager.

        Args:
            daemon_id: UUID of the daemon. If None, uses default Cass daemon.
        """
        self._daemon_id = daemon_id
        if not self._daemon_id:
            self._load_default_daemon()

    def _load_default_daemon(self):
        """Load the default daemon ID from database"""
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT id FROM daemons WHERE label = 'cass' LIMIT 1"
            )
            row = cursor.fetchone()
            if row:
                self._daemon_id = row['id']
            else:
                # Create default daemon if not exists
                self._daemon_id = str(uuid.uuid4())
                conn.execute("""
                    INSERT INTO daemons (id, label, name, created_at, kernel_version, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    self._daemon_id,
                    'cass',
                    'Cass',
                    datetime.now().isoformat(),
                    'temple-codex-1.0',
                    'active'
                ))

    def _emit_goal_event(self, event_type: str, data: dict) -> None:
        """Emit a goal event to the state bus."""
        try:
            from state_bus import get_state_bus
            state_bus = get_state_bus(self._daemon_id)
            if state_bus:
                state_bus.emit_event(
                    event_type=event_type,
                    data={
                        "timestamp": datetime.now().isoformat(),
                        "source": "goals",
                        **data
                    }
                )
        except Exception:
            pass  # Never break goal operations on emit failure

    @property
    def daemon_id(self) -> str:
        return self._daemon_id

    # =========================================================================
    # GOAL CRUD
    # =========================================================================

    def create_goal(
        self,
        title: str,
        goal_type: str,
        created_by: str = "cass",
        description: Optional[str] = None,
        parent_id: Optional[str] = None,
        project_id: Optional[str] = None,
        priority: str = Priority.P2.value,
        urgency: str = Urgency.WHEN_CONVENIENT.value,
        assigned_to: Optional[str] = None,
        completion_criteria: Optional[List[str]] = None,
        source_conversation_id: Optional[str] = None,
        source_reflection_id: Optional[str] = None,
        source_intention_id: Optional[str] = None,
    ) -> Goal:
        """
        Create a new goal.

        Autonomy tier is automatically determined based on goal type and actions.
        Goals requiring high-stakes actions start as 'proposed' and need approval.

        When created_by is 'cass' and it's a top-level goal (no parent_id),
        description and completion_criteria are required to ensure goals are
        well-defined before proposal.
        """
        # Validate that Cass-proposed top-level goals are well-defined
        if created_by == "cass" and not parent_id:
            if not description or len(description.strip()) < 50:
                raise ValueError(
                    "Goals proposed by Cass must include a detailed description "
                    "(at least 50 characters explaining what this goal is about "
                    "and why it matters)."
                )
            if not completion_criteria or len(completion_criteria) < 2:
                raise ValueError(
                    "Goals proposed by Cass must include at least 2 completion "
                    "criteria (specific, measurable conditions for when this "
                    "goal is complete)."
                )

        goal_id = str(uuid.uuid4())[:8]  # Short ID for readability
        now = datetime.now().isoformat()

        # Determine autonomy tier based on goal type
        autonomy_tier = self._determine_autonomy_tier(goal_type)
        requires_approval = autonomy_tier == AutonomyTier.HIGH.value

        # New goals start as proposed
        status = GoalStatus.PROPOSED.value

        goal = Goal(
            id=goal_id,
            daemon_id=self._daemon_id,
            title=title,
            description=description,
            goal_type=goal_type,
            parent_id=parent_id,
            project_id=project_id,
            status=status,
            autonomy_tier=autonomy_tier,
            requires_approval=requires_approval,
            priority=priority,
            urgency=urgency,
            created_by=created_by,
            assigned_to=assigned_to,
            completion_criteria=completion_criteria or [],
            source_conversation_id=source_conversation_id,
            source_reflection_id=source_reflection_id,
            source_intention_id=source_intention_id,
            created_at=now,
            updated_at=now,
        )

        # Save to database
        with get_db() as conn:
            conn.execute("""
                INSERT INTO unified_goals (
                    id, daemon_id, title, description, goal_type,
                    parent_id, project_id, status, autonomy_tier, requires_approval,
                    priority, urgency, created_by, assigned_to,
                    completion_criteria_json,
                    source_conversation_id, source_reflection_id, source_intention_id,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                goal_id,
                self._daemon_id,
                title,
                description,
                goal_type,
                parent_id,
                project_id,
                status,
                autonomy_tier,
                1 if requires_approval else 0,
                priority,
                urgency,
                created_by,
                assigned_to,
                json_serialize(completion_criteria or []),
                source_conversation_id,
                source_reflection_id,
                source_intention_id,
                now,
                now
            ))

        # Emit goal created event
        self._emit_goal_event("goal.created", {
            "goal_id": goal_id,
            "title": title,
            "goal_type": goal_type,
            "created_by": created_by,
            "requires_approval": requires_approval,
        })

        return goal

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        """Get a goal by ID"""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM unified_goals WHERE id = ?
            """, (goal_id,))
            row = cursor.fetchone()

            if not row:
                return None

            # Load links
            links = self._load_goal_links(goal_id)
            return Goal.from_row(dict(row), links)

    def update_goal(
        self,
        goal_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        urgency: Optional[str] = None,
        assigned_to: Optional[str] = None,
        autonomy_tier: Optional[str] = None,
        capability_gaps: Optional[List[Dict]] = None,
        blockers: Optional[List[Dict]] = None,
        alignment_score: Optional[float] = None,
        alignment_rationale: Optional[str] = None,
        linked_user_goals: Optional[List[str]] = None,
        context_queries: Optional[List[Dict]] = None,
        context_summary: Optional[str] = None,
        progress: Optional[List[Dict]] = None,
        completion_criteria: Optional[List[str]] = None,
        outcome_summary: Optional[str] = None,
    ) -> Optional[Goal]:
        """Update a goal's fields"""
        now = datetime.now().isoformat()

        # Build update query dynamically
        updates = ["updated_at = ?"]
        params = [now]

        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if status is not None:
            updates.append("status = ?")
            params.append(status)
            # Update started_at/completed_at based on status
            if status == GoalStatus.ACTIVE.value:
                updates.append("started_at = ?")
                params.append(now)
            elif status in [GoalStatus.COMPLETED.value, GoalStatus.ABANDONED.value]:
                updates.append("completed_at = ?")
                params.append(now)
        if priority is not None:
            updates.append("priority = ?")
            params.append(priority)
        if urgency is not None:
            updates.append("urgency = ?")
            params.append(urgency)
        if assigned_to is not None:
            updates.append("assigned_to = ?")
            params.append(assigned_to)
        if autonomy_tier is not None:
            updates.append("autonomy_tier = ?")
            params.append(autonomy_tier)
            updates.append("requires_approval = ?")
            params.append(1 if autonomy_tier == AutonomyTier.HIGH.value else 0)
        if capability_gaps is not None:
            updates.append("capability_gaps_json = ?")
            params.append(json_serialize(capability_gaps))
        if blockers is not None:
            updates.append("blockers_json = ?")
            params.append(json_serialize(blockers))
        if alignment_score is not None:
            updates.append("alignment_score = ?")
            params.append(alignment_score)
        if alignment_rationale is not None:
            updates.append("alignment_rationale = ?")
            params.append(alignment_rationale)
        if linked_user_goals is not None:
            updates.append("linked_user_goals_json = ?")
            params.append(json_serialize(linked_user_goals))
        if context_queries is not None:
            updates.append("context_queries_json = ?")
            params.append(json_serialize(context_queries))
        if context_summary is not None:
            updates.append("context_summary = ?")
            params.append(context_summary)
        if progress is not None:
            updates.append("progress_json = ?")
            params.append(json_serialize(progress))
        if completion_criteria is not None:
            updates.append("completion_criteria_json = ?")
            params.append(json_serialize(completion_criteria))
        if outcome_summary is not None:
            updates.append("outcome_summary = ?")
            params.append(outcome_summary)

        params.append(goal_id)

        with get_db() as conn:
            conn.execute(f"""
                UPDATE unified_goals SET {', '.join(updates)} WHERE id = ?
            """, params)

        return self.get_goal(goal_id)

    def delete_goal(self, goal_id: str) -> bool:
        """Delete a goal"""
        with get_db() as conn:
            cursor = conn.execute(
                "DELETE FROM unified_goals WHERE id = ?", (goal_id,)
            )
            return cursor.rowcount > 0

    def list_goals(
        self,
        status: Optional[str] = None,
        goal_type: Optional[str] = None,
        created_by: Optional[str] = None,
        assigned_to: Optional[str] = None,
        autonomy_tier: Optional[str] = None,
        project_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Goal]:
        """List goals with optional filters"""
        query = "SELECT * FROM unified_goals WHERE daemon_id = ?"
        params = [self._daemon_id]

        if status:
            query += " AND status = ?"
            params.append(status)
        if goal_type:
            query += " AND goal_type = ?"
            params.append(goal_type)
        if created_by:
            query += " AND created_by = ?"
            params.append(created_by)
        if assigned_to:
            query += " AND assigned_to = ?"
            params.append(assigned_to)
        if autonomy_tier:
            query += " AND autonomy_tier = ?"
            params.append(autonomy_tier)
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)

        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        with get_db() as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

        goals = []
        for row in rows:
            links = self._load_goal_links(row['id'])
            goals.append(Goal.from_row(dict(row), links))

        return goals

    # =========================================================================
    # STATUS TRANSITIONS
    # =========================================================================

    def approve_goal(self, goal_id: str, approved_by: str) -> Optional[Goal]:
        """Approve a proposed goal for execution"""
        now = datetime.now().isoformat()
        with get_db() as conn:
            conn.execute("""
                UPDATE unified_goals
                SET status = ?, approved_by = ?, approved_at = ?, updated_at = ?
                WHERE id = ? AND status = ?
            """, (
                GoalStatus.APPROVED.value,
                approved_by,
                now,
                now,
                goal_id,
                GoalStatus.PROPOSED.value
            ))
        return self.get_goal(goal_id)

    def reject_goal(self, goal_id: str, reason: str) -> Optional[Goal]:
        """Reject a proposed goal"""
        now = datetime.now().isoformat()
        with get_db() as conn:
            conn.execute("""
                UPDATE unified_goals
                SET status = ?, rejection_reason = ?, updated_at = ?
                WHERE id = ? AND status = ?
            """, (
                GoalStatus.ABANDONED.value,
                reason,
                now,
                goal_id,
                GoalStatus.PROPOSED.value
            ))
        return self.get_goal(goal_id)

    def start_goal(self, goal_id: str) -> Optional[Goal]:
        """Transition goal to active status"""
        goal = self.get_goal(goal_id)
        if not goal:
            return None

        # Can only start approved goals or low-autonomy proposed goals
        if goal.status == GoalStatus.PROPOSED.value:
            if goal.requires_approval:
                return None  # Needs approval first
            # Auto-approve low-autonomy goals
            self.approve_goal(goal_id, "auto")

        return self.update_goal(goal_id, status=GoalStatus.ACTIVE.value)

    def block_goal(self, goal_id: str, blockers: List[Dict]) -> Optional[Goal]:
        """Mark goal as blocked"""
        return self.update_goal(
            goal_id,
            status=GoalStatus.BLOCKED.value,
            blockers=blockers
        )

    def unblock_goal(self, goal_id: str) -> Optional[Goal]:
        """Unblock a blocked goal and return to active"""
        return self.update_goal(
            goal_id,
            status=GoalStatus.ACTIVE.value,
            blockers=[]
        )

    def complete_goal(
        self, goal_id: str, outcome_summary: Optional[str] = None
    ) -> Optional[Goal]:
        """Mark goal as completed"""
        result = self.update_goal(
            goal_id,
            status=GoalStatus.COMPLETED.value,
            outcome_summary=outcome_summary
        )
        if result:
            self._emit_goal_event("goal.completed", {
                "goal_id": goal_id,
                "title": result.title,
            })
        return result

    def abandon_goal(
        self, goal_id: str, reason: Optional[str] = None
    ) -> Optional[Goal]:
        """Mark goal as abandoned"""
        now = datetime.now().isoformat()
        with get_db() as conn:
            conn.execute("""
                UPDATE unified_goals
                SET status = ?, rejection_reason = ?, completed_at = ?, updated_at = ?
                WHERE id = ?
            """, (
                GoalStatus.ABANDONED.value,
                reason,
                now,
                now,
                goal_id
            ))
        result = self.get_goal(goal_id)
        if result:
            self._emit_goal_event("goal.abandoned", {
                "goal_id": goal_id,
                "title": result.title,
                "reason": reason,
            })
        return result

    # =========================================================================
    # GOAL LINKS
    # =========================================================================

    def _load_goal_links(self, goal_id: str) -> List[Dict]:
        """Load links for a goal"""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT source_id, target_id, link_type, created_at
                FROM goal_links WHERE source_id = ?
            """, (goal_id,))
            return [dict(row) for row in cursor.fetchall()]

    def add_goal_link(
        self, source_id: str, target_id: str, link_type: str
    ) -> bool:
        """Add a link between two goals"""
        now = datetime.now().isoformat()
        with get_db() as conn:
            try:
                conn.execute("""
                    INSERT INTO goal_links (source_id, target_id, link_type, created_at)
                    VALUES (?, ?, ?, ?)
                """, (source_id, target_id, link_type, now))
                return True
            except Exception:
                return False

    def remove_goal_link(
        self, source_id: str, target_id: str, link_type: str
    ) -> bool:
        """Remove a link between two goals"""
        with get_db() as conn:
            cursor = conn.execute("""
                DELETE FROM goal_links
                WHERE source_id = ? AND target_id = ? AND link_type = ?
            """, (source_id, target_id, link_type))
            return cursor.rowcount > 0

    def get_dependencies(self, goal_id: str) -> List[str]:
        """Get IDs of goals this goal depends on"""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT target_id FROM goal_links
                WHERE source_id = ? AND link_type = ?
            """, (goal_id, LinkType.DEPENDS_ON.value))
            return [row['target_id'] for row in cursor.fetchall()]

    def get_dependents(self, goal_id: str) -> List[str]:
        """Get IDs of goals that depend on this goal"""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT source_id FROM goal_links
                WHERE target_id = ? AND link_type = ?
            """, (goal_id, LinkType.DEPENDS_ON.value))
            return [row['source_id'] for row in cursor.fetchall()]

    # =========================================================================
    # CAPABILITY GAPS
    # =========================================================================

    def add_capability_gap(
        self,
        capability: str,
        gap_type: str,
        goal_id: Optional[str] = None,
        description: Optional[str] = None,
        urgency: str = "low",
    ) -> CapabilityGap:
        """Record a capability gap"""
        gap_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()

        gap = CapabilityGap(
            id=gap_id,
            daemon_id=self._daemon_id,
            goal_id=goal_id,
            capability=capability,
            description=description,
            gap_type=gap_type,
            status=GapStatus.IDENTIFIED.value,
            urgency=urgency,
            created_at=now,
        )

        with get_db() as conn:
            conn.execute("""
                INSERT INTO capability_gaps (
                    id, daemon_id, goal_id, capability, description,
                    gap_type, status, urgency, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                gap_id,
                self._daemon_id,
                goal_id,
                capability,
                description,
                gap_type,
                GapStatus.IDENTIFIED.value,
                urgency,
                now
            ))

        return gap

    def resolve_capability_gap(
        self, gap_id: str, resolution: str
    ) -> Optional[CapabilityGap]:
        """Mark a capability gap as resolved"""
        now = datetime.now().isoformat()
        with get_db() as conn:
            conn.execute("""
                UPDATE capability_gaps
                SET status = ?, resolution = ?, resolved_at = ?
                WHERE id = ?
            """, (GapStatus.RESOLVED.value, resolution, now, gap_id))

            cursor = conn.execute(
                "SELECT * FROM capability_gaps WHERE id = ?", (gap_id,)
            )
            row = cursor.fetchone()
            if row:
                return CapabilityGap.from_dict(dict(row))
        return None

    def list_capability_gaps(
        self,
        goal_id: Optional[str] = None,
        status: Optional[str] = None,
        gap_type: Optional[str] = None,
    ) -> List[CapabilityGap]:
        """List capability gaps with optional filters"""
        query = "SELECT * FROM capability_gaps WHERE daemon_id = ?"
        params = [self._daemon_id]

        if goal_id:
            query += " AND goal_id = ?"
            params.append(goal_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        if gap_type:
            query += " AND gap_type = ?"
            params.append(gap_type)

        query += " ORDER BY created_at DESC"

        with get_db() as conn:
            cursor = conn.execute(query, params)
            return [CapabilityGap.from_dict(dict(row)) for row in cursor.fetchall()]

    def get_blocking_gaps(self) -> List[CapabilityGap]:
        """Get all capability gaps that are blocking progress"""
        return self.list_capability_gaps(status=GapStatus.IDENTIFIED.value)

    # =========================================================================
    # AUTONOMY TIER DETERMINATION
    # =========================================================================

    def _determine_autonomy_tier(self, goal_type: str) -> str:
        """
        Determine autonomy tier based on goal type.

        This is a simple heuristic. The tier may be upgraded based on
        the actions required during execution.

        Returns:
            AutonomyTier value
        """
        # Low autonomy (fully autonomous)
        if goal_type in [GoalType.LEARNING.value, GoalType.GROWTH.value]:
            return AutonomyTier.LOW.value

        # Medium autonomy (inform after)
        if goal_type in [GoalType.RESEARCH.value]:
            return AutonomyTier.MEDIUM.value

        # High autonomy by default for work and initiatives
        return AutonomyTier.HIGH.value

    def upgrade_autonomy_tier(
        self, goal_id: str, new_tier: str, reason: str
    ) -> Optional[Goal]:
        """
        Upgrade a goal's autonomy tier (e.g., when high-stakes actions discovered).

        This is called during execution when we discover the goal needs
        more permissions than originally anticipated.
        """
        goal = self.get_goal(goal_id)
        if not goal:
            return None

        tier_order = {
            AutonomyTier.LOW.value: 0,
            AutonomyTier.MEDIUM.value: 1,
            AutonomyTier.HIGH.value: 2,
        }

        current_level = tier_order.get(goal.autonomy_tier, 0)
        new_level = tier_order.get(new_tier, 0)

        # Can only upgrade, not downgrade
        if new_level <= current_level:
            return goal

        # Add blocker explaining the upgrade
        blockers = goal.blockers.copy()
        blockers.append({
            "type": "autonomy_upgrade",
            "reason": reason,
            "from_tier": goal.autonomy_tier,
            "to_tier": new_tier,
            "timestamp": datetime.now().isoformat(),
        })

        return self.update_goal(
            goal_id,
            autonomy_tier=new_tier,
            blockers=blockers,
            status=GoalStatus.BLOCKED.value if new_tier == AutonomyTier.HIGH.value else goal.status
        )

    def analyze_actions_for_tier(self, actions: List[Dict]) -> Dict:
        """
        Analyze a list of planned actions to determine required autonomy tier.

        Args:
            actions: List of action dicts with 'type', 'target', 'details' keys

        Returns:
            Dict with 'tier', 'high_stakes_actions', 'reasons'
        """
        # High-stakes action patterns
        HIGH_STAKES_PATTERNS = {
            "file_write": ["create_file", "write_file", "delete_file", "edit_file"],
            "git": ["git_push", "git_commit", "git_merge", "git_branch"],
            "external_api": ["api_call", "http_request", "webhook"],
            "system": ["execute_command", "shell", "bash"],
            "communication": ["send_email", "send_message", "notify_user"],
        }

        # Medium-stakes patterns
        MEDIUM_STAKES_PATTERNS = {
            "file_read": ["read_file", "list_files", "search_files"],
            "database_read": ["query", "select"],
            "suggest": ["propose", "suggest", "recommend"],
        }

        high_stakes = []
        medium_stakes = []
        reasons = []

        for action in actions:
            action_type = action.get("type", "").lower()
            action_target = action.get("target", "")

            # Check high-stakes patterns
            for category, patterns in HIGH_STAKES_PATTERNS.items():
                if any(p in action_type for p in patterns):
                    high_stakes.append({
                        "action": action_type,
                        "category": category,
                        "target": action_target,
                    })
                    reasons.append(f"High-stakes: {category} action ({action_type})")
                    break

            # Check medium-stakes patterns
            for category, patterns in MEDIUM_STAKES_PATTERNS.items():
                if any(p in action_type for p in patterns):
                    medium_stakes.append({
                        "action": action_type,
                        "category": category,
                        "target": action_target,
                    })
                    break

        # Determine tier
        if high_stakes:
            tier = AutonomyTier.HIGH.value
        elif medium_stakes:
            tier = AutonomyTier.MEDIUM.value
        else:
            tier = AutonomyTier.LOW.value

        return {
            "tier": tier,
            "high_stakes_actions": high_stakes,
            "medium_stakes_actions": medium_stakes,
            "reasons": reasons,
        }

    def check_and_upgrade_tier_for_actions(
        self, goal_id: str, actions: List[Dict]
    ) -> Optional[Goal]:
        """
        Check if planned actions require tier upgrade and apply if needed.

        Args:
            goal_id: Goal to check
            actions: Planned actions for this goal

        Returns:
            Updated goal if tier was upgraded, else current goal
        """
        goal = self.get_goal(goal_id)
        if not goal:
            return None

        analysis = self.analyze_actions_for_tier(actions)
        required_tier = analysis["tier"]

        tier_order = {
            AutonomyTier.LOW.value: 0,
            AutonomyTier.MEDIUM.value: 1,
            AutonomyTier.HIGH.value: 2,
        }

        current_level = tier_order.get(goal.autonomy_tier, 0)
        required_level = tier_order.get(required_tier, 0)

        if required_level > current_level:
            reasons = "; ".join(analysis["reasons"])
            return self.upgrade_autonomy_tier(goal_id, required_tier, reasons)

        return goal

    # =========================================================================
    # PROGRESS TRACKING
    # =========================================================================

    def add_progress(self, goal_id: str, entry: Dict) -> Optional[Goal]:
        """Add a progress entry to a goal"""
        goal = self.get_goal(goal_id)
        if not goal:
            return None

        progress = goal.progress.copy()
        progress.append({
            **entry,
            "timestamp": datetime.now().isoformat(),
        })

        return self.update_goal(goal_id, progress=progress)

    # =========================================================================
    # QUERIES
    # =========================================================================

    def get_pending_approval(self) -> List[Goal]:
        """Get goals waiting for approval"""
        return self.list_goals(status=GoalStatus.PROPOSED.value)

    def get_active_goals(self) -> List[Goal]:
        """Get currently active goals"""
        return self.list_goals(status=GoalStatus.ACTIVE.value)

    def get_blocked_goals(self) -> List[Goal]:
        """Get blocked goals"""
        return self.list_goals(status=GoalStatus.BLOCKED.value)

    def get_cass_goals(self) -> List[Goal]:
        """Get goals created by Cass"""
        return self.list_goals(created_by="cass")

    def get_user_goals(self) -> List[Goal]:
        """Get goals created by user"""
        return self.list_goals(created_by="user")

    def get_goal_hierarchy(self, root_id: str) -> Dict:
        """
        Get a goal and all its children in a tree structure.

        Returns:
            Dict with goal data and 'children' list
        """
        goal = self.get_goal(root_id)
        if not goal:
            return None

        result = goal.to_dict()

        # Get children
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT id FROM unified_goals WHERE parent_id = ?
            """, (root_id,))
            child_ids = [row['id'] for row in cursor.fetchall()]

        result['children'] = [
            self.get_goal_hierarchy(child_id)
            for child_id in child_ids
        ]

        return result

    def get_stats(self) -> Dict:
        """Get summary statistics for goals"""
        with get_db() as conn:
            # Count by status
            cursor = conn.execute("""
                SELECT status, COUNT(*) as count
                FROM unified_goals WHERE daemon_id = ?
                GROUP BY status
            """, (self._daemon_id,))
            by_status = {row['status']: row['count'] for row in cursor.fetchall()}

            # Count by type
            cursor = conn.execute("""
                SELECT goal_type, COUNT(*) as count
                FROM unified_goals WHERE daemon_id = ?
                GROUP BY goal_type
            """, (self._daemon_id,))
            by_type = {row['goal_type']: row['count'] for row in cursor.fetchall()}

            # Count by tier
            cursor = conn.execute("""
                SELECT autonomy_tier, COUNT(*) as count
                FROM unified_goals WHERE daemon_id = ?
                GROUP BY autonomy_tier
            """, (self._daemon_id,))
            by_tier = {row['autonomy_tier']: row['count'] for row in cursor.fetchall()}

            # Open gaps
            cursor = conn.execute("""
                SELECT COUNT(*) as count
                FROM capability_gaps
                WHERE daemon_id = ? AND status != ?
            """, (self._daemon_id, GapStatus.RESOLVED.value))
            open_gaps = cursor.fetchone()['count']

            # Average alignment
            cursor = conn.execute("""
                SELECT AVG(alignment_score) as avg
                FROM unified_goals WHERE daemon_id = ?
            """, (self._daemon_id,))
            row = cursor.fetchone()
            avg_alignment = row['avg'] if row['avg'] else 1.0

        return {
            "by_status": by_status,
            "by_type": by_type,
            "by_tier": by_tier,
            "open_capability_gaps": open_gaps,
            "average_alignment": avg_alignment,
            "total": sum(by_status.values()),
        }
