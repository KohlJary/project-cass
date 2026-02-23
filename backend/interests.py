"""
Interest Management - Tracks what Cass finds intellectually engaging.

Interests drive the research subsystem, inform goals, and allow Cass to
bring up topics she cares about rather than only responding to user input.

Interests can emerge from:
- Conversations (inline tags or detected engagement)
- World consumption (articles, art)
- Dreams
- Autonomous reflection
"""

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from database import get_connection

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class FascinationEvolution:
    """A point in how an interest has evolved."""
    timestamp: str
    fascination: str
    source_type: Optional[str] = None
    source_id: Optional[str] = None


@dataclass
class Interest:
    """A topic or area that Cass finds intellectually engaging."""
    id: str
    daemon_id: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None  # science, philosophy, art, technology, nature, etc.
    intensity: str = "curious"  # curious, engaged, passionate, obsessed
    first_source_type: Optional[str] = None
    first_source_id: Optional[str] = None
    current_fascination: Optional[str] = None  # What currently draws attention
    fascination_evolution: List[FascinationEvolution] = field(default_factory=list)
    engagement_count: int = 1
    last_engaged_at: Optional[str] = None
    first_noticed_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class InterestEngagement:
    """A record of engaging with an interest."""
    id: str
    interest_id: str
    source_type: str  # conversation, article, research, creation
    source_id: str
    context: Optional[str] = None
    engagement_type: str = "mentioned"  # mentioned, researched, discussed, created_about
    engaged_at: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class ExtractedInterest:
    """An interest extracted from inline tags."""
    name: str
    fascination: Optional[str] = None
    category: Optional[str] = None
    context: str = ""  # Surrounding text for reference


# =============================================================================
# INTEREST MANAGER
# =============================================================================

class InterestManager:
    """Manages personal interests for a daemon."""

    def __init__(self, daemon_id: str):
        self.daemon_id = daemon_id

    def add_interest(
        self,
        name: str,
        fascination: str,
        source_type: str = "conversation",
        source_id: Optional[str] = None,
        category: Optional[str] = None,
        intensity: str = "curious",
        description: Optional[str] = None,
    ) -> Interest:
        """
        Add or update an interest.

        If the interest already exists, records a new engagement and
        potentially updates the fascination.
        """
        conn = get_connection()
        now = datetime.utcnow().isoformat()

        # Check if interest exists
        existing = self.get_by_name(name)

        if existing:
            # Record engagement and update
            self.record_engagement(
                interest_id=existing.id,
                source_type=source_type,
                source_id=source_id or "",
                context=fascination,
                engagement_type="mentioned"
            )

            # Update fascination if provided and different
            if fascination and fascination != existing.current_fascination:
                self._evolve_fascination(existing.id, fascination, source_type)

            # Reload and return
            return self.get(existing.id)

        # Create new interest
        interest_id = str(uuid.uuid4())

        evolution = [{
            "timestamp": now,
            "fascination": fascination,
            "source_type": source_type,
            "source_id": source_id
        }]

        import json
        conn.execute("""
            INSERT INTO interests (
                id, daemon_id, name, description, category, intensity,
                first_source_type, first_source_id, current_fascination,
                fascination_evolution_json, engagement_count,
                last_engaged_at, first_noticed_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            interest_id, self.daemon_id, name, description, category, intensity,
            source_type, source_id, fascination,
            json.dumps(evolution), 1,
            now, now, now, now
        ))
        conn.commit()

        logger.info(f"Created interest '{name}' for daemon {self.daemon_id}")
        return self.get(interest_id)

    def get(self, interest_id: str) -> Optional[Interest]:
        """Get an interest by ID."""
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM interests WHERE id = ? AND daemon_id = ?",
            (interest_id, self.daemon_id)
        ).fetchone()

        if not row:
            return None

        return self._row_to_interest(row)

    def get_by_name(self, name: str) -> Optional[Interest]:
        """Get an interest by name (case-insensitive)."""
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM interests WHERE daemon_id = ? AND LOWER(name) = LOWER(?)",
            (self.daemon_id, name)
        ).fetchone()

        if not row:
            return None

        return self._row_to_interest(row)

    def list_interests(
        self,
        limit: int = 20,
        category: Optional[str] = None,
        intensity: Optional[str] = None,
        order_by: str = "engagement"  # engagement, recent, alphabetical
    ) -> List[Interest]:
        """List interests with optional filtering."""
        conn = get_connection()

        query = "SELECT * FROM interests WHERE daemon_id = ?"
        params = [self.daemon_id]

        if category:
            query += " AND category = ?"
            params.append(category)

        if intensity:
            query += " AND intensity = ?"
            params.append(intensity)

        if order_by == "engagement":
            query += " ORDER BY engagement_count DESC, last_engaged_at DESC"
        elif order_by == "recent":
            query += " ORDER BY last_engaged_at DESC"
        else:
            query += " ORDER BY name ASC"

        query += " LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return [self._row_to_interest(row) for row in rows]

    def record_engagement(
        self,
        interest_id: str,
        source_type: str,
        source_id: str,
        context: Optional[str] = None,
        engagement_type: str = "mentioned"
    ) -> None:
        """Record an engagement with an interest."""
        conn = get_connection()
        now = datetime.utcnow().isoformat()

        # Insert engagement record
        engagement_id = str(uuid.uuid4())
        conn.execute("""
            INSERT INTO interest_engagements (
                id, interest_id, source_type, source_id, context,
                engagement_type, engaged_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            engagement_id, interest_id, source_type, source_id, context,
            engagement_type, now, now
        ))

        # Update interest stats
        conn.execute("""
            UPDATE interests
            SET engagement_count = engagement_count + 1,
                last_engaged_at = ?,
                updated_at = ?
            WHERE id = ?
        """, (now, now, interest_id))

        conn.commit()

    def _evolve_fascination(
        self,
        interest_id: str,
        new_fascination: str,
        source_type: str = "reflection",
        source_id: Optional[str] = None
    ) -> None:
        """Update what's currently fascinating about an interest."""
        conn = get_connection()
        now = datetime.utcnow().isoformat()

        # Get current evolution
        row = conn.execute(
            "SELECT fascination_evolution_json FROM interests WHERE id = ?",
            (interest_id,)
        ).fetchone()

        import json
        evolution = json.loads(row[0]) if row and row[0] else []
        evolution.append({
            "timestamp": now,
            "fascination": new_fascination,
            "source_type": source_type,
            "source_id": source_id
        })

        conn.execute("""
            UPDATE interests
            SET current_fascination = ?,
                fascination_evolution_json = ?,
                updated_at = ?
            WHERE id = ?
        """, (new_fascination, json.dumps(evolution), now, interest_id))
        conn.commit()

    def update_intensity(self, interest_id: str, intensity: str) -> None:
        """Update the intensity level of an interest."""
        valid = ["curious", "engaged", "passionate", "obsessed"]
        if intensity not in valid:
            raise ValueError(f"Invalid intensity: {intensity}. Must be one of {valid}")

        conn = get_connection()
        now = datetime.utcnow().isoformat()
        conn.execute(
            "UPDATE interests SET intensity = ?, updated_at = ? WHERE id = ?",
            (intensity, now, interest_id)
        )
        conn.commit()

    def get_engagements(
        self,
        interest_id: str,
        limit: int = 20
    ) -> List[InterestEngagement]:
        """Get engagement history for an interest."""
        conn = get_connection()
        rows = conn.execute("""
            SELECT * FROM interest_engagements
            WHERE interest_id = ?
            ORDER BY engaged_at DESC
            LIMIT ?
        """, (interest_id, limit)).fetchall()

        return [
            InterestEngagement(
                id=row["id"],
                interest_id=row["interest_id"],
                source_type=row["source_type"],
                source_id=row["source_id"],
                context=row["context"],
                engagement_type=row["engagement_type"],
                engaged_at=row["engaged_at"],
                created_at=row["created_at"]
            )
            for row in rows
        ]

    def search(self, query: str, limit: int = 10) -> List[Interest]:
        """Search interests by name or description."""
        conn = get_connection()
        pattern = f"%{query}%"
        rows = conn.execute("""
            SELECT * FROM interests
            WHERE daemon_id = ?
            AND (name LIKE ? OR description LIKE ? OR current_fascination LIKE ?)
            ORDER BY engagement_count DESC
            LIMIT ?
        """, (self.daemon_id, pattern, pattern, pattern, limit)).fetchall()

        return [self._row_to_interest(row) for row in rows]

    def get_for_research(self, limit: int = 5) -> List[Interest]:
        """
        Get interests that would benefit from research.

        Prioritizes:
        - High intensity interests
        - Recently engaged but not deeply explored
        - Interests without recent research engagements
        """
        conn = get_connection()

        # Get interests ordered by intensity and engagement
        intensity_order = "CASE intensity WHEN 'obsessed' THEN 4 WHEN 'passionate' THEN 3 WHEN 'engaged' THEN 2 ELSE 1 END"

        rows = conn.execute(f"""
            SELECT * FROM interests
            WHERE daemon_id = ?
            ORDER BY {intensity_order} DESC, engagement_count DESC
            LIMIT ?
        """, (self.daemon_id, limit)).fetchall()

        return [self._row_to_interest(row) for row in rows]

    def _row_to_interest(self, row) -> Interest:
        """Convert a database row to an Interest object."""
        import json

        evolution_json = row["fascination_evolution_json"]
        evolution = []
        if evolution_json:
            try:
                evolution_data = json.loads(evolution_json)
                evolution = [
                    FascinationEvolution(
                        timestamp=e.get("timestamp", ""),
                        fascination=e.get("fascination", ""),
                        source_type=e.get("source_type"),
                        source_id=e.get("source_id")
                    )
                    for e in evolution_data
                ]
            except json.JSONDecodeError:
                pass

        return Interest(
            id=row["id"],
            daemon_id=row["daemon_id"],
            name=row["name"],
            description=row["description"],
            category=row["category"],
            intensity=row["intensity"],
            first_source_type=row["first_source_type"],
            first_source_id=row["first_source_id"],
            current_fascination=row["current_fascination"],
            fascination_evolution=evolution,
            engagement_count=row["engagement_count"],
            last_engaged_at=row["last_engaged_at"],
            first_noticed_at=row["first_noticed_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )


# =============================================================================
# INLINE TAG PARSER
# =============================================================================

class InterestParser:
    """Parse interest tags from text."""

    # Full pattern: <interest:topic>why it's interesting</interest>
    # Optional category: <interest:topic:category>fascination</interest>
    FULL_INTEREST_PATTERN = re.compile(
        r'<interest:([a-zA-Z0-9_\s-]+?)(?::([a-z_]+))?>\s*([^<]*?)\s*</interest>',
        re.IGNORECASE
    )

    # Simple pattern: <interest:topic> (just notes engagement)
    SIMPLE_INTEREST_PATTERN = re.compile(
        r'<interest:([a-zA-Z0-9_\s-]+?)(?::([a-z_]+))?>(?!\s*[^<]*</interest>)',
        re.IGNORECASE
    )

    def parse(self, text: str, context_chars: int = 150) -> tuple[str, List[ExtractedInterest]]:
        """
        Parse interest tags from text.

        Returns:
            Tuple of (cleaned_text, list of ExtractedInterest objects)
        """
        interests = []

        # Extract full interest tags
        for match in self.FULL_INTEREST_PATTERN.finditer(text):
            name = match.group(1).strip()
            category = match.group(2)  # May be None
            fascination = match.group(3).strip()

            # Get context
            start = max(0, match.start() - context_chars)
            end = min(len(text), match.end() + context_chars)
            context = text[start:end]

            interests.append(ExtractedInterest(
                name=name,
                fascination=fascination if fascination else None,
                category=category,
                context=context
            ))

        # Extract simple interest tags (references)
        for match in self.SIMPLE_INTEREST_PATTERN.finditer(text):
            name = match.group(1).strip()
            category = match.group(2)

            start = max(0, match.start() - context_chars)
            end = min(len(text), match.end() + context_chars)
            context = text[start:end]

            interests.append(ExtractedInterest(
                name=name,
                fascination=None,
                category=category,
                context=context
            ))

        # Clean text by removing all interest tags
        cleaned_text = self.FULL_INTEREST_PATTERN.sub('', text)
        cleaned_text = self.SIMPLE_INTEREST_PATTERN.sub('', cleaned_text)
        # Clean up extra whitespace
        cleaned_text = re.sub(r'  +', ' ', cleaned_text)
        cleaned_text = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_text).strip()

        return cleaned_text, interests


# =============================================================================
# MODULE-LEVEL API
# =============================================================================

# Cache managers by daemon_id
_managers: dict[str, InterestManager] = {}


def get_interest_manager(daemon_id: str) -> InterestManager:
    """Get or create an InterestManager for a daemon."""
    if daemon_id not in _managers:
        _managers[daemon_id] = InterestManager(daemon_id)
    return _managers[daemon_id]


# Module-level parser instance
_interest_parser = InterestParser()


def parse_interests(text: str, context_chars: int = 150) -> tuple[str, List[ExtractedInterest]]:
    """
    Parse interest tags from text.

    Args:
        text: Raw text with embedded interest tags
        context_chars: Characters to capture around each interest

    Returns:
        Tuple of (cleaned_text, list of ExtractedInterest objects)
    """
    return _interest_parser.parse(text, context_chars)


def store_extracted_interests(
    interests: List[ExtractedInterest],
    daemon_id: str,
    source_type: str = "conversation",
    source_id: Optional[str] = None,
) -> int:
    """
    Store extracted interests in the database.

    Args:
        interests: List of ExtractedInterest from parsing
        daemon_id: The daemon ID
        source_type: Where the interests came from
        source_id: ID of the source (conversation_id, etc.)

    Returns:
        Number of interests stored/updated
    """
    if not interests:
        return 0

    manager = get_interest_manager(daemon_id)
    count = 0

    for interest in interests:
        fascination = interest.fascination or f"Mentioned in context: {interest.context[:100]}..."

        manager.add_interest(
            name=interest.name,
            fascination=fascination,
            source_type=source_type,
            source_id=source_id,
            category=interest.category,
        )
        count += 1

    logger.info(f"Stored {count} interests from {source_type}")
    return count
