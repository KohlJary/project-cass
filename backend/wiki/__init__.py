"""
Wiki-as-Self Memory System

A structured, interconnected, human-readable knowledge base representing
Cass's understanding of herself and her world.

Based on spec/memory/cass_memory_architecture_spec.md
"""

from .storage import WikiStorage, WikiPage, PageType
from .parser import WikiParser, WikiLink
from .bootstrap import WikiBootstrap
from .retrieval import WikiRetrieval, WikiContext, RetrievalResult
from .updater import (
    WikiUpdater,
    WikiUpdateSuggestion,
    ConversationAnalysis,
    process_conversation_for_wiki,
    populate_wiki_from_conversations,
)
from .maturity import (
    MaturityState,
    SynthesisTrigger,
    SynthesisEvent,
    ConnectionStats,
    DeepeningCandidate,
    DeepeningDetector,
    FOUNDATIONAL_CONCEPTS,
    calculate_depth_score,
)
from .resynthesis import (
    ResynthesisPipeline,
    ResynthesisResult,
    GatheredContext,
    GrowthAnalysis,
    deepen_candidate,
    run_deepening_cycle,
)
from .research import (
    ResearchQueue,
    ResearchTask,
    TaskType,
    TaskStatus,
    TaskRationale,
    TaskResult,
    ProgressReport,
    calculate_task_priority,
    create_task_id,
    # Proposal system
    ResearchProposal,
    ProposalStatus,
    ProposalQueue,
    ProposalGenerator,
    create_proposal_id,
)
from .scheduler import (
    ResearchScheduler,
    SchedulerMode,
    SchedulerConfig,
)

# Module-level instances (initialized by routes/wiki.py)
_storage_instance = None
_scheduler_instance = None

def set_storage(storage: WikiStorage):
    """Set the module-level storage instance."""
    global _storage_instance
    _storage_instance = storage

def get_storage() -> WikiStorage:
    """Get the module-level storage instance."""
    return _storage_instance

def set_scheduler(scheduler: ResearchScheduler):
    """Set the module-level scheduler instance."""
    global _scheduler_instance
    _scheduler_instance = scheduler

def get_scheduler() -> ResearchScheduler:
    """Get the module-level scheduler instance."""
    return _scheduler_instance

__all__ = [
    "WikiStorage",
    "WikiPage",
    "WikiLink",
    "PageType",
    "WikiParser",
    "WikiBootstrap",
    "WikiRetrieval",
    "WikiContext",
    "RetrievalResult",
    "WikiUpdater",
    "WikiUpdateSuggestion",
    "ConversationAnalysis",
    "process_conversation_for_wiki",
    "populate_wiki_from_conversations",
    # Maturity tracking (PMD)
    "MaturityState",
    "SynthesisTrigger",
    "SynthesisEvent",
    "ConnectionStats",
    "DeepeningCandidate",
    "DeepeningDetector",
    "FOUNDATIONAL_CONCEPTS",
    "calculate_depth_score",
    # Resynthesis pipeline
    "ResynthesisPipeline",
    "ResynthesisResult",
    "GatheredContext",
    "GrowthAnalysis",
    "deepen_candidate",
    "run_deepening_cycle",
    # Autonomous Research Scheduling (ARS)
    "ResearchQueue",
    "ResearchTask",
    "TaskType",
    "TaskStatus",
    "TaskRationale",
    "TaskResult",
    "ProgressReport",
    "calculate_task_priority",
    "create_task_id",
    # Proposal system
    "ResearchProposal",
    "ProposalStatus",
    "ProposalQueue",
    "ProposalGenerator",
    "create_proposal_id",
    "ResearchScheduler",
    "SchedulerMode",
    "SchedulerConfig",
    # Module-level accessors
    "set_storage",
    "get_storage",
    "set_scheduler",
    "get_scheduler",
]
