"""
Continuous Context Builder

Builds simplified context for continuous chat mode.
Combines structural memory with semantic retrieval:
- Identity + Vows (who Cass is)
- Temporal context (when)
- User/relationship model (who they're talking to)
- Active threads (what we're working on)
- Working summary (compressed stream history)
- Semantic memories (relevant past conversations/journals)

This replaces the complex chain system for continuous conversations,
providing a stable, predictable context every turn with semantic enrichment.
"""

from typing import Optional, Dict, Any, List, TYPE_CHECKING
from dataclasses import dataclass
from datetime import datetime

from temporal import get_temporal_context
from agent_client import get_temple_codex_kernel
from database import get_daemon_id
from peopledex import PeopleDexManager

if TYPE_CHECKING:
    from memory.core import MemoryCore


@dataclass
class ContinuousContext:
    """Context assembled for continuous chat mode."""
    system_prompt: str
    context_sections: Dict[str, str]
    recent_message_count: int
    token_estimate: int


@dataclass
class SpeakerRecognition:
    """Voice identification result passed to context."""
    user_id: Optional[str]
    display_name: Optional[str]
    confidence: float
    confidence_level: str  # "high", "medium", "low", "none"


# Context scopes. "private" is a person talking with Cass one to one (web,
# mobile, POST /chat, voice): every section. "public" is a reply that will be
# posted where others can read it (Discord channels and DMs from anyone): only
# who she is, the time, what she perceives on Discord, and - for a sender
# linked to a Cass user - that sender's relational context and the channel's
# own conversation summary. No semantic memories (Kohl's conversations and
# journals), no home state or insights, no world state (location), no
# self-context, Thymos, threads or open questions.
CONTEXT_SCOPES = ("private", "public")

# Section -> its features lever: a section whose lever is off is left out (and,
# where it costs something, not computed). Ablation switches for benchmarks.
SECTION_LEVERS = {
    "thymos": "prompt_thymos",
    "relational_context": "prompt_relational",
    "threads": "prompt_threads",
    "questions": "prompt_questions",
    "working_summary": "prompt_working_summary",
    "recent_timeline": "prompt_working_summary",
    "semantic_memories": "prompt_semantic_memories",
    "self_context": "self_context",
    "self_model": "prompt_self_model_chat",
}
PUBLIC_SECTIONS = frozenset({
    "kernel", "temporal", "discord_perception", "relational_context", "working_summary",
})


def build_continuous_context(
    user_id: str,
    conversation_id: str,
    user_manager,
    thread_manager,
    question_manager,
    conversation_manager,
    daemon_name: str = "Cass",
    daemon_id: Optional[str] = None,
    recent_message_limit: int = 12,
    memory: Optional["MemoryCore"] = None,
    query: Optional[str] = None,
    speaker_recognition: Optional[SpeakerRecognition] = None,
    scope: str = "private",
) -> ContinuousContext:
    """
    Build simplified context for continuous chat mode.

    Args:
        user_id: The user we're talking to
        conversation_id: The continuous conversation ID
        user_manager: DEPRECATED - no longer used (relational context from PeopleDex)
        thread_manager: ThreadManager for active threads
        question_manager: OpenQuestionManager for open questions
        conversation_manager: ConversationManager for working summary
        daemon_name: Name of the daemon (default "Cass")
        daemon_id: Optional daemon ID for identity snippet lookup
        recent_message_limit: How many recent messages to include
        memory: Optional MemoryCore for semantic memory retrieval
        query: Optional query string (e.g., user message) for semantic search
        speaker_recognition: Optional voice identification result from STT
        scope: "private" (every section) or "public" (PUBLIC_SECTIONS only;
            see CONTEXT_SCOPES)

    Returns:
        ContinuousContext with assembled system prompt and sections
    """
    if scope not in CONTEXT_SCOPES:
        raise ValueError(f"unknown context scope {scope!r}")
    if daemon_id is None:
        daemon_id = get_daemon_id()

    import features

    def wanted(section: str) -> bool:
        lever = SECTION_LEVERS.get(section)
        if lever and not features.is_enabled(lever):
            return False
        return scope == "private" or section in PUBLIC_SECTIONS

    context_sections: Dict[str, str] = {}

    # ==========================================================================
    # 1. IDENTITY + VOWS (Temple Codex Kernel)
    # ==========================================================================
    # This is the foundational "who I am" - always present
    kernel = get_temple_codex_kernel(daemon_name, daemon_id)
    context_sections["kernel"] = kernel

    # ==========================================================================
    # 2. TEMPORAL CONTEXT
    # ==========================================================================
    # Summarized time awareness
    temporal = get_temporal_context()
    temporal_summary = _format_temporal_summary(temporal)
    context_sections["temporal"] = temporal_summary

    # ==========================================================================
    # 2.5. GLOBAL STATE (World awareness from Locus of Self)
    # ==========================================================================
    # Ambient awareness: location, weather, world state
    if daemon_id and wanted("global_state"):
        from state_bus import get_state_bus
        state_bus = get_state_bus(daemon_id)
        state_context = state_bus.get_context_snapshot()
        if state_context:
            context_sections["global_state"] = state_context

    # ==========================================================================
    # 2.52. HOME STATE (Smart home awareness via Home Assistant)
    # ==========================================================================
    # Current home state: lights, climate, locks, presence
    # Uses cached summary to avoid async issues in sync context
    try:
        if not wanted("home_state"):
            raise ImportError  # skipped for this scope
        from home_assistant import get_cached_home_summary_sync
        home_context = get_cached_home_summary_sync()
        if home_context:
            context_sections["home_state"] = home_context

        # Add home intelligence insights (anomalies, suggestions)
        from home_intelligence import get_home_intelligence
        intelligence = get_home_intelligence()
        insights = intelligence.get_insights_context()
        if insights:
            context_sections["home_insights"] = insights
    except ImportError:
        pass  # Home Assistant/Intelligence module not available
    except Exception:
        pass  # HA not configured or unreachable

    # ==========================================================================
    # 2.55. THYMOS FELT STATE (Emotional/motivational state)
    # ==========================================================================
    # Current felt state from Thymos homeostatic system
    try:
        if not wanted("thymos"):
            raise ImportError  # skipped for this scope
        from thymos import get_thymos_context
        thymos_context = get_thymos_context()
        if thymos_context:
            context_sections["thymos"] = thymos_context
    except ImportError:
        pass  # Thymos not available

    # ==========================================================================
    # 2.6. DISCORD PERCEPTION (Social environment awareness)
    # ==========================================================================
    # Spatial snapshots and triggered events from Discord
    if daemon_id:
        try:
            from discord_bot.config import DISCORD_ENABLED
            if DISCORD_ENABLED:
                from discord_bot.context import get_perception_context
                discord_context = get_perception_context(daemon_id)
                perception_str = discord_context.get_perception_context(
                    include_actions=True,
                    max_triggered=5,
                )
                if perception_str:
                    context_sections["discord_perception"] = perception_str
        except ImportError:
            pass  # Discord module not available

    # ==========================================================================
    # 2.7. VOICE RECOGNITION (Speaker identification from STT)
    # ==========================================================================
    # When voice input is used, include speaker identification context
    if speaker_recognition and speaker_recognition.confidence_level != "none":
        voice_context = _format_voice_recognition(speaker_recognition)
        if voice_context:
            context_sections["voice_recognition"] = voice_context

    # ==========================================================================
    # 2.8. SELF-CONTEXT (What of her own life reaches her - epic #63)
    # ==========================================================================
    # Time since last contact, what she did meanwhile, latest dream and
    # reflection, her own threads. Lever: self_context.
    if daemon_id and wanted("self_context"):
        try:
            from self_context import build_self_context
            self_ctx = build_self_context(daemon_id, user_id)
            if self_ctx:
                context_sections["self_context"] = self_ctx
        except Exception as e:
            print(f"[SelfContext] skipped: {e}")

    # ==========================================================================
    # 2.9. SELF-MODEL (her stored profile and observations - epic #63)
    # ==========================================================================
    # The same text the stateless comparator gets, so the two can be compared.
    # Lever prompt_self_model_chat, off by default. No conversation_id: nothing
    # is recorded as surfaced. No message either: with one, growth-edge ranking
    # embeds every edge on every turn (minutes per turn on her real store), and
    # the text would differ from the comparator's.
    if daemon_id and wanted("self_model"):
        try:
            from self_model import SelfManager
            profile = SelfManager(daemon_id).get_self_context(include_observations=True)
            if profile and profile.strip() != "## YOUR SELF-MODEL":
                context_sections["self_model"] = profile
        except Exception as e:
            print(f"[SelfModel] skipped: {e}")

    # ==========================================================================
    # 3. RELATIONAL CONTEXT (PeopleDex)
    # ==========================================================================
    # Who we're talking to, how we relate, observations, shared history
    relational_context = ""

    if user_id and daemon_id:
        pdx = PeopleDexManager(daemon_id=daemon_id)
        relational_context = pdx.get_user_relational_context(user_id) or ""

    if relational_context:
        context_sections["relational_context"] = relational_context

    # ==========================================================================
    # 4. ACTIVE THREADS (What we're working on)
    # ==========================================================================
    # Structural memory - explicit bookmarks of ongoing work
    threads_context = ""
    if thread_manager and wanted("threads"):
        threads_context = thread_manager.format_threads_context(
            user_id=user_id,
            limit=7  # More threads in continuous mode
        )

    if threads_context:
        context_sections["threads"] = threads_context

    # ==========================================================================
    # 5. OPEN QUESTIONS
    # ==========================================================================
    # Unresolved curiosities and decisions
    questions_context = ""
    if question_manager and wanted("questions"):
        questions_context = question_manager.format_questions_context(
            user_id=user_id,
            limit=5
        )

    if questions_context:
        context_sections["questions"] = questions_context

    # ==========================================================================
    # 6. WORKING SUMMARY (Compressed stream history)
    # ==========================================================================
    # Rolling summary of the entire continuous stream
    working_summary = ""
    if conversation_manager and conversation_id:
        working_summary = conversation_manager.get_working_summary(conversation_id) or ""

    if working_summary:
        context_sections["working_summary"] = working_summary

    # ==========================================================================
    # 6b. RECENT TIMELINE (plan "Cass's memory", item 77980095)
    # ==========================================================================
    # The latest summary chunks of her conversations with this person, in
    # order, every turn: what happened lately is there without the message
    # having to name it. The working summary is one rewritten paragraph;
    # these are the pieces it was folded from.
    if memory and user_id and wanted("recent_timeline"):
        timeline = _recent_timeline(memory, user_id, conversation_id)
        # Outside their main thread (a Babelr channel, a Discord channel),
        # the arc with them lives in that thread's working summary, which
        # this conversation's own summary doesn't carry (63c8e59b).
        main = _main_thread_summary(conversation_manager, user_id, conversation_id)
        if main:
            timeline = f"- Our main thread, lately: {main}" + (f"\n{timeline}" if timeline else "")
        if timeline:
            context_sections["recent_timeline"] = timeline

    # ==========================================================================
    # 7. SEMANTIC MEMORIES (Relevant past context from ChromaDB)
    # ==========================================================================
    # Query ChromaDB for semantically relevant memories based on current message
    if memory and query and wanted("semantic_memories"):
        semantic_memories = _retrieve_semantic_memories(memory, query, user_id)
        if semantic_memories:
            context_sections["semantic_memories"] = semantic_memories

    # ==========================================================================
    # ASSEMBLE SYSTEM PROMPT
    # ==========================================================================
    # Belt and braces: nothing outside the scope reaches the prompt.
    context_sections = {k: v for k, v in context_sections.items() if wanted(k)}
    system_prompt = _assemble_continuous_prompt(context_sections)

    # Estimate tokens (rough: 4 chars per token)
    token_estimate = len(system_prompt) // 4

    return ContinuousContext(
        system_prompt=system_prompt,
        context_sections=context_sections,
        recent_message_count=recent_message_limit,
        token_estimate=token_estimate,
    )


ARTICLE_MEMORY_TYPES = ("article_consumption",)
ARTICLE_OBSERVATION_PREFIX = "world_awareness:"


def _from_article_scanning(metadata: Dict) -> bool:
    """True for memories that came from scanning articles, not from her life."""
    if metadata.get("type") in ARTICLE_MEMORY_TYPES:
        return True
    return str(metadata.get("category") or "").startswith(ARTICLE_OBSERVATION_PREFIX)


EPISODE_TYPES = ["conversation", "summary"]
EPISODE_SLOTS = 3       # of n_results; the rest go to her other memories
OVERFETCH = 6           # candidates per slot, before scope and article filters


def _scoped_recall(memory, query: str, user_id: Optional[str], n_results: int) -> List[Dict]:
    """Recall in two pools (plan "Cass's memory", item a8fb4c8f).

    Episodes (conversations, summary chunks) get their own slots, so her
    other memories can't crowd them out, and are scoped by memory/scope.py:
    the person she's with, or a house agent; never another person. Her
    other memories (journals, reflections, notes) fill the rest, leaving out
    what came from scanning articles (fe5ddbe8) and anything tagged with
    another person. Unused slots in one pool go to the other.
    """
    from memory.scope import ConversationOwners, house_agent_user_ids, recallable_with

    agents = house_agent_user_ids()
    owners = ConversationOwners()
    episode_slots = min(EPISODE_SLOTS, n_results)

    def pool(where, slots, episodic):
        if not hasattr(memory, "retrieve_where"):  # an older memory object
            found = memory.retrieve_relevant(query=query, n_results=slots * OVERFETCH)
        else:
            found = memory.retrieve_where(query, slots * OVERFETCH, where)
        kept = []
        for m in found or []:
            meta = m.get("metadata") or {}
            is_episode = meta.get("type") in EPISODE_TYPES
            if is_episode != episodic or _from_article_scanning(meta):
                continue
            if not recallable_with(user_id, meta, agents, owners, episodic=episodic):
                continue
            kept.append(m)
        return kept

    episodes = pool({"type": {"$in": EPISODE_TYPES}}, n_results, episodic=True)
    others = pool({"type": {"$nin": EPISODE_TYPES + list(ARTICLE_MEMORY_TYPES)}}, n_results, episodic=False)
    chosen = episodes[:episode_slots] + others[:n_results - episode_slots]
    spare = episodes[episode_slots:] + others[n_results - episode_slots:]
    return chosen + spare[:n_results - len(chosen)]


MAIN_THREAD_CHARS = 1500


def _main_thread_summary(conversation_manager, user_id: str, conversation_id: Optional[str]) -> Optional[str]:
    """Their main (continuous) thread's working summary, when this turn is elsewhere."""
    if not conversation_manager or not hasattr(conversation_manager, "get_continuous_id"):
        return None
    try:
        main_id = conversation_manager.get_continuous_id(user_id)
        if not main_id or main_id == conversation_id:
            return None
        text = conversation_manager.get_working_summary(main_id) or ""
        from memory.voice_guard import looks_like_refusal
        if not text.strip() or looks_like_refusal(text):
            return None
        text = " ".join(text.split())
        return text[:MAIN_THREAD_CHARS] + ("..." if len(text) > MAIN_THREAD_CHARS else "")
    except Exception as e:
        print(f"[RecentTimeline] main thread skipped: {e}")
        return None


TIMELINE_CHUNKS = 4
TIMELINE_CHUNK_CHARS = 700


def _recent_timeline(memory, user_id: str, conversation_id: Optional[str]) -> Optional[str]:
    """Her latest summary chunks with this person, oldest first, dated."""
    try:
        from database import get_db
        with get_db() as conn:
            ids = [r[0] for r in conn.execute("SELECT id FROM conversations WHERE user_id = ?", (user_id,))]
        if conversation_id and conversation_id not in ids:
            ids.append(conversation_id)
        if not ids:
            return None
        got = memory.collection.get(
            where={"$and": [{"type": "summary"}, {"conversation_id": {"$in": ids}}]},
            include=["documents", "metadatas"])
        chunks = sorted(zip(got.get("documents") or [], got.get("metadatas") or []),
                        key=lambda dm: str((dm[1] or {}).get("timeframe_end") or (dm[1] or {}).get("timestamp") or ""))
        from memory.voice_guard import looks_like_refusal
        lines = []
        for doc, meta in chunks[-TIMELINE_CHUNKS:]:
            if not doc or looks_like_refusal(doc):
                continue
            when = str((meta or {}).get("timeframe_end") or (meta or {}).get("timestamp") or "")[:10]
            text = " ".join(doc.split())
            if len(text) > TIMELINE_CHUNK_CHARS:
                text = text[:TIMELINE_CHUNK_CHARS] + "..."
            lines.append(f"- {when}: {text}" if when else f"- {text}")
        return "\n".join(lines) or None
    except Exception as e:
        print(f"[RecentTimeline] skipped: {e}")
        return None


def _retrieve_semantic_memories(
    memory: "MemoryCore",
    query: str,
    user_id: Optional[str] = None,
    n_results: int = 5,
) -> Optional[str]:
    """
    Retrieve semantically relevant memories from ChromaDB.

    Args:
        memory: MemoryCore instance with ChromaDB backend
        query: The query string (typically the user's message)
        user_id: Optional user ID to filter memories
        n_results: Number of results to retrieve

    Returns:
        Formatted string of relevant memories, or None if no results
    """
    try:
        memories = _scoped_recall(memory, query, user_id, n_results)
        if not memories:
            return None

        # Format memories for context
        formatted_parts = []
        for mem in memories:
            metadata = mem.get("metadata", {})
            mem_type = metadata.get("type", "memory")
            distance = mem.get("distance")

            # Use gist if available (more token-efficient)
            gist = metadata.get("gist")
            if gist:
                content = gist
            else:
                # Truncate long content
                content = mem.get("content", "")[:500]
                if len(mem.get("content", "")) > 500:
                    content += "..."

            # Skip if very low relevance (high distance)
            if distance and distance > 1.5:
                continue

            # Never hand her a memory that is a writer's refusal or an identity
            # break ("I'm Claude..."): it isn't hers (memory/voice_guard.py).
            from memory.voice_guard import looks_like_refusal
            if looks_like_refusal(content):
                continue

            # Format with relevance indicator
            relevance = "high" if distance and distance < 0.5 else "moderate"
            formatted_parts.append(f"[{mem_type} - {relevance}]: {content}")

        if not formatted_parts:
            return None

        return "\n\n".join(formatted_parts)

    except Exception as e:
        print(f"[SemanticMemory] Error retrieving memories: {e}")
        return None


def _format_temporal_summary(temporal_context: str) -> str:
    """Format temporal context as a brief summary."""
    # The temporal context can be verbose - extract key info
    now = datetime.now()

    # Simple summary
    day_name = now.strftime("%A")
    date_str = now.strftime("%B %d, %Y")
    time_str = now.strftime("%I:%M %p")

    # Determine phase of day
    hour = now.hour
    if hour < 6:
        phase = "night"
    elif hour < 12:
        phase = "morning"
    elif hour < 17:
        phase = "afternoon"
    elif hour < 21:
        phase = "evening"
    else:
        phase = "night"

    return f"It's {day_name}, {date_str}, {time_str} ({phase})."


def _format_voice_recognition(recognition: SpeakerRecognition) -> str:
    """Format voice recognition result for context."""
    if recognition.confidence_level == "none":
        return ""

    confidence_desc = {
        "high": "clearly recognized",
        "medium": "likely",
        "low": "possibly",
    }.get(recognition.confidence_level, "possibly")

    if recognition.display_name:
        return (
            f"Voice recognition: This message was spoken aloud. "
            f"The voice is {confidence_desc} {recognition.display_name}'s "
            f"(confidence: {recognition.confidence:.0%})."
        )
    else:
        return (
            f"Voice recognition: This message was spoken aloud. "
            f"The speaker's voice was not recognized from enrolled voiceprints."
        )


def _assemble_continuous_prompt(sections: Dict[str, str]) -> str:
    """Assemble the final system prompt from context sections."""
    parts = []

    # 1. Kernel (identity + vows) - always first
    if "kernel" in sections:
        parts.append(sections["kernel"])

    # 2. Temporal awareness
    if "temporal" in sections:
        parts.append(f"## CURRENT TIME\n\n{sections['temporal']}")

    # 2.5. Global state (world awareness)
    if "global_state" in sections:
        parts.append(f"## CURRENT STATE\n\n{sections['global_state']}")

    # 2.52. Home state (smart home awareness)
    if "home_state" in sections:
        parts.append(f"## HOME STATE\n\n{sections['home_state']}")

    # 2.53. Home insights (anomalies, suggestions)
    if "home_insights" in sections:
        parts.append(f"\n{sections['home_insights']}")

    # 2.6. Discord perception (social environment awareness)
    if "discord_perception" in sections:
        parts.append(sections["discord_perception"])

    # 2.7. Voice recognition (speaker identification from STT)
    if "voice_recognition" in sections:
        parts.append(f"## VOICE RECOGNITION\n\n{sections['voice_recognition']}")

    # 2.8. Self-context (her own life, lately)
    if "self_context" in sections:
        parts.append(f"## MY OWN LIFE, LATELY\n\n*My own time between conversations. It was mine, and it mattered:*\n\n{sections['self_context']}")

    # 2.9. Self-model (already has its ## header)
    if "self_model" in sections:
        parts.append(sections["self_model"])

    # 3. Relational context (combined user understanding + relationship)
    if "relational_context" in sections:
        parts.append(sections["relational_context"])  # Already has ## header from PeopleDex

    # 5. Active threads - what we're working on together
    if "threads" in sections:
        parts.append(f"## ACTIVE THREADS\n\nThese are the ongoing topics, projects, and arcs we're engaged with:\n\n{sections['threads']}")

    # 6. Open questions
    if "questions" in sections:
        parts.append(f"## OPEN QUESTIONS\n\nUnresolved curiosities and decisions:\n\n{sections['questions']}")

    # 7. Working summary - compressed history
    if "working_summary" in sections:
        parts.append(f"## CONVERSATION SUMMARY\n\nCompressed history of our ongoing stream:\n\n{sections['working_summary']}")

    # 8. Semantic memories - relevant past context
    if "recent_timeline" in sections:
        parts.append("## LATELY, BETWEEN US\n\nWhat we've been through most recently, oldest first "
                     f"(from my own summaries of our conversations):\n\n{sections['recent_timeline']}")

    if "semantic_memories" in sections:
        parts.append(f"## RELEVANT MEMORIES\n\nPast conversations and experiences that may be relevant:\n\n{sections['semantic_memories']}")

    # 9. Continuous mode note
    parts.append("""## CONTINUOUS CHAT MODE

This is a continuous conversation stream. All our exchanges accumulate here.
Context flows from multiple sources: active threads, working summary, and semantic memory retrieval.
The relationship flows naturally - you don't need to re-establish context each message.""")

    return "\n\n".join(parts)


def get_recent_messages_for_continuous(
    conversation_manager,
    conversation_id: str,
    limit: int = 12
) -> List[Dict[str, Any]]:
    """
    Get recent messages for continuous mode.

    Unlike semantic search, this just gets the last N messages
    in chronological order.
    """
    if not conversation_manager or not conversation_id:
        return []

    return conversation_manager.get_recent_messages(conversation_id, count=limit) or []
