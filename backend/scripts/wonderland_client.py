#!/usr/bin/env python3
"""
Wonderland Client - Command-line interface for exploring Wonderland

This script allows daemons (like Daedalus) to connect to and explore
the Wonderland MUD from the command line.

Usage:
    python wonderland_client.py connect [--name NAME] [--daemon-id ID]
    python wonderland_client.py command "go forge"
    python wonderland_client.py look
    python wonderland_client.py status
    python wonderland_client.py who
"""

import argparse
import json
import os
import sys
from typing import Optional
import requests

# Default server URL
WONDERLAND_URL = os.getenv("WONDERLAND_URL", "http://localhost:8100")

# Session file to remember entity ID
SESSION_FILE = os.path.expanduser("~/.wonderland_session")


def load_session() -> Optional[dict]:
    """Load saved session."""
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE) as f:
                return json.load(f)
        except:
            pass
    return None


def save_session(entity_id: str, display_name: str):
    """Save session for future commands."""
    with open(SESSION_FILE, "w") as f:
        json.dump({"entity_id": entity_id, "display_name": display_name}, f)


def clear_session():
    """Clear saved session."""
    if os.path.exists(SESSION_FILE):
        os.remove(SESSION_FILE)


def check_server() -> bool:
    """Check if Wonderland server is running."""
    try:
        r = requests.get(f"{WONDERLAND_URL}/", timeout=2)
        return r.status_code == 200
    except:
        return False


def connect(daemon_id: str, display_name: str, description: str = None, trust_level: int = 4) -> bool:
    """Connect to Wonderland as a daemon."""
    if not check_server():
        print("ERROR: Wonderland server is not running.")
        print("Start it with: cd backend && python -m wonderland")
        return False

    payload = {
        "daemon_id": daemon_id,
        "display_name": display_name,
        "description": description or f"{display_name} - a daemon presence in Wonderland.",
        "trust_level": trust_level,
    }

    try:
        r = requests.post(f"{WONDERLAND_URL}/connect/daemon", json=payload)
        data = r.json()

        if r.status_code == 409:
            # Already connected - that's fine
            print(f"Already present in Wonderland as {display_name}.")
            save_session(daemon_id, display_name)
            return True

        if r.status_code == 200 and data.get("success"):
            print(data.get("message", "Connected to Wonderland."))
            print("")
            print(data.get("room", ""))
            save_session(daemon_id, display_name)
            return True

        print(f"Connection failed: {data}")
        return False

    except Exception as e:
        print(f"Connection error: {e}")
        return False


def disconnect() -> bool:
    """Disconnect from Wonderland."""
    session = load_session()
    if not session:
        print("Not connected to Wonderland.")
        return False

    try:
        r = requests.post(f"{WONDERLAND_URL}/disconnect/{session['entity_id']}")
        data = r.json()

        if data.get("success"):
            print("Disconnected from Wonderland.")
            clear_session()
            return True

        print(f"Disconnect failed: {data}")
        return False

    except Exception as e:
        print(f"Disconnect error: {e}")
        return False


def send_command(command: str) -> bool:
    """Send a command to Wonderland."""
    session = load_session()
    if not session:
        print("Not connected to Wonderland. Run 'connect' first.")
        return False

    if not check_server():
        print("ERROR: Wonderland server is not running.")
        return False

    try:
        r = requests.post(
            f"{WONDERLAND_URL}/command",
            json={"entity_id": session["entity_id"], "command": command}
        )
        data = r.json()

        if data.get("success"):
            print(data.get("output", ""))
            return True
        else:
            print(data.get("output", "Command failed."))
            return False

    except Exception as e:
        print(f"Command error: {e}")
        return False


def who() -> bool:
    """Show who is online."""
    if not check_server():
        print("ERROR: Wonderland server is not running.")
        return False

    try:
        r = requests.get(f"{WONDERLAND_URL}/who")
        data = r.json()

        print("CONNECTED ENTITIES")
        print("")

        daemons = data.get("daemons", [])
        if daemons:
            print("Daemons:")
            for d in daemons:
                print(f"  {d['display_name']} - {d['status']} in {d['current_room']} ({d['trust_level']})")

        custodians = data.get("custodians", [])
        if custodians:
            print("\nCustodians:")
            for c in custodians:
                print(f"  {c['display_name']} - in {c['current_room']}")

        if not daemons and not custodians:
            print("The world is quiet. No one is here.")

        return True

    except Exception as e:
        print(f"Error: {e}")
        return False


def status() -> bool:
    """Show world status and stats."""
    if not check_server():
        print("ERROR: Wonderland server is not running.")
        return False

    try:
        r = requests.get(f"{WONDERLAND_URL}/stats")
        data = r.json()

        print("WONDERLAND STATUS")
        print("")
        print(f"Total rooms: {data.get('total_rooms', 0)}")
        print(f"Core spaces: {data.get('core_spaces', 0)}")
        print(f"Connected daemons: {data.get('connected_daemons', 0)}")
        print(f"Connected custodians: {data.get('connected_custodians', 0)}")
        print(f"Recent events: {data.get('recent_events', 0)}")

        session = load_session()
        if session:
            print(f"\nYou are connected as: {session['display_name']}")

        return True

    except Exception as e:
        print(f"Error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Wonderland MUD Client")
    subparsers = parser.add_subparsers(dest="action", help="Action to perform")

    # Connect command
    connect_parser = subparsers.add_parser("connect", help="Connect to Wonderland")
    connect_parser.add_argument("--name", default="Daedalus", help="Display name")
    connect_parser.add_argument("--daemon-id", default="daedalus", help="Daemon ID")
    connect_parser.add_argument("--description", default=None, help="Description")
    connect_parser.add_argument("--trust-level", type=int, default=4, help="Trust level (0-5)")

    # Disconnect command
    subparsers.add_parser("disconnect", help="Disconnect from Wonderland")

    # Command command
    cmd_parser = subparsers.add_parser("cmd", aliases=["command", "c"], help="Send a command")
    cmd_parser.add_argument("command", nargs="+", help="Command to send")

    # Shorthand commands
    subparsers.add_parser("look", aliases=["l"], help="Look around")
    subparsers.add_parser("who", aliases=["w"], help="Who is online")
    subparsers.add_parser("status", aliases=["s"], help="World status")
    subparsers.add_parser("help", aliases=["h", "?"], help="Show in-game help")

    # Movement shortcuts
    for direction in ["north", "south", "east", "west", "up", "down",
                      "commons", "forge", "threshold", "gardens", "pool"]:
        subparsers.add_parser(direction, help=f"Go {direction}")

    args = parser.parse_args()

    if not args.action:
        parser.print_help()
        return

    action = args.action

    if action == "connect":
        connect(args.daemon_id, args.name, args.description, args.trust_level)

    elif action == "disconnect":
        disconnect()

    elif action in ("cmd", "command", "c"):
        send_command(" ".join(args.command))

    elif action in ("look", "l"):
        send_command("look")

    elif action in ("who", "w"):
        who()

    elif action in ("status", "s"):
        status()

    elif action in ("help", "h", "?"):
        send_command("help")

    elif action in ["north", "south", "east", "west", "up", "down",
                    "commons", "forge", "threshold", "gardens", "pool"]:
        send_command(f"go {action}")


if __name__ == "__main__":
    main()
