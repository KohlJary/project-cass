#!/usr/bin/env python3
"""
Seed the symbols table from existing dream insights.

Dreams extract recurring_symbols during integration, but these weren't
previously persisted to a dedicated symbol table. This script migrates
that data to enable symbol-based art generation and other features.
"""
import json
import sqlite3
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from symbols import get_symbol_manager


def seed_symbols_from_dreams(db_path: str, daemon_id: str = None) -> dict:
    """
    Extract symbols from dream integration_insights_json and store them.

    Returns stats about what was migrated.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get daemon_id from dreams if not provided
    if daemon_id is None:
        row = conn.execute("SELECT DISTINCT daemon_id FROM dreams LIMIT 1").fetchone()
        if row:
            daemon_id = row[0]
            print(f"Using daemon_id from dreams: {daemon_id}")
        else:
            # Fall back to first daemon
            row = conn.execute("SELECT id FROM daemons WHERE name = 'Cass' LIMIT 1").fetchone()
            if row:
                daemon_id = row[0]
                print(f"Using daemon_id from daemons table: {daemon_id}")
            else:
                raise ValueError("No daemon_id found")

    # Get all dreams with integration insights
    cursor = conn.execute("""
        SELECT id, integration_insights_json, created_at
        FROM dreams
        WHERE integration_insights_json IS NOT NULL
        ORDER BY created_at ASC
    """)
    # Fetch all rows and close connection to avoid locking
    rows = cursor.fetchall()
    conn.close()

    manager = get_symbol_manager(daemon_id)
    stats = {
        "dreams_processed": 0,
        "symbols_found": 0,
        "symbols_created": 0,
        "symbols_updated": 0,
        "errors": []
    }

    for row in rows:
        dream_id = row["id"]
        try:
            insights = json.loads(row["integration_insights_json"])
            symbols = insights.get("recurring_symbols", [])

            if not symbols:
                continue

            stats["dreams_processed"] += 1

            for sym_data in symbols:
                symbol_name = sym_data.get("symbol", "").strip()
                meaning = sym_data.get("meaning", "").strip()
                charge = sym_data.get("emotional_charge", "ambivalent")

                if not symbol_name or not meaning:
                    continue

                stats["symbols_found"] += 1

                # Check if symbol already exists
                existing = manager.get_by_name(symbol_name)

                if existing:
                    # Record another appearance
                    manager.record_appearance(
                        symbol_id=existing.id,
                        source_type="dream",
                        source_id=dream_id,
                        context=f"Dream insight: {meaning}",
                        meaning_in_context=meaning
                    )
                    stats["symbols_updated"] += 1
                    print(f"  Updated: {symbol_name} (appearance #{existing.appearance_count + 1})")
                else:
                    # Create new symbol
                    symbol = manager.add_symbol(
                        name=symbol_name,
                        meaning=meaning,
                        source_type="dream",
                        source_id=dream_id,
                        emotional_charge=charge,
                        description=f"First emerged in dream {dream_id}"
                    )
                    stats["symbols_created"] += 1
                    print(f"  Created: {symbol_name} [{charge}]")

        except Exception as e:
            stats["errors"].append(f"Dream {dream_id}: {e}")
            print(f"  Error processing dream {dream_id}: {e}")

    return stats


def main():
    db_path = Path(__file__).parent.parent.parent / "data" / "cass.db"

    if not db_path.exists():
        print(f"Database not found: {db_path}")
        sys.exit(1)

    print(f"Seeding symbols from dreams...")
    print(f"Database: {db_path}")
    print()

    stats = seed_symbols_from_dreams(str(db_path))

    print()
    print("=" * 50)
    print("Seed Summary:")
    print(f"  Dreams processed: {stats['dreams_processed']}")
    print(f"  Symbols found: {stats['symbols_found']}")
    print(f"  New symbols created: {stats['symbols_created']}")
    print(f"  Existing symbols updated: {stats['symbols_updated']}")

    if stats["errors"]:
        print(f"  Errors: {len(stats['errors'])}")
        for err in stats["errors"]:
            print(f"    - {err}")

    # Get daemon_id for summary
    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT DISTINCT daemon_id FROM dreams LIMIT 1").fetchone()
    daemon_id = row[0] if row else None
    conn.close()

    if not daemon_id:
        print("\nNo daemon_id found, skipping library summary")
        return

    # Show current symbol library
    print()
    print("Current Symbol Library:")
    print("-" * 50)

    from symbols import get_symbol_manager
    manager = get_symbol_manager(daemon_id)
    symbols = manager.list_symbols(limit=50)

    for sym in symbols:
        charge_icon = {
            "positive": "+",
            "negative": "-",
            "ambivalent": "~",
            "transformative": "*"
        }.get(sym.emotional_charge, "?")
        print(f"  [{charge_icon}] {sym.name}: {sym.current_meaning[:60]}...")


if __name__ == "__main__":
    main()
