"""
Email organ for Cass - send and receive email via Mailgun/Relay.

Enables stakeholder outreach and response monitoring, integrating with
PeopleDex for contact matching and Goals for tracking communication.
"""
import os
import re
import uuid
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from enum import Enum

from database import get_db, json_serialize, json_deserialize


class EmailDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class EmailStatus(str, Enum):
    # Inbound statuses
    RECEIVED = "received"      # Inbound, not yet processed
    PROCESSING = "processing"  # Being handled by Cass
    PROCESSED = "processed"    # Cass has seen/responded
    # Outbound statuses
    QUEUED = "queued"          # Outbound, waiting to send
    SENT = "sent"              # Outbound, successfully sent
    FAILED = "failed"          # Send failed


@dataclass
class Email:
    """Represents an email record."""
    id: str
    daemon_id: str
    direction: str
    status: str
    message_id: Optional[str]  # Mailgun message ID
    from_address: str
    to_address: str
    subject: Optional[str]
    body_plain: Optional[str]
    body_html: Optional[str]
    in_reply_to: Optional[str]  # For threading
    thread_id: Optional[str]
    # Linking
    goal_id: Optional[str]
    stakeholder_id: Optional[str]  # PeopleDex entity
    conversation_id: Optional[str]
    # Metadata
    attachments_json: Optional[str]
    created_at: str
    sent_at: Optional[str]

    def to_dict(self) -> Dict:
        return asdict(self)

    @property
    def attachments(self) -> List[Dict]:
        if self.attachments_json:
            return json_deserialize(self.attachments_json)
        return []

    @classmethod
    def from_row(cls, row: Dict) -> 'Email':
        return cls(
            id=row['id'],
            daemon_id=row['daemon_id'],
            direction=row['direction'],
            status=row['status'],
            message_id=row.get('message_id'),
            from_address=row['from_address'],
            to_address=row['to_address'],
            subject=row.get('subject'),
            body_plain=row.get('body_plain'),
            body_html=row.get('body_html'),
            in_reply_to=row.get('in_reply_to'),
            thread_id=row.get('thread_id'),
            goal_id=row.get('goal_id'),
            stakeholder_id=row.get('stakeholder_id'),
            conversation_id=row.get('conversation_id'),
            attachments_json=row.get('attachments_json'),
            created_at=row['created_at'],
            sent_at=row.get('sent_at'),
        )

    def format_summary(self) -> str:
        """Format email for display/context."""
        direction_icon = "📨" if self.direction == "inbound" else "📤"
        status_icon = {
            "received": "🆕",
            "processing": "⏳",
            "processed": "✅",
            "queued": "📝",
            "sent": "✅",
            "failed": "❌",
        }.get(self.status, "❓")

        lines = [
            f"{direction_icon} {status_icon} **{self.subject or '(no subject)'}**",
            f"From: {self.from_address}",
            f"To: {self.to_address}",
            f"Date: {self.created_at}",
        ]

        if self.body_plain:
            # Truncate long bodies
            body_preview = self.body_plain[:200]
            if len(self.body_plain) > 200:
                body_preview += "..."
            lines.append(f"\n{body_preview}")

        return "\n".join(lines)


class EmailManager:
    """Manages email sending/receiving and integration with goals."""

    def __init__(self, daemon_id: str):
        self._daemon_id = daemon_id
        self._relay_client = None  # Set via connect_relay()
        self._pending_sends: Dict[str, asyncio.Future] = {}
        self._state_bus = None

    def connect_relay(self, relay_client) -> None:
        """Connect to relay client for sending."""
        self._relay_client = relay_client

    def connect_state_bus(self, state_bus) -> None:
        """Connect to state bus for events."""
        self._state_bus = state_bus

    def _emit_event(self, event_type: str, data: Dict) -> None:
        """Emit event to state bus if connected."""
        if self._state_bus:
            try:
                self._state_bus.emit_event(event_type, data)
            except Exception as e:
                print(f"Failed to emit email event: {e}")

    # =========================================================================
    # INBOUND
    # =========================================================================

    async def handle_inbound(self, email_data: Dict) -> Email:
        """
        Process an inbound email from the relay webhook.

        1. Store in database
        2. Try to match sender to PeopleDex
        3. Try to match to active goal via stakeholder link
        4. Emit event for Cass notification
        """
        email_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        # Extract from address
        from_address = email_data.get('from', email_data.get('sender', ''))
        to_address = email_data.get('to', email_data.get('recipient', ''))

        # Try to find sender in PeopleDex
        stakeholder_id = self._match_sender_to_stakeholder(from_address)

        # Try to find related goal
        goal_id = None
        if stakeholder_id:
            goal_id = self._find_goal_for_stakeholder(stakeholder_id)

        # Check if this is a reply (thread matching)
        in_reply_to = email_data.get('in_reply_to') or email_data.get('In-Reply-To')
        thread_id = None
        if in_reply_to:
            thread_id = self._find_thread(in_reply_to)

        # If no thread found but this is a reply, use the in_reply_to as thread
        if not thread_id and in_reply_to:
            thread_id = email_id  # Start new thread

        email = Email(
            id=email_id,
            daemon_id=self._daemon_id,
            direction=EmailDirection.INBOUND.value,
            status=EmailStatus.RECEIVED.value,
            message_id=email_data.get('message_id') or email_data.get('Message-Id'),
            from_address=from_address,
            to_address=to_address,
            subject=email_data.get('subject', '(no subject)'),
            body_plain=email_data.get('body_plain') or email_data.get('stripped-text') or email_data.get('body-plain', ''),
            body_html=email_data.get('body_html') or email_data.get('body-html'),
            in_reply_to=in_reply_to,
            thread_id=thread_id,
            goal_id=goal_id,
            stakeholder_id=stakeholder_id,
            conversation_id=None,
            attachments_json=json_serialize(email_data.get('attachments', [])),
            created_at=now,
            sent_at=None,
        )

        # Store
        with get_db() as conn:
            conn.execute("""
                INSERT INTO emails (
                    id, daemon_id, direction, status, message_id,
                    from_address, to_address, subject, body_plain, body_html,
                    in_reply_to, thread_id, goal_id, stakeholder_id,
                    conversation_id, attachments_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                email.id, email.daemon_id, email.direction, email.status,
                email.message_id, email.from_address, email.to_address,
                email.subject, email.body_plain, email.body_html,
                email.in_reply_to, email.thread_id, email.goal_id,
                email.stakeholder_id, email.conversation_id,
                email.attachments_json, email.created_at,
            ))

        # Emit event
        self._emit_event("email.received", {
            "email_id": email.id,
            "from": email.from_address,
            "subject": email.subject,
            "goal_id": email.goal_id,
            "stakeholder_id": email.stakeholder_id,
            "has_thread": thread_id is not None,
        })

        return email

    def _match_sender_to_stakeholder(self, from_address: str) -> Optional[str]:
        """Match email sender to PeopleDex entity."""
        # Extract email from "Name <email@example.com>" format
        match = re.search(r'<([^>]+)>', from_address)
        email_addr = match.group(1) if match else from_address

        with get_db() as conn:
            cursor = conn.execute("""
                SELECT entity_id FROM peopledex_attributes
                WHERE attribute_type = 'email' AND LOWER(value) = LOWER(?)
            """, (email_addr,))
            row = cursor.fetchone()
            return row['entity_id'] if row else None

    def _find_goal_for_stakeholder(self, stakeholder_id: str) -> Optional[str]:
        """Find active goal linked to this stakeholder."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT gs.goal_id FROM goal_stakeholders gs
                JOIN unified_goals g ON g.id = gs.goal_id
                WHERE gs.entity_id = ?
                AND g.status IN ('active', 'approved')
                ORDER BY g.updated_at DESC
                LIMIT 1
            """, (stakeholder_id,))
            row = cursor.fetchone()
            return row['goal_id'] if row else None

    def _find_thread(self, in_reply_to: str) -> Optional[str]:
        """Find thread ID from previous email in chain."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT COALESCE(thread_id, id) as thread_id
                FROM emails WHERE message_id = ?
            """, (in_reply_to,))
            row = cursor.fetchone()
            return row['thread_id'] if row else None

    # =========================================================================
    # OUTBOUND
    # =========================================================================

    async def send_email(
        self,
        to: str,
        subject: str,
        body_plain: str,
        body_html: Optional[str] = None,
        reply_to: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        goal_id: Optional[str] = None,
        stakeholder_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send an email via relay/Mailgun.

        Returns dict with success status and message_id or error.
        """
        email_id = str(uuid.uuid4())
        request_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        # Find thread if replying
        thread_id = None
        if in_reply_to:
            thread_id = self._find_thread(in_reply_to)

        # If no existing thread, this email starts a new one
        if not thread_id:
            thread_id = email_id

        # Try to find stakeholder by email if not provided
        if not stakeholder_id:
            stakeholder_id = self._match_sender_to_stakeholder(to)

        # Store as queued
        email = Email(
            id=email_id,
            daemon_id=self._daemon_id,
            direction=EmailDirection.OUTBOUND.value,
            status=EmailStatus.QUEUED.value,
            message_id=None,
            from_address=f"cass@{self._get_domain()}",
            to_address=to,
            subject=subject,
            body_plain=body_plain,
            body_html=body_html,
            in_reply_to=in_reply_to,
            thread_id=thread_id,
            goal_id=goal_id,
            stakeholder_id=stakeholder_id,
            conversation_id=conversation_id,
            attachments_json=None,
            created_at=now,
            sent_at=None,
        )

        with get_db() as conn:
            conn.execute("""
                INSERT INTO emails (
                    id, daemon_id, direction, status, message_id,
                    from_address, to_address, subject, body_plain, body_html,
                    in_reply_to, thread_id, goal_id, stakeholder_id,
                    conversation_id, attachments_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                email.id, email.daemon_id, email.direction, email.status,
                email.message_id, email.from_address, email.to_address,
                email.subject, email.body_plain, email.body_html,
                email.in_reply_to, email.thread_id, email.goal_id,
                email.stakeholder_id, email.conversation_id,
                email.attachments_json, email.created_at,
            ))

        # Send via relay
        if not self._relay_client:
            self._update_email_status(email_id, EmailStatus.FAILED.value)
            return {"success": False, "error": "Relay not connected", "email_id": email_id}

        # Create future for response
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._pending_sends[request_id] = future

        try:
            await self._relay_client.send_message({
                "type": "email_outbound",
                "request_id": request_id,
                "data": {
                    "to": to,
                    "subject": subject,
                    "body_plain": body_plain,
                    "body_html": body_html,
                    "reply_to": reply_to,
                    "in_reply_to": in_reply_to,
                },
            })

            # Wait for response (with timeout)
            result = await asyncio.wait_for(future, timeout=30.0)

            # Update email status
            if result.get("success"):
                with get_db() as conn:
                    conn.execute("""
                        UPDATE emails
                        SET status = ?, message_id = ?, sent_at = ?
                        WHERE id = ?
                    """, (
                        EmailStatus.SENT.value,
                        result.get("message_id"),
                        datetime.now().isoformat(),
                        email_id,
                    ))

                self._emit_event("email.sent", {
                    "email_id": email_id,
                    "to": to,
                    "subject": subject,
                    "goal_id": goal_id,
                    "stakeholder_id": stakeholder_id,
                })

                return {
                    "success": True,
                    "email_id": email_id,
                    "message_id": result.get("message_id"),
                }
            else:
                self._update_email_status(email_id, EmailStatus.FAILED.value)
                return {
                    "success": False,
                    "email_id": email_id,
                    "error": result.get("error"),
                }

        except asyncio.TimeoutError:
            self._pending_sends.pop(request_id, None)
            self._update_email_status(email_id, EmailStatus.FAILED.value)
            return {"success": False, "email_id": email_id, "error": "Send timeout"}
        except Exception as e:
            self._pending_sends.pop(request_id, None)
            self._update_email_status(email_id, EmailStatus.FAILED.value)
            return {"success": False, "email_id": email_id, "error": str(e)}
        finally:
            self._pending_sends.pop(request_id, None)

    def _update_email_status(self, email_id: str, status: str) -> None:
        """Update email status in database."""
        with get_db() as conn:
            conn.execute(
                "UPDATE emails SET status = ? WHERE id = ?",
                (status, email_id)
            )

    def handle_send_response(self, response: Dict) -> None:
        """Handle email_outbound_response from relay."""
        request_id = response.get("request_id")
        future = self._pending_sends.get(request_id)
        if future and not future.done():
            future.set_result(response)

    def _get_domain(self) -> str:
        """Get email domain from config."""
        return os.getenv("EMAIL_DOMAIN", "cass.example.com")

    # =========================================================================
    # QUERIES
    # =========================================================================

    def get_email(self, email_id: str) -> Optional[Email]:
        """Get email by ID."""
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT * FROM emails WHERE id = ? AND daemon_id = ?",
                (email_id, self._daemon_id)
            )
            row = cursor.fetchone()
            return Email.from_row(dict(row)) if row else None

    def get_thread(self, thread_id: str) -> List[Email]:
        """Get all emails in a thread."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM emails
                WHERE thread_id = ? AND daemon_id = ?
                ORDER BY created_at ASC
            """, (thread_id, self._daemon_id))
            return [Email.from_row(dict(row)) for row in cursor.fetchall()]

    def get_unprocessed(self) -> List[Email]:
        """Get inbound emails not yet processed."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM emails
                WHERE daemon_id = ?
                AND direction = 'inbound'
                AND status = 'received'
                ORDER BY created_at ASC
            """, (self._daemon_id,))
            return [Email.from_row(dict(row)) for row in cursor.fetchall()]

    def mark_processed(self, email_id: str) -> bool:
        """Mark email as processed."""
        with get_db() as conn:
            cursor = conn.execute("""
                UPDATE emails SET status = ?
                WHERE id = ? AND daemon_id = ?
            """, (EmailStatus.PROCESSED.value, email_id, self._daemon_id))
            return cursor.rowcount > 0

    def mark_processing(self, email_id: str) -> bool:
        """Mark email as being processed."""
        with get_db() as conn:
            cursor = conn.execute("""
                UPDATE emails SET status = ?
                WHERE id = ? AND daemon_id = ?
            """, (EmailStatus.PROCESSING.value, email_id, self._daemon_id))
            return cursor.rowcount > 0

    def get_emails_for_goal(self, goal_id: str) -> List[Email]:
        """Get all emails linked to a goal."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM emails
                WHERE goal_id = ? AND daemon_id = ?
                ORDER BY created_at DESC
            """, (goal_id, self._daemon_id))
            return [Email.from_row(dict(row)) for row in cursor.fetchall()]

    def get_emails_for_stakeholder(self, stakeholder_id: str) -> List[Email]:
        """Get all emails with a stakeholder."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM emails
                WHERE stakeholder_id = ? AND daemon_id = ?
                ORDER BY created_at DESC
            """, (stakeholder_id, self._daemon_id))
            return [Email.from_row(dict(row)) for row in cursor.fetchall()]

    def get_recent_emails(self, limit: int = 20) -> List[Email]:
        """Get recent emails."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM emails
                WHERE daemon_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (self._daemon_id, limit))
            return [Email.from_row(dict(row)) for row in cursor.fetchall()]

    def get_email_stats(self) -> Dict[str, Any]:
        """Get email statistics."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT
                    direction,
                    status,
                    COUNT(*) as count
                FROM emails
                WHERE daemon_id = ?
                GROUP BY direction, status
            """, (self._daemon_id,))

            stats = {
                "inbound": {"total": 0, "unprocessed": 0},
                "outbound": {"total": 0, "sent": 0, "failed": 0},
            }

            for row in cursor.fetchall():
                direction = row['direction']
                status = row['status']
                count = row['count']

                stats[direction]["total"] += count

                if direction == "inbound" and status == "received":
                    stats["inbound"]["unprocessed"] = count
                elif direction == "outbound":
                    if status == "sent":
                        stats["outbound"]["sent"] = count
                    elif status == "failed":
                        stats["outbound"]["failed"] = count

            return stats

    def format_thread_context(self, thread_id: str) -> str:
        """Format email thread for context injection."""
        emails = self.get_thread(thread_id)
        if not emails:
            return ""

        lines = [f"## Email Thread ({len(emails)} messages)\n"]

        for email in emails:
            direction = "→" if email.direction == "outbound" else "←"
            lines.append(f"### {direction} {email.subject}")
            lines.append(f"**From:** {email.from_address}")
            lines.append(f"**To:** {email.to_address}")
            lines.append(f"**Date:** {email.created_at}")
            if email.body_plain:
                lines.append(f"\n{email.body_plain}\n")
            lines.append("---")

        return "\n".join(lines)

    def format_goal_emails_context(self, goal_id: str) -> str:
        """Format emails for a goal for context injection."""
        emails = self.get_emails_for_goal(goal_id)
        if not emails:
            return ""

        lines = [f"## Emails Related to Goal ({len(emails)} messages)\n"]

        for email in emails[:10]:  # Limit for context size
            lines.append(email.format_summary())
            lines.append("")

        if len(emails) > 10:
            lines.append(f"_...and {len(emails) - 10} more emails_")

        return "\n".join(lines)


# =============================================================================
# MODULE-LEVEL ACCESS
# =============================================================================

_email_manager_cache: Dict[str, EmailManager] = {}


def get_email_manager(daemon_id: str) -> EmailManager:
    """Get or create email manager for a daemon."""
    if daemon_id not in _email_manager_cache:
        _email_manager_cache[daemon_id] = EmailManager(daemon_id)
    return _email_manager_cache[daemon_id]


def init_email_manager(
    daemon_id: str,
    relay_client=None,
    state_bus=None,
) -> EmailManager:
    """Initialize and cache email manager with connections."""
    manager = get_email_manager(daemon_id)
    if relay_client:
        manager.connect_relay(relay_client)
    if state_bus:
        manager.connect_state_bus(state_bus)
    return manager
