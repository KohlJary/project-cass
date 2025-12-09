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

Environment:
    CASS_API_URL - Base URL (default: http://localhost:8000)
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

import requests

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

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


def get_auth_headers():
    """Get authorization headers"""
    creds = load_credentials()
    if "token" in creds:
        return {"Authorization": f"Bearer {creds['token']}"}
    return {}


def create_conversation(title: str = None) -> dict:
    """
    Create a new conversation.

    Args:
        title: Optional title for the conversation

    Returns:
        dict with 'success', 'conversation_id'
    """
    try:
        payload = {
            "user_id": DAEDALUS_USER_ID,
        }
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

    # Build request
    payload = {
        "message": message,
        "user_id": DAEDALUS_USER_ID,
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
            params={"user_id": DAEDALUS_USER_ID, "limit": limit},
            headers=get_auth_headers(),
            timeout=10
        )
        response.raise_for_status()
        return {"success": True, "conversations": response.json()}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_conversation(conversation_id: str) -> dict:
    """Get full conversation history"""
    try:
        # Read directly from file since API might have auth issues
        conv_file = DATA_DIR / "conversations" / f"{conversation_id}.json"
        if conv_file.exists():
            with open(conv_file) as f:
                return {"success": True, "conversation": json.load(f)}
        return {"success": False, "error": "Conversation not found"}
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

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
