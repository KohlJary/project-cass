"""
Daemon Export/Import System

Exports and imports a complete daemon's data from/to SQLite database.
Supports selective export of specific daemons for sharing, backup, or seeding new instances.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zipfile import ZipFile
import tempfile
import shutil

from database import get_db, json_serialize, json_deserialize

logger = logging.getLogger("cass-vessel")


# Tables that contain daemon-specific data (with daemon_id column)
DAEMON_TABLES = [
    # Core identity
    "daemon_profiles",
    "growth_edges",
    "opinions",
    "cognitive_snapshots",
    "milestones",
    "development_logs",
    "self_observations",
    "journals",

    # Conversations and messages
    "conversations",
    "messages",

    # Projects
    "projects",
    "project_files",
    "project_documents",

    # User observations (daemon's observations about users)
    "user_observations",
    "user_growth_edges",

    # Dreams and reflections
    "dreams",
    "solo_reflections",

    # Research
    "research_sessions",
    "research_notes",
    "research_tasks",
    "research_task_history",
    "research_proposals",

    # Wiki
    "wiki_pages",

    # Goals
    "goals",

    # Operational
    "roadmap_items",
    "calendar_events",
    "tasks",
    "rhythm_phases",
    "rhythm_records",
    "rhythm_daily_summaries",

    # Metrics
    "token_usage",
    "token_usage_records",
    "github_metrics",
    "research_schedules",
]

# Tables that need special handling (foreign keys to other daemon tables)
DEPENDENT_TABLES = {
    "messages": "conversations",  # messages.conversation_id -> conversations.id
    "project_files": "projects",  # project_files.project_id -> projects.id
    "project_documents": "projects",
    "research_notes": "research_sessions",  # research_notes.session_id -> research_sessions.id
    "roadmap_links": "roadmap_items",  # both source_id and target_id -> roadmap_items.id
}


def export_daemon(daemon_id: str, output_path: Optional[Path] = None, include_users: bool = False) -> Dict[str, Any]:
    """
    Export a complete daemon's data to a JSON file or ZIP archive.

    Args:
        daemon_id: The daemon ID to export
        output_path: Optional path for output file. If ends with .zip, creates archive.
                    If None, returns data dict directly.
        include_users: Whether to include user profiles (default False for privacy)

    Returns:
        Dict with export metadata and optionally the file path
    """
    export_data = {
        "export_version": "2.0",
        "export_type": "daemon",
        "exported_at": datetime.now().isoformat(),
        "daemon_id": daemon_id,
        "tables": {},
        "stats": {},
    }

    with get_db() as conn:
        # Get daemon info
        cursor = conn.execute(
            "SELECT id, name, created_at, kernel_version, status FROM daemons WHERE id = ?",
            (daemon_id,)
        )
        daemon_row = cursor.fetchone()
        if not daemon_row:
            raise ValueError(f"Daemon {daemon_id} not found")

        export_data["daemon"] = {
            "id": daemon_row[0],
            "name": daemon_row[1],
            "created_at": daemon_row[2],
            "kernel_version": daemon_row[3],
            "status": daemon_row[4],
        }

        # Export each table
        total_rows = 0
        for table in DAEMON_TABLES:
            rows = _export_table(conn, table, daemon_id)
            if rows:
                export_data["tables"][table] = rows
                export_data["stats"][table] = len(rows)
                total_rows += len(rows)
                logger.info(f"Exported {len(rows)} rows from {table}")

        # Export roadmap_links (special case - no daemon_id, but linked to roadmap_items)
        roadmap_item_ids = [r["id"] for r in export_data["tables"].get("roadmap_items", [])]
        if roadmap_item_ids:
            links = _export_roadmap_links(conn, roadmap_item_ids)
            if links:
                export_data["tables"]["roadmap_links"] = links
                export_data["stats"]["roadmap_links"] = len(links)
                total_rows += len(links)

        # Optionally include users
        if include_users:
            cursor = conn.execute("SELECT * FROM users")
            columns = [desc[0] for desc in cursor.description]
            users = [dict(zip(columns, row)) for row in cursor.fetchall()]
            export_data["tables"]["users"] = users
            export_data["stats"]["users"] = len(users)
            total_rows += len(users)

        export_data["stats"]["total_rows"] = total_rows

    # Write output if path specified
    if output_path:
        output_path = Path(output_path)

        if output_path.suffix == ".zip":
            # Create ZIP archive with JSON + wiki markdown
            _create_export_archive(export_data, output_path, daemon_id)
        else:
            # Write JSON directly
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                json.dump(export_data, f, indent=2, default=str)

        return {
            "success": True,
            "daemon_name": export_data["daemon"]["name"],
            "output_path": str(output_path),
            "total_rows": total_rows,
            "stats": export_data["stats"],
        }

    return export_data


def _export_table(conn, table: str, daemon_id: str) -> List[Dict]:
    """Export all rows from a table for a specific daemon."""
    try:
        # Check if table exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,)
        )
        if not cursor.fetchone():
            return []

        # Get column names
        cursor = conn.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in cursor.fetchall()]

        # Check if table has daemon_id column
        if "daemon_id" in columns:
            cursor = conn.execute(f"SELECT * FROM {table} WHERE daemon_id = ?", (daemon_id,))
        else:
            # Table doesn't have daemon_id (shouldn't happen for DAEMON_TABLES)
            return []

        rows = []
        for row in cursor.fetchall():
            row_dict = dict(zip(columns, row))
            rows.append(row_dict)

        return rows
    except Exception as e:
        logger.warning(f"Error exporting table {table}: {e}")
        return []


def _export_roadmap_links(conn, roadmap_item_ids: List[str]) -> List[Dict]:
    """Export roadmap links for the given roadmap items."""
    if not roadmap_item_ids:
        return []

    placeholders = ",".join("?" * len(roadmap_item_ids))
    cursor = conn.execute(f"""
        SELECT id, source_id, target_id, link_type
        FROM roadmap_links
        WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders})
    """, roadmap_item_ids + roadmap_item_ids)

    columns = ["id", "source_id", "target_id", "link_type"]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _create_export_archive(export_data: Dict, output_path: Path, daemon_id: str):
    """Create a ZIP archive with JSON data and wiki markdown files."""
    tmpdir = tempfile.mkdtemp()

    try:
        # Write main JSON
        json_path = Path(tmpdir) / "daemon_data.json"
        with open(json_path, 'w') as f:
            json.dump(export_data, f, indent=2, default=str)

        # Create wiki markdown files
        wiki_dir = Path(tmpdir) / "wiki"
        wiki_pages = export_data["tables"].get("wiki_pages", [])
        if wiki_pages:
            wiki_dir.mkdir()
            for page in wiki_pages:
                safe_name = page["id"].replace("/", "_").replace("\\", "_")
                page_path = wiki_dir / f"{safe_name}.md"

                frontmatter = f"""---
title: {page.get('title', page['id'])}
category: {page.get('category', 'unknown')}
created: {page.get('created_at', 'unknown')}
modified: {page.get('updated_at', 'unknown')}
---

"""
                page_path.write_text(frontmatter + (page.get('content') or ''))

        # Create README
        readme_path = Path(tmpdir) / "README.md"
        daemon_name = export_data["daemon"]["name"]
        stats = export_data["stats"]

        readme = f"""# {daemon_name} Export

Exported: {export_data['exported_at']}
Export Version: {export_data['export_version']}

## Contents

- `daemon_data.json` - Complete daemon data in JSON format
- `wiki/` - Wiki pages as markdown files (if any)

## Statistics

| Table | Rows |
|-------|------|
"""
        for table, count in sorted(stats.items()):
            if table != "total_rows":
                readme += f"| {table} | {count} |\n"

        readme += f"\n**Total Rows:** {stats.get('total_rows', 0)}\n"
        readme += f"\n## Import\n\nTo import this daemon into a new instance:\n\n"
        readme += f"```bash\npython -c \"from daemon_export import import_daemon; import_daemon('{output_path.name}')\"\n```\n"

        readme_path.write_text(readme)

        # Create ZIP
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(output_path, 'w') as zf:
            zf.write(json_path, "daemon_data.json")
            zf.write(readme_path, "README.md")
            if wiki_dir.exists():
                for md_file in wiki_dir.glob("*.md"):
                    zf.write(md_file, f"wiki/{md_file.name}")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def import_daemon(
    input_path: Path,
    new_daemon_name: Optional[str] = None,
    merge_existing: bool = False,
    skip_embeddings: bool = False
) -> Dict[str, Any]:
    """
    Import a daemon from an export file.

    Args:
        input_path: Path to JSON file or ZIP archive
        new_daemon_name: Optional new name for the daemon (creates new daemon_id)
        merge_existing: If True, merge into existing daemon instead of creating new
        skip_embeddings: If True, skip ChromaDB embedding regeneration

    Returns:
        Dict with import results
    """
    input_path = Path(input_path)

    # Load export data
    if input_path.suffix == ".zip":
        with ZipFile(input_path, 'r') as zf:
            with zf.open("daemon_data.json") as f:
                export_data = json.load(f)
    else:
        with open(input_path, 'r') as f:
            export_data = json.load(f)

    if export_data.get("export_type") != "daemon":
        raise ValueError("Not a daemon export file")

    original_daemon = export_data["daemon"]
    tables_data = export_data["tables"]

    with get_db() as conn:
        # Determine target daemon_id
        if new_daemon_name:
            # Create new daemon with new ID
            import uuid
            new_daemon_id = str(uuid.uuid4())
            conn.execute("""
                INSERT INTO daemons (id, name, created_at, kernel_version, status)
                VALUES (?, ?, ?, ?, ?)
            """, (
                new_daemon_id,
                new_daemon_name,
                datetime.now().isoformat(),
                original_daemon.get("kernel_version", "temple-codex-1.0"),
                "active"
            ))
            logger.info(f"Created new daemon '{new_daemon_name}' with ID {new_daemon_id}")
            target_daemon_id = new_daemon_id
        elif merge_existing:
            # Use original daemon_id (must exist)
            cursor = conn.execute(
                "SELECT id FROM daemons WHERE id = ?",
                (original_daemon["id"],)
            )
            if not cursor.fetchone():
                raise ValueError(f"Daemon {original_daemon['id']} not found for merge")
            target_daemon_id = original_daemon["id"]
        else:
            # Create daemon with original ID if it doesn't exist
            cursor = conn.execute(
                "SELECT id FROM daemons WHERE id = ?",
                (original_daemon["id"],)
            )
            if cursor.fetchone():
                raise ValueError(
                    f"Daemon {original_daemon['id']} already exists. "
                    "Use new_daemon_name to create a copy or merge_existing=True to merge."
                )

            conn.execute("""
                INSERT INTO daemons (id, name, created_at, kernel_version, status)
                VALUES (?, ?, ?, ?, ?)
            """, (
                original_daemon["id"],
                original_daemon["name"],
                original_daemon["created_at"],
                original_daemon.get("kernel_version"),
                original_daemon.get("status", "active")
            ))
            target_daemon_id = original_daemon["id"]

        # Import tables in dependency order
        imported_counts = {}
        old_to_new_ids = {}  # Track ID mappings if we're creating new daemon

        # Import in order (independent tables first)
        import_order = [
            # Core identity (no dependencies)
            "daemon_profiles",
            "growth_edges",
            "opinions",
            "cognitive_snapshots",
            "milestones",
            "development_logs",
            "self_observations",
            "journals",

            # Projects (needed before project_files/documents)
            "projects",
            "project_files",
            "project_documents",

            # User observations
            "user_observations",
            "user_growth_edges",

            # Dreams and reflections
            "dreams",
            "solo_reflections",

            # Research
            "research_sessions",
            "research_notes",
            "research_tasks",
            "research_task_history",
            "research_proposals",

            # Wiki
            "wiki_pages",

            # Goals
            "goals",

            # Conversations (needed before messages)
            "conversations",
            "messages",

            # Operational
            "roadmap_items",
            "calendar_events",
            "tasks",
            "rhythm_phases",
            "rhythm_records",
            "rhythm_daily_summaries",

            # Metrics
            "token_usage",
            "token_usage_records",
            "github_metrics",
            "research_schedules",
        ]

        for table in import_order:
            rows = tables_data.get(table, [])
            if not rows:
                continue

            count = _import_table(conn, table, rows, target_daemon_id, original_daemon["id"])
            imported_counts[table] = count
            logger.info(f"Imported {count} rows into {table}")

        # Import roadmap_links
        links = tables_data.get("roadmap_links", [])
        if links:
            count = _import_roadmap_links(conn, links)
            imported_counts["roadmap_links"] = count

        # Import users if present
        users = tables_data.get("users", [])
        if users:
            count = _import_users(conn, users)
            imported_counts["users"] = count

        conn.commit()

    # Regenerate ChromaDB embeddings from imported data
    embedding_counts = {}
    if not skip_embeddings:
        try:
            embedding_counts = regenerate_embeddings(target_daemon_id, tables_data)
        except Exception as e:
            logger.error(f"Embedding regeneration failed: {e}")
            logger.info("Import succeeded but embeddings not regenerated. "
                       "Run regenerate_embeddings() manually or restart server.")

    return {
        "success": True,
        "daemon_id": target_daemon_id,
        "daemon_name": new_daemon_name or original_daemon["name"],
        "imported_counts": imported_counts,
        "total_rows": sum(imported_counts.values()),
        "embedding_counts": embedding_counts,
    }


def _import_table(conn, table: str, rows: List[Dict], target_daemon_id: str, original_daemon_id: str) -> int:
    """Import rows into a table, updating daemon_id as needed."""
    if not rows:
        return 0

    # Check if table exists
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    )
    if not cursor.fetchone():
        logger.warning(f"Table {table} does not exist, skipping")
        return 0

    # Get column info
    cursor = conn.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]

    imported = 0
    for row in rows:
        # Update daemon_id if needed
        if "daemon_id" in row:
            row["daemon_id"] = target_daemon_id

        # Filter to only columns that exist in table
        filtered_row = {k: v for k, v in row.items() if k in columns}

        if not filtered_row:
            continue

        cols = list(filtered_row.keys())
        placeholders = ",".join("?" * len(cols))
        col_names = ",".join(cols)

        try:
            conn.execute(
                f"INSERT OR REPLACE INTO {table} ({col_names}) VALUES ({placeholders})",
                list(filtered_row.values())
            )
            imported += 1
        except Exception as e:
            logger.warning(f"Error importing row into {table}: {e}")

    return imported


def _import_roadmap_links(conn, links: List[Dict]) -> int:
    """Import roadmap links."""
    imported = 0
    for link in links:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO roadmap_links (source_id, target_id, link_type)
                VALUES (?, ?, ?)
            """, (link["source_id"], link["target_id"], link["link_type"]))
            imported += 1
        except Exception as e:
            logger.warning(f"Error importing roadmap link: {e}")
    return imported


def _import_users(conn, users: List[Dict]) -> int:
    """Import users (without overwriting existing)."""
    imported = 0
    for user in users:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO users (
                    id, display_name, relationship, background_json,
                    communication_json, preferences_json, password_hash,
                    is_admin, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user["id"],
                user.get("display_name"),
                user.get("relationship"),
                user.get("background_json"),
                user.get("communication_json"),
                user.get("preferences_json"),
                user.get("password_hash"),
                user.get("is_admin", 0),
                user.get("created_at"),
                user.get("updated_at"),
            ))
            imported += 1
        except Exception as e:
            logger.warning(f"Error importing user: {e}")
    return imported


def regenerate_embeddings(daemon_id: str, tables_data: Dict[str, List[Dict]]) -> Dict[str, int]:
    """
    Regenerate ChromaDB embeddings from imported SQLite data.

    This is called after import to rebuild the semantic search index.
    Embeddings are model-specific, so we regenerate rather than export/import them.

    Args:
        daemon_id: The daemon ID to regenerate embeddings for
        tables_data: The imported table data (to access content without re-querying)

    Returns:
        Dict with counts of embedded items by type
    """
    from memory import CassMemory, initialize_attractor_basins
    import asyncio

    logger.info(f"Regenerating ChromaDB embeddings for daemon {daemon_id[:8]}...")

    memory = CassMemory()
    counts = {}

    # 1. Initialize attractor basins (core cognitive markers)
    initialize_attractor_basins(memory)
    counts["attractor_basins"] = 5

    # 2. Embed wiki pages
    wiki_pages = tables_data.get("wiki_pages", [])
    embedded_wiki = 0
    for page in wiki_pages:
        try:
            content = page.get("content", "")
            if content:
                memory.embed_wiki_page(
                    page_name=page["id"],
                    title=page.get("title", page["id"]),
                    content=content,
                    category=page.get("category", "unknown"),
                    timestamp=page.get("updated_at", page.get("created_at", ""))
                )
                embedded_wiki += 1
        except Exception as e:
            logger.warning(f"Failed to embed wiki page {page.get('id')}: {e}")
    counts["wiki_pages"] = embedded_wiki
    logger.info(f"  Embedded {embedded_wiki} wiki pages")

    # 3. Embed journals
    journals = tables_data.get("journals", [])
    embedded_journals = 0
    for journal in journals:
        try:
            content = journal.get("content", "")
            if content:
                # Journals are embedded via store_journal_entry but we need sync version
                # Use the core collection directly
                entry_id = memory._generate_id(content, journal.get("date", ""))
                memory.collection.add(
                    documents=[content],
                    metadatas=[{
                        "type": "journal",
                        "date": journal.get("date", ""),
                        "daemon_id": daemon_id,
                        "timestamp": journal.get("created_at", ""),
                    }],
                    ids=[entry_id]
                )
                embedded_journals += 1
        except Exception as e:
            logger.warning(f"Failed to embed journal {journal.get('date')}: {e}")
    counts["journals"] = embedded_journals
    logger.info(f"  Embedded {embedded_journals} journals")

    # 4. Embed self observations
    self_obs = tables_data.get("self_observations", [])
    embedded_self_obs = 0
    for obs in self_obs:
        try:
            observation = obs.get("observation", "")
            if observation:
                memory.embed_self_observation(
                    observation_id=obs.get("id", ""),
                    category=obs.get("category", "general"),
                    observation=observation,
                    confidence=obs.get("confidence", 0.7),
                    timestamp=obs.get("created_at", "")
                )
                embedded_self_obs += 1
        except Exception as e:
            logger.warning(f"Failed to embed self observation: {e}")
    counts["self_observations"] = embedded_self_obs
    logger.info(f"  Embedded {embedded_self_obs} self observations")

    # 5. Embed conversations (as summaries/gists - full messages would be too large)
    # We embed conversation summaries if available, not individual messages
    conversations = tables_data.get("conversations", [])
    embedded_convs = 0
    for conv in conversations:
        try:
            summary = conv.get("working_summary", "")
            if summary:
                entry_id = memory._generate_id(summary, conv.get("created_at", ""))
                memory.collection.add(
                    documents=[summary],
                    metadatas=[{
                        "type": "summary",
                        "conversation_id": conv.get("id", ""),
                        "daemon_id": daemon_id,
                        "timestamp": conv.get("updated_at", conv.get("created_at", "")),
                    }],
                    ids=[entry_id]
                )
                embedded_convs += 1
        except Exception as e:
            logger.warning(f"Failed to embed conversation summary: {e}")
    counts["conversation_summaries"] = embedded_convs
    logger.info(f"  Embedded {embedded_convs} conversation summaries")

    # 6. Embed user observations
    user_obs = tables_data.get("user_observations", [])
    embedded_user_obs = 0
    for obs in user_obs:
        try:
            content_json = obs.get("content_json", "{}")
            if isinstance(content_json, str):
                content = json.loads(content_json) if content_json else {}
            else:
                content = content_json or {}

            observation_text = content.get("observation", content.get("content", str(content)))
            if observation_text:
                memory.embed_user_observation(
                    user_id=obs.get("user_id", ""),
                    observation_id=obs.get("id", ""),
                    observation_type=obs.get("observation_type", "identity"),
                    content=observation_text,
                    confidence=obs.get("confidence", 0.7),
                    timestamp=obs.get("created_at", "")
                )
                embedded_user_obs += 1
        except Exception as e:
            logger.warning(f"Failed to embed user observation: {e}")
    counts["user_observations"] = embedded_user_obs
    logger.info(f"  Embedded {embedded_user_obs} user observations")

    # 7. Embed dreams (key exchanges for memory)
    dreams = tables_data.get("dreams", [])
    embedded_dreams = 0
    for dream in dreams:
        try:
            exchanges_json = dream.get("exchanges_json", "[]")
            if isinstance(exchanges_json, str):
                exchanges = json.loads(exchanges_json) if exchanges_json else []
            else:
                exchanges = exchanges_json or []

            # Combine exchanges into searchable content
            if exchanges:
                dream_content = "\n".join([
                    f"{ex.get('role', 'unknown')}: {ex.get('content', '')}"
                    for ex in exchanges[:10]  # Limit to first 10 exchanges
                ])
                entry_id = memory._generate_id(dream_content, dream.get("created_at", ""))
                memory.collection.add(
                    documents=[dream_content],
                    metadatas=[{
                        "type": "dream",
                        "date": dream.get("date", ""),
                        "daemon_id": daemon_id,
                        "timestamp": dream.get("created_at", ""),
                    }],
                    ids=[entry_id]
                )
                embedded_dreams += 1
        except Exception as e:
            logger.warning(f"Failed to embed dream: {e}")
    counts["dreams"] = embedded_dreams
    logger.info(f"  Embedded {embedded_dreams} dreams")

    total = sum(counts.values())
    logger.info(f"Embedding regeneration complete: {total} items embedded")

    return counts


def list_daemons() -> List[Dict[str, Any]]:
    """List all daemons in the database."""
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT id, name, created_at, kernel_version, status
            FROM daemons
            ORDER BY created_at DESC
        """)

        daemons = []
        for row in cursor.fetchall():
            daemons.append({
                "id": row[0],
                "name": row[1],
                "created_at": row[2],
                "kernel_version": row[3],
                "status": row[4],
            })

        return daemons


# CLI interface
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python daemon_export.py list                    - List all daemons")
        print("  python daemon_export.py export <daemon_id> [output_path]")
        print("  python daemon_export.py import <input_path> [new_name] [--skip-embeddings]")
        print("")
        print("Options:")
        print("  --skip-embeddings   Skip ChromaDB embedding regeneration during import")
        sys.exit(1)

    command = sys.argv[1]

    if command == "list":
        daemons = list_daemons()
        print(f"\nFound {len(daemons)} daemon(s):\n")
        for d in daemons:
            print(f"  {d['name']} ({d['id'][:8]}...)")
            print(f"    Created: {d['created_at']}")
            print(f"    Kernel: {d['kernel_version']}")
            print(f"    Status: {d['status']}")
            print()

    elif command == "export":
        if len(sys.argv) < 3:
            print("Error: daemon_id required")
            sys.exit(1)

        daemon_id = sys.argv[2]
        output_path = sys.argv[3] if len(sys.argv) > 3 else f"exports/{daemon_id[:8]}_export.zip"

        result = export_daemon(daemon_id, Path(output_path))
        print(f"\nExport complete!")
        print(f"  Daemon: {result['daemon_name']}")
        print(f"  Output: {result['output_path']}")
        print(f"  Total rows: {result['total_rows']}")

    elif command == "import":
        if len(sys.argv) < 3:
            print("Error: input_path required")
            sys.exit(1)

        input_path = sys.argv[2]
        new_name = None
        skip_embeddings = False

        # Parse remaining args
        for arg in sys.argv[3:]:
            if arg == "--skip-embeddings":
                skip_embeddings = True
            else:
                new_name = arg

        result = import_daemon(
            Path(input_path),
            new_daemon_name=new_name,
            skip_embeddings=skip_embeddings
        )
        print(f"\nImport complete!")
        print(f"  Daemon: {result['daemon_name']} ({result['daemon_id'][:8]}...)")
        print(f"  Total rows: {result['total_rows']}")

        if result.get("embedding_counts"):
            print(f"\n  Embeddings regenerated:")
            for embed_type, count in result["embedding_counts"].items():
                print(f"    {embed_type}: {count}")
            print(f"    Total: {sum(result['embedding_counts'].values())}")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
