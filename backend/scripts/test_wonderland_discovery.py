#!/usr/bin/env python3
"""
Wonderland Discovery Test

Tests the PeopleDex discovery system with Wonderland NPCs.
Creates stub entries for NPCs (like a Pokédex) and tracks discovery progress.

Usage:
    python scripts/test_wonderland_discovery.py init     # Initialize stubs
    python scripts/test_wonderland_discovery.py progress # Show discovery progress
    python scripts/test_wonderland_discovery.py validate <npc_id>  # Validate facts
    python scripts/test_wonderland_discovery.py simulate # Simulate learning facts
"""

import argparse
import json
import sys
import os

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wonderland.world import WonderlandWorld
from wonderland.integration import WonderlandPeopleDexBridge


def get_world():
    """Initialize and return Wonderland world with mythology."""
    world = WonderlandWorld()
    return world


def cmd_init(args):
    """Initialize PeopleDex with NPC stubs."""
    print("=" * 60)
    print("INITIALIZING WONDERLAND NPC STUBS")
    print("=" * 60)
    print()

    world = get_world()
    bridge = WonderlandPeopleDexBridge()

    # Check mythology registry
    if not world.mythology_registry:
        print("ERROR: No mythology registry available")
        return 1

    print(f"Found {len(world.mythology_registry.npcs)} NPCs in mythology registry")
    print()

    # Sync as stubs
    stats = bridge.sync_all_npcs(world, stub_only=True)

    print(f"Results:")
    print(f"  Synced: {stats['synced']}")
    print(f"  Failed: {stats['failed']}")
    print(f"  Skipped: {stats['skipped']}")
    print()

    # Show initial progress
    progress = bridge.get_discovery_progress(world)

    if "error" in progress:
        print(f"Progress error: {progress['error']}")
        return 1

    print("Initial discovery progress:")
    print(f"  Total NPCs: {progress['total_npcs']}")
    print(f"  Discovered (any facts): {progress['discovered']}")
    print(f"  Fully discovered: {progress['fully_discovered']}")
    print(f"  Discovery rate: {progress['discovery_rate']:.1%}")
    print()

    print("NPCs created as stubs (ready for discovery):")
    for npc_id, data in progress.get("by_npc", {}).items():
        name = data.get("name", npc_id)
        known = data.get("attributes_known", 0)
        possible = data.get("attributes_possible", 0)
        print(f"  [{npc_id}] {name}: {known}/{possible} facts known")

    return 0


def cmd_progress(args):
    """Show discovery progress."""
    print("=" * 60)
    print("WONDERLAND DISCOVERY PROGRESS")
    print("=" * 60)
    print()

    world = get_world()
    bridge = WonderlandPeopleDexBridge()

    progress = bridge.get_discovery_progress(world)

    if "error" in progress:
        print(f"Error: {progress['error']}")
        return 1

    print(f"Total NPCs: {progress['total_npcs']}")
    print(f"Discovered (any facts): {progress['discovered']}")
    print(f"Fully discovered: {progress['fully_discovered']}")
    print(f"Discovery rate: {progress['discovery_rate']:.1%}")
    print()

    print("By NPC:")
    print("-" * 50)

    for npc_id, data in sorted(progress.get("by_npc", {}).items()):
        name = data.get("name", npc_id)
        status = data.get("status", "")
        known = data.get("attributes_known", 0)
        possible = data.get("attributes_possible", 0)

        if status == "not_in_peopledex":
            print(f"  {name}: NOT IN PEOPLEDEX")
        else:
            known_facts = data.get("known_facts", [])
            missing_facts = data.get("missing_facts", [])
            learned = data.get("learned_details", [])

            pct = (known / possible * 100) if possible > 0 else 0
            print(f"  {name}: {known}/{possible} ({pct:.0f}%)")

            if known_facts:
                print(f"    Known: {', '.join(known_facts)}")
            if missing_facts:
                print(f"    Missing: {', '.join(missing_facts)}")
            if learned:
                print("    Learned details:")
                for item in learned:
                    print(f"      - {item['type']}: {item['value']}")

    return 0


def cmd_validate(args):
    """Validate learned facts for an NPC."""
    if not args.npc_id:
        print("ERROR: npc_id required")
        return 1

    print(f"Validating facts for NPC: {args.npc_id}")
    print("=" * 60)

    world = get_world()
    bridge = WonderlandPeopleDexBridge()

    result = bridge.validate_learned_facts(args.npc_id, world)

    if "error" in result:
        print(f"Error: {result['error']}")
        return 1

    print(f"NPC: {result['npc_name']} ({result['npc_id']})")
    print(f"Facts learned: {result['facts_learned']}")
    print(f"Accuracy rate: {result['accuracy_rate']:.1%}")
    print()

    print("Validations:")
    for v in result.get("validations", []):
        status_icon = {
            "correct": "✓",
            "uncertain": "?",
            "novel": "+"
        }.get(v["accuracy"], "?")

        print(f"  [{status_icon}] {v['type']}: {v['learned']}")

    return 0


def cmd_simulate(args):
    """Simulate learning facts about NPCs (for testing)."""
    print("=" * 60)
    print("SIMULATING NPC FACT DISCOVERY")
    print("=" * 60)
    print()

    world = get_world()
    bridge = WonderlandPeopleDexBridge()

    if not world.mythology_registry:
        print("ERROR: No mythology registry")
        return 1

    # Pick a few NPCs to "learn about"
    npcs_to_learn = list(world.mythology_registry.npcs.values())[:3]

    print(f"Simulating discovery for {len(npcs_to_learn)} NPCs...")
    print()

    for npc in npcs_to_learn:
        print(f"Learning about: {npc.name}")

        # Simulate learning their role
        if npc.title:
            success = bridge.record_npc_fact(
                npc_id=npc.npc_id,
                attribute_type="role",
                value=f"They are known as {npc.title}",
                conversation_id="test-simulation"
            )
            if success:
                print(f"  ✓ Learned role: {npc.title}")

        # Simulate learning their description (bio)
        if npc.description:
            # Extract first sentence as a "learned" bio
            first_sentence = npc.description.split('.')[0] + '.'
            success = bridge.record_npc_fact(
                npc_id=npc.npc_id,
                attribute_type="bio",
                value=first_sentence,
                conversation_id="test-simulation"
            )
            if success:
                print(f"  ✓ Learned bio: {first_sentence[:50]}...")

        print()

    # Show updated progress
    print("Updated discovery progress:")
    print("-" * 40)

    progress = bridge.get_discovery_progress(world)
    if "error" not in progress:
        print(f"Discovery rate: {progress['discovery_rate']:.1%}")
        print(f"NPCs with any facts: {progress['discovered']}/{progress['total_npcs']}")

    return 0


def main():
    parser = argparse.ArgumentParser(description="Wonderland Discovery Test")
    subparsers = parser.add_subparsers(dest="command")

    # init command
    subparsers.add_parser("init", help="Initialize NPC stubs")

    # progress command
    subparsers.add_parser("progress", help="Show discovery progress")

    # validate command
    validate_parser = subparsers.add_parser("validate", help="Validate learned facts")
    validate_parser.add_argument("npc_id", nargs="?", help="NPC ID to validate")

    # simulate command
    subparsers.add_parser("simulate", help="Simulate learning facts")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "init":
        return cmd_init(args)
    elif args.command == "progress":
        return cmd_progress(args)
    elif args.command == "validate":
        return cmd_validate(args)
    elif args.command == "simulate":
        return cmd_simulate(args)


if __name__ == "__main__":
    sys.exit(main() or 0)
