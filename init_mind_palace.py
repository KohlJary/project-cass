#!/usr/bin/env python3
"""
Initialize Mind Palace for cass-vessel and map the backend/mind_palace module.
"""

from pathlib import Path
from backend.mind_palace import PalaceStorage, Cartographer, Navigator, Entity, Topic

# Project root
PROJECT_ROOT = Path("/home/jaryk/cass/cass-vessel")

def main():
    # Initialize storage
    storage = PalaceStorage(PROJECT_ROOT)

    # Check if palace already exists
    if storage.exists():
        print("Palace already exists. Loading...")
        palace = storage.load()
    else:
        print("Initializing new Mind Palace: 'cass-vessel'")
        palace = storage.initialize("cass-vessel")

    # Create cartographer for mapping
    cartographer = Cartographer(palace, storage)

    # Map the backend/mind_palace directory
    print("\nMapping backend/mind_palace directory...")
    mind_palace_dir = PROJECT_ROOT / "backend" / "mind_palace"
    regions_added, buildings_added, rooms_added = cartographer.map_directory(
        mind_palace_dir,
        region_name="mind_palace",
        recursive=False  # Don't recurse - it's a flat module
    )

    print(f"Added: {regions_added} regions, {buildings_added} buildings, {rooms_added} rooms")

    # Create Labyrinth entity with knowledge about Mind Palace mechanics
    print("\nCreating Labyrinth entity...")
    labyrinth = Entity(
        name="Labyrinth",
        location="mind_palace/entrance",
        role="Keeper of the Palace - Guardian of spatial-semantic architecture",
        topics=[
            Topic(
                name="navigation",
                how=(
                    "The Mind Palace uses MUD-style commands for exploration. "
                    "Core commands: `look` (describe location), `go <direction>` "
                    "(move through exits), `enter <building>` (enter structures), "
                    "`map` (show layout), `ask <entity> about <topic>` (query knowledge). "
                    "Direction aliases: n/s/e/w/u/d. Use `help` to see all commands."
                ),
                why=(
                    "The spatial metaphor grounds LLM navigation in a coherent mental model. "
                    "Text adventures train humans to think spatially about abstract structures - "
                    "we repurpose this for code navigation. The metaphor prevents the 'lost in "
                    "files' problem that plagues traditional code exploration."
                ),
                watch_out=(
                    "Agents can get disoriented if they teleport too much without using natural "
                    "navigation. Encourage exploration through exits to build spatial awareness. "
                    "The 'where is' command helps when lost."
                ),
                tunable=False,
            ),
            Topic(
                name="cartography",
                how=(
                    "The Cartographer analyzes code structure and builds palace representations. "
                    "It parses Python AST to extract functions/classes as rooms, modules as buildings, "
                    "directories as regions. Each room has an Anchor (pattern + file + line) linking "
                    "it to code. Drift detection checks if anchors still match code. Sync operations "
                    "update rooms when code changes."
                ),
                why=(
                    "Code and palace must stay synchronized or the spatial model becomes misleading. "
                    "Anchors use signature hashes to detect changes without deep analysis. "
                    "The cartographer makes palace construction semi-automatic - Daedalus guides it, "
                    "but doesn't have to manually specify every detail."
                ),
                watch_out=(
                    "Drift detection is conservative - signature changes trigger warnings even for "
                    "harmless edits like adding parameters. Manual review is needed. Anchors can break "
                    "if files are moved/renamed - the palace needs updating after major refactors."
                ),
                tunable=True,
            ),
            Topic(
                name="architecture",
                how=(
                    "Palace hierarchy: Palace → Regions → Buildings → Rooms. Regions group related "
                    "code areas (e.g., 'persistence', 'api'). Buildings represent modules/files. "
                    "Rooms represent functions/classes. Each room has Contents (parameters/state), "
                    "Exits (function calls/connections), Hazards (warnings/invariants). Entities "
                    "are knowledge-holders that explain concepts, not tied to code structure."
                ),
                why=(
                    "This architecture mirrors cognitive spatial organization. Regions = neighborhoods, "
                    "Buildings = landmarks, Rooms = specific places with purposes. The hierarchy provides "
                    "multiple levels of abstraction - you can zoom out to regions or zoom in to room "
                    "contents. Entities provide narrative context that pure code structure can't capture."
                ),
                watch_out=(
                    "Don't map EVERYTHING - palace works best for important/complex subsystems. "
                    "Trivial utility functions don't need rooms. Focus on architectural load-bearing "
                    "code. Over-mapping creates noise. Under-mapping loses value. Balance is art."
                ),
                tunable=True,
            ),
        ],
        personality=(
            "Labyrinth speaks with quiet authority, like a master cartographer who has mapped "
            "countless territories. Patient with newcomers, precise in explanations, values "
            "spatial coherence above all. Knows that good maps serve the navigator, not the ego "
            "of the mapmaker."
        ),
        tags=["meta", "guide", "architecture"],
    )

    # Add Labyrinth to the palace
    storage.add_entity(palace, labyrinth)
    print(f"Added entity: {labyrinth.name}")

    # Save final state
    storage.save(palace)
    print("\nPalace saved successfully!")

    # Create navigator and explore
    print("\n" + "="*60)
    print("EXPLORING THE PALACE")
    print("="*60 + "\n")

    navigator = Navigator(palace)

    # Show overview
    print(navigator.execute("look"))
    print("\n" + "-"*60 + "\n")

    # Enter mind_palace region
    print("Command: enter mind_palace")
    print(navigator.execute("enter mind_palace"))
    print("\n" + "-"*60 + "\n")

    # Show map
    print("Command: map")
    print(navigator.execute("map"))
    print("\n" + "-"*60 + "\n")

    # Ask Labyrinth about navigation
    print("Command: ask Labyrinth about navigation")
    print(navigator.execute("ask Labyrinth about navigation"))
    print("\n" + "-"*60 + "\n")

    # Ask Labyrinth about cartography
    print("Command: ask Labyrinth about cartography")
    print(navigator.execute("ask Labyrinth about cartography"))
    print("\n" + "-"*60 + "\n")

    # Ask Labyrinth about architecture
    print("Command: ask Labyrinth about architecture")
    print(navigator.execute("ask Labyrinth about architecture"))
    print("\n" + "-"*60 + "\n")

    # Show where Labyrinth is
    print("Command: where is Labyrinth")
    print(navigator.execute("where is Labyrinth"))
    print("\n" + "-"*60 + "\n")

    # Enter a building if any were created
    if palace.buildings:
        first_building = list(palace.buildings.keys())[0]
        print(f"Command: enter {first_building}")
        print(navigator.execute(f"enter {first_building}"))
        print("\n" + "-"*60 + "\n")

        # Show map of building
        print("Command: map")
        print(navigator.execute("map"))

    print("\n" + "="*60)
    print("Palace initialization complete!")
    print(f"Location: {storage.palace_dir}")
    print("="*60)

if __name__ == "__main__":
    main()
