"""
Autonomous Cartography - Proposal System for Mind Palace.

Phase 5: Daedalus proposes map updates based on code changes.

Workflow:
1. After code changes, run analyze_changes() to detect palace impact
2. Proposals are generated for new rooms, modified descriptions, removed anchors
3. Human reviews proposals and approves/rejects
4. Approved proposals are applied to the palace
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set

from .models import Palace, Room, Building, Anchor, Hazard, HazardType
from .storage import PalaceStorage
from .cartographer import Cartographer
from .languages import get_language_registry, CodeElement

logger = logging.getLogger(__name__)


class ProposalType(str, Enum):
    """Types of palace update proposals."""
    ADD_ROOM = "add_room"
    REMOVE_ROOM = "remove_room"
    UPDATE_ROOM = "update_room"
    ADD_BUILDING = "add_building"
    ADD_HAZARD = "add_hazard"
    UPDATE_ANCHOR = "update_anchor"


class ProposalStatus(str, Enum):
    """Status of a proposal."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"


@dataclass
class Proposal:
    """A proposed change to the palace."""
    id: str
    type: ProposalType
    target: str  # Room/building name
    reason: str  # Why this change is proposed
    details: Dict  # Type-specific details
    status: ProposalStatus = ProposalStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    reviewed_at: Optional[str] = None
    reviewer_note: Optional[str] = None


@dataclass
class ProposalSet:
    """A batch of proposals from a single analysis."""
    id: str
    created_at: str
    source: str  # What triggered the analysis (e.g., "git commit abc123")
    proposals: List[Proposal] = field(default_factory=list)

    def pending(self) -> List[Proposal]:
        """Get all pending proposals."""
        return [p for p in self.proposals if p.status == ProposalStatus.PENDING]

    def summary(self) -> str:
        """Generate a human-readable summary."""
        by_type = {}
        for p in self.proposals:
            by_type.setdefault(p.type.value, []).append(p)

        lines = [f"Proposal Set: {self.id}", f"Source: {self.source}", ""]

        for ptype, proposals in by_type.items():
            lines.append(f"**{ptype}** ({len(proposals)})")
            for p in proposals[:5]:  # Show first 5
                lines.append(f"  - {p.target}: {p.reason}")
            if len(proposals) > 5:
                lines.append(f"  ... and {len(proposals) - 5} more")
            lines.append("")

        return "\n".join(lines)


class ProposalManager:
    """
    Manages palace update proposals.

    Usage:
        manager = ProposalManager(palace, storage)
        proposals = manager.analyze_directory(Path("backend"))
        print(proposals.summary())

        # Review and approve
        manager.approve(proposals.proposals[0].id, "Looks good")

        # Apply approved proposals
        manager.apply_approved(proposals)
    """

    def __init__(self, palace: Palace, storage: PalaceStorage):
        self.palace = palace
        self.storage = storage
        self.cartographer = Cartographer(palace, storage)
        self._proposal_counter = 0

    def _generate_id(self) -> str:
        """Generate a unique proposal ID."""
        self._proposal_counter += 1
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        return f"prop-{timestamp}-{self._proposal_counter:04d}"

    def analyze_directory(
        self,
        directory: Path,
        project_root: Path,
        source: str = "manual",
    ) -> ProposalSet:
        """
        Analyze a directory for palace changes.

        Compares current code with palace structure and proposes updates.
        """
        proposal_set = ProposalSet(
            id=self._generate_id(),
            created_at=datetime.utcnow().isoformat(),
            source=source,
        )

        registry = get_language_registry()
        existing_rooms = set(self.palace.rooms.keys())
        found_rooms: Set[str] = set()

        # Scan code for elements
        for ext in registry.supported_extensions():
            for file_path in directory.rglob(f"*{ext}"):
                # Skip non-code directories
                if any(part.startswith(".") or part in ("__pycache__", "node_modules", "venv", "data")
                       for part in file_path.parts):
                    continue

                lang = registry.get_by_extension(file_path)
                if not lang:
                    continue

                try:
                    elements = lang.analyze_file(file_path, project_root)
                    relative_path = str(file_path.relative_to(project_root))

                    for element in elements:
                        room_name = element.name
                        found_rooms.add(room_name)

                        if room_name not in existing_rooms:
                            # Propose new room
                            anchor_pattern = lang.generate_anchor_pattern(element)
                            proposal = Proposal(
                                id=self._generate_id(),
                                type=ProposalType.ADD_ROOM,
                                target=room_name,
                                reason=f"New {element.element_type} found in {relative_path}",
                                details={
                                    "element_type": element.element_type,
                                    "file": relative_path,
                                    "line": element.line,
                                    "signature": element.signature,
                                    "docstring": element.docstring[:200] if element.docstring else None,
                                    "anchor_pattern": anchor_pattern.pattern,
                                    "anchor_is_regex": anchor_pattern.is_regex,
                                },
                            )
                            proposal_set.proposals.append(proposal)

                        else:
                            # Check if existing room needs update
                            existing = self.palace.rooms[room_name]
                            if existing.anchor:
                                # Check if anchor still valid
                                try:
                                    with open(file_path) as f:
                                        content = f.read()
                                    anchor_pattern = lang.generate_anchor_pattern(element)
                                    if not anchor_pattern.matches(content):
                                        proposal = Proposal(
                                            id=self._generate_id(),
                                            type=ProposalType.UPDATE_ANCHOR,
                                            target=room_name,
                                            reason="Anchor pattern no longer matches code",
                                            details={
                                                "old_pattern": existing.anchor.pattern,
                                                "new_pattern": anchor_pattern.pattern,
                                                "file": relative_path,
                                            },
                                        )
                                        proposal_set.proposals.append(proposal)
                                except Exception:
                                    pass

                except Exception as e:
                    logger.warning(f"Failed to analyze {file_path}: {e}")

        # Check for removed rooms (only for rooms with anchors in this directory)
        for room_name in existing_rooms:
            room = self.palace.rooms[room_name]
            if room.anchor and room.anchor.file:
                anchor_file = project_root / room.anchor.file
                if anchor_file.exists() and directory in anchor_file.parents or anchor_file.parent == directory:
                    if room_name not in found_rooms:
                        proposal = Proposal(
                            id=self._generate_id(),
                            type=ProposalType.REMOVE_ROOM,
                            target=room_name,
                            reason=f"Code element no longer found in {room.anchor.file}",
                            details={"anchor_file": room.anchor.file},
                        )
                        proposal_set.proposals.append(proposal)

        return proposal_set

    def approve(self, proposal_id: str, note: str = None) -> bool:
        """Mark a proposal as approved."""
        # This would need to track proposals persistently
        # For now, we operate on in-memory proposal sets
        return True

    def reject(self, proposal_id: str, note: str = None) -> bool:
        """Mark a proposal as rejected."""
        return True

    def apply_proposal(self, proposal: Proposal) -> bool:
        """Apply a single approved proposal to the palace."""
        if proposal.status != ProposalStatus.APPROVED:
            logger.warning(f"Cannot apply non-approved proposal: {proposal.id}")
            return False

        try:
            if proposal.type == ProposalType.ADD_ROOM:
                details = proposal.details
                room = Room(
                    name=proposal.target,
                    building=details.get("building", "unmapped"),
                    description=details.get("docstring") or f"{details['element_type']} in {details['file']}",
                    anchor=Anchor(
                        file=details["file"],
                        pattern=details["anchor_pattern"],
                        is_regex=details.get("anchor_is_regex", False),
                    ),
                )
                self.palace.rooms[proposal.target] = room

            elif proposal.type == ProposalType.REMOVE_ROOM:
                if proposal.target in self.palace.rooms:
                    del self.palace.rooms[proposal.target]

            elif proposal.type == ProposalType.UPDATE_ANCHOR:
                if proposal.target in self.palace.rooms:
                    room = self.palace.rooms[proposal.target]
                    if room.anchor:
                        room.anchor.pattern = proposal.details["new_pattern"]

            elif proposal.type == ProposalType.ADD_HAZARD:
                if proposal.target in self.palace.rooms:
                    room = self.palace.rooms[proposal.target]
                    hazard = Hazard(
                        type=HazardType(proposal.details.get("type", "invariant")),
                        description=proposal.details["description"],
                    )
                    room.hazards.append(hazard)

            proposal.status = ProposalStatus.APPLIED
            return True

        except Exception as e:
            logger.error(f"Failed to apply proposal {proposal.id}: {e}")
            return False

    def apply_approved(self, proposal_set: ProposalSet) -> int:
        """Apply all approved proposals in a set. Returns count of applied."""
        applied = 0
        for proposal in proposal_set.proposals:
            if proposal.status == ProposalStatus.APPROVED:
                if self.apply_proposal(proposal):
                    applied += 1

        if applied > 0:
            self.storage.save(self.palace)

        return applied


def save_proposals(proposal_set: ProposalSet, path: Path) -> None:
    """Save a proposal set to JSON for review."""
    data = {
        "id": proposal_set.id,
        "created_at": proposal_set.created_at,
        "source": proposal_set.source,
        "proposals": [asdict(p) for p in proposal_set.proposals],
    }
    path.write_text(json.dumps(data, indent=2))


def load_proposals(path: Path) -> ProposalSet:
    """Load a proposal set from JSON."""
    data = json.loads(path.read_text())
    proposals = [
        Proposal(
            id=p["id"],
            type=ProposalType(p["type"]),
            target=p["target"],
            reason=p["reason"],
            details=p["details"],
            status=ProposalStatus(p["status"]),
            created_at=p.get("created_at", ""),
            reviewed_at=p.get("reviewed_at"),
            reviewer_note=p.get("reviewer_note"),
        )
        for p in data["proposals"]
    ]
    return ProposalSet(
        id=data["id"],
        created_at=data["created_at"],
        source=data["source"],
        proposals=proposals,
    )
