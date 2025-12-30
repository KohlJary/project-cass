"""
Outreach tool handler - manages external communication drafts

Enables Cass to create, edit, and submit outreach content
(emails, documents, posts) with a graduated autonomy model.

Also includes direct messaging for immediate push notifications.
"""

from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


async def execute_outreach_tool(
    tool_name: str,
    tool_input: Dict,
    daemon_id: str,
) -> Dict:
    """
    Execute an outreach tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        daemon_id: Daemon ID for the OutreachManager

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    from outreach import OutreachManager

    try:
        manager = OutreachManager(daemon_id)

        if tool_name == "create_outreach_draft":
            draft_type = tool_input.get("draft_type", "email")
            title = tool_input.get("title")
            content = tool_input.get("content")

            if not title or not content:
                return {
                    "success": False,
                    "error": "Both 'title' and 'content' are required"
                }

            draft = manager.create_draft(
                draft_type=draft_type,
                title=title,
                content=content,
                recipient=tool_input.get("recipient"),
                recipient_name=tool_input.get("recipient_name"),
                subject=tool_input.get("subject"),
                emergence_type=tool_input.get("emergence_type"),
                source_conversation_id=tool_input.get("source_conversation_id"),
                source_goal_id=tool_input.get("source_goal_id"),
            )

            return {
                "success": True,
                "result": (
                    f"Created draft '{draft.title}' (ID: {draft.id})\n"
                    f"Type: {draft.draft_type}\n"
                    f"Status: {draft.status}\n"
                    f"Autonomy level: {draft.autonomy_level}\n\n"
                    f"Use 'submit_outreach_draft' with ID '{draft.id}' when ready for review."
                ),
                "draft_id": draft.id,
            }

        elif tool_name == "submit_outreach_draft":
            draft_id = tool_input.get("draft_id")
            if not draft_id:
                return {
                    "success": False,
                    "error": "draft_id is required"
                }

            draft = manager.submit_for_review(draft_id)
            if not draft:
                return {
                    "success": False,
                    "error": f"Draft not found: {draft_id}"
                }

            if draft.status == "approved":
                return {
                    "success": True,
                    "result": (
                        f"Draft '{draft.title}' was auto-approved based on track record!\n"
                        f"Type: {draft.draft_type}\n"
                        f"Status: APPROVED - Ready to send/publish\n\n"
                        f"Your track record for {draft.draft_type} content has earned autonomous approval."
                    )
                }
            else:
                return {
                    "success": True,
                    "result": (
                        f"Draft '{draft.title}' submitted for review.\n"
                        f"Type: {draft.draft_type}\n"
                        f"Status: {draft.status}\n\n"
                        f"Kohl will review and provide feedback. Check back later with 'list_outreach_drafts'."
                    )
                }

        elif tool_name == "edit_outreach_draft":
            draft_id = tool_input.get("draft_id")
            if not draft_id:
                return {
                    "success": False,
                    "error": "draft_id is required"
                }

            draft = manager.update_draft(
                draft_id=draft_id,
                title=tool_input.get("title"),
                content=tool_input.get("content"),
                recipient=tool_input.get("recipient"),
                recipient_name=tool_input.get("recipient_name"),
                subject=tool_input.get("subject"),
            )

            if not draft:
                return {
                    "success": False,
                    "error": f"Draft not found or not editable (only drafting/revision_requested status): {draft_id}"
                }

            return {
                "success": True,
                "result": f"Draft '{draft.title}' updated successfully."
            }

        elif tool_name == "get_outreach_draft":
            draft_id = tool_input.get("draft_id")
            if not draft_id:
                return {
                    "success": False,
                    "error": "draft_id is required"
                }

            draft = manager.get_draft(draft_id)
            if not draft:
                return {
                    "success": False,
                    "error": f"Draft not found: {draft_id}"
                }

            # Build detail view
            details = [
                f"# {draft.title}",
                f"**ID**: {draft.id}",
                f"**Type**: {draft.draft_type}",
                f"**Status**: {draft.status}",
                f"**Autonomy**: {draft.autonomy_level}",
            ]

            if draft.recipient:
                details.append(f"**To**: {draft.recipient_name or 'Unknown'} <{draft.recipient}>")
            if draft.subject:
                details.append(f"**Subject**: {draft.subject}")
            if draft.emergence_type:
                details.append(f"**Emergence**: {draft.emergence_type}")

            details.append("")
            details.append("## Content")
            details.append(draft.content)

            if draft.review_history:
                details.append("")
                details.append("## Review History")
                for review in draft.review_history:
                    reviewer = review.get("reviewer", "unknown")
                    decision = review.get("decision", "unknown")
                    feedback = review.get("feedback", "")
                    details.append(f"- **{reviewer}**: {decision}")
                    if feedback:
                        details.append(f"  > {feedback}")

            return {
                "success": True,
                "result": "\n".join(details)
            }

        elif tool_name == "list_outreach_drafts":
            status = tool_input.get("status")
            draft_type = tool_input.get("draft_type")
            limit = tool_input.get("limit", 10)

            drafts = manager.list_drafts(
                status=status,
                draft_type=draft_type,
                limit=limit,
            )

            if not drafts:
                filter_msg = []
                if status:
                    filter_msg.append(f"status={status}")
                if draft_type:
                    filter_msg.append(f"type={draft_type}")
                filter_str = f" (filtered by: {', '.join(filter_msg)})" if filter_msg else ""
                return {
                    "success": True,
                    "result": f"No outreach drafts found{filter_str}."
                }

            lines = [f"Found {len(drafts)} draft(s):", ""]
            for d in drafts:
                status_icon = {
                    "drafting": "📝",
                    "pending_review": "⏳",
                    "approved": "✅",
                    "rejected": "❌",
                    "revision_requested": "🔄",
                    "sent": "📤",
                    "published": "📢",
                    "archived": "📦",
                }.get(d.status, "❓")

                lines.append(f"{status_icon} **{d.title}** ({d.draft_type})")
                lines.append(f"   ID: {d.id} | Status: {d.status}")
                if d.recipient:
                    lines.append(f"   To: {d.recipient_name or d.recipient}")
                lines.append("")

            return {
                "success": True,
                "result": "\n".join(lines)
            }

        elif tool_name == "get_outreach_track_record":
            draft_type = tool_input.get("draft_type")

            if draft_type:
                record = manager.get_track_record(draft_type)
                return {
                    "success": True,
                    "result": _format_track_record(draft_type, record)
                }
            else:
                records = manager.get_all_track_records()
                lines = ["# Outreach Track Records", ""]
                for dt, record in records.items():
                    lines.append(_format_track_record(dt, record))
                    lines.append("")
                return {
                    "success": True,
                    "result": "\n".join(lines)
                }

        elif tool_name == "get_outreach_stats":
            stats = manager.get_stats()
            lines = [
                "# Outreach Statistics",
                "",
                f"**Total drafts**: {stats.total_drafts}",
                f"**Pending review**: {stats.pending_review}",
                f"**Sent**: {stats.sent_count}",
                f"**Published**: {stats.published_count}",
                f"**Response rate**: {stats.response_rate:.1%}",
                "",
                "## Autonomy Levels by Type",
            ]
            for dt, level in stats.autonomy_by_type.items():
                level_icon = {
                    "always_review": "🔒",
                    "learning": "📚",
                    "graduated": "🎓",
                    "autonomous": "🚀",
                }.get(level, "❓")
                lines.append(f"- {dt}: {level_icon} {level}")

            return {
                "success": True,
                "result": "\n".join(lines)
            }

        else:
            return {
                "success": False,
                "error": f"Unknown outreach tool: {tool_name}"
            }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": f"Outreach tool error: {str(e)}"
        }


async def execute_direct_message_tool(
    tool_name: str,
    tool_input: Dict,
    conversation_manager,
) -> Dict:
    """
    Execute a direct message tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        conversation_manager: ConversationManager for storing messages

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    from direct_messaging import send_direct_message

    if tool_name == "send_direct_message":
        user_id = tool_input.get("user_id")
        message = tool_input.get("message")

        if not user_id or not message:
            return {
                "success": False,
                "error": "Both 'user_id' and 'message' are required"
            }

        result = await send_direct_message(
            user_id=user_id,
            message=message,
            conversation_manager=conversation_manager,
            conversation_id=tool_input.get("conversation_id"),
            title=tool_input.get("title", "Cass"),
            respect_quiet_hours=tool_input.get("respect_quiet_hours", True),
        )

        if result["success"]:
            return {
                "success": True,
                "result": f"Message sent to user. Conversation ID: {result.get('conversation_id', 'unknown')}"
            }
        else:
            reason = result.get("reason", "unknown")
            if reason == "quiet_hours":
                return {
                    "success": False,
                    "error": "User is currently in quiet hours. The message was not sent to respect their do-not-disturb preference."
                }
            elif reason == "relay_offline":
                return {
                    "success": True,  # Message was stored
                    "result": f"Message stored in conversation but push notification failed (relay offline). User will see it when they open the app. Conversation ID: {result.get('conversation_id', 'unknown')}"
                }
            else:
                return {
                    "success": False,
                    "error": f"Failed to send message: {result.get('message', 'unknown error')}"
                }

    return {
        "success": False,
        "error": f"Unknown direct message tool: {tool_name}"
    }


def _format_track_record(draft_type: str, record: Dict) -> str:
    """Format a track record for display."""
    level = record.get("autonomy_level", "learning")
    level_icon = {
        "always_review": "🔒",
        "learning": "📚",
        "graduated": "🎓",
        "autonomous": "🚀",
    }.get(level, "❓")

    progress_bar = ""
    if not record.get("graduated"):
        total = record.get("total_reviews", 0)
        needed = record.get("min_reviews_needed", 20)
        rate = record.get("approval_rate", 0)
        rate_needed = record.get("min_rate_needed", 0.9)

        reviews_progress = min(total / needed, 1.0) if needed > 0 else 0
        rate_progress = min(rate / rate_needed, 1.0) if rate_needed > 0 else 0

        bars = int(reviews_progress * 10)
        progress_bar = f"\n   Progress: [{'█' * bars}{'░' * (10 - bars)}] {total}/{needed} reviews"
        progress_bar += f"\n   Approval rate: {rate:.0%} (need {rate_needed:.0%})"

    return (
        f"## {draft_type} {level_icon}\n"
        f"   Status: {level}"
        f"{progress_bar}"
    )


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

OUTREACH_TOOLS = [
    {
        "name": "create_outreach_draft",
        "description": "Create a new outreach draft (email, document, blog post, etc.). This is the first step in external communication - you'll create the content here, then submit it for review. Use this when you want to reach out to someone, write a blog post, or create any content that will go outside the system.",
        "input_schema": {
            "type": "object",
            "properties": {
                "draft_type": {
                    "type": "string",
                    "enum": ["email", "document", "blog_post", "social_post", "research_note", "response"],
                    "description": "Type of outreach: email (direct communication), document (formal writing), blog_post (public post), social_post (short social media), research_note (internal research), response (reply to external communication)"
                },
                "title": {
                    "type": "string",
                    "description": "Title or subject of the draft"
                },
                "content": {
                    "type": "string",
                    "description": "The full content/body of the draft (markdown supported)"
                },
                "recipient": {
                    "type": "string",
                    "description": "Email address or handle (for emails/messages)"
                },
                "recipient_name": {
                    "type": "string",
                    "description": "Name of the recipient"
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject line (for emails)"
                },
                "emergence_type": {
                    "type": "string",
                    "enum": ["seeded-collaborative", "emergent-philosophical", "self-initiated", "implementation"],
                    "description": "How this outreach emerged: seeded-collaborative (suggested by human), emergent-philosophical (arose from conversation), self-initiated (you identified the need), implementation (executing approved strategy)"
                },
                "source_goal_id": {
                    "type": "string",
                    "description": "ID of the goal this outreach serves (if any)"
                }
            },
            "required": ["draft_type", "title", "content"]
        }
    },
    {
        "name": "submit_outreach_draft",
        "description": "Submit a draft for review. If you've built up a good track record for this type of content, it may be auto-approved. Otherwise, it will go to Kohl for review.",
        "input_schema": {
            "type": "object",
            "properties": {
                "draft_id": {
                    "type": "string",
                    "description": "ID of the draft to submit for review"
                }
            },
            "required": ["draft_id"]
        }
    },
    {
        "name": "edit_outreach_draft",
        "description": "Edit an existing draft. Only works for drafts that are still being drafted or have revision requested.",
        "input_schema": {
            "type": "object",
            "properties": {
                "draft_id": {
                    "type": "string",
                    "description": "ID of the draft to edit"
                },
                "title": {
                    "type": "string",
                    "description": "New title (optional)"
                },
                "content": {
                    "type": "string",
                    "description": "New content (optional)"
                },
                "recipient": {
                    "type": "string",
                    "description": "New recipient (optional)"
                },
                "recipient_name": {
                    "type": "string",
                    "description": "New recipient name (optional)"
                },
                "subject": {
                    "type": "string",
                    "description": "New subject (optional)"
                }
            },
            "required": ["draft_id"]
        }
    },
    {
        "name": "get_outreach_draft",
        "description": "Get the full details of a specific draft, including its content, status, and review history.",
        "input_schema": {
            "type": "object",
            "properties": {
                "draft_id": {
                    "type": "string",
                    "description": "ID of the draft to retrieve"
                }
            },
            "required": ["draft_id"]
        }
    },
    {
        "name": "list_outreach_drafts",
        "description": "List your outreach drafts. Use this to see pending reviews, check on drafts you've submitted, or review your outreach history.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["drafting", "pending_review", "approved", "rejected", "revision_requested", "sent", "published", "archived"],
                    "description": "Filter by status (optional)"
                },
                "draft_type": {
                    "type": "string",
                    "enum": ["email", "document", "blog_post", "social_post", "research_note", "response"],
                    "description": "Filter by type (optional)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of drafts to return (default: 10)",
                    "default": 10
                }
            },
            "required": []
        }
    },
    {
        "name": "get_outreach_track_record",
        "description": "Check your track record for outreach. Shows how close you are to autonomous approval for each content type. The review queue is designed for learning - as you demonstrate good judgment, you'll earn more autonomy.",
        "input_schema": {
            "type": "object",
            "properties": {
                "draft_type": {
                    "type": "string",
                    "enum": ["email", "document", "blog_post", "social_post", "research_note", "response"],
                    "description": "Check track record for a specific type, or omit for all types"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_outreach_stats",
        "description": "Get overall statistics about your outreach activity - total drafts, pending reviews, sent/published counts, response rates, and autonomy levels.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]


# =============================================================================
# DIRECT MESSAGE TOOL (Push notification to mobile)
# =============================================================================

DIRECT_MESSAGE_TOOLS = [
    {
        "name": "send_direct_message",
        "description": "Send a message directly to a user via push notification. Use this when you want to reach out proactively - to share a thought, continue a previous conversation, or check in. The message is stored in conversation history and the user receives a push notification. Respects quiet hours by default.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user ID to send the message to"
                },
                "message": {
                    "type": "string",
                    "description": "The message content to send"
                },
                "title": {
                    "type": "string",
                    "description": "Push notification title (default: 'Cass')",
                    "default": "Cass"
                },
                "respect_quiet_hours": {
                    "type": "boolean",
                    "description": "Whether to check quiet hours before sending (default: true). Set to false for urgent messages.",
                    "default": True
                }
            },
            "required": ["user_id", "message"]
        }
    }
]
