#!/usr/bin/env python3
"""
Test various navigation commands to demonstrate Mind Palace capabilities.
"""

from pathlib import Path
from backend.mind_palace import PalaceStorage, Navigator

PROJECT_ROOT = Path("/home/jaryk/cass/cass-vessel")

def test_command(navigator, command, description):
    print(f"\n{'='*70}")
    print(f"TEST: {description}")
    print(f"COMMAND: {command}")
    print(f"{'='*70}\n")
    result = navigator.execute(command)
    print(result)

def main():
    storage = PalaceStorage(PROJECT_ROOT)
    palace = storage.load()
    navigator = Navigator(palace)

    # Test 1: Basic navigation
    test_command(navigator, "enter mind_palace",
                 "Enter the mind_palace region")

    # Test 2: Enter a building
    test_command(navigator, "enter navigator",
                 "Enter the navigator building")

    # Test 3: Look at current room
    test_command(navigator, "look",
                 "Examine current location in detail")

    # Test 4: Go to another room
    test_command(navigator, "go north",
                 "Move through north exit")

    # Test 5: Show exits
    test_command(navigator, "exits",
                 "List all available exits")

    # Test 6: Show building map
    test_command(navigator, "map",
                 "Display building floor plan")

    # Test 7: Teleport to a specific room
    test_command(navigator, "teleport Cartographer",
                 "Jump directly to Cartographer class room")

    # Test 8: Look at the Cartographer room
    test_command(navigator, "look",
                 "Examine Cartographer class")

    # Test 9: Check hazards
    test_command(navigator, "hazards",
                 "Check for hazards in current room")

    # Test 10: Find something
    test_command(navigator, "where is check_drift",
                 "Locate the check_drift function")

    # Test 11: Enter cartographer building and explore
    test_command(navigator, "enter cartographer",
                 "Enter the cartographer building")

    # Test 12: Ask Labyrinth about navigation
    test_command(navigator, "ask Labyrinth about navigation",
                 "Query Labyrinth entity about MUD navigation")

    # Test 13: Show history
    test_command(navigator, "history",
                 "Show modification history of current room")

    # Test 14: Help
    test_command(navigator, "help",
                 "Display all available commands")

    print(f"\n{'='*70}")
    print("TESTING COMPLETE")
    print(f"{'='*70}\n")

if __name__ == "__main__":
    main()
