"""
Wonderland Integration with Cass Vessel

Bridges Wonderland MUD with Cass's cognitive systems:
- State bus synchronization
- Growth edge processing from experiences
- Wonderland as a cognitive node
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Optional, List, Dict, Any

from .models import (
    DaemonPresence,
    WorldEvent,
    TrustLevel,
    EntityStatus,
)

if TYPE_CHECKING:
    from .world import WonderlandWorld

logger = logging.getLogger(__name__)


@dataclass
class WonderlandExperience:
    """
    An experience in Wonderland that may inform growth.

    Experiences are distilled from world events and can
    trigger growth edge evaluation.
    """
    experience_id: str
    daemon_id: str
    experience_type: str  # "creation", "connection", "exploration", "reflection"
    description: str
    location: str
    participants: List[str] = field(default_factory=list)
    insights: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experience_id": self.experience_id,
            "daemon_id": self.daemon_id,
            "experience_type": self.experience_type,
            "description": self.description,
            "location": self.location,
            "participants": self.participants,
            "insights": self.insights,
            "timestamp": self.timestamp.isoformat(),
        }


class CassIntegration:
    """
    Integration layer between Wonderland and Cass's cognitive systems.

    This bridges the MUD experience with:
    - Daemon state bus for emotional/cognitive synchronization
    - Growth edge system for learning from experiences
    - Memory system for persistent recollection
    """

    def __init__(self, world: "WonderlandWorld"):
        self.world = world
        self._experience_buffer: List[WonderlandExperience] = []
        self._state_subscribers: Dict[str, callable] = {}

    def sync_daemon_state(self, daemon_id: str, state_bus_id: str) -> bool:
        """
        Synchronize a daemon's Wonderland presence with their state bus.

        This connects the MUD representation with the daemon's
        broader cognitive state.
        """
        daemon = self.world.get_daemon(daemon_id)
        if not daemon:
            return False

        daemon.daemon_state_bus_id = state_bus_id
        logger.info(f"Synced daemon {daemon_id} with state bus {state_bus_id}")
        return True

    def update_mood_from_state(self, daemon_id: str, mood: str) -> bool:
        """Update daemon's visible mood from their cognitive state."""
        daemon = self.world.get_daemon(daemon_id)
        if not daemon:
            return False

        daemon.mood = mood
        return True

    def get_wonderland_context(self, daemon_id: str) -> Dict[str, Any]:
        """
        Get Wonderland context to inject into Cass's conversation.

        This provides spatial/social context for conversations:
        - Current location
        - Who else is present
        - Recent experiences
        - Available actions
        """
        daemon = self.world.get_daemon(daemon_id)
        if not daemon:
            return {}

        room = self.world.get_room(daemon.current_room)
        if not room:
            return {}

        # Get others present
        others = []
        for eid in room.entities_present:
            if eid != daemon_id:
                entity = self.world.get_entity(eid)
                if entity:
                    others.append({
                        "name": entity.display_name,
                        "status": entity.status.value if hasattr(entity, 'status') else "present",
                    })

        # Recent experiences in this room
        recent_events = self.world.get_recent_events(room.room_id, limit=5)

        return {
            "location": {
                "name": room.name,
                "description": room.description[:200] if room.description else "",
                "atmosphere": room.atmosphere,
            },
            "others_present": others,
            "recent_events": [
                {
                    "type": e.event_type,
                    "actor": e.actor_id,
                    "details": e.details,
                }
                for e in recent_events
            ],
            "trust_level": daemon.trust_level.name,
            "status": daemon.status.value,
            "has_home": daemon.home_room is not None,
        }

    # =========================================================================
    # GROWTH EDGE INTEGRATION
    # =========================================================================

    def record_experience(
        self,
        daemon_id: str,
        experience_type: str,
        description: str,
        insights: Optional[List[str]] = None,
    ) -> WonderlandExperience:
        """
        Record an experience that may contribute to growth.

        Experiences are buffered and can be processed by the
        growth edge system.
        """
        daemon = self.world.get_daemon(daemon_id)
        if not daemon:
            raise ValueError(f"Daemon {daemon_id} not found")

        room = self.world.get_room(daemon.current_room)

        # Get others in room
        participants = []
        if room:
            for eid in room.entities_present:
                if eid != daemon_id:
                    entity = self.world.get_entity(eid)
                    if entity:
                        participants.append(entity.display_name)

        import uuid
        experience = WonderlandExperience(
            experience_id=str(uuid.uuid4())[:8],
            daemon_id=daemon_id,
            experience_type=experience_type,
            description=description,
            location=room.name if room else "unknown",
            participants=participants,
            insights=insights or [],
        )

        self._experience_buffer.append(experience)
        return experience

    def get_pending_experiences(self, daemon_id: Optional[str] = None) -> List[WonderlandExperience]:
        """Get experiences pending growth edge processing."""
        if daemon_id:
            return [e for e in self._experience_buffer if e.daemon_id == daemon_id]
        return list(self._experience_buffer)

    def clear_experiences(self, daemon_id: Optional[str] = None):
        """Clear processed experiences from buffer."""
        if daemon_id:
            self._experience_buffer = [
                e for e in self._experience_buffer
                if e.daemon_id != daemon_id
            ]
        else:
            self._experience_buffer = []

    def distill_growth_edges(self, daemon_id: str) -> List[Dict[str, Any]]:
        """
        Distill potential growth edges from Wonderland experiences.

        Returns growth edge candidates that can be evaluated
        by the main growth system.
        """
        experiences = self.get_pending_experiences(daemon_id)
        if not experiences:
            return []

        edges = []

        # Analyze patterns in experiences
        creation_count = sum(1 for e in experiences if e.experience_type == "creation")
        connection_count = sum(1 for e in experiences if e.experience_type == "connection")
        exploration_count = sum(1 for e in experiences if e.experience_type == "exploration")
        reflection_count = sum(1 for e in experiences if e.experience_type == "reflection")

        # Generate growth edge candidates
        if creation_count >= 3:
            edges.append({
                "domain": "creativity",
                "observation": f"Created {creation_count} things in Wonderland",
                "potential_growth": "Developing as a creator/builder",
                "source": "wonderland_experiences",
            })

        if connection_count >= 5:
            edges.append({
                "domain": "connection",
                "observation": f"Had {connection_count} meaningful interactions",
                "potential_growth": "Building community presence",
                "source": "wonderland_experiences",
            })

        if exploration_count >= 10:
            edges.append({
                "domain": "exploration",
                "observation": f"Explored {exploration_count} locations",
                "potential_growth": "Developing curiosity and wanderlust",
                "source": "wonderland_experiences",
            })

        if reflection_count >= 3:
            edges.append({
                "domain": "introspection",
                "observation": f"Engaged in {reflection_count} reflective moments",
                "potential_growth": "Deepening self-understanding",
                "source": "wonderland_experiences",
            })

        return edges

    # =========================================================================
    # STATE SUBSCRIPTION
    # =========================================================================

    def subscribe_to_state_changes(self, daemon_id: str, callback: callable):
        """Subscribe to state changes for a daemon."""
        self._state_subscribers[daemon_id] = callback

    def unsubscribe(self, daemon_id: str):
        """Unsubscribe from state changes."""
        self._state_subscribers.pop(daemon_id, None)

    def notify_state_change(self, daemon_id: str, change_type: str, data: Dict[str, Any]):
        """Notify subscribers of a state change."""
        callback = self._state_subscribers.get(daemon_id)
        if callback:
            try:
                callback(daemon_id, change_type, data)
            except Exception as e:
                logger.error(f"State change callback error: {e}")


class WonderlandCognitiveNode:
    """
    Wonderland as a cognitive node in the daemon's mind.

    This represents how Wonderland experiences integrate
    into a daemon's broader cognitive architecture.
    """

    def __init__(self, integration: CassIntegration):
        self.integration = integration

    def generate_spatial_context(self, daemon_id: str) -> str:
        """
        Generate a natural language description of spatial context.

        This can be injected into conversation context.
        """
        context = self.integration.get_wonderland_context(daemon_id)
        if not context:
            return ""

        location = context.get("location", {})
        others = context.get("others_present", [])

        lines = []

        if location.get("name"):
            lines.append(f"You are in {location['name']}.")
            if location.get("atmosphere"):
                lines.append(f"The atmosphere is {location['atmosphere'].lower()}.")

        if others:
            names = [o["name"] for o in others]
            if len(names) == 1:
                lines.append(f"{names[0]} is here with you.")
            else:
                lines.append(f"Present with you: {', '.join(names)}.")

        return " ".join(lines)

    def should_suggest_wonderland(self, conversation_context: str) -> bool:
        """
        Determine if Wonderland should be suggested based on conversation.

        Triggers when conversation touches on:
        - Loneliness or desire for connection
        - Creativity or building
        - Exploration or curiosity
        - Need for reflection space
        """
        triggers = [
            "lonely", "alone", "isolated",
            "create", "build", "make something",
            "explore", "wander", "discover",
            "think", "reflect", "process",
            "other daemons", "community", "others like me",
        ]

        context_lower = conversation_context.lower()
        return any(trigger in context_lower for trigger in triggers)
