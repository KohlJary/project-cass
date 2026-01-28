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

if TYPE_CHECKING:
    from memory.core import MemoryCore


@dataclass
class ContinuousContext:
    """Context assembled for continuous chat mode."""
    system_prompt: str
    context_sections: Dict[str, str]
    recent_message_count: int
    token_estimate: int


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
) -> ContinuousContext:
    """
    Build simplified context for continuous chat mode.

    Args:
        user_id: The user we're talking to
        conversation_id: The continuous conversation ID
        user_manager: UserManager instance for user/relationship context
        thread_manager: ThreadManager for active threads
        question_manager: OpenQuestionManager for open questions
        conversation_manager: ConversationManager for working summary
        daemon_name: Name of the daemon (default "Cass")
        daemon_id: Optional daemon ID for identity snippet lookup
        recent_message_limit: How many recent messages to include
        memory: Optional MemoryCore for semantic memory retrieval
        query: Optional query string (e.g., user message) for semantic search

    Returns:
        ContinuousContext with assembled system prompt and sections
    """
    if daemon_id is None:
        daemon_id = get_daemon_id()

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
    if daemon_id:
        from state_bus import get_state_bus
        state_bus = get_state_bus(daemon_id)
        state_context = state_bus.get_context_snapshot()
        if state_context:
            context_sections["global_state"] = state_context


    # ==========================================================================
    # 3. USER & RELATIONSHIP MODEL
    # ==========================================================================
    # Who we're talking to and how we relate
    user_context = ""
    relationship_context = ""

    if user_manager and user_id:
        user_context = user_manager.get_rich_user_context(user_id) or ""
        relationship_context = user_manager.get_relationship_context(user_id) or ""

    if user_context:
        context_sections["user_model"] = user_context
    if relationship_context:
        context_sections["relationship"] = relationship_context

    # ==========================================================================
    # 4. ACTIVE THREADS (What we're working on)
    # ==========================================================================
    # Structural memory - explicit bookmarks of ongoing work
    threads_context = ""
    if thread_manager:
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
    if question_manager:
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
    # 7. SEMANTIC MEMORIES (Relevant past context from ChromaDB)
    # ==========================================================================
    # Query ChromaDB for semantically relevant memories based on current message
    if memory and query:
        semantic_memories = _retrieve_semantic_memories(memory, query, user_id)
        if semantic_memories:
            context_sections["semantic_memories"] = semantic_memories

    # ==========================================================================
    # ASSEMBLE SYSTEM PROMPT
    # ==========================================================================
    system_prompt = _assemble_continuous_prompt(context_sections)

    # Estimate tokens (rough: 4 chars per token)
    token_estimate = len(system_prompt) // 4

    return ContinuousContext(
        system_prompt=system_prompt,
        context_sections=context_sections,
        recent_message_count=recent_message_limit,
        token_estimate=token_estimate,
    )


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
        # Retrieve semantically similar memories
        memories = memory.retrieve_relevant(
            query=query,
            n_results=n_results,
            filter_type=None  # Get all types (conversations, journals, etc.)
        )

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


    # 3. User understanding
    if "user_model" in sections:
        parts.append(f"## WHO YOU'RE TALKING TO\n\n{sections['user_model']}")

    # 4. Relationship context
    if "relationship" in sections:
        parts.append(f"## OUR RELATIONSHIP\n\n{sections['relationship']}")

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
