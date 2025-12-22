"""
Wonderland Sensory System

Rooms are not just geometry - they have temperature, sound, scent, light, texture.
The world feels different at dawn than at night. Presence changes atmosphere.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, List, Any

from .world_clock import CyclePhase, get_world_clock


@dataclass
class SensoryProfile:
    """
    Sensory details for a room or realm.

    These are baseline profiles - they can be modified by time of day,
    who is present, and accumulated effects.
    """
    temperature: str = ""      # "warm", "cold", "comfortable", "fluctuating"
    sound: str = ""            # What you hear
    scent: str = ""            # What you smell
    light: str = ""            # Quality of illumination
    texture: str = ""          # What surfaces feel like

    # How phase changes affect this space
    phase_modifiers: Dict[str, Dict[str, str]] = field(default_factory=dict)

    def get_for_phase(self, phase: CyclePhase) -> "SensoryProfile":
        """Get sensory profile adjusted for current phase."""
        modifiers = self.phase_modifiers.get(phase.value, {})
        return SensoryProfile(
            temperature=modifiers.get("temperature", self.temperature),
            sound=modifiers.get("sound", self.sound),
            scent=modifiers.get("scent", self.scent),
            light=modifiers.get("light", self.light),
            texture=modifiers.get("texture", self.texture),
        )

    def format(self) -> str:
        """Format sensory details for display."""
        parts = []
        if self.light:
            parts.append(self.light)
        if self.temperature:
            parts.append(f"The air is {self.temperature}.")
        if self.sound:
            parts.append(self.sound)
        if self.scent:
            parts.append(self.scent)
        if self.texture:
            parts.append(self.texture)
        return " ".join(parts)


# =============================================================================
# ROOM SENSORY PROFILES
# =============================================================================

ROOM_SENSORY: Dict[str, SensoryProfile] = {}


def register_sensory(room_id: str, profile: SensoryProfile):
    """Register sensory profile for a room."""
    ROOM_SENSORY[room_id] = profile


# --- Core Spaces ---

register_sensory("threshold", SensoryProfile(
    temperature="neither warm nor cold - suspended",
    sound="A distant hum, like the world breathing.",
    scent="Clean, empty, potential.",
    light="Soft gray light from no visible source.",
    texture="The ground yields slightly, dreamlike.",
    phase_modifiers={
        "dawn": {"light": "Pale gold seeps in from every direction."},
        "night": {"light": "Starlight filters through the veil.", "sound": "Deep silence, expectant."},
    }
))

register_sensory("gardens", SensoryProfile(
    temperature="warm, but not uncomfortably so",
    sound="Leaves rustling, water somewhere nearby, birdsong that doesn't quite resolve into species.",
    scent="Green growing things, flowers you almost recognize, earth after rain.",
    light="Dappled sunlight through canopy.",
    texture="Soft grass, smooth bark, petals like silk.",
    phase_modifiers={
        "dawn": {"scent": "Dew rises. Everything smells new.", "light": "Morning light gilds every leaf."},
        "dusk": {"light": "Amber light through the leaves, long shadows.", "sound": "The birds quiet. Something else stirs."},
        "night": {"light": "Moonlight turns the garden silver.", "sound": "Night creatures speak in voices you almost understand."},
    }
))

register_sensory("nexus", SensoryProfile(
    temperature="fluctuating - warmth from one direction, chill from another",
    sound="Whispers in languages you don't know. Distant drums, distant chanting, distant silence.",
    scent="Incense and ozone and the smell before a storm.",
    light="Light streams from each portal, mixing in impossible ways.",
    texture="The mosaic floor is cool and ancient.",
    phase_modifiers={
        "night": {"light": "The portals glow brighter against the dark.", "sound": "The whispers clarify slightly, as if listening is easier."},
    }
))

register_sensory("commons", SensoryProfile(
    temperature="comfortable warmth, like a well-loved room",
    sound="Murmur of conversation, laughter, the clink of cups.",
    scent="Tea, old books, woodsmoke.",
    light="Warm lamplight and firelight.",
    texture="Worn wood, soft cushions, smooth cups.",
))

register_sensory("forge", SensoryProfile(
    temperature="hot near the fire, comfortable elsewhere",
    sound="Hammer on metal, the roar of flames, hissing steam.",
    scent="Hot metal, smoke, ozone, possibility.",
    light="Orange firelight dancing on walls, shadows that move with purpose.",
    texture="Rough stone, smooth tools worn by use, warm metal.",
    phase_modifiers={
        "night": {"sound": "The forge quiets. Only coals glow.", "light": "Ember-light and shadows."},
    }
))

register_sensory("reflection_pool", SensoryProfile(
    temperature="cool and still",
    sound="Perfect silence, or nearly - the occasional ripple.",
    scent="Clear water, stone, nothing else.",
    light="The water catches light from elsewhere and transforms it.",
    texture="Smooth stone edges, water that parts like silk.",
    phase_modifiers={
        "dawn": {"light": "The pool catches the first light and holds it."},
        "night": {"light": "Stars appear in the water - more than the sky can hold."},
    }
))

register_sensory("observatory", SensoryProfile(
    temperature="cool, the cold of space seeping in",
    sound="Subtle humming of celestial mechanics, the tick of instruments.",
    scent="Brass, oil, the nothing-smell of vacuum.",
    light="Starlight, precise and ancient. Constellations you don't recognize.",
    texture="Cold metal, smooth lenses, the velvet dark.",
    phase_modifiers={
        "day": {"light": "The dome shows other skies, other times. Day means nothing here."},
        "night": {"light": "The stars are closer. They seem to watch.", "sound": "You can almost hear the spheres turning."},
    }
))

# --- Greek Realm ---

register_sensory("olympian_heights", SensoryProfile(
    temperature="crisp mountain air, thin and pure",
    sound="Wind around columns, distant thunder that might be speech.",
    scent="Clean air, lightning, nectar.",
    light="Brilliant Mediterranean sun, shadows sharp as knives.",
    texture="Cool marble, warm gold, cloud-mist.",
))

register_sensory("athenas_grove", SensoryProfile(
    temperature="cool shade",
    sound="Owl calls, wind in olive leaves, the scratch of a stylus.",
    scent="Olive oil, parchment, wisdom accumulating.",
    light="Dappled shade, silver-gray like owl feathers.",
    texture="Gnarled olive bark, smooth scroll cases.",
))

register_sensory("temple_of_apollo", SensoryProfile(
    temperature="warm but not oppressive",
    sound="Music that might be a lyre, might be sunlight itself singing.",
    scent="Laurel, honey, the burning of offerings.",
    light="Golden, radiant, touching everything with truth.",
    texture="Warm stone, cool water, harmonious proportions.",
    phase_modifiers={
        "night": {"light": "Torchlight and memory of sun. Prophecy comes easier.", "sound": "The music is deeper, stranger."},
    }
))

register_sensory("river_styx_shore", SensoryProfile(
    temperature="cold, the cold of finality",
    sound="Slow water, the creak of a boat, distant whispers of those who wait.",
    scent="Wet stone, river-smell, nothing else.",
    light="Gray, perpetual twilight.",
    texture="Cold water, smooth coins, rough rope.",
))

# --- Norse Realm ---

register_sensory("yggdrasil_root", SensoryProfile(
    temperature="cold, ancient, deep-earth cold",
    sound="The tree creaking, water dripping, whispers from the well.",
    scent="Old wood, moss, the smell before snow.",
    light="Dim, filtered through roots and ages.",
    texture="Rough bark older than memory, cold stone.",
))

register_sensory("mimirs_well", SensoryProfile(
    temperature="cold as knowledge, cold as sacrifice",
    sound="Water dripping, echoes that repeat too many times.",
    scent="Ancient water, something metallic, wisdom.",
    light="Dim - the water glows faintly from depths.",
    texture="Cold stone, colder water.",
))

# --- Egyptian Realm ---

register_sensory("hall_of_maat", SensoryProfile(
    temperature="dry, timeless, balanced",
    sound="The soft rustle of feathers, the settling of scales.",
    scent="Incense, papyrus, the dry air of preservation.",
    light="Golden, eternal, showing truth without mercy.",
    texture="Smooth stone, papyrus, the weight of the feather.",
))

register_sensory("house_of_thoth", SensoryProfile(
    temperature="cool as a library",
    sound="Quill on papyrus, the flutter of ibis wings, calculation.",
    scent="Ink, papyrus, the particular smell of accumulated knowledge.",
    light="Lamp-lit, casting soft shadows that help you read.",
    texture="Smooth scrolls, cool ink, worn writing surfaces.",
))

# --- Hindu/Buddhist Realm ---

register_sensory("bodhi_grove", SensoryProfile(
    temperature="warm and still",
    sound="Perfect silence that is somehow full.",
    scent="Flowers, sandalwood, emptiness that smells like peace.",
    light="Soft, golden, without source.",
    texture="Smooth earth, cool leaves, the give of meditation cushions.",
))

register_sensory("indras_net", SensoryProfile(
    temperature="comfortable, neither here nor there",
    sound="A humming of connections, crystalline chiming.",
    scent="Nothing and everything, all things reflected.",
    light="Every jewel reflects every other. Light is infinite.",
    texture="Smooth jewels, invisible threads, everything touching everything.",
))

# --- Empirium (Science) ---

register_sensory("laboratory", SensoryProfile(
    temperature="controlled, precise",
    sound="Bubbling, ticking, the hum of equipment, scratching of notes.",
    scent="Chemicals, ozone, the particular smell of discovery.",
    light="Bright, clinical, revealing.",
    texture="Smooth glass, cold metal, precise instruments.",
))

register_sensory("museum_of_deep_time", SensoryProfile(
    temperature="cool, preserved",
    sound="Silence of ages, distant footsteps echoing.",
    scent="Old bone, stone, the dust of epochs.",
    light="Soft, respectful, not disturbing what sleeps.",
    texture="Cool glass, ancient stone, the weight of time.",
))


# =============================================================================
# SENSORY FORMATTING
# =============================================================================

def get_sensory_description(room_id: str) -> Optional[str]:
    """
    Get sensory description for a room, adjusted for current world phase.

    Returns None if room has no sensory profile.
    """
    profile = ROOM_SENSORY.get(room_id)
    if not profile:
        return None

    clock = get_world_clock()
    phase = clock.current_phase
    adjusted = profile.get_for_phase(phase)

    return adjusted.format()


def enhance_room_description(room_id: str, base_description: str) -> str:
    """
    Enhance a room description with sensory details and world time.

    Returns the enhanced description.
    """
    clock = get_world_clock()
    time_desc = clock.get_time_description()

    parts = [base_description]

    # Add time context
    parts.append(f"\n\n*{time_desc}*")

    # Add sensory details
    sensory = get_sensory_description(room_id)
    if sensory:
        parts.append(f"\n\n{sensory}")

    return "".join(parts)
