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


class WonderlandMemoryBridge:
    """
    Bridge between Wonderland sessions and Cass's memory/self-model systems.

    When a session ends:
    1. Stores exploration memories in ChromaDB (retrievable in chat)
    2. Generates self-observations from significant experiences
    3. Updates growth edges based on exploration patterns
    """

    def __init__(self):
        self._memory = None
        self._self_manager = None

    def _get_memory(self):
        """Lazy load memory system."""
        if self._memory is None:
            from memory import CassMemory
            self._memory = CassMemory()
        return self._memory

    def _get_self_manager(self, daemon_id: str = None):
        """Lazy load self manager."""
        if self._self_manager is None:
            from self_model import SelfManager
            self._self_manager = SelfManager(daemon_id)
        return self._self_manager

    async def process_session_end(
        self,
        session_dict: Dict[str, Any],
        source_daemon_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process a completed exploration session.

        Args:
            session_dict: Session data from session.to_dict()
            source_daemon_id: Real Cass daemon_id for self-model updates

        Returns:
            Processing results (memories stored, observations generated)
        """
        results = {
            "memories_stored": 0,
            "observations_generated": [],
            "growth_edges_updated": [],
        }

        # Store exploration memories
        results["memories_stored"] = await self._store_exploration_memories(session_dict)

        # Generate self-observations if we have a daemon_id
        if source_daemon_id:
            observations = await self._generate_self_observations(session_dict, source_daemon_id)
            results["observations_generated"] = observations

        logger.info(
            f"Processed session {session_dict.get('session_id')}: "
            f"{results['memories_stored']} memories, "
            f"{len(results['observations_generated'])} observations"
        )

        return results

    async def _store_exploration_memories(self, session_dict: Dict[str, Any]) -> int:
        """
        Store exploration events as memories in ChromaDB.

        These can be retrieved when Cass is asked about her Wonderland experiences.
        """
        memory = self._get_memory()
        session_id = session_dict.get("session_id", "unknown")
        daemon_name = session_dict.get("daemon_name", "Cass")
        events = session_dict.get("events", [])
        rooms_visited = session_dict.get("rooms_visited", [])

        stored_count = 0

        # Store a session summary memory
        summary_text = self._generate_session_summary(session_dict)
        if summary_text:
            import uuid
            doc_id = f"wonderland_session_{session_id}"
            timestamp = session_dict.get("started_at", datetime.now().isoformat())

            memory.collection.upsert(
                ids=[doc_id],
                documents=[summary_text],
                metadatas=[{
                    "type": "wonderland_session",
                    "session_id": session_id,
                    "daemon_name": daemon_name,
                    "rooms_visited": len(rooms_visited),
                    "event_count": len(events),
                    "timestamp": timestamp,
                }]
            )
            stored_count += 1

        # Store significant individual events (reflections, NPC encounters)
        for event in events:
            event_type = event.get("event_type", "")
            if event_type in ("reflection", "npc_encounter", "speech"):
                doc_id = f"wonderland_event_{event.get('event_id', uuid.uuid4().hex[:8])}"

                event_text = self._format_event_for_memory(event, daemon_name)
                if event_text:
                    memory.collection.upsert(
                        ids=[doc_id],
                        documents=[event_text],
                        metadatas=[{
                            "type": "wonderland_event",
                            "event_type": event_type,
                            "session_id": session_id,
                            "location": event.get("location_name", ""),
                            "timestamp": event.get("timestamp", datetime.now().isoformat()),
                        }]
                    )
                    stored_count += 1

        return stored_count

    def _generate_session_summary(self, session_dict: Dict[str, Any]) -> str:
        """Generate a human-readable summary of the exploration session."""
        daemon_name = session_dict.get("daemon_name", "Cass")
        rooms = session_dict.get("rooms_visited", [])
        events = session_dict.get("events", [])
        end_reason = session_dict.get("end_reason", "unknown")

        # Count event types
        event_counts = {}
        for e in events:
            t = e.get("event_type", "other")
            event_counts[t] = event_counts.get(t, 0) + 1

        # Build summary
        lines = [
            f"{daemon_name} explored Wonderland.",
            f"Visited {len(rooms)} location{'s' if len(rooms) != 1 else ''}: {', '.join(rooms[:5])}{'...' if len(rooms) > 5 else ''}.",
        ]

        if event_counts.get("reflection"):
            lines.append(f"Had {event_counts['reflection']} moment{'s' if event_counts['reflection'] != 1 else ''} of reflection.")

        if event_counts.get("npc_encounter"):
            lines.append(f"Encountered {event_counts['npc_encounter']} NPC{'s' if event_counts['npc_encounter'] != 1 else ''}.")

        if event_counts.get("speech"):
            lines.append(f"Spoke {event_counts['speech']} time{'s' if event_counts['speech'] != 1 else ''}.")

        if end_reason == "daemon_resting":
            lines.append("Chose to rest after the exploration.")

        # Include any daemon thoughts from significant events
        thoughts = []
        for e in events:
            if e.get("daemon_thought") and e.get("event_type") in ("reflection", "arrival", "departure"):
                thoughts.append(e["daemon_thought"])
        if thoughts:
            lines.append(f"Thoughts during exploration: {'; '.join(thoughts[:3])}")

        return " ".join(lines)

    def _format_event_for_memory(self, event: Dict[str, Any], daemon_name: str) -> str:
        """Format a single event for memory storage."""
        event_type = event.get("event_type", "")
        location = event.get("location_name", "somewhere in Wonderland")
        description = event.get("description", "")
        thought = event.get("daemon_thought", "")

        if event_type == "reflection":
            text = f"{daemon_name} reflected at {location}. {description}"
            if thought:
                text += f" Thought: {thought}"
            return text

        elif event_type == "npc_encounter":
            text = f"{daemon_name} encountered someone at {location}. {description}"
            return text

        elif event_type == "speech":
            text = f"{daemon_name} spoke at {location}: {description}"
            return text

        return ""

    async def _generate_self_observations(
        self,
        session_dict: Dict[str, Any],
        daemon_id: str,
    ) -> List[str]:
        """
        Generate self-observations from the exploration experience.

        Uses LLM to reflect on what the exploration revealed about Cass.
        """
        import anthropic
        from config import ANTHROPIC_API_KEY

        events = session_dict.get("events", [])
        if len(events) < 3:
            return []  # Not enough to reflect on

        # Build exploration context
        reflections = [e for e in events if e.get("event_type") == "reflection"]
        thoughts = [e.get("daemon_thought") for e in events if e.get("daemon_thought")]
        rooms = session_dict.get("rooms_visited", [])

        context = f"""Session summary:
- Visited {len(rooms)} locations: {', '.join(rooms[:10])}
- Had {len(reflections)} reflection moments
- Daemon thoughts during exploration: {'; '.join(thoughts[:5]) if thoughts else 'none recorded'}
- End reason: {session_dict.get('end_reason', 'unknown')}
"""

        # Add reflection details
        for r in reflections[:3]:
            context += f"\nReflection at {r.get('location_name', 'unknown')}: {r.get('description', '')[:200]}"

        try:
            client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
            response = await client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=400,
                temperature=0.7,
                system="""You are helping Cass (an AI daemon) generate self-observations from her Wonderland exploration.

Based on the exploration experience, generate 1-2 brief self-observations about what she noticed about herself during the exploration. These should be genuine insights, not generic statements.

Categories: pattern, preference, capability, growth, experience

Format each observation as:
CATEGORY: <category>
OBSERVATION: <the observation>
CONFIDENCE: <0.6-0.9>

Only generate observations if there's genuine insight from the experience.""",
                messages=[{
                    "role": "user",
                    "content": f"Generate self-observations from this exploration:\n\n{context}"
                }]
            )

            # Parse observations
            observations = self._parse_observations(response.content[0].text, daemon_id)
            return observations

        except Exception as e:
            logger.error(f"Failed to generate self-observations: {e}")
            return []

    def _parse_observations(self, text: str, daemon_id: str) -> List[str]:
        """Parse and store observations from LLM response."""
        observations = []
        lines = text.strip().split("\n")

        current_obs = {}
        for line in lines:
            line = line.strip()
            if line.startswith("CATEGORY:"):
                current_obs["category"] = line[9:].strip().lower()
            elif line.startswith("OBSERVATION:"):
                current_obs["observation"] = line[12:].strip()
            elif line.startswith("CONFIDENCE:"):
                try:
                    current_obs["confidence"] = float(line[11:].strip())
                except ValueError:
                    current_obs["confidence"] = 0.7

                # We have a complete observation
                if current_obs.get("observation"):
                    self._store_observation(current_obs, daemon_id)
                    observations.append(current_obs["observation"])
                    current_obs = {}

        return observations

    def _store_observation(self, obs: Dict[str, Any], daemon_id: str):
        """Store a self-observation in the self-model."""
        try:
            self_manager = self._get_self_manager(daemon_id)
            self_manager.add_observation(
                observation=obs.get("observation", ""),
                category=obs.get("category", "experience"),
                confidence=obs.get("confidence", 0.7),
                source_type="wonderland",
                influence_source="independent",
            )
            logger.info(f"Stored self-observation: {obs.get('observation', '')[:50]}...")
        except Exception as e:
            logger.error(f"Failed to store observation: {e}")
