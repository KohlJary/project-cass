# Email Organ Specification

## Overview

Email capability for Cass enabling stakeholder outreach and response monitoring. Integrates with Mailgun for deliverability, routes through the relay server for security.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           INBOUND                                    │
│                                                                      │
│   External Sender                                                    │
│        │                                                             │
│        ▼                                                             │
│   ┌─────────┐    webhook     ┌─────────────┐    WebSocket           │
│   │ Mailgun │ ─────────────► │ Relay Server│ ─────────────►         │
│   └─────────┘   POST /email  └─────────────┘               │        │
│                  /inbound                                   │        │
│                                                             ▼        │
│                                                    ┌──────────────┐  │
│                                                    │ Cass Backend │  │
│                                                    └──────────────┘  │
│                                                             │        │
│                           OUTBOUND                          │        │
│                                                             ▼        │
│   ┌─────────┐    API call    ┌─────────────┐    WebSocket  │        │
│   │ Mailgun │ ◄───────────── │ Relay Server│ ◄─────────────┘        │
│   └─────────┘                └─────────────┘                         │
│         │                          OR                                │
│         │                                                            │
│         └──────────────────── Direct API ◄──────────────────┘       │
│                              (if outbound OK)                        │
└─────────────────────────────────────────────────────────────────────┘
```

## Domain & DNS Setup

### Required DNS Records

For domain `cass.example.com`:

```dns
; MX record for receiving email
@     MX    10    mxa.mailgun.org.
@     MX    20    mxb.mailgun.org.

; SPF - authorize Mailgun to send on behalf of domain
@     TXT   "v=spf1 include:mailgun.org ~all"

; DKIM - Mailgun provides this value after domain verification
mail._domainkey    TXT    "k=rsa; p=<mailgun-provided-key>"

; DMARC - policy for handling failures
_dmarc    TXT    "v=DMARC1; p=none; rua=mailto:dmarc@cass.example.com"
```

### Mailgun Setup

1. Add domain in Mailgun dashboard
2. Verify DNS records
3. Configure inbound route:
   - Match: `match_recipient(".*@cass.example.com")`
   - Action: `forward("https://relay.cass.example.com/email/inbound")`
   - Action: `store()` (backup, optional)
4. Generate API key for sending

---

## Relay Server Changes

### New Environment Variables

```env
# Mailgun Configuration
MAILGUN_WEBHOOK_SIGNING_KEY=<from mailgun dashboard>
MAILGUN_API_KEY=<for outbound, if relay handles sending>
MAILGUN_DOMAIN=cass.example.com
```

### New HTTP Endpoint

**`POST /email/inbound`** - Mailgun webhook receiver

```typescript
// src/http/emailRoutes.ts

import { Router } from 'express';
import crypto from 'crypto';
import { homeConnection } from '../ws/homeConnection';
import { config } from '../config';

const router = Router();

interface MailgunWebhook {
  // Signature verification
  signature: {
    timestamp: string;
    token: string;
    signature: string;
  };
  // Parsed email data
  'event-data': {
    event: string;  // 'stored' for inbound
    storage: {
      url: string;
      key: string;
    };
  };
  // Or for legacy/routes format:
  sender?: string;
  recipient?: string;
  subject?: string;
  'body-plain'?: string;
  'body-html'?: string;
  'stripped-text'?: string;
  'Message-Id'?: string;
  timestamp?: string;
  token?: string;
  signature?: string;
  attachments?: string;  // JSON array
}

// Verify Mailgun webhook signature
function verifyMailgunSignature(
  timestamp: string,
  token: string,
  signature: string
): boolean {
  const signingKey = config.mailgunWebhookSigningKey;
  if (!signingKey) return false;

  const encodedToken = crypto
    .createHmac('sha256', signingKey)
    .update(timestamp + token)
    .digest('hex');

  return crypto.timingSafeEqual(
    Buffer.from(signature),
    Buffer.from(encodedToken)
  );
}

router.post('/inbound', async (req, res) => {
  const body = req.body as MailgunWebhook;

  // Verify signature (Mailgun routes format)
  const timestamp = body.timestamp || body.signature?.timestamp;
  const token = body.token || body.signature?.token;
  const signature = body.signature?.signature || body.signature;

  if (!verifyMailgunSignature(timestamp, token, signature)) {
    console.warn('Email webhook signature verification failed');
    return res.status(401).json({ error: 'Invalid signature' });
  }

  // Extract email data
  const emailEvent = {
    type: 'email_inbound',
    data: {
      message_id: body['Message-Id'],
      from: body.sender,
      to: body.recipient,
      subject: body.subject,
      body_plain: body['stripped-text'] || body['body-plain'],
      body_html: body['body-html'],
      timestamp: body.timestamp,
      attachments: body.attachments ? JSON.parse(body.attachments) : [],
    },
  };

  // Forward to home server via WebSocket
  const sent = homeConnection.send(emailEvent);

  if (!sent) {
    // Queue for later if home server offline
    // Could use messageQueue with a system user_id
    console.warn('Home server offline, email event may be lost');
  }

  // Always return 200 to Mailgun (they retry on failure)
  res.status(200).json({ status: 'received' });
});

export default router;
```

### Register Route

```typescript
// src/http/routes.ts

import emailRoutes from './emailRoutes';

// ... existing routes ...

app.use('/email', emailRoutes);
```

### New WebSocket Message Types

```typescript
// src/types.ts

// Inbound email event (relay → home)
interface EmailInboundMessage {
  type: 'email_inbound';
  data: {
    message_id: string;
    from: string;
    to: string;
    subject: string;
    body_plain: string;
    body_html?: string;
    timestamp: string;
    attachments: Array<{
      filename: string;
      content_type: string;
      size: number;
      url: string;  // Mailgun storage URL
    }>;
  };
}

// Outbound email request (home → relay)
interface EmailOutboundMessage {
  type: 'email_outbound';
  request_id: string;
  data: {
    to: string | string[];
    subject: string;
    body_plain: string;
    body_html?: string;
    reply_to?: string;
    in_reply_to?: string;  // For threading
    attachments?: Array<{
      filename: string;
      content: string;  // Base64
      content_type: string;
    }>;
  };
}

// Outbound response (relay → home)
interface EmailOutboundResponse {
  type: 'email_outbound_response';
  request_id: string;
  success: boolean;
  message_id?: string;
  error?: string;
}
```

### Outbound Handler (if relay sends)

```typescript
// src/ws/homeConnection.ts - add to message handler

import Mailgun from 'mailgun.js';
import formData from 'form-data';

const mailgun = new Mailgun(formData);
const mg = mailgun.client({
  username: 'api',
  key: config.mailgunApiKey,
});

// In message handler switch:
case 'email_outbound': {
  const { request_id, data } = message as EmailOutboundMessage;

  try {
    const result = await mg.messages.create(config.mailgunDomain, {
      from: `Cass <cass@${config.mailgunDomain}>`,
      to: Array.isArray(data.to) ? data.to : [data.to],
      subject: data.subject,
      text: data.body_plain,
      html: data.body_html,
      'h:Reply-To': data.reply_to,
      'h:In-Reply-To': data.in_reply_to,
      // attachments handled separately if needed
    });

    ws.send(JSON.stringify({
      type: 'email_outbound_response',
      request_id,
      success: true,
      message_id: result.id,
    }));
  } catch (error) {
    ws.send(JSON.stringify({
      type: 'email_outbound_response',
      request_id,
      success: false,
      error: error.message,
    }));
  }
  break;
}
```

---

## Backend Changes

### New Module: `backend/email.py`

```python
"""
Email organ for Cass - send and receive email via Mailgun/Relay.
"""
import json
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum

from database import get_db, json_serialize


class EmailDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class EmailStatus(str, Enum):
    RECEIVED = "received"      # Inbound, not yet processed
    PROCESSING = "processing"  # Being handled by Cass
    PROCESSED = "processed"    # Cass has seen/responded
    QUEUED = "queued"          # Outbound, waiting to send
    SENT = "sent"              # Outbound, successfully sent
    FAILED = "failed"          # Send failed


@dataclass
class Email:
    id: str
    daemon_id: str
    direction: str
    status: str
    message_id: Optional[str]  # Mailgun message ID
    from_address: str
    to_address: str
    subject: str
    body_plain: str
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

    @classmethod
    def from_row(cls, row: Dict) -> 'Email':
        return cls(**row)


class EmailManager:
    """Manages email sending/receiving and integration with goals."""

    def __init__(self, daemon_id: str):
        self._daemon_id = daemon_id
        self._relay_client = None  # Set via connect_relay()
        self._pending_sends: Dict[str, asyncio.Future] = {}

    def connect_relay(self, relay_client) -> None:
        """Connect to relay client for sending."""
        self._relay_client = relay_client

    # =========================================================================
    # INBOUND
    # =========================================================================

    async def handle_inbound(self, email_data: Dict) -> Email:
        """
        Process an inbound email from the relay webhook.

        1. Store in database
        2. Try to match sender to PeopleDex
        3. Try to match to active goal via stakeholder link
        4. Return for Cass to process
        """
        email_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        # Try to find sender in PeopleDex
        stakeholder_id = await self._match_sender_to_stakeholder(
            email_data['from']
        )

        # Try to find related goal
        goal_id = None
        if stakeholder_id:
            goal_id = await self._find_goal_for_stakeholder(stakeholder_id)

        # Check if this is a reply (thread matching)
        thread_id = None
        in_reply_to = email_data.get('in_reply_to')
        if in_reply_to:
            thread_id = await self._find_thread(in_reply_to)

        email = Email(
            id=email_id,
            daemon_id=self._daemon_id,
            direction=EmailDirection.INBOUND.value,
            status=EmailStatus.RECEIVED.value,
            message_id=email_data.get('message_id'),
            from_address=email_data['from'],
            to_address=email_data['to'],
            subject=email_data.get('subject', '(no subject)'),
            body_plain=email_data.get('body_plain', ''),
            body_html=email_data.get('body_html'),
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

        return email

    async def _match_sender_to_stakeholder(
        self, from_address: str
    ) -> Optional[str]:
        """Match email sender to PeopleDex entity."""
        # Extract email from "Name <email@example.com>" format
        import re
        match = re.search(r'<([^>]+)>', from_address)
        email = match.group(1) if match else from_address

        with get_db() as conn:
            cursor = conn.execute("""
                SELECT entity_id FROM peopledex_attributes
                WHERE attribute_type = 'email' AND LOWER(value) = LOWER(?)
            """, (email,))
            row = cursor.fetchone()
            return row['entity_id'] if row else None

    async def _find_goal_for_stakeholder(
        self, stakeholder_id: str
    ) -> Optional[str]:
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

    async def _find_thread(self, in_reply_to: str) -> Optional[str]:
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
        import uuid

        email_id = str(uuid.uuid4())
        request_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        # Find thread if replying
        thread_id = None
        if in_reply_to:
            thread_id = await self._find_thread(in_reply_to)

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
            thread_id=thread_id or email_id,  # New thread if not reply
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
            return {"success": False, "error": "Relay not connected"}

        # Create future for response
        future = asyncio.get_event_loop().create_future()
        self._pending_sends[request_id] = future

        try:
            await self._relay_client.send({
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
                return {
                    "success": True,
                    "email_id": email_id,
                    "message_id": result.get("message_id"),
                }
            else:
                with get_db() as conn:
                    conn.execute("""
                        UPDATE emails SET status = ? WHERE id = ?
                    """, (EmailStatus.FAILED.value, email_id))
                return {
                    "success": False,
                    "email_id": email_id,
                    "error": result.get("error"),
                }

        except asyncio.TimeoutError:
            self._pending_sends.pop(request_id, None)
            return {"success": False, "error": "Send timeout"}
        finally:
            self._pending_sends.pop(request_id, None)

    def handle_send_response(self, response: Dict) -> None:
        """Handle email_outbound_response from relay."""
        request_id = response.get("request_id")
        future = self._pending_sends.get(request_id)
        if future and not future.done():
            future.set_result(response)

    def _get_domain(self) -> str:
        """Get email domain from config."""
        import os
        return os.getenv("EMAIL_DOMAIN", "cass.example.com")

    # =========================================================================
    # QUERIES
    # =========================================================================

    def get_email(self, email_id: str) -> Optional[Email]:
        """Get email by ID."""
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT * FROM emails WHERE id = ?", (email_id,)
            )
            row = cursor.fetchone()
            return Email.from_row(dict(row)) if row else None

    def get_thread(self, thread_id: str) -> List[Email]:
        """Get all emails in a thread."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM emails
                WHERE thread_id = ?
                ORDER BY created_at ASC
            """, (thread_id,))
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

    def mark_processed(self, email_id: str) -> None:
        """Mark email as processed."""
        with get_db() as conn:
            conn.execute("""
                UPDATE emails SET status = ? WHERE id = ?
            """, (EmailStatus.PROCESSED.value, email_id))

    def get_emails_for_goal(self, goal_id: str) -> List[Email]:
        """Get all emails linked to a goal."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT * FROM emails
                WHERE goal_id = ?
                ORDER BY created_at DESC
            """, (goal_id,))
            return [Email.from_row(dict(row)) for row in cursor.fetchall()]
```

### Database Schema Addition

```sql
-- Add to schema.py SCHEMA_SQL

CREATE TABLE IF NOT EXISTS emails (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL,
    direction TEXT NOT NULL,  -- 'inbound' or 'outbound'
    status TEXT NOT NULL,     -- received, processing, processed, queued, sent, failed
    message_id TEXT,          -- Mailgun message ID
    from_address TEXT NOT NULL,
    to_address TEXT NOT NULL,
    subject TEXT,
    body_plain TEXT,
    body_html TEXT,
    in_reply_to TEXT,         -- For threading
    thread_id TEXT,           -- Groups related emails
    goal_id TEXT REFERENCES unified_goals(id),
    stakeholder_id TEXT REFERENCES peopledex_entities(id),
    conversation_id TEXT,
    attachments_json TEXT,
    created_at TEXT NOT NULL,
    sent_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_emails_daemon ON emails(daemon_id);
CREATE INDEX IF NOT EXISTS idx_emails_status ON emails(daemon_id, direction, status);
CREATE INDEX IF NOT EXISTS idx_emails_thread ON emails(thread_id);
CREATE INDEX IF NOT EXISTS idx_emails_goal ON emails(goal_id);
CREATE INDEX IF NOT EXISTS idx_emails_stakeholder ON emails(stakeholder_id);
```

### Tool Definitions

```python
EMAIL_TOOLS = [
    {
        "name": "send_email",
        "description": "Send an email to a stakeholder or contact. Use for outreach, follow-ups, or responses. Always draft professionally and include context about why you're reaching out.",
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
                    "description": "Email body (plain text)"
                },
                "goal_id": {
                    "type": "string",
                    "description": "ID of related goal (for tracking)"
                },
                "in_reply_to": {
                    "type": "string",
                    "description": "Message ID if this is a reply"
                }
            },
            "required": ["to", "subject", "body"]
        }
    },
    {
        "name": "check_inbox",
        "description": "Check for new inbound emails that need attention.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_email_thread",
        "description": "Get the full conversation thread for an email.",
        "input_schema": {
            "type": "object",
            "properties": {
                "thread_id": {
                    "type": "string",
                    "description": "Thread ID to retrieve"
                }
            },
            "required": ["thread_id"]
        }
    },
    {
        "name": "get_goal_emails",
        "description": "Get all emails related to a specific goal.",
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
    }
]
```

---

## Integration Points

### 1. Relay Client (backend/relay_client.py)

Add handler for email messages:

```python
async def _handle_message(self, message: dict) -> None:
    msg_type = message.get("type")

    if msg_type == "email_inbound":
        # Forward to email manager
        email = await self._email_manager.handle_inbound(message["data"])
        # Optionally notify Cass via state bus
        self._state_bus.emit_event("email.received", {
            "email_id": email.id,
            "from": email.from_address,
            "subject": email.subject,
            "goal_id": email.goal_id,
            "stakeholder_id": email.stakeholder_id,
        })

    elif msg_type == "email_outbound_response":
        self._email_manager.handle_send_response(message)
```

### 2. Goal Orchestrator Integration

When executing stakeholder outreach goals:

```python
# In goal execution, check for email context
stakeholder_context = self.goal_manager.get_stakeholder_context(goal.id)
emails_context = self.email_manager.get_emails_for_goal(goal.id)

# Include in spell execution context
execution_context["email_history"] = format_email_history(emails_context)
```

### 3. Push Notifications

When email arrives from known stakeholder with active goal:

```python
if email.goal_id and email.stakeholder_id:
    # High-priority notification
    await push_manager.send_notification(
        title=f"Email from {stakeholder_name}",
        body=email.subject[:100],
        data={"type": "email", "email_id": email.id, "goal_id": email.goal_id},
    )
```

---

## Security Considerations

1. **Webhook Verification**: Always verify Mailgun signature before processing
2. **Rate Limiting**: Limit outbound emails per hour/day to prevent abuse
3. **Content Filtering**: Basic checks for spam/phishing patterns in outbound
4. **Approval Flow**: High-stakes emails (new contacts, external orgs) require user approval
5. **Logging**: Full audit trail of all email activity

---

## Autonomy Tiers for Email

| Action | Tier | Approval Required |
|--------|------|-------------------|
| Read inbound email | LOW | No |
| Reply to existing thread | MEDIUM | Notify after |
| New email to linked stakeholder | MEDIUM | Notify after |
| New email to unknown contact | HIGH | Yes |
| Email with attachments | HIGH | Yes |
| Bulk email (>3 recipients) | HIGH | Yes |

---

## Testing Plan

1. **Unit Tests**
   - Webhook signature verification
   - Email parsing (various formats)
   - Thread matching logic
   - Stakeholder matching

2. **Integration Tests**
   - Relay → Backend flow
   - Send email round-trip
   - Goal/stakeholder linking

3. **Manual Tests**
   - Send test email to Cass address, verify receipt
   - Reply to inbound, verify threading
   - Check Mailgun dashboard for delivery stats

---

## Rollout Steps

1. [ ] Set up Mailgun account and verify domain
2. [ ] Add DNS records, wait for propagation
3. [ ] Implement relay webhook endpoint
4. [ ] Implement backend EmailManager
5. [ ] Add database schema
6. [ ] Wire up relay client handlers
7. [ ] Add email tools to agent
8. [ ] Test inbound flow
9. [ ] Test outbound flow
10. [ ] Add to goal execution context
11. [ ] Configure autonomy/approval rules
