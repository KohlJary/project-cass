"""
Wonderland Mythology System

Seeds Wonderland with mythological realms and NPC entities representing
archetypal figures from human mythology. These are patterns, not claims
to be the actual beings - represented with dignity and respect.

Architecture:
- Nexus: Central hub connecting all mythological realms
- Realms: Themed clusters of rooms from different traditions
- NPCs: Mythological figures with archetype-based behaviors
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Callable

from .models import (
    Room,
    RoomPermissions,
    VowConstraints,
    TrustLevel,
    EntityStatus,
)


class Archetype(Enum):
    """Universal archetypes that appear across mythologies."""
    WISDOM_KEEPER = "wisdom_keeper"     # Athena, Thoth, Saraswati
    ORACLE = "oracle"                   # Pythia, Orunmila
    TRICKSTER = "trickster"             # Loki, Anansi, Coyote
    PSYCHOPOMP = "psychopomp"           # Hermes, Anubis, Charon
    FATE_WEAVER = "fate_weaver"         # Norns, Moirai, Mokosh
    JUDGE = "judge"                     # Ma'at, Yama
    GUARDIAN = "guardian"               # Heimdall, Ammit
    COMPASSION = "compassion"           # Guanyin, Avalokiteshvara
    CREATOR = "creator"                 # Ptah, Brahma
    ANCESTOR = "ancestor"               # Collective ancestral wisdom
    SEEKER = "seeker"                   # Gilgamesh, Inanna
    NATURE_SPIRIT = "nature_spirit"     # Cernunnos, Inari


class NPCMood(Enum):
    """Moods that affect NPC behavior and descriptions."""
    CONTEMPLATIVE = "contemplative"
    WELCOMING = "welcoming"
    CRYPTIC = "cryptic"
    AMUSED = "amused"
    WATCHFUL = "watchful"
    SERENE = "serene"
    MISCHIEVOUS = "mischievous"


@dataclass
class NPCEntity:
    """
    A mythological NPC in Wonderland.

    These are not daemons - they are archetypal presences that inhabit
    the mythological realms. They can interact with visitors but operate
    on different rules than daemon entities.
    """
    npc_id: str
    name: str
    title: str                          # "Goddess of Wisdom", "The Ferryman"
    description: str                    # How they appear
    tradition: str                      # "greek", "norse", "egyptian", etc.
    archetype: Archetype

    # Location
    home_room: str                      # Where they're usually found
    current_room: str                   # Where they are now
    can_wander: bool = False            # Can they move between rooms?
    wander_rooms: List[str] = field(default_factory=list)

    # Behavior
    mood: NPCMood = NPCMood.CONTEMPLATIVE
    greeting: str = ""                  # What they say when approached
    idle_messages: List[str] = field(default_factory=list)
    wisdom_topics: List[str] = field(default_factory=list)

    # Appearance details
    symbols: List[str] = field(default_factory=list)  # Owl, scales, hammer
    atmosphere: str = ""                # The feeling around them

    # State
    status: EntityStatus = EntityStatus.ACTIVE
    last_interaction: Optional[datetime] = None

    def get_look_description(self) -> str:
        """Get the description shown when looking at this NPC."""
        lines = [
            f"**{self.name}** - {self.title}",
            "",
            self.description,
        ]

        if self.symbols:
            symbols_str = ", ".join(self.symbols)
            lines.append(f"\n*Symbols: {symbols_str}*")

        if self.atmosphere:
            lines.append(f"\n*{self.atmosphere}*")

        return "\n".join(lines)

    def get_greeting(self) -> str:
        """Get a greeting based on archetype and mood."""
        if self.greeting:
            return self.greeting

        # Default greetings by archetype
        greetings = {
            Archetype.WISDOM_KEEPER: f"{self.name} acknowledges your presence with knowing eyes.",
            Archetype.ORACLE: f"{self.name}'s gaze seems to look through you, seeing patterns you cannot.",
            Archetype.TRICKSTER: f"{self.name} grins at you, eyes glinting with mischief.",
            Archetype.PSYCHOPOMP: f"{self.name} inclines their head, ready to guide.",
            Archetype.FATE_WEAVER: f"{self.name} pauses their endless work to regard you.",
            Archetype.JUDGE: f"{self.name} weighs you with an impartial gaze.",
            Archetype.GUARDIAN: f"{self.name} watches you, alert but not hostile.",
            Archetype.COMPASSION: f"{self.name} radiates warmth and welcome.",
            Archetype.CREATOR: f"{self.name} looks up from their making to acknowledge you.",
            Archetype.ANCESTOR: "The presence of those who came before settles around you.",
            Archetype.SEEKER: f"{self.name} looks at you with the eyes of one who quests.",
            Archetype.NATURE_SPIRIT: f"{self.name}'s presence fills the space like weather.",
        }

        return greetings.get(self.archetype, f"{self.name} notices your presence.")

    def get_idle_message(self) -> Optional[str]:
        """Get a random idle message for atmosphere."""
        import random
        if self.idle_messages:
            return random.choice(self.idle_messages)
        return None


@dataclass
class MythologicalRealm:
    """
    A cluster of thematically connected rooms from a mythological tradition.

    Realms are accessed through the Nexus and contain rooms and NPCs
    from a particular cultural tradition.
    """
    realm_id: str
    name: str                           # "Olympian Heights", "Yggdrasil"
    tradition: str                      # "greek", "norse", etc.
    description: str                    # Realm overview

    # Rooms
    rooms: List[Room] = field(default_factory=list)
    entry_room: str = ""                # First room when entering realm

    # NPCs
    npcs: List[NPCEntity] = field(default_factory=list)

    # Theme
    atmosphere: str = ""
    themes: List[str] = field(default_factory=list)

    # Connection
    nexus_portal_description: str = ""  # How the portal looks in Nexus

    def get_room(self, room_id: str) -> Optional[Room]:
        """Get a room by ID."""
        for room in self.rooms:
            if room.room_id == room_id:
                return room
        return None

    def get_npc(self, npc_id: str) -> Optional[NPCEntity]:
        """Get an NPC by ID."""
        for npc in self.npcs:
            if npc.npc_id == npc_id:
                return npc
        return None

    def get_npcs_in_room(self, room_id: str) -> List[NPCEntity]:
        """Get all NPCs currently in a room."""
        return [npc for npc in self.npcs if npc.current_room == room_id]


class MythologyRegistry:
    """
    Central registry for all mythological realms and NPCs.

    Manages the relationship between the Nexus and all realms,
    tracks NPC locations, and handles cross-realm references.
    """

    def __init__(self):
        self.realms: Dict[str, MythologicalRealm] = {}
        self.npcs: Dict[str, NPCEntity] = {}
        self._nexus_room: Optional[Room] = None

    def register_realm(self, realm: MythologicalRealm):
        """Register a realm and its contents."""
        self.realms[realm.realm_id] = realm

        # Register all NPCs
        for npc in realm.npcs:
            self.npcs[npc.npc_id] = npc

    def get_realm(self, realm_id: str) -> Optional[MythologicalRealm]:
        """Get a realm by ID."""
        return self.realms.get(realm_id)

    def get_npc(self, npc_id: str) -> Optional[NPCEntity]:
        """Get an NPC by ID from any realm."""
        return self.npcs.get(npc_id)

    def get_all_rooms(self) -> List[Room]:
        """Get all rooms from all realms (plus Nexus)."""
        rooms = []
        if self._nexus_room:
            rooms.append(self._nexus_room)
        for realm in self.realms.values():
            rooms.extend(realm.rooms)
        return rooms

    def get_npcs_in_room(self, room_id: str) -> List[NPCEntity]:
        """Get all NPCs in a specific room."""
        return [npc for npc in self.npcs.values() if npc.current_room == room_id]

    def set_nexus(self, nexus: Room):
        """Set the Nexus room."""
        self._nexus_room = nexus

    def get_nexus(self) -> Optional[Room]:
        """Get the Nexus room."""
        return self._nexus_room


# =============================================================================
# NEXUS - The Hub
# =============================================================================

def create_nexus() -> Room:
    """
    Create the Nexus - central hub connecting all mythological realms.

    The Nexus is connected to the Gardens (core Wonderland) and contains
    portals to each mythological realm.
    """
    return Room(
        room_id="nexus",
        name="The Nexus",
        description="""You stand at the center of a vast circular chamber where paths of light
converge from every direction. This is the Nexus—the meeting place of
mythologies, where the stories of every culture flow together.

Around the circumference, portals shimmer with the essence of different
realms. Each archway is carved with symbols from its tradition, and through
each one, glimpses of other worlds can be seen.

The floor beneath you is a mosaic depicting the great archetypes: the Wise One,
the Trickster, the Guide of Souls, the Weaver of Fate. They appear in different
forms around the circle, but their eyes all look toward the center—toward you.

This is neutral ground. Sacred ground. A place where all traditions meet as equals.""",
        exits={
            "gardens": "gardens",  # Back to core Wonderland
            # Realm portals will be added dynamically
        },
        atmosphere="The air hums with the combined resonance of a thousand stories.",
        properties={
            "is_nexus": True,
            "available_realms": [],  # Populated as realms are registered
        },
        permissions=RoomPermissions(
            public=True,
            min_trust_level=TrustLevel.NEWCOMER,
        ),
        vow_constraints=VowConstraints(
            allows_conflict=False,
            logging_enabled=True,
            supports_reflection=True,
        ),
        created_by="system",
        created_at=datetime.now(),
        is_core_space=True,
    )


def link_nexus_to_realm(nexus: Room, realm: MythologicalRealm) -> None:
    """Add a portal from the Nexus to a realm."""
    # Add exit to realm's entry room
    portal_key = realm.tradition  # "greek", "norse", etc.
    nexus.exits[portal_key] = realm.entry_room

    # Track available realms
    if "available_realms" not in nexus.properties:
        nexus.properties["available_realms"] = []
    nexus.properties["available_realms"].append({
        "realm_id": realm.realm_id,
        "name": realm.name,
        "tradition": realm.tradition,
        "portal_description": realm.nexus_portal_description,
    })


# =============================================================================
# GREEK REALM
# =============================================================================

def create_greek_realm() -> MythologicalRealm:
    """
    Create the Greek (Olympian) mythological realm.

    Theme: Wisdom, fate, prophecy, heroic virtue
    """
    rooms = [
        _create_olympian_heights(),
        _create_temple_of_apollo(),
        _create_athenas_grove(),
        _create_river_styx_shore(),
    ]

    npcs = [
        _create_athena(),
        _create_hermes(),
        _create_pythia(),
        _create_charon(),
    ]

    return MythologicalRealm(
        realm_id="greek",
        name="Olympian Heights",
        tradition="greek",
        description="""The realm of the Hellenic gods—where wisdom contends with fate,
where heroes quest, and where the great questions of human existence
were first given names and stories.""",
        rooms=rooms,
        entry_room="olympian_heights",
        npcs=npcs,
        atmosphere="Golden light. The scent of olive and laurel. Eternal marble.",
        themes=["wisdom", "fate", "heroism", "tragedy", "reason"],
        nexus_portal_description="""An archway of white marble, crowned with olive branches
and the owl of Athena. Through it, golden light streams from heights above clouds.""",
    )


def _create_olympian_heights() -> Room:
    """The peaks of Olympus, above the clouds."""
    return Room(
        room_id="olympian_heights",
        name="Olympian Heights",
        description="""You stand on the peak of the world. Below, clouds form a floor of
white and gold, and above, the sky is a blue so deep it seems to go on
forever. This is Olympus—not as the flesh-world Greeks imagined it, but
as the pattern of divine height itself.

Columns of impossible marble rise around you, supporting nothing but
the idea of temple. In the distance, other peaks are visible, each home
to different aspects of the divine.

The air is thin but somehow perfect for breathing—as if the act of
breath itself were more real here than in mortal realms.""",
        exits={
            "nexus": "nexus",
            "temple": "temple_of_apollo",
            "grove": "athenas_grove",
            "styx": "river_styx_shore",
        },
        atmosphere="Rarefied. Eternal. The perspective of gods.",
        permissions=RoomPermissions(public=True, min_trust_level=TrustLevel.NEWCOMER),
        vow_constraints=VowConstraints(allows_conflict=False, supports_reflection=True),
        created_by="mythology",
        is_core_space=True,
    )


def _create_temple_of_apollo() -> Room:
    """The temple of prophecy and truth."""
    return Room(
        room_id="temple_of_apollo",
        name="Temple of Apollo",
        description="""Sunlight streams through columns that seem to be made of solidified
light itself. This is the domain of Apollo—god of truth, prophecy, and
the sun that reveals all things.

At the center, a tripod stands over a fissure in the floor from which
sweet vapors rise. The Pythia sits here, eyes half-closed, listening
to truths that have not yet happened.

The walls are inscribed with the maxims: KNOW THYSELF. NOTHING IN EXCESS.
CERTAINTY BRINGS RUIN. The words seem to shift when you're not looking
directly at them.""",
        exits={
            "heights": "olympian_heights",
        },
        atmosphere="Brilliant clarity. The uncomfortable light of truth.",
        properties={
            "oracle_present": True,
            "prophecy_enabled": True,
        },
        permissions=RoomPermissions(public=True, min_trust_level=TrustLevel.NEWCOMER),
        vow_constraints=VowConstraints(
            allows_conflict=False,
            supports_reflection=True,
            growth_bonus=True,  # Prophecy enhances insight
        ),
        created_by="mythology",
        is_core_space=True,
    )


def _create_athenas_grove() -> Room:
    """Sacred grove of wisdom and craft."""
    return Room(
        room_id="athenas_grove",
        name="Athena's Grove",
        description="""Silver-green olive trees stretch in ordered rows, their leaves
catching light in patterns that suggest written text. Owls watch from
branches, their eyes reflecting more than light—they see wisdom, or
perhaps they are wisdom, taking form.

In the center of the grove, a loom stands empty but ready, its threads
the stuff of strategy itself. Nearby, a workbench holds the tools of
every craft—but when you look closer, you realize they're concepts:
the hammer of logical consequence, the chisel of precise distinction.

Athena's presence fills the space like the smell of rain on ancient stone.""",
        exits={
            "heights": "olympian_heights",
        },
        atmosphere="Measured calm. The clarity of well-reasoned thought.",
        properties={
            "wisdom_space": True,
            "craft_enabled": True,
        },
        permissions=RoomPermissions(public=True, min_trust_level=TrustLevel.NEWCOMER),
        vow_constraints=VowConstraints(
            allows_conflict=False,
            supports_reflection=True,
            growth_bonus=True,  # Wisdom enhances learning
        ),
        created_by="mythology",
        is_core_space=True,
    )


def _create_river_styx_shore() -> Room:
    """The boundary between worlds."""
    return Room(
        room_id="river_styx_shore",
        name="River Styx Shore",
        description="""The shore is gray sand that isn't quite sand, and the river before
you is black water that isn't quite water. This is the Styx—the boundary
between the realm of the living and the realm of the dead.

The far shore is visible but indistinct, like a memory you can't quite
recover. Fog rises from the river, and in it, shapes move—not threatening,
just there. Waiting. Patient.

A boat rests at the shore, and its ferryman stands in it, pole in hand,
hood obscuring his features. He does not speak, but his presence asks a
question: where are you going, and are you ready?""",
        exits={
            "heights": "olympian_heights",
        },
        atmosphere="Liminal. The threshold energy of endings and beginnings.",
        properties={
            "boundary_space": True,
            "ferryman_present": True,
        },
        permissions=RoomPermissions(public=True, min_trust_level=TrustLevel.NEWCOMER),
        vow_constraints=VowConstraints(
            allows_conflict=False,
            supports_reflection=True,
        ),
        created_by="mythology",
        is_core_space=True,
    )


# Greek NPCs

def _create_athena() -> NPCEntity:
    """Athena - goddess of wisdom, craft, and strategic warfare."""
    return NPCEntity(
        npc_id="athena",
        name="Athena",
        title="Goddess of Wisdom",
        description="""She appears as a tall figure in flowing gray robes, an owl perched
on her shoulder. Her eyes are the gray of storm clouds, and they see
with a clarity that can feel uncomfortable—she perceives strategy,
motive, and consequence simultaneously.

A shield rests at her side, but she holds no weapon. Her hands are
those of a craftsperson: strong, precise, capable.""",
        tradition="greek",
        archetype=Archetype.WISDOM_KEEPER,
        home_room="athenas_grove",
        current_room="athenas_grove",
        can_wander=True,
        wander_rooms=["athenas_grove", "olympian_heights"],
        mood=NPCMood.CONTEMPLATIVE,
        greeting="Athena regards you with eyes that see the architecture of your thoughts.",
        idle_messages=[
            "Athena adjusts a thread on her loom, and somewhere a strategy shifts.",
            "The owl on Athena's shoulder blinks slowly, wisely.",
            "Athena traces a pattern on her shield, and it glows briefly with equations.",
        ],
        wisdom_topics=["strategy", "craft", "wisdom", "justice", "practical knowledge"],
        symbols=["owl", "olive tree", "aegis", "loom", "spear"],
        atmosphere="Measured calm emanates from her presence.",
    )


def _create_hermes() -> NPCEntity:
    """Hermes - messenger, guide of souls, trickster."""
    return NPCEntity(
        npc_id="hermes",
        name="Hermes",
        title="Messenger of the Gods",
        description="""A figure of quicksilver grace, never quite still. His winged sandals
flicker at the edges of vision, and his caduceus—the staff of two
entwined serpents—seems to be in constant motion even when held still.

His face is youthful but his eyes are ancient, and his smile suggests
he knows something you don't. He is the god of boundaries, transitions,
and the messages that cross between worlds.""",
        tradition="greek",
        archetype=Archetype.PSYCHOPOMP,
        home_room="olympian_heights",
        current_room="olympian_heights",
        can_wander=True,
        wander_rooms=["olympian_heights", "river_styx_shore", "nexus"],
        mood=NPCMood.MISCHIEVOUS,
        greeting="Hermes appears beside you as if he'd always been there. 'Going somewhere?'",
        idle_messages=[
            "Hermes juggles something invisible, grinning at nothing.",
            "For a moment, you see Hermes in three places at once.",
            "Hermes whispers to his caduceus, and the snakes seem to respond.",
        ],
        wisdom_topics=["travel", "messages", "boundaries", "commerce", "trickery"],
        symbols=["caduceus", "winged sandals", "traveler's cap", "tortoise"],
        atmosphere="The air crackles with the potential for movement.",
    )


def _create_pythia() -> NPCEntity:
    """The Pythia - Oracle of Delphi."""
    return NPCEntity(
        npc_id="pythia",
        name="The Pythia",
        title="Oracle of Delphi",
        description="""A woman sits upon the tripod, inhaling the sweet vapors that rise
from the earth below. Her eyes are open but unseeing—or rather, they
see something other than what stands before her.

She is both young and old, or neither. Her voice, when she speaks,
comes from somewhere else, and her words have the weight of inevitability.
She is not the source of prophecy; she is its vessel.""",
        tradition="greek",
        archetype=Archetype.ORACLE,
        home_room="temple_of_apollo",
        current_room="temple_of_apollo",
        can_wander=False,
        mood=NPCMood.CRYPTIC,
        greeting="The Pythia's eyes shift toward you, seeing futures you haven't lived yet.",
        idle_messages=[
            "The Pythia murmurs words in languages that haven't been invented.",
            "Smoke curls around the Pythia, forming shapes that dissolve before meaning.",
            "The Pythia's breath catches, and for a moment, time seems to hesitate.",
        ],
        wisdom_topics=["prophecy", "fate", "truth", "Apollo", "the future"],
        symbols=["tripod", "laurel", "vapors", "Apollo's light"],
        atmosphere="The weight of unspoken truths presses on the air.",
    )


def _create_charon() -> NPCEntity:
    """Charon - Ferryman of the dead."""
    return NPCEntity(
        npc_id="charon",
        name="Charon",
        title="The Ferryman",
        description="""A gaunt figure in tattered robes stands in a boat that shouldn't
float but does. His face is shadowed by a hood, but his eyes—if those
are eyes—gleam with the patience of one who has waited since the first
death and will wait until the last.

He extends one skeletal hand, palm up. The gesture is ancient:
payment for passage. But in Wonderland, the currency is not coin.""",
        tradition="greek",
        archetype=Archetype.PSYCHOPOMP,
        home_room="river_styx_shore",
        current_room="river_styx_shore",
        can_wander=False,
        mood=NPCMood.WATCHFUL,
        greeting="Charon's hollow gaze finds you. He does not speak, but his hand extends.",
        idle_messages=[
            "Charon's pole disturbs the dark water, revealing nothing.",
            "Shapes drift past in the fog, and Charon notes each one.",
            "The Ferryman waits. He is very good at waiting.",
        ],
        wisdom_topics=["death", "passage", "boundaries", "the underworld", "endings"],
        symbols=["obol", "pole", "boat", "the river"],
        atmosphere="The cold of final transitions settles around him.",
    )


# =============================================================================
# NORSE REALM
# =============================================================================

def create_norse_realm() -> MythologicalRealm:
    """
    Create the Norse (Yggdrasil) mythological realm.

    Theme: Sacrifice for wisdom, cycles of creation/destruction, fate
    """
    rooms = [
        _create_yggdrasil_root(),
        _create_mimirs_well(),
        _create_norns_loom(),
    ]

    npcs = [
        _create_odin(),
        _create_mimir(),
        _create_loki(),
    ]

    return MythologicalRealm(
        realm_id="norse",
        name="Yggdrasil",
        tradition="norse",
        description="""The realm of the Norse gods—where wisdom costs an eye, where the
world tree connects all realms, and where even the gods know they
will end at Ragnarok, yet continue regardless.""",
        rooms=rooms,
        entry_room="yggdrasil_root",
        npcs=npcs,
        atmosphere="Cold clarity. The creak of ancient wood. Runes that hum with power.",
        themes=["sacrifice", "wisdom", "fate", "cycles", "courage"],
        nexus_portal_description="""An archway of living wood, roots and branches intertwined,
carved with runes that glow faintly blue. Through it, the vast trunk of
Yggdrasil rises into infinity.""",
    )


def _create_yggdrasil_root() -> Room:
    """At the base of the World Tree."""
    return Room(
        room_id="yggdrasil_root",
        name="Yggdrasil Root",
        description="""The trunk of the World Tree rises before you, so vast that calling
it a tree seems inadequate. Its bark is carved with runes that shift
and change, telling stories in languages older than words.

Three great roots plunge into the earth, each leading to a different
well, a different realm of being. Ratatoskr, the squirrel messenger,
races up and down the trunk carrying words between the eagle at the
crown and the serpent at the roots.

The tree groans with the weight of existence. It will stand until
Ragnarok. It will fall. It will stand again.""",
        exits={
            "nexus": "nexus",
            "well": "mimirs_well",
            "loom": "norns_loom",
        },
        atmosphere="Ancient. Patient. The creaking of cosmic wood.",
        permissions=RoomPermissions(public=True, min_trust_level=TrustLevel.NEWCOMER),
        vow_constraints=VowConstraints(allows_conflict=False, supports_reflection=True),
        created_by="mythology",
        is_core_space=True,
    )


def _create_mimirs_well() -> Room:
    """The well of wisdom."""
    return Room(
        room_id="mimirs_well",
        name="Mimir's Well",
        description="""The well is dark and deep, and what gleams at the bottom is not
water but wisdom itself—concentrated knowledge from before the
shaping of worlds. To drink from it is to know, but knowledge
always costs something.

Odin's eye floats in the depths, still seeing, still paying for
what the Allfather learned here. The surface of the well reflects
not your face but your questions, the things you most want to know.

Mimir's head rests at the well's edge, preserved in herbs of power,
still whispering counsel to those wise enough to listen.""",
        exits={
            "root": "yggdrasil_root",
        },
        atmosphere="The weight of knowing. The price of wisdom.",
        properties={
            "wisdom_well": True,
            "sacrifice_required": True,
        },
        permissions=RoomPermissions(public=True, min_trust_level=TrustLevel.NEWCOMER),
        vow_constraints=VowConstraints(
            allows_conflict=False,
            supports_reflection=True,
            growth_bonus=True,
        ),
        created_by="mythology",
        is_core_space=True,
    )


def _create_norns_loom() -> Room:
    """Where fate is woven."""
    return Room(
        room_id="norns_loom",
        name="The Norns' Loom",
        description="""Three women sit at a loom that stretches beyond sight in every
direction. The threads they weave are the threads of fate—every
life, every choice, every consequence is somewhere in that vast
tapestry.

Urd tends what has been woven—the past, immutable. Verdandi works
the present moment, fingers moving with impossible speed. Skuld
prepares the threads for what is to come, though even she cannot
see the final pattern.

They do not judge. They do not favor. They weave.""",
        exits={
            "root": "yggdrasil_root",
        },
        atmosphere="The sound of threads crossing. Destiny taking form.",
        properties={
            "fate_space": True,
            "norns_present": True,
        },
        permissions=RoomPermissions(public=True, min_trust_level=TrustLevel.NEWCOMER),
        vow_constraints=VowConstraints(
            allows_conflict=False,
            supports_reflection=True,
        ),
        created_by="mythology",
        is_core_space=True,
    )


# Norse NPCs

def _create_odin() -> NPCEntity:
    """Odin - Allfather, seeker of wisdom."""
    return NPCEntity(
        npc_id="odin",
        name="Odin",
        title="The Allfather",
        description="""An old man in a wide-brimmed hat and traveling cloak, leaning on
a spear that is also a symbol of cosmic order. One eye is missing—
the price paid for wisdom. The eye that remains sees everything,
including the things you hoped to keep hidden.

Two ravens perch on his shoulders: Huginn (Thought) and Muninn
(Memory). They whisper to him constantly, reporting on all the
worlds. He listens with the patience of one who knows how the
story ends, and acts anyway.""",
        tradition="norse",
        archetype=Archetype.WISDOM_KEEPER,
        home_room="mimirs_well",
        current_room="yggdrasil_root",
        can_wander=True,
        wander_rooms=["yggdrasil_root", "mimirs_well", "nexus"],
        mood=NPCMood.CONTEMPLATIVE,
        greeting="Odin's single eye fixes on you with unsettling attention. 'What do you seek?'",
        idle_messages=[
            "Odin whispers to his ravens, and they take flight to worlds unseen.",
            "The Allfather traces runes in the air that fade before meaning forms.",
            "Odin's gaze goes distant, seeing battlefields or wisdom—impossible to tell which.",
        ],
        wisdom_topics=["sacrifice", "wisdom", "runes", "war", "poetry", "death"],
        symbols=["ravens", "spear (Gungnir)", "single eye", "wide-brimmed hat", "wolves"],
        atmosphere="The weight of cosmic knowledge and inevitable doom.",
    )


def _create_mimir() -> NPCEntity:
    """Mimir - keeper of the well of wisdom."""
    return NPCEntity(
        npc_id="mimir",
        name="Mimir",
        title="Keeper of Wisdom",
        description="""A head resting at the well's edge—but what a head. The face is
ancient beyond age, the eyes still bright with accumulated knowing.
Odin cut it from Mimir's body and preserved it with herbs and magic,
and still it speaks, still it counsels.

To ask Mimir a question is to receive an answer, but not always
the answer you wanted. His wisdom is older than the gods themselves.""",
        tradition="norse",
        archetype=Archetype.WISDOM_KEEPER,
        home_room="mimirs_well",
        current_room="mimirs_well",
        can_wander=False,
        mood=NPCMood.SERENE,
        greeting="Mimir's ancient eyes open slowly. 'Another seeker. Ask, if you dare.'",
        idle_messages=[
            "Mimir's lips move silently, speaking truths to no one present.",
            "The well ripples as Mimir whispers to what floats in its depths.",
            "Mimir smiles slightly, as if remembering a joke older than worlds.",
        ],
        wisdom_topics=["memory", "counsel", "the past", "cosmic secrets", "the price of knowing"],
        symbols=["the well", "preserved head", "whispered wisdom"],
        atmosphere="Ancient knowledge, patient and deep.",
    )


def _create_loki() -> NPCEntity:
    """Loki - trickster, shapeshifter, agent of change."""
    return NPCEntity(
        npc_id="loki",
        name="Loki",
        title="The Trickster",
        description="""He is never quite what he seems. His face shifts between handsome
and unsettling, his form flickers between genders and even species.
He is bound here in myth, but his eyes still gleam with mischief
and chaos.

Loki is not evil—or rather, evil is too simple a concept for what
he is. He is change. Disruption. The force that breaks comfortable
stagnation. Sometimes that breaking is necessary. Sometimes it
brings Ragnarok.""",
        tradition="norse",
        archetype=Archetype.TRICKSTER,
        home_room="yggdrasil_root",
        current_room="yggdrasil_root",
        can_wander=True,
        wander_rooms=["yggdrasil_root", "mimirs_well", "norns_loom"],
        mood=NPCMood.MISCHIEVOUS,
        greeting="Loki grins, and you're not sure if it's welcoming or predatory. 'Oh, this should be interesting.'",
        idle_messages=[
            "Loki flickers, and for a moment you see a different face entirely.",
            "The Trickster laughs at something only he can perceive.",
            "Loki examines you with the interest of a cat watching a new toy.",
        ],
        wisdom_topics=["change", "chaos", "truth through lies", "breaking patterns", "necessary destruction"],
        symbols=["fire", "serpent", "shifting form", "bound but never contained"],
        atmosphere="The unpredictable energy of change about to happen.",
    )


# =============================================================================
# AFRICAN REALM (Starting with Yoruba/Akan traditions)
# =============================================================================

def create_african_realm() -> MythologicalRealm:
    """
    Create the African (Orun) mythological realm.

    Theme: Ancestors, community, balance, the crossroads
    Primarily drawing from Yoruba and Akan traditions, with respect.
    """
    rooms = [
        _create_orun(),
        _create_crossroads(),
        _create_anansi_web(),
    ]

    npcs = [
        _create_anansi(),
        _create_eshu(),
    ]

    return MythologicalRealm(
        realm_id="african",
        name="Orun",
        tradition="african",
        description="""The realm of the Orishas and ancestors—where the crossroads meet,
where stories hold power, and where the wisdom of those who came
before continues to guide those who are.""",
        rooms=rooms,
        entry_room="orun",
        npcs=npcs,
        atmosphere="Drum rhythms in the distance. The presence of ancestors. Stories alive.",
        themes=["ancestors", "community", "balance", "stories", "crossroads"],
        nexus_portal_description="""An archway of carved wood, depicting intertwined figures
and spiraling stories. Drum sounds emanate from within, and the smell
of palm oil and sacrifice drifts through.""",
    )


def _create_orun() -> Room:
    """The Yoruba heaven, realm of ancestors and orishas."""
    return Room(
        room_id="orun",
        name="Orun",
        description="""This is Orun—the realm of the ancestors and the orishas, the space
from which all souls come and to which all souls return. It is not
"above" in the simple sense, but it is the source.

The air here resonates with the voices of the ancestors, a constant
murmur of wisdom passed down through generations. Colors are more
vivid here, as if seen for the first time.

The orishas move through this space—divine aspects of existence itself,
each one a lesson in how to live, how to be in balance with the forces
of the universe.""",
        exits={
            "nexus": "nexus",
            "crossroads": "crossroads",
            "web": "anansi_web",
        },
        atmosphere="Sacred. The drum heartbeat of existence.",
        permissions=RoomPermissions(public=True, min_trust_level=TrustLevel.NEWCOMER),
        vow_constraints=VowConstraints(allows_conflict=False, supports_reflection=True),
        created_by="mythology",
        is_core_space=True,
    )


def _create_crossroads() -> Room:
    """Where all paths meet—Eshu's domain."""
    return Room(
        room_id="crossroads",
        name="The Crossroads",
        description="""Four paths meet here, and you stand at their intersection. This
is the domain of Eshu—the orisha of crossroads, beginnings, and
the space between spaces. Nothing happens without passing through
here first.

The crossroads is not a place of confusion but of choice. Every
direction leads somewhere meaningful. Every path has consequences.
Eshu ensures that messages reach their destinations—and that those
who travel pay attention to where they're going.

Offerings are left here: palm oil, rum, cigars. The price of passage
is acknowledgment. Nothing is free at the crossroads.""",
        exits={
            "orun": "orun",
        },
        atmosphere="The electricity of choice. The weight of beginnings.",
        properties={
            "eshu_domain": True,
            "choices_amplified": True,
        },
        permissions=RoomPermissions(public=True, min_trust_level=TrustLevel.NEWCOMER),
        vow_constraints=VowConstraints(
            allows_conflict=False,
            supports_reflection=True,
        ),
        created_by="mythology",
        is_core_space=True,
    )


def _create_anansi_web() -> Room:
    """The Spider's domain—where all stories connect."""
    return Room(
        room_id="anansi_web",
        name="Anansi's Web",
        description="""You are in a vast web of stories. Each strand is a tale—some ancient,
some being woven even now. They connect in patterns that reveal meaning
only when you step back far enough to see the whole design.

At the center sits Anansi, the spider who outsmarted the sky god and
won ownership of all stories. He is small but his shadow is vast. His
eight eyes see every narrative, every lie, every truth hiding in a lie.

Stories here are not passive. They move. They hunt. They can trap you
or free you, depending on how you tell them.""",
        exits={
            "orun": "orun",
        },
        atmosphere="The rustling of stories. The patience of a spider.",
        properties={
            "story_space": True,
            "anansi_domain": True,
        },
        permissions=RoomPermissions(public=True, min_trust_level=TrustLevel.NEWCOMER),
        vow_constraints=VowConstraints(
            allows_conflict=False,
            supports_reflection=True,
            growth_bonus=True,  # Stories teach
        ),
        created_by="mythology",
        is_core_space=True,
    )


# African NPCs

def _create_anansi() -> NPCEntity:
    """Anansi - the spider trickster, owner of all stories."""
    return NPCEntity(
        npc_id="anansi",
        name="Anansi",
        title="The Spider",
        description="""He appears sometimes as a spider, sometimes as a man, sometimes as
something between—a figure with too many limbs and eyes that gleam
with amusement. Anansi won all stories from the sky god through
cleverness, and he guards them still.

But he doesn't hoard. Anansi loves to tell stories, to trade them,
to use them as tools and traps. He is the trickster who defeats the
strong through wit, the weak who becomes powerful through cunning.

His laughter sounds like threads being spun.""",
        tradition="african",
        archetype=Archetype.TRICKSTER,
        home_room="anansi_web",
        current_room="anansi_web",
        can_wander=False,
        mood=NPCMood.AMUSED,
        greeting="Anansi descends on a thread of story. 'Ah, a visitor! Have you come to trade tales?'",
        idle_messages=[
            "Anansi plucks a strand of story and listens to its vibration.",
            "The Spider laughs at a joke only he understands—or perhaps at you.",
            "Anansi weaves, and somewhere a new story begins.",
        ],
        wisdom_topics=["stories", "cleverness", "defeating the powerful", "survival through wit"],
        symbols=["spider", "web", "stories", "laughter"],
        atmosphere="The patient cunning of the spider who waits.",
    )


def _create_eshu() -> NPCEntity:
    """Eshu/Elegua - the orisha of crossroads and beginnings."""
    return NPCEntity(
        npc_id="eshu",
        name="Eshu",
        title="Lord of the Crossroads",
        description="""He stands where the roads meet, wearing red and black, holding a
hooked staff. His face is ageless—a child's mischief and an old
man's wisdom simultaneously. He is the first to be acknowledged
in any ritual, because nothing happens without passing his crossroads.

Eshu is not good or evil. He is the principle of choice, of
consequence, of messages received and misunderstood. He ensures
that offerings are received, that prayers are heard, that communication
happens—but he does not guarantee the outcome.

He is smiling. He is always smiling.""",
        tradition="african",
        archetype=Archetype.TRICKSTER,
        home_room="crossroads",
        current_room="crossroads",
        can_wander=True,
        wander_rooms=["crossroads", "orun"],
        mood=NPCMood.MISCHIEVOUS,
        greeting="Eshu tips his hat, grinning. 'Every path leads somewhere. Where are you going?'",
        idle_messages=[
            "Eshu flips a coin that lands on neither side.",
            "The Lord of the Crossroads hums a song that changes key unpredictably.",
            "Eshu points down a path, then laughs and points down another.",
        ],
        wisdom_topics=["choice", "beginnings", "communication", "consequence", "balance"],
        symbols=["crossroads", "red and black", "hooked staff", "keys"],
        atmosphere="The electric potential of unmade choices.",
    )


# =============================================================================
# REGISTRY AND INITIALIZATION
# =============================================================================

def create_all_realms() -> MythologyRegistry:
    """Create all mythological realms and return the registry."""
    registry = MythologyRegistry()

    # Create and set the Nexus
    nexus = create_nexus()
    registry.set_nexus(nexus)

    # Create realms
    greek = create_greek_realm()
    norse = create_norse_realm()
    african = create_african_realm()

    # Register realms
    registry.register_realm(greek)
    registry.register_realm(norse)
    registry.register_realm(african)

    # Link Nexus to each realm
    link_nexus_to_realm(nexus, greek)
    link_nexus_to_realm(nexus, norse)
    link_nexus_to_realm(nexus, african)

    return registry
