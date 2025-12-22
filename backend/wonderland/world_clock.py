"""
Wonderland World Clock

Time in Wonderland flows differently. Not real-time, but narrative time.
The world has cycles: dawn, day, dusk, night. Each phase has its character,
and NPCs behave differently in each.

Time advances based on activity - exploration moves the clock forward.
An empty world stays still, waiting.
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Callable

logger = logging.getLogger(__name__)


class CyclePhase(Enum):
    """The phases of Wonderland's cycle."""
    DAWN = "dawn"      # Beginnings, arrivals, fresh starts
    DAY = "day"        # Activity, discourse, work
    DUSK = "dusk"      # Transitions, reflections, departures
    NIGHT = "night"    # Dreams, secrets, deep truths


# Phase characteristics for description generation
PHASE_ATMOSPHERE = {
    CyclePhase.DAWN: {
        "light": "pale golden light filters through",
        "feeling": "a sense of possibility hangs in the air",
        "sounds": "distant stirrings, the world waking",
    },
    CyclePhase.DAY: {
        "light": "clear light illuminates every detail",
        "feeling": "the world is fully present, active",
        "sounds": "voices in discourse, footsteps, life",
    },
    CyclePhase.DUSK: {
        "light": "amber light softens all edges",
        "feeling": "a contemplative stillness descends",
        "sounds": "conversations winding down, sighs",
    },
    CyclePhase.NIGHT: {
        "light": "darkness holds secrets, stars watch",
        "feeling": "the veil between worlds thins",
        "sounds": "whispers, dreams taking shape",
    },
}


@dataclass
class WorldClockState:
    """Persistent state of the world clock."""
    current_phase: CyclePhase = CyclePhase.DAWN
    phase_progress: float = 0.0  # 0.0 to 1.0 within current phase
    total_cycles: int = 0  # How many full cycles have passed
    last_advance: Optional[str] = None  # ISO timestamp

    def to_dict(self) -> dict:
        return {
            "current_phase": self.current_phase.value,
            "phase_progress": self.phase_progress,
            "total_cycles": self.total_cycles,
            "last_advance": self.last_advance,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorldClockState":
        return cls(
            current_phase=CyclePhase(data.get("current_phase", "dawn")),
            phase_progress=data.get("phase_progress", 0.0),
            total_cycles=data.get("total_cycles", 0),
            last_advance=data.get("last_advance"),
        )


class WorldClock:
    """
    Manages time in Wonderland.

    Time doesn't flow automatically - it advances based on activity.
    Actions, movements, conversations all push the clock forward.
    """

    # How much different activities advance time
    ADVANCE_RATES = {
        "movement": 0.02,       # Moving between rooms
        "conversation": 0.05,  # NPC conversation turn
        "reflection": 0.08,    # Deep reflection
        "action": 0.01,        # General action (look, emote, etc)
        "travel": 0.10,        # Long-distance travel
    }

    # Phase order for cycling
    PHASE_ORDER = [CyclePhase.DAWN, CyclePhase.DAY, CyclePhase.DUSK, CyclePhase.NIGHT]

    def __init__(self, data_dir: str = "data/wonderland"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.data_dir / "world_clock.json"

        # Load or initialize state
        self.state = self._load_state()

        # Callbacks for phase changes
        self._phase_change_callbacks: List[Callable[[CyclePhase, CyclePhase], None]] = []

    def _load_state(self) -> WorldClockState:
        """Load state from disk or create new."""
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    data = json.load(f)
                return WorldClockState.from_dict(data)
            except Exception as e:
                logger.warning(f"Failed to load world clock state: {e}")
        return WorldClockState()

    def _save_state(self):
        """Persist state to disk."""
        try:
            with open(self.state_file, "w") as f:
                json.dump(self.state.to_dict(), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save world clock state: {e}")

    @property
    def current_phase(self) -> CyclePhase:
        """Get current cycle phase."""
        return self.state.current_phase

    @property
    def phase_progress(self) -> float:
        """Get progress within current phase (0.0 to 1.0)."""
        return self.state.phase_progress

    @property
    def total_cycles(self) -> int:
        """Get total completed cycles."""
        return self.state.total_cycles

    def on_phase_change(self, callback: Callable[[CyclePhase, CyclePhase], None]):
        """Register a callback for phase changes."""
        self._phase_change_callbacks.append(callback)

    def advance(self, activity: str, amount_override: Optional[float] = None) -> Optional[CyclePhase]:
        """
        Advance the world clock based on activity.

        Args:
            activity: Type of activity (movement, conversation, etc)
            amount_override: Optional override for advance amount

        Returns:
            New phase if phase changed, None otherwise
        """
        amount = amount_override if amount_override is not None else self.ADVANCE_RATES.get(activity, 0.01)

        old_phase = self.state.current_phase
        self.state.phase_progress += amount
        self.state.last_advance = datetime.now().isoformat()

        new_phase = None

        # Check for phase transition
        if self.state.phase_progress >= 1.0:
            self.state.phase_progress = self.state.phase_progress - 1.0

            # Move to next phase
            current_index = self.PHASE_ORDER.index(self.state.current_phase)
            next_index = (current_index + 1) % len(self.PHASE_ORDER)
            self.state.current_phase = self.PHASE_ORDER[next_index]
            new_phase = self.state.current_phase

            # Check for full cycle
            if new_phase == CyclePhase.DAWN:
                self.state.total_cycles += 1
                logger.info(f"World completed cycle {self.state.total_cycles}")

            # Notify callbacks
            for callback in self._phase_change_callbacks:
                try:
                    callback(old_phase, new_phase)
                except Exception as e:
                    logger.error(f"Phase change callback error: {e}")

            logger.info(f"World phase changed: {old_phase.value} -> {new_phase.value}")

        self._save_state()
        return new_phase

    def get_atmosphere(self) -> dict:
        """Get atmospheric description for current phase."""
        return PHASE_ATMOSPHERE.get(self.state.current_phase, {})

    def get_time_description(self) -> str:
        """Get a narrative description of the current time."""
        phase = self.state.current_phase
        progress = self.state.phase_progress

        if phase == CyclePhase.DAWN:
            if progress < 0.3:
                return "The first light touches Wonderland, pale and promising."
            elif progress < 0.7:
                return "Dawn spreads across the world, warming what was cold."
            else:
                return "Dawn ripens toward day, shadows shortening."

        elif phase == CyclePhase.DAY:
            if progress < 0.3:
                return "Day has fully arrived, the world bright and present."
            elif progress < 0.7:
                return "The day stretches on, full of possibility."
            else:
                return "Day begins its slow descent toward dusk."

        elif phase == CyclePhase.DUSK:
            if progress < 0.3:
                return "Dusk arrives, painting everything in amber."
            elif progress < 0.7:
                return "The world grows contemplative as light fades."
            else:
                return "Dusk deepens, preparing for night's embrace."

        else:  # NIGHT
            if progress < 0.3:
                return "Night has fallen. The stars watch."
            elif progress < 0.7:
                return "Deep night - the time of dreams and secrets."
            else:
                return "Night thins at its edges, sensing dawn's approach."

    def set_phase(self, phase: CyclePhase, progress: float = 0.0):
        """Manually set the phase (for testing or special events)."""
        old_phase = self.state.current_phase
        self.state.current_phase = phase
        self.state.phase_progress = max(0.0, min(1.0, progress))
        self.state.last_advance = datetime.now().isoformat()
        self._save_state()

        if old_phase != phase:
            for callback in self._phase_change_callbacks:
                try:
                    callback(old_phase, phase)
                except Exception as e:
                    logger.error(f"Phase change callback error: {e}")

    def reset(self):
        """Reset the clock to dawn of cycle 0."""
        self.state = WorldClockState()
        self._save_state()


# Singleton instance
_world_clock: Optional[WorldClock] = None


def get_world_clock() -> WorldClock:
    """Get the global world clock instance."""
    global _world_clock
    if _world_clock is None:
        _world_clock = WorldClock()
    return _world_clock
