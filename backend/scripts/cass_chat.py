#!/usr/bin/env python3
"""
Daedalus-Cass Communication Script

Provides a clean interface for Daedalus to communicate with Cass via REST API.
Uses the /chat endpoint which is more reliable than WebSocket for scripted use.

Usage:
    python scripts/cass_chat.py send "Your message here"
    python scripts/cass_chat.py send "Message" --conversation-id <id>
    python scripts/cass_chat.py send "Message" --new  # Force new conversation
    python scripts/cass_chat.py list                  # List recent conversations
    python scripts/cass_chat.py history <conv_id>    # Show conversation history
    python scripts/cass_chat.py summary <conv_id>    # Show working summary
    python scripts/cass_chat.py whoami                # User the server sees for our token

Environment:
    CASS_API_URL - Base URL (default: http://localhost:8000)
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

import requests

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))  # daedalus_auth

from config import DATA_DIR

DAEDALUS_USER_ID = "7fe31ade-e3d2-42b7-a128-e0e3a6b46fa1"
CREDENTIALS_FILE = DATA_DIR / "daedalus_credentials.json"
STATE_FILE = DATA_DIR / "daedalus_chat_state.json"
API_BASE = "http://localhost:8000"


def load_credentials():
    """Load Daedalus credentials"""
    if CREDENTIALS_FILE.exists():
        with open(CREDENTIALS_FILE) as f:
            return json.load(f)
    return {}


def load_state():
    """Load chat state (current conversation, etc.)"""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    """Save chat state"""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def _token_expiring(creds: dict, margin: timedelta = timedelta(minutes=5)) -> bool:
    """True if the stored token is missing, unparseable, or about to expire.

    token_expires is written by daedalus_auth.py as naive UTC.
    """
    if not creds.get("token") or not creds.get("token_expires"):
        return True
    try:
        expires = datetime.fromisoformat(creds["token_expires"])
    except ValueError:
        return True
    return expires <= datetime.utcnow() + margin


def _refresh_token(creds: dict) -> dict:
    """Mint a fresh token for the Daedalus user, as `daedalus_auth.py token` does.

    Uses the server's one token issuer (auth.create_dashboard_token, #61), so
    roles come from users.is_admin and the token verifies like any login's.
    Expiry is naive UTC, as _token_expiring expects.
    """
    import daedalus_auth
    from auth import create_dashboard_token
    token, expires = create_dashboard_token(creds["user_id"], creds["display_name"])
    creds["token"] = token
    creds["token_expires"] = expires.isoformat()
    daedalus_auth.save_credentials(creds)
    return creds


def get_auth_headers():
    """Authorization headers carrying the Daedalus user's own token.

    Tokens last 24h. An expired one used to be sent anyway; the server then
    fell back to the localhost default user, so requests ran as someone else
    and the ownership checks (#73) answered 403. Refresh first instead.
    """
    creds = load_credentials()
    if _token_expiring(creds) and "password" in creds:
        try:
            creds = _refresh_token(creds)
        except Exception as e:
            print(f"Warning: could not refresh Daedalus token: {e}", file=sys.stderr)
    if creds.get("token"):
        return {"Authorization": f"Bearer {creds['token']}"}
    print("Warning: no Daedalus token; run scripts/daedalus_auth.py setup", file=sys.stderr)
    return {}


def ensure_user_set():
    """Make Daedalus the server's current user (POST /users/current).

    /chat reads that global for user context. The route accepts only the
    caller's own id (#73), so send our token and the id it authenticates as.
    """
    try:
        response = requests.post(
            f"{API_BASE}/users/current",
            json={"user_id": whoami()},
            headers=get_auth_headers(),
            timeout=5
        )
        response.raise_for_status()
    except Exception as e:
        print(f"Warning: could not set current user: {e}", file=sys.stderr)


def whoami() -> str:
    """The user id the server sees for our token (GET /auth/me)."""
    response = requests.get(f"{API_BASE}/auth/me", headers=get_auth_headers(), timeout=10)
    response.raise_for_status()
    user_id = response.json().get("user_id")
    if user_id != DAEDALUS_USER_ID:
        print(f"Warning: authenticated as {user_id}, not the Daedalus user", file=sys.stderr)
    return user_id


def create_conversation(title: str = None) -> dict:
    """
    Create a new conversation.

    Args:
        title: Optional title for the conversation

    Returns:
        dict with 'success', 'conversation_id'
    """
    try:
        # No user_id: the server attributes the conversation to the token's user.
        payload = {}
        if title:
            payload["title"] = title

        response = requests.post(
            f"{API_BASE}/conversations/new",
            json=payload,
            headers=get_auth_headers(),
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        return {
            "success": True,
            "conversation_id": data.get("id"),
            "title": data.get("title"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def send_message(message: str, conversation_id: str = None, new: bool = False) -> dict:
    """
    Send a message to Cass and get the response.

    Args:
        message: The message to send
        conversation_id: Optional conversation ID to continue
        new: Force start a new conversation

    Returns:
        dict with 'success', 'response', 'conversation_id', 'animations'
    """
    # Ensure Daedalus is the current user
    ensure_user_set()

    state = load_state()

    # Determine conversation ID
    if new:
        # Create a new conversation first
        title = message[:50] + "..." if len(message) > 50 else message
        create_result = create_conversation(title=title)
        if not create_result["success"]:
            return create_result
        conv_id = create_result["conversation_id"]
    elif conversation_id:
        conv_id = conversation_id
    else:
        conv_id = state.get("current_conversation_id")

    # If still no conversation, create one
    if not conv_id:
        title = message[:50] + "..." if len(message) > 50 else message
        create_result = create_conversation(title=title)
        if not create_result["success"]:
            return create_result
        conv_id = create_result["conversation_id"]

    # Build request - REMOVED user_id as it's not in ChatRequest model
    payload = {
        "message": message,
        "conversation_id": conv_id,
    }

    try:
        response = requests.post(
            f"{API_BASE}/chat",
            json=payload,
            headers=get_auth_headers(),
            timeout=120  # LLM responses can be slow
        )
        response.raise_for_status()
        data = response.json()

        # Update state with current conversation
        state["current_conversation_id"] = conv_id
        state["last_message_at"] = datetime.now().isoformat()
        save_state(state)

        return {
            "success": True,
            "response": data.get("text", ""),  # API returns 'text' not 'response'
            "raw": data.get("raw", ""),
            "conversation_id": conv_id,
            "animations": data.get("animations", []),
            "tool_uses": data.get("tool_uses", []),
        }

    except requests.exceptions.Timeout:
        return {"success": False, "error": "Request timed out (120s)"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "Could not connect to Cass backend. Is it running?"}
    except requests.exceptions.HTTPError as e:
        return {"success": False, "error": f"HTTP error: {e.response.status_code} - {e.response.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_conversations(limit: int = 10) -> dict:
    """List recent conversations for Daedalus"""
    try:
        response = requests.get(
            f"{API_BASE}/conversations",
            # No user_id: the server lists the token's own conversations.
            params={"limit": limit},
            headers=get_auth_headers(),
            timeout=10
        )
        response.raise_for_status()
        return {"success": True, "conversations": response.json().get("conversations", [])}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_conversation(conversation_id: str) -> dict:
    """Get full conversation history"""
    try:
        # Conversations live in SQLite now; the old per-file JSON is gone.
        response = requests.get(
            f"{API_BASE}/conversations/{conversation_id}",
            headers=get_auth_headers(),
            timeout=10
        )
        if response.status_code == 404:
            return {"success": False, "error": "Conversation not found"}
        response.raise_for_status()
        return {"success": True, "conversation": response.json()}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_summary(conversation_id: str) -> dict:
    """Get working summary for a conversation"""
    result = get_conversation(conversation_id)
    if result["success"]:
        conv = result["conversation"]
        return {
            "success": True,
            "summary": conv.get("working_summary", "No summary yet"),
            "messages_since_summary": conv.get("messages_since_last_summary", 0),
        }
    return result


def format_conversation(conv: dict) -> str:
    """Format conversation for display"""
    lines = []
    lines.append(f"=== {conv.get('title', 'Untitled')} ===")
    lines.append(f"ID: {conv.get('id')}")
    lines.append(f"Created: {conv.get('created_at')}")
    lines.append(f"Updated: {conv.get('updated_at')}")
    lines.append("")

    if conv.get("working_summary"):
        lines.append("--- Working Summary ---")
        lines.append(conv["working_summary"])
        lines.append("")

    lines.append("--- Messages ---")
    for msg in conv.get("messages", []):
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")
        # Truncate long messages for display
        if len(content) > 500:
            content = content[:500] + "..."
        lines.append(f"\n[{role}]")
        lines.append(content)

    return "\n".join(lines)


def cmd_send(args):
    """Handle send command"""
    result = send_message(
        message=args.message,
        conversation_id=args.conversation_id,
        new=args.new
    )

    if result["success"]:
        print(f"Conversation: {result['conversation_id']}")
        print()
        print("=== Cass's Response ===")
        print(result["response"])

        if result.get("animations"):
            print()
            print("--- Animations ---")
            for anim in result["animations"]:
                print(f"  {anim.get('type')}: {anim.get('name')}")

        if result.get("tool_uses"):
            print()
            print("--- Tool Uses ---")
            for tu in result["tool_uses"]:
                print(f"  {tu}")
    else:
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)


def cmd_list(args):
    """Handle list command"""
    result = list_conversations(limit=args.limit)

    if result["success"]:
        convs = result["conversations"]
        if not convs:
            print("No conversations found")
            return

        print(f"Recent conversations for Daedalus ({len(convs)} found):")
        print()
        for conv in convs:
            updated = conv.get("updated_at", "")[:19]  # Trim to datetime
            title = conv.get("title", "Untitled")[:50]
            print(f"  {conv['id'][:8]}  {updated}  {title}")
    else:
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)


def cmd_history(args):
    """Handle history command"""
    result = get_conversation(args.conversation_id)

    if result["success"]:
        print(format_conversation(result["conversation"]))
    else:
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)


def cmd_summary(args):
    """Handle summary command"""
    result = get_summary(args.conversation_id)

    if result["success"]:
        print(f"Working Summary:")
        print(result["summary"])
        print()
        print(f"Messages since summary: {result['messages_since_summary']}")
    else:
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)


def cmd_whoami(args):
    """Show which user the server sees for our token"""
    try:
        print(whoami())
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_current(args):
    """Show current conversation state"""
    state = load_state()
    if state.get("current_conversation_id"):
        print(f"Current conversation: {state['current_conversation_id']}")
        print(f"Last message: {state.get('last_message_at', 'unknown')}")
    else:
        print("No active conversation")


def main():
    parser = argparse.ArgumentParser(
        description="Daedalus-Cass communication interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # send command
    send_parser = subparsers.add_parser("send", help="Send a message to Cass")
    send_parser.add_argument("message", help="The message to send")
    send_parser.add_argument("-c", "--conversation-id", help="Continue specific conversation")
    send_parser.add_argument("-n", "--new", action="store_true", help="Start new conversation")
    send_parser.set_defaults(func=cmd_send)

    # list command
    list_parser = subparsers.add_parser("list", help="List recent conversations")
    list_parser.add_argument("-l", "--limit", type=int, default=10, help="Number to show")
    list_parser.set_defaults(func=cmd_list)

    # history command
    history_parser = subparsers.add_parser("history", help="Show conversation history")
    history_parser.add_argument("conversation_id", help="Conversation ID")
    history_parser.set_defaults(func=cmd_history)

    # summary command
    summary_parser = subparsers.add_parser("summary", help="Show conversation summary")
    summary_parser.add_argument("conversation_id", help="Conversation ID")
    summary_parser.set_defaults(func=cmd_summary)

    # current command
    current_parser = subparsers.add_parser("current", help="Show current conversation")
    current_parser.set_defaults(func=cmd_current)

    # whoami command
    whoami_parser = subparsers.add_parser("whoami", help="Show the user the server sees for our token")
    whoami_parser.set_defaults(func=cmd_whoami)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
