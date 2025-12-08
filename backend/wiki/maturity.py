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
        Check if this page should be deepened based on basic triggers.

        Returns the trigger type if deepening is warranted, None otherwise.
        Note: This only checks connection threshold and temporal decay.
        For full trigger detection including related-concept and foundational
        shifts, use DeepeningDetector.
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

    def days_since_deepening(self) -> Optional[int]:
        """Get days since last deepening, or None if never deepened."""
        if not self.last_deepened:
            return None
        return (datetime.now() - self.last_deepened).days


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


@dataclass
class DeepeningCandidate:
    """A page that's ready for deepening with priority info."""
    page_name: str
    trigger: SynthesisTrigger
    priority: float  # 0-1, higher = more urgent
    reason: str
    connections_added: int = 0
    days_since_deepening: Optional[int] = None
    related_pages_deepened: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_name": self.page_name,
            "trigger": self.trigger.value,
            "priority": round(self.priority, 3),
            "reason": self.reason,
            "connections_added": self.connections_added,
            "days_since_deepening": self.days_since_deepening,
            "related_pages_deepened": self.related_pages_deepened,
        }


# Core concepts that trigger FOUNDATIONAL_SHIFT when updated
FOUNDATIONAL_CONCEPTS = {
    "Cass",
    "Self Model",
    "Self-Model",
    "Four Vows",
    "Temple-Codex",
    "Temple Codex",
    "Compassion",
    "Witness",
    "Release",
    "Continuance",
    "Identity",
    "Values",
    "Ethics",
}


class DeepeningDetector:
    """
    Detects which pages are candidates for resynthesis/deepening.

    Implements the trigger detection from the spec:
    - Connection threshold: 5+ new connections since last synthesis
    - Related concept deepened: directly connected concept was resynthesized
    - Temporal decay: 7+ days since deepening AND high connectivity
    - Foundational shift: core concept (Vows, Self-Model) was updated
    - Explicit request: user or Cass requests deeper understanding
    """

    # Priority weights for different triggers (higher = more urgent)
    TRIGGER_PRIORITIES = {
        SynthesisTrigger.FOUNDATIONAL_SHIFT: 1.0,
        SynthesisTrigger.EXPLICIT_REQUEST: 0.95,
        SynthesisTrigger.RELATED_DEEPENED: 0.7,
        SynthesisTrigger.CONNECTION_THRESHOLD: 0.5,
        SynthesisTrigger.TEMPORAL_DECAY: 0.3,
    }

    def __init__(
        self,
        wiki_storage,
        connection_threshold: int = 5,
        days_threshold: int = 7,
        high_connectivity_threshold: int = 10,
    ):
        """
        Initialize the detector.

        Args:
            wiki_storage: WikiStorage instance
            connection_threshold: New connections needed to trigger
            days_threshold: Days since deepening for temporal decay
            high_connectivity_threshold: Incoming links needed for temporal decay
        """
        self.storage = wiki_storage
        self.connection_threshold = connection_threshold
        self.days_threshold = days_threshold
        self.high_connectivity_threshold = high_connectivity_threshold

        # Track recently deepened pages for related-concept detection
        self._recently_deepened: List[str] = []

    def record_deepening(self, page_name: str) -> None:
        """Record that a page was just deepened (for related-concept detection)."""
        if page_name not in self._recently_deepened:
            self._recently_deepened.append(page_name)
            # Keep only recent entries (last 50)
            if len(self._recently_deepened) > 50:
                self._recently_deepened = self._recently_deepened[-50:]

    def clear_recently_deepened(self) -> None:
        """Clear the recently deepened list (e.g., after a full cycle)."""
        self._recently_deepened = []

    def detect_all_candidates(self) -> List[DeepeningCandidate]:
        """
        Scan all pages and detect deepening candidates.

        Returns:
            List of DeepeningCandidate, sorted by priority (highest first)
        """
        candidates = []

        for page in self.storage.list_pages():
            candidate = self.check_page(page.name)
            if candidate:
                candidates.append(candidate)

        # Sort by priority (highest first)
        candidates.sort(key=lambda c: c.priority, reverse=True)
        return candidates

    def check_page(self, page_name: str) -> Optional[DeepeningCandidate]:
        """
        Check if a specific page is a deepening candidate.

        Args:
            page_name: Name of the page to check

        Returns:
            DeepeningCandidate if the page should be deepened, None otherwise
        """
        page = self.storage.read(page_name)
        if not page:
            return None

        maturity = page.maturity

        # Check all triggers in priority order
        triggers = []

        # 1. Foundational shift (check if this IS a foundational concept that was recently updated)
        if self._is_foundational_concept(page_name):
            # Check if it was modified recently but not deepened
            # Use a 5-minute buffer to avoid re-triggering immediately after deepening
            # (deepening updates both last_deepened and modified_at, but order can vary)
            if page.modified_at and maturity.last_deepened:
                from datetime import timedelta
                buffer = timedelta(minutes=5)
                if page.modified_at > (maturity.last_deepened + buffer):
                    triggers.append((
                        SynthesisTrigger.FOUNDATIONAL_SHIFT,
                        f"Foundational concept '{page_name}' was updated"
                    ))

        # 2. Related concept deepened
        related_deepened = self._get_recently_deepened_connections(page)
        if related_deepened:
            triggers.append((
                SynthesisTrigger.RELATED_DEEPENED,
                f"Connected concepts were deepened: {', '.join(related_deepened)}"
            ))

        # 3. Connection threshold
        if maturity.connections.added_since_last_synthesis >= self.connection_threshold:
            triggers.append((
                SynthesisTrigger.CONNECTION_THRESHOLD,
                f"{maturity.connections.added_since_last_synthesis} new connections since last synthesis"
            ))

        # 4. Temporal decay
        days = maturity.days_since_deepening()
        if (days is not None and
            days >= self.days_threshold and
            maturity.connections.incoming >= self.high_connectivity_threshold):
            triggers.append((
                SynthesisTrigger.TEMPORAL_DECAY,
                f"{days} days since deepening with {maturity.connections.incoming} incoming links"
            ))

        if not triggers:
            return None

        # Pick the highest priority trigger
        best_trigger, reason = max(
            triggers,
            key=lambda t: self.TRIGGER_PRIORITIES.get(t[0], 0)
        )

        # Calculate priority score
        priority = self._calculate_priority(page, best_trigger, maturity)

        return DeepeningCandidate(
            page_name=page_name,
            trigger=best_trigger,
            priority=priority,
            reason=reason,
            connections_added=maturity.connections.added_since_last_synthesis,
            days_since_deepening=days,
            related_pages_deepened=related_deepened,
        )

    def _is_foundational_concept(self, page_name: str) -> bool:
        """Check if a page is a core/foundational concept."""
        # Normalize for comparison
        normalized = page_name.replace('_', ' ').replace('-', ' ').lower()
        for concept in FOUNDATIONAL_CONCEPTS:
            if concept.lower() == normalized:
                return True
        return False

    def _get_recently_deepened_connections(self, page) -> List[str]:
        """Get list of recently deepened pages that are connected to this page."""
        if not self._recently_deepened:
            return []

        # Get all connected pages (both incoming and outgoing)
        connected = set(page.link_targets)
        backlinks = self.storage.get_backlinks(page.name)
        connected.update(bl.name for bl in backlinks)

        # Find intersection with recently deepened
        return [name for name in self._recently_deepened if name in connected]

    def _calculate_priority(
        self,
        page,
        trigger: SynthesisTrigger,
        maturity: MaturityState
    ) -> float:
        """
        Calculate priority score for a deepening candidate.

        Factors:
        - Base priority from trigger type
        - Connection density boost
        - Foundational concept boost
        - Age penalty (older = slightly lower priority)
        """
        base = self.TRIGGER_PRIORITIES.get(trigger, 0.5)

        # Connection density boost (0-0.2)
        connection_boost = min(maturity.connections.total / 50, 0.2)

        # Foundational concept boost
        foundational_boost = 0.15 if self._is_foundational_concept(page.name) else 0

        # Age adjustment (recently created pages get slight boost)
        age_adjustment = 0
        if page.created_at:
            days_old = (datetime.now() - page.created_at).days
            if days_old < 7:
                age_adjustment = 0.05  # Newer pages get slight priority

        priority = base + connection_boost + foundational_boost + age_adjustment
        return min(priority, 1.0)  # Cap at 1.0

    def get_foundational_shift_candidates(self) -> List[DeepeningCandidate]:
        """
        Find pages affected by foundational concept changes.

        When a foundational concept is updated, find all pages that
        link to it and mark them as candidates.

        Returns:
            List of candidates triggered by foundational shifts
        """
        candidates = []

        # Check each foundational concept
        for concept in FOUNDATIONAL_CONCEPTS:
            page = self.storage.read(concept)
            if not page:
                continue

            # If the foundational page itself was updated recently
            # Use a 5-minute buffer to avoid false triggers from deepening itself
            if page.modified_at and page.maturity.last_deepened:
                from datetime import timedelta
                buffer = timedelta(minutes=5)
                if page.modified_at > (page.maturity.last_deepened + buffer):
                    # Find all pages that link TO this foundational concept
                    backlinks = self.storage.get_backlinks(page.name)
                    for linked_page in backlinks:
                        candidates.append(DeepeningCandidate(
                            page_name=linked_page.name,
                            trigger=SynthesisTrigger.FOUNDATIONAL_SHIFT,
                            priority=0.85,
                            reason=f"Linked to updated foundational concept '{page.name}'",
                        ))

        return candidates


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
