"""
Queryable Sources for the Unified State Query Interface.

This package contains implementations of QueryableSource that wrap
existing subsystems and expose them through the unified query interface.

Each source:
- Wraps an existing manager/tracker class
- Implements the QueryableSource interface
- Maintains precomputed rollups for fast access
- Registers with the GlobalStateBus on startup
"""

from .github_source import GitHubQueryableSource
from .token_source import TokenQueryableSource
from .conversation_source import ConversationQueryableSource
from .memory_source import MemoryQueryableSource
from .self_source import SelfQueryableSource
from .goal_source import GoalQueryableSource

__all__ = [
    "GitHubQueryableSource",
    "TokenQueryableSource",
    "ConversationQueryableSource",
    "MemoryQueryableSource",
    "SelfQueryableSource",
    "GoalQueryableSource",
]
