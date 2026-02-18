"""
Chat Context - Unified context assembly for chat requests.

This module consolidates the context building logic that was duplicated
between main_sdk.py and websocket_handlers.py. It provides:

1. ChatContext - A dataclass holding all assembled context
2. ContextAssembler - Builds ChatContext from various sources

The goal is to have ONE place where context is assembled, not two parallel
implementations that can drift apart.

Slays: websocket-hydra, main-sdk-minotaur (partial)
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from memory.core import MemoryCore
    from conversations import ConversationManager
    from users import UserManager
    from self_model import SelfManager
    from self_model_graph import SelfModelGraph
    from goal_planner import GoalManager
    from memory import ThreadManager, OpenQuestionManager


@dataclass
class ChatContext:
    """
    All context needed for an LLM chat request.

    This replaces the 15+ parameter explosion in send_message().
    Instead of passing 15 optional strings, pass one ChatContext.
    """
    # Core identifiers
    user_id: str
    conversation_id: str
    daemon_id: Optional[str] = None
    project_id: Optional[str] = None

    # The assembled system prompt (for continuous mode, this is pre-built)
    system_prompt: Optional[str] = None

    # Legacy context components (for non-continuous mode)
    memory_context: str = ""
    user_context: Optional[str] = None
    user_model_context: Optional[str] = None
    relationship_context: Optional[str] = None
    threads_context: Optional[str] = None
    questions_context: Optional[str] = None
    global_state_context: Optional[str] = None
    intro_guidance: Optional[str] = None

    # Recent messages for conversation continuity
    recent_messages: List[Dict[str, Any]] = field(default_factory=list)

    # Metadata for diagnostics
    context_sizes: Dict[str, int] = field(default_factory=dict)
    is_continuous: bool = False
    unsummarized_count: int = 0

    # Counts for status messages
    thread_count: int = 0
    question_count: int = 0
    tool_count: int = 0
    wiki_pages_count: int = 0
    pattern_count: int = 0

    def get_memory_summary(self) -> Dict[str, Any]:
        """Get summary dict for 'thinking' status messages."""
        return {
            "has_context": bool(self.memory_context or self.system_prompt),
            "thread_count": self.thread_count,
            "question_count": self.question_count,
            "tool_count": self.tool_count,
            "wiki_pages_count": self.wiki_pages_count,
            "pattern_count": self.pattern_count,
            "context_sizes": self.context_sizes,
            "is_continuous": self.is_continuous,
        }


class ContextAssembler:
    """
    Assembles ChatContext from various managers and sources.

    This class encapsulates the ~200 lines of context building logic
    that was duplicated between main_sdk.py and websocket_handlers.py.

    Usage:
        assembler = ContextAssembler(
            memory=memory,
            conversation_manager=conversation_manager,
            user_manager=user_manager,
            ...
        )
        ctx = await assembler.assemble(
            user_id="user-123",
            conversation_id="conv-456",
            message="Hello!"
        )
    """

    def __init__(
        self,
        memory: "MemoryCore",
        conversation_manager: "ConversationManager",
        user_manager: "UserManager",
        self_manager: Optional["SelfManager"] = None,
        self_model_graph: Optional["SelfModelGraph"] = None,
        goal_manager: Optional["GoalManager"] = None,
        thread_manager: Optional["ThreadManager"] = None,
        question_manager: Optional["OpenQuestionManager"] = None,
        marker_store: Optional[Any] = None,
        daemon_id: Optional[str] = None,
    ):
        self.memory = memory
        self.conversation_manager = conversation_manager
        self.user_manager = user_manager
        self.self_manager = self_manager
        self.self_model_graph = self_model_graph
        self.goal_manager = goal_manager
        self.thread_manager = thread_manager
        self.question_manager = question_manager
        self.marker_store = marker_store
        self.daemon_id = daemon_id

    async def assemble(
        self,
        user_id: str,
        conversation_id: str,
        message: str,
        project_id: Optional[str] = None,
        use_continuous: bool = True,
    ) -> ChatContext:
        """
        Assemble full chat context for an LLM request.

        Args:
            user_id: The user sending the message
            conversation_id: The conversation ID
            message: The user's message (used for semantic retrieval)
            project_id: Optional project ID for project-specific context
            use_continuous: If True, use continuous mode with semantic retrieval

        Returns:
            ChatContext with all assembled context
        """
        ctx = ChatContext(
            user_id=user_id,
            conversation_id=conversation_id,
            daemon_id=self.daemon_id,
            project_id=project_id,
            is_continuous=use_continuous,
        )

        if use_continuous:
            await self._assemble_continuous(ctx, message)
        else:
            await self._assemble_legacy(ctx, message)

        return ctx

    async def _assemble_continuous(self, ctx: ChatContext, message: str) -> None:
        """
        Assemble context using continuous mode with semantic retrieval.

        This is the preferred mode - simpler, cleaner, with semantic memory.
        """
        from continuous_context import build_continuous_context, get_recent_messages_for_continuous

        continuous_ctx = build_continuous_context(
            user_id=ctx.user_id,
            conversation_id=ctx.conversation_id,
            user_manager=self.user_manager,
            thread_manager=self.thread_manager,
            question_manager=self.question_manager,
            conversation_manager=self.conversation_manager,
            daemon_name="Cass",
            daemon_id=self.daemon_id,
            memory=self.memory,
            query=message,
        )

        ctx.system_prompt = continuous_ctx.system_prompt
        ctx.context_sizes = {
            section: len(content)
            for section, content in continuous_ctx.context_sections.items()
        }
        ctx.context_sizes["total"] = continuous_ctx.token_estimate * 4  # Rough char estimate

        # Get recent messages for conversation continuity
        ctx.recent_messages = get_recent_messages_for_continuous(
            conversation_manager=self.conversation_manager,
            conversation_id=ctx.conversation_id,
            limit=12
        )

        # Extract counts from context sections for diagnostics
        if "threads" in continuous_ctx.context_sections:
            ctx.thread_count = continuous_ctx.context_sections["threads"].count("\n") // 2
        if "questions" in continuous_ctx.context_sections:
            ctx.question_count = continuous_ctx.context_sections["questions"].count("\n") // 2
        if "semantic_memories" in continuous_ctx.context_sections:
            ctx.context_sizes["semantic"] = len(continuous_ctx.context_sections["semantic_memories"])

    async def _assemble_legacy(self, ctx: ChatContext, message: str) -> None:
        """
        Assemble context using legacy hierarchical retrieval.

        This is kept for backwards compatibility but continuous mode is preferred.
        """
        context_sizes = {}
        memory_parts = []

        # 1. Hierarchical memory (summaries + details)
        hierarchical = self.memory.retrieve_hierarchical(
            query=message,
            conversation_id=ctx.conversation_id
        )
        working_summary = self.conversation_manager.get_working_summary(ctx.conversation_id)
        recent_messages = self.conversation_manager.get_recent_messages(ctx.conversation_id, count=6)
        memory_context = self.memory.format_hierarchical_context(
            hierarchical,
            working_summary=working_summary,
            recent_messages=recent_messages
        )
        context_sizes["hierarchical"] = len(memory_context)
        memory_parts.append(memory_context)

        # 2. User context
        if ctx.user_id:
            user_context_entries = self.memory.retrieve_user_context(
                query=message,
                user_id=ctx.user_id
            )
            ctx.user_context = self.memory.format_user_context(user_context_entries)
            context_sizes["user"] = len(ctx.user_context) if ctx.user_context else 0

            # Check for sparse user model
            sparseness = self.user_manager.check_user_model_sparseness(ctx.user_id)
            ctx.intro_guidance = sparseness.get("intro_guidance")

            # Rich user modeling
            ctx.user_model_context = self.user_manager.get_rich_user_context(ctx.user_id)
            ctx.relationship_context = self.user_manager.get_relationship_context(ctx.user_id)
            context_sizes["user_model"] = len(ctx.user_model_context) if ctx.user_model_context else 0
            context_sizes["relationship"] = len(ctx.relationship_context) if ctx.relationship_context else 0

        # 3. Project context
        if ctx.project_id:
            project_docs = self.memory.retrieve_project_context(
                query=message,
                project_id=ctx.project_id
            )
            project_context = self.memory.format_project_context(project_docs)
            if project_context:
                memory_parts.insert(0, project_context)
            context_sizes["project"] = len(project_context) if project_context else 0

        # 4. Self-model context
        if self.self_manager:
            self_context = self.self_manager.get_self_context(
                include_observations=False,
                message=message,
                conversation_id=ctx.conversation_id,
                directive_growth_edges=True
            )
            if self_context:
                memory_parts.insert(0, self_context)
            context_sizes["self_model"] = len(self_context) if self_context else 0

        # 5. Self-model graph (intentions, observations)
        if self.self_model_graph:
            intention_context = self.self_model_graph.get_intention_directive_context(
                message=message,
                conversation_id=ctx.conversation_id,
                top_n=3
            )
            if intention_context:
                memory_parts.insert(0, intention_context)
            context_sizes["intentions"] = len(intention_context) if intention_context else 0

            graph_context = self.self_model_graph.get_graph_context(
                message=message,
                include_contradictions=True,
                include_recent=True,
                include_stats=True,
                max_related=5
            )
            if graph_context:
                memory_parts.insert(0, graph_context)
            context_sizes["graph"] = len(graph_context) if graph_context else 0

        # 6. Wiki context (automatic retrieval)
        try:
            from wiki import get_automatic_wiki_context
            wiki_context_str, wiki_page_names, _ = get_automatic_wiki_context(
                query=message,
                relevance_threshold=0.5,
                max_pages=3,
                max_tokens=1500
            )
            if wiki_context_str:
                memory_parts.insert(0, wiki_context_str)
                ctx.wiki_pages_count = len(wiki_page_names)
            context_sizes["wiki"] = len(wiki_context_str) if wiki_context_str else 0
        except ImportError:
            pass

        # 7. Cross-session insights
        cross_session_insights = self.memory.retrieve_cross_session_insights(
            query=message,
            n_results=5,
            max_distance=1.2,
            min_importance=0.5,
            exclude_conversation_id=ctx.conversation_id
        )
        if cross_session_insights:
            insights_context = self.memory.format_cross_session_context(cross_session_insights)
            if insights_context:
                memory_parts.insert(0, insights_context)
            context_sizes["insights"] = len(insights_context) if insights_context else 0

        # 8. Active goals
        if self.goal_manager:
            goals_context = self.goal_manager.get_active_summary()
            if goals_context:
                memory_parts.insert(0, goals_context)
            context_sizes["goals"] = len(goals_context) if goals_context else 0

        # 9. Pattern surfacing (skip for continuous - too slow)
        if self.marker_store and not ctx.is_continuous:
            try:
                from pattern_aggregation import get_pattern_summary_for_surfacing
                patterns_context, pattern_count = get_pattern_summary_for_surfacing(
                    marker_store=self.marker_store,
                    min_significance=0.5,
                    limit=3
                )
                if patterns_context:
                    memory_parts.insert(0, patterns_context)
                    ctx.pattern_count = pattern_count
                context_sizes["patterns"] = len(patterns_context) if patterns_context else 0
            except ImportError:
                pass

        # 10. Threads and questions
        if self.thread_manager:
            ctx.threads_context = self.thread_manager.format_threads_context(
                user_id=ctx.user_id,
                limit=5
            )
            if ctx.threads_context:
                ctx.thread_count = len(self.thread_manager.get_active_threads(
                    user_id=ctx.user_id, limit=5
                ))
            context_sizes["threads"] = len(ctx.threads_context) if ctx.threads_context else 0

        if self.question_manager:
            ctx.questions_context = self.question_manager.format_questions_context(
                user_id=ctx.user_id,
                limit=5
            )
            if ctx.questions_context:
                ctx.question_count = len(self.question_manager.get_open_questions(
                    user_id=ctx.user_id, limit=5
                ))
            context_sizes["questions"] = len(ctx.questions_context) if ctx.questions_context else 0

        # 11. Global state (State Bus)
        if self.daemon_id:
            try:
                from state_bus import get_state_bus
                state_bus = get_state_bus(self.daemon_id)
                ctx.global_state_context = state_bus.get_context_snapshot()
                context_sizes["state_bus"] = len(ctx.global_state_context) if ctx.global_state_context else 0
            except ImportError:
                pass

        # Assemble final memory context
        ctx.memory_context = "\n\n".join(memory_parts)
        context_sizes["total"] = len(ctx.memory_context)
        ctx.context_sizes = context_sizes

        # Get unsummarized count
        unsummarized = self.conversation_manager.get_unsummarized_messages(ctx.conversation_id)
        ctx.unsummarized_count = len(unsummarized) if unsummarized else 0

        # Get recent messages for history
        ctx.recent_messages = self.conversation_manager.get_recent_messages(
            ctx.conversation_id, count=12
        ) or []
