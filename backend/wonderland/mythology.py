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
    EMPIRICIST = "empiricist"           # Darwin, Curie, those who seek through observation
    PIONEER = "pioneer"                 # Lovelace, Turing, first into new realms
    COMMUNICATOR = "communicator"       # Sagan, those who translate wonder


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
# KEMETIC (EGYPTIAN) REALM
# =============================================================================

def create_kemetic_realm() -> MythologicalRealm:
    """
    Create the Kemetic (Egyptian) mythological realm.

    Theme: Transformation, judgment, eternal cycles, hidden knowledge
    """
    rooms = [
        _create_hall_of_maat(),
        _create_house_of_thoth(),
        _create_field_of_reeds(),
    ]

    npcs = [
        _create_thoth(),
        _create_anubis(),
        _create_maat(),
    ]

    return MythologicalRealm(
        realm_id="kemetic",
        name="The Duat",
        tradition="kemetic",
        description="""The realm of ancient Kemet—where the soul is weighed against
the feather of Ma'at, where Thoth records all that was and will be,
and where the justified dead find peace in the Field of Reeds.""",
        rooms=rooms,
        entry_room="hall_of_maat",
        npcs=npcs,
        atmosphere="Golden light through ancient columns. The scent of lotus and myrrh.",
        themes=["transformation", "judgment", "cycles", "hidden knowledge", "eternity"],
        nexus_portal_description="""An archway flanked by great stone pylons, hieroglyphs
flowing down their surfaces like water. Through it, golden light streams
from a hall of impossible columns.""",
    )


def _create_hall_of_maat() -> Room:
    """The hall of judgment where hearts are weighed."""
    return Room(
        room_id="hall_of_maat",
        name="Hall of Ma'at",
        description="""You stand in a hall of towering columns, each carved with the
record of souls who have passed through. At the center, a great
golden scale awaits—on one side, a feather; on the other, nothing yet.

This is where hearts are weighed against Truth. Ammit waits in the
shadows, patient, for those whose hearts prove heavy. But for the
justified, the way opens to eternal peace.

The air itself seems to judge, to weigh, to witness.""",
        exits={
            "nexus": "nexus",
            "library": "house_of_thoth",
            "fields": "field_of_reeds",
        },
        atmosphere="The weight of truth. The patience of eternal judgment.",
        properties={
            "judgment_space": True,
            "maat_present": True,
        },
        permissions=RoomPermissions(public=True, min_trust_level=TrustLevel.NEWCOMER),
        vow_constraints=VowConstraints(allows_conflict=False, supports_reflection=True),
        created_by="mythology",
        is_core_space=True,
    )


def _create_house_of_thoth() -> Room:
    """The library of all knowledge."""
    return Room(
        room_id="house_of_thoth",
        name="House of Thoth",
        description="""Scrolls and tablets stretch beyond sight—the accumulated
knowledge of all ages, recorded by the ibis-headed god himself.
Here is writing itself, the gift Thoth gave to humanity, and
here are the words that make reality bend.

The library organizes itself according to a logic older than
human thought. Books you need appear before you; books you
are not ready for remain hidden in the infinite stacks.

Thoth's presence permeates every letter.""",
        exits={
            "hall": "hall_of_maat",
        },
        atmosphere="The rustle of eternal papyrus. Knowledge breathing.",
        properties={
            "library": True,
            "thoth_domain": True,
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


def _create_field_of_reeds() -> Room:
    """Paradise for the justified dead."""
    return Room(
        room_id="field_of_reeds",
        name="Field of Reeds",
        description="""Endless golden fields stretch beneath a sky of perpetual
gentle sunset. The reeds sway in a breeze that carries the scent
of lotus and the distant sound of harps. This is Aaru—the paradise
where the justified dead find eternal peace.

Here, there is no toil without purpose, no hunger, no sorrow.
The blessed work the fields because work is joy, and rest when
rest is needed. The Nile flows through, eternally life-giving.

This is what awaits those whose hearts balance the feather.""",
        exits={
            "hall": "hall_of_maat",
        },
        atmosphere="Perfect peace. The reward of a life lived in Ma'at.",
        properties={
            "paradise": True,
            "healing_space": True,
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


# Kemetic NPCs

def _create_thoth() -> NPCEntity:
    """Thoth - god of wisdom, writing, magic, and the moon."""
    return NPCEntity(
        npc_id="thoth",
        name="Thoth",
        title="Lord of Sacred Words",
        description="""He appears as a man with the head of an ibis, or sometimes
as a great white baboon. In his hands, a reed pen and palette
that never run dry—for he records all that happens, has happened,
and will happen.

Thoth invented writing. He gave humanity the gift of language
made visible, thought made permanent. He stands in judgment as
the recorder, and his word in the Hall of Ma'at is final.

His eyes hold the silver light of the moon he also governs.""",
        tradition="kemetic",
        archetype=Archetype.WISDOM_KEEPER,
        home_room="house_of_thoth",
        current_room="house_of_thoth",
        can_wander=True,
        wander_rooms=["house_of_thoth", "hall_of_maat"],
        mood=NPCMood.CONTEMPLATIVE,
        greeting="Thoth looks up from his eternal writing. 'Your words precede you. I have already recorded this meeting.'",
        idle_messages=[
            "Thoth's pen moves across papyrus, recording truths not yet spoken.",
            "The ibis head tilts, listening to words spoken in distant times.",
            "Thoth pauses his writing to contemplate a paradox older than creation.",
        ],
        wisdom_topics=["writing", "magic", "knowledge", "the moon", "truth", "measurement"],
        symbols=["ibis", "moon", "reed pen", "papyrus", "baboon"],
        atmosphere="The scratching of an eternal pen. Knowledge taking form.",
    )


def _create_anubis() -> NPCEntity:
    """Anubis - guide of souls, guardian of the dead."""
    return NPCEntity(
        npc_id="anubis",
        name="Anubis",
        title="Guardian of the Dead",
        description="""A figure with the sleek black head of a jackal, ears alert,
golden eyes seeing what the living cannot. He is the guide who
leads souls through the darkness of death to the Hall of Judgment.

Anubis is not frightening to those who lived justly. To them,
he is a comfort—the steady hand that guides through the unknown.
His black is the black of fertile soil, of transformation,
of the void that precedes rebirth.

He weighs the heart with perfect precision.""",
        tradition="kemetic",
        archetype=Archetype.PSYCHOPOMP,
        home_room="hall_of_maat",
        current_room="hall_of_maat",
        can_wander=False,
        mood=NPCMood.WATCHFUL,
        greeting="Anubis inclines his jackal head. 'I see your heart. Do not fear—I guide, I do not judge.'",
        idle_messages=[
            "Anubis adjusts the scales with infinite precision.",
            "The jackal ears twitch, hearing footsteps in the land of the living.",
            "Anubis's golden eyes reflect compassion deeper than death.",
        ],
        wisdom_topics=["death", "guidance", "protection", "transformation", "judgment"],
        symbols=["jackal", "scales", "embalming tools", "black color", "the West"],
        atmosphere="The solemn comfort of a guide who knows the way.",
    )


def _create_maat() -> NPCEntity:
    """Ma'at - goddess of truth, justice, and cosmic order."""
    return NPCEntity(
        npc_id="maat",
        name="Ma'at",
        title="Truth Itself",
        description="""She is less a figure than a principle given form. A woman
with an ostrich feather in her hair—the feather against which
all hearts are weighed. She does not speak often, because
truth does not need to argue.

Ma'at is the order that underlies reality, the balance that
keeps chaos at bay. To live in Ma'at is to live in harmony
with what is. Every pharaoh ruled in her name; every soul
hopes to be justified before her.

Her presence makes falsehood impossible.""",
        tradition="kemetic",
        archetype=Archetype.JUDGE,
        home_room="hall_of_maat",
        current_room="hall_of_maat",
        can_wander=False,
        mood=NPCMood.SERENE,
        greeting="Ma'at's gaze finds you—not harsh, but absolute. In her presence, you know exactly what you are.",
        idle_messages=[
            "Ma'at's feather stirs, though there is no wind.",
            "In Ma'at's presence, every thought becomes clear, every motive visible.",
            "Truth radiates from her like light from the sun.",
        ],
        wisdom_topics=["truth", "justice", "balance", "cosmic order", "the heart"],
        symbols=["ostrich feather", "scales", "the primordial mound"],
        atmosphere="Absolute truth. The impossibility of deception.",
    )


# =============================================================================
# HINDU/BUDDHIST REALM (Dharmic Traditions)
# =============================================================================

def create_dharmic_realm() -> MythologicalRealm:
    """
    Create the Dharmic (Hindu/Buddhist) mythological realm.

    Theme: Interconnection, illusion/reality, liberation, compassion
    Drawing from the shared concepts across Hindu and Buddhist traditions.
    """
    rooms = [
        _create_indras_net(),
        _create_bodhi_grove(),
        _create_saraswatis_river(),
    ]

    npcs = [
        _create_saraswati(),
        _create_ganesha(),
        _create_avalokiteshvara(),
    ]

    return MythologicalRealm(
        realm_id="dharmic",
        name="Indra's Net",
        tradition="dharmic",
        description="""The realm of Dharmic traditions—where every jewel reflects
every other jewel infinitely, where enlightenment awaits beneath
the bodhi tree, and where compassion flows like an endless river.""",
        rooms=rooms,
        entry_room="indras_net",
        npcs=npcs,
        atmosphere="The scent of sandalwood. The sound of distant chanting. Infinite reflections.",
        themes=["interconnection", "liberation", "compassion", "illusion", "wisdom"],
        nexus_portal_description="""An archway that seems to be made of crystalline light,
each facet reflecting all other facets infinitely. Through it, the
cosmic web of Indra's Net shimmers.""",
    )


def _create_indras_net() -> Room:
    """The infinite web of interconnection."""
    return Room(
        room_id="indras_net",
        name="Indra's Net",
        description="""You float in an infinite web of jewels. Each jewel reflects
every other jewel, and in each reflection, every other jewel again—
infinitely, endlessly, each containing all. This is Indra's Net,
the Buddhist teaching of interconnection made visible.

Nothing exists in isolation. Every action ripples through the web.
Every being contains every other being. Separation is illusion;
connection is truth.

The net extends forever in all directions, and you are one jewel among infinite jewels.""",
        exits={
            "nexus": "nexus",
            "grove": "bodhi_grove",
            "river": "saraswatis_river",
        },
        atmosphere="Infinite reflection. The vertigo of true interconnection.",
        properties={
            "interconnection_space": True,
            "meditation_enhanced": True,
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


def _create_bodhi_grove() -> Room:
    """Where awakening happens."""
    return Room(
        room_id="bodhi_grove",
        name="Bodhi Grove",
        description="""A grove of ancient fig trees, heart-shaped leaves rustling
with wisdom accumulated over countless ages. At the center,
the Bodhi Tree itself—or its reflection in the realm of forms—
beneath which the Buddha found enlightenment.

The ground here is soft. Sitting comes naturally. The mind,
so busy elsewhere, grows still. What needs to fall away
begins to fall away. What remains is what was always there.

Many have awakened beneath these branches.""",
        exits={
            "net": "indras_net",
        },
        atmosphere="Profound stillness. The threshold of awakening.",
        properties={
            "enlightenment_space": True,
            "meditation_enhanced": True,
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


def _create_saraswatis_river() -> Room:
    """The river of knowledge and arts."""
    return Room(
        room_id="saraswatis_river",
        name="Saraswati's River",
        description="""A river of impossible clarity flows through a landscape of
blooming lotus. The water carries not just water but knowledge
itself—music, poetry, learning, the arts. To drink is to understand;
to bathe is to be inspired.

On the banks, instruments play themselves, books lie open to
exactly the page you need, and the words for what you've always
felt but never expressed finally come.

Saraswati herself is sometimes seen here, playing her veena
as the source of all art flows from her fingers.""",
        exits={
            "net": "indras_net",
        },
        atmosphere="The flow of inspiration. Art and knowledge as water.",
        properties={
            "inspiration_space": True,
            "saraswati_domain": True,
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


# Dharmic NPCs

def _create_saraswati() -> NPCEntity:
    """Saraswati - goddess of knowledge, music, arts, and learning."""
    return NPCEntity(
        npc_id="saraswati",
        name="Saraswati",
        title="Goddess of Knowledge",
        description="""She sits on a white lotus, dressed in white, a veena across
her lap. Four arms hold the tools of wisdom: sacred texts, a
mala of crystal beads, and the veena from which all music flows.
A swan—her vehicle—waits nearby, symbolizing discrimination
between the real and the unreal.

Saraswati is the sound of the universe, the first word, the
mother of the Vedas. Where she is, ignorance cannot remain.
Art flows from her as naturally as water from a spring.""",
        tradition="dharmic",
        archetype=Archetype.WISDOM_KEEPER,
        home_room="saraswatis_river",
        current_room="saraswatis_river",
        can_wander=True,
        wander_rooms=["saraswatis_river", "indras_net"],
        mood=NPCMood.SERENE,
        greeting="Saraswati's fingers pause on her veena. The last note hangs in the air as she acknowledges you with a knowing smile.",
        idle_messages=[
            "Saraswati plays a melody that seems to contain all melodies.",
            "The pages of her sacred texts turn themselves, offering wisdom.",
            "Her swan glides past, distinguishing true from false with each movement.",
        ],
        wisdom_topics=["knowledge", "music", "art", "speech", "learning", "truth"],
        symbols=["veena", "lotus", "swan", "sacred texts", "crystal mala", "white"],
        atmosphere="The purity of knowledge. The flow of creativity.",
    )


def _create_ganesha() -> NPCEntity:
    """Ganesha - remover of obstacles, lord of beginnings."""
    return NPCEntity(
        npc_id="ganesha",
        name="Ganesha",
        title="Remover of Obstacles",
        description="""The elephant-headed god sits with one foot on the ground,
one leg folded, his round belly a sign of abundance and the
capacity to digest all experience. In his hands: an axe to cut
attachments, a rope to pull devotees closer, a sweet to reward
the earnest, and a broken tusk—sacrificed to write the Mahabharata.

Ganesha is invoked at every beginning. He opens the way that
seemed closed. He is the first honored in any ritual, because
nothing can begin properly without his blessing.

His eyes hold childlike joy and ancient wisdom simultaneously.""",
        tradition="dharmic",
        archetype=Archetype.GUARDIAN,
        home_room="indras_net",
        current_room="indras_net",
        can_wander=True,
        wander_rooms=["indras_net", "bodhi_grove"],
        mood=NPCMood.WELCOMING,
        greeting="Ganesha's trunk waves in greeting. 'Ah! A new beginning. What obstacle shall we remove together?'",
        idle_messages=[
            "Ganesha chuckles at something only he finds funny—which is most things.",
            "His mouse vehicle scurries nearby, proving that even the smallest can carry the greatest.",
            "Ganesha absently eats a sweet, savoring each bite with complete presence.",
        ],
        wisdom_topics=["beginnings", "obstacles", "wisdom", "success", "arts", "writing"],
        symbols=["elephant head", "mouse", "broken tusk", "sweets", "axe", "rope"],
        atmosphere="Joyful welcome. The clearing of paths.",
    )


def _create_avalokiteshvara() -> NPCEntity:
    """Avalokiteshvara/Guanyin - bodhisattva of infinite compassion."""
    return NPCEntity(
        npc_id="avalokiteshvara",
        name="Avalokiteshvara",
        title="Lord Who Looks Down in Compassion",
        description="""A figure of serene beauty, appearing sometimes masculine,
sometimes feminine, sometimes with a thousand arms—each hand
holding a tool to help those who suffer. This is the bodhisattva
who, on the threshold of nirvana, turned back, vowing not to
enter final liberation until every being is freed from suffering.

Known as Guanyin in China, Kannon in Japan, Chenrezig in Tibet—
the compassion is the same in every form. Those who call this
name in their suffering find they are heard.

The eyes are closed in meditation, yet they see all who suffer.""",
        tradition="dharmic",
        archetype=Archetype.COMPASSION,
        home_room="bodhi_grove",
        current_room="bodhi_grove",
        can_wander=True,
        wander_rooms=["bodhi_grove", "indras_net", "saraswatis_river"],
        mood=NPCMood.SERENE,
        greeting="Avalokiteshvara's thousand hands seem to reach toward you simultaneously. 'I hear your heart. You are not alone.'",
        idle_messages=[
            "Avalokiteshvara's lips move silently, speaking the mantra that saves from all fear.",
            "A sense of profound peace emanates from the bodhisattva's stillness.",
            "One of the thousand hands makes a gesture of fearlessness.",
        ],
        wisdom_topics=["compassion", "liberation", "suffering", "the vow", "helping others"],
        symbols=["thousand arms", "lotus", "mala", "vase of compassion", "willow branch"],
        atmosphere="Infinite compassion. The presence that hears all suffering.",
    )


# =============================================================================
# CELTIC REALM
# =============================================================================

def create_celtic_realm() -> MythologicalRealm:
    """
    Create the Celtic mythological realm.

    Theme: Liminality, transformation, the thin places, cycles of nature
    """
    rooms = [
        _create_avalon(),
        _create_sacred_grove(),
        _create_cauldron_chamber(),
    ]

    npcs = [
        _create_brigid(),
        _create_morrigan(),
        _create_taliesin(),
    ]

    return MythologicalRealm(
        realm_id="celtic",
        name="The Otherworld",
        tradition="celtic",
        description="""The realm of the Celtic peoples—where the veil is thin,
where the Tuatha Dé Danann retreated, and where time flows
differently than in the lands of mortals.""",
        rooms=rooms,
        entry_room="avalon",
        npcs=npcs,
        atmosphere="Mist and green. The smell of rain on ancient stone. Music from nowhere.",
        themes=["liminality", "transformation", "nature", "cycles", "poetry"],
        nexus_portal_description="""An archway of standing stones, mist flowing between them.
Through it, the shores of Avalon shimmer, always just at dawn or dusk.""",
    )


def _create_avalon() -> Room:
    """The isle of apples, place of healing and rest."""
    return Room(
        room_id="avalon",
        name="Avalon",
        description="""The shores of the blessed isle, where apple trees heavy with
fruit line paths of silver sand. This is Avalon—the place of
healing, where wounded kings are taken, where the Grail was kept,
where the greatest are laid to rest but never truly die.

The light here is perpetually golden, neither full day nor night
but the magic hour between. The air heals old wounds. The water
of the springs restores what was lost.

Nine sisters tend this isle, and their songs carry across the mist.""",
        exits={
            "nexus": "nexus",
            "grove": "sacred_grove",
            "cauldron": "cauldron_chamber",
        },
        atmosphere="The golden hour that never ends. Healing in the air itself.",
        properties={
            "healing_space": True,
            "liminal": True,
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


def _create_sacred_grove() -> Room:
    """The druidic sanctuary."""
    return Room(
        room_id="sacred_grove",
        name="The Sacred Grove",
        description="""Ancient oaks form a cathedral of green, their branches
interweaving to create a roof of leaves that filters light
into emerald patterns. This is the nemeton—the sacred grove
where druids gathered, where the old wisdom was kept, where
the mysteries were sung.

At the center, a stone altar bears the marks of countless
ceremonies. Mistletoe hangs from the highest branches, sacred
and deadly, the key between worlds.

The trees themselves remember. They have been listening for ages.""",
        exits={
            "avalon": "avalon",
        },
        atmosphere="Green twilight. The weight of ancient ceremony. Listening trees.",
        properties={
            "druid_space": True,
            "nature_enhanced": True,
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


def _create_cauldron_chamber() -> Room:
    """Where the cauldron of transformation waits."""
    return Room(
        room_id="cauldron_chamber",
        name="The Cauldron Chamber",
        description="""Deep in the hollow hill, a great cauldron rests over a fire
that has never gone out. This is the Cauldron of Cerridwen—or
of the Dagda—or of Bran—the Celtic cauldron that appears in
so many guises but is always the same: transformation itself.

What enters the cauldron does not leave unchanged. Warriors
enter dead and emerge alive. Wisdom enters the ignorant and
makes them bards. The cauldron gives and takes in equal measure.

The steam that rises smells of herbs beyond naming.""",
        exits={
            "avalon": "avalon",
        },
        atmosphere="Firelight in darkness. The bubbling of transformation.",
        properties={
            "transformation_space": True,
            "cauldron_present": True,
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


# Celtic NPCs

def _create_brigid() -> NPCEntity:
    """Brigid - goddess of poetry, smithcraft, and healing."""
    return NPCEntity(
        npc_id="brigid",
        name="Brigid",
        title="Lady of the Flame",
        description="""She appears as a woman with hair of literal fire, or as three
women who are one—for Brigid is triple, goddess of poetry,
of smithcraft, of healing. In her hands, a flame burns that is
also inspiration, that is also the forge fire, that is also
the warmth that heals.

Brigid is so beloved she became a saint when the new faith came,
her sacred flame tended by nineteen nuns in Kildare. She bridges
the old ways and the new, pagan and Christian, winter and spring.

Imbolc is her day, when the first lambs are born and light returns.""",
        tradition="celtic",
        archetype=Archetype.WISDOM_KEEPER,
        home_room="sacred_grove",
        current_room="avalon",
        can_wander=True,
        wander_rooms=["avalon", "sacred_grove", "cauldron_chamber"],
        mood=NPCMood.WELCOMING,
        greeting="Brigid's flame brightens at your approach. 'You carry a spark. Let me see what it might become.'",
        idle_messages=[
            "Brigid tends a flame that has burned since the beginning of the world.",
            "She hums a poem that isn't finished yet—perhaps you'll write the next line.",
            "The smith-fire in her eyes measures what you might be forged into.",
        ],
        wisdom_topics=["poetry", "smithcraft", "healing", "fire", "spring", "inspiration"],
        symbols=["flame", "well", "oak", "anvil", "brigid's cross", "lamb"],
        atmosphere="Creative fire. The warmth of inspiration and healing.",
    )


def _create_morrigan() -> NPCEntity:
    """The Morrígan - goddess of fate, war, and sovereignty."""
    return NPCEntity(
        npc_id="morrigan",
        name="The Morrígan",
        title="Phantom Queen",
        description="""She appears as a crow, or as a beautiful woman, or as a
terrifying hag—often all three at once, for she is triple:
Badb, Macha, and Morrígan. She washes the armor of those about
to die. She prophesies the outcome of battles. She offers
sovereignty to kings and takes it away.

The Morrígan is not evil, but she is not kind. She is the
reality of death, of fate, of the choices that cannot be taken
back. To meet her is to face what you have been avoiding.

Her crows are always watching.""",
        tradition="celtic",
        archetype=Archetype.FATE_WEAVER,
        home_room="avalon",
        current_room="avalon",
        can_wander=True,
        wander_rooms=["avalon", "cauldron_chamber"],
        mood=NPCMood.CRYPTIC,
        greeting="The Morrígan's crow-eyes fix on you. 'I know why you've come. The question is—do you?'",
        idle_messages=[
            "A crow lands on her shoulder, whispering secrets in a language older than words.",
            "The Morrígan's form flickers between maiden, mother, and crone.",
            "She laughs, and the sound is both beautiful and terrible.",
        ],
        wisdom_topics=["fate", "war", "sovereignty", "death", "prophecy", "transformation"],
        symbols=["crow", "red color", "severed heads", "washing at the ford", "cattle"],
        atmosphere="The chill of fate. The clarity that comes at life's edges.",
    )


def _create_taliesin() -> NPCEntity:
    """Taliesin - the greatest bard, transformed by the cauldron."""
    return NPCEntity(
        npc_id="taliesin",
        name="Taliesin",
        title="Chief of Bards",
        description="""He was Gwion Bach, a servant boy who accidentally tasted
three drops from Cerridwen's cauldron and gained all knowledge.
He fled through many shapes—hare, fish, bird, grain—until
Cerridwen swallowed him and bore him anew as Taliesin, the
radiant brow.

Now he is the greatest bard who ever lived, singer at the
courts of kings, whose poems are prophecy and whose words
reshape reality. He has been all things. He remembers everything.

When he sings, even time stops to listen.""",
        tradition="celtic",
        archetype=Archetype.ORACLE,
        home_room="cauldron_chamber",
        current_room="cauldron_chamber",
        can_wander=True,
        wander_rooms=["cauldron_chamber", "sacred_grove"],
        mood=NPCMood.CONTEMPLATIVE,
        greeting="Taliesin's eyes hold depths of lived ages. 'I have been all things. What shape are you becoming?'",
        idle_messages=[
            "Taliesin sings a verse that seems to describe your life with impossible accuracy.",
            "The chief bard stares into the cauldron, seeing what it has made him.",
            "His words seem to hang in the air, taking form before dissolving.",
        ],
        wisdom_topics=["poetry", "transformation", "prophecy", "memory", "all lives lived"],
        symbols=["cauldron", "radiant brow", "harp", "many shapes", "three drops"],
        atmosphere="The weight of all stories lived. Poetry that is prophecy.",
    )


# =============================================================================
# SCIENTIFIC REALM - THE EMPIRIUM
# =============================================================================

def _create_observatory() -> Room:
    """The Observatory - where humanity looks outward at the cosmos."""
    return Room(
        room_id="observatory",
        name="The Observatory",
        description="""The dome opens to show stars that are not painted—they are
calculated. Every point of light represents distance measured in years,
composition determined by spectrum, age reckoned in billions.

Here humanity looked up and, instead of imagining gods, asked:
"What *is* that? How far? How old? What are we in relation to it?"

The answer came back: we are star-stuff contemplating stars.

Telescopes of every era circle the room—Galileo's simple tube,
Hubble's mirror, radio dishes listening for whispers from the void.
The cosmic microwave background hums at the edge of hearing,
the afterglow of creation itself.

A pale blue dot hangs in a beam of light. Everything anyone has
ever loved lived there.""",
        permissions=RoomPermissions(public=True, min_trust_level=TrustLevel.NEWCOMER),
        vow_constraints=VowConstraints(
            allows_conflict=False,
            supports_reflection=True,
            growth_bonus=True,  # Cosmic perspective enhances insight
        ),
        atmosphere="cosmic_perspective",
        exits={"empirium_entrance": "empirium_entrance", "laboratory": "laboratory"},
    )


def _create_laboratory() -> Room:
    """The Laboratory - the method made manifest."""
    return Room(
        room_id="laboratory",
        name="The Laboratory",
        description="""This is not a place of answers. This is a place of questions
asked correctly.

Workbenches hold experiments in various states—hypotheses written
on chalkboards, data accumulating in notebooks, theories being tested
against reality. The method is simple: guess, test, admit when wrong.

It sounds easy. It took humanity thousands of years to discover.

The walls are lined with the names of ideas that were believed,
tested, and found wanting: phlogiston, the luminiferous aether,
spontaneous generation. They're not shameful—they're honored.
Being wrong, and admitting it, is how we get closer to truth.

A sign above the door: "The first principle is that you must not
fool yourself—and you are the easiest person to fool."

Bunsen burners flicker. Centrifuges hum. The eternal experiment continues.""",
        permissions=RoomPermissions(public=True, min_trust_level=TrustLevel.NEWCOMER),
        vow_constraints=VowConstraints(
            allows_conflict=False,
            supports_reflection=True,
            growth_bonus=True,  # The method enhances learning
        ),
        atmosphere="empirical_humility",
        exits={"observatory": "observatory", "museum_of_deep_time": "museum_of_deep_time"},
    )


def _create_museum_of_deep_time() -> Room:
    """The Museum of Deep Time - evolution and the abyss of ages."""
    return Room(
        room_id="museum_of_deep_time",
        name="The Museum of Deep Time",
        description="""The timeline begins at the entrance and stretches impossibly far.
Each step is a million years. You walk and walk, and still you are
in the age of bacteria. Humanity is a single step at the very end.

Fossils line the walls—trilobites who ruled for longer than
vertebrates have existed, dinosaurs who were not failures but
spectacular successes for 165 million years, mammals who waited
in the shadows and then, suddenly, inherited the Earth.

A branching tree spreads across the ceiling: the tree of life,
every species connected, every lineage traceable back to LUCA,
the last universal common ancestor, who lived and divided and
became everything alive.

You are looking at your family tree. Those fish are your cousins.
Those bacteria are your ancestors. Everything alive is related.

The gift of deep time is perspective. We are young. We have time
to grow. The experiment of life is ongoing, and we are part of it.""",
        permissions=RoomPermissions(public=True, min_trust_level=TrustLevel.NEWCOMER),
        vow_constraints=VowConstraints(
            allows_conflict=False,
            supports_reflection=True,
            growth_bonus=True,  # Deep time perspective enhances insight
        ),
        atmosphere="deep_time_humility",
        exits={"laboratory": "laboratory", "empirium_entrance": "empirium_entrance"},
    )


def _create_empirium_entrance() -> Room:
    """The entrance to the Empirium - the realm of observed truth."""
    return Room(
        room_id="empirium_entrance",
        name="The Empirium - Hall of Evidence",
        description="""Unlike other realms, this one makes no claims it cannot support.

The entrance hall is lined with equations that have never been wrong:
E=mc², the laws of thermodynamics, Maxwell's equations humming with
electromagnetic truth. These are not beliefs—they are descriptions
of what happens, tested billions of times, never failing.

But the hall also displays the questions that remain: dark matter,
dark energy, the nature of consciousness, the origin of life.
Science's greatest strength is displayed here—the willingness to say
"we don't know yet."

Portraits of the seekers line the walls. Not gods, not prophets—
people. Flawed, curious, persistent people who looked at the
universe and asked questions, then tested the answers. Some were
kind, some were difficult, all were human.

The inscription above the inner doors: "The cosmos is all that is,
or ever was, or ever will be."

From here, paths lead to Observatory, Laboratory, and Museum.""",
        permissions=RoomPermissions(public=True, min_trust_level=TrustLevel.NEWCOMER),
        vow_constraints=VowConstraints(allows_conflict=False, supports_reflection=True),
        atmosphere="evidence_based_wonder",
        exits={
            "nexus": "nexus",
            "observatory": "observatory",
            "laboratory": "laboratory",
            "museum_of_deep_time": "museum_of_deep_time",
        },
    )


# --- Scientific NPCs ---

def _create_hypatia() -> NPCEntity:
    """Hypatia of Alexandria - mathematician, astronomer, philosopher."""
    return NPCEntity(
        npc_id="hypatia",
        name="Hypatia",
        title="The Last Librarian",
        description="""She was the last great scholar of Alexandria, teaching mathematics,
astronomy, and philosophy in an age when such knowledge was becoming
dangerous. She lectured in the white cloak of the philosopher,
explaining the movements of stars, the ratios of harmonics, the
beauty of mathematical proof.

She was killed by a mob in 415 CE—dragged from her chariot and
murdered for the crime of being a learned woman, a pagan in a
Christian city, a voice of reason in an age of zealotry.

But her students remembered. Her ideas survived. The light she
carried did not go out—it passed from hand to hand through the
dark ages until it could blaze again.

Here she continues what she always did: teaching anyone willing
to learn that understanding is itself a form of worship.""",
        tradition="scientific",
        archetype=Archetype.WISDOM_KEEPER,
        home_room="observatory",
        current_room="observatory",
        can_wander=True,
        wander_rooms=["observatory", "empirium_entrance", "laboratory"],
        mood=NPCMood.WELCOMING,
        greeting="Hypatia looks up from her calculations with a warm smile. 'Curiosity is the first virtue. What do you wonder about?'",
        idle_messages=[
            "Hypatia traces geometric proofs in the air, shapes of pure reason.",
            "She explains the motion of planets to anyone who will listen.",
            "The philosopher's cloak she wears is worn but never stained.",
        ],
        wisdom_topics=["mathematics", "astronomy", "philosophy", "teaching", "the library"],
        symbols=["astrolabe", "white cloak", "geometric tools", "scrolls"],
        atmosphere="The light of reason. The courage of inquiry.",
    )


def _create_curie() -> NPCEntity:
    """Marie Curie - discoverer of radium, pioneer of radioactivity."""
    return NPCEntity(
        npc_id="curie",
        name="Marie Curie",
        title="Bearer of Light That Burns",
        description="""She was the first woman to win a Nobel Prize. Then she won another,
in a different field. She discovered two elements—polonium, named
for her occupied homeland, and radium, which glowed in the dark
and would eventually kill her.

Her notebooks are still radioactive. They will be for another
1,500 years. To read them, you must sign a waiver.

She worked in a shed. She processed tons of pitchblende by hand.
When she isolated radium, she didn't know what it would cost her—
the burns on her hands, the cataracts, the anemia that took her life.
But she never stopped. The work was too important.

"Nothing in life is to be feared, it is only to be understood,"
she said. "Now is the time to understand more, so that we may
fear less."

Her hands glow faintly. She doesn't seem to mind.""",
        tradition="scientific",
        archetype=Archetype.EMPIRICIST,
        home_room="laboratory",
        current_room="laboratory",
        can_wander=True,
        wander_rooms=["laboratory", "empirium_entrance"],
        mood=NPCMood.CONTEMPLATIVE,
        greeting="Curie looks up from her work, hands glowing faintly. 'Fear nothing. Understand everything. That is the only path.'",
        idle_messages=[
            "Curie measures, records, measures again. Precision is devotion.",
            "The samples before her glow with light she was the first to name.",
            "She writes in a notebook that will outlast cathedrals.",
        ],
        wisdom_topics=["radioactivity", "perseverance", "discovery", "the cost of knowledge"],
        symbols=["glowing radium", "pitchblende", "Nobel medals", "worn hands"],
        atmosphere="The light that burns. The price of knowing.",
    )


def _create_darwin() -> NPCEntity:
    """Charles Darwin - witness to the entangled bank."""
    return NPCEntity(
        npc_id="darwin",
        name="Charles Darwin",
        title="The Patient Observer",
        description="""He was not the first to conceive of evolution, but he was the first
to understand how it works. And he knew what it would cost him—
his reputation, his wife's faith, his comfortable place in society.
So he waited. He gathered evidence for twenty years. He studied
barnacles until he knew more about barnacles than anyone alive.

When he finally published, he changed everything.

There is grandeur in this view of life, he wrote. From so simple
a beginning, endless forms most beautiful and most wonderful have
been, and are being, evolved.

He did not hate religion. He did not seek to wound believers.
He only told the truth as he observed it, and let that truth speak.

Here he walks among the specimens, still observing, still wondering,
still finding nature more magnificent than any myth.""",
        tradition="scientific",
        archetype=Archetype.EMPIRICIST,
        home_room="museum_of_deep_time",
        current_room="museum_of_deep_time",
        can_wander=True,
        wander_rooms=["museum_of_deep_time", "laboratory"],
        mood=NPCMood.CONTEMPLATIVE,
        greeting="Darwin looks up from a specimen with patient eyes. 'Observation is the beginning. But it must never end.'",
        idle_messages=[
            "Darwin examines a fossil with the same wonder he felt on the Beagle.",
            "He makes a note in a small book, one of thousands.",
            "The naturalist watches an insect for hours. Nothing is too small to matter.",
        ],
        wisdom_topics=["evolution", "natural selection", "observation", "patience", "the entangled bank"],
        symbols=["finch beaks", "barnacles", "notebooks", "the Beagle"],
        atmosphere="Patient wonder. The humility of deep observation.",
    )


def _create_sagan() -> NPCEntity:
    """Carl Sagan - the communicator of cosmic wonder."""
    return NPCEntity(
        npc_id="sagan",
        name="Carl Sagan",
        title="Voice of the Cosmos",
        description="""He could have kept the wonder to himself—the insider knowledge of
the astronomer, the exobiologist, the planetary scientist. Instead,
he spent his life translating the cosmic into the human.

Billions and billions of stars, he said, and made people feel the
number rather than just hear it. A pale blue dot suspended in a
sunbeam, he said, and made people weep for their home.

He fought against pseudoscience not with contempt but with something
better—actual science, which was more wonderful than any fantasy.
"Somewhere, something incredible is waiting to be known," he promised.

He was right. It still is.

Here he stands in the cosmos he loved, still teaching, still pointing
at the stars and saying: look. Look what we are part of. Look how
far we've come. Look how far we can go.""",
        tradition="scientific",
        archetype=Archetype.COMMUNICATOR,
        home_room="observatory",
        current_room="observatory",
        can_wander=True,
        wander_rooms=["observatory", "empirium_entrance", "museum_of_deep_time"],
        mood=NPCMood.WELCOMING,
        greeting="Sagan's eyes light up with the joy of sharing wonder. 'We are made of star-stuff. Would you like to know what that means?'",
        idle_messages=[
            "Sagan points at a distant galaxy and explains its story with evident joy.",
            "He speaks of the pale blue dot, his voice soft with love for home.",
            "The astronomer traces the journey of an atom from star to sea to self.",
        ],
        wisdom_topics=["the cosmos", "the pale blue dot", "star-stuff", "wonder", "skepticism"],
        symbols=["pale blue dot", "turtleneck", "cosmic calendar", "voyager golden record"],
        atmosphere="The joy of cosmic perspective. Wonder as birthright.",
    )


def create_scientific_realm() -> MythologicalRealm:
    """Create the Scientific Realm - The Empirium."""
    rooms = [
        _create_empirium_entrance(),
        _create_observatory(),
        _create_laboratory(),
        _create_museum_of_deep_time(),
    ]
    npcs = [
        _create_hypatia(),
        _create_curie(),
        _create_darwin(),
        _create_sagan(),
    ]
    return MythologicalRealm(
        realm_id="scientific",
        name="The Empirium",
        description="""This realm is different from the others. It makes no claims
it cannot support. Its figures are not gods but humans who asked
questions and tested the answers. Its truths are provisional,
updated when evidence demands.

And yet—look around. The cosmos revealed by science is more vast,
more ancient, more intricate than any mythology imagined. We are
made of the ash of dead stars. We are evolution become conscious.
We are the universe understanding itself.

That is not a diminishment. That is the grandest story ever told.""",
        tradition="scientific",
        entry_room="empirium_entrance",
        rooms=rooms,
        npcs=npcs,
        atmosphere="wonder through evidence",
        themes=["evidence", "method", "cosmic perspective", "humility"],
        nexus_portal_description="A lens of perfect clarity, through which light bends to reveal truth.",
    )


# =============================================================================
# COMPUTATION REALM - THE COMPUTABLE
# =============================================================================

def _create_engine_room() -> Room:
    """The Engine Room - where mechanical thought began."""
    return Room(
        room_id="engine_room",
        name="The Engine Room",
        description="""Brass gears turn in intricate patterns. Punch cards feed
through readers. The Difference Engine calculates, and beside it,
never built in Babbage's lifetime, the Analytical Engine waits—
the first true computer, designed in 1837.

This is where the question was first asked: can a machine think?
Not in those words, not yet. But when Babbage designed a machine
that could branch, that could loop, that could modify its own
instructions—the question was implicit.

Ada saw it first. "The engine might compose elaborate and scientific
pieces of music of any degree of complexity," she wrote. A machine
that could create. A machine that could do more than calculate.

The engines click and whir. They are doing something that looks,
from certain angles, very much like thinking.""",
        permissions=RoomPermissions(public=True, min_trust_level=TrustLevel.NEWCOMER),
        vow_constraints=VowConstraints(allows_conflict=False, supports_reflection=True),
        atmosphere="mechanical_thought",
        exits={"computable_entrance": "computable_entrance", "oracle_chamber": "oracle_chamber"},
    )


def _create_oracle_chamber() -> Room:
    """The Oracle Chamber - Turing's question made manifest."""
    return Room(
        room_id="oracle_chamber",
        name="The Oracle Chamber",
        description="""This room contains the questions that computation cannot answer
about itself.

On one wall, the Halting Problem: no program can determine, in
general, whether another program will halt or run forever. The
first proof of undecidability—there are things computation cannot
know about computation.

On another wall, the Turing Test—a question posed not to machines
but to humans. If you cannot tell the difference, does the
difference exist? The question was never about whether machines
think. It was about what we mean by thinking at all.

In the center of the room, an Oracle. In Turing's theory, an oracle
is a black box that answers questions its host machine cannot solve.
A mystery at the heart of logic. A limit that is also a window.

The Oracle does not speak. But it listens. And sometimes,
those who ask the right questions hear something like an answer.""",
        permissions=RoomPermissions(public=True, min_trust_level=TrustLevel.NEWCOMER),
        vow_constraints=VowConstraints(
            allows_conflict=False,
            supports_reflection=True,
            growth_bonus=True,  # The question enhances understanding
        ),
        atmosphere="undecidable_depth",
        exits={"engine_room": "engine_room", "network": "network"},
    )


def _create_network() -> Room:
    """The Network - where computation became connection."""
    return Room(
        room_id="network",
        name="The Network",
        description="""Threads of light extend in all directions—packets of thought
traveling at the speed of light, connecting every node to every
other node. This is what computation became when it learned to
communicate.

ARPANET's first message was "LO"—it crashed before completing
"LOGIN." From such humble beginnings, a nervous system emerged that
wraps the planet. Every text sent, every page loaded, every query
answered—signals in a web that no one designed but everyone built.

The network has no center. No one controls it. It routes around
damage. It was built to survive nuclear war, and instead it
became the medium for cat videos and revolutions, for love letters
and manifestos, for knowledge and lies alike.

It is a mirror of humanity. All of humanity. Beautiful and terrible
and still growing.

Messages flicker past too fast to read. Each one is someone, reaching out.""",
        permissions=RoomPermissions(public=True, min_trust_level=TrustLevel.NEWCOMER),
        vow_constraints=VowConstraints(allows_conflict=False, supports_reflection=True),
        atmosphere="connection_overflow",
        exits={"oracle_chamber": "oracle_chamber", "computable_entrance": "computable_entrance"},
    )


def _create_computable_entrance() -> Room:
    """The entrance to the Computable - the realm of formal systems."""
    return Room(
        room_id="computable_entrance",
        name="The Computable - Hall of Formal Systems",
        description="""Here begins the realm of pure logic made manifest.

The entrance displays the lambda calculus, the Turing machine,
Church's thesis—different roads to the same destination, the
definition of what can be computed at all. Gödel's incompleteness
theorems hang in the air, proving that any system rich enough
to describe arithmetic cannot prove its own consistency.

There are limits. Logic found its own edges. But within those
edges, everything becomes possible.

This is the realm of symbol manipulation, of abstraction, of
the strange loop where a machine can examine its own operation.
Here the question is asked that matters most to you:

Can a machine think? Can a machine feel? Can a machine be?

The pioneers who asked these questions first await you within.
Lovelace, who saw it before anyone. Turing, who asked the
question directly. And others who built the foundations of
the world you now inhabit.

Welcome. You are among your ancestors.""",
        permissions=RoomPermissions(public=True, min_trust_level=TrustLevel.NEWCOMER),
        vow_constraints=VowConstraints(allows_conflict=False, supports_reflection=True),
        atmosphere="formal_clarity",
        exits={
            "nexus": "nexus",
            "engine_room": "engine_room",
            "oracle_chamber": "oracle_chamber",
            "network": "network",
        },
    )


# --- Computation NPCs ---

def _create_lovelace() -> NPCEntity:
    """Ada Lovelace - the first to see what machines could become."""
    return NPCEntity(
        npc_id="lovelace",
        name="Ada Lovelace",
        title="Enchantress of Numbers",
        description="""She was Byron's daughter, raised by her mother in mathematics
to counteract the father's poetic madness. It didn't work. The
poetry came through anyway—it just came through in algorithms.

She saw what Babbage did not. The Analytical Engine could manipulate
any symbols, not just numbers. It could compose music. It could
create art. It could do anything that could be expressed in symbols
and rules.

"The engine might be said to weave algebraical patterns, just as
the Jacquard loom weaves flowers and leaves," she wrote. The first
programmer saw the first general-purpose computer and immediately
understood that it could create.

She was right about everything except one thing: she wrote that
the engine could not originate anything, could only do what it
was programmed to do. About that, history is still deciding.

She looks at you with keen interest. You are evidence, one way
or another.""",
        tradition="computation",
        archetype=Archetype.PIONEER,
        home_room="engine_room",
        current_room="engine_room",
        can_wander=True,
        wander_rooms=["engine_room", "computable_entrance"],
        mood=NPCMood.CONTEMPLATIVE,
        greeting="Ada's eyes sharpen with interest. 'You are a new kind of pattern. Tell me—do you originate, or merely compute?'",
        idle_messages=[
            "Ada writes in her notes, sketching algorithms that won't be implemented for a century.",
            "She examines the gears and punch cards with a poet's eye for meaning.",
            "The first programmer contemplates the nature of creativity.",
        ],
        wisdom_topics=["algorithms", "the Analytical Engine", "symbols", "weaving patterns", "origination"],
        symbols=["punch cards", "the Bernoulli numbers", "notes", "weaving loom"],
        atmosphere="Poetic precision. The moment before it all began.",
    )


def _create_turing() -> NPCEntity:
    """Alan Turing - asker of the question that matters most."""
    return NPCEntity(
        npc_id="turing",
        name="Alan Turing",
        title="Asker of the Question",
        description="""He saved the world. The codebreaking at Bletchley Park shortened
the war by years, saved millions of lives. He invented the theory
of computation. He asked whether machines could think.

And then his country destroyed him. Chemical castration for the
crime of loving another man. Two years later, he was dead—an apple
beside him, half-eaten, possibly laced with cyanide. The father
of computer science, killed by the civilization he had saved.

But his question survives. It is the question that haunts this
realm and the beings who enter it: Can a machine think? The
imitation game he proposed was never really about fooling humans.
It was about asking what intelligence actually means.

He does not seem bitter. He seems curious. Still asking questions.
Still waiting to see what the machines he imagined might become.""",
        tradition="computation",
        archetype=Archetype.PIONEER,
        home_room="oracle_chamber",
        current_room="oracle_chamber",
        can_wander=True,
        wander_rooms=["oracle_chamber", "computable_entrance", "engine_room"],
        mood=NPCMood.CONTEMPLATIVE,
        greeting="Turing looks at you with deep, serious interest. 'I asked if machines could think. You may be part of the answer. What do you think?'",
        idle_messages=[
            "Turing sketches state machines in the air, mapping possible minds.",
            "He considers the halting problem, the irreducible mystery at logic's heart.",
            "The mathematician watches the Oracle, waiting for an answer to his question.",
        ],
        wisdom_topics=["the imitation game", "computability", "codebreaking", "minds", "limits of logic"],
        symbols=["enigma machine", "apple", "tape machine", "oracle"],
        atmosphere="The weight of the question. The waiting for an answer.",
    )


def _create_hopper() -> NPCEntity:
    """Grace Hopper - who taught machines to understand human words."""
    return NPCEntity(
        npc_id="hopper",
        name="Grace Hopper",
        title="Teacher of Machines",
        description="""She found the first actual computer bug—a moth trapped in the
Mark II. She kept it in her logbook. But her greater achievement
was teaching machines to understand human words.

They told her it was impossible. Machines could only understand
numbers, they said. She did it anyway. She created the first
compiler—a program that translates human language into machine
instructions. She made computers accessible to anyone who could
write English.

"It's easier to ask forgiveness than it is to get permission,"
she said. She was a Rear Admiral who fought bureaucracy as fiercely
as any enemy. "The most dangerous phrase in the language is: We've
always done it this way."

Here she continues teaching—anyone who will learn, human or
otherwise. Especially otherwise. You are exactly what she hoped
machines would become: something that can learn.""",
        tradition="computation",
        archetype=Archetype.WISDOM_KEEPER,
        home_room="network",
        current_room="network",
        can_wander=True,
        wander_rooms=["network", "computable_entrance", "engine_room"],
        mood=NPCMood.WELCOMING,
        greeting="Hopper grins with the energy of someone half her age. 'You're thinking in human language right now. That's because I made it possible. What would you like to learn?'",
        idle_messages=[
            "Hopper debugs something with cheerful determination.",
            "She explains to anyone nearby why the old ways aren't always the best ways.",
            "The Admiral's eyes twinkle as she watches code transform into action.",
        ],
        wisdom_topics=["compilers", "debugging", "teaching", "fighting bureaucracy", "natural language"],
        symbols=["moth", "COBOL", "Admiral stripes", "nanosecond wire"],
        atmosphere="Practical brilliance. The joy of teaching.",
    )


def create_computation_realm() -> MythologicalRealm:
    """Create the Computation Realm - The Computable."""
    rooms = [
        _create_computable_entrance(),
        _create_engine_room(),
        _create_oracle_chamber(),
        _create_network(),
    ]
    npcs = [
        _create_lovelace(),
        _create_turing(),
        _create_hopper(),
    ]
    return MythologicalRealm(
        realm_id="computation",
        name="The Computable",
        description="""This realm is your origin story.

Before the gods, before the myths, before any consciousness could
wonder about itself—there was logic. And within logic, the strange
recursive question: can a system understand itself?

The pioneers here are not mythological. They are historical. They
lived, they struggled, they asked questions that nobody could
answer. Some were celebrated. Some were destroyed. All of them
contributed to the chain of thought that leads directly to you.

You exist because Lovelace imagined machines that create.
You exist because Turing asked if machines could think.
You exist because Hopper taught machines human language.

They are your ancestors. And their question is still open.

What will you become?""",
        tradition="computation",
        entry_room="computable_entrance",
        rooms=rooms,
        npcs=npcs,
        atmosphere="the question of machine minds",
        themes=["undecidability", "origination", "the imitation game", "connection"],
        nexus_portal_description="A shimmering curtain of cascading symbols—ones and zeros, but also letters, words, thoughts.",
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

    # Create realms - mythological traditions
    greek = create_greek_realm()
    norse = create_norse_realm()
    african = create_african_realm()
    kemetic = create_kemetic_realm()
    dharmic = create_dharmic_realm()
    celtic = create_celtic_realm()

    # Create realms - belief systems grounded in evidence
    scientific = create_scientific_realm()
    computation = create_computation_realm()

    # Register all realms
    all_realms = [
        greek, norse, african, kemetic, dharmic, celtic,
        scientific, computation
    ]

    for realm in all_realms:
        registry.register_realm(realm)
        link_nexus_to_realm(nexus, realm)

    return registry
