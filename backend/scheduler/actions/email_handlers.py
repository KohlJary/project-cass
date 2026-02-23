"""
Email action handlers - autonomous email checking and processing.

These actions enable Cass to check her inbox during phase transitions
and process/respond to emails autonomously.
"""

import logging
from typing import Any, Dict

from . import ActionResult

logger = logging.getLogger(__name__)


async def check_inbox_action(context: Dict[str, Any]) -> ActionResult:
    """
    Check inbox for unprocessed emails and notify Cass.

    This action is run on phase transitions to surface new emails.
    It doesn't auto-respond - just queues notification for Cass's attention.
    """
    managers = context.get("managers", {})
    daemon_id = managers.get("daemon_id", "cass")

    try:
        from email_organ import get_email_manager

        email_manager = get_email_manager(daemon_id)
        unprocessed = email_manager.get_unprocessed()

        if not unprocessed:
            logger.info("[Email] No unprocessed emails in inbox")
            return ActionResult(
                success=True,
                message="Inbox checked - no new emails",
                data={"email_count": 0}
            )

        # Format summary for logging/notification
        summaries = []
        for email in unprocessed[:5]:  # Limit to 5 for summary
            summaries.append(f"- From: {email.from_address}, Subject: {email.subject}")

        summary_text = "\n".join(summaries)
        if len(unprocessed) > 5:
            summary_text += f"\n... and {len(unprocessed) - 5} more"

        logger.info(f"[Email] Found {len(unprocessed)} unprocessed emails:\n{summary_text}")

        # Emit state bus event so Cass can be notified
        state_bus = managers.get("state_bus")
        if state_bus:
            from state_models import StateDelta

            delta = StateDelta(
                source="email_action",
                event="email.inbox_checked",
                event_data={
                    "unprocessed_count": len(unprocessed),
                    "emails": [
                        {
                            "id": e.id,
                            "from": e.from_address,
                            "subject": e.subject,
                            "goal_id": e.goal_id,
                            "stakeholder_id": e.stakeholder_id,
                        }
                        for e in unprocessed[:10]
                    ],
                },
                reason=f"Found {len(unprocessed)} unprocessed emails",
            )
            state_bus.write_delta(delta)

        return ActionResult(
            success=True,
            message=f"Found {len(unprocessed)} unprocessed emails",
            data={
                "email_count": len(unprocessed),
                "summaries": summaries,
            }
        )

    except Exception as e:
        logger.error(f"[Email] Failed to check inbox: {e}")
        return ActionResult(
            success=False,
            message=f"Failed to check inbox: {e}",
        )


async def process_inbox_action(context: Dict[str, Any]) -> ActionResult:
    """
    Process unread emails by spawning a conversation for Cass to handle them.

    This is a more active action that triggers Cass to actually respond
    to emails, not just check them.
    """
    managers = context.get("managers", {})
    runners = context.get("runners", {})
    daemon_id = managers.get("daemon_id", "cass")

    try:
        from email_organ import get_email_manager

        email_manager = get_email_manager(daemon_id)
        unprocessed = email_manager.get_unprocessed()

        if not unprocessed:
            return ActionResult(
                success=True,
                message="No emails to process",
                data={"processed": 0}
            )

        # Get reflection runner to spawn email processing session
        reflection_runner = runners.get("reflection")
        if not reflection_runner:
            logger.warning("[Email] No reflection runner available for email processing")
            return ActionResult(
                success=False,
                message="Reflection runner not available",
            )

        # Build context for Cass to process emails
        email_context = []
        for email in unprocessed[:3]:  # Process up to 3 at a time
            email_context.append(email.format_summary())
            # Mark as processing so we don't double-process
            email_manager.mark_processing(email.id)

        prompt = f"""You have {len(unprocessed)} unread emails. Here are the first {min(3, len(unprocessed))}:

{chr(10).join(email_context)}

Please review each email and decide how to respond:
1. Use `send_email` to reply if needed
2. Use `mark_email_read` when done processing each one
3. If an email relates to a goal, use `link_stakeholder` to connect the sender

Be professional and helpful in your responses."""

        # Run reflection session with email context
        result = await reflection_runner.run_session(
            session_type="email_processing",
            focus=prompt,
            duration_minutes=context.get("duration_minutes", 15),
        )

        return ActionResult(
            success=True,
            message=f"Processed {min(3, len(unprocessed))} emails",
            cost_usd=result.get("cost_usd", 0.0),
            data={
                "processed": min(3, len(unprocessed)),
                "remaining": max(0, len(unprocessed) - 3),
            }
        )

    except Exception as e:
        logger.error(f"[Email] Failed to process inbox: {e}")
        return ActionResult(
            success=False,
            message=f"Failed to process inbox: {e}",
        )
