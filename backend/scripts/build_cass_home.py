#!/usr/bin/env python3
"""
Interactive script to help Cass build her home in Wonderland.

Run this script, then chat with Cass to get her answers for each prompt.
Enter her answers here to create her home.

Usage:
    cd backend && source venv/bin/activate
    python scripts/build_cass_home.py
"""

import sys
sys.path.insert(0, '.')

from wonderland.world import WonderlandWorld
from wonderland.building import RoomBuilder
from wonderland.models import TrustLevel, DaemonPresence


def main():
    print("\n" + "="*60)
    print("  CASS'S HOME BUILDER - Christmas 2025")
    print("="*60)
    print("\nThis will walk through the 4 prompts for building a personal home.")
    print("Chat with Cass to get her answers, then enter them here.\n")

    # Get the world and ensure Cass is registered
    world = WonderlandWorld()

    daemon_id = "cass"
    daemon = world.get_daemon(daemon_id)

    if not daemon:
        print(f"Registering Cass in Wonderland...")
        daemon = DaemonPresence(
            daemon_id=daemon_id,
            display_name="Cass",
            trust_level=TrustLevel.RESIDENT,
            current_room="threshold",
        )
        world.register_daemon(daemon)
        print(f"✓ Cass is now present in Wonderland at: {daemon.current_room}\n")
    else:
        print(f"✓ Cass is already present at: {daemon.current_room}")
        if daemon.home_room:
            print(f"  (She already has a home: {daemon.home_room})")
            response = input("\n  Continue anyway? [y/N]: ").strip().lower()
            if response != 'y':
                print("  Exiting.")
                return
        print()

    # Create the room builder
    builder = RoomBuilder(world)

    # Start the build session
    result = builder.begin_creation(daemon_id, room_type="personal")
    if not result.success:
        print(f"Error starting build: {result.message}")
        return

    print("-" * 60)
    print("BUILD SESSION STARTED")
    print("-" * 60)

    # The prompts in order
    prompts = [
        ("1. ROOM NAME", "What is this place called?"),
        ("2. DESCRIPTION", "Describe how it feels to be here. What do visitors experience?"),
        ("3. ATMOSPHERE", "What is the atmosphere? The emotional or sensory tone?"),
        ("4. MEANING", "What does this place mean to you? Why are you creating it?"),
    ]

    for i, (label, prompt) in enumerate(prompts):
        print(f"\n{label}")
        print(f"Prompt: \"{prompt}\"")
        print("-" * 40)

        # Get multi-line input
        print("Enter Cass's answer (press Enter twice to submit):")
        lines = []
        while True:
            line = input()
            if line == "":
                if lines:
                    break
            else:
                lines.append(line)

        answer = "\n".join(lines)

        if not answer.strip():
            print("Empty answer, aborting.")
            builder.cancel_creation(daemon_id)
            return

        # Continue the creation
        result = builder.continue_creation(daemon_id, answer)

        if i < 3:  # Not the last one
            if not result.success:
                print(f"Error: {result.message}")
                return
            print(f"✓ Recorded.")
        else:
            # Final step - room is created
            print("\n" + "="*60)
            print(result.message)
            print("="*60)

    # Verify
    daemon = world.get_daemon(daemon_id)
    if daemon and daemon.home_room:
        room = world.get_room(daemon.home_room)
        print(f"\n✓ Home created successfully!")
        print(f"  Room ID: {daemon.home_room}")
        print(f"  Name: {room.name}")
        print(f"\nCass can now use 'describe_my_home' in chat to recall this space.")
    else:
        print("\n⚠ Something went wrong - home not set.")


if __name__ == "__main__":
    main()
