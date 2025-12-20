"""
Wiki Action Handlers - Research note management.

Standalone actions for wiki/research note operations.
"""

import logging
from datetime import datetime
from typing import Any, Dict

from . import ActionResult

logger = logging.getLogger(__name__)


async def create_note_action(context: Dict[str, Any]) -> ActionResult:
    """
    Create a new research note in the wiki.

    Context params:
    - title: str - Note title
    - content: str - Note content (markdown)
    - category: str (optional) - Note category
    - tags: list (optional) - Tags for the note
    - session_id: str (optional) - Associated session ID
    """
    managers = context.get("managers", {})

    title = context.get("title")
    content = context.get("content")
    category = context.get("category", "research")
    tags = context.get("tags", [])
    session_id = context.get("session_id")

    if not title or not content:
        return ActionResult(
            success=False,
            message="title and content required"
        )

    try:
        # Try to use wiki manager if available
        wiki_manager = managers.get("wiki_manager")

        if wiki_manager:
            note_id = await wiki_manager.create_note(
                title=title,
                content=content,
                category=category,
                tags=tags,
                session_id=session_id
            )
            return ActionResult(
                success=True,
                message=f"Created note: {title}",
                data={
                    "note_id": note_id,
                    "title": title,
                    "category": category
                }
            )

        # Fallback: write to filesystem
        from pathlib import Path
        import re

        data_dir = managers.get("data_dir", Path("data"))
        notes_dir = data_dir / "wiki" / "notes"
        notes_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename from title
        safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{safe_title}.md"

        # Build note content
        frontmatter = f"""---
title: {title}
category: {category}
tags: {tags}
created: {datetime.now().isoformat()}
session_id: {session_id or 'standalone'}
---

"""
        full_content = frontmatter + content

        note_path = notes_dir / filename
        note_path.write_text(full_content)

        return ActionResult(
            success=True,
            message=f"Created note: {title}",
            data={
                "path": str(note_path),
                "title": title,
                "category": category
            }
        )

    except Exception as e:
        logger.error(f"Create note failed: {e}")
        return ActionResult(
            success=False,
            message=f"Create note failed: {e}"
        )


async def update_note_action(context: Dict[str, Any]) -> ActionResult:
    """
    Update an existing research note.

    Context params:
    - note_id: str - Note ID or path
    - content: str (optional) - New content to append or replace
    - append: bool (optional) - Append to existing content (default True)
    - tags: list (optional) - Additional tags to add
    """
    managers = context.get("managers", {})

    note_id = context.get("note_id")
    content = context.get("content")
    append = context.get("append", True)
    new_tags = context.get("tags", [])

    if not note_id:
        return ActionResult(
            success=False,
            message="note_id required"
        )

    try:
        wiki_manager = managers.get("wiki_manager")

        if wiki_manager:
            result = await wiki_manager.update_note(
                note_id=note_id,
                content=content,
                append=append,
                tags=new_tags
            )
            return ActionResult(
                success=True,
                message=f"Updated note: {note_id}",
                data={"note_id": note_id, "updated": True}
            )

        # Fallback: filesystem update
        from pathlib import Path

        note_path = Path(note_id)
        if not note_path.exists():
            return ActionResult(
                success=False,
                message=f"Note not found: {note_id}"
            )

        existing = note_path.read_text()

        if content:
            if append:
                new_content = existing + "\n\n" + content
            else:
                # Try to preserve frontmatter
                if existing.startswith("---"):
                    end_idx = existing.find("---", 3)
                    if end_idx > 0:
                        frontmatter = existing[:end_idx + 3]
                        new_content = frontmatter + "\n\n" + content
                    else:
                        new_content = content
                else:
                    new_content = content

            note_path.write_text(new_content)

        return ActionResult(
            success=True,
            message=f"Updated note: {note_id}",
            data={"path": str(note_path), "updated": True}
        )

    except Exception as e:
        logger.error(f"Update note failed: {e}")
        return ActionResult(
            success=False,
            message=f"Update note failed: {e}"
        )
