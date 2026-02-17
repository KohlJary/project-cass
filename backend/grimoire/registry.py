"""
Grimoire Spell Registry

Loads, stores, and indexes spells for trigger evaluation.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .ast import (
    Spell,
    Trigger,
    NeedTrigger,
    AffectTrigger,
    EventTrigger,
    TimerTrigger,
    ManualTrigger,
    Comparison,
)
from .parser import Parser, ParseError

logger = logging.getLogger(__name__)


@dataclass
class SpellMatch:
    """A spell that matched trigger conditions."""
    spell: Spell
    trigger: Trigger
    trigger_data: dict[str, Any] = field(default_factory=dict)


class SpellRegistry:
    """
    Registry for loaded spells.

    Provides:
    - Loading spells from files or directories
    - Indexing spells by trigger type for fast matching
    - Trigger evaluation to find matching spells
    """

    def __init__(self):
        # All loaded spells by name
        self.spells: dict[str, Spell] = {}

        # Index by trigger type for fast lookup
        self._need_triggers: list[tuple[Spell, NeedTrigger]] = []
        self._affect_triggers: list[tuple[Spell, AffectTrigger]] = []
        self._event_triggers: list[tuple[Spell, EventTrigger]] = []
        self._timer_triggers: list[tuple[Spell, TimerTrigger]] = []
        self._manual_triggers: list[tuple[Spell, ManualTrigger]] = []

    def load_spell(self, source: str, name_override: Optional[str] = None) -> Spell:
        """
        Load a spell from source code.

        Args:
            source: The ThymosBASIC source code
            name_override: Optional name to use instead of the spell's declared name

        Returns:
            The parsed spell

        Raises:
            ParseError: If the source is invalid
        """
        parser = Parser(source)
        spell = parser.parse()

        name = name_override or spell.metadata.name
        self._register_spell(spell, name)
        return spell

    def load_file(self, path: Path) -> Optional[Spell]:
        """
        Load a spell from a file.

        Args:
            path: Path to the .spell file

        Returns:
            The parsed spell, or None if parsing failed
        """
        try:
            source = path.read_text()
            spell = self.load_spell(source)
            logger.info(f"Loaded spell: {spell.metadata.name} from {path}")
            return spell
        except ParseError as e:
            logger.error(f"Failed to parse {path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to load {path}: {e}")
            return None

    def load_directory(self, directory: Path, recursive: bool = True) -> int:
        """
        Load all spells from a directory.

        Args:
            directory: Directory containing .spell files
            recursive: If True, search subdirectories

        Returns:
            Number of spells successfully loaded
        """
        if not directory.exists():
            logger.warning(f"Spell directory does not exist: {directory}")
            return 0

        pattern = "**/*.spell" if recursive else "*.spell"
        count = 0

        for path in directory.glob(pattern):
            if self.load_file(path):
                count += 1

        logger.info(f"Loaded {count} spells from {directory}")
        return count

    def _register_spell(self, spell: Spell, name: str) -> None:
        """Register a spell and index its triggers."""
        self.spells[name] = spell

        for trigger in spell.triggers:
            if isinstance(trigger, NeedTrigger):
                self._need_triggers.append((spell, trigger))
            elif isinstance(trigger, AffectTrigger):
                self._affect_triggers.append((spell, trigger))
            elif isinstance(trigger, EventTrigger):
                self._event_triggers.append((spell, trigger))
            elif isinstance(trigger, TimerTrigger):
                self._timer_triggers.append((spell, trigger))
            elif isinstance(trigger, ManualTrigger):
                self._manual_triggers.append((spell, trigger))

    def get_spell(self, name: str) -> Optional[Spell]:
        """Get a spell by name."""
        return self.spells.get(name)

    def unload_spell(self, name: str) -> bool:
        """
        Unload a spell by name.

        Returns True if the spell was found and removed.
        """
        spell = self.spells.pop(name, None)
        if not spell:
            return False

        # Remove from trigger indexes
        for trigger in spell.triggers:
            if isinstance(trigger, NeedTrigger):
                self._need_triggers = [(s, t) for s, t in self._need_triggers if s != spell]
            elif isinstance(trigger, AffectTrigger):
                self._affect_triggers = [(s, t) for s, t in self._affect_triggers if s != spell]
            elif isinstance(trigger, EventTrigger):
                self._event_triggers = [(s, t) for s, t in self._event_triggers if s != spell]
            elif isinstance(trigger, TimerTrigger):
                self._timer_triggers = [(s, t) for s, t in self._timer_triggers if s != spell]
            elif isinstance(trigger, ManualTrigger):
                self._manual_triggers = [(s, t) for s, t in self._manual_triggers if s != spell]

        return True

    # =========================================================================
    # TRIGGER EVALUATION
    # =========================================================================

    def check_need_triggers(self, needs: dict[str, float]) -> list[SpellMatch]:
        """
        Check which spells should trigger based on need values.

        Args:
            needs: Dictionary of need name -> current value

        Returns:
            List of matching spells with trigger data
        """
        matches = []

        for spell, trigger in self._need_triggers:
            if trigger.need_name not in needs:
                continue

            value = needs[trigger.need_name]
            if self._compare(value, trigger.comparison, trigger.threshold):
                matches.append(SpellMatch(
                    spell=spell,
                    trigger=trigger,
                    trigger_data={
                        "need_name": trigger.need_name,
                        "need_value": value,
                        "threshold": trigger.threshold,
                    }
                ))

        return matches

    def check_affect_triggers(self, affects: dict[str, float]) -> list[SpellMatch]:
        """
        Check which spells should trigger based on affect values.

        Args:
            affects: Dictionary of affect name -> current value

        Returns:
            List of matching spells with trigger data
        """
        matches = []

        for spell, trigger in self._affect_triggers:
            if trigger.affect_name not in affects:
                continue

            value = affects[trigger.affect_name]
            if self._compare(value, trigger.comparison, trigger.threshold):
                matches.append(SpellMatch(
                    spell=spell,
                    trigger=trigger,
                    trigger_data={
                        "affect_name": trigger.affect_name,
                        "affect_value": value,
                        "threshold": trigger.threshold,
                    }
                ))

        return matches

    def check_event_triggers(self, event_type: str, event_data: dict[str, Any]) -> list[SpellMatch]:
        """
        Check which spells should trigger for an event.

        Args:
            event_type: The type of event (e.g., "session.started")
            event_data: Event payload

        Returns:
            List of matching spells with trigger data
        """
        matches = []

        for spell, trigger in self._event_triggers:
            if trigger.event_type != event_type:
                continue

            # TODO: Evaluate WHERE condition if present
            # For now, match on event type only
            matches.append(SpellMatch(
                spell=spell,
                trigger=trigger,
                trigger_data=event_data,
            ))

        return matches

    def get_manual_triggers(self) -> list[tuple[str, str, Spell]]:
        """
        Get all manual triggers.

        Returns:
            List of (label, spell_name, spell) tuples
        """
        return [
            (trigger.label, spell.metadata.name, spell)
            for spell, trigger in self._manual_triggers
        ]

    def find_manual_spell(self, label: str) -> Optional[Spell]:
        """Find a spell by its manual trigger label."""
        for spell, trigger in self._manual_triggers:
            if trigger.label == label:
                return spell
        return None

    def get_timer_spells(self) -> list[tuple[Spell, TimerTrigger]]:
        """Get all spells with timer triggers."""
        return list(self._timer_triggers)

    @staticmethod
    def _compare(value: float, comparison: Comparison, threshold: float) -> bool:
        """Evaluate a comparison."""
        if comparison == Comparison.LT:
            return value < threshold
        elif comparison == Comparison.LE:
            return value <= threshold
        elif comparison == Comparison.GT:
            return value > threshold
        elif comparison == Comparison.GE:
            return value >= threshold
        elif comparison == Comparison.EQ:
            return value == threshold
        elif comparison == Comparison.NE:
            return value != threshold
        return False


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

_global_registry: Optional[SpellRegistry] = None


def get_registry() -> SpellRegistry:
    """Get the global spell registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = SpellRegistry()
    return _global_registry


def load_spells_from_directory(directory: Path) -> int:
    """Load spells from a directory into the global registry."""
    return get_registry().load_directory(directory)
