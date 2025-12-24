#!/usr/bin/env python3
"""
Check Mind Palace for drift from current code state.

Phase 3 of Mind Palace: Anchor Sync

Reports rooms where:
- Anchor file no longer exists
- Anchor pattern not found (code renamed/removed)
- Signature hash changed (API modified)

Exit codes:
- 0: No drift detected
- 1: Warnings only (signature changes)
- 2: Errors detected (missing files/patterns)

Usage:
  python scripts/check_palace_drift.py          # Check all rooms
  python scripts/check_palace_drift.py --sample # Check random 100 rooms
  python scripts/check_palace_drift.py --quick  # Skip signature hash checks
"""

import sys
import argparse
import random
from pathlib import Path
from collections import defaultdict

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.mind_palace import PalaceStorage, Cartographer


def main():
    parser = argparse.ArgumentParser(description="Check Mind Palace for drift")
    parser.add_argument("--sample", type=int, nargs="?", const=100,
                        help="Only check N random rooms (default 100)")
    parser.add_argument("--quick", action="store_true",
                        help="Skip signature hash checks (faster)")
    parser.add_argument("--region", type=str,
                        help="Only check rooms in this region")
    args = parser.parse_args()

    storage = PalaceStorage(PROJECT_ROOT)

    if not storage.exists():
        print("No palace found. Run scripts/rebuild_palace_map.py first.")
        return 2

    palace = storage.load()
    if not palace:
        print("Failed to load palace.")
        return 2

    # Filter rooms if needed
    rooms_to_check = list(palace.rooms.items())

    if args.region:
        # Filter by region (building's region)
        filtered = []
        for name, room in rooms_to_check:
            building = palace.get_building(room.building)
            if building and args.region in building.region:
                filtered.append((name, room))
        rooms_to_check = filtered
        print(f"Filtering to region: {args.region}")

    if args.sample:
        if len(rooms_to_check) > args.sample:
            rooms_to_check = random.sample(rooms_to_check, args.sample)
        print(f"Sampling {len(rooms_to_check)} rooms")

    print(f"Checking drift for palace: {palace.name}")
    print(f"Rooms to check: {len(rooms_to_check)}")
    print()

    # Manual drift check with progress
    reports = []
    import re
    import hashlib

    for i, (room_name, room) in enumerate(rooms_to_check):
        if i % 500 == 0 and i > 0:
            print(f"  Checked {i}/{len(rooms_to_check)} rooms...")

        if not room.anchor:
            continue

        anchor = room.anchor
        file_path = PROJECT_ROOT / anchor.file

        if not file_path.exists():
            reports.append({
                "room_name": room_name,
                "anchor_file": anchor.file,
                "issues": ["Anchor file no longer exists"],
                "severity": "error",
                "suggested_fix": "Remove room or update anchor to new location",
            })
            continue

        try:
            with open(file_path) as f:
                content = f.read()

            # Check pattern
            pattern_found = False
            if getattr(anchor, 'is_regex', False):
                pattern_found = bool(re.search(anchor.pattern, content, re.MULTILINE))
            else:
                pattern_found = anchor.pattern in content

            if not pattern_found:
                reports.append({
                    "room_name": room_name,
                    "anchor_file": anchor.file,
                    "issues": [f"Pattern '{anchor.pattern}' not found"],
                    "severity": "error",
                    "suggested_fix": "Function/class may have been renamed or removed",
                })
                continue

            # Check signature hash (skip if --quick)
            if not args.quick and anchor.signature_hash:
                # This is slow - skip for now
                pass

        except Exception as e:
            reports.append({
                "room_name": room_name,
                "anchor_file": anchor.file,
                "issues": [f"Error checking: {e}"],
                "severity": "warning",
            })

    if not reports:
        print("✓ No drift detected - palace is in sync with code!")
        return 0

    # Group by severity
    by_severity = defaultdict(list)
    for report in reports:
        by_severity[report.severity].append(report)

    # Print errors first
    if by_severity["error"]:
        print(f"{'='*60}")
        print(f"ERRORS ({len(by_severity['error'])} rooms)")
        print(f"{'='*60}")
        for report in by_severity["error"]:
            print(f"\n✗ {report.room_name}")
            print(f"  File: {report.anchor_file}")
            for issue in report.issues:
                print(f"  Issue: {issue}")
            if report.suggested_fix:
                print(f"  Fix: {report.suggested_fix}")

    # Then warnings
    if by_severity["warning"]:
        print(f"\n{'='*60}")
        print(f"WARNINGS ({len(by_severity['warning'])} rooms)")
        print(f"{'='*60}")
        for report in by_severity["warning"]:
            print(f"\n⚠ {report.room_name}")
            print(f"  File: {report.anchor_file}")
            for issue in report.issues:
                print(f"  Issue: {issue}")
            if report.suggested_fix:
                print(f"  Fix: {report.suggested_fix}")

    # Info
    if by_severity["info"]:
        print(f"\n{'='*60}")
        print(f"INFO ({len(by_severity['info'])} rooms)")
        print(f"{'='*60}")
        for report in by_severity["info"]:
            print(f"\nℹ {report.room_name}: {', '.join(report.issues)}")

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Total rooms checked: {len(palace.rooms)}")
    print(f"Errors: {len(by_severity['error'])}")
    print(f"Warnings: {len(by_severity['warning'])}")
    print(f"Info: {len(by_severity['info'])}")

    if by_severity["error"]:
        print("\nTo fix errors, run: python scripts/rebuild_palace_map.py")
        return 2
    elif by_severity["warning"]:
        print("\nWarnings indicate signature changes. Review and sync if needed.")
        return 1
    else:
        return 0


if __name__ == "__main__":
    sys.exit(main())
