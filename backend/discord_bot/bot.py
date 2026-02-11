"""
Discord Bot - Main bot module with event handlers and action executors

This is the core Discord.py bot that connects to Discord, receives events,
and provides action methods for Cass to send messages and reactions.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any, Callable
from collections import deque

try:
    import discord
    from discord.ext import tasks
    DISCORD_PY_AVAILABLE = True
except ImportError:
    DISCORD_PY_AVAILABLE = False
    discord = None

from discord_bot.config import (
    DISCORD_BOT_TOKEN,
    DISCORD_ENABLED,
    DISCORD_GUILDS,
    DISCORD_SNAPSHOT_INTERVAL,
    DISCORD_MAX_EVENTS_PER_GUILD,
    DISCORD_DAEMON_ID,
    ACTION_RATE_LIMIT_MESSAGES,
    ACTION_RATE_LIMIT_WINDOW,
    validate_config,
)
from discord_bot.event_parser import get_event_parser, ParsedEvent, EventType
from discord_bot.triggers import get_trigger_system, TriggerAction, TriggerResult
from discord_bot.snapshot_generator import (
    get_snapshot_generator,
    PresenceInfo,
    VoiceChannelState,
)
from discord_bot.context import get_perception_context

logger = logging.getLogger("discord_bot.bot")


class CassDiscordBot:
    """
    Discord bot for Cass's perception and action in Discord.

    Provides:
    - Event handlers for messages, presence, reactions, voice
    - Periodic snapshot generation
    - Action methods for sending messages and reactions
    - Rate limiting for actions
    """

    def __init__(self, daemon_id: str = DISCORD_DAEMON_ID):
        """
        Initialize the Discord bot.

        Args:
            daemon_id: Daemon ID for state bus and entity registry
        """
        if not DISCORD_PY_AVAILABLE:
            raise ImportError("discord.py is required for Discord integration. Install with: pip install discord.py")

        self.daemon_id = daemon_id
        self.client: Optional[discord.Client] = None
        self._running = False

        # Event buffer per guild
        self._event_buffers: Dict[str, deque] = {}

        # Rate limiting for actions
        self._action_timestamps: Dict[str, List[datetime]] = {}

        # Components
        self.parser = get_event_parser(daemon_id)
        self.trigger_system = get_trigger_system(daemon_id)
        self.snapshot_generator = get_snapshot_generator(daemon_id)
        self.perception_context = get_perception_context(daemon_id)

        # Wake callback (set by integration code)
        self._wake_callback: Optional[Callable] = None

        # State bus reference (set during startup)
        self._state_bus = None

    def set_wake_callback(self, callback: Callable) -> None:
        """
        Set callback for waking Cass.

        Args:
            callback: Async function called with (event, trigger_result, context)
        """
        self._wake_callback = callback

    def set_state_bus(self, state_bus) -> None:
        """Set state bus reference for emitting deltas."""
        self._state_bus = state_bus

    def _get_event_buffer(self, guild_id: str) -> deque:
        """Get or create event buffer for guild."""
        if guild_id not in self._event_buffers:
            self._event_buffers[guild_id] = deque(maxlen=DISCORD_MAX_EVENTS_PER_GUILD)
        return self._event_buffers[guild_id]

    def _check_rate_limit(self, channel_id: str) -> bool:
        """
        Check if action is within rate limit.

        Returns:
            True if action is allowed, False if rate limited
        """
        now = datetime.now(timezone.utc)
        window_start = now.timestamp() - ACTION_RATE_LIMIT_WINDOW

        if channel_id not in self._action_timestamps:
            self._action_timestamps[channel_id] = []

        # Clean old timestamps
        self._action_timestamps[channel_id] = [
            ts for ts in self._action_timestamps[channel_id]
            if ts.timestamp() > window_start
        ]

        # Check limit
        if len(self._action_timestamps[channel_id]) >= ACTION_RATE_LIMIT_MESSAGES:
            return False

        # Record this action
        self._action_timestamps[channel_id].append(now)
        return True

    async def _process_event(self, event: ParsedEvent) -> None:
        """Process a parsed event through triggers and context."""
        # Add to event buffer
        buffer = self._get_event_buffer(event.guild_id)
        buffer.append(event)

        # Evaluate triggers
        result = self.trigger_system.evaluate(event)

        if result.triggered:
            # Add to perception context
            self.perception_context.add_triggered_event(event, result)

            # Handle wake action
            if result.action == TriggerAction.WAKE_CASS:
                await self._handle_wake(event, result)

            # Emit state delta if configured
            if self._state_bus and result.action == TriggerAction.EMIT_STATE_DELTA:
                self._emit_perception_delta(event, result)

    async def _handle_wake(self, event: ParsedEvent, result: TriggerResult) -> None:
        """Handle WAKE_CASS trigger action."""
        if not self._wake_callback:
            logger.warning("[Bot] Wake triggered but no callback set")
            return

        # Build wake context
        from discord_bot.context import build_wake_context
        snapshot = self.perception_context._snapshots.get(event.guild_id)
        context = build_wake_context(event, result, snapshot)

        try:
            await self._wake_callback(event, result, context)
        except Exception as e:
            logger.error(f"[Bot] Error in wake callback: {e}")

    def _emit_perception_delta(self, event: ParsedEvent, result: TriggerResult) -> None:
        """Emit state delta for perception event."""
        if not self._state_bus:
            return

        from state_models import StateDelta

        delta = StateDelta(
            source="discord_perception",
            event="discord.perception",
            event_data={
                "event_type": event.event_type.value,
                "entity_slug": event.entity_slug,
                "trigger": result.trigger_name,
                "priority": result.priority.value,
            },
        )

        self._state_bus.write_delta(delta)

    def _create_client(self) -> discord.Client:
        """Create and configure Discord client."""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.presences = True
        intents.guild_messages = True
        intents.dm_messages = True
        intents.voice_states = True
        intents.reactions = True

        client = discord.Client(intents=intents)

        # Register event handlers
        @client.event
        async def on_ready():
            logger.info(f"[Bot] Logged in as {client.user}")
            logger.info(f"[Bot] Connected to {len(client.guilds)} guilds")

            # Set bot user ID in parser for @mention detection
            if client.user:
                self.parser.set_bot_user_id(str(client.user.id))

            # Filter to allowed guilds if configured
            if DISCORD_GUILDS:
                for guild in client.guilds:
                    if guild.id not in DISCORD_GUILDS:
                        logger.info(f"[Bot] Ignoring guild {guild.name} (not in allowed list)")

            # Start periodic snapshot task
            if not self._snapshot_task.is_running():
                self._snapshot_task.start()

        @client.event
        async def on_message(message):
            # Ignore bot's own messages
            if message.author == client.user:
                return

            # Check guild filter
            if message.guild and DISCORD_GUILDS and message.guild.id not in DISCORD_GUILDS:
                return

            event = self.parser.parse_message(message)
            await self._process_event(event)

        @client.event
        async def on_presence_update(before, after):
            if DISCORD_GUILDS and after.guild.id not in DISCORD_GUILDS:
                return

            event = self.parser.parse_presence_update(before, after)
            if event:
                await self._process_event(event)

        @client.event
        async def on_reaction_add(reaction, user):
            if user == client.user:
                return

            if reaction.message.guild and DISCORD_GUILDS and reaction.message.guild.id not in DISCORD_GUILDS:
                return

            event = self.parser.parse_reaction(reaction, user, added=True)
            await self._process_event(event)

        @client.event
        async def on_voice_state_update(member, before, after):
            if DISCORD_GUILDS and member.guild.id not in DISCORD_GUILDS:
                return

            event = self.parser.parse_voice_state(before, after)
            if event:
                await self._process_event(event)

        @client.event
        async def on_member_join(member):
            if DISCORD_GUILDS and member.guild.id not in DISCORD_GUILDS:
                return

            event = self.parser.parse_member_join(member)
            await self._process_event(event)

        @client.event
        async def on_member_remove(member):
            if DISCORD_GUILDS and member.guild.id not in DISCORD_GUILDS:
                return

            event = self.parser.parse_member_leave(member)
            await self._process_event(event)

        return client

    @tasks.loop(seconds=DISCORD_SNAPSHOT_INTERVAL)
    async def _snapshot_task(self):
        """Periodic task to generate snapshots."""
        if not self.client or not self.client.is_ready():
            return

        for guild in self.client.guilds:
            if DISCORD_GUILDS and guild.id not in DISCORD_GUILDS:
                continue

            try:
                await self._generate_snapshot(guild)
            except Exception as e:
                logger.error(f"[Bot] Error generating snapshot for {guild.name}: {e}")

    async def _generate_snapshot(self, guild) -> str:
        """Generate snapshot for a guild."""
        guild_id = str(guild.id)

        # Gather channel info
        channels = []
        voice_states = []

        for channel in guild.channels:
            if isinstance(channel, discord.TextChannel):
                channels.append({
                    "id": str(channel.id),
                    "name": channel.name,
                    "type": "text",
                })
            elif isinstance(channel, discord.VoiceChannel):
                channels.append({
                    "id": str(channel.id),
                    "name": channel.name,
                    "type": "voice",
                })

                # Get voice state
                members = []
                for member in channel.members:
                    entity = self.parser.registry.get_by_discord_id(str(member.id))
                    if entity:
                        members.append({
                            "slug": entity.slug,
                            "muted": member.voice.self_mute if member.voice else False,
                            "deafened": member.voice.self_deaf if member.voice else False,
                        })

                if members:
                    voice_states.append(VoiceChannelState(
                        channel_id=str(channel.id),
                        channel_name=channel.name,
                        members=members,
                    ))

        # Gather presence info
        presences: Dict[str, PresenceInfo] = {}
        for member in guild.members:
            entity = self.parser.registry.get_by_discord_id(str(member.id))
            if not entity:
                continue

            presences[entity.slug] = PresenceInfo(
                slug=entity.slug,
                display_name=entity.display_name,
                status=str(member.status),
                activity=member.activity.name if member.activity else None,
                relationship_tier=entity.relationship_tier,
            )

        # Get recent events from buffer
        buffer = self._get_event_buffer(guild_id)
        recent_events = list(buffer)

        # Generate snapshot
        snapshot = self.snapshot_generator.generate_snapshot(
            guild_name=guild.name,
            guild_id=guild_id,
            channels=channels,
            presences=presences,
            recent_events=recent_events,
            voice_states=voice_states,
        )

        # Update perception context
        self.perception_context.update_snapshot(guild_id, snapshot)

        logger.debug(f"[Bot] Generated snapshot for {guild.name}")

        return snapshot

    # === Action Methods ===

    async def send_message(
        self,
        channel_id: str,
        content: str,
        reply_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a message to a channel.

        Args:
            channel_id: Discord channel ID
            content: Message content
            reply_to: Optional message ID to reply to

        Returns:
            Dict with success status and message info
        """
        if not self.client or not self.client.is_ready():
            return {"success": False, "error": "Bot not connected"}

        # Check rate limit
        if not self._check_rate_limit(channel_id):
            return {"success": False, "error": "Rate limited"}

        try:
            channel = self.client.get_channel(int(channel_id))
            if not channel:
                # DM channels aren't cached - need to fetch them
                try:
                    channel = await self.client.fetch_channel(int(channel_id))
                except Exception as e:
                    logger.warning(f"[Bot] Failed to fetch channel {channel_id}: {e}")
                    return {"success": False, "error": f"Channel {channel_id} not found"}

            # Get reply reference if provided
            reference = None
            if reply_to:
                try:
                    reference = discord.MessageReference(
                        message_id=int(reply_to),
                        channel_id=int(channel_id),
                    )
                except Exception:
                    pass  # Ignore invalid reference

            # Discord has a 2000 character limit - split if needed
            DISCORD_MAX_LENGTH = 2000
            if len(content) <= DISCORD_MAX_LENGTH:
                message = await channel.send(content, reference=reference)
            else:
                # Split into chunks, trying to break at newlines
                chunks = []
                remaining = content
                while remaining:
                    if len(remaining) <= DISCORD_MAX_LENGTH:
                        chunks.append(remaining)
                        break
                    # Find a good break point (newline or space)
                    break_at = DISCORD_MAX_LENGTH
                    # Try to break at a newline
                    newline_pos = remaining.rfind('\n', 0, DISCORD_MAX_LENGTH)
                    if newline_pos > DISCORD_MAX_LENGTH // 2:
                        break_at = newline_pos + 1
                    else:
                        # Try to break at a space
                        space_pos = remaining.rfind(' ', 0, DISCORD_MAX_LENGTH)
                        if space_pos > DISCORD_MAX_LENGTH // 2:
                            break_at = space_pos + 1
                    chunks.append(remaining[:break_at])
                    remaining = remaining[break_at:]

                # Send all chunks - first one with reply reference
                message = None
                for i, chunk in enumerate(chunks):
                    ref = reference if i == 0 else None
                    message = await channel.send(chunk, reference=ref)
                    # Small delay between chunks to avoid rate limits
                    if i < len(chunks) - 1:
                        await asyncio.sleep(0.5)

            return {
                "success": True,
                "message_id": str(message.id),
                "channel": channel.name if hasattr(channel, 'name') else "DM",
            }

        except discord.Forbidden:
            return {"success": False, "error": "Missing permissions"}
        except Exception as e:
            logger.error(f"[Bot] Error sending message: {e}")
            return {"success": False, "error": str(e)}

    async def add_reaction(
        self,
        channel_id: str,
        message_id: str,
        emoji: str,
    ) -> Dict[str, Any]:
        """
        Add a reaction to a message.

        Args:
            channel_id: Discord channel ID
            message_id: Message ID to react to
            emoji: Emoji to add (unicode or custom format)

        Returns:
            Dict with success status
        """
        if not self.client or not self.client.is_ready():
            return {"success": False, "error": "Bot not connected"}

        try:
            channel = self.client.get_channel(int(channel_id))
            if not channel:
                # DM channels aren't cached - need to fetch them
                try:
                    channel = await self.client.fetch_channel(int(channel_id))
                except Exception:
                    return {"success": False, "error": f"Channel {channel_id} not found"}

            message = await channel.fetch_message(int(message_id))
            await message.add_reaction(emoji)

            return {"success": True}

        except discord.Forbidden:
            return {"success": False, "error": "Missing permissions"}
        except discord.NotFound:
            return {"success": False, "error": "Message not found"}
        except Exception as e:
            logger.error(f"[Bot] Error adding reaction: {e}")
            return {"success": False, "error": str(e)}

    async def get_channel_history(
        self,
        channel_id: str,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """
        Get recent message history from a channel.

        Args:
            channel_id: Discord channel ID
            limit: Maximum messages to fetch

        Returns:
            Dict with messages list
        """
        if not self.client or not self.client.is_ready():
            return {"success": False, "error": "Bot not connected"}

        try:
            channel = self.client.get_channel(int(channel_id))
            if not channel:
                # DM channels aren't cached - need to fetch them
                try:
                    channel = await self.client.fetch_channel(int(channel_id))
                except Exception:
                    return {"success": False, "error": f"Channel {channel_id} not found"}

            messages = []
            async for message in channel.history(limit=limit):
                entity = self.parser.registry.get_by_discord_id(str(message.author.id))
                messages.append({
                    "id": str(message.id),
                    "author_slug": entity.slug if entity else None,
                    "author_name": message.author.display_name,
                    "content": message.content,
                    "timestamp": message.created_at.isoformat(),
                })

            return {"success": True, "messages": messages}

        except Exception as e:
            logger.error(f"[Bot] Error fetching history: {e}")
            return {"success": False, "error": str(e)}

    # === Lifecycle Methods ===

    async def start(self) -> None:
        """Start the Discord bot."""
        is_valid, error = validate_config()
        if not is_valid:
            logger.error(f"[Bot] Configuration invalid: {error}")
            return

        if not DISCORD_ENABLED:
            logger.info("[Bot] Discord disabled (DISCORD_ENABLED=false)")
            return

        self.client = self._create_client()
        self._running = True

        logger.info("[Bot] Starting Discord bot...")
        await self.client.start(DISCORD_BOT_TOKEN)

    async def stop(self) -> None:
        """Stop the Discord bot."""
        self._running = False

        if self._snapshot_task.is_running():
            self._snapshot_task.cancel()

        if self.client:
            await self.client.close()
            logger.info("[Bot] Discord bot stopped")

    def is_running(self) -> bool:
        """Check if bot is running."""
        return self._running and self.client and self.client.is_ready()

    def get_stats(self) -> Dict[str, Any]:
        """Get bot statistics."""
        stats = {
            "running": self.is_running(),
            "guilds": 0,
            "total_events_buffered": sum(len(b) for b in self._event_buffers.values()),
        }

        if self.client and self.client.is_ready():
            stats["guilds"] = len(self.client.guilds)
            stats["guild_names"] = [g.name for g in self.client.guilds]

        stats["trigger_stats"] = self.trigger_system.get_trigger_stats()
        stats["context_stats"] = self.perception_context.get_stats()
        stats["entity_stats"] = self.parser.registry.get_stats()

        return stats


# Module-level singleton
_bot_instance: Optional[CassDiscordBot] = None


def get_discord_bot(daemon_id: str = DISCORD_DAEMON_ID) -> CassDiscordBot:
    """Get or create Discord bot instance."""
    global _bot_instance
    if _bot_instance is None:
        _bot_instance = CassDiscordBot(daemon_id)
    return _bot_instance


async def start_discord_bot(daemon_id: str = DISCORD_DAEMON_ID) -> Optional[CassDiscordBot]:
    """Start Discord bot if enabled and configured."""
    if not DISCORD_PY_AVAILABLE:
        logger.warning("[Bot] discord.py not installed, Discord integration disabled")
        return None

    if not DISCORD_ENABLED:
        logger.info("[Bot] Discord disabled (DISCORD_ENABLED=false)")
        return None

    bot = get_discord_bot(daemon_id)

    # Start in background task
    asyncio.create_task(bot.start())

    return bot
