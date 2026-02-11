"""
Discord Bot Configuration

Environment variables for Discord integration.
"""

import os
from typing import Optional, List


# Discord bot token (required for operation)
DISCORD_BOT_TOKEN: Optional[str] = os.getenv("DISCORD_BOT_TOKEN")

# Master enable flag
DISCORD_ENABLED: bool = os.getenv("DISCORD_ENABLED", "false").lower() == "true"

# Allowed guild IDs (comma-separated, empty = all joined guilds)
_guilds_str = os.getenv("DISCORD_GUILDS", "")
DISCORD_GUILDS: List[int] = [int(g.strip()) for g in _guilds_str.split(",") if g.strip()]

# Snapshot interval in seconds (default: 5 minutes)
DISCORD_SNAPSHOT_INTERVAL: int = int(os.getenv("DISCORD_SNAPSHOT_INTERVAL", "300"))

# Whether to log full message content (privacy setting)
# When False, only content_summary (length, sentiment, mentions) is stored
DISCORD_CONTENT_LOGGING: bool = os.getenv("DISCORD_CONTENT_LOGGING", "false").lower() == "true"

# Maximum events to keep in memory per guild
DISCORD_MAX_EVENTS_PER_GUILD: int = int(os.getenv("DISCORD_MAX_EVENTS_PER_GUILD", "500"))

# Daemon ID for state bus (should match main Cass daemon)
DISCORD_DAEMON_ID: str = os.getenv("DISCORD_DAEMON_ID", "cass")

# Trigger thresholds
TRIGGER_IMMEDIATE_KEYWORDS: List[str] = ["@cass", "cass,", "hey cass", "hi cass"]
TRIGGER_FRIEND_TIER_THRESHOLD: str = "friend"  # minimum tier for elevated attention

# Action rate limits (messages per minute per channel)
ACTION_RATE_LIMIT_MESSAGES: int = int(os.getenv("DISCORD_RATE_LIMIT_MESSAGES", "5"))
ACTION_RATE_LIMIT_WINDOW: int = 60  # seconds


def validate_config() -> tuple[bool, str]:
    """
    Validate Discord configuration.

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not DISCORD_ENABLED:
        return True, "Discord disabled (DISCORD_ENABLED=false)"

    if not DISCORD_BOT_TOKEN:
        return False, "DISCORD_BOT_TOKEN environment variable not set"

    return True, "Configuration valid"
