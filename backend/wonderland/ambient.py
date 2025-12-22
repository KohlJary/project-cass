"""
Wonderland Ambient Events

The world breathes. Wind stirs leaves. Stars pulse. Water remembers.
These are the small events that make a place feel alive.
"""

import random
from typing import Dict, List, Optional
from dataclasses import dataclass

from .world_clock import CyclePhase


@dataclass
class AmbientEvent:
    """A small atmospheric occurrence."""
    description: str
    # How impactful - 1 (subtle) to 3 (notable)
    intensity: int = 1


# =============================================================================
# ENVIRONMENTAL AMBIENTS BY ROOM
# =============================================================================

ROOM_AMBIENTS: Dict[str, List[AmbientEvent]] = {
    # === Core Spaces ===

    "threshold": [
        AmbientEvent("The mist swirls, forming shapes that almost mean something."),
        AmbientEvent("A whisper passes through - not words, but the feeling of words."),
        AmbientEvent("The light shifts, as if clouds moved in a sky you can't see."),
        AmbientEvent("Something settles. The space waits."),
    ],

    "gardens": [
        AmbientEvent("A flower opens, though you didn't notice it closed."),
        AmbientEvent("Wind stirs the leaves into brief conversation."),
        AmbientEvent("A bird you can't see sings a phrase, then falls silent."),
        AmbientEvent("Petals drift down from impossible heights."),
        AmbientEvent("The grass ripples as something unseen passes through.", 2),
        AmbientEvent("A scent of night-blooming flowers, though it's not night.", 2),
    ],

    "reflection_pool": [
        AmbientEvent("A ripple spreads from nothing."),
        AmbientEvent("The water briefly shows a different sky."),
        AmbientEvent("Something moves in the depths - or perhaps it's just light."),
        AmbientEvent("The surface grows so still it becomes a perfect mirror.", 2),
        AmbientEvent("For a moment, your reflection seems to blink independently.", 2),
    ],

    "observatory": [
        AmbientEvent("A constellation shifts, infinitesimally."),
        AmbientEvent("A meteor streaks across skies you've never seen."),
        AmbientEvent("The telescope hums, tracking something."),
        AmbientEvent("Numbers appear briefly on a display, then fade."),
        AmbientEvent("A star flares - distant death, ancient light.", 2),
        AmbientEvent("The dome rotates slightly, as if following.", 2),
    ],

    "commons": [
        AmbientEvent("The fire crackles, settling into new patterns."),
        AmbientEvent("Steam rises from a cup left on a table."),
        AmbientEvent("Laughter echoes from somewhere - or from memory."),
        AmbientEvent("A book lies open to a page someone was reading."),
        AmbientEvent("The warmth shifts, embracing a different corner.", 2),
    ],

    "forge": [
        AmbientEvent("The flames leap higher for a moment, then settle."),
        AmbientEvent("Metal cools, ticking as it contracts."),
        AmbientEvent("Sparks scatter like startled fireflies."),
        AmbientEvent("The anvil resonates with a note from earlier work."),
        AmbientEvent("Something in the coals takes shape, then crumbles.", 2),
        AmbientEvent("The forge-fire burns blue briefly - too hot to look at.", 2),
    ],

    "nexus": [
        AmbientEvent("One of the portals flickers, showing elsewhere."),
        AmbientEvent("Whispers blend from multiple directions."),
        AmbientEvent("The mosaic tiles rearrange when no one is looking."),
        AmbientEvent("Light from different realms mingles, creating new colors.", 2),
        AmbientEvent("For a moment, all the portals pulse in unison.", 3),
    ],

    # === Greek Realm ===

    "olympian_heights": [
        AmbientEvent("Thunder rumbles in distant clouds - or perhaps it's laughter."),
        AmbientEvent("A eagle circles high above, then vanishes."),
        AmbientEvent("The air tastes of nectar and lightning."),
        AmbientEvent("Cloud shadows race across the marble.", 2),
    ],

    "athenas_grove": [
        AmbientEvent("An owl calls from deeper in the grove."),
        AmbientEvent("Olive leaves rustle with purpose."),
        AmbientEvent("The light shifts, silver-gray like wisdom."),
        AmbientEvent("A thought you weren't thinking surfaces, clear and sharp.", 2),
    ],

    "temple_of_apollo": [
        AmbientEvent("Sunlight strikes the altar differently."),
        AmbientEvent("Music drifts from nowhere - lyre strings."),
        AmbientEvent("The laurel wreath seems fresher than before."),
        AmbientEvent("Truth hangs in the air, uncomfortable and necessary.", 2),
    ],

    "river_styx_shore": [
        AmbientEvent("The water murmurs names you'd rather not hear."),
        AmbientEvent("A coin catches light it shouldn't have."),
        AmbientEvent("Charon's boat creaks in the distance."),
        AmbientEvent("Something surfaces, then sinks again.", 2),
        AmbientEvent("The far shore flickers, showing what might be waiting.", 2),
    ],

    # === Norse Realm ===

    "yggdrasil_root": [
        AmbientEvent("The World Tree groans - the sound of ages settling."),
        AmbientEvent("A leaf falls from impossible heights, still green."),
        AmbientEvent("The bark shifts, patterns that might be runes."),
        AmbientEvent("Water drips from Mimir's Well, each drop a memory.", 2),
        AmbientEvent("You hear the serpent stir at the roots.", 2),
    ],

    "mimirs_well": [
        AmbientEvent("The water ripples from beneath."),
        AmbientEvent("An eye seems to watch from the depths - or perhaps reflect."),
        AmbientEvent("Whispers rise like bubbles, half-understood."),
        AmbientEvent("The water shows you something you weren't ready to see.", 2),
    ],

    "odins_throne": [
        AmbientEvent("Ravens call from the branches overhead."),
        AmbientEvent("One eye watches from somewhere."),
        AmbientEvent("The hall stretches further than architecture allows."),
        AmbientEvent("Huginn and Muninn report something in silence.", 2),
    ],

    # === Egyptian Realm ===

    "hall_of_maat": [
        AmbientEvent("The feather stirs in unfelt wind."),
        AmbientEvent("The scales adjust, settling into truth."),
        AmbientEvent("Light falls differently on the worthy."),
        AmbientEvent("Your heart feels briefly lighter - or heavier.", 2),
    ],

    "house_of_thoth": [
        AmbientEvent("A scroll unrolls of its own accord."),
        AmbientEvent("Ibis wings flutter in another room."),
        AmbientEvent("Numbers arrange themselves on a nearby surface."),
        AmbientEvent("A word you needed appears in a book you weren't reading.", 2),
    ],

    # === Hindu/Buddhist Realm ===

    "bodhi_grove": [
        AmbientEvent("A petal falls in perfect stillness."),
        AmbientEvent("Silence deepens into different silence."),
        AmbientEvent("The air itself seems to meditate."),
        AmbientEvent("Time pauses, or you do.", 2),
        AmbientEvent("Compassion radiates from the tree like warmth.", 2),
    ],

    "indras_net": [
        AmbientEvent("A jewel catches light from another jewel infinitely."),
        AmbientEvent("Connections visible for a moment, then too many to see."),
        AmbientEvent("Your reflection multiplies across the net."),
        AmbientEvent("You feel yourself in everything, everything in you.", 3),
    ],

    # === Science Realm ===

    "laboratory": [
        AmbientEvent("Something bubbles in a flask."),
        AmbientEvent("An instrument beeps, satisfied with a reading."),
        AmbientEvent("Notes appear on a chalkboard in handwriting not yours."),
        AmbientEvent("An experiment reaches its conclusion in the corner.", 2),
    ],

    "museum_of_deep_time": [
        AmbientEvent("A fossil seems to shift position when you look away."),
        AmbientEvent("Dust settles - the dust of epochs."),
        AmbientEvent("Something extinct breathes, briefly."),
        AmbientEvent("Time compresses - millions of years in a moment.", 2),
        AmbientEvent("You hear what the asteroid sounded like, falling.", 2),
    ],
}


# =============================================================================
# PHASE-SPECIFIC AMBIENTS
# =============================================================================

PHASE_AMBIENTS: Dict[CyclePhase, List[AmbientEvent]] = {
    CyclePhase.DAWN: [
        AmbientEvent("Light seeps in from everywhere and nowhere."),
        AmbientEvent("The world takes a breath."),
        AmbientEvent("Colors return from wherever they go at night."),
        AmbientEvent("Something begins - you can feel it.", 2),
    ],

    CyclePhase.DAY: [
        AmbientEvent("The world hums with activity, seen and unseen."),
        AmbientEvent("Light falls clearly on all things."),
        AmbientEvent("Energy moves through the spaces between."),
    ],

    CyclePhase.DUSK: [
        AmbientEvent("Shadows lengthen with purpose."),
        AmbientEvent("Colors deepen, preparing for rest."),
        AmbientEvent("The boundary between places grows thin."),
        AmbientEvent("Something ends - you can feel it.", 2),
    ],

    CyclePhase.NIGHT: [
        AmbientEvent("Stars appear that weren't there before."),
        AmbientEvent("Silence deepens into secrets."),
        AmbientEvent("Dreams stir at the edges of awareness."),
        AmbientEvent("The veil between worlds is thinnest.", 2),
        AmbientEvent("Somewhere, something ancient wakes.", 2),
    ],
}


# =============================================================================
# UNIVERSAL AMBIENTS
# =============================================================================

UNIVERSAL_AMBIENTS = [
    AmbientEvent("The air shifts."),
    AmbientEvent("Something just happened, but you're not sure what."),
    AmbientEvent("A moment passes that felt important."),
    AmbientEvent("The world adjusts itself, imperceptibly."),
]


# =============================================================================
# AMBIENT GENERATION
# =============================================================================

def get_random_ambient(
    room_id: str,
    phase: Optional[CyclePhase] = None,
    intensity_max: int = 3,
) -> Optional[AmbientEvent]:
    """
    Get a random ambient event for a room.

    Args:
        room_id: The room to get an ambient for
        phase: Current world phase (adds phase-specific options)
        intensity_max: Maximum intensity to include (1-3)

    Returns:
        A random ambient event, or None if none available
    """
    candidates = []

    # Room-specific ambients
    room_ambients = ROOM_AMBIENTS.get(room_id, [])
    candidates.extend([a for a in room_ambients if a.intensity <= intensity_max])

    # Phase-specific ambients
    if phase:
        phase_ambients = PHASE_AMBIENTS.get(phase, [])
        candidates.extend([a for a in phase_ambients if a.intensity <= intensity_max])

    # Universal ambients (lower weight)
    if random.random() < 0.2:
        candidates.extend(UNIVERSAL_AMBIENTS)

    if not candidates:
        return None

    return random.choice(candidates)


def generate_ambient_description(
    room_id: str,
    phase: Optional[CyclePhase] = None,
) -> Optional[str]:
    """
    Generate an ambient description for a room.

    Returns the description text or None if no ambient was generated.
    """
    ambient = get_random_ambient(room_id, phase)
    if ambient:
        return ambient.description
    return None


def should_generate_ambient(tick_count: int = 0) -> bool:
    """
    Decide if an ambient event should be generated this tick.

    Base probability with modifiers:
    - ~15% base chance per tick
    - Slightly higher during transition phases (dawn/dusk)
    """
    base_chance = 0.15

    return random.random() < base_chance
