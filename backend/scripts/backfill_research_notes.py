#!/usr/bin/env python3
"""
Backfill Research Notes to ChromaDB

One-time migration script to embed existing research notes into ChromaDB
for semantic retrieval during conversations.

Usage:
    cd backend && python scripts/backfill_research_notes.py
"""
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from database import get_db, json_deserialize
from memory import CassMemory


def backfill_research_notes():
    """Embed all existing research notes into ChromaDB."""
    memory = CassMemory()

    with get_db() as conn:
        cursor = conn.execute("""
            SELECT id, daemon_id, session_id, title, content,
                   sources_json, tags_json
            FROM research_notes
            ORDER BY created_at
        """)
        rows = cursor.fetchall()

    if not rows:
        print("No research notes found to backfill.")
        return

    print(f"Found {len(rows)} research notes to embed...")

    total_chunks = 0
    success_count = 0
    error_count = 0

    for row in rows:
        note_id = row[0]
        daemon_id = row[1]
        session_id = row[2]
        title = row[3]
        content = row[4]
        sources = json_deserialize(row[5]) or []
        tags = json_deserialize(row[6]) or []

        try:
            chunks = memory.embed_research_note(
                note_id=note_id,
                title=title,
                content=content,
                tags=tags,
                sources=sources,
                session_id=session_id,
                daemon_id=daemon_id
            )
            total_chunks += chunks
            success_count += 1
            print(f"  ✓ {title[:50]:<50} ({chunks} chunks)")
        except Exception as e:
            error_count += 1
            print(f"  ✗ {title[:50]:<50} ERROR: {e}")

    print()
    print(f"Backfill complete:")
    print(f"  - Notes embedded: {success_count}")
    print(f"  - Total chunks: {total_chunks}")
    if error_count:
        print(f"  - Errors: {error_count}")


if __name__ == "__main__":
    backfill_research_notes()
