"""
Email tool handler - enables Cass to send and receive email.

These tools allow Cass to:
- Send emails to stakeholders and contacts
- Check inbox for new messages
- View email threads
- Get emails related to goals
"""
from typing import Dict, Optional, List

from email_organ import (
    EmailManager,
    get_email_manager,
)


# Tool definitions for agent_client.py
EMAIL_TOOLS = [
    {
        "name": "send_email",
        "description": "Send an email to a stakeholder or contact. Use for outreach, follow-ups, or responses. Always draft professionally and include context about why you're reaching out. The email will be sent from cass@<configured-domain>.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient email address"
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject line"
                },
                "body": {
                    "type": "string",
                    "description": "Email body (plain text). Write professionally and clearly."
                },
                "goal_id": {
                    "type": "string",
                    "description": "ID of related goal (for tracking). Include if this email is part of goal execution."
                },
                "in_reply_to": {
                    "type": "string",
                    "description": "Message ID if this is a reply to a previous email (for threading)"
                }
            },
            "required": ["to", "subject", "body"]
        }
    },
    {
        "name": "check_inbox",
        "description": "Check for new inbound emails that need attention. Returns unprocessed emails with sender, subject, and preview.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_email_thread",
        "description": "Get the full conversation thread for an email. Use to understand context before replying.",
        "input_schema": {
            "type": "object",
            "properties": {
                "thread_id": {
                    "type": "string",
                    "description": "Thread ID to retrieve (from email metadata)"
                }
            },
            "required": ["thread_id"]
        }
    },
    {
        "name": "get_goal_emails",
        "description": "Get all emails related to a specific goal. Useful for reviewing communication history during goal execution.",
        "input_schema": {
            "type": "object",
            "properties": {
                "goal_id": {
                    "type": "string",
                    "description": "Goal ID to get emails for"
                }
            },
            "required": ["goal_id"]
        }
    },
    {
        "name": "mark_email_read",
        "description": "Mark an email as processed/read after reviewing it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "email_id": {
                    "type": "string",
                    "description": "ID of the email to mark as read"
                }
            },
            "required": ["email_id"]
        }
    },
    {
        "name": "get_email_stats",
        "description": "Get email statistics - total sent, received, unprocessed count.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]


async def execute_email_tool(
    tool_name: str,
    tool_input: Dict,
    daemon_id: str,
    email_manager: Optional[EmailManager] = None,
    conversation_id: Optional[str] = None,
) -> Dict:
    """
    Execute an email tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        daemon_id: The daemon ID
        email_manager: EmailManager instance (created if not provided)
        conversation_id: Current conversation ID (for linking)

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    try:
        # Initialize manager if not provided
        if email_manager is None:
            email_manager = get_email_manager(daemon_id)

        if tool_name == "send_email":
            return await _send_email(email_manager, tool_input, conversation_id)

        elif tool_name == "check_inbox":
            return await _check_inbox(email_manager)

        elif tool_name == "get_email_thread":
            return await _get_email_thread(email_manager, tool_input)

        elif tool_name == "get_goal_emails":
            return await _get_goal_emails(email_manager, tool_input)

        elif tool_name == "mark_email_read":
            return await _mark_email_read(email_manager, tool_input)

        elif tool_name == "get_email_stats":
            return await _get_email_stats(email_manager)

        else:
            return {
                "success": False,
                "error": f"Unknown email tool: {tool_name}"
            }

    except Exception as e:
        return {
            "success": False,
            "error": f"Email tool error: {str(e)}"
        }


async def _send_email(
    manager: EmailManager,
    tool_input: Dict,
    conversation_id: Optional[str] = None,
) -> Dict:
    """Send an email."""
    to = tool_input.get("to")
    subject = tool_input.get("subject")
    body = tool_input.get("body")

    if not to:
        return {"success": False, "error": "Recipient email address (to) is required"}
    if not subject:
        return {"success": False, "error": "Subject is required"}
    if not body:
        return {"success": False, "error": "Body is required"}

    # Send email
    result = await manager.send_email(
        to=to,
        subject=subject,
        body_plain=body,
        goal_id=tool_input.get("goal_id"),
        in_reply_to=tool_input.get("in_reply_to"),
        conversation_id=conversation_id,
    )

    if result.get("success"):
        return {
            "success": True,
            "result": f"Email sent successfully to {to}.\nSubject: {subject}\nEmail ID: {result.get('email_id')}"
        }
    else:
        return {
            "success": False,
            "error": f"Failed to send email: {result.get('error')}"
        }


async def _check_inbox(manager: EmailManager) -> Dict:
    """Check for unprocessed emails."""
    emails = manager.get_unprocessed()

    if not emails:
        return {
            "success": True,
            "result": "No new emails in inbox."
        }

    lines = [f"## Inbox ({len(emails)} unread)\n"]

    for email in emails:
        lines.append(f"### {email.subject or '(no subject)'}")
        lines.append(f"- **From:** {email.from_address}")
        lines.append(f"- **Date:** {email.created_at}")
        lines.append(f"- **Email ID:** {email.id}")
        if email.thread_id:
            lines.append(f"- **Thread ID:** {email.thread_id}")
        if email.goal_id:
            lines.append(f"- **Linked Goal:** {email.goal_id}")
        if email.stakeholder_id:
            lines.append(f"- **Known Stakeholder:** {email.stakeholder_id}")

        # Preview
        if email.body_plain:
            preview = email.body_plain[:300]
            if len(email.body_plain) > 300:
                preview += "..."
            lines.append(f"\n{preview}")

        lines.append("")

    return {
        "success": True,
        "result": "\n".join(lines),
        "emails": [e.to_dict() for e in emails],
    }


async def _get_email_thread(
    manager: EmailManager,
    tool_input: Dict,
) -> Dict:
    """Get email thread."""
    thread_id = tool_input.get("thread_id")
    if not thread_id:
        return {"success": False, "error": "thread_id is required"}

    emails = manager.get_thread(thread_id)

    if not emails:
        return {
            "success": True,
            "result": f"No emails found for thread: {thread_id}"
        }

    context = manager.format_thread_context(thread_id)
    return {
        "success": True,
        "result": context,
        "emails": [e.to_dict() for e in emails],
    }


async def _get_goal_emails(
    manager: EmailManager,
    tool_input: Dict,
) -> Dict:
    """Get emails for a goal."""
    goal_id = tool_input.get("goal_id")
    if not goal_id:
        return {"success": False, "error": "goal_id is required"}

    emails = manager.get_emails_for_goal(goal_id)

    if not emails:
        return {
            "success": True,
            "result": f"No emails linked to goal: {goal_id}"
        }

    context = manager.format_goal_emails_context(goal_id)
    return {
        "success": True,
        "result": context,
        "emails": [e.to_dict() for e in emails],
    }


async def _mark_email_read(
    manager: EmailManager,
    tool_input: Dict,
) -> Dict:
    """Mark email as read/processed."""
    email_id = tool_input.get("email_id")
    if not email_id:
        return {"success": False, "error": "email_id is required"}

    success = manager.mark_processed(email_id)

    if success:
        return {
            "success": True,
            "result": f"Marked email {email_id} as processed"
        }
    else:
        return {
            "success": False,
            "error": f"Email not found: {email_id}"
        }


async def _get_email_stats(manager: EmailManager) -> Dict:
    """Get email statistics."""
    stats = manager.get_email_stats()

    lines = [
        "## Email Statistics\n",
        f"**Inbound:** {stats['inbound']['total']} total, {stats['inbound']['unprocessed']} unprocessed",
        f"**Outbound:** {stats['outbound']['total']} total, {stats['outbound']['sent']} sent, {stats['outbound']['failed']} failed",
    ]

    return {
        "success": True,
        "result": "\n".join(lines),
        "stats": stats,
    }
