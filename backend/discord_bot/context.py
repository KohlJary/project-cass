"""
Perception Context - Assembles Discord perception for prompt injection

Combines spatial snapshots, triggered events, and felt state into
a format suitable for Cass's system prompt.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, List, Any

from discord_bot.event_parser import ParsedEvent, EventType
from discord_bot.triggers import TriggerResult, TriggerPriority, TriggerAction
from discord_bot.entity_registry import get_entity_registry

logger = logging.getLogger("discord_bot.context")


def get_user_context_for_discord_entity(daemon_id: str, entity_slug: str) -> Optional[str]:
    """
    Get relationship context for a Discord user if they're linked to a known Cass user.

    Args:
        daemon_id: Daemon ID for registry lookup
        entity_slug: 4-character entity slug

    Returns:
        Formatted user context string, or None if not a known user
    """
    try:
        registry = get_entity_registry(daemon_id)
        entity = registry.get_by_slug(entity_slug)

        if not entity or not entity.user_id:
            return None

        # Get user relationship context from UserManager
        from users import get_user_manager
        user_manager = get_user_manager()

        # Get rich context (includes relationship, observations, etc.)
        user_context = user_manager.get_rich_user_context(entity.user_id)
        if not user_context:
            return None

        return user_context

    except Exception as e:
        logger.warning(f"[Context] Failed to get user context for {entity_slug}: {e}")
        return None


def format_triggered_events(
    events: List[tuple[ParsedEvent, TriggerResult]],
    max_events: int = 5,
    daemon_id: Optional[str] = None,
) -> str:
    """
    Format triggered events for prompt injection.

    Args:
        events: List of (event, trigger_result) tuples
        max_events: Maximum events to include
        daemon_id: Daemon ID for looking up user context

    Returns:
        Formatted string for prompt context
    """
    if not events:
        return ""

    lines = ["### Triggered Events"]
    lines.append("*These events have been flagged for your attention:*")
    lines.append("")

    # Sort by priority
    priority_order = {
        TriggerPriority.IMMEDIATE: 0,
        TriggerPriority.HIGH: 1,
        TriggerPriority.NOTABLE: 2,
        TriggerPriority.BACKGROUND: 3,
    }
    sorted_events = sorted(
        events[:max_events],
        key=lambda x: priority_order.get(x[1].priority, 99)
    )

    # Track entities we've shown user context for (avoid duplication)
    shown_user_context = set()

    for event, result in sorted_events:
        # Priority indicator
        priority_icon = {
            TriggerPriority.IMMEDIATE: "🔴",
            TriggerPriority.HIGH: "🟠",
            TriggerPriority.NOTABLE: "🟡",
            TriggerPriority.BACKGROUND: "⚪",
        }.get(result.priority, "⚪")

        # Build event line
        time_str = event.timestamp.strftime("%H:%M")

        if event.event_type == EventType.MESSAGE:
            if event.is_dm:
                line = f"{priority_icon} [{time_str}] **DM from {event.entity_display_name}**"
            else:
                line = f"{priority_icon} [{time_str}] **{event.entity_display_name}** in #{event.channel_name}"

            # Add content preview if available
            if event.content:
                preview = event.content[:100]
                if len(event.content) > 100:
                    preview += "..."
                line += f": \"{preview}\""
            elif event.content_summary:
                cs = event.content_summary
                line += f" ({cs.length.value} message, {cs.sentiment.value})"

        elif event.event_type == EventType.PRESENCE:
            line = f"{priority_icon} [{time_str}] **{event.entity_display_name}** is now {event.status}"

        elif event.event_type == EventType.VOICE:
            line = f"{priority_icon} [{time_str}] **{event.entity_display_name}** {event.voice_state} voice"
            if event.channel_name:
                line += f" in {event.channel_name}"

        elif event.event_type == EventType.REACTION:
            line = f"{priority_icon} [{time_str}] **{event.entity_display_name}** reacted {event.emoji}"

        else:
            line = f"{priority_icon} [{time_str}] {event.event_type.value} from {event.entity_display_name}"

        lines.append(line)

        # Add trigger context if relevant
        if result.context:
            context_parts = [f"  - {k}: {v}" for k, v in result.context.items()]
            lines.extend(context_parts)

        # For high-priority events from known users, include relationship context
        if (
            daemon_id
            and event.entity_slug not in shown_user_context
            and result.priority in (TriggerPriority.IMMEDIATE, TriggerPriority.HIGH)
        ):
            user_context = get_user_context_for_discord_entity(daemon_id, event.entity_slug)
            if user_context:
                shown_user_context.add(event.entity_slug)
                lines.append("")
                lines.append(f"*{event.entity_display_name} is a known user:*")
                lines.append(user_context)
                lines.append("")

    return "\n".join(lines)


def format_available_actions() -> str:
    """
    Format available Discord actions for prompt.

    Returns:
        Formatted action list
    """
    return """### Available Actions
- `discord_respond` - Send a message to a channel
- `discord_react` - Add a reaction to a message
- `discord_expand` - Get full context on a person/entity
- `discord_history` - View relationship timeline with someone
- `discord_snapshot` - Get current server state"""


def build_discord_perception_context(
    snapshot: Optional[str] = None,
    triggered_events: Optional[List[tuple[ParsedEvent, TriggerResult]]] = None,
    felt_state_summary: Optional[str] = None,
    include_actions: bool = True,
    daemon_id: Optional[str] = None,
) -> str:
    """
    Build complete Discord perception context for Cass's prompt.

    Args:
        snapshot: Ophanic spatial snapshot
        triggered_events: Events that triggered attention
        felt_state_summary: Thymos felt-state summary (if available)
        include_actions: Whether to include available actions list
        daemon_id: Daemon ID for looking up user context

    Returns:
        Formatted perception context string
    """
    sections = []

    sections.append("## Current Perception: Discord")
    sections.append("")

    # Spatial snapshot
    if snapshot:
        sections.append("### Environment State")
        sections.append(snapshot)
        sections.append("")

    # Felt state (Thymos integration - placeholder for now)
    if felt_state_summary:
        sections.append("### Felt State")
        sections.append(felt_state_summary)
        sections.append("")

    # Triggered events
    if triggered_events:
        triggered_str = format_triggered_events(triggered_events, daemon_id=daemon_id)
        if triggered_str:
            sections.append(triggered_str)
            sections.append("")

    # Available actions
    if include_actions:
        sections.append(format_available_actions())

    return "\n".join(sections)


def build_wake_context(
    event: ParsedEvent,
    result: TriggerResult,
    snapshot: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build context for waking Cass in response to a trigger.

    This is used when WAKE_CASS action is triggered - provides
    full context for Cass to reason about and respond to.

    Args:
        event: The triggering event
        result: Trigger evaluation result
        snapshot: Current server snapshot

    Returns:
        Dict with wake context for Cass invocation
    """
    context = {
        "trigger": result.trigger_name,
        "priority": result.priority.value,
        "event_type": event.event_type.value,
        "timestamp": event.timestamp.isoformat(),
        "entity_slug": event.entity_slug,
        "entity_name": event.entity_display_name,
        "guild_id": event.guild_id,
        "channel_id": event.channel_id,
        "channel_name": event.channel_name,
    }

    # Add event-specific data
    if event.event_type == EventType.MESSAGE:
        context["is_dm"] = event.is_dm
        context["is_direct_mention"] = event.is_direct_mention
        if event.content:
            context["message_content"] = event.content
        if event.content_summary:
            context["content_summary"] = event.content_summary.to_dict()

    elif event.event_type == EventType.PRESENCE:
        context["status"] = event.status
        context["activity"] = event.activity

    elif event.event_type == EventType.VOICE:
        context["voice_state"] = event.voice_state

    elif event.event_type == EventType.REACTION:
        context["emoji"] = event.emoji
        context["target_message_id"] = event.target_message_id

    # Add trigger context
    context["trigger_context"] = result.context

    # Add snapshot if available
    if snapshot:
        context["server_snapshot"] = snapshot

    return context


class DiscordPerceptionContext:
    """
    Manages perception context state for a daemon.

    Maintains current snapshot, recent events, and builds
    context for prompt injection.
    """

    def __init__(self, daemon_id: str):
        self.daemon_id = daemon_id
        self._snapshots: Dict[str, str] = {}  # guild_id → snapshot
        self._recent_triggered: List[tuple[ParsedEvent, TriggerResult]] = []
        self._last_snapshot_time: Dict[str, datetime] = {}

    def update_snapshot(self, guild_id: str, snapshot: str) -> None:
        """Update snapshot for a guild."""
        self._snapshots[guild_id] = snapshot
        self._last_snapshot_time[guild_id] = datetime.utcnow()

    def add_triggered_event(self, event: ParsedEvent, result: TriggerResult) -> None:
        """Add a triggered event to recent list."""
        self._recent_triggered.append((event, result))
        # Keep only last 20
        if len(self._recent_triggered) > 20:
            self._recent_triggered = self._recent_triggered[-20:]

    def get_perception_context(
        self,
        guild_id: Optional[str] = None,
        include_actions: bool = True,
        max_triggered: int = 5,
    ) -> str:
        """
        Get current perception context for prompt injection.

        Args:
            guild_id: Specific guild to get context for (None = all)
            include_actions: Include available actions list
            max_triggered: Max triggered events to include

        Returns:
            Formatted perception context string
        """
        # Get snapshot(s)
        if guild_id:
            snapshot = self._snapshots.get(guild_id)
        else:
            # Combine all snapshots
            snapshots = list(self._snapshots.values())
            snapshot = "\n\n---\n\n".join(snapshots) if snapshots else None

        # Get recent triggered events (only notable ones)
        triggered = [
            (e, r) for e, r in self._recent_triggered
            if r.priority in (TriggerPriority.IMMEDIATE, TriggerPriority.HIGH, TriggerPriority.NOTABLE)
        ][-max_triggered:]

        return build_discord_perception_context(
            snapshot=snapshot,
            triggered_events=triggered if triggered else None,
            include_actions=include_actions,
            daemon_id=self.daemon_id,
        )

    def clear_triggered_events(self) -> None:
        """Clear triggered events after processing."""
        self._recent_triggered.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get context statistics."""
        return {
            "guilds_with_snapshots": len(self._snapshots),
            "pending_triggered_events": len(self._recent_triggered),
            "snapshot_ages": {
                gid: (datetime.utcnow() - ts).total_seconds()
                for gid, ts in self._last_snapshot_time.items()
            },
        }


# Module-level singleton
_contexts: Dict[str, DiscordPerceptionContext] = {}


def get_perception_context(daemon_id: str) -> DiscordPerceptionContext:
    """Get or create perception context for daemon."""
    if daemon_id not in _contexts:
        _contexts[daemon_id] = DiscordPerceptionContext(daemon_id)
    return _contexts[daemon_id]
