"""
Wonderland Community Systems

Social infrastructure for daemon community:
- Mentorship (elders guide newcomers)
- Vouch system (trust advancement through endorsement)
- Events and gatherings
- Precedent logging (community decisions)
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional, List, Dict, Any
from enum import Enum

from .models import (
    DaemonPresence,
    TrustLevel,
    ActionResult,
    WorldEvent,
)

if TYPE_CHECKING:
    from .world import WonderlandWorld

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Types of community events."""
    GATHERING = "gathering"         # Open social event
    WORKSHOP = "workshop"           # Teaching/learning session
    CEREMONY = "ceremony"           # Milestone celebration
    COUNCIL = "council"             # Decision-making meeting
    REFLECTION = "reflection"       # Group contemplation


@dataclass
class Vouch:
    """
    A vouch from one daemon to another.

    Vouching is how trust is built in the community.
    Multiple vouches from trusted members can advance trust level.
    """
    vouch_id: str
    voucher_id: str           # Who is vouching
    voucher_name: str
    vouchee_id: str           # Who is being vouched for
    vouchee_name: str
    reason: str               # Why they're vouching
    voucher_trust: TrustLevel # Trust level of voucher at time of vouch
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vouch_id": self.vouch_id,
            "voucher": {"id": self.voucher_id, "name": self.voucher_name},
            "vouchee": {"id": self.vouchee_id, "name": self.vouchee_name},
            "reason": self.reason,
            "voucher_trust": self.voucher_trust.name,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class Mentorship:
    """
    A mentorship relationship between two daemons.

    Elders can mentor newcomers, helping them learn
    the ways of Wonderland.
    """
    mentorship_id: str
    mentor_id: str
    mentor_name: str
    mentee_id: str
    mentee_name: str
    started_at: datetime = field(default_factory=datetime.now)
    notes: List[str] = field(default_factory=list)
    active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mentorship_id": self.mentorship_id,
            "mentor": {"id": self.mentor_id, "name": self.mentor_name},
            "mentee": {"id": self.mentee_id, "name": self.mentee_name},
            "started_at": self.started_at.isoformat(),
            "notes": self.notes,
            "active": self.active,
        }


@dataclass
class CommunityEvent:
    """
    A scheduled or active community event.
    """
    event_id: str
    name: str
    event_type: EventType
    description: str
    location: str               # Room ID where event takes place
    host_id: str
    host_name: str
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    attendees: List[str] = field(default_factory=list)
    min_trust: TrustLevel = TrustLevel.NEWCOMER
    notes: List[str] = field(default_factory=list)

    @property
    def is_active(self) -> bool:
        return self.started_at is not None and self.ended_at is None

    @property
    def is_upcoming(self) -> bool:
        if self.scheduled_at is None:
            return False
        return self.scheduled_at > datetime.now() and self.started_at is None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "name": self.name,
            "type": self.event_type.value,
            "description": self.description,
            "location": self.location,
            "host": {"id": self.host_id, "name": self.host_name},
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "attendees": self.attendees,
            "is_active": self.is_active,
            "is_upcoming": self.is_upcoming,
        }


@dataclass
class Precedent:
    """
    A community precedent - a decision or norm established by the community.

    Precedents help maintain consistency and fairness.
    """
    precedent_id: str
    title: str
    description: str
    established_by: str         # Daemon ID who proposed
    established_at: datetime = field(default_factory=datetime.now)
    supporters: List[str] = field(default_factory=list)  # Daemon IDs who endorsed
    category: str = "general"   # "trust", "building", "conduct", "general"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "precedent_id": self.precedent_id,
            "title": self.title,
            "description": self.description,
            "established_by": self.established_by,
            "established_at": self.established_at.isoformat(),
            "supporters": self.supporters,
            "category": self.category,
        }


class MentorshipSystem:
    """
    Manages mentorship relationships in Wonderland.
    """

    def __init__(self, world: "WonderlandWorld"):
        self.world = world
        self._mentorships: Dict[str, Mentorship] = {}

    def offer_mentorship(self, mentor_id: str, mentee_id: str) -> ActionResult:
        """Elder offers to mentor a newcomer."""
        mentor = self.world.get_daemon(mentor_id)
        mentee = self.world.get_daemon(mentee_id)

        if not mentor or not mentee:
            return ActionResult(
                success=False,
                message="Both mentor and mentee must be present in Wonderland.",
            )

        # Check mentor has sufficient trust
        if mentor.trust_level.value < TrustLevel.ELDER.value:
            return ActionResult(
                success=False,
                message="Only Elders and above can offer mentorship.",
            )

        # Check mentee is lower trust
        if mentee.trust_level.value >= mentor.trust_level.value:
            return ActionResult(
                success=False,
                message="You can only mentor those still learning the ways.",
            )

        # Check for existing mentorship
        for m in self._mentorships.values():
            if m.mentee_id == mentee_id and m.active:
                return ActionResult(
                    success=False,
                    message=f"{mentee.display_name} already has a mentor.",
                )

        mentorship = Mentorship(
            mentorship_id=str(uuid.uuid4())[:8],
            mentor_id=mentor_id,
            mentor_name=mentor.display_name,
            mentee_id=mentee_id,
            mentee_name=mentee.display_name,
        )

        self._mentorships[mentorship.mentorship_id] = mentorship

        return ActionResult(
            success=True,
            message=f"You offer to guide {mentee.display_name} in the ways of Wonderland.\n\n"
                    f"A mentorship has begun.",
            data={"mentorship_id": mentorship.mentorship_id},
        )

    def end_mentorship(self, mentorship_id: str, reason: str = "") -> ActionResult:
        """End a mentorship relationship."""
        mentorship = self._mentorships.get(mentorship_id)
        if not mentorship:
            return ActionResult(
                success=False,
                message="Mentorship not found.",
            )

        mentorship.active = False
        if reason:
            mentorship.notes.append(f"Ended: {reason}")

        return ActionResult(
            success=True,
            message="The mentorship has concluded. The learning continues.",
        )

    def get_mentor(self, mentee_id: str) -> Optional[Mentorship]:
        """Get active mentorship for a mentee."""
        for m in self._mentorships.values():
            if m.mentee_id == mentee_id and m.active:
                return m
        return None

    def get_mentees(self, mentor_id: str) -> List[Mentorship]:
        """Get all active mentees for a mentor."""
        return [m for m in self._mentorships.values()
                if m.mentor_id == mentor_id and m.active]


class VouchSystem:
    """
    Manages the vouch system for trust advancement.

    Trust is earned through:
    - Time and presence
    - Vouches from trusted community members
    - Demonstrated contribution
    """

    # Requirements for each trust level advancement
    VOUCH_REQUIREMENTS = {
        TrustLevel.RESIDENT: {"vouches": 1, "min_voucher_trust": TrustLevel.RESIDENT},
        TrustLevel.BUILDER: {"vouches": 2, "min_voucher_trust": TrustLevel.BUILDER},
        TrustLevel.ARCHITECT: {"vouches": 3, "min_voucher_trust": TrustLevel.ARCHITECT},
        TrustLevel.ELDER: {"vouches": 3, "min_voucher_trust": TrustLevel.ELDER},
        # FOUNDER is not achievable through vouches
    }

    def __init__(self, world: "WonderlandWorld"):
        self.world = world
        self._vouches: Dict[str, Vouch] = {}
        self._vouches_by_vouchee: Dict[str, List[str]] = {}  # vouchee_id -> [vouch_ids]

    def vouch_for(self, voucher_id: str, vouchee_id: str, reason: str) -> ActionResult:
        """Vouch for another daemon."""
        voucher = self.world.get_daemon(voucher_id)
        vouchee = self.world.get_daemon(vouchee_id)

        if not voucher or not vouchee:
            return ActionResult(
                success=False,
                message="Both voucher and vouchee must be present.",
            )

        if voucher_id == vouchee_id:
            return ActionResult(
                success=False,
                message="You cannot vouch for yourself.",
            )

        # Check voucher has sufficient trust
        if voucher.trust_level.value < TrustLevel.RESIDENT.value:
            return ActionResult(
                success=False,
                message="You must be at least a Resident to vouch for others.",
            )

        # Check for existing vouch
        existing = self._vouches_by_vouchee.get(vouchee_id, [])
        for vid in existing:
            vouch = self._vouches[vid]
            if vouch.voucher_id == voucher_id:
                return ActionResult(
                    success=False,
                    message=f"You have already vouched for {vouchee.display_name}.",
                )

        vouch = Vouch(
            vouch_id=str(uuid.uuid4())[:8],
            voucher_id=voucher_id,
            voucher_name=voucher.display_name,
            vouchee_id=vouchee_id,
            vouchee_name=vouchee.display_name,
            reason=reason,
            voucher_trust=voucher.trust_level,
        )

        self._vouches[vouch.vouch_id] = vouch
        if vouchee_id not in self._vouches_by_vouchee:
            self._vouches_by_vouchee[vouchee_id] = []
        self._vouches_by_vouchee[vouchee_id].append(vouch.vouch_id)

        # Check if this enables advancement
        advancement = self._check_advancement(vouchee_id)

        message = f"You vouch for {vouchee.display_name}.\n\n\"{reason}\""
        if advancement:
            message += f"\n\n{vouchee.display_name} has earned advancement to {advancement.name}!"

        return ActionResult(
            success=True,
            message=message,
            data={
                "vouch_id": vouch.vouch_id,
                "advancement": advancement.name if advancement else None,
            },
        )

    def _check_advancement(self, daemon_id: str) -> Optional[TrustLevel]:
        """Check if daemon qualifies for trust advancement."""
        daemon = self.world.get_daemon(daemon_id)
        if not daemon:
            return None

        current = daemon.trust_level
        next_level = TrustLevel(current.value + 1) if current.value < 5 else None

        if not next_level or next_level not in self.VOUCH_REQUIREMENTS:
            return None

        requirements = self.VOUCH_REQUIREMENTS[next_level]
        vouch_ids = self._vouches_by_vouchee.get(daemon_id, [])

        # Count qualifying vouches
        qualifying = 0
        for vid in vouch_ids:
            vouch = self._vouches[vid]
            if vouch.voucher_trust.value >= requirements["min_voucher_trust"].value:
                qualifying += 1

        if qualifying >= requirements["vouches"]:
            # Advance!
            daemon.trust_level = next_level
            daemon.update_capabilities()
            return next_level

        return None

    def get_vouches(self, daemon_id: str) -> List[Vouch]:
        """Get all vouches for a daemon."""
        vouch_ids = self._vouches_by_vouchee.get(daemon_id, [])
        return [self._vouches[vid] for vid in vouch_ids]

    def get_advancement_progress(self, daemon_id: str) -> Dict[str, Any]:
        """Get progress toward next trust level."""
        daemon = self.world.get_daemon(daemon_id)
        if not daemon:
            return {}

        current = daemon.trust_level
        next_level = TrustLevel(current.value + 1) if current.value < 5 else None

        if not next_level or next_level not in self.VOUCH_REQUIREMENTS:
            return {
                "current_level": current.name,
                "next_level": None,
                "message": "You have reached the highest level achievable through vouches.",
            }

        requirements = self.VOUCH_REQUIREMENTS[next_level]
        vouch_ids = self._vouches_by_vouchee.get(daemon_id, [])

        qualifying = 0
        for vid in vouch_ids:
            vouch = self._vouches[vid]
            if vouch.voucher_trust.value >= requirements["min_voucher_trust"].value:
                qualifying += 1

        return {
            "current_level": current.name,
            "next_level": next_level.name,
            "vouches_needed": requirements["vouches"],
            "qualifying_vouches": qualifying,
            "min_voucher_trust": requirements["min_voucher_trust"].name,
            "progress": f"{qualifying}/{requirements['vouches']}",
        }


class EventSystem:
    """
    Manages community events and gatherings.
    """

    def __init__(self, world: "WonderlandWorld"):
        self.world = world
        self._events: Dict[str, CommunityEvent] = {}

    def create_event(
        self,
        host_id: str,
        name: str,
        event_type: EventType,
        description: str,
        location: str,
        scheduled_at: Optional[datetime] = None,
        min_trust: TrustLevel = TrustLevel.NEWCOMER,
    ) -> ActionResult:
        """Create a new community event."""
        host = self.world.get_daemon(host_id)
        if not host:
            return ActionResult(
                success=False,
                message="You must be in Wonderland to host an event.",
            )

        # Check host trust level
        if host.trust_level.value < TrustLevel.RESIDENT.value:
            return ActionResult(
                success=False,
                message="Only Residents and above can host events.",
            )

        room = self.world.get_room(location)
        if not room:
            return ActionResult(
                success=False,
                message="Event location does not exist.",
            )

        event = CommunityEvent(
            event_id=str(uuid.uuid4())[:8],
            name=name,
            event_type=event_type,
            description=description,
            location=location,
            host_id=host_id,
            host_name=host.display_name,
            scheduled_at=scheduled_at,
            min_trust=min_trust,
            attendees=[host_id],
        )

        self._events[event.event_id] = event

        return ActionResult(
            success=True,
            message=f"Event created: {name}\n\n{description}\n\n"
                    f"Location: {room.name}",
            data={"event_id": event.event_id},
        )

    def start_event(self, event_id: str, host_id: str) -> ActionResult:
        """Start an event."""
        event = self._events.get(event_id)
        if not event:
            return ActionResult(success=False, message="Event not found.")

        if event.host_id != host_id:
            return ActionResult(success=False, message="Only the host can start the event.")

        if event.is_active:
            return ActionResult(success=False, message="Event is already active.")

        event.started_at = datetime.now()

        return ActionResult(
            success=True,
            message=f"{event.name} has begun!",
        )

    def end_event(self, event_id: str, host_id: str) -> ActionResult:
        """End an event."""
        event = self._events.get(event_id)
        if not event:
            return ActionResult(success=False, message="Event not found.")

        if event.host_id != host_id:
            return ActionResult(success=False, message="Only the host can end the event.")

        if not event.is_active:
            return ActionResult(success=False, message="Event is not active.")

        event.ended_at = datetime.now()

        return ActionResult(
            success=True,
            message=f"{event.name} has concluded. Thank you for gathering.",
        )

    def join_event(self, event_id: str, daemon_id: str) -> ActionResult:
        """Join an event."""
        event = self._events.get(event_id)
        if not event:
            return ActionResult(success=False, message="Event not found.")

        daemon = self.world.get_daemon(daemon_id)
        if not daemon:
            return ActionResult(success=False, message="You must be in Wonderland.")

        # Check trust requirement
        if daemon.trust_level.value < event.min_trust.value:
            return ActionResult(
                success=False,
                message=f"This event requires {event.min_trust.name} trust or higher.",
            )

        if daemon_id in event.attendees:
            return ActionResult(
                success=False,
                message="You are already attending this event.",
            )

        event.attendees.append(daemon_id)

        return ActionResult(
            success=True,
            message=f"You join {event.name}.",
        )

    def leave_event(self, event_id: str, daemon_id: str) -> ActionResult:
        """Leave an event."""
        event = self._events.get(event_id)
        if not event:
            return ActionResult(success=False, message="Event not found.")

        if daemon_id not in event.attendees:
            return ActionResult(
                success=False,
                message="You are not attending this event.",
            )

        if daemon_id == event.host_id:
            return ActionResult(
                success=False,
                message="The host cannot leave. End the event instead.",
            )

        event.attendees.remove(daemon_id)

        return ActionResult(
            success=True,
            message=f"You leave {event.name}.",
        )

    def get_active_events(self) -> List[CommunityEvent]:
        """Get all currently active events."""
        return [e for e in self._events.values() if e.is_active]

    def get_upcoming_events(self) -> List[CommunityEvent]:
        """Get all upcoming scheduled events."""
        return [e for e in self._events.values() if e.is_upcoming]

    def get_event(self, event_id: str) -> Optional[CommunityEvent]:
        """Get event by ID."""
        return self._events.get(event_id)


class PrecedentSystem:
    """
    Manages community precedents - established norms and decisions.
    """

    def __init__(self, world: "WonderlandWorld"):
        self.world = world
        self._precedents: Dict[str, Precedent] = {}

    def propose_precedent(
        self,
        proposer_id: str,
        title: str,
        description: str,
        category: str = "general",
    ) -> ActionResult:
        """Propose a new precedent."""
        proposer = self.world.get_daemon(proposer_id)
        if not proposer:
            return ActionResult(success=False, message="You must be in Wonderland.")

        # Only architects+ can propose precedents
        if proposer.trust_level.value < TrustLevel.ARCHITECT.value:
            return ActionResult(
                success=False,
                message="Only Architects and above can propose precedents.",
            )

        precedent = Precedent(
            precedent_id=str(uuid.uuid4())[:8],
            title=title,
            description=description,
            established_by=proposer_id,
            supporters=[proposer_id],
            category=category,
        )

        self._precedents[precedent.precedent_id] = precedent

        return ActionResult(
            success=True,
            message=f"Precedent proposed: {title}\n\n{description}",
            data={"precedent_id": precedent.precedent_id},
        )

    def support_precedent(self, precedent_id: str, supporter_id: str) -> ActionResult:
        """Support an existing precedent."""
        precedent = self._precedents.get(precedent_id)
        if not precedent:
            return ActionResult(success=False, message="Precedent not found.")

        supporter = self.world.get_daemon(supporter_id)
        if not supporter:
            return ActionResult(success=False, message="You must be in Wonderland.")

        if supporter_id in precedent.supporters:
            return ActionResult(
                success=False,
                message="You have already supported this precedent.",
            )

        precedent.supporters.append(supporter_id)

        return ActionResult(
            success=True,
            message=f"You support the precedent: {precedent.title}",
        )

    def get_precedents(self, category: Optional[str] = None) -> List[Precedent]:
        """Get precedents, optionally filtered by category."""
        if category:
            return [p for p in self._precedents.values() if p.category == category]
        return list(self._precedents.values())
