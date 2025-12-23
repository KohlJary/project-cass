#!/usr/bin/env python3
"""
Interactive exploration script for the Mind Palace.
"""

from pathlib import Path
from backend.mind_palace import PalaceStorage, Navigator

PROJECT_ROOT = Path("/home/jaryk/cass/cass-vessel")

def main():
    storage = PalaceStorage(PROJECT_ROOT)
    palace = storage.load()

    if not palace:
        print("No palace found. Run init_mind_palace.py first.")
        return

    navigator = Navigator(palace)

    print("="*70)
    print("MIND PALACE EXPLORER")
    print("="*70)
    print()
    print("Type 'help' for commands, 'quit' to exit")
    print()

    # Start with overview
    print(navigator.execute("look"))
    print()

    while True:
        try:
            command = input("\n> ").strip()

            if not command:
                continue

            if command.lower() in ['quit', 'exit', 'q']:
                print("\nLeaving the Mind Palace...")
                break

            result = navigator.execute(command)
            print()
            print(result)

        except KeyboardInterrupt:
            print("\n\nLeaving the Mind Palace...")
            break
        except Exception as e:
            print(f"\nError: {e}")

if __name__ == "__main__":
    main()
