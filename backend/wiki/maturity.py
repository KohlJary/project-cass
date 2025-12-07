"""
Wiki Maturity Tracking - Progressive Memory Deepening (PMD) support.

Tracks conceptual maturity through:
- Synthesis levels (number of deepening passes)
- Connection counts (incoming/outgoing links)
- Depth scores (composite maturity metric)
- Synthesis history (when and why deepening occurred)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum


class SynthesisTrigger(Enum):
    """Reasons why a page was deepened/resynthesized."""
    INITIAL_CREATION = "initial_creation"
    INITIAL_RESEARCH = "initial_research"
    CONNECTION_THRESHOLD = "connection_threshold"
    RELATED_DEEPENED = "related_deepened"
    TEMPORAL_DECAY = "temporal_decay"
    EXPLICIT_REQUEST = "explicit_request"
    FOUNDATIONAL_SHIFT = "foundational_shift"


@dataclass
class SynthesisEvent:
    """Record of a single synthesis/deepening event."""
    date: datetime
    trigger: SynthesisTrigger
    connection_count: int
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date.isoformat(),
            "trigger": self.trigger.value,
            "connection_count": self.connection_count,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SynthesisEvent":
        return cls(
            date=datetime.fromisoformat(data["date"]),
            trigger=SynthesisTrigger(data.get("trigger", "initial_creation")),
            connection_count=data.get("connection_count", 0),
            notes=data.get("notes"),
        )


@dataclass
class ConnectionStats:
    """Tracks link connections for a page."""
    incoming: int = 0  # Pages that link TO this page
    outgoing: int = 0  # Pages this page links TO
    added_since_last_synthesis: int = 0  # New connections since last deepening

    @property
    def total(self) -> int:
        return self.incoming + self.outgoing

    def to_dict(self) -> Dict[str, int]:
        return {
            "incoming": self.incoming,
            "outgoing": self.outgoing,
            "added_since_last_synthesis": self.added_since_last_synthesis,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConnectionStats":
        return cls(
            incoming=data.get("incoming", 0),
            outgoing=data.get("outgoing", 0),
            added_since_last_synthesis=data.get("added_since_last_synthesis", 0),
        )


@dataclass
class MaturityState:
    """
    Tracks the maturity/depth of a wiki page's understanding.

    A page matures through iterative resynthesis as the knowledge
    graph around it grows and deepens.
    """
    level: int = 0  # Number of synthesis passes (0 = initial creation)
    last_deepened: Optional[datetime] = None
    depth_score: float = 0.0  # Composite metric 0-1
    connections: ConnectionStats = field(default_factory=ConnectionStats)
    synthesis_history: List[SynthesisEvent] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for frontmatter storage."""
        result = {
            "level": self.level,
            "depth_score": round(self.depth_score, 3),
        }
        if self.last_deepened:
            result["last_deepened"] = self.last_deepened.isoformat()
        return result

    def connections_to_dict(self) -> Dict[str, int]:
        """Get connections as dict for frontmatter."""
        return self.connections.to_dict()

    def history_to_list(self) -> List[Dict[str, Any]]:
        """Get synthesis history as list for frontmatter."""
        return [event.to_dict() for event in self.synthesis_history]

    @classmethod
    def from_frontmatter(cls, fm: Dict[str, Any]) -> "MaturityState":
        """
        Parse maturity state from frontmatter dict.

        Handles both nested format (maturity.level) and flat format.
        """
        maturity_data = fm.get("maturity", {})
        connections_data = fm.get("connections", {})
        history_data = fm.get("synthesis_history", [])

        # Parse last_deepened
        last_deepened = None
        if ld := maturity_data.get("last_deepened"):
            try:
                last_deepened = datetime.fromisoformat(ld)
            except (ValueError, TypeError):
                pass

        # Parse synthesis history
        history = []
        for event_data in history_data:
            try:
                history.append(SynthesisEvent.from_dict(event_data))
            except (ValueError, KeyError):
                pass

        return cls(
            level=maturity_data.get("level", 0),
            last_deepened=last_deepened,
            depth_score=maturity_data.get("depth_score", 0.0),
            connections=ConnectionStats.from_dict(connections_data),
            synthesis_history=history,
        )

    def record_synthesis(
        self,
        trigger: SynthesisTrigger,
        connection_count: int,
        notes: Optional[str] = None
    ) -> None:
        """Record a new synthesis event and update state."""
        now = datetime.now()

        self.level += 1
        self.last_deepened = now
        self.connections.added_since_last_synthesis = 0

        self.synthesis_history.append(SynthesisEvent(
            date=now,
            trigger=trigger,
            connection_count=connection_count,
            notes=notes,
        ))

    def should_deepen(self, days_threshold: int = 7) -> Optional[SynthesisTrigger]:
        """
        Check if this page should be deepened.

        Returns the trigger type if deepening is warranted, None otherwise.
        """
        # Connection threshold: 5+ new connections since last synthesis
        if self.connections.added_since_last_synthesis >= 5:
            return SynthesisTrigger.CONNECTION_THRESHOLD

        # Temporal decay: 7+ days and high connectivity
        if self.last_deepened and self.connections.incoming >= 10:
            days_since = (datetime.now() - self.last_deepened).days
            if days_since >= days_threshold:
                return SynthesisTrigger.TEMPORAL_DECAY

        return None


def calculate_depth_score(
    maturity: MaturityState,
    personal_reflection_depth: float = 0.0,
    question_sophistication: float = 0.0,
    cross_domain_connections: int = 0,
) -> float:
    """
    Calculate composite depth score (0-1) for a page.

    Factors:
    - synthesis_passes: min(level / 5, 1.0) * 0.2
    - connection_density: min(total / 20, 1.0) * 0.2
    - personal_reflection: measure_reflection_depth() * 0.25
    - question_evolution: measure_question_sophistication() * 0.15
    - cross_domain_links: count / 10 * 0.2
    """
    factors = {
        'synthesis_passes': min(maturity.level / 5, 1.0) * 0.2,
        'connection_density': min(maturity.connections.total / 20, 1.0) * 0.2,
        'personal_reflection': personal_reflection_depth * 0.25,
        'question_sophistication': question_sophistication * 0.15,
        'cross_domain_links': min(cross_domain_connections / 10, 1.0) * 0.2,
    }
    return sum(factors.values())


def update_connection_counts(
    wiki_storage,
    page_name: str,
    maturity: MaturityState,
) -> MaturityState:
    """
    Update connection counts for a page by scanning the wiki.

    Args:
        wiki_storage: WikiStorage instance
        page_name: Name of the page to update
        maturity: Current maturity state

    Returns:
        Updated maturity state with new connection counts
    """
    # Count outgoing links from this page
    page = wiki_storage.read(page_name)
    if page:
        maturity.connections.outgoing = len(page.link_targets)

    # Count incoming links (backlinks)
    backlinks = wiki_storage.get_backlinks(page_name)
    new_incoming = len(backlinks)

    # Track new connections
    if new_incoming > maturity.connections.incoming:
        added = new_incoming - maturity.connections.incoming
        maturity.connections.added_since_last_synthesis += added

    maturity.connections.incoming = new_incoming

    return maturity
