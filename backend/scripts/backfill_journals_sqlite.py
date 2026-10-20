"""
Copy journals that exist only in Chroma into the SQLite journals table (#56).

Until schema v60, journals were written to Chroma only and the SQLite table
held 10 seed rows. SQLite is now the source of truth and Chroma the search
index; this backfills the rows that were never written.

Reads Chroma (type=journal entries with journal_date metadata) and inserts a
SQLite row for each one that has none. It never edits or deletes anything in
Chroma, and never edits or deletes SQLite rows. Idempotent: a second run
inserts nothing.

A Chroma entry already counts as present when a row has its id in chroma_id,
or, for the pre-v60 rows that have no chroma_id, when a row has the same date
and identical content.

Dry run by default (prints counts, writes nothing). --apply migrates the
schema to v60 if needed, then inserts.

Run from backend/ (DATA_DIR picks the data directory):
    venv/bin/python scripts/backfill_journals_sqlite.py            # dry run
    venv/bin/python scripts/backfill_journals_sqlite.py --apply
"""
import argparse
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import CHROMA_PERSIST_DIR, COLLECTION_NAME, DATA_DIR  # noqa: E402
from database import get_db  # noqa: E402


def infer_journal_type(meta: dict) -> str:
    """journal_type for an entry; older entries don't carry one."""
    if meta.get("journal_type"):
        return meta["journal_type"]
    date = meta.get("journal_date") or ""
    if date.endswith("-research"):
        return "research"
    if date.endswith("-world"):
        return "world"
    # Only the daily journal was ever built from summaries or conversations
    # (same rule as journal_generation._is_daily_journal).
    if meta.get("summary_count") or meta.get("conversation_count"):
        return "daily"
    # Research-session and Grimoire reflections from before journal_type.
    return "untyped"


def chroma_journals(persist_dir=CHROMA_PERSIST_DIR, collection_name=COLLECTION_NAME):
    """[(id, document, metadata)] for every type=journal entry with a journal_date. Read-only."""
    import chromadb
    from chromadb.config import Settings

    client = chromadb.PersistentClient(path=str(persist_dir), settings=Settings(anonymized_telemetry=False))
    existing = {c if isinstance(c, str) else c.name for c in client.list_collections()}
    if collection_name not in existing:
        return []
    collection = client.get_collection(collection_name)
    result = collection.get(where={"type": "journal"}, include=["documents", "metadatas"])
    return [
        (doc_id, doc, meta or {})
        for doc_id, doc, meta in zip(result["ids"], result["documents"], result["metadatas"])
        if (meta or {}).get("journal_date") and doc
    ]


def _journal_columns(conn):
    return {row[1] for row in conn.execute("PRAGMA table_info(journals)").fetchall()}


def sqlite_state(daemon_id):
    """(row count, chroma_ids present, {(date, content)} of rows without chroma_id)."""
    with get_db() as conn:
        has_chroma_id = "chroma_id" in _journal_columns(conn)
        select = "SELECT date, content, chroma_id" if has_chroma_id else "SELECT date, content, NULL"
        rows = conn.execute(f"{select} FROM journals WHERE daemon_id = ?", (daemon_id,)).fetchall()
    chroma_ids = {r[2] for r in rows if r[2]}
    legacy = {(r[0], r[1]) for r in rows if not r[2]}
    return len(rows), chroma_ids, legacy


def plan(entries, chroma_ids, legacy):
    """Split Chroma entries into (missing, present_by_id, present_by_content, legacy rows matched)."""
    missing, by_id, by_content, matched = [], 0, 0, set()
    for doc_id, doc, meta in entries:
        key = (meta["journal_date"], doc)
        if doc_id in chroma_ids:
            by_id += 1
        elif key in legacy:
            by_content += 1
            matched.add(key)
        else:
            missing.append((doc_id, doc, meta))
    return missing, by_id, by_content, matched


def default_daemon_id():
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM daemons WHERE label = 'cass' ORDER BY created_at LIMIT 1"
        ).fetchone()
    if not row:
        raise SystemExit("No 'cass' daemon in this database; nothing to backfill into.")
    return row[0]


def run(apply: bool, persist_dir=CHROMA_PERSIST_DIR, collection_name=COLLECTION_NAME) -> dict:
    daemon_id = default_daemon_id()
    if apply:
        from database.migrations import init_database
        init_database()  # brings the journals table to v60 (adds chroma_id etc.)

    entries = chroma_journals(persist_dir, collection_name)
    before, chroma_ids, legacy = sqlite_state(daemon_id)
    missing, by_id, by_content, matched = plan(entries, chroma_ids, legacy)
    missing_types = Counter(infer_journal_type(meta) for _, _, meta in missing)

    inserted = 0
    if apply:
        from memory.journals import insert_journal_row
        for doc_id, doc, meta in missing:
            insert_journal_row(
                date=meta["journal_date"],
                content=doc,
                created_at=meta.get("timestamp") or datetime.now().isoformat(),
                journal_type=infer_journal_type(meta),
                chroma_id=doc_id,
                metadata=meta,
                daemon_id=daemon_id,
            )
            inserted += 1

    after = sqlite_state(daemon_id)[0]
    return {
        "chroma_journals": len(entries),
        "sqlite_rows_before": before,
        "present_by_chroma_id": by_id,
        "present_by_date_and_content": by_content,
        "pre_v60_rows_with_no_chroma_match": len(legacy - matched),
        "missing": len(missing),
        "missing_by_type": dict(missing_types),
        "inserted": inserted,
        "sqlite_rows_after": after,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("--apply", action="store_true", help="insert the missing rows (default: dry run)")
    args = parser.parse_args()

    print(f"DATA_DIR: {DATA_DIR}")
    print("Mode: APPLY" if args.apply else "Mode: dry run (nothing is written)")
    counts = run(apply=args.apply)
    for key, value in counts.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
