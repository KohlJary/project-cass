"""
Event Parser - Converts raw Discord events to structured perception events

Handles privacy-conscious content summarization and entity resolution.
"""

import logging
import re
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

from discord_bot.entity_registry import get_entity_registry, DiscordEntityRegistry
from discord_bot.config import DISCORD_CONTENT_LOGGING, TRIGGER_IMMEDIATE_KEYWORDS

logger = logging.getLogger("discord_bot.event_parser")


class EventType(str, Enum):
    """Types of parsed Discord events."""
    MESSAGE = "message"
    PRESENCE = "presence"
    REACTION = "reaction"
    VOICE = "voice"
    TYPING = "typing"
    MEMBER_JOIN = "member_join"
    MEMBER_LEAVE = "member_leave"


class ContentLength(str, Enum):
    """Content length buckets for privacy-preserving summaries."""
    BRIEF = "brief"          # < 50 chars
    SHORT = "short"          # 50-200 chars
    MEDIUM = "medium"        # 200-500 chars
    LONG = "long"            # 500-1000 chars
    EXTENDED = "extended"    # > 1000 chars


class ContentSentiment(str, Enum):
    """Simple sentiment classification."""
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    QUESTION = "question"


@dataclass
class ContentSummary:
    """Privacy-preserving content summary."""
    length: ContentLength
    sentiment: ContentSentiment
    mentions_cass: bool = False
    has_media: bool = False
    has_link: bool = False
    has_embed: bool = False
    word_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "length": self.length.value,
            "sentiment": self.sentiment.value,
            "mentions_cass": self.mentions_cass,
            "has_media": self.has_media,
            "has_link": self.has_link,
            "has_embed": self.has_embed,
            "word_count": self.word_count,
        }


@dataclass
class ParsedEvent:
    """Structured perception event from Discord."""
    event_type: EventType
    guild_id: str
    timestamp: datetime

    # Entity info (resolved from Discord ID)
    entity_slug: Optional[str] = None
    entity_display_name: Optional[str] = None

    # Channel info
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None

    # Event-specific data
    content_summary: Optional[ContentSummary] = None
    content: Optional[str] = None  # Only if DISCORD_CONTENT_LOGGING=true

    # For reactions
    target_message_id: Optional[str] = None
    emoji: Optional[str] = None

    # For presence
    status: Optional[str] = None  # online, idle, dnd, offline
    activity: Optional[str] = None

    # For voice
    voice_state: Optional[str] = None  # joined, left, muted, unmuted, deafened

    # Trigger flags (set by parser for immediate attention)
    is_direct_mention: bool = False
    is_dm: bool = False

    # Raw Discord data (for debugging)
    raw_discord_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "guild_id": self.guild_id,
            "timestamp": self.timestamp.isoformat(),
            "entity_slug": self.entity_slug,
            "entity_display_name": self.entity_display_name,
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "content_summary": self.content_summary.to_dict() if self.content_summary else None,
            "content": self.content,
            "target_message_id": self.target_message_id,
            "emoji": self.emoji,
            "status": self.status,
            "activity": self.activity,
            "voice_state": self.voice_state,
            "is_direct_mention": self.is_direct_mention,
            "is_dm": self.is_dm,
        }


class DiscordEventParser:
    """
    Parser for converting raw Discord.py events to structured perception events.
    """

    def __init__(self, daemon_id: str):
        """
        Initialize the event parser.

        Args:
            daemon_id: Daemon ID for entity registry access
        """
        self.daemon_id = daemon_id
        self.registry: DiscordEntityRegistry = get_entity_registry(daemon_id)

        # Bot user ID (set by bot.py when connected)
        self._bot_user_id: Optional[str] = None

        # Compile patterns for content analysis
        self._link_pattern = re.compile(r'https?://\S+')
        self._mention_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in TRIGGER_IMMEDIATE_KEYWORDS
        ]

    def set_bot_user_id(self, user_id: str) -> None:
        """Set the bot's user ID for mention detection."""
        self._bot_user_id = user_id
        logger.info(f"[EventParser] Bot user ID set: {user_id}")

    def _get_content_length(self, content: str) -> ContentLength:
        """Classify content length."""
        length = len(content)
        if length < 50:
            return ContentLength.BRIEF
        elif length < 200:
            return ContentLength.SHORT
        elif length < 500:
            return ContentLength.MEDIUM
        elif length < 1000:
            return ContentLength.LONG
        else:
            return ContentLength.EXTENDED

    def _get_content_sentiment(self, content: str) -> ContentSentiment:
        """Simple sentiment classification."""
        content_lower = content.lower()

        # Check for question first
        if '?' in content or content_lower.startswith(('what', 'why', 'how', 'when', 'where', 'who', 'which', 'could', 'would', 'should', 'can', 'is', 'are', 'do', 'does')):
            return ContentSentiment.QUESTION

        # Simple keyword-based sentiment
        positive_keywords = {'thanks', 'thank', 'love', 'great', 'awesome', 'amazing', 'nice', 'good', 'wonderful', 'beautiful', '❤️', '💕', '😊', '🎉', '👍', ':)', ':D'}
        negative_keywords = {'hate', 'angry', 'sad', 'terrible', 'awful', 'bad', 'horrible', 'upset', 'frustrated', '😢', '😠', '😡', ':('}

        words = set(content_lower.split())

        positive_count = len(words & positive_keywords)
        negative_count = len(words & negative_keywords)

        if positive_count > negative_count:
            return ContentSentiment.POSITIVE
        elif negative_count > positive_count:
            return ContentSentiment.NEGATIVE
        else:
            return ContentSentiment.NEUTRAL

    def _mentions_cass(self, content: str) -> bool:
        """Check if content mentions Cass."""
        for pattern in self._mention_patterns:
            if pattern.search(content):
                return True
        return False

    def _summarize_content(
        self,
        content: str,
        has_attachments: bool = False,
        has_embeds: bool = False,
    ) -> ContentSummary:
        """Generate privacy-preserving content summary."""
        return ContentSummary(
            length=self._get_content_length(content),
            sentiment=self._get_content_sentiment(content),
            mentions_cass=self._mentions_cass(content),
            has_media=has_attachments,
            has_link=bool(self._link_pattern.search(content)),
            has_embed=has_embeds,
            word_count=len(content.split()),
        )

    def _resolve_entity(self, discord_user) -> tuple[Optional[str], str]:
        """
        Resolve Discord user to entity slug.

        Returns:
            Tuple of (slug, display_name)
        """
        discord_id = str(discord_user.id)
        display_name = discord_user.display_name or discord_user.name
        # The 'name' attribute is the actual Discord username (e.g., "birdfacemd")
        discord_username = discord_user.name

        # Register/update in entity registry
        # Pass username to allow linking to existing Cass users
        entity = self.registry.register_user(
            discord_id=discord_id,
            display_name=display_name,
            discord_username=discord_username,
            discriminator=getattr(discord_user, 'discriminator', None),
        )

        return entity.slug, entity.display_name

    def parse_message(self, message) -> ParsedEvent:
        """
        Parse a Discord message event.

        Args:
            message: discord.Message object

        Returns:
            ParsedEvent
        """
        slug, display_name = self._resolve_entity(message.author)

        content_summary = self._summarize_content(
            message.content or "",
            has_attachments=bool(message.attachments),
            has_embeds=bool(message.embeds),
        )

        # Check for direct @mention of the bot
        # Discord mentions are in message.mentions as User objects
        is_bot_mentioned = False
        if self._bot_user_id and message.mentions:
            for mentioned_user in message.mentions:
                if str(mentioned_user.id) == self._bot_user_id:
                    is_bot_mentioned = True
                    logger.info(f"[EventParser] Bot @mentioned by {display_name}")
                    break

        # Also check text patterns for "cass" etc (fallback)
        mentions_cass_in_text = content_summary.mentions_cass

        # Direct mention = actual @mention OR text pattern match
        is_direct_mention = is_bot_mentioned or mentions_cass_in_text

        # Only store full content if configured and relevant
        content = None
        if DISCORD_CONTENT_LOGGING or is_direct_mention:
            content = message.content

        # Get guild ID (None for DMs)
        guild_id = str(message.guild.id) if message.guild else "dm"
        is_dm = message.guild is None

        return ParsedEvent(
            event_type=EventType.MESSAGE,
            guild_id=guild_id,
            timestamp=message.created_at,
            entity_slug=slug,
            entity_display_name=display_name,
            channel_id=str(message.channel.id),
            channel_name=getattr(message.channel, 'name', 'DM'),
            content_summary=content_summary,
            content=content,
            is_direct_mention=is_direct_mention,
            is_dm=is_dm,
            raw_discord_id=str(message.author.id),
        )

    def parse_presence_update(self, before, after) -> Optional[ParsedEvent]:
        """
        Parse a presence update event.

        Args:
            before: Previous member state
            after: New member state

        Returns:
            ParsedEvent or None if no significant change
        """
        # Only emit event if status changed
        if before.status == after.status:
            return None

        slug, display_name = self._resolve_entity(after)

        # Get activity name if present
        activity = None
        if after.activity:
            activity = after.activity.name

        return ParsedEvent(
            event_type=EventType.PRESENCE,
            guild_id=str(after.guild.id),
            timestamp=datetime.utcnow(),
            entity_slug=slug,
            entity_display_name=display_name,
            status=str(after.status),
            activity=activity,
            raw_discord_id=str(after.id),
        )

    def parse_reaction(self, reaction, user, added: bool = True) -> ParsedEvent:
        """
        Parse a reaction add/remove event.

        Args:
            reaction: discord.Reaction object
            user: discord.User who reacted
            added: True if reaction added, False if removed

        Returns:
            ParsedEvent
        """
        slug, display_name = self._resolve_entity(user)

        guild_id = str(reaction.message.guild.id) if reaction.message.guild else "dm"

        return ParsedEvent(
            event_type=EventType.REACTION,
            guild_id=guild_id,
            timestamp=datetime.utcnow(),
            entity_slug=slug,
            entity_display_name=display_name,
            channel_id=str(reaction.message.channel.id),
            channel_name=getattr(reaction.message.channel, 'name', 'DM'),
            target_message_id=str(reaction.message.id),
            emoji=str(reaction.emoji),
            raw_discord_id=str(user.id),
        )

    def parse_voice_state(self, before, after) -> Optional[ParsedEvent]:
        """
        Parse a voice state update event.

        Args:
            before: Previous voice state
            after: New voice state

        Returns:
            ParsedEvent or None if no significant change
        """
        member = after

        # Determine what changed
        voice_state = None
        channel_id = None
        channel_name = None

        if before.channel is None and after.channel is not None:
            voice_state = "joined"
            channel_id = str(after.channel.id)
            channel_name = after.channel.name
        elif before.channel is not None and after.channel is None:
            voice_state = "left"
            channel_id = str(before.channel.id)
            channel_name = before.channel.name
        elif before.channel != after.channel:
            voice_state = "moved"
            channel_id = str(after.channel.id)
            channel_name = after.channel.name
        elif before.self_mute != after.self_mute:
            voice_state = "muted" if after.self_mute else "unmuted"
            channel_id = str(after.channel.id) if after.channel else None
            channel_name = after.channel.name if after.channel else None
        elif before.self_deaf != after.self_deaf:
            voice_state = "deafened" if after.self_deaf else "undeafened"
            channel_id = str(after.channel.id) if after.channel else None
            channel_name = after.channel.name if after.channel else None
        else:
            return None  # No significant change

        slug, display_name = self._resolve_entity(member)

        return ParsedEvent(
            event_type=EventType.VOICE,
            guild_id=str(member.guild.id),
            timestamp=datetime.utcnow(),
            entity_slug=slug,
            entity_display_name=display_name,
            channel_id=channel_id,
            channel_name=channel_name,
            voice_state=voice_state,
            raw_discord_id=str(member.id),
        )

    def parse_member_join(self, member) -> ParsedEvent:
        """Parse a member join event."""
        slug, display_name = self._resolve_entity(member)

        return ParsedEvent(
            event_type=EventType.MEMBER_JOIN,
            guild_id=str(member.guild.id),
            timestamp=datetime.utcnow(),
            entity_slug=slug,
            entity_display_name=display_name,
            raw_discord_id=str(member.id),
        )

    def parse_member_leave(self, member) -> ParsedEvent:
        """Parse a member leave event."""
        slug, display_name = self._resolve_entity(member)

        return ParsedEvent(
            event_type=EventType.MEMBER_LEAVE,
            guild_id=str(member.guild.id),
            timestamp=datetime.utcnow(),
            entity_slug=slug,
            entity_display_name=display_name,
            raw_discord_id=str(member.id),
        )


# Module-level singleton
_parsers: Dict[str, DiscordEventParser] = {}


def get_event_parser(daemon_id: str) -> DiscordEventParser:
    """Get or create event parser for daemon."""
    if daemon_id not in _parsers:
        _parsers[daemon_id] = DiscordEventParser(daemon_id)
    return _parsers[daemon_id]
