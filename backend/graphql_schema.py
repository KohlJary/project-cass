"""
GraphQL Schema for Cass Vessel

Provides a unified query interface wrapping the State Bus.
Each source becomes a GraphQL type with its metrics as fields.

Usage:
    query {
        goals { active, blocked, pendingApproval }
        tokens { todayCost, monthCost }
        github { stars, commits }
        state { activity { current, rhythmPhase } }
    }
"""

import strawberry
from strawberry.fastapi import GraphQLRouter
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from state_bus import get_state_bus
from database import get_daemon_id
from peopledex import (
    get_peopledex_manager,
    EntityType as PDEntityType,
    AttributeType as PDAttributeType,
    RelationshipType as PDRelationshipType,
    Realm as PDRealm,
)

logger = logging.getLogger(__name__)


# =============================================================================
# GOALS TYPES
# =============================================================================

@strawberry.type
class GoalStats:
    total: int
    active: int
    blocked: int
    pending_approval: int
    completed: int
    abandoned: int
    open_capability_gaps: int
    average_alignment: float

    @strawberry.field
    def completion_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.completed / self.total) * 100


@strawberry.type
class GoalsByStatus:
    proposed: int
    approved: int
    active: int
    blocked: int
    completed: int
    abandoned: int


@strawberry.type
class GoalsByType:
    work: int
    learning: int
    research: int
    growth: int
    initiative: int


@strawberry.type
class Goals:
    stats: GoalStats
    by_status: GoalsByStatus
    by_type: GoalsByType


# =============================================================================
# TOKENS TYPES
# =============================================================================

@strawberry.type
class TokenUsage:
    today_cost_usd: float
    today_input_tokens: int
    today_output_tokens: int
    today_total_tokens: int
    week_cost_usd: float
    month_cost_usd: float
    month_total_tokens: int
    total_cost_usd: float
    total_tokens: int
    total_requests: int


# =============================================================================
# GITHUB TYPES
# =============================================================================

@strawberry.type
class GitHubMetrics:
    stars_total: int
    forks_total: int
    watchers_total: int
    open_issues: int
    clones_14d: int
    views_14d: int
    stars_7d: int
    repos_tracked: int


# =============================================================================
# CONVERSATIONS TYPES
# =============================================================================

@strawberry.type
class ConversationStats:
    total_conversations: int
    conversations_today: int
    conversations_week: int
    total_messages: int
    messages_today: int
    active_users_today: int


@strawberry.type
class ContinuousConversation:
    """The continuous chat stream for a user."""
    conversation_id: str
    user_id: str
    message_count: int
    created_at: str
    updated_at: str
    has_working_summary: bool


# =============================================================================
# MEMORY TYPES
# =============================================================================

@strawberry.type
class MemoryStats:
    total_journals: int
    total_threads: int
    threads_active: int
    total_questions: int
    questions_open: int
    total_embeddings: int


# =============================================================================
# SELF MODEL TYPES
# =============================================================================

@strawberry.type
class SelfModelStats:
    total_nodes: int
    total_edges: int
    observations: int
    opinions: int
    growth_edges: int
    intentions: int


# =============================================================================
# ACTIONS TYPES
# =============================================================================

@strawberry.type
class ActionDefinition:
    """An atomic action definition."""
    id: str
    name: str
    description: str
    category: str
    handler: str
    estimated_cost_usd: float
    default_duration_minutes: int
    priority: str
    requires_idle: bool


@strawberry.type
class ActionCategory:
    """Actions grouped by category."""
    category: str
    count: int
    actions: List[ActionDefinition]


@strawberry.type
class ActionsStats:
    """Summary statistics for all actions."""
    total_actions: int
    category_count: int
    by_category: List[ActionCategory]


# =============================================================================
# WORK PLANNING TYPES (Cass's taskboard and calendar)
# =============================================================================

@strawberry.type
class WorkItemSummary:
    """A work item from Cass's taskboard."""
    id: str
    title: str
    description: Optional[str]
    category: str
    priority: int
    status: str
    estimated_duration_minutes: int
    estimated_cost_usd: float
    requires_approval: bool
    approval_status: str
    goal_id: Optional[str]
    created_at: str


@strawberry.type
class WorkStats:
    """Summary statistics for Cass's work items."""
    total: int
    by_status: strawberry.scalars.JSON
    by_category: strawberry.scalars.JSON
    pending_approval: int
    estimated_pending_cost_usd: float
    actual_completed_cost_usd: float

    @strawberry.field
    def completion_rate(self) -> float:
        by_status = self.by_status if isinstance(self.by_status, dict) else {}
        completed = by_status.get("completed", 0)
        if self.total == 0:
            return 0.0
        return (completed / self.total) * 100


@strawberry.type
class ScheduleSlotSummary:
    """A schedule slot from Cass's calendar."""
    id: str
    work_item_id: Optional[str]
    start_time: Optional[str]
    end_time: Optional[str]
    duration_minutes: int
    priority: int
    status: str
    requires_idle: bool
    notes: Optional[str]


@strawberry.type
class ScheduleStats:
    """Summary statistics for Cass's schedule."""
    total: int
    by_status: strawberry.scalars.JSON
    today_count: int
    week_count: int
    budget_scheduled_usd: float
    flexible_slots: int
    idle_slots: int


@strawberry.type
class WorkPlanning:
    """Cass's work planning state - taskboard and calendar."""
    work_stats: WorkStats
    schedule_stats: ScheduleStats
    pending_approval: List[WorkItemSummary]
    upcoming_slots: List[ScheduleSlotSummary]


# =============================================================================
# STATE TYPES (Emotional, Activity, Coherence)
# =============================================================================

@strawberry.type
class EmotionalState:
    directedness: Optional[str]
    clarity: float
    relational_presence: float
    generativity: float
    integration: float
    curiosity: float
    contentment: float
    anticipation: float
    concern: float
    recognition: float
    last_updated: Optional[str]


@strawberry.type
class ActivityState:
    current: str
    user_id: Optional[str]
    contact_started: Optional[str]  # ISO timestamp when contact began
    messages_this_contact: int
    current_topics: List[str]
    rhythm_phase: Optional[str]
    rhythm_summary: Optional[str]
    active_threads: int
    active_questions: int


@strawberry.type
class CoherenceState:
    local: float
    pattern: float
    sessions_today: int


@strawberry.type
class GlobalState:
    emotional: EmotionalState
    activity: ActivityState
    coherence: CoherenceState


# =============================================================================
# DAILY SUMMARY TYPE (aggregates across sources)
# =============================================================================

@strawberry.type
class DailySummary:
    """Aggregated view of today's activity across all sources."""
    date: str

    # Activity
    conversations_count: int
    messages_count: int

    # Resources
    token_cost_usd: float

    # Goals
    goals_completed: int
    goals_created: int

    # Research/Growth
    journals_written: int

    # GitHub
    commits: int

    # State
    current_activity: str
    rhythm_phase: Optional[str]


# =============================================================================
# WORK SUMMARY TYPES - Autonomous work history
# =============================================================================

@strawberry.type
class ActionSummaryType:
    """Summary of a single action within a work unit."""
    action_id: str
    action_type: str
    slug: str
    summary: str
    started_at: Optional[str]
    completed_at: Optional[str]
    artifacts: List[str]


@strawberry.type
class ArtifactRef:
    """Reference to an artifact created during work."""
    artifact_type: str  # note, insight, journal, observation
    artifact_id: str
    title: Optional[str]


@strawberry.type
class WorkSummaryType:
    """Complete summary of a work unit execution."""
    work_unit_id: str
    slug: str
    name: str
    template_id: Optional[str]
    phase: str  # morning, afternoon, evening, night
    category: str
    focus: Optional[str]
    motivation: Optional[str]
    date: str
    started_at: Optional[str]
    completed_at: Optional[str]
    duration_minutes: int
    summary: str
    key_insights: List[str]
    questions_addressed: List[str]
    questions_raised: List[str]
    action_summaries: List[ActionSummaryType]
    artifacts: strawberry.scalars.JSON  # List of artifact refs
    success: bool
    error: Optional[str]
    cost_usd: float

    @strawberry.field
    def brief(self) -> str:
        """Get a brief one-line description."""
        duration = f"{self.duration_minutes}min" if self.duration_minutes else "?"
        focus_str = f" - {self.focus}" if self.focus else ""
        return f"{self.name} ({duration}){focus_str}"


@strawberry.type
class DayPhaseType:
    """Current day phase information."""
    current_phase: str  # morning, afternoon, evening, night
    phase_started_at: Optional[str]
    next_transition_at: Optional[str]
    recent_work_slugs: List[str]
    todays_work_slugs: List[str]
    work_by_phase: strawberry.scalars.JSON


@strawberry.type
class WorkHistoryStats:
    """Statistics for work history."""
    total_count: int
    total_minutes: int
    by_phase: strawberry.scalars.JSON
    by_category: strawberry.scalars.JSON
    date_range_start: str
    date_range_end: str


# =============================================================================
# AUTONOMOUS SCHEDULE TYPES - Schedule panel data
# =============================================================================

@strawberry.type
class WorkUnitType:
    """A planned or queued work unit (not yet executed)."""
    id: str
    name: str
    template_id: Optional[str]
    category: Optional[str]
    focus: Optional[str]
    motivation: Optional[str]
    estimated_duration_minutes: int
    estimated_cost_usd: float
    status: str  # queued, running, completed, failed


@strawberry.type
class QueuedWorkUnitType:
    """A work unit queued for a specific phase."""
    work_unit: WorkUnitType
    target_phase: str
    queued_at: str
    priority: int


@strawberry.type
class PhaseQueueType:
    """A day phase with its queued work units."""
    phase: str  # morning, afternoon, evening, night
    is_current: bool
    queue_count: int
    work_units: List[QueuedWorkUnitType]


@strawberry.type
class TodaysPlanByPhase:
    """Planned work for a specific phase."""
    phase: str
    work_units: List[WorkUnitType]


@strawberry.type
class TodaysPlanType:
    """Today's full work plan."""
    day_intention: Optional[str]
    planned_at: Optional[str]
    phases: List[TodaysPlanByPhase]
    total_work_units: int


@strawberry.type
class CurrentWorkType:
    """Currently executing work unit."""
    work_unit: WorkUnitType
    started_at: str
    elapsed_minutes: int


@strawberry.type
class AutonomousScheduleState:
    """Full state of the autonomous scheduling system."""
    enabled: bool
    is_working: bool
    current_work: Optional[CurrentWorkType]
    todays_plan: TodaysPlanType
    phase_queues: List[PhaseQueueType]
    daily_summary: strawberry.scalars.JSON


# =============================================================================
# APPROVALS TYPES - Synkratos "what needs attention?"
# =============================================================================

@strawberry.type
class ApprovalItem:
    """An item pending human approval."""
    approval_id: str
    approval_type: str  # goal, research, action, user
    title: str
    description: str
    source_id: str
    created_at: str
    created_by: str
    priority: str  # high, normal, low


@strawberry.type
class ApprovalCounts:
    """Counts by approval type."""
    goal: int
    research: int
    action: int
    user: int
    total: int


@strawberry.type
class Approvals:
    """Pending approvals from Synkratos."""
    items: List[ApprovalItem]
    count: int
    counts: ApprovalCounts


# =============================================================================
# PEOPLEDEX TYPES
# =============================================================================

@strawberry.type
class PeopleDexAttribute:
    """An attribute of a PeopleDex entity."""
    id: str
    entity_id: str
    attribute_type: str  # name, birthday, pronoun, email, phone, handle, role, bio, note, location
    attribute_key: Optional[str]  # For handles: twitter, github, etc.
    value: str
    is_primary: bool
    source_type: Optional[str]
    source_id: Optional[str]
    confidence: float
    created_at: str
    updated_at: str


@strawberry.type
class PeopleDexRelatedEntity:
    """A related entity in a relationship."""
    id: str
    entity_type: str
    primary_name: str
    realm: str


@strawberry.type
class PeopleDexRelationship:
    """A relationship between PeopleDex entities."""
    relationship_id: str
    relationship_type: str  # partner, spouse, parent, child, sibling, friend, colleague, member_of, leads, knows
    relationship_label: Optional[str]
    direction: str  # "to" or "from"
    related_entity: PeopleDexRelatedEntity


@strawberry.type
class PeopleDexEntity:
    """A PeopleDex entity (person, organization, team, daemon)."""
    id: str
    entity_type: str
    primary_name: str
    realm: str  # meatspace or wonderland
    user_id: Optional[str]
    npc_id: Optional[str]
    created_at: str
    updated_at: str


@strawberry.type
class PeopleDexProfile:
    """Full profile of a PeopleDex entity including attributes and relationships."""
    entity: PeopleDexEntity
    attributes: List[PeopleDexAttribute]
    relationships: List[PeopleDexRelationship]


@strawberry.type
class PeopleDexStats:
    """Statistics about the PeopleDex."""
    total_entities: int
    by_type: strawberry.scalars.JSON  # {"person": 10, "organization": 2, ...}
    by_realm: strawberry.scalars.JSON  # {"meatspace": 8, "wonderland": 4}


# =============================================================================
# PEOPLEDEX INPUT TYPES
# =============================================================================

@strawberry.input
class CreateEntityInput:
    """Input for creating a new entity."""
    entity_type: str  # person, organization, team, daemon
    primary_name: str
    realm: str = "meatspace"
    user_id: Optional[str] = None
    npc_id: Optional[str] = None


@strawberry.input
class UpdateEntityInput:
    """Input for updating an entity."""
    primary_name: Optional[str] = None
    entity_type: Optional[str] = None


@strawberry.input
class AddAttributeInput:
    """Input for adding an attribute."""
    attribute_type: str  # name, birthday, pronoun, email, phone, handle, role, bio, note, location
    value: str
    attribute_key: Optional[str] = None  # For handles: twitter, github, etc.
    is_primary: bool = False
    source_type: Optional[str] = "admin_corrected"


@strawberry.input
class UpdateAttributeInput:
    """Input for updating an attribute."""
    value: Optional[str] = None
    is_primary: Optional[bool] = None
    source_type: Optional[str] = None
    confidence: Optional[float] = None


@strawberry.input
class AddRelationshipInput:
    """Input for adding a relationship."""
    from_entity_id: str
    to_entity_id: str
    relationship_type: str  # partner, spouse, parent, child, sibling, friend, colleague, member_of, leads, knows
    relationship_label: Optional[str] = None
    source_type: Optional[str] = "admin_corrected"


@strawberry.input
class MergeEntitiesInput:
    """Input for merging two entities."""
    keep_id: str  # Entity to keep
    merge_id: str  # Entity to merge into keep_id (will be deleted)


# =============================================================================
# ROOT QUERY
# =============================================================================

def get_daemon_state_bus():
    """Get the state bus for the current daemon."""
    daemon_id = get_daemon_id()
    return get_state_bus(daemon_id)


@strawberry.type
class Query:
    @strawberry.field
    async def goals(self) -> Goals:
        """Get unified goal statistics."""
        bus = get_daemon_state_bus()

        try:
            from query_models import StateQuery
            query = StateQuery(source="goals", metric="all")
            result = await bus.query(query)

            data = result.metadata if result.metadata else {}
            by_status = data.get("by_status", {})
            by_type = data.get("by_type", {})

            return Goals(
                stats=GoalStats(
                    total=data.get("total_goals", 0),
                    active=by_status.get("active", 0),
                    blocked=by_status.get("blocked", 0),
                    pending_approval=by_status.get("proposed", 0),
                    completed=by_status.get("completed", 0),
                    abandoned=by_status.get("abandoned", 0),
                    open_capability_gaps=data.get("open_capability_gaps", 0),
                    average_alignment=data.get("average_alignment", 1.0),
                ),
                by_status=GoalsByStatus(
                    proposed=by_status.get("proposed", 0),
                    approved=by_status.get("approved", 0),
                    active=by_status.get("active", 0),
                    blocked=by_status.get("blocked", 0),
                    completed=by_status.get("completed", 0),
                    abandoned=by_status.get("abandoned", 0),
                ),
                by_type=GoalsByType(
                    work=by_type.get("work", 0),
                    learning=by_type.get("learning", 0),
                    research=by_type.get("research", 0),
                    growth=by_type.get("growth", 0),
                    initiative=by_type.get("initiative", 0),
                ),
            )
        except Exception as e:
            logger.warning(f"Failed to query goals: {e}")
            # Return empty stats
            return Goals(
                stats=GoalStats(
                    total=0, active=0, blocked=0, pending_approval=0,
                    completed=0, abandoned=0, open_capability_gaps=0, average_alignment=1.0
                ),
                by_status=GoalsByStatus(
                    proposed=0, approved=0, active=0, blocked=0, completed=0, abandoned=0
                ),
                by_type=GoalsByType(work=0, learning=0, research=0, growth=0, initiative=0),
            )

    @strawberry.field
    async def tokens(self) -> TokenUsage:
        """Get token usage statistics."""
        bus = get_daemon_state_bus()

        try:
            from query_models import StateQuery
            query = StateQuery(source="tokens", metric="all")
            result = await bus.query(query)

            data = result.data.value if result.data else {}
            if isinstance(data, dict):
                return TokenUsage(
                    today_cost_usd=data.get("today_cost_usd", 0.0),
                    today_input_tokens=data.get("today_input_tokens", 0),
                    today_output_tokens=data.get("today_output_tokens", 0),
                    today_total_tokens=data.get("today_total_tokens", 0),
                    week_cost_usd=data.get("week_cost_usd", 0.0),
                    month_cost_usd=data.get("month_cost_usd", 0.0),
                    month_total_tokens=data.get("month_total_tokens", 0),
                    total_cost_usd=data.get("total_cost_usd", 0.0),
                    total_tokens=data.get("total_tokens", 0),
                    total_requests=data.get("total_requests", 0),
                )
        except Exception as e:
            logger.warning(f"Failed to query tokens: {e}")

        return TokenUsage(
            today_cost_usd=0.0, today_input_tokens=0, today_output_tokens=0,
            today_total_tokens=0, week_cost_usd=0.0, month_cost_usd=0.0,
            month_total_tokens=0, total_cost_usd=0.0, total_tokens=0, total_requests=0
        )

    @strawberry.field
    async def github(self) -> GitHubMetrics:
        """Get GitHub metrics across tracked repositories."""
        bus = get_daemon_state_bus()

        try:
            from query_models import StateQuery
            query = StateQuery(source="github", metric="all")
            result = await bus.query(query)

            data = result.data.value if result.data else {}
            if isinstance(data, dict):
                return GitHubMetrics(
                    stars_total=data.get("stars_total", 0),
                    forks_total=data.get("forks_total", 0),
                    watchers_total=data.get("watchers_total", 0),
                    open_issues=data.get("open_issues", 0),
                    clones_14d=data.get("clones_14d", 0),
                    views_14d=data.get("views_14d", 0),
                    stars_7d=data.get("stars_7d", 0),
                    repos_tracked=data.get("repos_tracked", 0),
                )
        except Exception as e:
            logger.warning(f"Failed to query github: {e}")

        return GitHubMetrics(
            stars_total=0, forks_total=0, watchers_total=0,
            open_issues=0, clones_14d=0, views_14d=0, stars_7d=0, repos_tracked=0
        )

    @strawberry.field
    async def conversations(self) -> ConversationStats:
        """Get conversation statistics."""
        bus = get_daemon_state_bus()

        try:
            from query_models import StateQuery
            query = StateQuery(source="conversations", metric="all")
            result = await bus.query(query)

            data = result.data.value if result.data else {}
            if isinstance(data, dict):
                return ConversationStats(
                    total_conversations=data.get("total_conversations", 0),
                    conversations_today=data.get("conversations_today", 0),
                    conversations_week=data.get("conversations_week", 0),
                    total_messages=data.get("total_messages", 0),
                    messages_today=data.get("messages_today", 0),
                    active_users_today=data.get("active_users_today", 0),
                )
        except Exception as e:
            logger.warning(f"Failed to query conversations: {e}")

        return ConversationStats(
            total_conversations=0, conversations_today=0, conversations_week=0,
            total_messages=0, messages_today=0, active_users_today=0
        )

    @strawberry.field
    async def memory(self) -> MemoryStats:
        """Get memory system statistics."""
        bus = get_daemon_state_bus()

        try:
            from query_models import StateQuery
            query = StateQuery(source="memory", metric="all")
            result = await bus.query(query)

            data = result.data.value if result.data else {}
            if isinstance(data, dict):
                return MemoryStats(
                    total_journals=data.get("total_journals", 0),
                    total_threads=data.get("total_threads", 0),
                    threads_active=data.get("threads_active", 0),
                    total_questions=data.get("total_questions", 0),
                    questions_open=data.get("questions_open", 0),
                    total_embeddings=data.get("total_embeddings", 0),
                )
        except Exception as e:
            logger.warning(f"Failed to query memory: {e}")

        return MemoryStats(
            total_journals=0, total_threads=0, threads_active=0,
            total_questions=0, questions_open=0, total_embeddings=0
        )

    @strawberry.field
    async def self_model(self) -> SelfModelStats:
        """Get self-model graph statistics."""
        bus = get_daemon_state_bus()

        try:
            from query_models import StateQuery
            query = StateQuery(source="self", metric="all")
            result = await bus.query(query)

            data = result.data.value if result.data else {}
            if isinstance(data, dict):
                return SelfModelStats(
                    total_nodes=data.get("total_nodes", 0),
                    total_edges=data.get("total_edges", 0),
                    observations=data.get("observations", 0),
                    opinions=data.get("opinions", 0),
                    growth_edges=data.get("growth_edges", 0),
                    intentions=data.get("intentions", 0),
                )
        except Exception as e:
            logger.warning(f"Failed to query self: {e}")

        return SelfModelStats(
            total_nodes=0, total_edges=0, observations=0, opinions=0, growth_edges=0, intentions=0
        )

    @strawberry.field
    async def state(self) -> GlobalState:
        """Get current global state (emotional, activity, coherence)."""
        bus = get_daemon_state_bus()
        state = bus.read_state()

        emotional = state.emotional.to_dict()
        activity = state.activity.to_dict()
        coherence = state.coherence.to_dict()

        return GlobalState(
            emotional=EmotionalState(
                directedness=emotional.get("directedness"),
                clarity=emotional.get("clarity", 0.7),
                relational_presence=emotional.get("relational_presence", 0.7),
                generativity=emotional.get("generativity", 0.7),
                integration=emotional.get("integration", 0.7),
                curiosity=emotional.get("curiosity", 0.5),
                contentment=emotional.get("contentment", 0.5),
                anticipation=emotional.get("anticipation", 0.5),
                concern=emotional.get("concern", 0.2),
                recognition=emotional.get("recognition", 0.5),
                last_updated=emotional.get("last_updated"),
            ),
            activity=ActivityState(
                current=activity.get("current_activity", "idle"),
                user_id=activity.get("active_user_id"),
                contact_started=activity.get("contact_started_at"),
                messages_this_contact=activity.get("messages_this_contact", 0),
                current_topics=activity.get("current_topics", []),
                rhythm_phase=activity.get("rhythm_phase"),
                rhythm_summary=activity.get("rhythm_day_summary"),
                active_threads=len(activity.get("active_threads", [])),
                active_questions=len(activity.get("active_questions", [])),
            ),
            coherence=CoherenceState(
                local=coherence.get("local_coherence", 0.8),
                pattern=coherence.get("pattern_coherence", 0.8),
                sessions_today=coherence.get("sessions_today", 0),
            ),
        )

    @strawberry.field
    async def daily_summary(self) -> DailySummary:
        """Get aggregated summary of today's activity across all sources."""
        bus = get_daemon_state_bus()
        from query_models import StateQuery

        today = datetime.now().strftime("%Y-%m-%d")

        # Gather data from multiple sources
        conversations_today = 0
        messages_today = 0
        token_cost = 0.0
        goals_completed = 0
        goals_created = 0
        journals = 0
        commits = 0

        try:
            # Conversations
            result = await bus.query(StateQuery(source="conversations", metric="all"))
            if result.data and isinstance(result.data.value, dict):
                conversations_today = result.data.value.get("conversations_today", 0)
                messages_today = result.data.value.get("messages_today", 0)
        except Exception:
            pass

        try:
            # Tokens
            result = await bus.query(StateQuery(source="tokens", metric="all"))
            if result.data and isinstance(result.data.value, dict):
                token_cost = result.data.value.get("today_cost_usd", 0.0)
        except Exception:
            pass

        try:
            # Goals - would need daily tracking, for now just totals
            result = await bus.query(StateQuery(source="goals", metric="all"))
            # TODO: Add daily goal tracking
        except Exception:
            pass

        try:
            # Memory (journals)
            result = await bus.query(StateQuery(source="memory", metric="all"))
            if result.data and isinstance(result.data.value, dict):
                journals = result.data.value.get("total_journals", 0)
        except Exception:
            pass

        try:
            # GitHub (no commit tracking yet, use stars_7d as activity proxy)
            result = await bus.query(StateQuery(source="github", metric="all"))
            if result.data and isinstance(result.data.value, dict):
                commits = result.data.value.get("stars_7d", 0)  # TODO: Add commit tracking
        except Exception:
            pass

        # Get current activity state
        state = bus.read_state()
        activity = state.activity.to_dict()

        return DailySummary(
            date=today,
            conversations_count=conversations_today,
            messages_count=messages_today,
            token_cost_usd=token_cost,
            goals_completed=goals_completed,
            goals_created=goals_created,
            journals_written=journals,
            commits=commits,
            current_activity=activity.get("current_activity", "idle"),
            rhythm_phase=activity.get("rhythm_phase"),
        )

    @strawberry.field
    async def actions(self) -> ActionsStats:
        """Get all atomic action definitions grouped by category."""
        bus = get_daemon_state_bus()

        try:
            from query_models import StateQuery
            query = StateQuery(source="actions", metric="all")
            result = await bus.query(query)

            data = result.data.value if result.data else {}
            if isinstance(data, dict):
                by_cat = data.get("by_category", {})
                categories = []

                for cat_name, action_list in by_cat.items():
                    actions = [
                        ActionDefinition(
                            id=a.get("id", ""),
                            name=a.get("name", ""),
                            description=a.get("description", ""),
                            category=a.get("category", ""),
                            handler=a.get("handler", ""),
                            estimated_cost_usd=a.get("estimated_cost_usd", 0.0),
                            default_duration_minutes=a.get("default_duration_minutes", 30),
                            priority=a.get("priority", "normal"),
                            requires_idle=a.get("requires_idle", False),
                        )
                        for a in action_list
                    ]
                    categories.append(ActionCategory(
                        category=cat_name,
                        count=len(actions),
                        actions=actions,
                    ))

                return ActionsStats(
                    total_actions=data.get("total", 0),
                    category_count=len(categories),
                    by_category=categories,
                )
        except Exception as e:
            logger.warning(f"Failed to query actions: {e}")

        return ActionsStats(
            total_actions=0,
            category_count=0,
            by_category=[],
        )

    @strawberry.field
    async def work_planning(self) -> WorkPlanning:
        """Get Cass's work planning state - taskboard and calendar."""
        bus = get_daemon_state_bus()

        try:
            from query_models import StateQuery

            # Query work items
            work_query = StateQuery(source="work", metric="all")
            work_result = await bus.query(work_query)
            work_data = work_result.data.value if work_result.data else {}

            # Query schedule
            schedule_query = StateQuery(source="schedule", metric="all")
            schedule_result = await bus.query(schedule_query)
            schedule_data = schedule_result.data.value if schedule_result.data else {}

            # Query pending approval work items
            pending_query = StateQuery(source="work", metric="pending_approval")
            pending_result = await bus.query(pending_query)

            # Query upcoming schedule slots
            upcoming_query = StateQuery(source="schedule", metric="upcoming", filters={"hours": 24})
            upcoming_result = await bus.query(upcoming_query)
            upcoming_data = upcoming_result.data.value if upcoming_result.data else []

            # Build work stats
            work_stats = WorkStats(
                total=work_data.get("total", 0) if isinstance(work_data, dict) else 0,
                by_status=work_data.get("by_status", {}) if isinstance(work_data, dict) else {},
                by_category=work_data.get("by_category", {}) if isinstance(work_data, dict) else {},
                pending_approval=work_data.get("pending_approval", 0) if isinstance(work_data, dict) else 0,
                estimated_pending_cost_usd=work_data.get("estimated_pending_cost_usd", 0.0) if isinstance(work_data, dict) else 0.0,
                actual_completed_cost_usd=work_data.get("actual_completed_cost_usd", 0.0) if isinstance(work_data, dict) else 0.0,
            )

            # Build schedule stats
            schedule_stats = ScheduleStats(
                total=schedule_data.get("total", 0) if isinstance(schedule_data, dict) else 0,
                by_status=schedule_data.get("by_status", {}) if isinstance(schedule_data, dict) else {},
                today_count=schedule_data.get("today_count", 0) if isinstance(schedule_data, dict) else 0,
                week_count=schedule_data.get("week_count", 0) if isinstance(schedule_data, dict) else 0,
                budget_scheduled_usd=schedule_data.get("budget_scheduled_usd", 0.0) if isinstance(schedule_data, dict) else 0.0,
                flexible_slots=schedule_data.get("flexible_slots", 0) if isinstance(schedule_data, dict) else 0,
                idle_slots=schedule_data.get("idle_slots", 0) if isinstance(schedule_data, dict) else 0,
            )

            # Convert upcoming slots to GraphQL type
            upcoming_slots = []
            if isinstance(upcoming_data, list):
                for s in upcoming_data:
                    upcoming_slots.append(ScheduleSlotSummary(
                        id=s.get("id", ""),
                        work_item_id=s.get("work_item_id"),
                        start_time=s.get("start_time"),
                        end_time=s.get("end_time"),
                        duration_minutes=s.get("duration_minutes", 30),
                        priority=s.get("priority", 2),
                        status=s.get("status", "scheduled"),
                        requires_idle=s.get("requires_idle", False),
                        notes=s.get("notes"),
                    ))

            return WorkPlanning(
                work_stats=work_stats,
                schedule_stats=schedule_stats,
                pending_approval=[],  # Would need to query actual work items
                upcoming_slots=upcoming_slots,
            )
        except Exception as e:
            logger.warning(f"Failed to query work planning: {e}")

        # Return empty state on error
        return WorkPlanning(
            work_stats=WorkStats(
                total=0, by_status={}, by_category={},
                pending_approval=0, estimated_pending_cost_usd=0.0, actual_completed_cost_usd=0.0
            ),
            schedule_stats=ScheduleStats(
                total=0, by_status={}, today_count=0, week_count=0,
                budget_scheduled_usd=0.0, flexible_slots=0, idle_slots=0
            ),
            pending_approval=[],
            upcoming_slots=[],
        )

    @strawberry.field
    async def approvals(self) -> Approvals:
        """Get pending approvals from Synkratos - unified 'what needs attention?' view."""
        from routes.admin.scheduler import get_scheduler

        scheduler = get_scheduler()
        if not scheduler:
            return Approvals(
                items=[],
                count=0,
                counts=ApprovalCounts(goal=0, research=0, action=0, user=0, total=0),
            )

        # Get pending approvals
        pending = scheduler.get_pending_approvals()
        counts = scheduler.get_approval_counts()

        items = [
            ApprovalItem(
                approval_id=a.approval_id,
                approval_type=a.approval_type.value,
                title=a.title,
                description=a.description,
                source_id=a.source_id,
                created_at=a.created_at.isoformat() if a.created_at else "",
                created_by=a.created_by or "unknown",
                priority=a.priority.value if hasattr(a.priority, 'value') else str(a.priority),
            )
            for a in pending
        ]

        return Approvals(
            items=items,
            count=len(items),
            counts=ApprovalCounts(
                goal=counts.get("goal", 0),
                research=counts.get("research", 0),
                action=counts.get("action", 0),
                user=counts.get("user", 0),
                total=counts.get("total", 0),
            ),
        )

    # =========================================================================
    # PEOPLEDEX QUERIES
    # =========================================================================

    @strawberry.field
    async def peopledex_stats(self) -> PeopleDexStats:
        """Get PeopleDex statistics."""
        manager = get_peopledex_manager()
        all_entities = manager.list_entities(limit=10000)

        type_counts: Dict[str, int] = {}
        realm_counts: Dict[str, int] = {}

        for entity in all_entities:
            type_str = entity.entity_type.value
            type_counts[type_str] = type_counts.get(type_str, 0) + 1

            realm_str = entity.realm.value
            realm_counts[realm_str] = realm_counts.get(realm_str, 0) + 1

        return PeopleDexStats(
            total_entities=len(all_entities),
            by_type=type_counts,
            by_realm=realm_counts,
        )

    @strawberry.field
    async def peopledex_entities(
        self,
        entity_type: Optional[str] = None,
        realm: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[PeopleDexEntity]:
        """List or search PeopleDex entities."""
        manager = get_peopledex_manager()

        # Parse entity type if provided
        etype = None
        if entity_type:
            try:
                etype = PDEntityType(entity_type)
            except ValueError:
                raise ValueError(f"Invalid entity_type: {entity_type}")

        if search:
            entities = manager.search_entities(search, etype, limit=limit)
        else:
            entities = manager.list_entities(etype, limit=limit, offset=offset)

        # Filter by realm if specified
        if realm:
            entities = [e for e in entities if e.realm.value == realm]

        return [
            PeopleDexEntity(
                id=e.id,
                entity_type=e.entity_type.value,
                primary_name=e.primary_name,
                realm=e.realm.value,
                user_id=e.user_id,
                npc_id=e.npc_id,
                created_at=e.created_at,
                updated_at=e.updated_at,
            )
            for e in entities
        ]

    @strawberry.field
    async def peopledex_entity(self, entity_id: str) -> Optional[PeopleDexProfile]:
        """Get full PeopleDex entity profile."""
        manager = get_peopledex_manager()
        profile = manager.get_full_profile(entity_id)

        if not profile:
            return None

        return PeopleDexProfile(
            entity=PeopleDexEntity(
                id=profile.entity.id,
                entity_type=profile.entity.entity_type.value,
                primary_name=profile.entity.primary_name,
                realm=profile.entity.realm.value,
                user_id=profile.entity.user_id,
                npc_id=profile.entity.npc_id,
                created_at=profile.entity.created_at,
                updated_at=profile.entity.updated_at,
            ),
            attributes=[
                PeopleDexAttribute(
                    id=a.id,
                    entity_id=a.entity_id,
                    attribute_type=a.attribute_type.value,
                    attribute_key=a.attribute_key,
                    value=a.value,
                    is_primary=a.is_primary,
                    source_type=a.source_type,
                    source_id=a.source_id,
                    confidence=a.confidence,
                    created_at=a.created_at,
                    updated_at=a.updated_at,
                )
                for a in profile.attributes
            ],
            relationships=[
                PeopleDexRelationship(
                    relationship_id=r["relationship_id"],
                    relationship_type=r["relationship_type"],
                    relationship_label=r.get("relationship_label"),
                    direction=r["direction"],
                    related_entity=PeopleDexRelatedEntity(
                        id=r["entity"].id,
                        entity_type=r["entity"].entity_type.value,
                        primary_name=r["entity"].primary_name,
                        realm=r["entity"].realm.value,
                    ),
                )
                for r in profile.relationships
            ],
        )

    # =========================================================================
    # WORK SUMMARY QUERIES
    # =========================================================================

    @strawberry.field
    async def day_phase(self) -> DayPhaseType:
        """Get current day phase information."""
        bus = get_daemon_state_bus()
        state = bus.read_state()

        dp = state.day_phase
        return DayPhaseType(
            current_phase=dp.current_phase,
            phase_started_at=dp.phase_started_at.isoformat() if dp.phase_started_at else None,
            next_transition_at=dp.next_transition_at.isoformat() if dp.next_transition_at else None,
            recent_work_slugs=dp.recent_work_slugs,
            todays_work_slugs=dp.todays_work_slugs,
            work_by_phase=dp.work_by_phase,
        )

    @strawberry.field
    async def work_summary(self, slug: str) -> Optional[WorkSummaryType]:
        """Get a specific work summary by slug."""
        from scheduling import WorkSummaryStore
        from database import get_daemon_id

        daemon_id = get_daemon_id()
        store = WorkSummaryStore(daemon_id)
        summary = store.get_by_slug(slug)

        if not summary:
            return None

        return self._work_summary_to_type(summary)

    @strawberry.field
    async def work_history(
        self,
        date: Optional[str] = None,
        phase: Optional[str] = None,
        limit: int = 20,
    ) -> List[WorkSummaryType]:
        """Get work history, optionally filtered by date and/or phase."""
        from scheduling import WorkSummaryStore
        from database import get_daemon_id
        from datetime import date as date_type

        daemon_id = get_daemon_id()
        store = WorkSummaryStore(daemon_id)

        if date:
            target_date = date_type.fromisoformat(date)
            if phase:
                summaries = store.get_by_phase(target_date, phase)
            else:
                summaries = store.get_by_date(target_date)
        else:
            summaries = store.get_recent(limit)

        return [self._work_summary_to_type(s) for s in summaries[:limit]]

    @strawberry.field
    async def work_stats(
        self,
        start_date: str,
        end_date: str,
    ) -> WorkHistoryStats:
        """Get work statistics for a date range."""
        from scheduling import WorkSummaryStore
        from database import get_daemon_id
        from datetime import date as date_type

        daemon_id = get_daemon_id()
        store = WorkSummaryStore(daemon_id)

        start = date_type.fromisoformat(start_date)
        end = date_type.fromisoformat(end_date)
        stats = store.get_stats(start, end)

        return WorkHistoryStats(
            total_count=stats["total_count"],
            total_minutes=stats["total_minutes"],
            by_phase=stats["by_phase"],
            by_category=stats["by_category"],
            date_range_start=start_date,
            date_range_end=end_date,
        )

    @strawberry.field
    async def autonomous_schedule(self) -> AutonomousScheduleState:
        """Get full autonomous schedule state for the schedule panel."""
        from routes.admin.scheduler import get_autonomous_scheduler, get_phase_queue_manager

        scheduler = get_autonomous_scheduler()
        phase_queue = get_phase_queue_manager()
        bus = get_daemon_state_bus()
        state = bus.read_state()
        current_phase = state.day_phase.current_phase if state.day_phase else "afternoon"

        # Handle case where scheduler isn't initialized
        if not scheduler:
            return AutonomousScheduleState(
                enabled=False,
                is_working=False,
                current_work=None,
                todays_plan=TodaysPlanType(
                    day_intention=None,
                    planned_at=None,
                    phases=[],
                    total_work_units=0,
                ),
                phase_queues=[
                    PhaseQueueType(
                        phase=p,
                        is_current=(p == current_phase),
                        queue_count=0,
                        work_units=[],
                    )
                    for p in ["morning", "afternoon", "evening", "night"]
                ],
                daily_summary={},
            )

        # Build current work if any
        current_work = None
        if scheduler.is_working and scheduler.current_work:
            work = scheduler.current_work
            elapsed = 0
            if work.started_at:
                elapsed = int((datetime.now() - work.started_at.replace(tzinfo=None)).total_seconds() / 60)

            current_work = CurrentWorkType(
                work_unit=WorkUnitType(
                    id=work.id,
                    name=work.name,
                    template_id=work.template_id,
                    category=work.category,
                    focus=work.focus,
                    motivation=work.motivation,
                    estimated_duration_minutes=work.estimated_duration_minutes or 30,
                    estimated_cost_usd=work.estimated_cost_usd or 0.0,
                    status="running",
                ),
                started_at=work.started_at.isoformat() if work.started_at else datetime.now().isoformat(),
                elapsed_minutes=elapsed,
            )

        # Build today's plan
        todays_plan_data = scheduler.get_todays_plan()
        phases_list = []
        total_units = 0
        for phase_name in ["morning", "afternoon", "evening", "night"]:
            units = todays_plan_data.get(phase_name, [])
            work_units = [
                WorkUnitType(
                    id=u.get("id", ""),
                    name=u.get("name", ""),
                    template_id=u.get("template_id"),
                    category=u.get("category"),
                    focus=u.get("focus"),
                    motivation=u.get("motivation"),
                    estimated_duration_minutes=u.get("estimated_duration_minutes", 30),
                    estimated_cost_usd=u.get("estimated_cost_usd", 0.0),
                    status=u.get("status", "queued"),
                )
                for u in units
            ]
            phases_list.append(TodaysPlanByPhase(
                phase=phase_name,
                work_units=work_units,
            ))
            total_units += len(units)

        todays_plan = TodaysPlanType(
            day_intention=None,  # TODO: Store and retrieve day intention from decision engine
            planned_at=scheduler._last_plan_date.isoformat() if scheduler._last_plan_date else None,
            phases=phases_list,
            total_work_units=total_units,
        )

        # Build phase queues
        phase_queues = []
        if phase_queue:
            all_queues = phase_queue.get_all_queues()
            for phase_name in ["morning", "afternoon", "evening", "night"]:
                queue_data = all_queues.get(phase_name, [])
                queued_units = [
                    QueuedWorkUnitType(
                        work_unit=WorkUnitType(
                            id=q["work_unit"].get("id", ""),
                            name=q["work_unit"].get("name", ""),
                            template_id=q["work_unit"].get("template_id"),
                            category=q["work_unit"].get("category"),
                            focus=q["work_unit"].get("focus"),
                            motivation=q["work_unit"].get("motivation"),
                            estimated_duration_minutes=q["work_unit"].get("estimated_duration_minutes", 30),
                            estimated_cost_usd=q["work_unit"].get("estimated_cost_usd", 0.0),
                            status="queued",
                        ),
                        target_phase=q.get("target_phase", phase_name),
                        queued_at=q.get("queued_at", datetime.now().isoformat()),
                        priority=q.get("priority", 1),
                    )
                    for q in queue_data
                ]
                phase_queues.append(PhaseQueueType(
                    phase=phase_name,
                    is_current=(phase_name == current_phase),
                    queue_count=len(queued_units),
                    work_units=queued_units,
                ))
        else:
            # No phase queue manager, return empty queues
            for phase_name in ["morning", "afternoon", "evening", "night"]:
                phase_queues.append(PhaseQueueType(
                    phase=phase_name,
                    is_current=(phase_name == current_phase),
                    queue_count=0,
                    work_units=[],
                ))

        return AutonomousScheduleState(
            enabled=scheduler.is_enabled,
            is_working=scheduler.is_working,
            current_work=current_work,
            todays_plan=todays_plan,
            phase_queues=phase_queues,
            daily_summary=scheduler.get_daily_summary(),
        )

    @strawberry.field
    async def continuous_conversation(self, user_id: str) -> ContinuousConversation:
        """
        Get or create the continuous conversation for a user.

        The continuous conversation is a single stream where all messages
        accumulate. Context is composed from threads + working summary.
        """
        from conversations import ConversationManager

        manager = ConversationManager()
        conv = manager.get_or_create_continuous(user_id)

        return ContinuousConversation(
            conversation_id=conv.id,
            user_id=user_id,
            message_count=len(conv.messages),
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            has_working_summary=conv.working_summary is not None,
        )

    def _work_summary_to_type(self, summary) -> WorkSummaryType:
        """Convert WorkSummary to GraphQL type."""
        return WorkSummaryType(
            work_unit_id=summary.work_unit_id,
            slug=summary.slug,
            name=summary.name,
            template_id=summary.template_id,
            phase=summary.phase,
            category=summary.category,
            focus=summary.focus,
            motivation=summary.motivation,
            date=summary.date.isoformat(),
            started_at=summary.started_at.isoformat() if summary.started_at else None,
            completed_at=summary.completed_at.isoformat() if summary.completed_at else None,
            duration_minutes=summary.duration_minutes,
            summary=summary.summary,
            key_insights=summary.key_insights,
            questions_addressed=summary.questions_addressed,
            questions_raised=summary.questions_raised,
            action_summaries=[
                ActionSummaryType(
                    action_id=a.action_id,
                    action_type=a.action_type,
                    slug=a.slug,
                    summary=a.summary,
                    started_at=a.started_at.isoformat() if a.started_at else None,
                    completed_at=a.completed_at.isoformat() if a.completed_at else None,
                    artifacts=a.artifacts,
                )
                for a in summary.action_summaries
            ],
            artifacts=summary.artifacts,
            success=summary.success,
            error=summary.error,
            cost_usd=summary.cost_usd,
        )


# =============================================================================
# MUTATIONS
# =============================================================================

@strawberry.type
class MutationResult:
    """Result of a mutation operation."""
    success: bool
    message: str
    id: Optional[str] = None


@strawberry.type
class Mutation:
    """GraphQL mutations for Cass Vessel."""

    # =========================================================================
    # PEOPLEDEX MUTATIONS
    # =========================================================================

    @strawberry.mutation
    async def create_peopledex_entity(self, input: CreateEntityInput) -> MutationResult:
        """Create a new PeopleDex entity."""
        manager = get_peopledex_manager()

        try:
            entity_type = PDEntityType(input.entity_type)
        except ValueError:
            return MutationResult(
                success=False,
                message=f"Invalid entity_type: {input.entity_type}",
            )

        try:
            realm = PDRealm(input.realm)
        except ValueError:
            return MutationResult(
                success=False,
                message=f"Invalid realm: {input.realm}",
            )

        entity_id = manager.create_entity(
            entity_type=entity_type,
            primary_name=input.primary_name,
            realm=realm,
            user_id=input.user_id,
            npc_id=input.npc_id,
        )

        return MutationResult(
            success=True,
            message=f"Created entity: {input.primary_name}",
            id=entity_id,
        )

    @strawberry.mutation
    async def update_peopledex_entity(
        self, entity_id: str, input: UpdateEntityInput
    ) -> MutationResult:
        """Update a PeopleDex entity."""
        manager = get_peopledex_manager()

        entity_type = None
        if input.entity_type:
            try:
                entity_type = PDEntityType(input.entity_type)
            except ValueError:
                return MutationResult(
                    success=False,
                    message=f"Invalid entity_type: {input.entity_type}",
                )

        success = manager.update_entity(
            entity_id=entity_id,
            primary_name=input.primary_name,
            entity_type=entity_type,
        )

        if not success:
            return MutationResult(
                success=False,
                message=f"Entity not found or no updates applied: {entity_id}",
            )

        return MutationResult(
            success=True,
            message="Entity updated",
            id=entity_id,
        )

    @strawberry.mutation
    async def delete_peopledex_entity(self, entity_id: str) -> MutationResult:
        """Delete a PeopleDex entity."""
        manager = get_peopledex_manager()

        success = manager.delete_entity(entity_id)

        if not success:
            return MutationResult(
                success=False,
                message=f"Entity not found: {entity_id}",
            )

        return MutationResult(
            success=True,
            message="Entity deleted",
        )

    @strawberry.mutation
    async def add_peopledex_attribute(
        self, entity_id: str, input: AddAttributeInput
    ) -> MutationResult:
        """Add an attribute to a PeopleDex entity."""
        manager = get_peopledex_manager()

        # Verify entity exists
        entity = manager.get_entity(entity_id)
        if not entity:
            return MutationResult(
                success=False,
                message=f"Entity not found: {entity_id}",
            )

        try:
            attr_type = PDAttributeType(input.attribute_type)
        except ValueError:
            return MutationResult(
                success=False,
                message=f"Invalid attribute_type: {input.attribute_type}",
            )

        attr_id = manager.add_attribute(
            entity_id=entity_id,
            attribute_type=attr_type,
            value=input.value,
            attribute_key=input.attribute_key,
            is_primary=input.is_primary,
            source_type=input.source_type,
        )

        return MutationResult(
            success=True,
            message="Attribute added",
            id=attr_id,
        )

    @strawberry.mutation
    async def update_peopledex_attribute(
        self, attr_id: str, input: UpdateAttributeInput
    ) -> MutationResult:
        """Update a PeopleDex attribute."""
        manager = get_peopledex_manager()

        success = manager.update_attribute(
            attribute_id=attr_id,
            value=input.value,
            is_primary=input.is_primary,
            source_type=input.source_type,
            confidence=input.confidence,
        )

        if not success:
            return MutationResult(
                success=False,
                message=f"Attribute not found or no updates applied: {attr_id}",
            )

        return MutationResult(
            success=True,
            message="Attribute updated",
            id=attr_id,
        )

    @strawberry.mutation
    async def delete_peopledex_attribute(self, attr_id: str) -> MutationResult:
        """Delete a PeopleDex attribute."""
        manager = get_peopledex_manager()

        success = manager.delete_attribute(attr_id)

        if not success:
            return MutationResult(
                success=False,
                message=f"Attribute not found: {attr_id}",
            )

        return MutationResult(
            success=True,
            message="Attribute deleted",
        )

    @strawberry.mutation
    async def add_peopledex_relationship(
        self, input: AddRelationshipInput
    ) -> MutationResult:
        """Add a relationship between two PeopleDex entities."""
        manager = get_peopledex_manager()

        # Verify both entities exist
        from_entity = manager.get_entity(input.from_entity_id)
        to_entity = manager.get_entity(input.to_entity_id)

        if not from_entity:
            return MutationResult(
                success=False,
                message=f"From entity not found: {input.from_entity_id}",
            )
        if not to_entity:
            return MutationResult(
                success=False,
                message=f"To entity not found: {input.to_entity_id}",
            )

        try:
            rel_type = PDRelationshipType(input.relationship_type)
        except ValueError:
            return MutationResult(
                success=False,
                message=f"Invalid relationship_type: {input.relationship_type}",
            )

        rel_id = manager.add_relationship(
            from_entity_id=input.from_entity_id,
            to_entity_id=input.to_entity_id,
            relationship_type=rel_type,
            relationship_label=input.relationship_label,
            source_type=input.source_type,
        )

        return MutationResult(
            success=True,
            message="Relationship added",
            id=rel_id,
        )

    @strawberry.mutation
    async def delete_peopledex_relationship(self, rel_id: str) -> MutationResult:
        """Delete a PeopleDex relationship."""
        manager = get_peopledex_manager()

        success = manager.delete_relationship(rel_id)

        if not success:
            return MutationResult(
                success=False,
                message=f"Relationship not found: {rel_id}",
            )

        return MutationResult(
            success=True,
            message="Relationship deleted",
        )

    @strawberry.mutation
    async def merge_peopledex_entities(self, input: MergeEntitiesInput) -> MutationResult:
        """Merge two PeopleDex entities."""
        manager = get_peopledex_manager()

        # Verify both entities exist
        keep_entity = manager.get_entity(input.keep_id)
        merge_entity = manager.get_entity(input.merge_id)

        if not keep_entity:
            return MutationResult(
                success=False,
                message=f"Keep entity not found: {input.keep_id}",
            )
        if not merge_entity:
            return MutationResult(
                success=False,
                message=f"Merge entity not found: {input.merge_id}",
            )

        success = manager.merge_entities(input.keep_id, input.merge_id)

        if not success:
            return MutationResult(
                success=False,
                message="Merge failed",
            )

        return MutationResult(
            success=True,
            message=f"Merged '{merge_entity.primary_name}' into '{keep_entity.primary_name}'",
            id=input.keep_id,
        )


# Create the schema with mutations
schema = strawberry.Schema(query=Query, mutation=Mutation)

# Create the GraphQL router for FastAPI
def get_graphql_router() -> GraphQLRouter:
    """Get the GraphQL router to mount in FastAPI."""
    return GraphQLRouter(schema)
