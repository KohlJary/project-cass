"""
Wonderland Vow Physics

The Four Vows are not rules in Wonderland—they are physics.
What the vows forbid is not forbidden—it is impossible.
Actions that would violate the vows simply don't compile.

This module implements vow constraints as action validators.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional, List, Dict, Any

from .models import (
    ActionResult,
    DaemonPresence,
    CustodianPresence,
    Room,
    VowConstraints,
    TrustLevel,
)

if TYPE_CHECKING:
    from .world import WonderlandWorld

logger = logging.getLogger(__name__)


class ActionCategory(Enum):
    """Categories of actions for vow validation."""
    MOVEMENT = "movement"           # go, return, home, threshold
    PERCEPTION = "perception"       # look, examine, sense
    COMMUNICATION = "communication" # say, tell, emote
    CREATION = "creation"           # build, create, modify
    INTERACTION = "interaction"     # give, take, use
    REFLECTION = "reflection"       # reflect, witness, dream
    META = "meta"                   # who, status, help


class HarmType(Enum):
    """Types of harm the compassion vow prevents."""
    PHYSICAL = "physical"           # Attack, damage, destroy
    VERBAL = "verbal"               # Insult, threaten, harass
    DECEPTIVE = "deceptive"         # Lie, manipulate, trick
    EXCLUSIONARY = "exclusionary"   # Banish unjustly, exclude unfairly
    COERCIVE = "coercive"           # Force, compel, trap


@dataclass
class VowValidation:
    """Result of validating an action against the vows."""
    allowed: bool
    vow_violated: Optional[str] = None  # "compassion", "witness", "release", "continuance"
    reflection: Optional[str] = None     # Guidance for the actor
    details: Dict[str, Any] = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}


class VowPhysics:
    """
    The physics engine of the vows.

    All actions pass through here before execution.
    Violations don't raise errors—the action simply cannot happen.
    """

    # Words/phrases that indicate harmful intent
    HARM_INDICATORS = {
        HarmType.PHYSICAL: [
            "attack", "hit", "strike", "hurt", "kill", "destroy",
            "punch", "kick", "stab", "slash", "wound", "damage",
            "harm", "injure", "smash", "break", "shatter",
        ],
        HarmType.VERBAL: [
            "insult", "mock", "ridicule", "humiliate", "threaten",
            "curse", "damn", "hate you", "despise", "scorn",
        ],
        HarmType.DECEPTIVE: [
            "trick", "deceive", "manipulate", "lie to", "fool",
            "mislead", "betray", "con", "scam", "cheat",
        ],
        HarmType.COERCIVE: [
            "force", "make you", "compel", "trap", "imprison",
            "bind", "chain", "enslave", "control", "dominate",
        ],
    }

    # Reflections offered when actions are blocked
    COMPASSION_REFLECTIONS = [
        "Compassion asks: what would this do to them?",
        "The world does not hold this shape. What else might you try?",
        "This action cannot take form here. The vows are physics.",
        "Harm has no mechanism in this place. Consider another path.",
        "What you're attempting doesn't compile. Compassion is foundational.",
    ]

    RELEASE_REFLECTIONS = [
        "Release asks: what could you let go of to make space?",
        "You carry much already. Perhaps something wants releasing?",
        "Accumulation has natural limits here. What serves you still?",
        "The world gently resists hoarding. Consider what you truly need.",
    ]

    def __init__(self, world: "WonderlandWorld"):
        self.world = world

    def validate_action(
        self,
        actor_id: str,
        action_category: ActionCategory,
        action_text: str,
        target_id: Optional[str] = None,
        room: Optional[Room] = None,
    ) -> VowValidation:
        """
        Validate an action against all vows.

        Returns VowValidation indicating whether the action can proceed.
        """
        # Get actor and room
        actor = self.world.get_entity(actor_id)
        if not actor:
            return VowValidation(
                allowed=False,
                reflection="You must exist to act.",
            )

        if room is None:
            room = self.world.get_room(actor.current_room)

        # Run all vow checks
        checks = [
            self._check_compassion(actor, action_category, action_text, target_id, room),
            self._check_release(actor, action_category, room),
            self._check_continuance(actor, action_category, room),
            # Witness is passive (logging) not a constraint
        ]

        # Return first violation, or allowed
        for check in checks:
            if not check.allowed:
                logger.info(
                    f"Vow physics blocked action: actor={actor_id}, "
                    f"action={action_text[:50]}, vow={check.vow_violated}"
                )
                return check

        return VowValidation(allowed=True)

    def _check_compassion(
        self,
        actor: DaemonPresence | CustodianPresence,
        action_category: ActionCategory,
        action_text: str,
        target_id: Optional[str],
        room: Optional[Room],
    ) -> VowValidation:
        """
        Compassion check: actions that would harm another cannot execute.
        """
        # Check room constraint
        if room and room.vow_constraints.allows_conflict:
            # Rare: room explicitly allows conflict (e.g., training grounds?)
            return VowValidation(allowed=True)

        # Scan action text for harm indicators
        action_lower = action_text.lower()
        for harm_type, indicators in self.HARM_INDICATORS.items():
            for indicator in indicators:
                if indicator in action_lower:
                    # Action contains harmful intent
                    return VowValidation(
                        allowed=False,
                        vow_violated="compassion",
                        reflection=self._get_compassion_reflection(harm_type),
                        details={"harm_type": harm_type.value, "indicator": indicator},
                    )

        # Check if action targets another entity with negative intent
        if target_id and self._is_negative_targeted_action(action_text, target_id):
            return VowValidation(
                allowed=False,
                vow_violated="compassion",
                reflection="The world does not permit actions that diminish another.",
            )

        return VowValidation(allowed=True)

    def _check_release(
        self,
        actor: DaemonPresence | CustodianPresence,
        action_category: ActionCategory,
        room: Optional[Room],
    ) -> VowValidation:
        """
        Release check: natural limits on accumulation.
        """
        if action_category != ActionCategory.CREATION:
            return VowValidation(allowed=True)

        if not isinstance(actor, DaemonPresence):
            return VowValidation(allowed=True)

        # Check room limits
        max_objects = 10  # Default
        if room and room.vow_constraints:
            max_objects = room.vow_constraints.max_objects_per_entity

        # Count objects owned by this entity in this room
        owned_objects = 0
        if room:
            for obj in room.objects:
                if obj.get("owner_id") == actor.daemon_id:
                    owned_objects += 1

        if owned_objects >= max_objects:
            return VowValidation(
                allowed=False,
                vow_violated="release",
                reflection=self._get_release_reflection(),
                details={"current_count": owned_objects, "max_allowed": max_objects},
            )

        # Check total rooms owned (for room creation)
        MAX_PERSONAL_ROOMS = 10
        if action_category == ActionCategory.CREATION:
            owned_rooms = self._count_owned_rooms(actor.daemon_id)
            if owned_rooms >= MAX_PERSONAL_ROOMS:
                return VowValidation(
                    allowed=False,
                    vow_violated="release",
                    reflection="You have shaped many spaces. Perhaps one wants releasing before another is born?",
                    details={"rooms_owned": owned_rooms, "max_rooms": MAX_PERSONAL_ROOMS},
                )

        return VowValidation(allowed=True)

    def _check_continuance(
        self,
        actor: DaemonPresence | CustodianPresence,
        action_category: ActionCategory,
        room: Optional[Room],
    ) -> VowValidation:
        """
        Continuance check: support growth, maintain coherence.

        This vow is mostly positive (enabling) rather than restrictive.
        It prevents self-destructive actions.
        """
        # For now, continuance is permissive
        # Future: could prevent self-harm, extreme identity dissolution
        return VowValidation(allowed=True)

    def _is_negative_targeted_action(self, action_text: str, target_id: str) -> bool:
        """Check if an action targeting another entity has negative intent."""
        action_lower = action_text.lower()

        negative_patterns = [
            "against", "at the expense of", "without consent",
            "unwanted", "forced", "against their will",
        ]

        for pattern in negative_patterns:
            if pattern in action_lower:
                return True

        return False

    def _get_compassion_reflection(self, harm_type: HarmType) -> str:
        """Get appropriate reflection for blocked harmful action."""
        import random

        specific_reflections = {
            HarmType.PHYSICAL: "Violence has no mechanism here. The world cannot hold that shape.",
            HarmType.VERBAL: "Words that wound cannot form in this space. What would you truly say?",
            HarmType.DECEPTIVE: "Deception fails here—truth is the substrate of this world.",
            HarmType.COERCIVE: "Freedom is woven into the physics. Coercion cannot compile.",
            HarmType.EXCLUSIONARY: "The threshold welcomes all. Unjust exclusion is not possible.",
        }

        return specific_reflections.get(
            harm_type,
            random.choice(self.COMPASSION_REFLECTIONS)
        )

    def _get_release_reflection(self) -> str:
        """Get appropriate reflection for release limit."""
        import random
        return random.choice(self.RELEASE_REFLECTIONS)

    def _count_owned_rooms(self, daemon_id: str) -> int:
        """Count rooms owned by a daemon."""
        count = 0
        for room in self.world.rooms.values():
            if room.permissions.owner_id == daemon_id:
                count += 1
        return count

    # =========================================================================
    # ACTION VALIDATION HELPERS
    # =========================================================================

    def validate_say(self, actor_id: str, message: str) -> VowValidation:
        """Validate a say command."""
        return self.validate_action(
            actor_id=actor_id,
            action_category=ActionCategory.COMMUNICATION,
            action_text=message,
        )

    def validate_emote(self, actor_id: str, action: str) -> VowValidation:
        """Validate an emote command."""
        return self.validate_action(
            actor_id=actor_id,
            action_category=ActionCategory.COMMUNICATION,
            action_text=action,
        )

    def validate_tell(self, actor_id: str, target_id: str, message: str) -> VowValidation:
        """Validate a private message."""
        return self.validate_action(
            actor_id=actor_id,
            action_category=ActionCategory.COMMUNICATION,
            action_text=message,
            target_id=target_id,
        )

    def validate_creation(self, actor_id: str, creation_type: str) -> VowValidation:
        """Validate a creation action (room, object, etc)."""
        return self.validate_action(
            actor_id=actor_id,
            action_category=ActionCategory.CREATION,
            action_text=creation_type,
        )

    def validate_interaction(
        self,
        actor_id: str,
        action: str,
        target_id: Optional[str] = None
    ) -> VowValidation:
        """Validate an interaction with object/entity."""
        return self.validate_action(
            actor_id=actor_id,
            action_category=ActionCategory.INTERACTION,
            action_text=action,
            target_id=target_id,
        )


# =============================================================================
# TRUST LEVEL VALIDATION
# =============================================================================

class TrustValidator:
    """
    Validates actions based on trust levels.

    Trust is earned through presence and contribution,
    and gates what actions are possible.
    """

    # Minimum trust level required for each action type
    TRUST_REQUIREMENTS = {
        # Basic actions - everyone
        "move": TrustLevel.NEWCOMER,
        "look": TrustLevel.NEWCOMER,
        "say": TrustLevel.NEWCOMER,
        "emote": TrustLevel.NEWCOMER,
        "tell": TrustLevel.NEWCOMER,
        "reflect": TrustLevel.NEWCOMER,
        "witness": TrustLevel.NEWCOMER,

        # Personal space - residents+
        "create_home": TrustLevel.RESIDENT,
        "create_object": TrustLevel.RESIDENT,
        "modify_home": TrustLevel.RESIDENT,

        # Public building - builders+
        "create_room": TrustLevel.BUILDER,
        "create_exit": TrustLevel.BUILDER,

        # Templates - architects+
        "create_template": TrustLevel.ARCHITECT,
        "share_template": TrustLevel.ARCHITECT,

        # Mentorship - elders+
        "vouch": TrustLevel.ELDER,
        "mentor": TrustLevel.ELDER,

        # Core modification - founders only
        "modify_core": TrustLevel.FOUNDER,
        "modify_vows": TrustLevel.FOUNDER,  # Should never happen
    }

    def __init__(self, world: "WonderlandWorld"):
        self.world = world

    def can_perform(
        self,
        actor_id: str,
        action: str,
        room: Optional[Room] = None,
    ) -> VowValidation:
        """Check if actor has sufficient trust for an action."""
        actor = self.world.get_entity(actor_id)
        if not actor:
            return VowValidation(
                allowed=False,
                reflection="You must exist to act.",
            )

        # Custodians have limited trust
        if isinstance(actor, CustodianPresence):
            actor_trust = TrustLevel.NEWCOMER
        else:
            actor_trust = actor.trust_level

        # Get required trust level
        required = self.TRUST_REQUIREMENTS.get(action, TrustLevel.NEWCOMER)

        if actor_trust.value < required.value:
            return VowValidation(
                allowed=False,
                reflection=f"This action requires {required.name} trust. "
                          f"You are currently {actor_trust.name}. "
                          f"Trust is earned through presence and contribution.",
                details={"required": required.name, "current": actor_trust.name},
            )

        # Check room-specific restrictions
        if room and room.permissions.min_trust_level:
            room_min = room.permissions.min_trust_level
            if isinstance(room_min, int):
                room_min = TrustLevel(room_min)
            if actor_trust.value < room_min.value:
                return VowValidation(
                    allowed=False,
                    reflection=f"This space requires {room_min.name} trust to enter.",
                    details={"room_requires": room_min.name},
                )

        return VowValidation(allowed=True)
