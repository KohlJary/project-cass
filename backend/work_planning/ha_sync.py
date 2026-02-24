"""
Home Assistant Calendar Sync for Cass's Work Schedule.

Syncs ScheduleSlots to a Home Assistant Local Calendar entity,
making Cass's autonomous work visible in the HA dashboard.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from ha_calendar import get_ha_calendar_client, HACalendarClient

logger = logging.getLogger(__name__)


# Default entity ID for Cass's work calendar
CASS_CALENDAR_ENTITY = "calendar.cass_work"


class CassCalendarSync:
    """
    Syncs Cass's ScheduleSlots to Home Assistant Local Calendar.

    This makes Cass's autonomous work schedule visible in HA,
    allowing users to see when Cass plans to do work, and enabling
    HA automations to reference Cass's schedule.
    """

    def __init__(self, calendar_entity: str = CASS_CALENDAR_ENTITY):
        """
        Initialize the sync manager.

        Args:
            calendar_entity: HA calendar entity ID to sync to
        """
        self.calendar_entity = calendar_entity
        self._ha: Optional[HACalendarClient] = None
        self._enabled = True
        self._calendar_verified = False

    @property
    def ha(self) -> HACalendarClient:
        """Get HA calendar client (lazy init)."""
        if self._ha is None:
            self._ha = get_ha_calendar_client()
        return self._ha

    @property
    def is_enabled(self) -> bool:
        """Check if sync is enabled and HA is configured."""
        return self._enabled and self.ha.is_configured

    def disable(self) -> None:
        """Disable sync (useful during tests or debugging)."""
        self._enabled = False

    def enable(self) -> None:
        """Enable sync."""
        self._enabled = True

    async def ensure_calendar_exists(self) -> bool:
        """
        Ensure the Cass work calendar exists in Home Assistant.

        If the calendar doesn't exist and Local Calendar integration
        is available, attempts to create it.

        Returns:
            True if calendar exists or was created, False otherwise
        """
        if not self.is_enabled:
            return False

        if self._calendar_verified:
            return True

        # Check if calendar exists
        exists = await self.ha.calendar_exists(self.calendar_entity)
        if exists:
            self._calendar_verified = True
            logger.info(f"Cass work calendar verified: {self.calendar_entity}")
            return True

        # Try to create it
        logger.info(f"Cass work calendar not found, attempting to create...")
        entity_id = await self.ha.create_local_calendar("Cass Work")

        if entity_id:
            # Update our entity reference if the ID differs
            if entity_id != self.calendar_entity:
                logger.info(f"Calendar created with entity_id: {entity_id}")
                self.calendar_entity = entity_id
            self._calendar_verified = True
            return True

        logger.warning(
            f"Could not create Cass work calendar. "
            f"Please create a Local Calendar named 'Cass Work' in Home Assistant."
        )
        return False

    async def sync_slot(
        self,
        slot_id: str,
        work_title: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
    ) -> bool:
        """
        Sync a schedule slot to the HA calendar.

        Args:
            slot_id: The schedule slot ID (used as part of event summary for tracking)
            work_title: Title of the work item
            start_time: When the work is scheduled
            end_time: When the work ends (defaults to start + 30 min)
            description: Description of the work
            category: Work category (reflection, research, etc.)

        Returns:
            True if sync succeeded
        """
        if not self.is_enabled:
            return False

        if not await self.ensure_calendar_exists():
            return False

        # Default end time
        if end_time is None:
            end_time = start_time + timedelta(minutes=30)

        # Format event summary
        # Include category for better visibility
        if category:
            summary = f"[{category.title()}] {work_title}"
        else:
            summary = work_title

        # Include slot_id in description for tracking
        full_description = f"Slot ID: {slot_id}"
        if description:
            full_description = f"{description}\n\n{full_description}"

        success = await self.ha.create_event(
            entity_id=self.calendar_entity,
            summary=summary,
            start=start_time,
            end=end_time,
            description=full_description,
        )

        if success:
            logger.debug(f"Synced slot {slot_id} to HA calendar: {work_title}")
        else:
            logger.warning(f"Failed to sync slot {slot_id} to HA calendar")

        return success

    async def remove_slot(self, slot_id: str) -> bool:
        """
        Remove a slot's event from the HA calendar.

        Note: This requires finding the event by slot_id, which may
        not be straightforward since HA doesn't support searching
        by description content. For now, we'll log a warning.

        Args:
            slot_id: The schedule slot ID to remove

        Returns:
            True if removal succeeded
        """
        if not self.is_enabled:
            return False

        # HA doesn't provide a way to search events by content
        # We would need to track the UID when creating
        # For now, log a warning
        logger.warning(
            f"Cannot remove slot {slot_id} from HA calendar - "
            f"event UID tracking not yet implemented"
        )
        return False

    async def full_sync(
        self,
        slots: list,
        work_items: dict,
    ) -> int:
        """
        Perform a full sync of all scheduled slots.

        This is useful on startup or when calendar sync is first enabled.

        Args:
            slots: List of ScheduleSlot objects to sync
            work_items: Dict mapping work_item_id to WorkItem objects

        Returns:
            Number of slots successfully synced
        """
        if not self.is_enabled:
            return 0

        if not await self.ensure_calendar_exists():
            return 0

        synced_count = 0

        for slot in slots:
            # Skip slots without times
            if not slot.start_time:
                continue

            # Skip completed or skipped slots
            if slot.status.value in ("completed", "skipped"):
                continue

            # Get work item details
            work_item = work_items.get(slot.work_item_id) if slot.work_item_id else None

            title = work_item.title if work_item else f"Scheduled Work ({slot.id})"
            description = work_item.description if work_item else None
            category = work_item.category if work_item else None

            success = await self.sync_slot(
                slot_id=slot.id,
                work_title=title,
                start_time=slot.start_time,
                end_time=slot.end_time,
                description=description,
                category=category,
            )

            if success:
                synced_count += 1

        logger.info(f"Full sync completed: {synced_count}/{len(slots)} slots synced")
        return synced_count


# =============================================================================
# Module-level singleton
# =============================================================================

_cass_calendar_sync: Optional[CassCalendarSync] = None


def get_cass_calendar_sync() -> CassCalendarSync:
    """Get or create the global Cass calendar sync instance."""
    global _cass_calendar_sync
    if _cass_calendar_sync is None:
        _cass_calendar_sync = CassCalendarSync()
    return _cass_calendar_sync
