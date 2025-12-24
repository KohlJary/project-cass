#!/usr/bin/env python3
"""
Rebuild Mind Palace room/building/region structure from backend code.

This regenerates the .mind-palace/regions/ directory which is gitignored.
Entities are preserved (they're curated and checked into git).

Run after pulling fresh code or after major refactors.
"""

import sys
from pathlib import Path
import shutil

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.mind_palace import PalaceStorage, Cartographer, Region

# Backend modules to map (skip data directories, tests, etc.)
BACKEND_MODULES = [
    # Core
    ("backend", "core"),
    ("backend/memory", "memory"),
    ("backend/handlers", "handlers"),
    ("backend/routes", "routes"),
    ("backend/routes/admin", "admin-routes"),
    ("backend/scheduler", "scheduler"),
    ("backend/scheduling", "scheduling"),
    ("backend/session", "session"),
    # Features
    ("backend/dreaming", "dreaming"),
    ("backend/wonderland", "wonderland"),
    ("backend/wiki", "wiki"),
    ("backend/outreach", "outreach"),
    ("backend/janet", "janet"),
    ("backend/mind_palace", "mind-palace"),
]


def main():
    storage = PalaceStorage(PROJECT_ROOT)

    # Load existing palace (preserves entities)
    if storage.exists():
        palace = storage.load()
        print(f"Loaded palace: {palace.name} with {len(palace.entities)} entities")
    else:
        palace = storage.initialize("cass-vessel")
        print("Initialized new palace")

    # Clear existing regions/buildings/rooms (but NOT entities)
    regions_dir = storage.palace_dir / "regions"
    if regions_dir.exists():
        shutil.rmtree(regions_dir)
        print("Cleared old regions")
    regions_dir.mkdir(exist_ok=True)

    palace.regions.clear()
    palace.buildings.clear()
    palace.rooms.clear()

    # Create cartographer
    cartographer = Cartographer(palace, storage)

    total_regions = 0
    total_buildings = 0
    total_rooms = 0

    print("\nMapping backend modules:")
    for module_path, region_name in BACKEND_MODULES:
        full_path = PROJECT_ROOT / module_path
        if not full_path.exists():
            print(f"  SKIP {module_path} (not found)")
            continue

        # Check if it's a directory with Python files
        if full_path.is_dir():
            py_files = list(full_path.glob("*.py"))
            if not py_files:
                print(f"  SKIP {module_path} (no .py files)")
                continue

        print(f"  Mapping {module_path} -> {region_name}...")

        try:
            regions, buildings, rooms = cartographer.map_directory(
                full_path,
                region_name=region_name,
                recursive=False  # Each module mapped separately
            )
            total_regions += regions
            total_buildings += buildings
            total_rooms += rooms
            print(f"    Added {buildings} buildings, {rooms} rooms")
        except Exception as e:
            print(f"    ERROR: {e}")

    # Save palace
    storage.save(palace)

    print(f"\n{'='*60}")
    print(f"Palace rebuilt: {total_regions} regions, {total_buildings} buildings, {total_rooms} rooms")
    print(f"Entities preserved: {len(palace.entities)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
