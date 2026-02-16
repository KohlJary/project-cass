#!/usr/bin/env python3
"""
Migrate images from flat structure to organized folders.

Old structure: data/images/{uuid}.png
New structure: data/images/{category}/{subcategory}/{year}/{month}/{uuid}.png

This script:
1. Reads the generated_images table to get metadata
2. Determines category from purpose field
3. Moves files to organized directories
4. Updates database paths
"""

import json
import os
import sys
import shutil
from datetime import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import get_db


def get_category_from_purpose(purpose: str) -> str:
    """Map purpose to category."""
    mapping = {
        "autonomous": "autonomous",
        "article": "articles",
        "relational": "relational",
        "dream": "dreams",
        "art-study": "art-study",
    }
    return mapping.get(purpose, "autonomous")


def migrate_images(dry_run: bool = True):
    """
    Migrate images to organized directory structure.

    Args:
        dry_run: If True, only print what would be done
    """
    images_dir = Path(__file__).parent.parent.parent / "data" / "images"

    if not images_dir.exists():
        print(f"Images directory not found: {images_dir}")
        return

    # Get all image records from database
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT id, image_path, purpose, created_at
            FROM generated_images
            WHERE image_path IS NOT NULL
        """)
        records = cursor.fetchall()

    print(f"Found {len(records)} image records in database")

    moved = 0
    skipped = 0
    errors = 0
    already_organized = 0

    for record in records:
        image_id, old_path, purpose, created_at = record

        if not old_path:
            skipped += 1
            continue

        old_path = Path(old_path)

        # Check if already organized (has year/month in path)
        path_parts = old_path.parts
        if any(part.isdigit() and len(part) == 4 for part in path_parts):
            already_organized += 1
            continue

        # Check if file exists
        if not old_path.exists():
            print(f"  File not found: {old_path}")
            skipped += 1
            continue

        # Determine new path
        category = get_category_from_purpose(purpose or "autonomous")

        # Parse created_at for year/month
        try:
            if created_at:
                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            else:
                dt = datetime.fromtimestamp(old_path.stat().st_mtime)
        except Exception:
            dt = datetime.now()

        year = str(dt.year)
        month = f"{dt.month:02d}"

        # Build new path
        new_dir = images_dir / category / year / month
        new_path = new_dir / old_path.name

        if dry_run:
            print(f"  Would move: {old_path.name}")
            print(f"    From: {old_path.parent}")
            print(f"    To:   {new_dir}")
        else:
            try:
                new_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old_path), str(new_path))

                # Update database
                with get_db() as conn:
                    conn.execute(
                        "UPDATE generated_images SET image_path = ? WHERE id = ?",
                        (str(new_path), image_id)
                    )

                moved += 1
            except Exception as e:
                print(f"  Error moving {old_path.name}: {e}")
                errors += 1

    # Also handle art study images (creative_processes table)
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT cp.id, cp.image_id, cp.studied_artists, gi.image_path, gi.created_at
            FROM creative_processes cp
            LEFT JOIN generated_images gi ON cp.image_id = gi.id
            WHERE gi.image_path IS NOT NULL
        """)
        art_records = cursor.fetchall()

    print(f"\nFound {len(art_records)} art study records")

    # Get artist names for subcategory
    artist_names = {}
    with get_db() as conn:
        cursor = conn.execute("SELECT id, name FROM artists")
        for row in cursor.fetchall():
            artist_names[row[0]] = row[1]

    for record in art_records:
        process_id, image_id, studied_artists_json, old_path, created_at = record

        if not old_path:
            continue

        old_path = Path(old_path)

        # Skip if already organized
        if "art-study" in str(old_path):
            already_organized += 1
            continue

        if not old_path.exists():
            continue

        # Determine subcategory from studied_artists (JSON array of artist IDs)
        subcategory = "house-style"
        if studied_artists_json:
            try:
                studied_artists = json.loads(studied_artists_json)
                if studied_artists and len(studied_artists) > 0:
                    artist_id = studied_artists[0]
                    if artist_id in artist_names:
                        artist_name = artist_names[artist_id]
                        artist_slug = "".join(c if c.isalnum() or c in "-_ " else "" for c in artist_name).replace(" ", "-").lower()
                        subcategory = f"artists/{artist_slug}"
            except (json.JSONDecodeError, TypeError):
                pass

        # Parse date
        try:
            if created_at:
                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            else:
                dt = datetime.fromtimestamp(old_path.stat().st_mtime)
        except Exception:
            dt = datetime.now()

        year = str(dt.year)
        month = f"{dt.month:02d}"

        new_dir = images_dir / "art-study" / subcategory / year / month
        new_path = new_dir / old_path.name

        if dry_run:
            print(f"  Would move (art): {old_path.name}")
            print(f"    To: {new_dir}")
        else:
            try:
                new_dir.mkdir(parents=True, exist_ok=True)
                if old_path.exists():  # Check again in case already moved
                    shutil.move(str(old_path), str(new_path))

                    # Update database
                    with get_db() as conn:
                        conn.execute(
                            "UPDATE generated_images SET image_path = ? WHERE id = ?",
                            (str(new_path), image_id)
                        )

                    moved += 1
            except Exception as e:
                print(f"  Error: {e}")
                errors += 1

    print(f"\n{'DRY RUN - ' if dry_run else ''}Summary:")
    print(f"  Moved: {moved}")
    print(f"  Already organized: {already_organized}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors: {errors}")

    if dry_run:
        print("\nRun with --execute to actually move files")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Migrate images to organized folders")
    parser.add_argument("--execute", action="store_true", help="Actually move files (default is dry run)")
    args = parser.parse_args()

    migrate_images(dry_run=not args.execute)
