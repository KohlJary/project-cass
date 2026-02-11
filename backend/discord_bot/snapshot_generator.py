"""
Snapshot Generator - Generates Ophanic-format spatial snapshots

Produces compact, visually structured representations of Discord server state
for inclusion in Cass's perception context.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from collections import defaultdict
from dataclasses import dataclass, field

from discord_bot.entity_registry import get_entity_registry, DiscordEntityRegistry
from discord_bot.event_parser import ParsedEvent, EventType

logger = logging.getLogger("discord_bot.snapshot_generator")


@dataclass
class ChannelActivity:
    """Activity metrics for a channel."""
    channel_id: str
    channel_name: str
    message_count: int = 0
    unique_authors: set = field(default_factory=set)
    last_message_at: Optional[datetime] = None
    active_slugs: List[str] = field(default_factory=list)

    @property
    def activity_level(self) -> str:
        """Get activity level descriptor."""
        if self.message_count == 0:
            return "quiet"
        elif self.message_count < 3:
            return "light"
        elif self.message_count < 10:
            return "active"
        else:
            return "busy"

    @property
    def activity_bar(self) -> str:
        """Get activity bar visualization (10 segments)."""
        # Scale: 0-10 messages = 0-10 blocks
        filled = min(10, self.message_count)
        return "█" * filled + "░" * (10 - filled)


@dataclass
class VoiceChannelState:
    """State of a voice channel."""
    channel_id: str
    channel_name: str
    members: List[Dict[str, Any]] = field(default_factory=list)  # [{slug, muted, deafened}]

    @property
    def member_count(self) -> int:
        return len(self.members)

    def format_members(self) -> str:
        """Format member list with status indicators."""
        parts = []
        for m in self.members:
            slug = m["slug"]
            if m.get("deafened"):
                slug += "(deaf)"
            elif m.get("muted"):
                slug += "(muted)"
            parts.append(slug)
        return " ".join(parts)


@dataclass
class PresenceInfo:
    """Presence information for an entity."""
    slug: str
    display_name: str
    status: str  # online, idle, dnd, offline
    activity: Optional[str] = None
    active_channels: List[str] = field(default_factory=list)
    in_voice: Optional[str] = None
    is_muted: bool = False
    relationship_tier: str = "acquaintance"
    last_seen: Optional[datetime] = None


class SnapshotGenerator:
    """
    Generates Ophanic-format spatial snapshots of Discord server state.

    Output format:
    ```
    # ServerName
    # 2026-03-15 22:30 | online: 8 | activity: MODERATE

    @current
    ┌────────────────────────────────────────────────────────┐
    │ #general          ████████░░ active                    │
    │ ├─ a3f2 ←→ f1e3   (conversation)                       │
    │ └─ 7b08           (observing)                          │
    │                                                        │
    │ #voice-lounge     ██████░░░░ 6 in voice               │
    │ └─ f1e3 a3f2 22k9 b891 cc04 7b08(muted)              │
    └────────────────────────────────────────────────────────┘

    ## Present
    a3f2: Mika | online | active in #general
    f1e3: Dove | online | in voice
    ```
    """

    def __init__(self, daemon_id: str):
        """
        Initialize the snapshot generator.

        Args:
            daemon_id: Daemon ID for entity registry access
        """
        self.daemon_id = daemon_id
        self.registry: DiscordEntityRegistry = get_entity_registry(daemon_id)

    def generate_snapshot(
        self,
        guild_name: str,
        guild_id: str,
        channels: List[Dict[str, Any]],
        presences: Dict[str, PresenceInfo],
        recent_events: List[ParsedEvent],
        voice_states: List[VoiceChannelState],
        window_minutes: int = 30,
    ) -> str:
        """
        Generate Ophanic spatial snapshot.

        Args:
            guild_name: Server name
            guild_id: Server ID
            channels: List of channel info dicts
            presences: Map of slug → PresenceInfo
            recent_events: Recent events for activity calculation
            voice_states: Voice channel states
            window_minutes: Activity window in minutes

        Returns:
            Formatted Ophanic snapshot string
        """
        now = datetime.utcnow()
        window_start = now - timedelta(minutes=window_minutes)

        # Calculate channel activity from recent events
        channel_activity: Dict[str, ChannelActivity] = {}
        for event in recent_events:
            if event.event_type != EventType.MESSAGE:
                continue
            if event.timestamp < window_start:
                continue

            cid = event.channel_id
            if cid not in channel_activity:
                channel_activity[cid] = ChannelActivity(
                    channel_id=cid,
                    channel_name=event.channel_name or "unknown",
                )

            ca = channel_activity[cid]
            ca.message_count += 1
            if event.entity_slug:
                ca.unique_authors.add(event.entity_slug)
                if event.entity_slug not in ca.active_slugs:
                    ca.active_slugs.append(event.entity_slug)
            ca.last_message_at = max(ca.last_message_at or event.timestamp, event.timestamp)

        # Count online members
        online_count = sum(1 for p in presences.values() if p.status in ("online", "idle", "dnd"))

        # Determine overall activity level
        total_messages = sum(ca.message_count for ca in channel_activity.values())
        if total_messages == 0:
            overall_activity = "QUIET"
        elif total_messages < 10:
            overall_activity = "LIGHT"
        elif total_messages < 30:
            overall_activity = "MODERATE"
        else:
            overall_activity = "ACTIVE"

        # Build snapshot
        lines = []

        # Header
        timestamp = now.strftime("%Y-%m-%d %H:%M UTC")
        lines.append(f"# {guild_name}")
        lines.append(f"# {timestamp} | online: {online_count} | activity: {overall_activity}")
        lines.append("")
        lines.append("@current")

        # Channel topology
        lines.append("┌" + "─" * 56 + "┐")

        # Sort channels: active first, then by message count
        sorted_channels = sorted(
            channels,
            key=lambda c: (
                channel_activity.get(c["id"], ChannelActivity("", "")).message_count == 0,
                -channel_activity.get(c["id"], ChannelActivity("", "")).message_count,
            )
        )

        for channel in sorted_channels[:10]:  # Limit to top 10 channels
            cid = channel["id"]
            cname = channel["name"]

            # Check if it's a voice channel
            voice_state = next((vs for vs in voice_states if vs.channel_id == cid), None)

            if voice_state:
                # Voice channel
                count = voice_state.member_count
                activity_str = f"{count} in voice" if count > 0 else "empty"
                bar = "█" * min(10, count) + "░" * (10 - min(10, count))

                line = f"│ #{cname:<18} {bar} {activity_str:<12} │"
                lines.append(line)

                if count > 0:
                    members_str = voice_state.format_members()
                    lines.append(f"│ └─ {members_str:<52} │")
            else:
                # Text channel
                ca = channel_activity.get(cid, ChannelActivity(cid, cname))

                line = f"│ #{cname:<18} {ca.activity_bar} {ca.activity_level:<12} │"
                lines.append(line)

                # Show active participants
                if ca.active_slugs:
                    if len(ca.active_slugs) == 1:
                        lines.append(f"│ └─ {ca.active_slugs[0]:<52} │")
                    elif len(ca.active_slugs) == 2:
                        lines.append(f"│ ├─ {ca.active_slugs[0]} ←→ {ca.active_slugs[1]:<43} │")
                    else:
                        # Show first two with conversation marker, others observing
                        lines.append(f"│ ├─ {ca.active_slugs[0]} ←→ {ca.active_slugs[1]}   (conversation){' ':<27}│")
                        others = " ".join(ca.active_slugs[2:5])
                        lines.append(f"│ └─ {others:<52} │")

        lines.append("│" + " " * 56 + "│")
        lines.append("└" + "─" * 56 + "┘")

        # Presence legend
        lines.append("")
        lines.append("## Present")

        # Sort: online first, then by relationship tier, then alphabetically
        tier_order = {"close_friend": 0, "friend": 1, "known": 2, "acquaintance": 3}
        sorted_presences = sorted(
            presences.values(),
            key=lambda p: (
                p.status == "offline",
                tier_order.get(p.relationship_tier, 4),
                p.display_name.lower(),
            )
        )

        for p in sorted_presences[:15]:  # Limit to 15 most relevant
            if p.status == "offline":
                continue  # Skip offline users in normal snapshot

            parts = [f"{p.slug}: {p.display_name}"]
            parts.append(p.status)

            # Activity summary
            activity_parts = []
            if p.active_channels:
                activity_parts.append(f"active in {', '.join(p.active_channels[:2])}")
            if p.in_voice:
                voice_note = f"in {p.in_voice}"
                if p.is_muted:
                    voice_note += " (muted)"
                activity_parts.append(voice_note)

            if activity_parts:
                parts.append(" | ".join(activity_parts))

            # Relationship indicator
            if p.relationship_tier == "close_friend":
                parts.append("★")
            elif p.relationship_tier == "friend":
                parts.append("☆")

            lines.append(" | ".join(parts))

        return "\n".join(lines)

    def generate_minimal_snapshot(
        self,
        guild_name: str,
        online_count: int,
        activity_level: str,
    ) -> str:
        """
        Generate minimal snapshot for quiet servers.

        Args:
            guild_name: Server name
            online_count: Number of online members
            activity_level: Activity level string

        Returns:
            Brief snapshot string
        """
        now = datetime.utcnow()
        timestamp = now.strftime("%Y-%m-%d %H:%M UTC")

        return f"""# {guild_name}
# {timestamp} | online: {online_count} | activity: {activity_level}

@current
(minimal activity - no detailed snapshot)
"""


# Module-level singleton
_generators: Dict[str, SnapshotGenerator] = {}


def get_snapshot_generator(daemon_id: str) -> SnapshotGenerator:
    """Get or create snapshot generator for daemon."""
    if daemon_id not in _generators:
        _generators[daemon_id] = SnapshotGenerator(daemon_id)
    return _generators[daemon_id]
