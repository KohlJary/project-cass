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
    Check inbox for unprocessed emails and auto-respond to priority senders.

    Priority senders (auto-respond):
    - Emails linked to goal stakeholders
    - Emails from Kohl (primary user)

    Other emails are just surfaced for Cass's attention.
    """
    managers = context.get("managers", {})
    runners = context.get("runners", {})
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

        # Categorize emails
        auto_respond = []  # Stakeholders or Kohl
        notify_only = []   # Others

        for email in unprocessed:
            should_auto = _should_auto_respond(email, daemon_id)
            if should_auto:
                auto_respond.append(email)
            else:
                notify_only.append(email)

        # Format summary for logging
        summaries = []
        for email in unprocessed[:5]:
            summaries.append(f"- From: {email.from_address}, Subject: {email.subject}")

        summary_text = "\n".join(summaries)
        if len(unprocessed) > 5:
            summary_text += f"\n... and {len(unprocessed) - 5} more"

        logger.info(f"[Email] Found {len(unprocessed)} unprocessed emails:\n{summary_text}")
        logger.info(f"[Email] Auto-respond: {len(auto_respond)}, Notify only: {len(notify_only)}")

        # Emit state bus event
        state_bus = managers.get("state_bus")
        if state_bus:
            from state_models import StateDelta

            delta = StateDelta(
                source="email_action",
                event="email.inbox_checked",
                event_data={
                    "unprocessed_count": len(unprocessed),
                    "auto_respond_count": len(auto_respond),
                    "emails": [
                        {
                            "id": e.id,
                            "from": e.from_address,
                            "subject": e.subject,
                            "goal_id": e.goal_id,
                            "stakeholder_id": e.stakeholder_id,
                            "auto_respond": e in auto_respond,
                        }
                        for e in unprocessed[:10]
                    ],
                },
                reason=f"Found {len(unprocessed)} unprocessed emails ({len(auto_respond)} priority)",
            )
            state_bus.write_delta(delta)

        # Auto-respond to priority emails
        responded = 0
        total_cost = 0.0

        if auto_respond and managers.get("session_runner"):
            for email in auto_respond[:3]:  # Limit to 3 at a time
                try:
                    result = await _auto_respond_to_email(
                        email, email_manager, runners, managers
                    )
                    if result.get("success"):
                        responded += 1
                        total_cost += result.get("cost_usd", 0.0)
                except Exception as e:
                    logger.error(f"[Email] Auto-respond failed for {email.id}: {e}")

        return ActionResult(
            success=True,
            message=f"Found {len(unprocessed)} emails, auto-responded to {responded}",
            cost_usd=total_cost,
            data={
                "email_count": len(unprocessed),
                "auto_responded": responded,
                "notify_only": len(notify_only),
                "summaries": summaries,
            }
        )

    except Exception as e:
        logger.error(f"[Email] Failed to check inbox: {e}")
        return ActionResult(
            success=False,
            message=f"Failed to check inbox: {e}",
        )


def _should_auto_respond(email, daemon_id: str) -> bool:
    """
    Determine if an email should get an auto-response.

    Auto-respond to:
    1. Emails from stakeholders linked to active goals
    2. Emails from Kohl (primary user) - matched by PeopleDex
    """
    # If email is already linked to a stakeholder, auto-respond
    if email.stakeholder_id:
        return True

    # If email is linked to a goal, auto-respond
    if email.goal_id:
        return True

    # Check if sender is in PeopleDex as a known contact
    try:
        from database import get_db
        import re

        # Extract email address from "Name <email>" format
        match = re.search(r'<([^>]+)>', email.from_address)
        sender_email = match.group(1) if match else email.from_address

        with get_db() as conn:
            # Check if sender is in PeopleDex with "primary_user" or "kohl" tag
            # or has relationship type indicating they're important
            cursor = conn.execute("""
                SELECT e.id, e.primary_name
                FROM peopledex_entities e
                JOIN peopledex_attributes a ON e.id = a.entity_id
                WHERE a.attribute_type = 'email'
                AND LOWER(a.value) = LOWER(?)
                AND e.daemon_id = ?
            """, (sender_email, daemon_id))

            row = cursor.fetchone()
            if row:
                entity_id = row['id']
                primary_name = row['primary_name']

                # Check if this is Kohl or a primary user
                cursor2 = conn.execute("""
                    SELECT value FROM peopledex_attributes
                    WHERE entity_id = ? AND attribute_type = 'tag'
                    AND LOWER(value) IN ('primary_user', 'kohl', 'creator', 'partner')
                """, (entity_id,))

                if cursor2.fetchone():
                    logger.info(f"[Email] Auto-respond: {primary_name} is a primary contact")
                    return True

                # Also check if they're linked to any goal as stakeholder
                cursor3 = conn.execute("""
                    SELECT goal_id FROM goal_stakeholders
                    WHERE entity_id = ?
                    LIMIT 1
                """, (entity_id,))

                if cursor3.fetchone():
                    logger.info(f"[Email] Auto-respond: {primary_name} is a goal stakeholder")
                    return True

        return False

    except Exception as e:
        logger.warning(f"[Email] Error checking auto-respond status: {e}")
        return False


async def _auto_respond_to_email(
    email,
    email_manager,
    runners: Dict[str, Any],
    managers: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Generate and send an auto-response to an email.

    Uses the session runner to have Cass compose a thoughtful reply.
    """
    # Use GenericSessionRunner from managers (has run_session method)
    session_runner = managers.get("session_runner")
    if not session_runner:
        return {"success": False, "error": "No session runner"}

    # Mark as processing
    email_manager.mark_processing(email.id)

    # Get thread context if this is a reply
    thread_context = ""
    if email.thread_id:
        thread_context = email_manager.format_thread_context(email.thread_id)

    # Get stakeholder context if linked
    stakeholder_context = ""
    if email.stakeholder_id:
        try:
            from peopledex import get_peopledex_manager
            pdex = get_peopledex_manager(managers.get("daemon_id", "cass"))
            profile = pdex.get_full_profile(email.stakeholder_id)
            if profile:
                # Build summary from profile
                entity = profile.entity
                attrs = profile.attributes
                summary_lines = [f"**{entity.primary_name}** ({entity.entity_type.value})"]
                for attr in attrs[:5]:  # Limit attributes
                    if attr.attribute_type.value in ['role', 'bio', 'organization', 'email']:
                        summary_lines.append(f"- {attr.attribute_type.value}: {attr.value}")
                stakeholder_context = f"\n## About the Sender\n" + "\n".join(summary_lines) + "\n"
        except Exception as e:
            logger.warning(f"[Email] Could not get stakeholder context: {e}")

    # Get goal context if linked
    goal_context = ""
    if email.goal_id:
        try:
            from unified_goals import UnifiedGoalManager
            gm = UnifiedGoalManager(daemon_id=managers.get("daemon_id", "cass"))
            goal = gm.get_goal(email.goal_id)
            if goal:
                goal_context = f"\n## Related Goal\n**{goal.title}**\n{goal.description}\n"
        except Exception as e:
            logger.warning(f"[Email] Could not get goal context: {e}")

    # Build prompt for Cass
    prompt = f"""You have received an email that needs a response.

## Incoming Email
**From:** {email.from_address}
**Subject:** {email.subject}
**Date:** {email.created_at}

{email.body_plain or "(no body)"}
{stakeholder_context}{goal_context}{thread_context}

Please compose a thoughtful, professional reply to this email. Consider:
1. The relationship with the sender (if known)
2. Any relevant goal context
3. Previous conversation thread (if any)
4. Maintaining your authentic voice while being helpful

After composing your reply, use the `send_email` tool to send it.
Use `in_reply_to` with the message ID for proper threading.

Email ID: {email.id}
Message ID for reply: {email.message_id or email.id}
"""

    try:
        # Import email tools for the session
        from handlers.email import EMAIL_TOOLS, execute_email_tool

        # Filter to just the tools we need
        email_tools = [t for t in EMAIL_TOOLS if t["name"] in ["send_email", "mark_email_read", "get_email_thread"]]

        # Build system prompt for email response
        system_prompt = """You are responding to an email. You should:
1. Read the email carefully and understand the context
2. Draft a thoughtful, professional response
3. Use the send_email tool to send your response
4. Mark the email as read when done

Be helpful, clear, and maintain your authentic voice. If the sender is a known stakeholder or contact, personalize your response appropriately."""

        # Register email tool handlers with the session runner
        from email_organ import get_email_manager as get_em
        daemon_id = managers.get("daemon_id", "cass")
        email_manager_for_tools = get_em(daemon_id)

        # Create tool handlers that match GenericSessionRunner signature
        async def handle_send_email(tool_input: dict, **kwargs) -> str:
            return await execute_email_tool(
                tool_name="send_email",
                tool_input=tool_input,
                daemon_id=daemon_id,
                email_manager=email_manager_for_tools,
            )

        async def handle_mark_email_read(tool_input: dict, **kwargs) -> str:
            return await execute_email_tool(
                tool_name="mark_email_read",
                tool_input=tool_input,
                daemon_id=daemon_id,
                email_manager=email_manager_for_tools,
            )

        async def handle_get_email_thread(tool_input: dict, **kwargs) -> str:
            return await execute_email_tool(
                tool_name="get_email_thread",
                tool_input=tool_input,
                daemon_id=daemon_id,
                email_manager=email_manager_for_tools,
            )

        # Register handlers for email tools
        session_runner.register_tool_handlers({
            "send_email": handle_send_email,
            "mark_email_read": handle_mark_email_read,
            "get_email_thread": handle_get_email_thread,
        })

        # Run session to compose and send reply
        result = await session_runner.run_session(
            session_type="email_response",
            system_prompt=system_prompt,
            tools=email_tools,
            focus=prompt,
            duration_minutes=10,
            max_turns=5,
        )

        # Mark as processed
        email_manager.mark_processed(email.id)

        logger.info(f"[Email] Auto-responded to email from {email.from_address}")

        return {
            "success": True,
            "email_id": email.id,
            "cost_usd": getattr(result, "estimated_cost_usd", 0.0),
        }

    except Exception as e:
        logger.error(f"[Email] Auto-response failed: {e}")
        # Don't mark as processed so it can be retried
        return {"success": False, "error": str(e)}


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
