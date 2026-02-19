#!/usr/bin/env python3
"""
Backfill Research Notes to Wiki Pages

Week 3 migration script to create wiki pages for existing research notes.
This makes wiki pages the canonical storage for research findings.

Usage:
    cd backend && python scripts/backfill_research_to_wiki.py
"""
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from database import get_db, json_deserialize
from wiki.storage import WikiStorage, PageType
from wiki.maturity import SynthesisTrigger
from config import DATA_DIR


def backfill_research_to_wiki():
    """Create wiki pages for all existing research notes."""
    storage = WikiStorage(wiki_root=str(DATA_DIR / "wiki"), git_enabled=True)

    with get_db() as conn:
        cursor = conn.execute("""
            SELECT id, daemon_id, session_id, title, content,
                   sources_json, tags_json, wiki_page_name
            FROM research_notes
            ORDER BY created_at
        """)
        rows = cursor.fetchall()

    if not rows:
        print("No research notes found to backfill.")
        return

    print(f"Found {len(rows)} research notes to process...")

    created_count = 0
    skipped_count = 0
    error_count = 0

    for row in rows:
        note_id = row[0]
        daemon_id = row[1]
        session_id = row[2]
        title = row[3]
        content = row[4]
        sources = json_deserialize(row[5]) or []
        tags = json_deserialize(row[6]) or []
        existing_wiki = row[7]

        # Skip if already has wiki page
        if existing_wiki:
            print(f"  - {title[:50]:<50} SKIP (already linked to {existing_wiki})")
            skipped_count += 1
            continue

        try:
            # Generate wiki page name
            page_name = f"Research:{title}"

            # Build source links section
            source_links = ""
            if sources:
                source_links = "\n## Sources\n"
                for src in sources:
                    url = src.get("url", "")
                    src_title = src.get("title", url)
                    accessed = src.get("accessed_at", "")
                    source_links += f"- [{src_title}]({url})"
                    if accessed:
                        source_links += f" (accessed {accessed})"
                    source_links += "\n"

            tags_line = ""
            if tags:
                tags_line = f"tags: [{', '.join(tags)}]\n"

            # Build frontmatter
            frontmatter = f"""---
title: "{title}"
source: research_session
session_id: {session_id or 'standalone'}
note_id: {note_id}
{tags_line}---

"""
            wiki_content = frontmatter + content + source_links

            # Check if page already exists
            existing = storage.read(page_name)
            if existing:
                print(f"  - {title[:50]:<50} EXISTS (updating)")
                storage.update(name=page_name, content=wiki_content, commit=True)
            else:
                storage.create(
                    name=page_name,
                    content=wiki_content,
                    page_type=PageType.CONCEPT,
                    commit=True,
                    synthesis_trigger=SynthesisTrigger.INITIAL_CREATION,
                )
                print(f"  + {title[:50]:<50} CREATED")

            # Update the research_notes table with wiki page name
            with get_db() as conn:
                conn.execute(
                    "UPDATE research_notes SET wiki_page_name = ? WHERE id = ?",
                    (page_name, note_id)
                )
                conn.commit()

            created_count += 1

        except Exception as e:
            error_count += 1
            print(f"  X {title[:50]:<50} ERROR: {e}")

    print()
    print(f"Backfill complete:")
    print(f"  - Wiki pages created/updated: {created_count}")
    print(f"  - Skipped (already linked): {skipped_count}")
    if error_count:
        print(f"  - Errors: {error_count}")


if __name__ == "__main__":
    backfill_research_to_wiki()
