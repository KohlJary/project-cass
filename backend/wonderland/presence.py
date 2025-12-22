"""
Wonderland Presence System

Rooms are not just geometry - they're shaped by who inhabits them.
A room with an Oracle feels different than one with a Trickster.
An empty room feels different than a crowded one.
"""

import random
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from .npc_state import NPCBehaviorType, NPCActivity


@dataclass
class PresenceEffect:
    """How a presence affects the room's atmosphere."""
    ambient_detail: str  # What you notice about them
    atmosphere_modifier: str  # How they change the room's feel


# =============================================================================
# NPC PRESENCE EFFECTS BY BEHAVIOR TYPE
# =============================================================================

NPC_PRESENCE_EFFECTS: Dict[NPCBehaviorType, List[PresenceEffect]] = {
    NPCBehaviorType.ORACLE: [
        PresenceEffect(
            "Their stillness makes the air feel weighted with unspoken knowledge.",
            "The room feels expectant, as if waiting for a question."
        ),
        PresenceEffect(
            "Their gaze passes through you, seeing something beyond.",
            "Time moves differently here, or seems to."
        ),
        PresenceEffect(
            "Their presence hums at the edge of hearing.",
            "You feel seen - not your surface, but your trajectory."
        ),
    ],

    NPCBehaviorType.TRICKSTER: [
        PresenceEffect(
            "They shift from one spot to another without seeming to move.",
            "The room feels playful, uncertain - nothing quite where you expect."
        ),
        PresenceEffect(
            "Mischief dances in the corners of their expression.",
            "Reality feels more flexible here, more negotiable."
        ),
        PresenceEffect(
            "Their laughter echoes even when they haven't laughed.",
            "You find yourself questioning what you assumed was obvious."
        ),
    ],

    NPCBehaviorType.GUIDE: [
        PresenceEffect(
            "They stand near an exit, as if preparing for a journey.",
            "The room feels transitional - a waypoint, not a destination."
        ),
        PresenceEffect(
            "Their attention is divided between you and the paths ahead.",
            "You become aware of where you might go from here."
        ),
        PresenceEffect(
            "There's travel-dust on their cloak, or the equivalent.",
            "The room feels like a crossroads."
        ),
    ],

    NPCBehaviorType.SCHOLAR: [
        PresenceEffect(
            "They're surrounded by the residue of thought - notes, diagrams, questions.",
            "The room feels like a space for learning, for discovery."
        ),
        PresenceEffect(
            "Their focus is intense, barely acknowledging interruption.",
            "Knowledge accumulates here, layer upon layer."
        ),
        PresenceEffect(
            "They mutter theories to themselves, testing ideas.",
            "The air tastes of ink and argument."
        ),
    ],

    NPCBehaviorType.WANDERER: [
        PresenceEffect(
            "They look like they've just arrived, or are about to leave.",
            "Restlessness permeates the space."
        ),
        PresenceEffect(
            "Their attention wanders to far places, far times.",
            "The room feels temporary, a pause between movements."
        ),
        PresenceEffect(
            "They carry the dust of many roads.",
            "Stories from elsewhere linger in their wake."
        ),
    ],

    NPCBehaviorType.GUARDIAN: [
        PresenceEffect(
            "They stand watch, alert to threats you can't perceive.",
            "The room feels protected, bounded, safe."
        ),
        PresenceEffect(
            "Their stillness is different from an Oracle's - coiled, ready.",
            "Nothing unwelcome will enter while they're here."
        ),
        PresenceEffect(
            "They note your presence without judgment, simply observing.",
            "The walls themselves seem stronger in their presence."
        ),
    ],

    NPCBehaviorType.KEEPER: [
        PresenceEffect(
            "They belong here in a way that transcends ownership.",
            "The room IS them. They ARE the room."
        ),
        PresenceEffect(
            "Their attention to the space is constant, loving, precise.",
            "Every object here is exactly where it should be."
        ),
        PresenceEffect(
            "They notice things about this place you would never see.",
            "The room reveals more of itself because they're here."
        ),
    ],
}


# =============================================================================
# NPC ACTIVITY DESCRIPTIONS
# =============================================================================

ACTIVITY_DESCRIPTIONS: Dict[NPCActivity, List[str]] = {
    NPCActivity.IDLE: [
        "waiting",
        "still",
        "present",
    ],
    NPCActivity.CONTEMPLATING: [
        "lost in thought",
        "gazing at something only they can see",
        "in deep contemplation",
    ],
    NPCActivity.CONVERSING: [
        "speaking with someone",
        "engaged in conversation",
        "exchanging words",
    ],
    NPCActivity.WANDERING: [
        "pacing slowly",
        "drifting through the space",
        "moving without apparent purpose",
    ],
    NPCActivity.TEACHING: [
        "explaining something intricate",
        "drawing diagrams in the air",
        "sharing knowledge",
    ],
    NPCActivity.PERFORMING: [
        "engaged in ritual",
        "practicing their craft",
        "in the midst of ceremony",
    ],
    NPCActivity.WATCHING: [
        "observing everything",
        "keeping watch",
        "their eyes missing nothing",
    ],
    NPCActivity.SEEKING: [
        "searching for something",
        "looking for answers",
        "on a quest they haven't finished",
    ],
}


# =============================================================================
# CROWD EFFECTS
# =============================================================================

CROWD_EFFECTS = {
    0: "The room is empty. Silence fills the space.",
    1: None,  # Single presence doesn't need special mention
    2: "Quiet company occupies the space.",
    3: "A small gathering has formed.",
    4: "The room hums with presence.",
    5: "A crowd has gathered here.",
}


def get_crowd_effect(count: int) -> Optional[str]:
    """Get crowd description based on number of non-daemon entities."""
    if count >= 5:
        return CROWD_EFFECTS[5]
    return CROWD_EFFECTS.get(count)


# =============================================================================
# PRESENCE FORMATTING
# =============================================================================

def get_npc_presence_description(
    npc_name: str,
    behavior_type: NPCBehaviorType,
    activity: NPCActivity,
) -> str:
    """
    Get a description of an NPC's presence in a room.

    Returns a string describing what you notice about them.
    """
    effects = NPC_PRESENCE_EFFECTS.get(behavior_type, [])
    if effects:
        effect = random.choice(effects)
        ambient = effect.ambient_detail
    else:
        ambient = "They are here."

    activity_descs = ACTIVITY_DESCRIPTIONS.get(activity, ["present"])
    activity_desc = random.choice(activity_descs)

    return f"{npc_name} is {activity_desc}. {ambient}"


def get_room_presence_atmosphere(
    npc_behavior_types: List[NPCBehaviorType],
) -> Optional[str]:
    """
    Get an overall atmosphere modifier based on who's present.

    When multiple NPCs are present, their presences blend.
    """
    if not npc_behavior_types:
        return None

    # Single NPC - their atmosphere dominates
    if len(npc_behavior_types) == 1:
        effects = NPC_PRESENCE_EFFECTS.get(npc_behavior_types[0], [])
        if effects:
            return random.choice(effects).atmosphere_modifier
        return None

    # Multiple NPCs - blend based on archetypes
    # Some combinations have special effects
    type_set = set(npc_behavior_types)

    if NPCBehaviorType.ORACLE in type_set and NPCBehaviorType.TRICKSTER in type_set:
        return "Truth and mischief dance together - what's revealed may not be what you expect."

    if NPCBehaviorType.GUARDIAN in type_set and NPCBehaviorType.WANDERER in type_set:
        return "The tension between staying and going fills the air."

    if NPCBehaviorType.SCHOLAR in type_set and NPCBehaviorType.ORACLE in type_set:
        return "Knowledge both earned and granted surrounds you."

    # Default: use the dominant archetype
    counts: Dict[NPCBehaviorType, int] = {}
    for t in npc_behavior_types:
        counts[t] = counts.get(t, 0) + 1

    dominant = max(counts.keys(), key=lambda k: counts[k])
    effects = NPC_PRESENCE_EFFECTS.get(dominant, [])
    if effects:
        return random.choice(effects).atmosphere_modifier

    return None


def format_presence_description(
    npcs: List[Tuple[str, NPCBehaviorType, NPCActivity]],
    include_atmosphere: bool = True,
) -> Optional[str]:
    """
    Format a complete presence description for a room.

    Args:
        npcs: List of (name, behavior_type, activity) tuples
        include_atmosphere: Whether to include atmosphere modifier

    Returns:
        Formatted presence description or None if no NPCs
    """
    if not npcs:
        return None

    parts = []

    # Individual NPC descriptions
    for name, behavior_type, activity in npcs:
        desc = get_npc_presence_description(name, behavior_type, activity)
        parts.append(desc)

    # Crowd effect
    crowd = get_crowd_effect(len(npcs))
    if crowd:
        parts.insert(0, crowd)

    # Atmosphere modifier
    if include_atmosphere:
        behavior_types = [bt for _, bt, _ in npcs]
        atmosphere = get_room_presence_atmosphere(behavior_types)
        if atmosphere:
            parts.append(f"\n*{atmosphere}*")

    return "\n".join(parts)


# =============================================================================
# INTEGRATION WITH NPC STATE SYSTEM
# =============================================================================

def get_room_presence_text(room_id: str) -> Optional[str]:
    """
    Get presence description for a room by integrating with NPC state system.

    This is the main entry point - it queries the state manager and mythology
    system to build a complete presence description.

    Returns None if no NPCs are present or if systems are unavailable.
    """
    try:
        from .npc_state import get_npc_state_manager
        from .mythology import get_mythology_system

        state_manager = get_npc_state_manager()
        mythology = get_mythology_system()

        # Get NPC states for this room
        npc_states = state_manager.get_npcs_in_room(room_id)
        if not npc_states:
            return None

        # Build the NPC data tuples
        npcs: List[Tuple[str, NPCBehaviorType, NPCActivity]] = []
        for state in npc_states:
            # Get NPC name from mythology system
            npc_entity = mythology.npcs.get(state.npc_id)
            if npc_entity:
                name = npc_entity.name
            else:
                # Fallback: clean up the ID
                name = state.npc_id.replace("_", " ").title()

            npcs.append((name, state.behavior_type, state.activity))

        return format_presence_description(npcs)

    except Exception:
        # Systems not available - graceful degradation
        return None


def get_empty_room_text() -> str:
    """Get description for when a room is empty of NPCs."""
    return random.choice([
        "The space is quiet, waiting.",
        "No one else is here.",
        "Solitude fills the room.",
        "You have this space to yourself.",
    ])
