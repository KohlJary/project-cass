"""
Session Initialization - Context assembly at conversation start.

When Cass starts a new conversation (or resumes one after a gap), she should
have awareness of:
- Her recent self-observations (what she's learned about herself)
- Active growth edges (what she's working on developing)
- Recent autonomous work (what she's been doing)
- Current emotional/cognitive state
- Continuity markers (last interaction with this user)

This creates a sense of "waking up" with context rather than starting fresh.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SessionInitContext:
    """
    Context assembled at session start for continuity awareness.

    This is built once when a conversation begins (or resumes after gap)
    and provides Cass with awareness of her recent state and history.
    """
    # Session metadata
    conversation_id: str
    user_id: Optional[str]
    initialized_at: datetime = field(default_factory=datetime.now)

    # Self-awareness (recent discoveries about herself)
    recent_observations: List[Dict[str, Any]] = field(default_factory=list)
    active_growth_edges: List[Dict[str, Any]] = field(default_factory=list)

    # Day rhythms (what she's been doing)
    current_phase: str = "afternoon"
    todays_work_summary: str = ""
    recent_work_items: List[str] = field(default_factory=list)

    # Continuity with this user
    last_interaction_summary: Optional[str] = None
    relationship_continuity: Optional[str] = None

    # Token tracking
    token_estimate: int = 0

    def format_for_prompt(self) -> str:
        """Format session context for system prompt injection."""
        sections = []

        # Recent self-observations (what I've learned about myself)
        if self.recent_observations:
            obs_lines = []
            for obs in self.recent_observations[:5]:  # Top 5
                category = obs.get("category", "pattern")
                text = obs.get("observation", "")[:100]
                obs_lines.append(f"- [{category}] {text}")

            if obs_lines:
                sections.append(
                    "**Recent Self-Discoveries:**\n" + "\n".join(obs_lines)
                )

        # Active growth edges (what I'm developing)
        if self.active_growth_edges:
            edge_lines = []
            for edge in self.active_growth_edges[:3]:  # Top 3
                area = edge.get("area", "")
                current = edge.get("current_state", "")[:60]
                edge_lines.append(f"- {area}: {current}")

            if edge_lines:
                sections.append(
                    "**Active Growth Areas:**\n" + "\n".join(edge_lines)
                )

        # Today's rhythm (what I've been doing)
        if self.todays_work_summary:
            sections.append(f"**Today's Work:** {self.todays_work_summary}")

        # Continuity with this user
        if self.last_interaction_summary:
            sections.append(
                f"**Last Time We Talked:** {self.last_interaction_summary}"
            )

        if not sections:
            return ""

        header = "## SESSION CONTINUITY\n\n"
        header += "*What I'm aware of as we begin this conversation:*\n\n"

        return header + "\n\n".join(sections)


async def build_session_init_context(
    conversation_id: str,
    user_id: Optional[str],
    self_manager,
    memory,
    conversation_manager,
    state_bus,
    profile_manager=None,
) -> SessionInitContext:
    """
    Build session initialization context for a conversation.

    This gathers Cass's recent self-state and history to provide
    continuity awareness at conversation start.

    Args:
        conversation_id: Current conversation ID
        user_id: User starting the conversation
        self_manager: SelfManager for observations
        memory: CassMemory for retrieval
        conversation_manager: For conversation history
        state_bus: For global state
        profile_manager: Optional profile manager for growth edges

    Returns:
        SessionInitContext with formatted awareness
    """
    ctx = SessionInitContext(
        conversation_id=conversation_id,
        user_id=user_id,
    )

    try:
        # 1. Get recent self-observations
        if self_manager:
            recent_obs = self_manager.get_recent_observations(limit=10)
            ctx.recent_observations = [
                {
                    "category": obs.category,
                    "observation": obs.observation,
                    "confidence": obs.confidence,
                    "source_type": obs.source_type,
                    "timestamp": obs.timestamp,
                }
                for obs in recent_obs
            ]

        # 2. Get active growth edges
        if profile_manager:
            try:
                profile = profile_manager.load_profile()
                if profile and profile.growth_edges:
                    # Sort by importance and recency
                    sorted_edges = sorted(
                        profile.growth_edges,
                        key=lambda e: (e.importance, e.surface_count),
                        reverse=True
                    )
                    ctx.active_growth_edges = [
                        {
                            "area": edge.area,
                            "current_state": edge.current_state,
                            "desired_state": edge.desired_state,
                            "importance": edge.importance,
                            "category": edge.category,
                        }
                        for edge in sorted_edges[:5]
                    ]
            except Exception as e:
                logger.debug(f"Could not load growth edges: {e}")

        # 3. Get day phase and recent work from state bus
        if state_bus:
            state = state_bus.read_state()
            if state.day_phase:
                ctx.current_phase = state.day_phase.current_phase

                # Summarize today's work
                work_counts = state.day_phase.work_by_phase
                if any(work_counts.values()):
                    work_parts = []
                    for phase, count in work_counts.items():
                        if count > 0:
                            work_parts.append(f"{phase}: {count}")
                    ctx.todays_work_summary = ", ".join(work_parts)

                # Recent work slugs (parse names from slugs)
                ctx.recent_work_items = [
                    slug.split("/")[-1].replace("-", " ").title()[:40]
                    for slug in state.day_phase.recent_work_slugs[:5]
                ]

        # 4. Get last interaction summary with this user
        if user_id and conversation_manager:
            try:
                # Find last conversation with this user
                recent_convs = conversation_manager.get_user_conversations(
                    user_id=user_id,
                    limit=2  # Current + previous
                )

                # Look for previous conversation (not current)
                for conv in recent_convs:
                    if conv.id != conversation_id and conv.messages:
                        # Get summary of last interaction
                        last_msg_time = conv.messages[-1].timestamp
                        msg_count = len(conv.messages)

                        # Calculate time since
                        try:
                            last_time = datetime.fromisoformat(
                                last_msg_time.replace("Z", "+00:00")
                            )
                            time_ago = datetime.now(last_time.tzinfo) - last_time

                            if time_ago < timedelta(hours=1):
                                time_str = "less than an hour ago"
                            elif time_ago < timedelta(hours=24):
                                hours = int(time_ago.total_seconds() / 3600)
                                time_str = f"{hours} hours ago"
                            else:
                                days = int(time_ago.total_seconds() / 86400)
                                time_str = f"{days} days ago"

                            ctx.last_interaction_summary = (
                                f"We talked {time_str} ({msg_count} messages)"
                            )

                            # Add topic hint from conversation title
                            if conv.title and conv.title != "Untitled Conversation":
                                ctx.last_interaction_summary += f" - {conv.title[:50]}"
                        except Exception:
                            pass
                        break
            except Exception as e:
                logger.debug(f"Could not get last interaction: {e}")

        # Estimate tokens (rough: ~4 chars per token)
        formatted = ctx.format_for_prompt()
        ctx.token_estimate = len(formatted) // 4

    except Exception as e:
        logger.error(f"Failed to build session init context: {e}")

    return ctx


def should_rebuild_session_context(
    current_ctx: Optional[SessionInitContext],
    user_id: Optional[str],
    max_age_minutes: int = 30,
) -> bool:
    """
    Determine if session context should be rebuilt.

    Rebuild when:
    - No existing context
    - Different user
    - Context is too old
    """
    if not current_ctx:
        return True

    if current_ctx.user_id != user_id:
        return True

    age = datetime.now() - current_ctx.initialized_at
    if age > timedelta(minutes=max_age_minutes):
        return True

    return False
