"""Which Cass conversation a Discord channel's turns belong to.

Shared by the wake callback (main_sdk) and by actions that send on her own
initiative (scheduler/actions/discord_handlers.py), so a DM she starts and
the reply that wakes her land in the same conversation.
"""


def dm_conversation_title(display_name: str) -> str:
    return f"Discord DM: {display_name}"


def channel_conversation_title(channel_name: str) -> str:
    return f"Discord #{channel_name}"


def discord_conversation_id(conversation_manager, user_id: str, title: str) -> str:
    """The conversation a linked Discord user's turns go to: one per
    (user, channel title), found again by title, created on first use.
    Renaming it in the UI starts a new one on the next message."""
    from database import get_db
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM conversations WHERE daemon_id = ? AND user_id = ? "
            "AND title = ? AND is_continuous = 0 ORDER BY updated_at DESC LIMIT 1",
            (conversation_manager.daemon_id, user_id, title),
        ).fetchone()
    if row:
        return row["id"]
    return conversation_manager.create_conversation(title=title, user_id=user_id).id
