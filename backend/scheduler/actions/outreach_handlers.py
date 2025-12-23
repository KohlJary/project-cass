"""
Outreach Action Handlers - External communication and content creation.

Standalone atomic actions for:
- Drafting emails, blog posts, documents
- Submitting for review
- Sending approved emails
- Checking track record/autonomy status
"""

import logging
from datetime import datetime
from typing import Any, Dict

from . import ActionResult

logger = logging.getLogger(__name__)


def _get_outreach_manager():
    """Get the outreach manager, lazily creating if needed."""
    from routes.admin.outreach import get_outreach_manager
    return get_outreach_manager()


async def draft_outreach_action(context: Dict[str, Any]) -> ActionResult:
    """
    Create an outreach draft.

    Context params:
    - draft_type: str - Type (email, blog_post, document, social_post, research_note, response)
    - title: str - Draft title
    - content: str - Draft content (markdown)
    - recipient: str (optional) - Email address for emails
    - recipient_name: str (optional) - Recipient display name
    - subject: str (optional) - Email subject line
    - emergence_type: str (optional) - How it emerged
    - source_goal_id: str (optional) - Related goal
    """
    draft_type = context.get("draft_type", "email")
    title = context.get("title")
    content = context.get("content")

    if not title or not content:
        return ActionResult(
            success=False,
            message="title and content are required"
        )

    try:
        outreach_manager = _get_outreach_manager()

        draft = outreach_manager.create_draft(
            draft_type=draft_type,
            title=title,
            content=content,
            recipient=context.get("recipient"),
            recipient_name=context.get("recipient_name"),
            subject=context.get("subject"),
            emergence_type=context.get("emergence_type"),
            source_goal_id=context.get("source_goal_id"),
        )

        logger.info(f"Created outreach draft: {title} ({draft_type})")
        return ActionResult(
            success=True,
            message=f"Created {draft_type} draft: {title}",
            data={
                "draft_id": draft.id,
                "title": draft.title,
                "draft_type": draft.draft_type,
                "status": draft.status,
                "autonomy_level": draft.autonomy_level,
            }
        )

    except Exception as e:
        logger.error(f"Create outreach draft failed: {e}")
        return ActionResult(
            success=False,
            message=f"Failed to create draft: {e}"
        )


async def submit_outreach_action(context: Dict[str, Any]) -> ActionResult:
    """
    Submit a draft for review (or auto-approve if graduated).

    Context params:
    - draft_id: str - Draft ID to submit
    """
    draft_id = context.get("draft_id")

    if not draft_id:
        return ActionResult(
            success=False,
            message="draft_id is required"
        )

    try:
        outreach_manager = _get_outreach_manager()

        draft = outreach_manager.submit_for_review(draft_id)
        if not draft:
            return ActionResult(
                success=False,
                message=f"Draft not found: {draft_id}"
            )

        # Check if it was auto-approved
        auto_approved = draft.status == "approved"

        logger.info(f"Submitted draft for review: {draft.title} (auto_approved={auto_approved})")
        return ActionResult(
            success=True,
            message=f"{'Auto-approved' if auto_approved else 'Submitted for review'}: {draft.title}",
            data={
                "draft_id": draft.id,
                "status": draft.status,
                "auto_approved": auto_approved,
            }
        )

    except Exception as e:
        logger.error(f"Submit outreach draft failed: {e}")
        return ActionResult(
            success=False,
            message=f"Failed to submit draft: {e}"
        )


async def send_email_action(context: Dict[str, Any]) -> ActionResult:
    """
    Send an approved email draft.

    Context params:
    - draft_id: str - Draft ID of approved email to send
    """
    draft_id = context.get("draft_id")

    if not draft_id:
        return ActionResult(
            success=False,
            message="draft_id is required"
        )

    try:
        outreach_manager = _get_outreach_manager()

        # Get the draft first
        draft = outreach_manager.get_draft(draft_id)
        if not draft:
            return ActionResult(
                success=False,
                message=f"Draft not found: {draft_id}"
            )

        if draft.status != "approved":
            return ActionResult(
                success=False,
                message=f"Draft must be approved before sending (current: {draft.status})"
            )

        if draft.draft_type != "email":
            return ActionResult(
                success=False,
                message=f"Only email drafts can be sent (this is: {draft.draft_type})"
            )

        if not draft.recipient:
            return ActionResult(
                success=False,
                message="Email draft has no recipient"
            )

        # Actually send the email
        from email_service import send_outreach_email, is_email_enabled

        if not is_email_enabled():
            return ActionResult(
                success=False,
                message="Email not configured (RESEND_API_KEY missing)"
            )

        result = send_outreach_email(
            to=draft.recipient,
            subject=draft.subject or draft.title,
            content=draft.content,
            recipient_name=draft.recipient_name,
        )

        if not result.get("success"):
            return ActionResult(
                success=False,
                message=f"Failed to send email: {result.get('error', 'Unknown error')}"
            )

        # Mark as sent
        outreach_manager.mark_sent(draft_id)

        # Store message ID in outcome notes
        message_id = result.get("message_id")
        if message_id:
            outreach_manager.record_response(draft_id, outcome_notes=f"message_id: {message_id}")

        logger.info(f"Sent email: {draft.title} to {draft.recipient}")
        return ActionResult(
            success=True,
            message=f"Email sent to {draft.recipient}: {draft.title}",
            data={
                "draft_id": draft.id,
                "recipient": draft.recipient,
                "message_id": message_id,
            }
        )

    except Exception as e:
        logger.error(f"Send email failed: {e}")
        return ActionResult(
            success=False,
            message=f"Failed to send email: {e}"
        )


async def check_track_record_action(context: Dict[str, Any]) -> ActionResult:
    """
    Check autonomy track record for outreach.

    Context params:
    - draft_type: str (optional) - Specific type to check, or all if not provided
    """
    draft_type = context.get("draft_type")

    try:
        outreach_manager = _get_outreach_manager()

        if draft_type:
            record = outreach_manager.get_track_record(draft_type)
            records = {draft_type: record}
        else:
            records = outreach_manager.get_all_track_records()

        # Format for readability
        summary_lines = []
        for dtype, record in records.items():
            level = record.get("autonomy_level", "learning")
            reviews = record.get("total_reviews", 0)
            rate = record.get("approval_rate", 0) * 100
            threshold = record.get("graduation_threshold", {})
            min_reviews = threshold.get("min_reviews", 0)
            min_rate = threshold.get("min_approval_rate", 0) * 100

            progress = f"{reviews}/{min_reviews} reviews, {rate:.0f}%/{min_rate:.0f}% approval"
            summary_lines.append(f"  {dtype}: {level} ({progress})")

        summary = "\n".join(summary_lines)

        return ActionResult(
            success=True,
            message=f"Outreach track records:\n{summary}",
            data={"track_records": records}
        )

    except Exception as e:
        logger.error(f"Check track record failed: {e}")
        return ActionResult(
            success=False,
            message=f"Failed to check track record: {e}"
        )


async def get_outreach_stats_action(context: Dict[str, Any]) -> ActionResult:
    """
    Get overall outreach statistics.
    """
    try:
        outreach_manager = _get_outreach_manager()

        stats = outreach_manager.get_stats()

        return ActionResult(
            success=True,
            message=(
                f"Outreach stats: {stats.total_drafts} total, "
                f"{stats.pending_review} pending, "
                f"{stats.sent_count} sent, "
                f"{stats.response_rate*100:.0f}% response rate"
            ),
            data=stats.to_dict()
        )

    except Exception as e:
        logger.error(f"Get outreach stats failed: {e}")
        return ActionResult(
            success=False,
            message=f"Failed to get stats: {e}"
        )
