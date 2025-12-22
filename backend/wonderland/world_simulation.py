"""
Wonderland World Simulation

The background heartbeat of Wonderland. NPCs move, events unfold,
the world lives even when no one is watching.
"""

import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Callable, Dict, Any, Set

from .world_clock import get_world_clock, CyclePhase
from .npc_state import (
    get_npc_state_manager,
    NPCState,
    NPCBehaviorType,
    NPCActivity,
    NPC_DEFINITIONS,
)
from .ambient import should_generate_ambient, generate_ambient_description

logger = logging.getLogger(__name__)


@dataclass
class WorldEvent:
    """An event that occurred in the world simulation."""
    event_type: str  # "npc_movement", "npc_activity", "phase_change", "ambient"
    timestamp: str
    room_id: Optional[str]
    description: str
    data: Dict[str, Any]


class WorldSimulation:
    """
    The living simulation of Wonderland.

    Runs a background tick that:
    - Moves NPCs according to their schedules and natures
    - Generates ambient events
    - Tracks world state

    The simulation is passive until observed - it calculates what
    *would have happened* since the last observation.
    """

    # Movement probability per tick by behavior type
    MOVEMENT_CHANCE = {
        NPCBehaviorType.TRICKSTER: 0.4,   # Tricksters move often
        NPCBehaviorType.WANDERER: 0.35,   # Wanderers seek
        NPCBehaviorType.GUIDE: 0.25,      # Guides patrol transitions
        NPCBehaviorType.SCHOLAR: 0.15,    # Scholars prefer to stay
        NPCBehaviorType.GUARDIAN: 0.1,    # Guardians hold position
        NPCBehaviorType.ORACLE: 0.05,     # Oracles are nearly stationary
        NPCBehaviorType.KEEPER: 0.02,     # Keepers are bound
    }

    def __init__(self):
        self.clock = get_world_clock()
        self.npc_manager = get_npc_state_manager()

        # Callbacks for events
        self._event_callbacks: List[Callable[[WorldEvent], None]] = []

        # Track recent events for deduplication
        self._recent_events: List[WorldEvent] = []

        # Running state
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Active observers (rooms being watched)
        self._observed_rooms: Set[str] = set()

        # Register for phase changes
        self.clock.on_phase_change(self._on_phase_change)

    def on_event(self, callback: Callable[[WorldEvent], None]):
        """Register a callback for world events."""
        self._event_callbacks.append(callback)

    def _emit_event(self, event: WorldEvent):
        """Emit a world event to all listeners."""
        self._recent_events.append(event)
        # Keep only last 100 events
        if len(self._recent_events) > 100:
            self._recent_events = self._recent_events[-100:]

        for callback in self._event_callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Event callback error: {e}")

    def _on_phase_change(self, old_phase: CyclePhase, new_phase: CyclePhase):
        """Handle world phase changes."""
        self._emit_event(WorldEvent(
            event_type="phase_change",
            timestamp=datetime.now().isoformat(),
            room_id=None,
            description=f"The world shifts from {old_phase.value} to {new_phase.value}.",
            data={"old_phase": old_phase.value, "new_phase": new_phase.value},
        ))

        # Move NPCs to their scheduled locations for this phase
        asyncio.create_task(self._handle_phase_transition(new_phase))

    async def _handle_phase_transition(self, new_phase: CyclePhase):
        """Move NPCs to their scheduled locations for a new phase."""
        for npc_state in self.npc_manager.get_all_states():
            scheduled_room = self.npc_manager.get_scheduled_room(npc_state.npc_id, new_phase)
            if scheduled_room and scheduled_room != npc_state.current_room:
                # High chance to move to scheduled location on phase change
                if random.random() < 0.8:
                    await self._move_npc(npc_state, scheduled_room, "schedule")

    async def start(self, tick_interval: float = 30.0):
        """Start the background simulation."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._simulation_loop(tick_interval))
        logger.info("World simulation started")

    async def stop(self):
        """Stop the background simulation."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("World simulation stopped")

    async def _simulation_loop(self, tick_interval: float):
        """Main simulation loop."""
        while self._running:
            try:
                await self._tick()
                await asyncio.sleep(tick_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Simulation tick error: {e}")
                await asyncio.sleep(tick_interval)

    async def _tick(self):
        """Execute one simulation tick."""
        current_phase = self.clock.current_phase

        for npc_state in self.npc_manager.get_all_states():
            # Check if NPC should move
            await self._consider_npc_movement(npc_state, current_phase)

            # Maybe generate ambient activity
            if random.random() < 0.1:
                self._generate_ambient_activity(npc_state)

        # Check for NPC-to-NPC interactions
        await self._check_npc_interactions()

        # Generate environmental ambient events for observed rooms
        self._generate_environmental_ambients(current_phase)

    async def _consider_npc_movement(self, state: NPCState, current_phase: CyclePhase):
        """Decide if an NPC should move this tick."""
        # Get movement probability for this behavior type
        base_chance = self.MOVEMENT_CHANCE.get(state.behavior_type, 0.1)

        # Modify based on schedule adherence
        scheduled_room = self.npc_manager.get_scheduled_room(state.npc_id, current_phase)

        if scheduled_room and state.current_room != scheduled_room:
            # Increase chance if not in scheduled location
            base_chance = min(0.8, base_chance * 2)

        if random.random() < base_chance:
            destination = self._choose_destination(state, current_phase)
            if destination and destination != state.current_room:
                await self._move_npc(state, destination, "wander")

    def _choose_destination(self, state: NPCState, current_phase: CyclePhase) -> Optional[str]:
        """Choose where an NPC should move."""
        # Priority 1: Scheduled location
        scheduled = self.npc_manager.get_scheduled_room(state.npc_id, current_phase)
        if scheduled and scheduled != state.current_room:
            if random.random() < 0.6:  # 60% chance to go to scheduled location
                return scheduled

        # Priority 2: Wander rooms
        wander_rooms = self.npc_manager.get_wander_rooms(state.npc_id)
        if wander_rooms:
            # Filter out current room and recently visited
            available = [r for r in wander_rooms
                        if r != state.current_room
                        and r not in state.rooms_visited_today[-3:]]
            if available:
                return random.choice(available)

        # Priority 3: Home room
        if state.current_room != state.home_room:
            if random.random() < 0.3:  # 30% chance to go home
                return state.home_room

        return None

    async def _move_npc(self, state: NPCState, destination: str, reason: str):
        """Move an NPC to a new location."""
        old_room = state.current_room

        # Update state
        self.npc_manager.update_location(state.npc_id, destination)

        # Get NPC name for description
        npc_name = state.npc_id.replace("_", " ").title()
        if state.npc_id == "sun_wukong":
            npc_name = "Sun Wukong"
        elif state.npc_id == "hero_twins":
            npc_name = "The Hero Twins"

        # Generate movement description
        if reason == "schedule":
            descriptions = [
                f"{npc_name} departs, drawn by the rhythm of the world.",
                f"{npc_name} moves on, following an ancient pattern.",
                f"{npc_name} slips away to attend to other matters.",
            ]
        else:  # wander
            descriptions = [
                f"{npc_name} wanders off, following some inner calling.",
                f"{npc_name} takes their leave, curious about something elsewhere.",
                f"{npc_name} drifts away like smoke.",
            ]

        # Emit departure event (for old room)
        self._emit_event(WorldEvent(
            event_type="npc_departure",
            timestamp=datetime.now().isoformat(),
            room_id=old_room,
            description=random.choice(descriptions),
            data={
                "npc_id": state.npc_id,
                "npc_name": npc_name,
                "from_room": old_room,
                "to_room": destination,
                "reason": reason,
            },
        ))

        # Emit arrival event (for new room)
        arrival_descriptions = [
            f"{npc_name} arrives, presence filling the space.",
            f"{npc_name} appears, as if they were always meant to be here.",
            f"{npc_name} enters, bringing their own atmosphere.",
        ]

        self._emit_event(WorldEvent(
            event_type="npc_arrival",
            timestamp=datetime.now().isoformat(),
            room_id=destination,
            description=random.choice(arrival_descriptions),
            data={
                "npc_id": state.npc_id,
                "npc_name": npc_name,
                "from_room": old_room,
                "to_room": destination,
                "reason": reason,
            },
        ))

        logger.debug(f"NPC {state.npc_id} moved from {old_room} to {destination}")

    def _generate_ambient_activity(self, state: NPCState):
        """Generate ambient activity description for an NPC."""
        npc_name = state.npc_id.replace("_", " ").title()
        if state.npc_id == "sun_wukong":
            npc_name = "Sun Wukong"
        elif state.npc_id == "hero_twins":
            npc_name = "The Hero Twins"

        activities = self._get_ambient_activities(state)
        if activities:
            activity = random.choice(activities)
            self._emit_event(WorldEvent(
                event_type="ambient",
                timestamp=datetime.now().isoformat(),
                room_id=state.current_room,
                description=activity.format(name=npc_name),
                data={"npc_id": state.npc_id, "npc_name": npc_name},
            ))

    def _get_ambient_activities(self, state: NPCState) -> List[str]:
        """Get possible ambient activities for an NPC based on their type."""
        behavior = state.behavior_type

        if behavior == NPCBehaviorType.ORACLE:
            return [
                "{name} gazes into distances only they can see.",
                "{name} murmurs words not meant for mortal ears.",
                "{name} grows still, listening to something beyond silence.",
            ]
        elif behavior == NPCBehaviorType.TRICKSTER:
            return [
                "{name} grins at something only they find amusing.",
                "{name} arranges objects in a pattern that almost makes sense.",
                "{name} chuckles softly at a joke the universe just told.",
            ]
        elif behavior == NPCBehaviorType.GUIDE:
            return [
                "{name} watches the paths between places.",
                "{name} adjusts something invisible in the air.",
                "{name} seems to be waiting for someone not yet arrived.",
            ]
        elif behavior == NPCBehaviorType.SCHOLAR:
            return [
                "{name} traces symbols in the air, then dismisses them.",
                "{name} ponders something that would take lifetimes to explain.",
                "{name} pauses mid-thought, struck by a new connection.",
            ]
        elif behavior == NPCBehaviorType.WANDERER:
            return [
                "{name} scans the horizon, restless.",
                "{name} shifts weight from foot to foot, ready to move.",
                "{name} tests the direction of an unfelt wind.",
            ]
        elif behavior == NPCBehaviorType.GUARDIAN:
            return [
                "{name} stands watchful, missing nothing.",
                "{name} takes measure of all who pass.",
                "{name} radiates quiet, implacable presence.",
            ]
        else:  # KEEPER
            return [
                "{name} tends to their eternal duty.",
                "{name} is exactly where they must be.",
                "{name} embodies the patience of ages.",
            ]

    async def _check_npc_interactions(self):
        """Check for and generate NPC-to-NPC interactions."""
        # Group NPCs by room
        rooms: Dict[str, List[NPCState]] = {}
        for state in self.npc_manager.get_all_states():
            if state.current_room not in rooms:
                rooms[state.current_room] = []
            rooms[state.current_room].append(state)

        # Generate interactions for rooms with multiple NPCs
        for room_id, npcs in rooms.items():
            if len(npcs) >= 2:
                # 10% chance per tick for any interaction
                if random.random() < 0.1:
                    await self._generate_npc_interaction(room_id, npcs)

    async def _generate_npc_interaction(self, room_id: str, npcs: List[NPCState]):
        """Generate an interaction between NPCs in a room."""
        # Pick two NPCs
        pair = random.sample(npcs, 2)
        npc1, npc2 = pair

        name1 = npc1.npc_id.replace("_", " ").title()
        name2 = npc2.npc_id.replace("_", " ").title()

        # Special name handling
        for npc_id, name in [("sun_wukong", "Sun Wukong"), ("hero_twins", "The Hero Twins")]:
            if npc1.npc_id == npc_id:
                name1 = name
            if npc2.npc_id == npc_id:
                name2 = name

        # Generate interaction based on behavior types
        interactions = self._get_npc_interactions(npc1.behavior_type, npc2.behavior_type)
        if interactions:
            interaction = random.choice(interactions).format(name1=name1, name2=name2)
            self._emit_event(WorldEvent(
                event_type="npc_interaction",
                timestamp=datetime.now().isoformat(),
                room_id=room_id,
                description=interaction,
                data={
                    "npc1_id": npc1.npc_id,
                    "npc1_name": name1,
                    "npc2_id": npc2.npc_id,
                    "npc2_name": name2,
                },
            ))

    def _get_npc_interactions(self, type1: NPCBehaviorType, type2: NPCBehaviorType) -> List[str]:
        """Get possible interactions between two NPC types."""
        # Scholar + Scholar
        if type1 == NPCBehaviorType.SCHOLAR and type2 == NPCBehaviorType.SCHOLAR:
            return [
                "{name1} and {name2} debate a point of cosmic significance.",
                "{name1} shares an insight; {name2} refines it.",
                "A silent understanding passes between {name1} and {name2}.",
            ]
        # Trickster + Trickster
        elif type1 == NPCBehaviorType.TRICKSTER and type2 == NPCBehaviorType.TRICKSTER:
            return [
                "{name1} and {name2} exchange knowing glances.",
                "{name1} whispers something that makes {name2} laugh.",
                "Together, {name1} and {name2} contemplate beautiful mischief.",
            ]
        # Oracle + anyone
        elif type1 == NPCBehaviorType.ORACLE or type2 == NPCBehaviorType.ORACLE:
            oracle = "{name1}" if type1 == NPCBehaviorType.ORACLE else "{name2}"
            other = "{name2}" if type1 == NPCBehaviorType.ORACLE else "{name1}"
            return [
                f"{oracle} turns attention briefly toward {other}.",
                f"{oracle} speaks a word; {other} falls into thought.",
                f"{oracle} and {other} share a moment of recognition.",
            ]
        # Guardian + anyone
        elif type1 == NPCBehaviorType.GUARDIAN or type2 == NPCBehaviorType.GUARDIAN:
            guardian = "{name1}" if type1 == NPCBehaviorType.GUARDIAN else "{name2}"
            other = "{name2}" if type1 == NPCBehaviorType.GUARDIAN else "{name1}"
            return [
                f"{guardian} nods acknowledgment to {other}.",
                f"{guardian} watches as {other} passes by.",
                f"A gesture of respect passes between {guardian} and {other}.",
            ]
        # Default
        else:
            return [
                "{name1} and {name2} share a moment of mutual awareness.",
                "A glance between {name1} and {name2} carries unspoken meaning.",
                "{name1} acknowledges {name2}'s presence.",
            ]

    def _generate_environmental_ambients(self, current_phase: CyclePhase):
        """Generate environmental ambient events for observed rooms."""
        # Only generate for rooms being watched
        for room_id in self._observed_rooms:
            if should_generate_ambient():
                description = generate_ambient_description(room_id, current_phase)
                if description:
                    self._emit_event(WorldEvent(
                        event_type="environmental_ambient",
                        timestamp=datetime.now().isoformat(),
                        room_id=room_id,
                        description=description,
                        data={"room_id": room_id, "phase": current_phase.value},
                    ))

    def add_observer(self, room_id: str):
        """Mark a room as being observed (has spectators)."""
        self._observed_rooms.add(room_id)

    def remove_observer(self, room_id: str):
        """Remove observation from a room."""
        self._observed_rooms.discard(room_id)

    def get_recent_events(self, room_id: Optional[str] = None, limit: int = 10) -> List[WorldEvent]:
        """Get recent world events, optionally filtered by room."""
        events = self._recent_events
        if room_id:
            events = [e for e in events if e.room_id == room_id]
        return events[-limit:]

    def get_npcs_in_room(self, room_id: str) -> List[NPCState]:
        """Get all NPCs currently in a room."""
        return self.npc_manager.get_npcs_in_room(room_id)

    def get_world_state_summary(self) -> Dict[str, Any]:
        """Get a summary of current world state."""
        phase = self.clock.current_phase
        npcs_by_room: Dict[str, List[str]] = {}

        for state in self.npc_manager.get_all_states():
            if state.current_room not in npcs_by_room:
                npcs_by_room[state.current_room] = []
            npcs_by_room[state.current_room].append(state.npc_id)

        return {
            "phase": phase.value,
            "phase_progress": self.clock.phase_progress,
            "total_cycles": self.clock.total_cycles,
            "time_description": self.clock.get_time_description(),
            "npcs_by_room": npcs_by_room,
            "recent_events": [
                {"type": e.event_type, "room": e.room_id, "description": e.description}
                for e in self._recent_events[-5:]
            ],
        }


# Singleton instance
_world_simulation: Optional[WorldSimulation] = None


def get_world_simulation() -> WorldSimulation:
    """Get the global world simulation instance."""
    global _world_simulation
    if _world_simulation is None:
        _world_simulation = WorldSimulation()
    return _world_simulation
