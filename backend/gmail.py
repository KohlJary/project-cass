"""
Her Gmail (cassandrajary@gmail.com; Kohl, 2026-11-18): a second mailbox for the
email organ, beside the Mailgun relay. Lever `gmail`, off until Kohl switches it on.

Inbound: IMAP over SSL. New messages in INBOX (by UID, above the last one seen)
become the same email_data dicts the relay webhook delivers, and go through
EmailManager.handle_inbound, so threading, PeopleDex matching, the phase-change
inbox check and her replies all work unchanged. Messages are read with
BODY.PEEK, so Gmail's own read/unread state is left alone.

Outbound: SMTP over SSL (smtp.gmail.com:465). EmailManager.send_email uses this
when the lever is on, so her replies, reach_out copies and her send_email tool all
go out from this address. Kohl's call (2026-11-18): she may write first, too.

The app password lives in DATA_DIR/gmail/credentials.json (mode 600; Kohl places
it), outside every workshop project, so her sandbox never sees it:
    {"user": "cassandrajary@gmail.com", "app_password": "..."}
Revoking the app password in her Google account cuts this off at once.
"""
from __future__ import annotations

import base64
import email
import imaplib
import json
import logging
import smtplib
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

LEVER = "gmail"
IMAP_HOST, IMAP_PORT = "imap.gmail.com", 993
SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 465
DISPLAY_NAME = "Cass"
FETCH_MAX = 50          # per check; the rest come next time
TIMEOUT_S = 30


def _dir(data_dir: Optional[Path] = None) -> Path:
    if data_dir is None:
        from config import DATA_DIR
        data_dir = Path(DATA_DIR)
    return Path(data_dir) / "gmail"


def credentials(data_dir: Optional[Path] = None) -> Optional[Dict[str, str]]:
    p = _dir(data_dir) / "credentials.json"
    try:
        c = json.loads(p.read_text())
    except (OSError, ValueError):
        return None
    user = str(c.get("user") or "").strip()
    pw = "".join(str(c.get("app_password") or "").split())   # Google shows it in groups of four
    return {"user": user, "app_password": pw} if user and pw else None


def enabled(data_dir: Optional[Path] = None) -> bool:
    try:
        from features import is_enabled
        if not is_enabled(LEVER):
            return False
    except Exception:
        return False
    return credentials(data_dir) is not None


def address(data_dir: Optional[Path] = None) -> Optional[str]:
    c = credentials(data_dir)
    return c["user"].lower() if c else None


# --- inbound ------------------------------------------------------------------

def _state_path(data_dir: Optional[Path]) -> Path:
    return _dir(data_dir) / "state.json"


def _load_state(data_dir: Optional[Path]) -> Dict[str, Any]:
    try:
        return json.loads(_state_path(data_dir).read_text())
    except (OSError, ValueError):
        return {}


def _save_state(state: Dict[str, Any], data_dir: Optional[Path]) -> None:
    p = _state_path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state))


def _h(msg, name: str) -> str:
    v = msg.get(name)
    if not v:
        return ""
    try:
        return str(make_header(decode_header(v)))
    except Exception:
        return str(v)


def parse(raw: bytes) -> Dict[str, Any]:
    """One RFC 822 message -> the email_data shape handle_inbound takes."""
    msg = email.message_from_bytes(raw)
    plain, html, attachments = [], [], []
    for part in msg.walk():
        if part.is_multipart():
            continue
        disp = (part.get("Content-Disposition") or "").lower()
        ctype = part.get_content_type()
        payload = part.get_payload(decode=True)
        if not isinstance(payload, (bytes, bytearray)):
            payload = b""
        if "attachment" in disp or part.get_filename():
            attachments.append({"filename": part.get_filename() or "attachment", "content_type": ctype,
                                "size": len(payload)})
            continue
        text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if ctype == "text/plain":
            plain.append(text)
        elif ctype == "text/html":
            html.append(text)
    data = {
        "from": _h(msg, "From"), "to": _h(msg, "To"), "subject": _h(msg, "Subject") or "(no subject)",
        "message_id": (msg.get("Message-ID") or "").strip() or None,
        "in_reply_to": (msg.get("In-Reply-To") or "").strip() or None,
        "body_plain": "\n".join(plain).strip(), "body_html": "\n".join(html).strip() or None,
        "attachments": attachments, "via": "gmail",
    }
    # the headers detect_automated_sender looks at
    for k in ("List-Id", "List-Unsubscribe", "Auto-Submitted", "Precedence", "X-Auto-Response-Suppress"):
        if msg.get(k):
            data[k] = str(msg.get(k))
    return data


def fetch_new(data_dir: Optional[Path] = None, imap_factory=None) -> List[Dict[str, Any]]:
    """New INBOX messages since the last check, oldest first (at most FETCH_MAX)."""
    c = credentials(data_dir)
    if c is None:
        return []
    state = _load_state(data_dir)
    factory = imap_factory or (lambda: imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, timeout=TIMEOUT_S))
    imap = factory()
    out: List[Dict[str, Any]] = []
    try:
        imap.login(c["user"], c["app_password"])
        typ, data = imap.select("INBOX", readonly=True)
        if typ != "OK":
            raise RuntimeError(f"couldn't open INBOX: {data}")
        typ, v = imap.response("UIDVALIDITY")
        validity = (v[0].decode() if v and v[0] else "") if typ == "OK" else ""
        last = int(state.get("last_uid", 0)) if state.get("uidvalidity") == validity else 0
        typ, data = imap.uid("search", None, f"UID {last + 1}:*")
        uids = sorted(int(u) for u in (data[0].split() if data and data[0] else []) if int(u) > last)
        for uid in uids[:FETCH_MAX]:
            typ, parts = imap.uid("fetch", str(uid), "(BODY.PEEK[])")
            raw = next((p[1] for p in parts or [] if isinstance(p, tuple) and len(p) > 1), None)
            if raw:
                d = parse(raw)
                d["gmail_uid"] = uid
                out.append(d)
            last = uid
        _save_state({"uidvalidity": validity, "last_uid": last}, data_dir)
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    return out


# --- outbound -----------------------------------------------------------------

def send(to: str, subject: str, body_plain: str, body_html: Optional[str] = None,
         in_reply_to: Optional[str] = None, reply_to: Optional[str] = None,
         attachments: Optional[List[Dict[str, Any]]] = None,
         data_dir: Optional[Path] = None, smtp_factory=None) -> Dict[str, Any]:
    """Send one message from her Gmail. Returns {"success", "message_id"} or {"success": False, "error"}."""
    c = credentials(data_dir)
    if c is None:
        return {"success": False, "error": "no Gmail credentials (DATA_DIR/gmail/credentials.json)"}
    msg = EmailMessage()
    msg["From"] = formataddr((DISPLAY_NAME, c["user"]))
    msg["To"] = to
    msg["Subject"] = subject
    mid = make_msgid(domain=c["user"].split("@")[-1])
    msg["Message-ID"] = mid
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body_plain or "")
    if body_html:
        msg.add_alternative(body_html, subtype="html")
    for a in attachments or []:
        try:
            blob = base64.b64decode(a.get("content_base64") or "")
        except Exception:
            continue
        maintype, _, subtype = (a.get("content_type") or "application/octet-stream").partition("/")
        msg.add_attachment(blob, maintype=maintype, subtype=subtype or "octet-stream",
                           filename=a.get("filename") or "attachment")
    factory = smtp_factory or (lambda: smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=TIMEOUT_S))
    try:
        with factory() as s:
            s.login(c["user"], c["app_password"])
            s.send_message(msg)
    except Exception as e:
        logger.warning(f"[gmail] send to {parseaddr(to)[1]} failed: {type(e).__name__}")
        return {"success": False, "error": f"{type(e).__name__}: {e}"}
    return {"success": True, "message_id": mid}
