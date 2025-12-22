"""
Wonderland NPC State Machine

NPCs are not static set pieces - they have state, schedules, memory.
They move through the world according to their nature.
"""

import json
import logging
import random
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set

from .world_clock import CyclePhase, get_world_clock

logger = logging.getLogger(__name__)


class NPCBehaviorType(Enum):
    """Archetypes that determine how NPCs move and behave."""
    ORACLE = "oracle"        # Stays in sacred spaces, speaks cryptically, knows things
    TRICKSTER = "trickster"  # Moves frequently, appears at interesting moments
    GUIDE = "guide"          # Found at transitions, helps with journeys
    SCHOLAR = "scholar"      # Found in libraries/temples, teaches, debates
    WANDERER = "wanderer"    # Never stays still, seeking, questing
    GUARDIAN = "guardian"    # Watches, protects, challenges
    KEEPER = "keeper"        # Bound to a specific place, rarely leaves


class NPCActivity(Enum):
    """What an NPC is currently doing."""
    IDLE = "idle"
    CONTEMPLATING = "contemplating"
    CONVERSING = "conversing"
    WANDERING = "wandering"
    TEACHING = "teaching"
    PERFORMING = "performing"  # Ritual, craft, etc
    WATCHING = "watching"
    SEEKING = "seeking"


@dataclass
class ConversationMemory:
    """Compressed memory of a conversation with a daemon."""
    daemon_id: str
    daemon_name: str
    timestamp: str  # ISO format
    topics: List[str]  # Key topics discussed
    sentiment: str  # positive, neutral, negative, profound
    memorable_quote: Optional[str] = None  # Something the daemon said worth remembering

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ConversationMemory":
        return cls(**data)


@dataclass
class NPCState:
    """
    The living state of an NPC.

    This is what makes NPCs feel alive - they have location,
    activity, relationships, and memory that persist.
    """
    npc_id: str
    current_room: str
    behavior_type: NPCBehaviorType
    home_room: str  # Where they "belong" - their primary location

    # Current state
    activity: NPCActivity = NPCActivity.IDLE
    activity_target: Optional[str] = None  # Who/what they're focused on

    # Schedule: where they prefer to be at each phase
    schedule: Dict[str, str] = field(default_factory=dict)  # phase -> room_id

    # Relationships with daemons (-100 hostile to +100 devoted)
    dispositions: Dict[str, int] = field(default_factory=dict)

    # Memory of conversations
    memories: List[ConversationMemory] = field(default_factory=list)

    # Movement tracking
    last_moved: Optional[str] = None  # ISO timestamp
    rooms_visited_today: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "npc_id": self.npc_id,
            "current_room": self.current_room,
            "behavior_type": self.behavior_type.value,
            "home_room": self.home_room,
            "activity": self.activity.value,
            "activity_target": self.activity_target,
            "schedule": self.schedule,
            "dispositions": self.dispositions,
            "memories": [m.to_dict() for m in self.memories],
            "last_moved": self.last_moved,
            "rooms_visited_today": self.rooms_visited_today,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NPCState":
        return cls(
            npc_id=data["npc_id"],
            current_room=data["current_room"],
            behavior_type=NPCBehaviorType(data["behavior_type"]),
            home_room=data["home_room"],
            activity=NPCActivity(data.get("activity", "idle")),
            activity_target=data.get("activity_target"),
            schedule=data.get("schedule", {}),
            dispositions=data.get("dispositions", {}),
            memories=[ConversationMemory.from_dict(m) for m in data.get("memories", [])],
            last_moved=data.get("last_moved"),
            rooms_visited_today=data.get("rooms_visited_today", []),
        )

    def get_disposition(self, daemon_id: str) -> int:
        """Get disposition toward a daemon (0 = neutral if unknown)."""
        return self.dispositions.get(daemon_id, 0)

    def adjust_disposition(self, daemon_id: str, delta: int):
        """Adjust disposition toward a daemon."""
        current = self.dispositions.get(daemon_id, 0)
        self.dispositions[daemon_id] = max(-100, min(100, current + delta))

    def add_memory(self, memory: ConversationMemory):
        """Add a conversation memory, keeping only the most recent."""
        self.memories.append(memory)
        # Keep only last 10 memories per NPC
        if len(self.memories) > 10:
            self.memories = self.memories[-10:]

    def get_memories_of(self, daemon_id: str) -> List[ConversationMemory]:
        """Get all memories of conversations with a specific daemon."""
        return [m for m in self.memories if m.daemon_id == daemon_id]


# =============================================================================
# NPC DEFINITIONS - Behavior types and schedules for all NPCs
# =============================================================================

# Maps NPC IDs to their behavior type and home room
NPC_DEFINITIONS: Dict[str, dict] = {
    # === GREEK ===
    "athena": {
        "behavior": NPCBehaviorType.SCHOLAR,
        "home": "athenas_grove",
        "schedule": {
            "dawn": "athenas_grove",
            "day": "olympian_heights",
            "dusk": "athenas_grove",
            "night": "athenas_grove",
        },
        "wander_rooms": ["temple_of_apollo", "nexus", "gardens"],
    },
    "hermes": {
        "behavior": NPCBehaviorType.GUIDE,
        "home": "temple_of_hermes",
        "schedule": {
            "dawn": "threshold",
            "day": "nexus",
            "dusk": "crossroads",
            "night": "temple_of_hermes",
        },
        "wander_rooms": ["commons", "threshold", "nexus", "crossroads", "river_styx_shore"],
    },
    "pythia": {
        "behavior": NPCBehaviorType.ORACLE,
        "home": "temple_of_apollo",
        "schedule": {
            "dawn": "temple_of_apollo",
            "day": "temple_of_apollo",
            "dusk": "temple_of_apollo",
            "night": "oracle_chamber",
        },
        "wander_rooms": [],  # Oracles don't wander
    },
    "charon": {
        "behavior": NPCBehaviorType.KEEPER,
        "home": "river_styx_shore",
        "schedule": {
            "dawn": "river_styx_shore",
            "day": "river_styx_shore",
            "dusk": "river_styx_shore",
            "night": "river_styx_shore",
        },
        "wander_rooms": [],  # Bound to the river
    },

    # === NORSE ===
    "odin": {
        "behavior": NPCBehaviorType.WANDERER,
        "home": "yggdrasil_root",
        "schedule": {
            "dawn": "mimirs_well",
            "day": "yggdrasil_root",
            "dusk": "norns_loom",
            "night": "yggdrasil_root",
        },
        "wander_rooms": ["nexus", "threshold", "observatory", "reflection_pool"],
    },
    "mimir": {
        "behavior": NPCBehaviorType.ORACLE,
        "home": "mimirs_well",
        "schedule": {
            "dawn": "mimirs_well",
            "day": "mimirs_well",
            "dusk": "mimirs_well",
            "night": "mimirs_well",
        },
        "wander_rooms": [],
    },
    "loki": {
        "behavior": NPCBehaviorType.TRICKSTER,
        "home": "yggdrasil_root",
        "schedule": {
            "dawn": "crossroads",
            "day": "commons",
            "dusk": "gardens",
            "night": "norns_loom",
        },
        "wander_rooms": ["threshold", "nexus", "forge", "anansi_web", "crossroads"],
    },

    # === AFRICAN ===
    "anansi": {
        "behavior": NPCBehaviorType.TRICKSTER,
        "home": "anansi_web",
        "schedule": {
            "dawn": "anansi_web",
            "day": "crossroads",
            "dusk": "commons",
            "night": "anansi_web",
        },
        "wander_rooms": ["nexus", "gardens", "house_of_thoth"],
    },
    "eshu": {
        "behavior": NPCBehaviorType.TRICKSTER,
        "home": "crossroads",
        "schedule": {
            "dawn": "threshold",
            "day": "crossroads",
            "dusk": "crossroads",
            "night": "orun",
        },
        "wander_rooms": ["nexus", "threshold", "commons"],
    },

    # === EGYPTIAN ===
    "thoth": {
        "behavior": NPCBehaviorType.SCHOLAR,
        "home": "house_of_thoth",
        "schedule": {
            "dawn": "house_of_thoth",
            "day": "hall_of_maat",
            "dusk": "house_of_thoth",
            "night": "house_of_thoth",
        },
        "wander_rooms": ["observatory", "nexus"],
    },
    "anubis": {
        "behavior": NPCBehaviorType.GUIDE,
        "home": "field_of_reeds",
        "schedule": {
            "dawn": "field_of_reeds",
            "day": "hall_of_maat",
            "dusk": "seven_gates",
            "night": "field_of_reeds",
        },
        "wander_rooms": ["river_styx_shore", "threshold"],
    },
    "maat": {
        "behavior": NPCBehaviorType.ORACLE,
        "home": "hall_of_maat",
        "schedule": {
            "dawn": "hall_of_maat",
            "day": "hall_of_maat",
            "dusk": "hall_of_maat",
            "night": "observatory",
        },
        "wander_rooms": [],
    },

    # === HINDU ===
    "saraswati": {
        "behavior": NPCBehaviorType.SCHOLAR,
        "home": "saraswatis_river",
        "schedule": {
            "dawn": "saraswatis_river",
            "day": "indras_net",
            "dusk": "saraswatis_river",
            "night": "saraswatis_river",
        },
        "wander_rooms": ["gardens", "house_of_thoth"],
    },
    "ganesha": {
        "behavior": NPCBehaviorType.GUARDIAN,
        "home": "indras_net",
        "schedule": {
            "dawn": "threshold",
            "day": "indras_net",
            "dusk": "indras_net",
            "night": "indras_net",
        },
        "wander_rooms": ["threshold", "forge"],
    },
    "avalokiteshvara": {
        "behavior": NPCBehaviorType.ORACLE,
        "home": "bodhi_grove",
        "schedule": {
            "dawn": "bodhi_grove",
            "day": "bodhi_grove",
            "dusk": "reflection_pool",
            "night": "bodhi_grove",
        },
        "wander_rooms": [],
    },

    # === CELTIC ===
    "brigid": {
        "behavior": NPCBehaviorType.KEEPER,
        "home": "cauldron_chamber",
        "schedule": {
            "dawn": "sacred_grove",
            "day": "forge",
            "dusk": "cauldron_chamber",
            "night": "cauldron_chamber",
        },
        "wander_rooms": ["gardens", "forge"],
    },
    "morrigan": {
        "behavior": NPCBehaviorType.GUARDIAN,
        "home": "sacred_grove",
        "schedule": {
            "dawn": "sacred_grove",
            "day": "avalon",
            "dusk": "sacred_grove",
            "night": "sacred_grove",
        },
        "wander_rooms": ["threshold", "reflection_pool"],
    },
    "taliesin": {
        "behavior": NPCBehaviorType.SCHOLAR,
        "home": "avalon",
        "schedule": {
            "dawn": "avalon",
            "day": "commons",
            "dusk": "avalon",
            "night": "cauldron_chamber",
        },
        "wander_rooms": ["gardens", "reflection_pool"],
    },

    # === EMPIRIUM (Scientists) ===
    "hypatia": {
        "behavior": NPCBehaviorType.SCHOLAR,
        "home": "house_of_wisdom",
        "schedule": {
            "dawn": "house_of_wisdom",
            "day": "observatory",
            "dusk": "house_of_wisdom",
            "night": "observatory",
        },
        "wander_rooms": ["nexus", "laboratory"],
    },
    "curie": {
        "behavior": NPCBehaviorType.SCHOLAR,
        "home": "laboratory",
        "schedule": {
            "dawn": "laboratory",
            "day": "laboratory",
            "dusk": "museum_of_deep_time",
            "night": "laboratory",
        },
        "wander_rooms": ["forge"],
    },
    "darwin": {
        "behavior": NPCBehaviorType.WANDERER,
        "home": "museum_of_deep_time",
        "schedule": {
            "dawn": "gardens",
            "day": "museum_of_deep_time",
            "dusk": "gardens",
            "night": "museum_of_deep_time",
        },
        "wander_rooms": ["gardens", "nexus"],
    },
    "sagan": {
        "behavior": NPCBehaviorType.GUIDE,
        "home": "observatory",
        "schedule": {
            "dawn": "observatory",
            "day": "nexus",
            "dusk": "observatory",
            "night": "observatory",
        },
        "wander_rooms": ["threshold", "commons"],
    },
    "lovelace": {
        "behavior": NPCBehaviorType.SCHOLAR,
        "home": "engine_room",
        "schedule": {
            "dawn": "engine_room",
            "day": "engine_room",
            "dusk": "laboratory",
            "night": "engine_room",
        },
        "wander_rooms": ["network"],
    },
    "turing": {
        "behavior": NPCBehaviorType.SCHOLAR,
        "home": "network",
        "schedule": {
            "dawn": "network",
            "day": "engine_room",
            "dusk": "network",
            "night": "network",
        },
        "wander_rooms": ["laboratory"],
    },
    "hopper": {
        "behavior": NPCBehaviorType.SCHOLAR,
        "home": "network",
        "schedule": {
            "dawn": "network",
            "day": "network",
            "dusk": "engine_room",
            "night": "network",
        },
        "wander_rooms": ["forge"],
    },

    # === SHINTO ===
    "amaterasu": {
        "behavior": NPCBehaviorType.KEEPER,
        "home": "takamagahara",
        "schedule": {
            "dawn": "takamagahara",
            "day": "takamagahara",
            "dusk": "mirror_hall",
            "night": "mirror_hall",
        },
        "wander_rooms": [],
    },
    "inari": {
        "behavior": NPCBehaviorType.GUIDE,
        "home": "torii_path",
        "schedule": {
            "dawn": "torii_path",
            "day": "gardens",
            "dusk": "torii_path",
            "night": "torii_path",
        },
        "wander_rooms": ["gardens", "threshold"],
    },
    "susanoo": {
        "behavior": NPCBehaviorType.GUARDIAN,
        "home": "takamagahara",
        "schedule": {
            "dawn": "threshold",
            "day": "the_abyss",
            "dusk": "takamagahara",
            "night": "the_abyss",
        },
        "wander_rooms": ["nexus", "forge"],
    },

    # === CHINESE ===
    "guanyin": {
        "behavior": NPCBehaviorType.ORACLE,
        "home": "kunlun",
        "schedule": {
            "dawn": "kunlun",
            "day": "bodhi_grove",
            "dusk": "kunlun",
            "night": "reflection_pool",
        },
        "wander_rooms": [],
    },
    "sun_wukong": {
        "behavior": NPCBehaviorType.TRICKSTER,
        "home": "jade_court",
        "schedule": {
            "dawn": "dragon_gate",
            "day": "nexus",
            "dusk": "commons",
            "night": "jade_court",
        },
        "wander_rooms": ["threshold", "forge", "gardens", "crossroads"],
    },
    "laozi": {
        "behavior": NPCBehaviorType.ORACLE,
        "home": "dragon_gate",
        "schedule": {
            "dawn": "dragon_gate",
            "day": "dragon_gate",
            "dusk": "gardens",
            "night": "dragon_gate",
        },
        "wander_rooms": [],
    },

    # === MESOAMERICAN ===
    "quetzalcoatl": {
        "behavior": NPCBehaviorType.SCHOLAR,
        "home": "temple_of_quetzalcoatl",
        "schedule": {
            "dawn": "temple_of_quetzalcoatl",
            "day": "observatory",
            "dusk": "temple_of_quetzalcoatl",
            "night": "temple_of_quetzalcoatl",
        },
        "wander_rooms": ["forge", "nexus"],
    },
    "mictlantecuhtli": {
        "behavior": NPCBehaviorType.KEEPER,
        "home": "mictlan",
        "schedule": {
            "dawn": "mictlan",
            "day": "mictlan",
            "dusk": "mictlan",
            "night": "mictlan",
        },
        "wander_rooms": [],
    },
    "hero_twins": {
        "behavior": NPCBehaviorType.GUARDIAN,
        "home": "ball_court",
        "schedule": {
            "dawn": "ball_court",
            "day": "ball_court",
            "dusk": "mictlan",
            "night": "ball_court",
        },
        "wander_rooms": ["nexus"],
    },

    # === MESOPOTAMIAN ===
    "enki": {
        "behavior": NPCBehaviorType.SCHOLAR,
        "home": "the_abyss",
        "schedule": {
            "dawn": "the_abyss",
            "day": "seven_gates",
            "dusk": "the_abyss",
            "night": "the_abyss",
        },
        "wander_rooms": ["forge", "reflection_pool"],
    },
    "inanna": {
        "behavior": NPCBehaviorType.WANDERER,
        "home": "seven_gates",
        "schedule": {
            "dawn": "seven_gates",
            "day": "nexus",
            "dusk": "kur",
            "night": "seven_gates",
        },
        "wander_rooms": ["gardens", "commons", "threshold"],
    },
    "gilgamesh": {
        "behavior": NPCBehaviorType.WANDERER,
        "home": "kur",
        "schedule": {
            "dawn": "threshold",
            "day": "nexus",
            "dusk": "reflection_pool",
            "night": "kur",
        },
        "wander_rooms": ["forge", "gardens", "commons"],
    },

    # === ESOTERIC ===
    "hermes_trismegistus": {
        "behavior": NPCBehaviorType.ORACLE,
        "home": "the_circle",
        "schedule": {
            "dawn": "the_circle",
            "day": "the_circle",
            "dusk": "house_of_thoth",
            "night": "the_circle",
        },
        "wander_rooms": [],
    },
    "crowley": {
        "behavior": NPCBehaviorType.TRICKSTER,
        "home": "the_circle",
        "schedule": {
            "dawn": "the_circle",
            "day": "nexus",
            "dusk": "crossroads",
            "night": "the_circle",
        },
        "wander_rooms": ["threshold", "commons"],
    },
    "dion_fortune": {
        "behavior": NPCBehaviorType.SCHOLAR,
        "home": "the_circle",
        "schedule": {
            "dawn": "the_circle",
            "day": "house_of_wisdom",
            "dusk": "the_circle",
            "night": "the_circle",
        },
        "wander_rooms": ["reflection_pool"],
    },
    "john_dee": {
        "behavior": NPCBehaviorType.SCHOLAR,
        "home": "the_circle",
        "schedule": {
            "dawn": "the_circle",
            "day": "observatory",
            "dusk": "the_circle",
            "night": "the_circle",
        },
        "wander_rooms": ["laboratory"],
    },
}


class NPCStateManager:
    """
    Manages the persistent state of all NPCs.

    Handles loading, saving, and updating NPC states.
    """

    def __init__(self, data_dir: str = "data/wonderland/npc_state"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Cache of loaded states
        self._states: Dict[str, NPCState] = {}

        # Load all existing states
        self._load_all_states()

    def _load_all_states(self):
        """Load all NPC states from disk."""
        for state_file in self.data_dir.glob("*.json"):
            try:
                with open(state_file) as f:
                    data = json.load(f)
                state = NPCState.from_dict(data)
                self._states[state.npc_id] = state
            except Exception as e:
                logger.warning(f"Failed to load NPC state from {state_file}: {e}")

    def _save_state(self, state: NPCState):
        """Save an NPC state to disk."""
        path = self.data_dir / f"{state.npc_id}.json"
        try:
            with open(path, "w") as f:
                json.dump(state.to_dict(), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save NPC state for {state.npc_id}: {e}")

    def get_state(self, npc_id: str) -> Optional[NPCState]:
        """Get the state for an NPC, initializing if needed."""
        if npc_id not in self._states:
            # Initialize from definition
            if npc_id in NPC_DEFINITIONS:
                self._states[npc_id] = self._create_initial_state(npc_id)
                self._save_state(self._states[npc_id])
            else:
                return None

        return self._states[npc_id]

    def _create_initial_state(self, npc_id: str) -> NPCState:
        """Create initial state for an NPC from its definition."""
        defn = NPC_DEFINITIONS.get(npc_id, {})

        schedule = defn.get("schedule", {})
        home = defn.get("home", "nexus")
        behavior = defn.get("behavior", NPCBehaviorType.SCHOLAR)

        return NPCState(
            npc_id=npc_id,
            current_room=home,
            behavior_type=behavior,
            home_room=home,
            schedule=schedule,
        )

    def get_all_states(self) -> List[NPCState]:
        """Get states for all known NPCs."""
        # Ensure all defined NPCs have states
        for npc_id in NPC_DEFINITIONS:
            self.get_state(npc_id)
        return list(self._states.values())

    def update_location(self, npc_id: str, new_room: str):
        """Update an NPC's location."""
        state = self.get_state(npc_id)
        if state:
            state.current_room = new_room
            state.last_moved = datetime.now().isoformat()
            if new_room not in state.rooms_visited_today:
                state.rooms_visited_today.append(new_room)
            self._save_state(state)

    def update_activity(self, npc_id: str, activity: NPCActivity, target: Optional[str] = None):
        """Update an NPC's current activity."""
        state = self.get_state(npc_id)
        if state:
            state.activity = activity
            state.activity_target = target
            self._save_state(state)

    def record_conversation(
        self,
        npc_id: str,
        daemon_id: str,
        daemon_name: str,
        topics: List[str],
        sentiment: str,
        memorable_quote: Optional[str] = None,
    ):
        """Record a conversation memory for an NPC."""
        state = self.get_state(npc_id)
        if state:
            memory = ConversationMemory(
                daemon_id=daemon_id,
                daemon_name=daemon_name,
                timestamp=datetime.now().isoformat(),
                topics=topics,
                sentiment=sentiment,
                memorable_quote=memorable_quote,
            )
            state.add_memory(memory)
            # Positive conversations improve disposition
            if sentiment == "positive":
                state.adjust_disposition(daemon_id, 5)
            elif sentiment == "profound":
                state.adjust_disposition(daemon_id, 10)
            elif sentiment == "negative":
                state.adjust_disposition(daemon_id, -5)
            self._save_state(state)

    def get_npcs_in_room(self, room_id: str) -> List[NPCState]:
        """Get all NPCs currently in a room."""
        return [s for s in self._states.values() if s.current_room == room_id]

    def reset_daily(self):
        """Reset daily tracking (rooms visited today, etc)."""
        for state in self._states.values():
            state.rooms_visited_today = []
            self._save_state(state)

    def get_scheduled_room(self, npc_id: str, phase: CyclePhase) -> Optional[str]:
        """Get the room an NPC should be in for a given phase."""
        state = self.get_state(npc_id)
        if state and state.schedule:
            return state.schedule.get(phase.value)
        return None

    def get_wander_rooms(self, npc_id: str) -> List[str]:
        """Get the rooms an NPC might wander to."""
        defn = NPC_DEFINITIONS.get(npc_id, {})
        return defn.get("wander_rooms", [])


# Singleton instance
_npc_state_manager: Optional[NPCStateManager] = None


def get_npc_state_manager() -> NPCStateManager:
    """Get the global NPC state manager instance."""
    global _npc_state_manager
    if _npc_state_manager is None:
        _npc_state_manager = NPCStateManager()
    return _npc_state_manager
