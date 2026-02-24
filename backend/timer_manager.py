"""
Timer Manager - Countdown timers with Home Assistant integration.

Supports:
- Home Assistant timer entities (if HA is configured)
- Local asyncio timers (fallback)
- Push notifications on timer completion
- Persistence across restarts
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, List, Callable, Awaitable, Any

from database import get_db
from home_assistant import get_ha_client
from relay_client import get_relay_client

logger = logging.getLogger(__name__)


class TimerStatus(str, Enum):
    """Status of a timer."""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TimerSource(str, Enum):
    """Where the timer is running."""
    LOCAL = "local"
    HOME_ASSISTANT = "ha"


@dataclass
class Timer:
    """A countdown timer."""
    id: str
    daemon_id: str
    user_id: str
    label: str
    duration_seconds: int
    started_at: datetime
    ends_at: datetime
    status: TimerStatus = TimerStatus.ACTIVE
    source: TimerSource = TimerSource.LOCAL
    ha_entity_id: Optional[str] = None  # For HA timers
    remaining_seconds: Optional[int] = None  # For paused timers
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "daemon_id": self.daemon_id,
            "user_id": self.user_id,
            "label": self.label,
            "duration_seconds": self.duration_seconds,
            "started_at": self.started_at.isoformat(),
            "ends_at": self.ends_at.isoformat(),
            "status": self.status.value,
            "source": self.source.value,
            "ha_entity_id": self.ha_entity_id,
            "remaining_seconds": self.remaining_seconds,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Timer":
        """Deserialize from dictionary."""
        return cls(
            id=data["id"],
            daemon_id=data["daemon_id"],
            user_id=data["user_id"],
            label=data["label"],
            duration_seconds=data["duration_seconds"],
            started_at=datetime.fromisoformat(data["started_at"]),
            ends_at=datetime.fromisoformat(data["ends_at"]),
            status=TimerStatus(data.get("status", "active")),
            source=TimerSource(data.get("source", "local")),
            ha_entity_id=data.get("ha_entity_id"),
            remaining_seconds=data.get("remaining_seconds"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
        )

    @property
    def time_remaining(self) -> timedelta:
        """Get time remaining on this timer."""
        if self.status == TimerStatus.PAUSED:
            return timedelta(seconds=self.remaining_seconds or 0)
        elif self.status == TimerStatus.ACTIVE:
            remaining = self.ends_at - datetime.now()
            return max(remaining, timedelta(0))
        else:
            return timedelta(0)

    @property
    def is_expired(self) -> bool:
        """Check if timer has expired."""
        return self.status == TimerStatus.ACTIVE and datetime.now() >= self.ends_at

    def format_duration(self) -> str:
        """Format duration for display."""
        return _format_duration(self.duration_seconds)

    def format_remaining(self) -> str:
        """Format remaining time for display."""
        return _format_duration(int(self.time_remaining.total_seconds()))


def _format_duration(seconds: int) -> str:
    """Format seconds as human-readable duration."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        mins = seconds // 60
        secs = seconds % 60
        if secs:
            return f"{mins}m {secs}s"
        return f"{mins}m"
    else:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        if mins:
            return f"{hours}h {mins}m"
        return f"{hours}h"


def parse_duration(duration_str: str) -> int:
    """
    Parse a duration string to seconds.

    Supports formats:
    - "30" or "30s" -> 30 seconds
    - "5m" or "5 minutes" -> 300 seconds
    - "1h" or "1 hour" -> 3600 seconds
    - "1h 30m" or "1:30" -> 5400 seconds
    """
    import re

    duration_str = duration_str.strip().lower()

    # Try HH:MM:SS or MM:SS format
    if ":" in duration_str:
        parts = duration_str.split(":")
        if len(parts) == 2:
            mins, secs = int(parts[0]), int(parts[1])
            return mins * 60 + secs
        elif len(parts) == 3:
            hours, mins, secs = int(parts[0]), int(parts[1]), int(parts[2])
            return hours * 3600 + mins * 60 + secs

    # Try combined format like "1h 30m"
    total = 0
    pattern = r'(\d+)\s*(h|hour|hours|m|min|mins|minutes|s|sec|secs|seconds)?'
    matches = re.findall(pattern, duration_str)

    if not matches:
        # Try plain number (assume seconds)
        try:
            return int(duration_str)
        except ValueError:
            raise ValueError(f"Cannot parse duration: {duration_str}")

    for value, unit in matches:
        value = int(value)
        if unit in ('h', 'hour', 'hours'):
            total += value * 3600
        elif unit in ('m', 'min', 'mins', 'minutes'):
            total += value * 60
        else:  # seconds or no unit
            total += value

    return total


class TimerManager:
    """
    Manages countdown timers.

    Prefers Home Assistant timer entities when available,
    falls back to local asyncio timers.
    """

    def __init__(self, daemon_id: str):
        self._daemon_id = daemon_id
        self._ha_client = get_ha_client()
        self._local_tasks: Dict[str, asyncio.Task] = {}
        self._completion_callbacks: List[Callable[[Timer], Awaitable[None]]] = []
        self._initialized = False

    @property
    def use_ha(self) -> bool:
        """Check if we should use Home Assistant timers."""
        return self._ha_client.is_configured

    def on_timer_complete(self, callback: Callable[[Timer], Awaitable[None]]) -> None:
        """Register a callback for timer completion."""
        self._completion_callbacks.append(callback)

    async def initialize(self) -> None:
        """Initialize the timer manager and restore active timers."""
        if self._initialized:
            return

        # Restore active local timers from database
        active_timers = self._load_active_timers()
        for timer in active_timers:
            if timer.source == TimerSource.LOCAL and timer.status == TimerStatus.ACTIVE:
                # Restart local timer tasks
                remaining = (timer.ends_at - datetime.now()).total_seconds()
                if remaining > 0:
                    self._start_local_timer_task(timer, remaining)
                else:
                    # Timer expired while we were down
                    await self._complete_timer(timer)

        self._initialized = True
        logger.info(f"TimerManager initialized with {len(active_timers)} active timers")

    # =========================================================================
    # Timer CRUD
    # =========================================================================

    async def create_timer(
        self,
        user_id: str,
        duration_seconds: int,
        label: str = "Timer",
    ) -> Timer:
        """
        Create and start a new timer.

        Args:
            user_id: User who owns this timer
            duration_seconds: Timer duration
            label: Display name for the timer

        Returns:
            Created Timer object
        """
        timer_id = str(uuid.uuid4())[:8]
        now = datetime.now()
        ends_at = now + timedelta(seconds=duration_seconds)

        timer = Timer(
            id=timer_id,
            daemon_id=self._daemon_id,
            user_id=user_id,
            label=label,
            duration_seconds=duration_seconds,
            started_at=now,
            ends_at=ends_at,
            status=TimerStatus.ACTIVE,
            created_at=now,
        )

        # Try HA first if available
        if self.use_ha:
            ha_entity = await self._create_ha_timer(timer)
            if ha_entity:
                timer.source = TimerSource.HOME_ASSISTANT
                timer.ha_entity_id = ha_entity
            else:
                # Fall back to local
                timer.source = TimerSource.LOCAL
                self._start_local_timer_task(timer, duration_seconds)
        else:
            timer.source = TimerSource.LOCAL
            self._start_local_timer_task(timer, duration_seconds)

        # Persist to database
        self._save_timer(timer)

        logger.info(f"Created timer {timer_id}: {label} for {_format_duration(duration_seconds)} ({timer.source.value})")
        return timer

    async def cancel_timer(self, timer_id: str, user_id: str) -> Optional[Timer]:
        """
        Cancel an active timer.

        Args:
            timer_id: Timer to cancel
            user_id: Must match timer owner

        Returns:
            Cancelled Timer or None if not found
        """
        timer = self.get_timer(timer_id, user_id)
        if not timer:
            return None

        if timer.status != TimerStatus.ACTIVE:
            return timer  # Already not active

        # Cancel based on source
        if timer.source == TimerSource.HOME_ASSISTANT and timer.ha_entity_id:
            await self._cancel_ha_timer(timer.ha_entity_id)
        elif timer.source == TimerSource.LOCAL:
            task = self._local_tasks.pop(timer_id, None)
            if task:
                task.cancel()

        timer.status = TimerStatus.CANCELLED
        self._save_timer(timer)

        logger.info(f"Cancelled timer {timer_id}")
        return timer

    async def pause_timer(self, timer_id: str, user_id: str) -> Optional[Timer]:
        """
        Pause an active timer.

        Note: Only supported for HA timers. Local timers cannot be paused.

        Args:
            timer_id: Timer to pause
            user_id: Must match timer owner

        Returns:
            Paused Timer or None if not found/not pausable
        """
        timer = self.get_timer(timer_id, user_id)
        if not timer or timer.status != TimerStatus.ACTIVE:
            return None

        if timer.source == TimerSource.HOME_ASSISTANT and timer.ha_entity_id:
            result = await self._ha_client.call_service(
                "timer", "pause", timer.ha_entity_id
            )
            if result.get("success"):
                timer.status = TimerStatus.PAUSED
                timer.remaining_seconds = int(timer.time_remaining.total_seconds())
                self._save_timer(timer)
                logger.info(f"Paused timer {timer_id}")
                return timer
        else:
            logger.warning(f"Cannot pause local timer {timer_id}")

        return None

    async def resume_timer(self, timer_id: str, user_id: str) -> Optional[Timer]:
        """
        Resume a paused timer.

        Args:
            timer_id: Timer to resume
            user_id: Must match timer owner

        Returns:
            Resumed Timer or None if not found/not paused
        """
        timer = self.get_timer(timer_id, user_id)
        if not timer or timer.status != TimerStatus.PAUSED:
            return None

        if timer.source == TimerSource.HOME_ASSISTANT and timer.ha_entity_id:
            result = await self._ha_client.call_service(
                "timer", "start", timer.ha_entity_id
            )
            if result.get("success"):
                timer.status = TimerStatus.ACTIVE
                timer.ends_at = datetime.now() + timedelta(seconds=timer.remaining_seconds or 0)
                timer.remaining_seconds = None
                self._save_timer(timer)
                logger.info(f"Resumed timer {timer_id}")
                return timer

        return None

    def get_timer(self, timer_id: str, user_id: str) -> Optional[Timer]:
        """Get a specific timer by ID."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM timers
                WHERE id = ? AND daemon_id = ? AND user_id = ?
            """, (timer_id, self._daemon_id, user_id))
            row = cursor.fetchone()
            if row:
                return self._row_to_timer(dict(row))
        return None

    def list_timers(
        self,
        user_id: str,
        include_completed: bool = False,
    ) -> List[Timer]:
        """
        List timers for a user.

        Args:
            user_id: User to list timers for
            include_completed: Whether to include completed/cancelled timers

        Returns:
            List of Timer objects
        """
        query = """
            SELECT * FROM timers
            WHERE daemon_id = ? AND user_id = ?
        """
        params = [self._daemon_id, user_id]

        if not include_completed:
            query += " AND status IN ('active', 'paused')"

        query += " ORDER BY ends_at"

        with get_db() as conn:
            cursor = conn.execute(query, params)
            return [self._row_to_timer(dict(row)) for row in cursor.fetchall()]

    # =========================================================================
    # Home Assistant Integration
    # =========================================================================

    async def _create_ha_timer(self, timer: Timer) -> Optional[str]:
        """
        Create a Home Assistant timer entity.

        Returns the entity_id if successful, None otherwise.
        """
        try:
            # HA timer.start creates a timer if it doesn't exist
            # But we need an existing timer entity or use input_number
            # For now, we'll use local timers and just monitor HA timer events

            # Check if we have a dedicated timer entity
            # Format: timer.cass_timer_<id>
            # This requires the timer entity to exist in HA config

            # For now, fall back to local - HA timer entity management
            # requires config flow or yaml configuration
            logger.debug("HA timer entity creation not implemented, using local")
            return None

        except Exception as e:
            logger.error(f"Failed to create HA timer: {e}")
            return None

    async def _cancel_ha_timer(self, entity_id: str) -> bool:
        """Cancel a Home Assistant timer."""
        try:
            result = await self._ha_client.call_service(
                "timer", "cancel", entity_id
            )
            return result.get("success", False)
        except Exception as e:
            logger.error(f"Failed to cancel HA timer {entity_id}: {e}")
            return False

    async def handle_ha_timer_finished(self, entity_id: str) -> None:
        """
        Handle a Home Assistant timer.finished event.

        Called when an HA timer completes.
        """
        # Find timer by entity_id
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM timers
                WHERE daemon_id = ? AND ha_entity_id = ? AND status = 'active'
            """, (self._daemon_id, entity_id))
            row = cursor.fetchone()
            if row:
                timer = self._row_to_timer(dict(row))
                await self._complete_timer(timer)

    # =========================================================================
    # Local Timer Implementation
    # =========================================================================

    def _start_local_timer_task(self, timer: Timer, duration: float) -> None:
        """Start an asyncio task for a local timer."""
        task = asyncio.create_task(self._local_timer_task(timer, duration))
        self._local_tasks[timer.id] = task

    async def _local_timer_task(self, timer: Timer, duration: float) -> None:
        """Asyncio task that waits for timer completion."""
        try:
            await asyncio.sleep(duration)
            # Timer completed
            await self._complete_timer(timer)
        except asyncio.CancelledError:
            logger.debug(f"Local timer {timer.id} was cancelled")
        except Exception as e:
            logger.error(f"Error in local timer {timer.id}: {e}")

    # =========================================================================
    # Timer Completion
    # =========================================================================

    async def _complete_timer(self, timer: Timer) -> None:
        """Handle timer completion."""
        # Update status
        timer.status = TimerStatus.COMPLETED
        self._save_timer(timer)

        # Remove from local tasks if present
        self._local_tasks.pop(timer.id, None)

        logger.info(f"Timer {timer.id} completed: {timer.label}")

        # Notify callbacks
        for callback in self._completion_callbacks:
            try:
                await callback(timer)
            except Exception as e:
                logger.error(f"Error in timer completion callback: {e}")

        # Send push notification
        await self._send_timer_notification(timer)

    async def _send_timer_notification(self, timer: Timer) -> None:
        """Send push notification for completed timer."""
        relay_client = get_relay_client()
        if not relay_client or not relay_client.is_connected:
            logger.warning(f"Cannot send timer notification - relay not connected")
            return

        try:
            await relay_client.send_push(
                user_id=timer.user_id,
                title="Timer Complete",
                body=f"{timer.label} ({timer.format_duration()})",
                data={
                    "type": "timer_complete",
                    "timer_id": timer.id,
                    "label": timer.label,
                    "duration_seconds": timer.duration_seconds,
                    "timestamp": datetime.now().isoformat(),
                },
            )
            logger.info(f"Sent timer notification to user {timer.user_id}")
        except Exception as e:
            logger.error(f"Failed to send timer notification: {e}")

    # =========================================================================
    # Database Operations
    # =========================================================================

    def _save_timer(self, timer: Timer) -> None:
        """Save or update a timer in the database."""
        with get_db() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO timers (
                    id, daemon_id, user_id, label, duration_seconds,
                    started_at, ends_at, status, source, ha_entity_id,
                    remaining_seconds, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                timer.id,
                timer.daemon_id,
                timer.user_id,
                timer.label,
                timer.duration_seconds,
                timer.started_at.isoformat(),
                timer.ends_at.isoformat(),
                timer.status.value,
                timer.source.value,
                timer.ha_entity_id,
                timer.remaining_seconds,
                timer.created_at.isoformat(),
            ))
            conn.commit()

    def _load_active_timers(self) -> List[Timer]:
        """Load active timers from database."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM timers
                WHERE daemon_id = ? AND status IN ('active', 'paused')
            """, (self._daemon_id,))
            return [self._row_to_timer(dict(row)) for row in cursor.fetchall()]

    def _row_to_timer(self, row: Dict) -> Timer:
        """Convert database row to Timer object."""
        return Timer(
            id=row["id"],
            daemon_id=row["daemon_id"],
            user_id=row["user_id"],
            label=row["label"],
            duration_seconds=row["duration_seconds"],
            started_at=datetime.fromisoformat(row["started_at"]),
            ends_at=datetime.fromisoformat(row["ends_at"]),
            status=TimerStatus(row["status"]),
            source=TimerSource(row["source"]),
            ha_entity_id=row.get("ha_entity_id"),
            remaining_seconds=row.get("remaining_seconds"),
            created_at=datetime.fromisoformat(row["created_at"]) if row.get("created_at") else datetime.now(),
        )


# =============================================================================
# Module-level singleton
# =============================================================================

_timer_managers: Dict[str, TimerManager] = {}


def get_timer_manager(daemon_id: str) -> TimerManager:
    """Get or create a timer manager for a daemon."""
    if daemon_id not in _timer_managers:
        _timer_managers[daemon_id] = TimerManager(daemon_id)
    return _timer_managers[daemon_id]


async def initialize_timer_manager(daemon_id: str) -> TimerManager:
    """Initialize and return a timer manager."""
    manager = get_timer_manager(daemon_id)
    await manager.initialize()
    return manager
