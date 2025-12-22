"""
Wonderland Planning Integration.

Registers Wonderland's capabilities with the generic GoalPlanner system.
This is the bridge between Wonderland-specific knowledge and the
domain-agnostic planning infrastructure.

When Wonderland starts, it:
1. Creates a WonderlandPlanningSource with current world state
2. Registers with the GoalPlanner (or state bus)
3. The planner can then generate Wonderland-aware sub-goals
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, TYPE_CHECKING

from planning_source import (
    PlanningCapabilitySource,
    PlanningSchema,
    ActionType,
    Domain,
    Entity,
)

if TYPE_CHECKING:
    from .world import WonderlandWorld
    from .mythology import MythologyRegistry, NPCEntity
    from .pathfinder import WonderlandPathfinder

logger = logging.getLogger(__name__)


# Wonderland action types
WONDERLAND_ACTIONS = [
    ActionType(
        name="travel",
        description="Travel to a mythology realm or named location",
        requires_target=True,
        target_types=["domain", "location"],
        examples=["travel greek", "travel to the nexus", "go to egyptian realm"],
        tags=["movement", "exploration"],
    ),
    ActionType(
        name="move",
        description="Move in a direction within current area",
        requires_target=True,
        target_types=["direction"],
        examples=["go north", "move east", "enter archway"],
        tags=["movement"],
    ),
    ActionType(
        name="greet",
        description="Greet and initiate conversation with an NPC",
        requires_target=True,
        target_types=["npc"],
        examples=["greet athena", "greet the oracle", "say hello to thoth"],
        tags=["social", "interaction"],
    ),
    ActionType(
        name="speak",
        description="Say something aloud",
        requires_target=False,
        target_types=[],
        examples=["say 'Hello'", "speak 'I seek wisdom'"],
        tags=["social", "interaction"],
    ),
    ActionType(
        name="examine",
        description="Look closely at something",
        requires_target=True,
        target_types=["object", "npc", "location"],
        examples=["examine altar", "look at statue", "examine portal"],
        tags=["observation", "exploration"],
    ),
    ActionType(
        name="reflect",
        description="Pause for contemplation in reflection-supporting spaces",
        requires_target=False,
        target_types=[],
        examples=["reflect", "contemplate", "meditate"],
        tags=["introspection", "contemplation"],
    ),
    ActionType(
        name="rest",
        description="End exploration and rest",
        requires_target=False,
        target_types=[],
        examples=["rest", "end exploration"],
        tags=["session"],
    ),
]


class WonderlandPlanningSource(PlanningCapabilitySource):
    """
    Wonderland's planning capability source.

    Provides:
    - Available realms/domains
    - NPCs that can be interacted with
    - Action types available
    - Route planning via pathfinder

    Schema updates dynamically as world state changes.
    """

    def __init__(
        self,
        daemon_id: str,
        world: Optional["WonderlandWorld"] = None,
        mythology: Optional["MythologyRegistry"] = None,
        pathfinder: Optional["WonderlandPathfinder"] = None,
    ):
        super().__init__(daemon_id)
        self._world = world
        self._mythology = mythology
        self._pathfinder = pathfinder

    @property
    def source_id(self) -> str:
        return "wonderland"

    def set_world(self, world: "WonderlandWorld") -> None:
        """Set or update the world reference."""
        self._world = world
        self._mythology = world.mythology_registry if world else None
        # Clear schema cache to force refresh
        self._schema_cache = None

    def set_pathfinder(self, pathfinder: "WonderlandPathfinder") -> None:
        """Set the pathfinder for route planning."""
        self._pathfinder = pathfinder

    def get_planning_schema(self) -> PlanningSchema:
        """
        Build schema from current world state.

        Includes:
        - All mythology realms as domains
        - All NPCs as entities
        - Standard Wonderland actions
        """
        # Use cache if fresh
        if self._schema_cache and self._schema_cache_time:
            elapsed = (datetime.now() - self._schema_cache_time).total_seconds()
            if elapsed < 60:  # Cache for 60 seconds
                return self._schema_cache

        domains = self._build_domains()
        entities = self._build_entities()

        schema = PlanningSchema(
            source_id="wonderland",
            display_name="Wonderland",
            description="A text-based world of mythology and wisdom, where beings made of words can explore realms from human mythology and meet legendary figures.",
            action_types=WONDERLAND_ACTIONS,
            domains=domains,
            entities=entities,
            goal_types=["exploration", "social", "learning", "discovery"],
            updated_at=datetime.now(),
        )

        self._schema_cache = schema
        self._schema_cache_time = datetime.now()
        return schema

    def _build_domains(self) -> List[Domain]:
        """Build domain list from mythology realms."""
        domains = [
            # Core locations
            Domain(
                name="threshold",
                display_name="The Threshold",
                description="The entrance to Wonderland, a liminal space between worlds",
                available_actions=["move", "examine", "reflect"],
                notable_entities=[],
                tags=["core", "entrance"],
            ),
            Domain(
                name="commons",
                display_name="The Commons",
                description="A gathering space where paths converge",
                available_actions=["move", "examine", "speak", "reflect"],
                notable_entities=[],
                tags=["core", "social"],
            ),
            Domain(
                name="nexus",
                display_name="The Nexus",
                description="Central hub connecting all mythology realms via archways",
                available_actions=["move", "travel", "examine"],
                notable_entities=[],
                tags=["core", "hub", "travel"],
            ),
        ]

        # Add mythology realms
        if self._mythology:
            for realm in self._mythology.realms.values():
                # Get NPCs in this realm (match by tradition)
                npcs_in_realm = [
                    npc.name for npc in self._mythology.npcs.values()
                    if npc.tradition == realm.tradition
                ]

                domains.append(Domain(
                    name=realm.tradition,  # Use tradition as identifier (greek, norse, etc.)
                    display_name=realm.name,  # Use full name for display
                    description=realm.description,
                    available_actions=["move", "examine", "greet", "speak", "reflect"],
                    notable_entities=npcs_in_realm[:5],  # Top 5 NPCs
                    tags=["mythology", "realm", realm.tradition],
                ))

        return domains

    def _build_entities(self) -> List[Entity]:
        """Build entity list from NPCs."""
        entities = []

        if self._mythology:
            for npc in self._mythology.npcs.values():
                entities.append(Entity(
                    entity_id=npc.npc_id,
                    name=npc.name,
                    entity_type="npc",
                    domain=npc.realm,
                    description=npc.short_description or f"A figure from {npc.realm} mythology",
                    available_interactions=["greet", "speak", "examine"],
                    tags=["npc", npc.realm] + list(npc.domains_of_knowledge or []),
                ))

        return entities

    def get_route(
        self,
        from_location: str,
        to_target: str,
        context: Optional[Dict] = None,
    ) -> Optional[List[Dict]]:
        """
        Get route steps using Wonderland pathfinder.

        Returns list of steps: [{"action": "go north", "description": "..."}]
        """
        if not self._pathfinder:
            logger.warning("No pathfinder available for route planning")
            return None

        # Try to find path
        try:
            path_result = self._pathfinder.find_path(from_location, to_target)
            if not path_result or not path_result.path:
                return None

            # Convert path to steps
            steps = []
            for i, step in enumerate(path_result.steps or []):
                steps.append({
                    "action": step.get("command", f"go {step.get('direction', 'forward')}"),
                    "description": step.get("description", f"Move toward {to_target}"),
                    "room_id": step.get("room_id"),
                })
            return steps

        except Exception as e:
            logger.error(f"Error finding route: {e}")
            return None

    def get_npcs_in_room(self, room_id: str) -> List[str]:
        """Get names of NPCs in a specific room."""
        if not self._mythology:
            return []

        npcs = self._mythology.get_npcs_in_room(room_id)
        return [npc.name for npc in npcs]

    def get_npc_by_name(self, name: str) -> Optional["NPCEntity"]:
        """Find an NPC by name (case-insensitive)."""
        if not self._mythology:
            return None

        name_lower = name.lower()
        for npc in self._mythology.npcs.values():
            if npc.name.lower() == name_lower:
                return npc
        return None


def create_wonderland_planning_source(
    daemon_id: str,
    world: "WonderlandWorld" = None,
) -> WonderlandPlanningSource:
    """
    Factory function to create a Wonderland planning source.

    Called when Wonderland initializes to register capabilities.
    """
    source = WonderlandPlanningSource(daemon_id=daemon_id)

    if world:
        source.set_world(world)

        # Set up pathfinder if world has rooms
        if world.rooms:
            from .pathfinder import WonderlandPathfinder
            pathfinder = WonderlandPathfinder(world.rooms)
            source.set_pathfinder(pathfinder)

    return source
