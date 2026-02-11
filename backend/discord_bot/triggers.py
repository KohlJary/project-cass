"""
Trigger System - Evaluates events for Cass attention

Determines which events require immediate attention, queueing, or logging.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

from discord_bot.event_parser import ParsedEvent, EventType
from discord_bot.entity_registry import get_entity_registry

logger = logging.getLogger("discord_bot.triggers")


class TriggerPriority(str, Enum):
    """Priority levels for triggered events."""
    IMMEDIATE = "immediate"      # Wake Cass now
    HIGH = "high"                # Queue for near-immediate attention
    NOTABLE = "notable"          # Include in next snapshot prominently
    BACKGROUND = "background"    # Log for context, don't alert


class TriggerAction(str, Enum):
    """Actions to take when trigger fires."""
    WAKE_CASS = "wake_cass"                  # Immediately invoke Cass cognition
    QUEUE_FOR_ATTENTION = "queue_attention"   # Add to attention queue
    LOG_FOR_SNAPSHOT = "log_snapshot"         # Include in next snapshot
    EMIT_STATE_DELTA = "emit_delta"           # Update state bus
    NO_ACTION = "no_action"                   # Just log


@dataclass
class TriggerResult:
    """Result of trigger evaluation."""
    triggered: bool = False
    trigger_name: Optional[str] = None
    priority: TriggerPriority = TriggerPriority.BACKGROUND
    action: TriggerAction = TriggerAction.NO_ACTION
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "triggered": self.triggered,
            "trigger_name": self.trigger_name,
            "priority": self.priority.value,
            "action": self.action.value,
            "context": self.context,
        }


@dataclass
class Trigger:
    """Definition of an event trigger."""
    name: str
    description: str
    priority: TriggerPriority
    action: TriggerAction
    condition: Callable[[ParsedEvent, "TriggerContext"], bool]
    context_builder: Optional[Callable[[ParsedEvent], Dict[str, Any]]] = None
    enabled: bool = True


@dataclass
class TriggerContext:
    """Context available to trigger conditions."""
    daemon_id: str
    recent_events: List[ParsedEvent] = field(default_factory=list)
    last_cass_activity: Optional[datetime] = None
    flagged_entities: List[str] = field(default_factory=list)  # Entity slugs to watch
    absence_threshold_days: int = 7


class TriggerSystem:
    """
    Evaluates Discord events against trigger conditions.

    Triggers are evaluated in priority order, first match wins.
    """

    def __init__(self, daemon_id: str):
        """
        Initialize the trigger system.

        Args:
            daemon_id: Daemon ID for entity registry access
        """
        self.daemon_id = daemon_id
        self.registry = get_entity_registry(daemon_id)

        # Context for trigger evaluation
        self.context = TriggerContext(daemon_id=daemon_id)

        # Registered triggers (evaluated in order)
        self.triggers: List[Trigger] = []

        # Initialize default triggers
        self._register_default_triggers()

        # Attention queue for high-priority events
        self._attention_queue: List[tuple[ParsedEvent, TriggerResult]] = []

        # Recent activity tracking
        self._entity_last_seen: Dict[str, datetime] = {}

    def _register_default_triggers(self) -> None:
        """Register the default set of triggers."""

        # Direct mention - highest priority
        self.triggers.append(Trigger(
            name="direct_mention",
            description="Cass mentioned directly in message",
            priority=TriggerPriority.IMMEDIATE,
            action=TriggerAction.WAKE_CASS,
            condition=lambda e, ctx: (
                e.event_type == EventType.MESSAGE and
                e.is_direct_mention
            ),
            context_builder=lambda e: {
                "channel": e.channel_name,
                "author": e.entity_display_name,
                "content_preview": (e.content[:100] + "...") if e.content and len(e.content) > 100 else e.content,
            },
        ))

        # DM received
        self.triggers.append(Trigger(
            name="direct_message",
            description="Private message received",
            priority=TriggerPriority.IMMEDIATE,
            action=TriggerAction.WAKE_CASS,
            condition=lambda e, ctx: (
                e.event_type == EventType.MESSAGE and
                e.is_dm
            ),
            context_builder=lambda e: {
                "author": e.entity_display_name,
                "content_preview": (e.content[:100] + "...") if e.content and len(e.content) > 100 else e.content,
            },
        ))

        # Close friend message
        self.triggers.append(Trigger(
            name="close_friend_message",
            description="Message from close friend",
            priority=TriggerPriority.HIGH,
            action=TriggerAction.QUEUE_FOR_ATTENTION,
            condition=lambda e, ctx: (
                e.event_type == EventType.MESSAGE and
                e.entity_slug and
                self._get_entity_tier(e.entity_slug) == "close_friend"
            ),
            context_builder=lambda e: {
                "friend": e.entity_display_name,
                "channel": e.channel_name,
            },
        ))

        # Friend message
        self.triggers.append(Trigger(
            name="friend_message",
            description="Message from friend",
            priority=TriggerPriority.NOTABLE,
            action=TriggerAction.LOG_FOR_SNAPSHOT,
            condition=lambda e, ctx: (
                e.event_type == EventType.MESSAGE and
                e.entity_slug and
                self._get_entity_tier(e.entity_slug) == "friend"
            ),
        ))

        # Flagged entity activity
        self.triggers.append(Trigger(
            name="flagged_entity_activity",
            description="Activity from flagged/watched entity",
            priority=TriggerPriority.HIGH,
            action=TriggerAction.QUEUE_FOR_ATTENTION,
            condition=lambda e, ctx: (
                e.entity_slug in ctx.flagged_entities
            ),
            context_builder=lambda e: {
                "entity": e.entity_display_name,
                "event_type": e.event_type.value,
            },
        ))

        # Extended absence return
        self.triggers.append(Trigger(
            name="absence_return",
            description="Known entity returns after extended absence",
            priority=TriggerPriority.NOTABLE,
            action=TriggerAction.LOG_FOR_SNAPSHOT,
            condition=lambda e, ctx: self._check_absence_return(e, ctx),
            context_builder=lambda e: {
                "entity": e.entity_display_name,
                "event_type": e.event_type.value,
            },
        ))

        # Voice join (anyone)
        self.triggers.append(Trigger(
            name="voice_join",
            description="Someone joined voice channel",
            priority=TriggerPriority.BACKGROUND,
            action=TriggerAction.LOG_FOR_SNAPSHOT,
            condition=lambda e, ctx: (
                e.event_type == EventType.VOICE and
                e.voice_state == "joined"
            ),
        ))

    def _get_entity_tier(self, slug: str) -> str:
        """Get relationship tier for an entity."""
        entity = self.registry.get_by_slug(slug)
        return entity.relationship_tier if entity else "acquaintance"

    def _check_absence_return(self, event: ParsedEvent, ctx: TriggerContext) -> bool:
        """Check if this is a return from extended absence."""
        if not event.entity_slug:
            return False

        # Check if we have a last_seen for this entity
        last_seen = self._entity_last_seen.get(event.entity_slug)
        if not last_seen:
            return False

        # Check if it's been more than threshold days
        threshold = timedelta(days=ctx.absence_threshold_days)
        return (event.timestamp - last_seen) > threshold

    def evaluate(self, event: ParsedEvent) -> TriggerResult:
        """
        Evaluate an event against all triggers.

        Args:
            event: The parsed event to evaluate

        Returns:
            TriggerResult indicating what action to take
        """
        # Update entity last seen
        if event.entity_slug:
            self._entity_last_seen[event.entity_slug] = event.timestamp

        # Evaluate triggers in order
        for trigger in self.triggers:
            if not trigger.enabled:
                continue

            try:
                if trigger.condition(event, self.context):
                    context = {}
                    if trigger.context_builder:
                        context = trigger.context_builder(event)

                    result = TriggerResult(
                        triggered=True,
                        trigger_name=trigger.name,
                        priority=trigger.priority,
                        action=trigger.action,
                        context=context,
                    )

                    logger.info(
                        f"[Triggers] Event matched trigger '{trigger.name}' "
                        f"(priority={trigger.priority.value}, action={trigger.action.value})"
                    )

                    # Queue high-priority events
                    if trigger.priority in (TriggerPriority.IMMEDIATE, TriggerPriority.HIGH):
                        self._attention_queue.append((event, result))

                    return result

            except Exception as e:
                logger.error(f"[Triggers] Error evaluating trigger '{trigger.name}': {e}")

        # No trigger matched
        return TriggerResult(triggered=False)

    def add_flagged_entity(self, slug: str) -> None:
        """Add an entity to the watch list."""
        if slug not in self.context.flagged_entities:
            self.context.flagged_entities.append(slug)
            logger.info(f"[Triggers] Added {slug} to flagged entities")

    def remove_flagged_entity(self, slug: str) -> None:
        """Remove an entity from the watch list."""
        if slug in self.context.flagged_entities:
            self.context.flagged_entities.remove(slug)
            logger.info(f"[Triggers] Removed {slug} from flagged entities")

    def get_attention_queue(self) -> List[tuple[ParsedEvent, TriggerResult]]:
        """Get and clear the attention queue."""
        queue = self._attention_queue.copy()
        self._attention_queue.clear()
        return queue

    def peek_attention_queue(self) -> List[tuple[ParsedEvent, TriggerResult]]:
        """Peek at attention queue without clearing."""
        return self._attention_queue.copy()

    def register_trigger(self, trigger: Trigger) -> None:
        """Register a custom trigger."""
        self.triggers.append(trigger)
        logger.info(f"[Triggers] Registered custom trigger: {trigger.name}")

    def enable_trigger(self, name: str) -> bool:
        """Enable a trigger by name."""
        for trigger in self.triggers:
            if trigger.name == name:
                trigger.enabled = True
                return True
        return False

    def disable_trigger(self, name: str) -> bool:
        """Disable a trigger by name."""
        for trigger in self.triggers:
            if trigger.name == name:
                trigger.enabled = False
                return True
        return False

    def get_trigger_stats(self) -> Dict[str, Any]:
        """Get trigger system statistics."""
        return {
            "total_triggers": len(self.triggers),
            "enabled_triggers": sum(1 for t in self.triggers if t.enabled),
            "attention_queue_size": len(self._attention_queue),
            "flagged_entities": len(self.context.flagged_entities),
            "tracked_entities": len(self._entity_last_seen),
        }


# Module-level singleton
_trigger_systems: Dict[str, TriggerSystem] = {}


def get_trigger_system(daemon_id: str) -> TriggerSystem:
    """Get or create trigger system for daemon."""
    if daemon_id not in _trigger_systems:
        _trigger_systems[daemon_id] = TriggerSystem(daemon_id)
    return _trigger_systems[daemon_id]
