#!/usr/bin/env python3
"""
Scan codebase for MAP: annotations and compare with Mind Palace.

Phase 4 of Mind Palace: Inline Annotations

Usage:
  python scripts/scan_palace_annotations.py              # Scan and show all annotations
  python scripts/scan_palace_annotations.py --sync       # Compare with palace
  python scripts/scan_palace_annotations.py --suggest    # Suggest annotations for rooms
"""

import sys
import argparse
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.mind_palace import PalaceStorage
from backend.mind_palace.annotations import scan_directory, sync_with_palace


def main():
    parser = argparse.ArgumentParser(description="Scan for MAP: annotations")
    parser.add_argument("--sync", action="store_true",
                        help="Compare annotations with palace structure")
    parser.add_argument("--suggest", action="store_true",
                        help="Suggest MAP:ROOM annotations for palace rooms")
    parser.add_argument("--dir", type=str, default="backend",
                        help="Directory to scan (default: backend)")
    args = parser.parse_args()

    scan_dir = PROJECT_ROOT / args.dir

    print(f"Scanning {scan_dir} for MAP: annotations...")
    annotations = scan_directory(scan_dir, PROJECT_ROOT)

    total_annotations = sum(len(a.annotations) for a in annotations.values())
    print(f"Found {total_annotations} annotations in {len(annotations)} files\n")

    if not annotations:
        print("No MAP: annotations found.")
        if args.suggest:
            suggest_annotations(PROJECT_ROOT)
        return 0

    # Show annotations grouped by file
    for file_path, annotated in sorted(annotations.items()):
        print(f"**{file_path}**")
        for ann in annotated.annotations:
            if ann.type == "EXIT":
                print(f"  L{ann.line}: MAP:{ann.type}:{ann.direction} {ann.value}")
            else:
                value_preview = ann.value[:60] + "..." if len(ann.value) > 60 else ann.value
                print(f"  L{ann.line}: MAP:{ann.type} {value_preview}")
        print()

    if args.sync:
        sync_with_palace_report(PROJECT_ROOT, annotations)

    if args.suggest:
        suggest_annotations(PROJECT_ROOT)

    return 0


def sync_with_palace_report(project_root: Path, annotations: dict):
    """Compare annotations with palace and report discrepancies."""
    storage = PalaceStorage(project_root)

    if not storage.exists():
        print("No palace found. Run scripts/rebuild_palace_map.py first.")
        return

    palace = storage.load()
    if not palace:
        print("Failed to load palace.")
        return

    report = sync_with_palace(annotations, palace)

    print("=" * 60)
    print("ANNOTATION SYNC REPORT")
    print("=" * 60)
    print(f"Annotations in code: {report.total_annotations}")
    print(f"Rooms in palace: {report.total_rooms}")
    print(f"Matched: {len(report.matched)}")
    print()

    if report.missing_in_palace:
        print(f"Annotations NOT in palace ({len(report.missing_in_palace)}):")
        for ann in report.missing_in_palace:
            print(f"  - {ann.value} ({ann.file}:{ann.line})")
        print()

    if report.missing_in_code and len(report.missing_in_code) < 20:
        # Only show if small number - most rooms won't have annotations
        print(f"Palace rooms without annotations ({len(report.missing_in_code)}):")
        for room in report.missing_in_code[:10]:
            print(f"  - {room}")
        if len(report.missing_in_code) > 10:
            print(f"  ... and {len(report.missing_in_code) - 10} more")


def suggest_annotations(project_root: Path):
    """Suggest annotations for high-value palace rooms."""
    storage = PalaceStorage(project_root)

    if not storage.exists():
        print("No palace found.")
        return

    palace = storage.load()
    if not palace:
        return

    # Find rooms with hazards or multiple exits (architecturally significant)
    significant_rooms = []
    for name, room in palace.rooms.items():
        # Rooms associated with entities are high-value
        if any(e.location and name.lower() in e.location.lower()
               for e in palace.entities.values()):
            significant_rooms.append((name, room, "entity-associated"))
            continue

        # Rooms with descriptions suggesting complexity
        if room.description and len(room.description) > 100:
            significant_rooms.append((name, room, "complex"))

    if significant_rooms:
        print("\n" + "=" * 60)
        print("SUGGESTED ANNOTATIONS")
        print("=" * 60)
        print("Consider adding MAP: annotations to these high-value rooms:\n")

        for name, room, reason in significant_rooms[:15]:
            print(f"**{name}** ({reason})")
            if room.anchor:
                print(f"  File: {room.anchor.file}")
                print(f"  Suggested: # MAP:ROOM {name}")
            print()


if __name__ == "__main__":
    sys.exit(main())
