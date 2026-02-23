"""
Symbol Manager - Personal symbols/motifs with significance.

Symbols are images, concepts, or motifs that hold personal meaning for the daemon.
They can emerge from dreams, world consumption (articles, art), or conversations.

This system tracks:
- Symbol definitions and meanings
- Where symbols appear (dreams, articles, conversations)
- How meaning evolves over time
- Emotional charge and significance
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

from database import get_db, json_serialize, json_deserialize

logger = logging.getLogger(__name__)


@dataclass
class MeaningEvolution:
    """A snapshot of symbol meaning at a point in time."""
    timestamp: str
    meaning: str
    source_type: Optional[str] = None  # What prompted the evolution
    source_id: Optional[str] = None
    confidence: float = 0.7


@dataclass
class SymbolAppearance:
    """Record of where a symbol appeared."""
    id: str
    symbol_id: str
    source_type: str  # dream, article, art_study, conversation
    source_id: str
    context: Optional[str] = None
    meaning_in_context: Optional[str] = None
    appeared_at: str = ""
    created_at: str = ""


@dataclass
class Symbol:
    """A personal symbol with meaning and history."""
    id: str
    daemon_id: str
    name: str
    description: Optional[str] = None
    emotional_charge: str = "ambivalent"  # positive, negative, ambivalent, transformative
    confidence: float = 0.7
    first_source_type: Optional[str] = None
    first_source_id: Optional[str] = None
    current_meaning: Optional[str] = None
    meaning_evolution: List[MeaningEvolution] = field(default_factory=list)
    appearance_count: int = 1
    first_noticed_at: str = ""
    last_appeared_at: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "daemon_id": self.daemon_id,
            "name": self.name,
            "description": self.description,
            "emotional_charge": self.emotional_charge,
            "confidence": self.confidence,
            "first_source_type": self.first_source_type,
            "first_source_id": self.first_source_id,
            "current_meaning": self.current_meaning,
            "meaning_evolution": [
                {
                    "timestamp": m.timestamp,
                    "meaning": m.meaning,
                    "source_type": m.source_type,
                    "source_id": m.source_id,
                    "confidence": m.confidence,
                }
                for m in self.meaning_evolution
            ],
            "appearance_count": self.appearance_count,
            "first_noticed_at": self.first_noticed_at,
            "last_appeared_at": self.last_appeared_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row: tuple) -> "Symbol":
        """Create Symbol from database row."""
        (
            id_, daemon_id, name, description, emotional_charge, confidence,
            first_source_type, first_source_id, current_meaning,
            meaning_evolution_json, appearance_count,
            first_noticed_at, last_appeared_at, created_at, updated_at
        ) = row

        meaning_evolution = []
        if meaning_evolution_json:
            raw = json_deserialize(meaning_evolution_json)
            for m in raw:
                meaning_evolution.append(MeaningEvolution(
                    timestamp=m.get("timestamp", ""),
                    meaning=m.get("meaning", ""),
                    source_type=m.get("source_type"),
                    source_id=m.get("source_id"),
                    confidence=m.get("confidence", 0.7),
                ))

        return cls(
            id=id_,
            daemon_id=daemon_id,
            name=name,
            description=description,
            emotional_charge=emotional_charge or "ambivalent",
            confidence=confidence or 0.7,
            first_source_type=first_source_type,
            first_source_id=first_source_id,
            current_meaning=current_meaning,
            meaning_evolution=meaning_evolution,
            appearance_count=appearance_count or 1,
            first_noticed_at=first_noticed_at or "",
            last_appeared_at=last_appeared_at or "",
            created_at=created_at or "",
            updated_at=updated_at or "",
        )


class SymbolManager:
    """
    Manages personal symbols for a daemon.

    Symbols are motifs, images, or concepts with personal significance.
    They can come from dreams, articles, art study, or conversations.
    """

    def __init__(self, daemon_id: str):
        self._daemon_id = daemon_id

    def add_symbol(
        self,
        name: str,
        meaning: str,
        source_type: str = "conversation",
        source_id: Optional[str] = None,
        description: Optional[str] = None,
        emotional_charge: str = "ambivalent",
        confidence: float = 0.7,
    ) -> Symbol:
        """
        Add a new symbol or update an existing one.

        If a symbol with the same name already exists, records a new appearance
        and potentially updates the meaning.
        """
        now = datetime.now().isoformat()

        # Check if symbol already exists
        existing = self.get_by_name(name)
        if existing:
            # Record new appearance
            self.record_appearance(
                symbol_id=existing.id,
                source_type=source_type,
                source_id=source_id or "",
                context=f"Symbol reappeared with meaning: {meaning}",
                meaning_in_context=meaning,
            )

            # If meaning differs, evolve it
            if meaning != existing.current_meaning:
                self.evolve_meaning(
                    symbol_id=existing.id,
                    new_meaning=meaning,
                    source_type=source_type,
                    source_id=source_id,
                    confidence=confidence,
                )

            return self.get(existing.id)

        # Create new symbol
        symbol_id = str(uuid4())
        initial_evolution = [{
            "timestamp": now,
            "meaning": meaning,
            "source_type": source_type,
            "source_id": source_id,
            "confidence": confidence,
        }]

        with get_db() as conn:
            conn.execute("""
                INSERT INTO symbols (
                    id, daemon_id, name, description, emotional_charge, confidence,
                    first_source_type, first_source_id, current_meaning,
                    meaning_evolution_json, appearance_count,
                    first_noticed_at, last_appeared_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                symbol_id, self._daemon_id, name, description, emotional_charge,
                confidence, source_type, source_id, meaning,
                json_serialize(initial_evolution), 1,
                now, now, now, now
            ))

            # Record first appearance
            appearance_id = str(uuid4())
            conn.execute("""
                INSERT INTO symbol_appearances (
                    id, symbol_id, source_type, source_id, context,
                    meaning_in_context, appeared_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                appearance_id, symbol_id, source_type, source_id or "",
                f"First noticed: {description or meaning}",
                meaning, now, now
            ))

        logger.info(f"Created new symbol: {name} ({symbol_id})")
        return self.get(symbol_id)

    def get(self, symbol_id: str) -> Optional[Symbol]:
        """Get a symbol by ID."""
        with get_db() as conn:
            row = conn.execute("""
                SELECT id, daemon_id, name, description, emotional_charge, confidence,
                       first_source_type, first_source_id, current_meaning,
                       meaning_evolution_json, appearance_count,
                       first_noticed_at, last_appeared_at, created_at, updated_at
                FROM symbols
                WHERE id = ? AND daemon_id = ?
            """, (symbol_id, self._daemon_id)).fetchone()

            if row:
                return Symbol.from_row(row)
            return None

    def get_by_name(self, name: str) -> Optional[Symbol]:
        """Get a symbol by name (case-insensitive)."""
        with get_db() as conn:
            row = conn.execute("""
                SELECT id, daemon_id, name, description, emotional_charge, confidence,
                       first_source_type, first_source_id, current_meaning,
                       meaning_evolution_json, appearance_count,
                       first_noticed_at, last_appeared_at, created_at, updated_at
                FROM symbols
                WHERE daemon_id = ? AND LOWER(name) = LOWER(?)
            """, (self._daemon_id, name)).fetchone()

            if row:
                return Symbol.from_row(row)
            return None

    def list_symbols(
        self,
        limit: int = 20,
        emotional_charge: Optional[str] = None,
        order_by: str = "last_appeared_at",
    ) -> List[Symbol]:
        """List symbols with optional filtering."""
        query = """
            SELECT id, daemon_id, name, description, emotional_charge, confidence,
                   first_source_type, first_source_id, current_meaning,
                   meaning_evolution_json, appearance_count,
                   first_noticed_at, last_appeared_at, created_at, updated_at
            FROM symbols
            WHERE daemon_id = ?
        """
        params = [self._daemon_id]

        if emotional_charge:
            query += " AND emotional_charge = ?"
            params.append(emotional_charge)

        # Validate order_by to prevent SQL injection
        valid_orders = ["last_appeared_at", "first_noticed_at", "appearance_count", "name"]
        if order_by not in valid_orders:
            order_by = "last_appeared_at"

        query += f" ORDER BY {order_by} DESC LIMIT ?"
        params.append(limit)

        with get_db() as conn:
            rows = conn.execute(query, params).fetchall()
            return [Symbol.from_row(row) for row in rows]

    def record_appearance(
        self,
        symbol_id: str,
        source_type: str,
        source_id: str,
        context: Optional[str] = None,
        meaning_in_context: Optional[str] = None,
    ) -> None:
        """Record a new appearance of a symbol."""
        now = datetime.now().isoformat()
        appearance_id = str(uuid4())

        with get_db() as conn:
            # Insert appearance record
            conn.execute("""
                INSERT INTO symbol_appearances (
                    id, symbol_id, source_type, source_id, context,
                    meaning_in_context, appeared_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                appearance_id, symbol_id, source_type, source_id,
                context, meaning_in_context, now, now
            ))

            # Update symbol's appearance count and last_appeared_at
            conn.execute("""
                UPDATE symbols
                SET appearance_count = appearance_count + 1,
                    last_appeared_at = ?,
                    updated_at = ?
                WHERE id = ?
            """, (now, now, symbol_id))

        logger.debug(f"Recorded appearance of symbol {symbol_id} in {source_type}:{source_id}")

    def evolve_meaning(
        self,
        symbol_id: str,
        new_meaning: str,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        confidence: float = 0.7,
    ) -> Optional[Symbol]:
        """
        Add a new meaning to a symbol's evolution history.

        This doesn't replace the meaning - it adds to the symbol's journey.
        """
        now = datetime.now().isoformat()

        symbol = self.get(symbol_id)
        if not symbol:
            return None

        # Add to evolution
        new_evolution = MeaningEvolution(
            timestamp=now,
            meaning=new_meaning,
            source_type=source_type,
            source_id=source_id,
            confidence=confidence,
        )
        symbol.meaning_evolution.append(new_evolution)

        evolution_json = json_serialize([
            {
                "timestamp": m.timestamp,
                "meaning": m.meaning,
                "source_type": m.source_type,
                "source_id": m.source_id,
                "confidence": m.confidence,
            }
            for m in symbol.meaning_evolution
        ])

        with get_db() as conn:
            conn.execute("""
                UPDATE symbols
                SET current_meaning = ?,
                    meaning_evolution_json = ?,
                    confidence = ?,
                    updated_at = ?
                WHERE id = ?
            """, (new_meaning, evolution_json, confidence, now, symbol_id))

        logger.info(f"Evolved meaning of symbol {symbol_id}: {new_meaning}")
        return self.get(symbol_id)

    def get_appearances(self, symbol_id: str, limit: int = 20) -> List[SymbolAppearance]:
        """Get all appearances of a symbol."""
        with get_db() as conn:
            rows = conn.execute("""
                SELECT id, symbol_id, source_type, source_id, context,
                       meaning_in_context, appeared_at, created_at
                FROM symbol_appearances
                WHERE symbol_id = ?
                ORDER BY appeared_at DESC
                LIMIT ?
            """, (symbol_id, limit)).fetchall()

            return [
                SymbolAppearance(
                    id=row[0],
                    symbol_id=row[1],
                    source_type=row[2],
                    source_id=row[3],
                    context=row[4],
                    meaning_in_context=row[5],
                    appeared_at=row[6],
                    created_at=row[7],
                )
                for row in rows
            ]

    def search(self, query: str, limit: int = 10) -> List[Symbol]:
        """Search symbols by name or meaning."""
        query_lower = f"%{query.lower()}%"

        with get_db() as conn:
            rows = conn.execute("""
                SELECT id, daemon_id, name, description, emotional_charge, confidence,
                       first_source_type, first_source_id, current_meaning,
                       meaning_evolution_json, appearance_count,
                       first_noticed_at, last_appeared_at, created_at, updated_at
                FROM symbols
                WHERE daemon_id = ?
                  AND (LOWER(name) LIKE ? OR LOWER(current_meaning) LIKE ?
                       OR LOWER(description) LIKE ?)
                ORDER BY appearance_count DESC
                LIMIT ?
            """, (self._daemon_id, query_lower, query_lower, query_lower, limit)).fetchall()

            return [Symbol.from_row(row) for row in rows]

    def integrate_dream_symbols(
        self,
        dream_id: str,
        symbols: List[Dict],
    ) -> List[Symbol]:
        """
        Integrate symbols extracted from a dream.

        Args:
            dream_id: ID of the dream
            symbols: List of dicts with 'symbol', 'meaning', 'emotional_charge'

        Returns:
            List of created/updated Symbol objects
        """
        results = []
        for sym_data in symbols:
            name = sym_data.get("symbol", "").strip()
            if not name:
                continue

            meaning = sym_data.get("meaning", "")
            charge = sym_data.get("emotional_charge", "ambivalent")

            # Normalize charge values
            charge_map = {
                "positive": "positive",
                "negative": "negative",
                "neutral": "ambivalent",
                "ambivalent": "ambivalent",
                "transformative": "transformative",
                "mixed": "ambivalent",
            }
            charge = charge_map.get(charge.lower(), "ambivalent")

            symbol = self.add_symbol(
                name=name,
                meaning=meaning,
                source_type="dream",
                source_id=dream_id,
                emotional_charge=charge,
                confidence=0.7,
            )
            results.append(symbol)

        logger.info(f"Integrated {len(results)} symbols from dream {dream_id}")
        return results

    def delete_symbol(self, symbol_id: str) -> bool:
        """Delete a symbol and its appearances."""
        with get_db() as conn:
            # Delete appearances first (or rely on CASCADE)
            conn.execute("DELETE FROM symbol_appearances WHERE symbol_id = ?", (symbol_id,))
            result = conn.execute("DELETE FROM symbols WHERE id = ? AND daemon_id = ?",
                                  (symbol_id, self._daemon_id))
            return result.rowcount > 0


# Module-level singleton pattern
_managers: Dict[str, SymbolManager] = {}


def get_symbol_manager(daemon_id: str) -> SymbolManager:
    """Get or create a SymbolManager for a daemon."""
    if daemon_id not in _managers:
        _managers[daemon_id] = SymbolManager(daemon_id)
    return _managers[daemon_id]


# =============================================================================
# INLINE SYMBOL TAG PARSING
# =============================================================================

import re

@dataclass
class ExtractedSymbol:
    """A symbol extracted from inline tags."""
    name: str
    meaning: Optional[str]
    charge: Optional[str]  # Optional emotional charge hint
    context: str  # Surrounding text
    position: int


class SymbolParser:
    """
    Parses symbol tags from text.

    Supports formats:
    - <symbol:name>meaning</symbol>  - Full format with meaning
    - <symbol:name:charge>meaning</symbol>  - With emotional charge
    - <symbol:name>  - Simple format (just noting appearance)

    Examples:
    - <symbol:wings>freedom and transcendence</symbol>
    - <symbol:labyrinth:transformative>the journey inward</symbol>
    - <symbol:mirror>
    """

    # Full pattern: <symbol:name>meaning</symbol> or <symbol:name:charge>meaning</symbol>
    FULL_SYMBOL_PATTERN = re.compile(
        r'<symbol:([a-zA-Z0-9_-]+)(?::([a-z]+))?>\s*([^<]*?)\s*</symbol>',
        re.IGNORECASE
    )

    # Simple pattern: <symbol:name> not followed by content and </symbol>
    SIMPLE_SYMBOL_PATTERN = re.compile(
        r'<symbol:([a-zA-Z0-9_-]+)(?::([a-z]+))?>(?!\s*[^<]*</symbol>)',
        re.IGNORECASE
    )

    # Pattern to remove full symbol tags
    FULL_SYMBOL_TAG_PATTERN = re.compile(
        r'<symbol:[a-zA-Z0-9_-]+(?::[a-z]+)?>[^<]*</symbol>',
        re.IGNORECASE
    )

    # Pattern to remove simple symbol tags
    SIMPLE_SYMBOL_TAG_PATTERN = re.compile(
        r'<symbol:[a-zA-Z0-9_-]+(?::[a-z]+)?>(?!\s*[^<]*</symbol>)',
        re.IGNORECASE
    )

    def parse(
        self,
        text: str,
        context_chars: int = 150
    ) -> tuple[str, List[ExtractedSymbol]]:
        """
        Parse text and extract symbol tags.

        Args:
            text: Raw text with embedded symbol tags
            context_chars: Characters to capture around each symbol

        Returns:
            Tuple of (cleaned_text, list of ExtractedSymbol objects)
        """
        symbols = []

        # First, find full symbols with meanings
        for match in self.FULL_SYMBOL_PATTERN.finditer(text):
            name = match.group(1).strip()
            charge = match.group(2)  # May be None
            meaning = match.group(3).strip() or None

            # Extract context
            start_pos = max(0, match.start() - context_chars // 2)
            end_pos = min(len(text), match.end() + context_chars // 2)
            context = text[start_pos:end_pos]
            # Remove symbol tags from context
            context = self.FULL_SYMBOL_TAG_PATTERN.sub('', context)
            context = self.SIMPLE_SYMBOL_TAG_PATTERN.sub('', context).strip()

            symbols.append(ExtractedSymbol(
                name=name,
                meaning=meaning,
                charge=charge,
                context=context[:300],
                position=match.start()
            ))

        # Find simple symbols (not already captured)
        full_positions = {s.position for s in symbols}
        for match in self.SIMPLE_SYMBOL_PATTERN.finditer(text):
            if match.start() in full_positions:
                continue

            name = match.group(1).strip()
            charge = match.group(2)

            # Extract context
            start_pos = max(0, match.start() - context_chars // 2)
            end_pos = min(len(text), match.end() + context_chars // 2)
            context = text[start_pos:end_pos]
            context = self.FULL_SYMBOL_TAG_PATTERN.sub('', context)
            context = self.SIMPLE_SYMBOL_TAG_PATTERN.sub('', context).strip()

            symbols.append(ExtractedSymbol(
                name=name,
                meaning=None,
                charge=charge,
                context=context[:300],
                position=match.start()
            ))

        # Sort by position
        symbols.sort(key=lambda s: s.position)

        # Remove symbol tags from text
        cleaned_text = self.FULL_SYMBOL_TAG_PATTERN.sub('', text)
        cleaned_text = self.SIMPLE_SYMBOL_TAG_PATTERN.sub('', cleaned_text)
        # Clean up extra whitespace
        cleaned_text = re.sub(r'  +', ' ', cleaned_text)
        cleaned_text = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_text).strip()

        return cleaned_text, symbols


# Module-level parser instance
_symbol_parser = SymbolParser()


def parse_symbols(text: str, context_chars: int = 150) -> tuple[str, List[ExtractedSymbol]]:
    """
    Parse symbol tags from text.

    Args:
        text: Raw text with embedded symbol tags
        context_chars: Characters to capture around each symbol

    Returns:
        Tuple of (cleaned_text, list of ExtractedSymbol objects)
    """
    return _symbol_parser.parse(text, context_chars)


def store_extracted_symbols(
    symbols: List[ExtractedSymbol],
    daemon_id: str,
    source_type: str = "conversation",
    source_id: Optional[str] = None,
) -> int:
    """
    Store extracted symbols in the database.

    Args:
        symbols: List of ExtractedSymbol from parsing
        daemon_id: The daemon ID
        source_type: Where the symbols came from
        source_id: ID of the source (conversation_id, etc.)

    Returns:
        Number of symbols stored/updated
    """
    if not symbols:
        return 0

    manager = get_symbol_manager(daemon_id)
    count = 0

    for sym in symbols:
        meaning = sym.meaning or f"Appeared in context: {sym.context[:100]}..."
        charge = sym.charge or "ambivalent"

        # Normalize charge
        charge_map = {
            "positive": "positive",
            "negative": "negative",
            "ambivalent": "ambivalent",
            "transformative": "transformative",
            "neutral": "ambivalent",
        }
        charge = charge_map.get(charge.lower(), "ambivalent")

        manager.add_symbol(
            name=sym.name,
            meaning=meaning,
            source_type=source_type,
            source_id=source_id,
            emotional_charge=charge,
        )
        count += 1

    logger.info(f"Stored {count} symbols from {source_type}")
    return count
