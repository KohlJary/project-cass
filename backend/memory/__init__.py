"""
Cass Memory System

Modular memory system organized by functional domain:
- core: ChromaDB setup, conversation storage/retrieval, utilities
- summaries: Summary generation, working summary, hierarchical retrieval
- journals: Journal generation, storage, observation extraction
- self_model: Self-observations, per-user journals, growth evaluation
- context_sources: Project/wiki/user embeddings and retrieval
- insights: Cross-session insight bridging
- threads: Conversation thread tracking for narrative coherence
- questions: Open question tracking for unresolved items

The CassMemory class is a facade that composes all submodules,
maintaining backwards compatibility with existing code.
"""

from .core import MemoryCore, initialize_attractor_basins
from .summaries import SummaryManager
from .journals import JournalManager
from .self_model import SelfModelMemory
from .context_sources import ContextSourceManager
from .insights import InsightManager
from .threads import ThreadManager
from .questions import OpenQuestionManager


class CassMemory:
    """
    Facade for the memory system - maintains backwards compatibility.

    Composes domain-specific managers and delegates method calls to them.
    All existing imports (`from memory import CassMemory`) continue to work.
    """

    def __init__(self, persist_dir: str = None):
        # Initialize core (owns ChromaDB client/collection)
        self._core = MemoryCore(persist_dir)

        # Initialize domain managers with core reference
        self._summaries = SummaryManager(self._core)
        self._journals = JournalManager(self._core, self._summaries)
        self._self_model = SelfModelMemory(self._core)
        self._context = ContextSourceManager(self._core)
        self._insights = InsightManager(self._core)

        # Wire up circular dependency
        self._journals.set_summary_manager(self._summaries)

    # === Core Properties ===

    @property
    def collection(self):
        """Direct access to ChromaDB collection."""
        return self._core.collection

    @property
    def client(self):
        """Direct access to ChromaDB client."""
        return self._core.client

    # === Core Methods ===

    def _generate_id(self, content: str, timestamp: str) -> str:
        return self._core._generate_id(content, timestamp)

    async def generate_gist(self, user_message: str, assistant_response: str):
        return await self._core.generate_gist(user_message, assistant_response)

    async def store_conversation(self, *args, **kwargs):
        return await self._core.store_conversation(*args, **kwargs)

    def store_attractor_marker(self, *args, **kwargs):
        return self._core.store_attractor_marker(*args, **kwargs)

    def retrieve_relevant(self, *args, **kwargs):
        return self._core.retrieve_relevant(*args, **kwargs)

    def format_for_context(self, memories):
        return self._core.format_for_context(memories)

    def get_recent(self, n: int = 10):
        return self._core.get_recent(n)

    def get_by_conversation(self, conversation_id: str):
        return self._core.get_by_conversation(conversation_id)

    def chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 200):
        return self._core.chunk_text(text, chunk_size, overlap)

    def count(self):
        return self._core.count()

    def clear(self):
        return self._core.clear()

    def export_memories(self):
        return self._core.export_memories()

    def import_memories(self, data):
        return self._core.import_memories(data)

    # === Summary Methods ===

    async def evaluate_summarization_readiness(self, *args, **kwargs):
        return await self._summaries.evaluate_summarization_readiness(*args, **kwargs)

    async def generate_summary_chunk(self, *args, **kwargs):
        return await self._summaries.generate_summary_chunk(*args, **kwargs)

    async def generate_working_summary(self, *args, **kwargs):
        return await self._summaries.generate_working_summary(*args, **kwargs)

    def store_summary(self, *args, **kwargs):
        return self._summaries.store_summary(*args, **kwargs)

    def get_summaries_for_conversation(self, conversation_id: str):
        return self._summaries.get_summaries_for_conversation(conversation_id)

    def get_summaries_by_date(self, date: str):
        return self._summaries.get_summaries_by_date(date)

    def get_conversations_by_date(self, date: str, user_id=None):
        return self._summaries.get_conversations_by_date(date, user_id)

    def get_user_ids_by_date(self, date: str):
        return self._summaries.get_user_ids_by_date(date)

    def retrieve_hierarchical(self, *args, **kwargs):
        return self._summaries.retrieve_hierarchical(*args, **kwargs)

    def format_hierarchical_context(self, *args, **kwargs):
        return self._summaries.format_hierarchical_context(*args, **kwargs)

    # === Journal Methods ===

    async def generate_journal_summary(self, journal_text: str):
        return await self._journals.generate_journal_summary(journal_text)

    async def generate_journal_entry(self, *args, **kwargs):
        return await self._journals.generate_journal_entry(*args, **kwargs)

    async def generate_conversation_digest(self, *args, **kwargs):
        return await self._journals.generate_conversation_digest(*args, **kwargs)

    async def generate_journal_from_digests(self, *args, **kwargs):
        return await self._journals.generate_journal_from_digests(*args, **kwargs)

    async def extract_observations_from_summaries(self, *args, **kwargs):
        return await self._journals.extract_observations_from_summaries(*args, **kwargs)

    async def store_journal_entry(self, *args, **kwargs):
        return await self._journals.store_journal_entry(*args, **kwargs)

    def get_journal_entry(self, date: str):
        return self._journals.get_journal_entry(date)

    def set_journal_locked(self, date: str, locked: bool):
        return self._journals.set_journal_locked(date, locked)

    def get_recent_journals(self, n: int = 10):
        return self._journals.get_recent_journals(n)

    # === Self-Model Methods ===

    def embed_self_observation(self, *args, **kwargs):
        return self._self_model.embed_self_observation(*args, **kwargs)

    def embed_self_profile(self, profile_text: str, timestamp: str):
        return self._self_model.embed_self_profile(profile_text, timestamp)

    def sync_self_observations_from_file(self, self_manager):
        return self._self_model.sync_self_observations_from_file(self_manager)

    def embed_per_user_journal(self, *args, **kwargs):
        return self._self_model.embed_per_user_journal(*args, **kwargs)

    def embed_question_reflection(self, *args, **kwargs):
        return self._self_model.embed_question_reflection(*args, **kwargs)

    def embed_growth_evaluation(self, *args, **kwargs):
        return self._self_model.embed_growth_evaluation(*args, **kwargs)

    def retrieve_self_context(self, *args, **kwargs):
        return self._self_model.retrieve_self_context(*args, **kwargs)

    async def extract_self_observations_from_journal(self, *args, **kwargs):
        return await self._self_model.extract_self_observations_from_journal(*args, **kwargs)

    def _parse_self_observations(self, text: str):
        return self._self_model._parse_self_observations(text)

    async def generate_user_observations(self, *args, **kwargs):
        return await self._self_model.generate_user_observations(*args, **kwargs)

    async def generate_per_user_journal(self, *args, **kwargs):
        return await self._self_model.generate_per_user_journal(*args, **kwargs)

    async def extract_opinions_from_conversations(self, *args, **kwargs):
        return await self._self_model.extract_opinions_from_conversations(*args, **kwargs)

    async def evaluate_growth_edges(self, *args, **kwargs):
        return await self._self_model.evaluate_growth_edges(*args, **kwargs)

    async def reflect_on_open_questions(self, *args, **kwargs):
        return await self._self_model.reflect_on_open_questions(*args, **kwargs)

    # === Context Source Methods ===

    def embed_project_file(self, *args, **kwargs):
        return self._context.embed_project_file(*args, **kwargs)

    def embed_project_document(self, *args, **kwargs):
        return self._context.embed_project_document(*args, **kwargs)

    def remove_project_document_embeddings(self, project_id: str, document_id: str):
        return self._context.remove_project_document_embeddings(project_id, document_id)

    def remove_project_file_embeddings(self, project_id: str, file_path: str):
        return self._context.remove_project_file_embeddings(project_id, file_path)

    def remove_project_embeddings(self, project_id: str):
        return self._context.remove_project_embeddings(project_id)

    def search_project_documents(self, *args, **kwargs):
        return self._context.search_project_documents(*args, **kwargs)

    def retrieve_project_context(self, *args, **kwargs):
        return self._context.retrieve_project_context(*args, **kwargs)

    def format_project_context(self, documents):
        return self._context.format_project_context(documents)

    def embed_wiki_page(self, *args, **kwargs):
        return self._context.embed_wiki_page(*args, **kwargs)

    def remove_wiki_page_embeddings(self, page_name: str):
        return self._context.remove_wiki_page_embeddings(page_name)

    def retrieve_wiki_context(self, *args, **kwargs):
        return self._context.retrieve_wiki_context(*args, **kwargs)

    def embed_user_profile(self, *args, **kwargs):
        return self._context.embed_user_profile(*args, **kwargs)

    def embed_user_observation(self, *args, **kwargs):
        return self._context.embed_user_observation(*args, **kwargs)

    def retrieve_user_context(self, *args, **kwargs):
        return self._context.retrieve_user_context(*args, **kwargs)

    def format_user_context(self, context_entries):
        return self._context.format_user_context(context_entries)

    # === Cross-Session Insight Methods ===

    def store_cross_session_insight(self, *args, **kwargs):
        return self._insights.store_cross_session_insight(*args, **kwargs)

    def retrieve_cross_session_insights(self, *args, **kwargs):
        return self._insights.retrieve_cross_session_insights(*args, **kwargs)

    def _increment_insight_retrieval(self, insight):
        return self._insights._increment_insight_retrieval(insight)

    def get_cross_session_insights_stats(self):
        return self._insights.get_cross_session_insights_stats()

    def list_cross_session_insights(self, *args, **kwargs):
        return self._insights.list_cross_session_insights(*args, **kwargs)

    def format_cross_session_context(self, insights):
        return self._insights.format_cross_session_context(insights)

    def delete_cross_session_insight(self, insight_id: str):
        return self._insights.delete_cross_session_insight(insight_id)


# Re-export for backwards compatibility
__all__ = [
    'CassMemory',
    'initialize_attractor_basins',
    'ThreadManager',
    'OpenQuestionManager',
]
