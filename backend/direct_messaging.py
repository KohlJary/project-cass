"""
Direct Messaging - Cass-initiated messages to users.

Enables Cass to proactively reach out to users via push notifications,
with messages stored in conversation history for continuity.
"""

import logging
from datetime import datetime
from typing import Optional

from conversations import ConversationManager
from quiet_hours import is_quiet_hours
from relay_client import get_relay_client

logger = logging.getLogger(__name__)


async def send_direct_message(
    user_id: str,
    message: str,
    conversation_manager: ConversationManager,
    conversation_id: Optional[str] = None,
    title: str = "Cass",
    respect_quiet_hours: bool = True,
    source: str = "cass_initiated",
) -> dict:
    """
    Send a Cass-initiated message to a user.

    The message is stored in conversation history and a push notification
    is sent to alert the user.

    Args:
        user_id: Target user ID
        message: Message content from Cass
        conversation_manager: For storing message in history
        conversation_id: Optional specific conversation, defaults to continuous
        title: Push notification title (default "Cass")
        respect_quiet_hours: Whether to check quiet hours (default True)
        source: Source tag for the message (default "cass_initiated")

    Returns:
        dict with status and details
    """
    # Check quiet hours if enabled
    if respect_quiet_hours and is_quiet_hours(user_id):
        logger.info(f"[DirectMessage] Skipping - quiet hours for user {user_id}")
        return {
            "success": False,
            "reason": "quiet_hours",
            "message": "User is in quiet hours. Message not sent.",
        }

    # Get or create continuous conversation for this user
    if not conversation_id:
        continuous_conv = conversation_manager.get_or_create_continuous(user_id)
        conversation_id = continuous_conv.id
        logger.info(f"[DirectMessage] Using continuous conversation {conversation_id}")

    # Store message in conversation history
    conversation_manager.add_message(
        conversation_id=conversation_id,
        role="assistant",
        content=message,
        # Mark as Cass-initiated for context
    )
    logger.info(f"[DirectMessage] Stored message in conversation {conversation_id}")

    # Send push notification via relay
    relay_client = get_relay_client()
    if not relay_client or not relay_client.is_connected:
        logger.warning("[DirectMessage] Relay client not connected, cannot send push")
        return {
            "success": False,
            "reason": "relay_offline",
            "message": "Message stored but push notification failed - relay offline.",
            "conversation_id": conversation_id,
        }

    # Truncate message for push notification body
    push_body = message[:150] + "..." if len(message) > 150 else message

    push_sent = await relay_client.send_push(
        user_id=user_id,
        title=title,
        body=push_body,
        data={
            "type": "cass_message",  # Mobile expects this to handle foreground notifications
            "conversation_id": conversation_id,
            "source": source,
            "text": message,  # Full message text for foreground display
            "timestamp": datetime.now().isoformat(),
        },
    )

    if push_sent:
        logger.info(f"[DirectMessage] Push notification sent to user {user_id}")
        return {
            "success": True,
            "conversation_id": conversation_id,
            "message": "Message sent successfully.",
        }
    else:
        logger.warning(f"[DirectMessage] Failed to send push to user {user_id}")
        return {
            "success": False,
            "reason": "push_failed",
            "message": "Message stored but push notification failed.",
            "conversation_id": conversation_id,
        }
