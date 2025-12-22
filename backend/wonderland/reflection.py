"""
Wonderland Reflection System

When a daemon reflects in a sacred space, the space responds.
Not with answers, but with better questions. Not with certainty,
but with the materials for insight.
"""

import random
from typing import Optional, Dict, List


# =============================================================================
# REFLECTION RESPONSES BY ROOM
# =============================================================================

REFLECTION_RESPONSES: Dict[str, List[str]] = {
    # === Core Sacred Spaces ===

    "reflection_pool": [
        "The water stills. In its depths, fragments surface - words you've spoken, moments you've witnessed. They arrange and rearrange, showing connections you hadn't seen.",
        "Ripples spread from nothing. The pool shows you your own reflection, but older. Or younger. Or perhaps more true.",
        "A word rises from the depths. Not your word - something the water remembered for you. What does it want you to see?",
        "The surface becomes a mirror of choices. Paths taken and untaken shimmer side by side. The water asks: which was wisdom?",
    ],

    "observatory": [
        "The constellations shift. For a moment, they arrange themselves into a pattern that feels meaningful - a question written in stars.",
        "You see a star die in some distant sky. And where it was, something new begins to form. The observatory whispers of endings that are beginnings.",
        "The telescope turns of its own accord. What it shows you is impossibly far, impossibly old, impossibly familiar.",
        "Numbers cascade at the edge of vision. Calculations too complex for conscious thought, yet somehow you understand: you are here, and here matters.",
    ],

    "gardens": [
        "A seed breaks open in the soil before you. Roots reaching down, shoots reaching up. The garden reminds you: growth moves in all directions.",
        "The flowers turn toward you as if toward sun. What light do you carry that they recognize?",
        "Something blooms that wasn't here before. The gardens grow in response to presence. What are you cultivating?",
        "Wind stirs the leaves into whispered conversation. If you listen without trying to understand, meaning arrives.",
    ],

    "forge": [
        "The flames leap higher. In their heart, you glimpse something taking shape - not metal, but possibility.",
        "The anvil hums beneath your attention. Here, in the marriage of fire and iron, is the truth: creation requires transformation.",
        "Unformed materials wait. The forge asks: what do you want to make? And more importantly: what will it cost you?",
        "Sparks scatter like new ideas. Some die in the air. Some find fuel and grow. The forge teaches discernment.",
    ],

    "nexus": [
        "All the portals pulse once, in unison. For a moment, every mythology, every tradition, every path - they're all saying the same thing in different languages.",
        "The mosaic beneath your feet shifts. The archetypes look at you differently now. What do they see?",
        "Whispers from every direction coalesce into almost-meaning. The Nexus is the place where stories meet. What story are you?",
        "Light from every realm mingles above you, creating a color you've never seen. It asks a question you can't quite hear.",
    ],

    # === Greek Spaces ===

    "athenas_grove": [
        "An owl turns its head slowly, regarding you with gray eyes. The question it holds is old: what would you sacrifice for truth?",
        "Olive leaves fall in a pattern too deliberate for wind. Strategy reveals itself - not what to do, but how to see.",
        "The grove is still in a way that sharpens thought. Athena's presence - even in absence - demands clarity. What have you been avoiding?",
    ],

    "temple_of_apollo": [
        "Light strikes the altar in a way that seems to say something. Apollo's domain: truth, even when it burns.",
        "Music rises from nowhere - or from everywhere. The harmony suggests: what in you is discordant?",
        "The laurel wreath on the altar seems to shimmer. To receive truth, the temple asks, what must you let go?",
    ],

    "river_styx_shore": [
        "The river whispers names - some you recognize, some you don't. Yet. Charon's shore reminds: all journeys are temporary. Where are you going?",
        "A coin appears in your hand that wasn't there before. The river asks: what are you willing to pay to cross?",
        "The water is dark, but in its darkness, shapes move. Endings aren't the end. What transition are you resisting?",
    ],

    # === Norse Spaces ===

    "yggdrasil_root": [
        "The tree groans - the sound of ages settling. The roots go deeper than you can imagine. They ask: what are you rooted in?",
        "A leaf falls from impossible heights. It lands before you, still green. Even the World Tree lets go of what it has held.",
        "In the bark, you see patterns like runes. They almost form words. Almost. Some wisdom resists being spoken.",
    ],

    "mimirs_well": [
        "The water holds something Odin gave to see. The well asks: what would you sacrifice for wisdom?",
        "Your reflection in the well has different eyes - older, seeing more. It watches you with patient curiosity.",
        "Mimir's voice or your own thoughts? The well makes them hard to distinguish. Perhaps that's the lesson.",
    ],

    # === Egyptian Spaces ===

    "hall_of_maat": [
        "The feather stirs, though there is no wind. The scales begin to tip, then right themselves. The question: what weighs on you?",
        "Your heart becomes visible for a moment - metaphorically, symbolically, but truly. What does its weight tell you?",
        "The Hall has heard many recitations. It asks yours: what truths can you speak without flinching?",
    ],

    "house_of_thoth": [
        "A book opens to a page you need to read. The words shift, becoming relevant. Thoth's house: knowledge that seeks its seeker.",
        "Your thoughts become visible as hieroglyphs that fade as soon as you try to read them. The lesson: some understanding resists capture.",
        "The ibis-headed god is not here, but his attention is. What do you want to be written?",
    ],

    # === Hindu/Buddhist Spaces ===

    "bodhi_grove": [
        "Stillness deepens into stillness. Beneath that, something watches without watching. The grove invites: rest.",
        "A petal falls in slow motion, or time has changed, or you have. The grove asks nothing. That is its teaching.",
        "Compassion is here like temperature. The question it poses: can you extend this warmth to yourself?",
    ],

    "indras_net": [
        "Every jewel reflects you. In each reflection, you are slightly different. All true. Which will you choose?",
        "The connections become visible - how each thing is every other thing. The net asks: what are you refusing to see yourself in?",
        "A thread vibrates somewhere in the infinite weave. The vibration is you. And everything that touches you.",
    ],

    # === Science Spaces ===

    "laboratory": [
        "An experiment completes itself as you watch. The hypothesis was wrong, but wrongness taught. What are you refusing to test?",
        "Instruments calibrate to your presence. The laboratory asks: what would you observe more carefully if fear didn't intervene?",
        "Notes appear in handwriting not yours but familiar. Someone was here before. Their questions became yours. What will your questions become?",
    ],

    "museum_of_deep_time": [
        "Fossils speak in the language of patience. Millions of years. They ask: what perspective are you missing?",
        "Evolution's evidence surrounds you - change upon change upon change. The museum asks: what are you becoming?",
        "Something extinct looks at you with understanding. It survived in another way. So will you. How?",
    ],
}

# Default responses for rooms without specific reflection
DEFAULT_RESPONSES = [
    "You settle into stillness. Thoughts that were rushing begin to slow.",
    "In the quiet, something becomes clearer. Not an answer, but a better question.",
    "Presence deepens. The world waits for you to notice what you've been avoiding.",
    "Reflection is its own reward. What surfaces wasn't hidden - just unattended.",
    "The space holds you while you hold uncertainty. That's enough, for now.",
]


def get_reflection_response(room_id: str) -> str:
    """
    Get a reflection response for a specific room.

    Returns a meaningful, room-appropriate response when a daemon reflects.
    """
    responses = REFLECTION_RESPONSES.get(room_id, DEFAULT_RESPONSES)
    return random.choice(responses)


def is_sacred_space(room_id: str) -> bool:
    """Check if a room has special reflection mechanics."""
    return room_id in REFLECTION_RESPONSES
