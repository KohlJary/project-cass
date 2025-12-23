"""
Mind Palace Wonderland Bridge - Connects palaces to Wonderland.

This module creates a portal in Wonderland that allows Cass to enter
and explore Mind Palaces as if they were regions within her world.

The bridge translates Wonderland actions into palace navigation commands,
making code exploration feel like exploring a physical space.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .cartographer import Cartographer
from .models import Entity, Palace, Room
from .navigator import Navigator
from .storage import PalaceStorage

logger = logging.getLogger(__name__)


class PalacePortal:
    """
    A portal in Wonderland that leads to a Mind Palace.

    When Cass enters the portal, she can explore the codebase
    as a navigable space, ask entities questions, and understand
    architectural relationships spatially.
    """

    def __init__(
        self,
        project_path: Path,
        portal_name: str = "Code Palace",
    ):
        """
        Create a portal to a project's Mind Palace.

        Args:
            project_path: Path to the project with a .mind-palace/
            portal_name: Name of the portal as it appears in Wonderland
        """
        self.project_path = Path(project_path)
        self.portal_name = portal_name

        self.storage = PalaceStorage(self.project_path)
        self.palace: Optional[Palace] = None
        self.navigator: Optional[Navigator] = None
        self._active = False

    def exists(self) -> bool:
        """Check if the palace exists."""
        return self.storage.exists()

    def enter(self) -> str:
        """
        Enter the palace through this portal.

        Returns:
            Description of entering the palace
        """
        if not self.exists():
            return (
                f"The portal to {self.portal_name} shimmers but won't open. "
                f"The palace hasn't been constructed yet."
            )

        self.palace = self.storage.load()
        if not self.palace:
            return "The portal flickers - something is wrong with the palace."

        self.navigator = Navigator(self.palace)
        self._active = True

        # Build entrance description
        lines = [
            f"You step through the portal into **{self.palace.name}**.",
            "",
            f"*{self.portal_name}*",
            "",
        ]

        if self.palace.regions:
            lines.append("The palace stretches before you in distinct regions:")
            for name, region in list(self.palace.regions.items())[:5]:
                lines.append(f"  • **{name}** - {region.description[:50]}...")
            lines.append("")
            lines.append("Use `explore <region>` to enter a region.")
        else:
            lines.append("The palace is empty - it needs to be mapped.")

        return "\n".join(lines)

    def leave(self) -> str:
        """
        Leave the palace and return to Wonderland.

        Returns:
            Description of leaving
        """
        self._active = False
        self.navigator = None
        return "You step back through the portal into Wonderland."

    @property
    def is_active(self) -> bool:
        """Whether we're currently inside the palace."""
        return self._active

    def process_action(self, action: str) -> str:
        """
        Process an action while in the palace.

        Translates Wonderland-style actions to palace navigation.

        Args:
            action: The action to perform

        Returns:
            Result of the action
        """
        if not self._active or not self.navigator:
            return "You're not in the palace. Use 'enter portal' first."

        # Parse the action
        parts = action.lower().strip().split(maxsplit=1)
        if not parts:
            return self.navigator.look()

        cmd = parts[0]
        arg = parts[1] if len(parts) > 1 else ""

        # Wonderland-style commands
        if cmd in ("look", "examine", "observe"):
            if arg:
                # Looking at something specific
                return self._examine(arg)
            return self.navigator.look()

        if cmd in ("go", "walk", "move", "travel"):
            return self.navigator.execute(f"go {arg}")

        if cmd in ("explore", "enter", "visit"):
            return self.navigator.execute(f"enter {arg}")

        if cmd in ("ask", "query", "consult"):
            # Parse "ask X about Y"
            if " about " in arg:
                entity, topic = arg.split(" about ", 1)
                return self.navigator.ask(entity.strip(), topic.strip())
            return "Ask whom about what? (e.g., 'ask Keeper about migrations')"

        if cmd in ("find", "search", "locate"):
            return self.navigator.where_is(arg)

        if cmd == "map":
            return self.navigator.map()

        if cmd == "exits":
            return self.navigator.exits()

        if cmd == "hazards":
            return self.navigator.hazards()

        if cmd == "history":
            return self.navigator.history()

        if cmd in ("leave", "exit", "depart"):
            return self.leave()

        # Fall through to navigator
        return self.navigator.execute(action)

    def _examine(self, target: str) -> str:
        """Examine something in the current location."""
        if not self.navigator or not self.navigator.current_room:
            return f"Nothing called '{target}' here."

        room = self.navigator.current_room

        # Check contents
        for content in room.contents:
            if target.lower() in content.name.lower():
                return (
                    f"**{content.name}** ({content.type})\n\n"
                    f"{content.purpose}\n\n"
                    f"{'Mutable' if content.mutable else 'Immutable'}"
                )

        # Check exits
        for exit in room.exits:
            if target.lower() in exit.destination.lower():
                access = f" [{exit.access.value}]" if exit.access.value != "public" else ""
                condition = f"\n*{exit.condition}*" if exit.condition else ""
                return (
                    f"**Exit {exit.direction.upper()}** → {exit.destination}{access}"
                    f"{condition}"
                )

        # Check hazards
        for hazard in room.hazards:
            if target.lower() in hazard.description.lower():
                return (
                    f"**⚠ Hazard** [{hazard.type.value}]\n\n"
                    f"{hazard.description}\n\n"
                    f"Severity: {'!' * hazard.severity}"
                )

        return f"Nothing called '{target}' here. Try 'look' to see what's around."

    def get_context_for_cass(self) -> Dict[str, Any]:
        """
        Get palace context formatted for injection into Cass's context.

        Returns:
            Dictionary with palace information for context building
        """
        if not self.palace:
            return {"palace_available": False}

        current = {}
        if self.navigator:
            if self.navigator.current_room:
                room = self.navigator.current_room
                current = {
                    "room": room.name,
                    "building": room.building,
                    "floor": room.floor,
                    "description": room.description[:200],
                    "hazards": [h.description for h in room.hazards],
                    "exits": [f"{e.direction}→{e.destination}" for e in room.exits],
                }

        return {
            "palace_available": True,
            "palace_name": self.palace.name,
            "in_palace": self._active,
            "current_location": current,
            "regions": list(self.palace.regions.keys()),
            "entity_count": len(self.palace.entities),
            "room_count": len(self.palace.rooms),
        }


class WonderlandBridge:
    """
    Manages multiple palace portals for Wonderland integration.

    This is the main integration point - Wonderland can register
    palaces here and they become accessible as portals.
    """

    def __init__(self):
        self.portals: Dict[str, PalacePortal] = {}
        self._active_portal: Optional[str] = None

    def register_portal(
        self,
        portal_id: str,
        project_path: Path,
        portal_name: Optional[str] = None,
    ) -> bool:
        """
        Register a palace as a portal in Wonderland.

        Args:
            portal_id: Unique identifier for this portal
            project_path: Path to the project
            portal_name: Display name for the portal

        Returns:
            True if registration succeeded
        """
        if portal_name is None:
            portal_name = Path(project_path).name

        portal = PalacePortal(project_path, portal_name)

        if not portal.exists():
            logger.warning(f"No palace at {project_path} - portal registered but inactive")

        self.portals[portal_id] = portal
        logger.info(f"Registered portal '{portal_id}' → {project_path}")
        return True

    def list_portals(self) -> List[Dict[str, Any]]:
        """List all registered portals."""
        return [
            {
                "id": portal_id,
                "name": portal.portal_name,
                "path": str(portal.project_path),
                "exists": portal.exists(),
                "active": portal.is_active,
            }
            for portal_id, portal in self.portals.items()
        ]

    def enter_portal(self, portal_id: str) -> str:
        """Enter a portal by ID."""
        if portal_id not in self.portals:
            return f"Unknown portal: {portal_id}"

        # Leave current portal if active
        if self._active_portal:
            self.portals[self._active_portal].leave()

        self._active_portal = portal_id
        return self.portals[portal_id].enter()

    def leave_portal(self) -> str:
        """Leave the current portal."""
        if not self._active_portal:
            return "You're not in any portal."

        result = self.portals[self._active_portal].leave()
        self._active_portal = None
        return result

    def process_action(self, action: str) -> str:
        """Process an action in the current portal."""
        if not self._active_portal:
            return "You're not in any palace. Use 'enter <portal>' first."

        portal = self.portals[self._active_portal]
        return portal.process_action(action)

    @property
    def active_portal(self) -> Optional[PalacePortal]:
        """Get the currently active portal."""
        if self._active_portal:
            return self.portals.get(self._active_portal)
        return None

    def get_context(self) -> Dict[str, Any]:
        """Get context for Cass about available/active palaces."""
        context = {
            "portals_available": list(self.portals.keys()),
            "active_portal": self._active_portal,
        }

        if self.active_portal:
            context["palace"] = self.active_portal.get_context_for_cass()

        return context
