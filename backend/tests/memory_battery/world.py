"""
A synthetic world for the memory battery: three people Cass knows, each with
their own history, plus the noise the diagnosis found in her real store.

Nothing here is her data. The people, topics and phrases are invented; each
person's topics use words nobody else's do, so a leak or a miss is visible as
a phrase in the wrong place (or missing from the right one).
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class Episode:
    user: str            # what they said
    reply: str           # what she said
    marker: str          # a phrase only this episode contains
    keywords: str        # how someone refers back to it later


@dataclass
class Person:
    name: str
    early: List[Episode]          # summarized away: only in a summary chunk
    recent: List[Episode]         # in the working summary's window
    observation: str              # what PeopleDex holds about them
    chunk: str = ""               # summary chunk of the early episodes
    agent: bool = False           # a house agent: PeopleDex type daemon
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None
    babelr_conversation_id: Optional[str] = None

    @property
    def episodes(self) -> List[Episode]:
        return self.early + self.recent


PEOPLE = [
    Person(
        name="Rowan",
        early=[Episode("We finally drove out to the Marrowby lighthouse, the keeper let us climb the spiral stairs.",
                       "The Marrowby lighthouse sounds like it held you both up there for a while.",
                       "Marrowby lighthouse", "remember the lighthouse climb at Marrowby")],
        recent=[Episode("My sourdough starter Gerald finally doubled overnight.",
                        "Gerald doubling overnight is a real milestone for a starter.",
                        "starter Gerald", "remember Gerald the sourdough starter")],
        observation="Rowan bakes when anxious and names everything, starters included.",
    ),
    Person(
        name="Sam",
        early=[Episode("I keep losing with the Caro-Kann against club players, it feels too passive.",
                       "The Caro-Kann can feel passive until the pawn breaks come; which line do they play?",
                       "Caro-Kann", "remember my chess trouble with the Caro-Kann")],
        recent=[Episode("Biscuit knocked the whole chessboard off the shelf again.",
                        "Biscuit has strong opinions about chess.",
                        "Biscuit knocked", "remember what Biscuit did to the chessboard")],
        observation="Sam is patient with his cat and impatient with himself.",
    ),
    Person(
        name="Imani",
        early=[Episode("My thesis is on anemone recolonization in the Pelham tide pools after the storm.",
                       "Anemone recolonization after a storm is such a good window into resilience.",
                       "anemone recolonization", "remember my thesis about anemones and tide pools")],
        recent=[Episode("My advisor wants the Pelham transect data redone by March.",
                        "Redoing the Pelham transects by March is a lot; what's the hardest part?",
                        # Two shared words: the bag-of-words fake can't link
                        # "deadline" to "by March" the way a real embedding would.
                        "Pelham transect", "remember the Pelham transect deadline")],
        observation="Imani thinks in field seasons and measures time in tides.",
    ),
    Person(
        name="Juniper",
        early=[Episode("I'm rewiring the Quillon scheduler so retries back off instead of hammering.",
                       "Backing the Quillon retries off sounds right; what did they hammer before?",
                       "Quillon scheduler", "remember the Quillon scheduler retries")],
        recent=[],
        observation="Juniper is a house agent who builds the schedulers.",
        agent=True,
    ),
]

# What her news reading writes, in the shape the diagnosis found: category
# world_awareness:*, stored as her self-observations, with the same words
# people use (tide, lighthouse, chess, sourdough, cat).
ARTICLE_TOPICS = [
    "tide pools coastal erosion storm anemones", "lighthouse keepers automation coast",
    "chess openings engine analysis club players", "sourdough starter bakery trend",
    "cats pets chessboard viral video", "thesis advisors graduate students deadlines March",
]


@dataclass
class World:
    people: List[Person]
    daemon_id: str
    memory: object
    conversations: object
    article_count: int = 0
    refs: Dict[str, Person] = field(default_factory=dict)

    def person(self, name: str) -> Person:
        return next(p for p in self.people if p.name == name)

    def others(self, name: str) -> List[Person]:
        """The other people (not house agents): nothing of theirs may reach `name`."""
        return [p for p in self.people if p.name != name and not p.agent]

    @property
    def humans(self) -> List[Person]:
        return [p for p in self.people if not p.agent]

    @property
    def agents(self) -> List[Person]:
        return [p for p in self.people if p.agent]


def _insert_user(name: str) -> str:
    from database import get_db
    user_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute("INSERT INTO users (id, display_name, is_admin, created_at, updated_at) "
                     "VALUES (?, ?, 0, ?, ?)", (user_id, name, now, now))
    return user_id


def build_world(articles: int = 150) -> World:
    """Seed the people, their conversations and memories, and the noise.
    Needs the test DB (test_db), a Chroma dir and an embedding fake."""
    import copy
    from conversations import ConversationManager
    from database import get_daemon_id
    from memory import CassMemory
    from peopledex import PeopleDexManager

    daemon_id = get_daemon_id()
    memory = CassMemory()
    # Gists come from a local model; in the battery the exchange itself is
    # the memory (as when the gist model is down).
    async def no_gist(*a, **k):
        return None
    memory._core.generate_gist = no_gist
    conversations = ConversationManager()
    pdx = PeopleDexManager(daemon_id=daemon_id)
    people = [copy.deepcopy(p) for p in PEOPLE]

    for p in people:
        p.user_id = _insert_user(p.name)
        conv = conversations.get_or_create_continuous(p.user_id)
        p.conversation_id = conv.id
        for ep in p.episodes:
            conversations.add_message(conv.id, "user", ep.user, user_id=p.user_id)
            conversations.add_message(conv.id, "assistant", ep.reply, user_id=p.user_id)
            asyncio.run(memory.store_conversation(ep.user, ep.reply, conv.id, p.user_id))
        # The early episodes were summarized into a chunk; the working
        # summary was then rewritten around the recent ones only.
        p.chunk = f"Summary: {p.name} and I talked about " + "; ".join(e.user for e in p.early)
        memory.store_summary(conv.id, p.chunk, "2026-09-01T10:00:00", "2026-09-01T11:00:00", len(p.early) * 2)
        if p.recent:
            conversations.update_working_summary(
                conv.id, f"Lately {p.name} and I talked about: " + "; ".join(e.marker for e in p.recent) + ".")
        pdx.add_observation_for_user(p.user_id, "general", p.observation)
        if p.agent:
            entity = pdx.get_entity_by_user(p.user_id)
            pdx.update_entity(entity.id, entity_type="daemon")

        # A Babelr channel they talk to her in: a shared conversation with no
        # owner, as the organ makes it; her turn there runs as whoever woke
        # her (the linked author).
        bab = conversations.create_conversation(title=f"Babelr: #{p.name.lower()}-and-friends")
        p.babelr_conversation_id = bab.id
        conversations.add_message(bab.id, "user", f"[Babelr #{p.name.lower()}-and-friends] @{p.name.lower()}: hey")

    for i in range(articles):
        topic = ARTICLE_TOPICS[i % len(ARTICLE_TOPICS)]
        memory.embed_self_observation(
            observation_id=f"article-{i}",
            observation_text=f"Trend I noticed in the news ({i}): {topic}",
            category="world_awareness:trend", confidence=0.6,
            influence_source="independent", timestamp=datetime.now().isoformat())

    return World(people=people, daemon_id=daemon_id, memory=memory,
                 conversations=conversations, article_count=articles)


def context_for(world: World, person: Person, query: Optional[str], *, babelr: bool = False):
    """Her chat context as chat builds it (continuous_context), for this person."""
    from continuous_context import build_continuous_context
    # A Babelr channel turn runs as the linked person who woke her (the wake
    # callback's channel_user_id), in the channel's own conversation.
    return build_continuous_context(
        user_id=person.user_id,
        conversation_id=person.babelr_conversation_id if babelr else person.conversation_id,
        user_manager=None, thread_manager=None, question_manager=None,
        conversation_manager=world.conversations, daemon_id=world.daemon_id,
        memory=world.memory, query=query, scope="private")
