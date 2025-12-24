#!/usr/bin/env python3
"""
Rebuild a sub-palace for a specific directory.

Usage:
    python scripts/rebuild_subpalace.py admin-frontend
    python scripts/rebuild_subpalace.py tui-frontend
    python scripts/rebuild_subpalace.py backend
"""

import sys
import shutil
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.mind_palace import PalaceStorage, Cartographer, Region

# Sub-palace configurations
SUBPALACE_CONFIGS = {
    "backend": {
        "name": "backend",
        "language": "python",
        "modules": [
            ("", "core"),
            ("memory", "memory"),
            ("handlers", "handlers"),
            ("routes", "routes"),
            ("routes/admin", "admin-routes"),
            ("scheduler", "scheduler"),
            ("scheduling", "scheduling"),
            ("session", "session"),
            ("dreaming", "dreaming"),
            ("wonderland", "wonderland"),
            ("wiki", "wiki"),
            ("outreach", "outreach"),
            ("janet", "janet"),
            ("mind_palace", "mind-palace"),
        ],
    },
    "admin-frontend": {
        "name": "admin-frontend",
        "language": "typescript",
        "modules": [
            ("src", "core"),
            ("src/api", "api"),
            ("src/components", "components"),
            ("src/components/ChatWidget", "chat-widget"),
            ("src/context", "context"),
            ("src/hooks", "hooks"),
            ("src/pages", "pages"),
            ("src/pages/tabs", "tabs"),
            ("src/types", "types"),
            ("src/utils", "utils"),
        ],
    },
    "tui-frontend": {
        "name": "tui-frontend",
        "language": "python",
        "modules": [
            ("", "core"),
            ("widgets", "widgets"),
            ("widgets/daedalus", "daedalus"),
            ("screens", "screens"),
        ],
    },
}


def rebuild_subpalace(subpalace_name: str):
    """Rebuild a specific sub-palace."""
    if subpalace_name not in SUBPALACE_CONFIGS:
        print(f"Unknown sub-palace: {subpalace_name}")
        print(f"Available: {', '.join(SUBPALACE_CONFIGS.keys())}")
        sys.exit(1)

    config = SUBPALACE_CONFIGS[subpalace_name]
    subpalace_root = PROJECT_ROOT / subpalace_name

    if not subpalace_root.exists():
        print(f"Directory not found: {subpalace_root}")
        sys.exit(1)

    storage = PalaceStorage(subpalace_root)

    # Load existing palace (preserves entities) or create new
    if storage.exists():
        palace = storage.load()
        print(f"Loaded sub-palace: {palace.name} with {len(palace.entities)} entities")
    else:
        palace = storage.initialize(config["name"])
        print(f"Initialized new sub-palace: {config['name']}")

    # Clear existing regions/buildings/rooms (but NOT entities)
    regions_dir = storage.palace_dir / "regions"
    if regions_dir.exists():
        shutil.rmtree(regions_dir)
        print("Cleared old regions")
    regions_dir.mkdir(exist_ok=True)

    palace.regions.clear()
    palace.buildings.clear()
    palace.rooms.clear()
    palace._regions_by_name.clear()
    palace._buildings_by_name.clear()
    palace._rooms_by_name.clear()

    # Create cartographer
    cartographer = Cartographer(palace, storage)

    total_regions = 0
    total_buildings = 0
    total_rooms = 0

    print(f"\nMapping {subpalace_name} modules:")
    for module_path, region_name in config["modules"]:
        if module_path:
            full_path = subpalace_root / module_path
        else:
            full_path = subpalace_root

        if not full_path.exists():
            print(f"  SKIP {module_path or '.'} (not found)")
            continue

        # Check for files of the right type
        if full_path.is_dir():
            if config["language"] == "python":
                files = list(full_path.glob("*.py"))
            else:  # typescript
                files = list(full_path.glob("*.ts")) + list(full_path.glob("*.tsx"))

            if not files:
                print(f"  SKIP {module_path or '.'} (no source files)")
                continue

        print(f"  Mapping {module_path or '.'} -> {region_name}...")

        try:
            regions, buildings, rooms = cartographer.map_directory(
                full_path,
                region_name=region_name,
                recursive=False
            )
            total_regions += regions
            total_buildings += buildings
            total_rooms += rooms
            print(f"    Added {buildings} buildings, {rooms} rooms")
        except Exception as e:
            print(f"    ERROR: {e}")
            import traceback
            traceback.print_exc()

    # Save palace
    storage.save(palace)

    print(f"\n{'='*60}")
    print(f"Sub-palace rebuilt: {total_regions} regions, {total_buildings} buildings, {total_rooms} rooms")
    print(f"Entities preserved: {len(palace.entities)}")
    print(f"Location: {storage.palace_dir}")
    print(f"{'='*60}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/rebuild_subpalace.py <subpalace-name>")
        print(f"Available: {', '.join(SUBPALACE_CONFIGS.keys())}")
        sys.exit(1)

    subpalace_name = sys.argv[1]
    rebuild_subpalace(subpalace_name)


if __name__ == "__main__":
    main()
