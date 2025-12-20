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
    session_id: Optional[str]
    user_id: Optional[str]
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
                session_id=activity.get("active_session_id"),
                user_id=activity.get("active_user_id"),
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


# Create the schema
schema = strawberry.Schema(query=Query)

# Create the GraphQL router for FastAPI
def get_graphql_router() -> GraphQLRouter:
    """Get the GraphQL router to mount in FastAPI."""
    return GraphQLRouter(schema)
