"""
Email Service using Resend

Handles sending transactional emails for user registration approval.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger("cass-vessel")

# Configuration
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM", "Cass <noreply@resend.dev>")  # Default to Resend test domain
APP_URL = os.getenv("APP_URL", "http://localhost:5173")


def is_email_enabled() -> bool:
    """Check if email sending is configured and enabled."""
    return bool(RESEND_API_KEY)


def send_approval_email(
    to_email: str,
    display_name: str,
    custom_message: Optional[str] = None
) -> bool:
    """
    Send an approval notification email to a user.

    Args:
        to_email: The recipient's email address
        display_name: The user's display name
        custom_message: Optional custom message from admin

    Returns:
        True if email sent successfully, False otherwise
    """
    if not RESEND_API_KEY:
        logger.warning("Email not configured - RESEND_API_KEY not set")
        return False

    if not to_email:
        logger.warning("Cannot send approval email - no email address provided")
        return False

    try:
        import resend
        resend.api_key = RESEND_API_KEY

        subject = "Your Cass account has been approved"

        html_content = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #1a1a2e;">Welcome to Cass!</h2>

            <p>Hi {display_name},</p>

            <p>Great news - your account has been approved! You can now log in and start using Cass.</p>

            {f'<p style="background: #f5f5f5; padding: 15px; border-radius: 8px; margin: 20px 0;"><em>{custom_message}</em></p>' if custom_message else ''}

            <p style="margin: 30px 0;">
                <a href="{APP_URL}/login"
                   style="background: #6366f1; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">
                    Log In Now
                </a>
            </p>

            <p style="color: #666; font-size: 14px;">
                If you have any questions, feel free to reach out.
            </p>

            <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">

            <p style="color: #999; font-size: 12px;">
                This email was sent from the Cass AI system.
            </p>
        </div>
        """

        text_content = f"""
Welcome to Cass!

Hi {display_name},

Great news - your account has been approved! You can now log in and start using Cass.

{f'Message from admin: {custom_message}' if custom_message else ''}

Log in at: {APP_URL}/login

If you have any questions, feel free to reach out.

---
This email was sent from the Cass AI system.
        """

        result = resend.Emails.send({
            "from": EMAIL_FROM,
            "to": [to_email],
            "subject": subject,
            "html": html_content,
            "text": text_content
        })

        logger.info(f"Approval email sent to {to_email}, id: {result.get('id', 'unknown')}")
        return True

    except Exception as e:
        logger.error(f"Failed to send approval email to {to_email}: {e}")
        return False


def send_rejection_email(
    to_email: str,
    display_name: str,
    reason: Optional[str] = None
) -> bool:
    """
    Send a rejection notification email to a user.

    Args:
        to_email: The recipient's email address
        display_name: The user's display name
        reason: The reason for rejection

    Returns:
        True if email sent successfully, False otherwise
    """
    if not RESEND_API_KEY:
        logger.warning("Email not configured - RESEND_API_KEY not set")
        return False

    if not to_email:
        logger.warning("Cannot send rejection email - no email address provided")
        return False

    try:
        import resend
        resend.api_key = RESEND_API_KEY

        subject = "Update on your Cass account request"

        html_content = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #1a1a2e;">Account Request Update</h2>

            <p>Hi {display_name},</p>

            <p>Thank you for your interest in Cass. Unfortunately, we're unable to approve your account request at this time.</p>

            {f'<p style="background: #fef2f2; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #ef4444;"><strong>Reason:</strong> {reason}</p>' if reason else ''}

            <p>If you believe this was a mistake or have questions, please reach out.</p>

            <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">

            <p style="color: #999; font-size: 12px;">
                This email was sent from the Cass AI system.
            </p>
        </div>
        """

        text_content = f"""
Account Request Update

Hi {display_name},

Thank you for your interest in Cass. Unfortunately, we're unable to approve your account request at this time.

{f'Reason: {reason}' if reason else ''}

If you believe this was a mistake or have questions, please reach out.

---
This email was sent from the Cass AI system.
        """

        result = resend.Emails.send({
            "from": EMAIL_FROM,
            "to": [to_email],
            "subject": subject,
            "html": html_content,
            "text": text_content
        })

        logger.info(f"Rejection email sent to {to_email}, id: {result.get('id', 'unknown')}")
        return True

    except Exception as e:
        logger.error(f"Failed to send rejection email to {to_email}: {e}")
        return False
