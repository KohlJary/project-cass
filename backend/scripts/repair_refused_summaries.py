"""
Rebuild working summaries that are writer refusals (see memory/voice_guard.py).

Dry run by default: lists the conversations whose stored working summary is a
refusal. With --apply, rebuilds each from its stored memory chunks (one
summarizer call per conversation), checks the result is not itself a
refusal, saves the old text to a JSON backup next to the database, and only
then replaces it.

Run from backend/:
    venv/bin/python scripts/repair_refused_summaries.py            # dry run
    venv/bin/python scripts/repair_refused_summaries.py --apply
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import ANTHROPIC_API_KEY, DATA_DIR  # noqa: E402
from conversations import ConversationManager  # noqa: E402
from database import get_db  # noqa: E402
from memory import CassMemory  # noqa: E402
from memory.voice_guard import looks_like_refusal  # noqa: E402


def refused_conversations():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, title, working_summary FROM conversations "
            "WHERE working_summary IS NOT NULL AND working_summary != ''"
        ).fetchall()
    return [(r["id"], r["title"], r["working_summary"]) for r in rows
            if looks_like_refusal(r["working_summary"])], len(rows)


async def rebuild(memory, conv_id, title):
    # existing_summary=None forces the full rebuild from stored chunks.
    return await memory.generate_working_summary(
        conversation_id=conv_id,
        conversation_title=title or "Conversation",
        new_chunk=None,
        existing_summary=None,
        anthropic_api_key=ANTHROPIC_API_KEY,
    )


async def main(apply: bool):
    found, total = refused_conversations()
    print(f"{len(found)} of {total} stored working summaries are refusals")
    for conv_id, title, text in found:
        print(f"- {conv_id} ({title!r}): {looks_like_refusal(text)!r}")
    if not apply or not found:
        return

    memory = CassMemory()
    manager = ConversationManager()
    backup = Path(DATA_DIR) / f"refused_working_summaries.{datetime.now():%Y%m%dT%H%M%S}.json"
    saved = []
    for conv_id, title, old in found:
        chunks = memory.get_summaries_for_conversation(conv_id)
        new = await rebuild(memory, conv_id, title)
        if not new or looks_like_refusal(new):
            print(f"  {conv_id}: rebuild failed or refused again; left as is")
            continue
        saved.append({"conversation_id": conv_id, "title": title, "old_working_summary": old,
                      "rebuilt_from_chunks": len(chunks), "replaced_at": datetime.now().isoformat()})
        backup.write_text(json.dumps(saved, indent=2))
        manager.update_working_summary(conv_id, new)
        print(f"  {conv_id}: rebuilt from {len(chunks)} chunks ({len(new)} chars); old text in {backup}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--apply", action="store_true", help="rebuild and replace (default: dry run)")
    asyncio.run(main(parser.parse_args().apply))
