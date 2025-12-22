"""
Planning Capability Source Interface.

Similar to QueryableSource (for metrics/data), this defines the interface
for subsystems that provide planning capabilities - things Cass can do,
places she can go, entities she can interact with.

Architecture parallel:
- QueryableSource: "What data do we have?" (metrics, stats, history)
- PlanningSource: "What can we do?" (actions, domains, targets)

When a system like Wonderland connects to the state bus, it registers
its planning capabilities. The GoalPlanner then queries these to generate
appropriate sub-goals and tasks for any goal type.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ActionType:
    """
    An action type that can be performed in this domain.

    Examples:
    - travel: Move to a location
    - greet: Interact with an entity
    - reflect: Contemplative action
    - examine: Inspect something closely
    """
    name: str                          # "travel", "greet", "reflect"
    description: str                   # Human-readable description
    requires_target: bool = True       # Does this action need a target?
    target_types: List[str] = field(default_factory=list)  # ["location", "npc", "item"]
    examples: List[str] = field(default_factory=list)  # Example usages for LLM
    tags: List[str] = field(default_factory=list)  # Categorical tags

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "requires_target": self.requires_target,
            "target_types": self.target_types,
            "examples": self.examples,
            "tags": self.tags,
        }


@dataclass
class Domain:
    """
    A domain or realm that can be explored/visited.

    Examples:
    - greek: The Greek mythology realm in Wonderland
    - library: A knowledge repository
    - workshop: A crafting space
    """
    name: str                          # "greek", "library"
    display_name: str                  # "Greek Mythology Realm"
    description: str                   # What is this domain?
    available_actions: List[str] = field(default_factory=list)  # Actions available here
    notable_entities: List[str] = field(default_factory=list)  # NPCs, items, etc.
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "available_actions": self.available_actions,
            "notable_entities": self.notable_entities,
            "tags": self.tags,
        }


@dataclass
class Entity:
    """
    An entity that can be interacted with.

    Examples:
    - Athena: A Greek goddess NPC
    - ancient_tome: A readable item
    - portal_greek: A travel destination
    """
    entity_id: str                     # Unique identifier
    name: str                          # Display name
    entity_type: str                   # "npc", "item", "location", "portal"
    domain: Optional[str] = None       # Which domain contains this entity
    description: Optional[str] = None  # Description for context
    available_interactions: List[str] = field(default_factory=list)  # What can be done
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "entity_type": self.entity_type,
            "domain": self.domain,
            "description": self.description,
            "available_interactions": self.available_interactions,
            "tags": self.tags,
        }


@dataclass
class PlanningSchema:
    """
    Schema describing planning capabilities of a source.

    This is what systems register with the state bus to enable
    goal planning that understands their capabilities.
    """
    source_id: str                     # "wonderland", "library", "workshop"
    display_name: str                  # "Wonderland MUD"
    description: str                   # What this system provides
    action_types: List[ActionType] = field(default_factory=list)
    domains: List[Domain] = field(default_factory=list)
    entities: List[Entity] = field(default_factory=list)
    goal_types: List[str] = field(default_factory=list)  # Goal types this source handles
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "display_name": self.display_name,
            "description": self.description,
            "action_types": [a.to_dict() for a in self.action_types],
            "domains": [d.to_dict() for d in self.domains],
            "entities": [e.to_dict() for e in self.entities],
            "goal_types": self.goal_types,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def describe_for_llm(self) -> str:
        """Generate a description for LLM context."""
        lines = [f"# {self.display_name}", f"{self.description}", ""]

        if self.domains:
            lines.append("## Available Domains")
            for d in self.domains:
                entities_str = f" (Notable: {', '.join(d.notable_entities[:3])})" if d.notable_entities else ""
                lines.append(f"- **{d.display_name}**: {d.description}{entities_str}")
            lines.append("")

        if self.action_types:
            lines.append("## Available Actions")
            for a in self.action_types:
                target_str = f" (targets: {', '.join(a.target_types)})" if a.requires_target else ""
                lines.append(f"- **{a.name}**: {a.description}{target_str}")
            lines.append("")

        if self.entities:
            # Group entities by type
            by_type: Dict[str, List[Entity]] = {}
            for e in self.entities:
                by_type.setdefault(e.entity_type, []).append(e)

            lines.append("## Entities")
            for etype, ents in by_type.items():
                lines.append(f"### {etype.title()}s")
                for e in ents[:10]:  # Limit to 10 per type
                    domain_str = f" ({e.domain})" if e.domain else ""
                    lines.append(f"- {e.name}{domain_str}")
                if len(ents) > 10:
                    lines.append(f"  ... and {len(ents) - 10} more")
            lines.append("")

        return "\n".join(lines)


class PlanningCapabilitySource(ABC):
    """
    Abstract base class for systems that provide planning capabilities.

    Implementations must provide:
    - source_id: Unique identifier
    - get_planning_schema(): Returns current capabilities
    - refresh_schema(): Update capabilities (e.g., if world state changes)

    Optional:
    - validate_action(): Check if an action is valid
    - get_route(): Get steps to reach a target
    """

    def __init__(self, daemon_id: str):
        self._daemon_id = daemon_id
        self._schema_cache: Optional[PlanningSchema] = None
        self._schema_cache_time: Optional[datetime] = None
        self._is_registered: bool = False

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Unique identifier for this source."""
        pass

    @abstractmethod
    def get_planning_schema(self) -> PlanningSchema:
        """
        Get the current planning schema.

        This describes all capabilities: actions, domains, entities.
        May be cached; call refresh_schema() to force update.
        """
        pass

    def refresh_schema(self) -> PlanningSchema:
        """
        Refresh and return updated schema.

        Override this if your schema can change dynamically
        (e.g., NPCs move, new areas unlock).
        """
        return self.get_planning_schema()

    def validate_action(
        self,
        action_type: str,
        target: Optional[str] = None,
        context: Optional[Dict] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Validate whether an action is possible.

        Returns:
            Tuple of (is_valid, error_message_if_invalid)
        """
        schema = self.get_planning_schema()

        # Check action type exists
        action = next((a for a in schema.action_types if a.name == action_type), None)
        if not action:
            return False, f"Unknown action type: {action_type}"

        # Check target if required
        if action.requires_target and not target:
            return False, f"Action '{action_type}' requires a target"

        return True, None

    def get_route(
        self,
        from_location: str,
        to_target: str,
        context: Optional[Dict] = None,
    ) -> Optional[List[Dict]]:
        """
        Get route steps from current location to target.

        Override in subclass if the system supports pathfinding.

        Returns:
            List of step dicts: [{"action": "go north", "description": "..."}]
            or None if no route found
        """
        return None

    def get_entities_by_type(self, entity_type: str) -> List[Entity]:
        """Get all entities of a specific type."""
        schema = self.get_planning_schema()
        return [e for e in schema.entities if e.entity_type == entity_type]

    def get_domain(self, domain_name: str) -> Optional[Domain]:
        """Get a specific domain by name."""
        schema = self.get_planning_schema()
        return next((d for d in schema.domains if d.name == domain_name), None)

    def on_registered(self) -> None:
        """Called when this source is registered with the state bus."""
        self._is_registered = True
        logger.info(f"Planning source '{self.source_id}' registered")

    def on_unregistered(self) -> None:
        """Called when this source is unregistered."""
        self._is_registered = False
        logger.info(f"Planning source '{self.source_id}' unregistered")
