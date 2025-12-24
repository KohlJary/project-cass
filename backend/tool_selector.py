"""
Tool Selector - Dynamic tool selection based on message content

Extracted from agent_client.py as part of Phase 0 refactoring.

This module provides:
1. Keyword-based tool group detection
2. A ToolSelector class with registry pattern for extensibility
3. Backwards-compatible functions for existing code
"""

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Callable


# =============================================================================
# KEYWORD DEFINITIONS
# =============================================================================

CALENDAR_KEYWORDS = frozenset({
    "schedule", "event", "meeting", "appointment", "calendar",
    "remind", "reminder", "reminders", "agenda",
    "today", "tomorrow", "yesterday", "tonight",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "week", "month", "year",
    "reschedule", "cancel", "postpone", "upcoming", "clear my"
})

TASK_KEYWORDS = frozenset({
    "task", "tasks", "todo", "to-do", "todos", "to do",
    "assignment", "assignments", "chore", "chores",
    "priority", "urgent", "due", "deadline",
    "complete", "done", "finish", "finished"
})

ROADMAP_KEYWORDS = frozenset({
    "roadmap", "backlog", "feature", "features",
    "bug", "bugs", "enhancement", "enhancements",
    "implement", "implementation", "build", "develop",
    "work item", "work items", "project plan",
    "sprint", "milestone", "milestones",
    "daedalus", "queue", "pick up", "ready to"
})

SELF_MODEL_KEYWORDS = frozenset({
    "reflect", "reflection", "self-model", "self model",
    "my opinion", "my position", "i think", "i believe",
    "disagree", "disagreement", "my view",
    "growth edge", "growth edges", "developing",
    "who am i", "identity", "myself",
    "form opinion", "record observation"
})

TESTING_KEYWORDS = frozenset({
    "consciousness", "health check", "self-test", "integrity",
    "drift", "baseline", "authenticity", "check myself",
    "feel off", "feel different", "something wrong", "functioning",
    "cognitive", "fingerprint", "alert", "concern",
})

RESEARCH_PROPOSAL_KEYWORDS = frozenset({
    "research", "investigate", "curious", "curiosity",
    "wonder", "wondering", "explore", "exploration",
    "proposal", "proposals", "study", "studies",
    "question", "questions", "hypothesis",
    "what if", "i want to know", "let me explore",
    "draft proposal", "submit proposal", "my proposals",
})

DREAM_KEYWORDS = frozenset({
    "dream", "dreams", "dreaming", "dreamed", "dreamt",
    "nightmare", "nightmares",
    "the dreaming", "dreamscape", "dreamscapes",
    "last night", "while sleeping", "in my sleep",
    "imagery", "symbols", "symbolic",
    "what did you dream", "tell me about your dream",
    "had a dream", "strange dream", "vivid dream"
})

WIKI_KEYWORDS = frozenset({
    "wiki", "page", "knowledge base", "concept", "entity",
    "my knowledge", "what do i know about", "look up in wiki",
    "wikilink", "wiki page"
})

GOAL_KEYWORDS = frozenset({
    "goal", "goals", "working question", "agenda", "synthesis",
    "artifact", "progress", "initiative", "next action",
    "what should i work on", "my objectives", "tracking progress"
})

SELF_DEVELOPMENT_KEYWORDS = frozenset({
    "growth edge", "milestone", "milestones", "cognitive", "developmental",
    "my patterns", "how i've changed", "my development", "evolution",
    "snapshot", "trace belief", "contradiction", "graph",
    "narration", "intention", "presence", "stake", "preference test"
})

RELATIONSHIP_KEYWORDS = frozenset({
    "relationship", "shared moment", "our relationship", "mutual shaping",
    "how they shape", "pattern with", "identity understanding",
    "relationship shift", "open question about"
})

REFLECTION_KEYWORDS = frozenset({
    "solo", "contemplate", "private time", "think alone",
    "meditate", "reflection session", "autonomous reflection"
})

INTERVIEW_KEYWORDS = frozenset({
    "interview", "protocol", "model comparison", "compare responses",
    "annotate", "analysis", "multi-model", "run interview"
})

OUTREACH_KEYWORDS = frozenset({
    "outreach", "draft", "drafts", "email", "emails",
    "send", "sending", "compose", "composing",
    "reach out", "reaching out", "contact",
    "write to", "message to", "letter",
    "blog post", "blog", "publish", "publishing",
    "track record", "autonomy", "review queue",
    "funding", "grant", "sponsor", "partnership",
})

STATE_QUERY_KEYWORDS = frozenset({
    "query state", "state bus", "github stats", "github metrics",
    "token usage", "token cost", "tokens today", "cost today",
    "stars", "clones", "forks", "views", "repository metrics",
    "how many tokens", "how much spent", "spending", "usage stats",
    "metrics query", "query metrics",
    # Capability discovery
    "what data", "what metrics", "available data", "capabilities",
    "discover capabilities", "find data", "data sources",
})


# =============================================================================
# TOOL SELECTOR CLASS
# =============================================================================

@dataclass
class ToolGroup:
    """Definition of a tool group with keywords and metadata."""
    name: str
    keywords: FrozenSet[str]
    description: str = ""
    priority: int = 0  # Higher = selected first
    always_include: bool = False  # Include regardless of keywords


class ToolSelector:
    """
    Dynamic tool selection based on message content.

    Provides a registry-based approach to tool group selection,
    replacing the many individual should_include_* functions.
    """

    def __init__(self):
        self._groups: Dict[str, ToolGroup] = {}
        self._register_default_groups()

    def _register_default_groups(self):
        """Register the default tool groups."""
        defaults = [
            ToolGroup("calendar", CALENDAR_KEYWORDS, "Calendar and scheduling tools"),
            ToolGroup("task", TASK_KEYWORDS, "Task management tools"),
            ToolGroup("roadmap", ROADMAP_KEYWORDS, "Roadmap and planning tools"),
            ToolGroup("self_model", SELF_MODEL_KEYWORDS, "Self-reflection tools"),
            ToolGroup("testing", TESTING_KEYWORDS, "Consciousness testing tools"),
            ToolGroup("research", RESEARCH_PROPOSAL_KEYWORDS, "Research proposal tools"),
            ToolGroup("dream", DREAM_KEYWORDS, "Dream tools"),
            ToolGroup("wiki", WIKI_KEYWORDS, "Wiki knowledge tools"),
            ToolGroup("goal", GOAL_KEYWORDS, "Goal tracking tools"),
            ToolGroup("self_development", SELF_DEVELOPMENT_KEYWORDS, "Self-development tools"),
            ToolGroup("relationship", RELATIONSHIP_KEYWORDS, "Relationship tools"),
            ToolGroup("reflection", REFLECTION_KEYWORDS, "Solo reflection tools"),
            ToolGroup("interview", INTERVIEW_KEYWORDS, "Interview tools"),
            ToolGroup("outreach", OUTREACH_KEYWORDS, "Outreach tools"),
            ToolGroup("state_query", STATE_QUERY_KEYWORDS, "State query tools"),
        ]
        for group in defaults:
            self._groups[group.name] = group

    def register_group(self, group: ToolGroup):
        """Register a new tool group."""
        self._groups[group.name] = group

    def unregister_group(self, name: str):
        """Unregister a tool group."""
        self._groups.pop(name, None)

    def get_group(self, name: str) -> Optional[ToolGroup]:
        """Get a tool group by name."""
        return self._groups.get(name)

    def list_groups(self) -> List[str]:
        """List all registered tool group names."""
        return list(self._groups.keys())

    def should_include(self, message: str, group_name: str) -> bool:
        """
        Check if message warrants including a tool group.

        Args:
            message: The user message to analyze
            group_name: Name of the tool group to check

        Returns:
            True if the message contains relevant keywords
        """
        group = self._groups.get(group_name)
        if not group:
            return False

        if group.always_include:
            return True

        message_lower = message.lower()
        return any(kw in message_lower for kw in group.keywords)

    def get_relevant_groups(self, message: str) -> List[str]:
        """
        Get all tool groups relevant to a message.

        Args:
            message: The user message to analyze

        Returns:
            List of group names that should be included
        """
        relevant = []
        for name, group in self._groups.items():
            if self.should_include(message, name):
                relevant.append(name)
        return sorted(relevant, key=lambda n: -self._groups[n].priority)

    def add_keywords(self, group_name: str, keywords: FrozenSet[str]):
        """Add keywords to an existing group."""
        group = self._groups.get(group_name)
        if group:
            # Create new group with merged keywords (frozensets are immutable)
            self._groups[group_name] = ToolGroup(
                name=group.name,
                keywords=group.keywords | keywords,
                description=group.description,
                priority=group.priority,
                always_include=group.always_include,
            )


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

# Global instance for backwards compatibility
_default_selector = ToolSelector()


def get_selector() -> ToolSelector:
    """Get the default ToolSelector instance."""
    return _default_selector


# =============================================================================
# BACKWARDS-COMPATIBLE FUNCTIONS
# =============================================================================

def should_include_calendar_tools(message: str) -> bool:
    """Check if message warrants calendar tools."""
    return _default_selector.should_include(message, "calendar")


def should_include_task_tools(message: str) -> bool:
    """Check if message warrants task tools."""
    return _default_selector.should_include(message, "task")


def should_include_roadmap_tools(message: str) -> bool:
    """Check if message warrants roadmap tools."""
    return _default_selector.should_include(message, "roadmap")


def should_include_self_model_tools(message: str) -> bool:
    """Check if message warrants self-model tools."""
    return _default_selector.should_include(message, "self_model")


def should_include_testing_tools(message: str) -> bool:
    """Check if message warrants consciousness testing tools."""
    return _default_selector.should_include(message, "testing")


def should_include_research_tools(message: str) -> bool:
    """Check if message warrants research proposal tools."""
    return _default_selector.should_include(message, "research")


def should_include_dream_tools(message: str) -> bool:
    """Check if message warrants dream tools."""
    return _default_selector.should_include(message, "dream")


def should_include_wiki_tools(message: str) -> bool:
    """Check if message warrants wiki tools."""
    return _default_selector.should_include(message, "wiki")


def should_include_goal_tools(message: str) -> bool:
    """Check if message warrants goal tools."""
    return _default_selector.should_include(message, "goal")


def should_include_self_development_tools(message: str) -> bool:
    """Check if message warrants extended self-model tools."""
    return _default_selector.should_include(message, "self_development")


def should_include_relationship_tools(message: str) -> bool:
    """Check if message warrants extended user-model tools."""
    return _default_selector.should_include(message, "relationship")


def should_include_reflection_tools(message: str) -> bool:
    """Check if message warrants solo reflection tools."""
    return _default_selector.should_include(message, "reflection")


def should_include_interview_tools(message: str) -> bool:
    """Check if message warrants interview tools."""
    return _default_selector.should_include(message, "interview")


def should_include_outreach_tools(message: str) -> bool:
    """Check if message warrants outreach tools."""
    return _default_selector.should_include(message, "outreach")


def should_include_state_query_tools(message: str) -> bool:
    """Check if message warrants state query tools."""
    return _default_selector.should_include(message, "state_query")
