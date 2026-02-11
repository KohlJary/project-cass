"""
Discord Perception Module - Cass's eyes and ears into Discord

This module enables Cass to perceive social dynamics in Discord servers,
react to events, and take actions. It integrates with the existing state
bus architecture and PeopleDex for entity management.

Components:
- bot.py: Main Discord bot with event handlers and action executors
- entity_registry.py: Discord ID → PeopleDex entity mapping
- event_parser.py: Raw Discord events → structured perception events
- snapshot_generator.py: Ophanic-format spatial snapshots
- triggers.py: Event trigger evaluation for Cass attention
- context.py: Perception context assembly for prompts
- config.py: Discord-specific configuration
"""

from discord_bot.config import DISCORD_ENABLED

__all__ = ["DISCORD_ENABLED"]
