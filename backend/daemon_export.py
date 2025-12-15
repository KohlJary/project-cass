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
    merge_existing: bool = False
) -> Dict[str, Any]:
    """
    Import a daemon from an export file.

    Args:
        input_path: Path to JSON file or ZIP archive
        new_daemon_name: Optional new name for the daemon (creates new daemon_id)
        merge_existing: If True, merge into existing daemon instead of creating new

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

    return {
        "success": True,
        "daemon_id": target_daemon_id,
        "daemon_name": new_daemon_name or original_daemon["name"],
        "imported_counts": imported_counts,
        "total_rows": sum(imported_counts.values()),
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
        print("  python daemon_export.py import <input_path> [new_name]")
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
        new_name = sys.argv[3] if len(sys.argv) > 3 else None

        result = import_daemon(Path(input_path), new_daemon_name=new_name)
        print(f"\nImport complete!")
        print(f"  Daemon: {result['daemon_name']} ({result['daemon_id'][:8]}...)")
        print(f"  Total rows: {result['total_rows']}")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
