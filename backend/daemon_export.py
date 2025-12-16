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

# File extension for daemon exports (.anima = Latin for soul/spirit)
ANIMA_EXTENSION = ".anima"


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

    # Note: projects are shared across daemons (no daemon_id)
    # project_files and project_documents are linked to projects, not daemons

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
    "research_queue",

    # Wiki
    "wiki_pages",

    # Goals
    "goals",

    # Operational
    "roadmap_epics",
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

    # Identity snippets (auto-generated identity narratives)
    "daemon_identity_snippets",
]

# Tables that need special handling (foreign keys to other daemon tables)
DEPENDENT_TABLES = {
    "messages": "conversations",  # messages.conversation_id -> conversations.id
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
            "SELECT id, label, name, created_at, kernel_version, status FROM daemons WHERE id = ?",
            (daemon_id,)
        )
        daemon_row = cursor.fetchone()
        if not daemon_row:
            raise ValueError(f"Daemon {daemon_id} not found")

        export_data["daemon"] = {
            "id": daemon_row[0],
            "label": daemon_row[1],
            "name": daemon_row[2],  # Entity name for prompts
            "created_at": daemon_row[3],
            "kernel_version": daemon_row[4],
            "status": daemon_row[5],
        }

        # Export each table
        total_rows = 0
        parent_ids = {}  # Track IDs for dependent table lookups

        for table in DAEMON_TABLES:
            rows = _export_table(conn, table, daemon_id, parent_ids)
            if rows:
                export_data["tables"][table] = rows
                export_data["stats"][table] = len(rows)
                total_rows += len(rows)
                logger.info(f"Exported {len(rows)} rows from {table}")

                # Track IDs for tables that have dependents
                if table in DEPENDENT_TABLES.values():
                    parent_ids[table] = [r.get("id") for r in rows if r.get("id")]

        # Export roadmap_links (special case - no daemon_id, but linked to roadmap_items)
        roadmap_item_ids = [r["id"] for r in export_data["tables"].get("roadmap_items", [])]
        if roadmap_item_ids:
            links = _export_roadmap_links(conn, roadmap_item_ids)
            if links:
                export_data["tables"]["roadmap_links"] = links
                export_data["stats"]["roadmap_links"] = len(links)
                total_rows += len(links)

        # Export projects (shared across daemons - no daemon_id)
        cursor = conn.execute("SELECT * FROM projects")
        columns = [desc[0] for desc in cursor.description]
        projects = [dict(zip(columns, row)) for row in cursor.fetchall()]
        if projects:
            export_data["tables"]["projects"] = projects
            export_data["stats"]["projects"] = len(projects)
            total_rows += len(projects)
            logger.info(f"Exported {len(projects)} projects")

            # Export project_documents and project_files (linked to projects)
            project_ids = [p["id"] for p in projects]
            placeholders = ",".join("?" * len(project_ids))

            cursor = conn.execute(
                f"SELECT * FROM project_documents WHERE project_id IN ({placeholders})",
                project_ids
            )
            columns = [desc[0] for desc in cursor.description]
            docs = [dict(zip(columns, row)) for row in cursor.fetchall()]
            if docs:
                export_data["tables"]["project_documents"] = docs
                export_data["stats"]["project_documents"] = len(docs)
                total_rows += len(docs)
                logger.info(f"Exported {len(docs)} project documents")

            cursor = conn.execute(
                f"SELECT * FROM project_files WHERE project_id IN ({placeholders})",
                project_ids
            )
            columns = [desc[0] for desc in cursor.description]
            files = [dict(zip(columns, row)) for row in cursor.fetchall()]
            if files:
                export_data["tables"]["project_files"] = files
                export_data["stats"]["project_files"] = len(files)
                total_rows += len(files)
                logger.info(f"Exported {len(files)} project files")

        # Optionally include users
        if include_users:
            cursor = conn.execute("SELECT * FROM users")
            columns = [desc[0] for desc in cursor.description]
            users = [dict(zip(columns, row)) for row in cursor.fetchall()]
            export_data["tables"]["users"] = users
            export_data["stats"]["users"] = len(users)
            total_rows += len(users)

        export_data["stats"]["total_rows"] = total_rows

    # Include self_model_graph.json if it exists
    from config import DATA_DIR
    graph_path = DATA_DIR / "cass" / "self_model_graph.json"
    if graph_path.exists():
        try:
            with open(graph_path, 'r') as f:
                export_data["self_model_graph"] = json.load(f)
            node_count = len(export_data["self_model_graph"].get("nodes", []))
            edge_count = len(export_data["self_model_graph"].get("edges", []))
            export_data["stats"]["self_model_graph_nodes"] = node_count
            export_data["stats"]["self_model_graph_edges"] = edge_count
            logger.info(f"Included self_model_graph: {node_count} nodes, {edge_count} edges")
        except Exception as e:
            logger.warning(f"Could not include self_model_graph: {e}")

    # Write output if path specified
    if output_path:
        output_path = Path(output_path)

        if output_path.suffix in (".zip", ANIMA_EXTENSION):
            # Create ZIP archive with JSON + wiki markdown
            _create_export_archive(export_data, output_path, daemon_id)
        else:
            # Write JSON directly
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                json.dump(export_data, f, indent=2, default=str)

        return {
            "success": True,
            "daemon_label": export_data["daemon"]["label"],
            "daemon_name": export_data["daemon"]["name"],
            "output_path": str(output_path),
            "total_rows": total_rows,
            "stats": export_data["stats"],
        }

    return export_data


def _export_table(conn, table: str, daemon_id: str, parent_ids: Dict[str, List[str]] = None) -> List[Dict]:
    """Export all rows from a table for a specific daemon.

    Args:
        conn: Database connection
        table: Table name to export
        daemon_id: Daemon ID to filter by
        parent_ids: Dict mapping parent table names to list of IDs for dependent tables
    """
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
        elif table in DEPENDENT_TABLES and parent_ids:
            # Handle dependent tables (e.g., messages -> conversations)
            parent_table = DEPENDENT_TABLES[table]
            ids = parent_ids.get(parent_table, [])
            if not ids:
                return []

            # Determine the foreign key column name
            if table == "messages":
                fk_column = "conversation_id"
            elif table == "project_files" or table == "project_documents":
                fk_column = "project_id"
            elif table == "research_notes":
                fk_column = "session_id"
            else:
                fk_column = f"{parent_table[:-1]}_id"  # e.g., conversations -> conversation_id

            placeholders = ",".join("?" * len(ids))
            cursor = conn.execute(f"SELECT * FROM {table} WHERE {fk_column} IN ({placeholders})", ids)
        else:
            # Table doesn't have daemon_id and no parent IDs provided
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
        # Write main JSON (graph already included in export_data)
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
        daemon_label = export_data["daemon"]["label"]
        daemon_name = export_data["daemon"]["name"]
        stats = export_data["stats"]

        readme = f"""# {daemon_label} Export

**Entity Name:** {daemon_name}
**Exported:** {export_data['exported_at']}
**Export Version:** {export_data['export_version']}

## Contents

- `daemon_data.json` - Complete daemon data in JSON format
- `wiki/` - Wiki pages as markdown files (if any)
- Self-model graph (embedded in daemon_data.json if available)

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
    if input_path.suffix in (".zip", ANIMA_EXTENSION):
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
            # Use new_daemon_name as label, derive entity name from original or default to label
            entity_name = original_daemon.get("name", new_daemon_name.capitalize())
            conn.execute("""
                INSERT INTO daemons (id, label, name, created_at, kernel_version, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                new_daemon_id,
                new_daemon_name,
                entity_name,
                datetime.now().isoformat(),
                original_daemon.get("kernel_version", "temple-codex-1.0"),
                "active"
            ))
            logger.info(f"Created new daemon '{new_daemon_name}' (entity: {entity_name}) with ID {new_daemon_id}")
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
                INSERT INTO daemons (id, label, name, created_at, kernel_version, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                original_daemon["id"],
                original_daemon.get("label", original_daemon.get("name", "daemon")),  # Handle old exports that don't have label
                original_daemon.get("name", "Cass"),  # Entity name
                original_daemon["created_at"],
                original_daemon.get("kernel_version"),
                original_daemon.get("status", "active")
            ))
            target_daemon_id = original_daemon["id"]

        # Import tables in dependency order
        imported_counts = {}
        old_to_new_ids = {}  # Track ID mappings if we're creating new daemon

        # Import users FIRST (conversations have FK to users)
        users = tables_data.get("users", [])
        if users:
            count = _import_users(conn, users)
            imported_counts["users"] = count
            logger.info(f"Imported {count} users")

        # Import projects SECOND (conversations have FK to projects)
        # Projects don't have daemon_id, so they're handled separately
        projects = tables_data.get("projects", [])
        if projects:
            count = _import_projects(conn, projects)
            imported_counts["projects"] = count
            logger.info(f"Imported {count} projects")

            # Import project_documents and project_files (depend on projects)
            docs = tables_data.get("project_documents", [])
            if docs:
                count = _import_project_items(conn, "project_documents", docs)
                imported_counts["project_documents"] = count
                logger.info(f"Imported {count} project documents")

            files = tables_data.get("project_files", [])
            if files:
                count = _import_project_items(conn, "project_files", files)
                imported_counts["project_files"] = count
                logger.info(f"Imported {count} project files")

        # Import in order (independent tables first)
        import_order = [
            # Core identity (no dependencies on other daemon tables)
            "daemon_profiles",
            "daemon_identity_snippets",
            "growth_edges",
            "opinions",
            "cognitive_snapshots",
            "milestones",
            "development_logs",
            "journals",

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
            "research_queue",

            # Wiki
            "wiki_pages",

            # Goals
            "goals",

            # Conversations (needed before messages and self_observations)
            "conversations",
            "messages",

            # Self observations (has FK to conversations.id via source_conversation_id)
            "self_observations",

            # Operational
            "roadmap_epics",
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

        # Track old->new ID mappings for FK relationships
        id_mapping = {}

        for table in import_order:
            rows = tables_data.get(table, [])
            if not rows:
                continue

            count = _import_table(conn, table, rows, target_daemon_id, original_daemon["id"], id_mapping)
            imported_counts[table] = count
            logger.info(f"Imported {count} rows into {table}")

        # Import roadmap_links (needs id_mapping for source_id/target_id)
        links = tables_data.get("roadmap_links", [])
        if links:
            count = _import_roadmap_links(conn, links, id_mapping)
            imported_counts["roadmap_links"] = count

        conn.commit()

    # Restore self_model_graph.json if included in export
    if "self_model_graph" in export_data:
        try:
            from config import DATA_DIR
            graph_dir = DATA_DIR / "cass"
            graph_dir.mkdir(parents=True, exist_ok=True)
            graph_path = graph_dir / "self_model_graph.json"
            with open(graph_path, 'w') as f:
                json.dump(export_data["self_model_graph"], f, indent=2)
            node_count = len(export_data["self_model_graph"].get("nodes", []))
            edge_count = len(export_data["self_model_graph"].get("edges", []))
            imported_counts["self_model_graph_nodes"] = node_count
            imported_counts["self_model_graph_edges"] = edge_count
            logger.info(f"Restored self_model_graph: {node_count} nodes, {edge_count} edges")
        except Exception as e:
            logger.warning(f"Could not restore self_model_graph: {e}")

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


def _import_table(
    conn,
    table: str,
    rows: List[Dict],
    target_daemon_id: str,
    original_daemon_id: str,
    id_mapping: Dict[str, str] = None
) -> int:
    """Import rows into a table, generating new IDs and updating daemon_id.

    Args:
        conn: Database connection
        table: Table name
        rows: Rows to import
        target_daemon_id: New daemon ID to assign
        original_daemon_id: Original daemon ID (unused but kept for signature)
        id_mapping: Dict to track old_id -> new_id mappings across tables
    """
    import uuid

    if not rows:
        return 0

    if id_mapping is None:
        id_mapping = {}

    # Check if table exists
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    )
    if not cursor.fetchone():
        logger.warning(f"Table {table} does not exist, skipping")
        return 0

    # Get column info including type
    cursor = conn.execute(f"PRAGMA table_info({table})")
    column_info = {row[1]: row[2] for row in cursor.fetchall()}  # name -> type
    columns = list(column_info.keys())

    # Check if id is INTEGER PRIMARY KEY (auto-increment)
    id_is_autoincrement = column_info.get("id", "").upper() == "INTEGER"

    # FK columns that need remapping
    fk_columns = {
        "conversation_id": True,
        "source_conversation_id": True,
        "session_id": True,
        "project_id": True,
        "epic_id": True,
    }

    imported = 0
    for row in rows:
        old_id = row.get("id")

        if id_is_autoincrement:
            # Let SQLite auto-generate the ID, but track mapping after insert
            row.pop("id", None)
        elif old_id and "id" in columns:
            # Generate new UUID for TEXT primary keys
            new_id = str(uuid.uuid4())
            id_mapping[old_id] = new_id
            row["id"] = new_id

        # Update daemon_id if needed
        if "daemon_id" in row:
            row["daemon_id"] = target_daemon_id

        # Remap FK columns to new IDs
        for fk_col in fk_columns:
            if fk_col in row and row[fk_col]:
                old_fk = row[fk_col]
                if old_fk in id_mapping:
                    row[fk_col] = id_mapping[old_fk]

        # Filter to only columns that exist in table
        filtered_row = {k: v for k, v in row.items() if k in columns}

        if not filtered_row:
            continue

        cols = list(filtered_row.keys())
        placeholders = ",".join("?" * len(cols))
        col_names = ",".join(cols)

        try:
            conn.execute(
                f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
                list(filtered_row.values())
            )
            imported += 1
        except Exception as e:
            logger.warning(f"Error importing row into {table}: {e}")

    return imported


def _import_roadmap_links(conn, links: List[Dict], id_mapping: Dict[str, str] = None) -> int:
    """Import roadmap links with ID remapping."""
    if id_mapping is None:
        id_mapping = {}

    imported = 0
    for link in links:
        try:
            # Remap source_id and target_id to new IDs
            source_id = id_mapping.get(link["source_id"], link["source_id"])
            target_id = id_mapping.get(link["target_id"], link["target_id"])

            conn.execute("""
                INSERT OR IGNORE INTO roadmap_links (source_id, target_id, link_type)
                VALUES (?, ?, ?)
            """, (source_id, target_id, link["link_type"]))
            imported += 1
        except Exception as e:
            logger.warning(f"Error importing roadmap link: {e}")
    return imported


def _import_projects(conn, projects: List[Dict]) -> int:
    """Import projects (shared across daemons - no daemon_id)."""
    imported = 0
    for proj in projects:
        try:
            conn.execute("""
                INSERT OR REPLACE INTO projects (
                    id, name, working_directory, created_at, updated_at, user_id, github_repo
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                proj["id"],
                proj["name"],
                proj.get("working_directory"),
                proj["created_at"],
                proj["updated_at"],
                proj.get("user_id"),
                proj.get("github_repo"),
            ))
            imported += 1
        except Exception as e:
            logger.warning(f"Error importing project: {e}")
    return imported


def _import_project_items(conn, table: str, items: List[Dict]) -> int:
    """Import project_documents or project_files."""
    imported = 0
    for item in items:
        try:
            if table == "project_documents":
                conn.execute("""
                    INSERT OR REPLACE INTO project_documents (
                        id, project_id, title, content, created_by, embedded, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item["id"],
                    item["project_id"],
                    item["title"],
                    item["content"],
                    item.get("created_by"),
                    item.get("embedded", 0),
                    item["created_at"],
                    item["updated_at"],
                ))
            elif table == "project_files":
                conn.execute("""
                    INSERT OR REPLACE INTO project_files (
                        id, project_id, path, content, embedded, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    item["id"],
                    item["project_id"],
                    item["path"],
                    item.get("content", ""),
                    item.get("embedded", 0),
                    item["created_at"],
                    item["updated_at"],
                ))
            imported += 1
        except Exception as e:
            logger.warning(f"Error importing {table} item: {e}")
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
            SELECT id, label, name, created_at, kernel_version, status
            FROM daemons
            ORDER BY created_at DESC
        """)

        daemons = []
        for row in cursor.fetchall():
            daemons.append({
                "id": row[0],
                "label": row[1],
                "name": row[2],  # Entity name for prompts
                "created_at": row[3],
                "kernel_version": row[4],
                "status": row[5],
            })

        return daemons


def preview_daemon_import(input_path: Path) -> Dict[str, Any]:
    """
    Preview a daemon import without applying it.

    Args:
        input_path: Path to JSON file or ZIP/anima archive

    Returns:
        Dict with daemon info and stats
    """
    input_path = Path(input_path)

    # Load export data
    if input_path.suffix in (".zip", ANIMA_EXTENSION):
        with ZipFile(input_path, 'r') as zf:
            with zf.open("daemon_data.json") as f:
                export_data = json.load(f)
    else:
        with open(input_path, 'r') as f:
            export_data = json.load(f)

    if export_data.get("export_type") != "daemon":
        raise ValueError("Not a daemon export file")

    daemon = export_data["daemon"]
    return {
        "daemon_label": daemon.get("label", daemon.get("name", "daemon")),  # Handle old exports
        "daemon_name": daemon.get("name", "Cass"),  # Entity name
        "daemon_id": daemon["id"],
        "exported_at": export_data.get("exported_at"),
        "export_version": export_data.get("export_version"),
        "stats": export_data.get("stats", {}),
        "tables": list(export_data.get("tables", {}).keys()),
    }


def list_seed_exports(seed_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    List available .anima exports from seed folder.

    Args:
        seed_dir: Optional path to seed directory. Defaults to ../seed from backend.

    Returns:
        List of export info dicts
    """
    if seed_dir is None:
        seed_dir = Path(__file__).parent.parent / "seed"

    if not seed_dir.exists():
        return []

    exports = []
    for file_path in seed_dir.glob(f"*{ANIMA_EXTENSION}"):
        try:
            preview = preview_daemon_import(file_path)
            exports.append({
                "filename": file_path.name,
                "path": str(file_path),
                "size_bytes": file_path.stat().st_size,
                "size_mb": round(file_path.stat().st_size / (1024 * 1024), 2),
                **preview,
            })
        except Exception as e:
            logger.warning(f"Could not read {file_path}: {e}")
            exports.append({
                "filename": file_path.name,
                "path": str(file_path),
                "size_bytes": file_path.stat().st_size,
                "size_mb": round(file_path.stat().st_size / (1024 * 1024), 2),
                "error": str(e),
            })

    return sorted(exports, key=lambda x: x.get("exported_at", ""), reverse=True)


def delete_daemon(daemon_id: str, confirm: bool = False) -> Dict[str, Any]:
    """
    Delete a daemon and all its associated data.

    Args:
        daemon_id: The daemon ID to delete
        confirm: Must be True to actually delete (safety check)

    Returns:
        Dict with deletion results
    """
    if not confirm:
        raise ValueError("Must set confirm=True to delete a daemon")

    with get_db() as conn:
        # Check daemon exists
        cursor = conn.execute("SELECT label, name FROM daemons WHERE id = ?", (daemon_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Daemon {daemon_id} not found")

        daemon_label = row[0]
        daemon_name = row[1]
        deleted_counts = {}

        # Delete from all daemon tables (order matters for FK constraints)
        # Messages first (depends on conversations)
        cursor = conn.execute("""
            DELETE FROM messages WHERE conversation_id IN
            (SELECT id FROM conversations WHERE daemon_id = ?)
        """, (daemon_id,))
        deleted_counts["messages"] = cursor.rowcount

        # Research notes (depends on research_sessions)
        cursor = conn.execute("""
            DELETE FROM research_notes WHERE session_id IN
            (SELECT id FROM research_sessions WHERE daemon_id = ?)
        """, (daemon_id,))
        deleted_counts["research_notes"] = cursor.rowcount

        # Delete from all other daemon tables
        for table in DAEMON_TABLES:
            if table in ("messages", "research_notes"):
                continue  # Already handled above

            try:
                cursor = conn.execute(f"DELETE FROM {table} WHERE daemon_id = ?", (daemon_id,))
                if cursor.rowcount > 0:
                    deleted_counts[table] = cursor.rowcount
            except Exception as e:
                logger.warning(f"Could not delete from {table}: {e}")

        # Finally delete the daemon itself
        conn.execute("DELETE FROM daemons WHERE id = ?", (daemon_id,))
        conn.commit()

        return {
            "success": True,
            "daemon_id": daemon_id,
            "daemon_label": daemon_label,
            "daemon_name": daemon_name,
            "deleted_counts": deleted_counts,
            "total_deleted": sum(deleted_counts.values()),
        }


# CLI interface
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python daemon_export.py list                    - List all daemons")
        print("  python daemon_export.py seeds                   - List seed exports in ../seed/")
        print("  python daemon_export.py export <daemon_id> [output_path]")
        print("  python daemon_export.py import <input_path> [new_name] [--skip-embeddings]")
        print("  python daemon_export.py preview <input_path>    - Preview import without applying")
        print("")
        print("Options:")
        print("  --skip-embeddings   Skip ChromaDB embedding regeneration during import")
        print("")
        print(f"Note: Default export format is {ANIMA_EXTENSION} (also accepts .zip)")
        sys.exit(1)

    command = sys.argv[1]

    if command == "list":
        daemons = list_daemons()
        print(f"\nFound {len(daemons)} daemon(s):\n")
        for d in daemons:
            print(f"  {d['label']} ({d['id'][:8]}...)")
            print(f"    Entity name: {d['name']}")
            print(f"    Created: {d['created_at']}")
            print(f"    Kernel: {d['kernel_version']}")
            print(f"    Status: {d['status']}")
            print()

    elif command == "seeds":
        exports = list_seed_exports()
        if not exports:
            print("\nNo seed exports found in ../seed/")
        else:
            print(f"\nFound {len(exports)} seed export(s):\n")
            for e in exports:
                print(f"  {e['filename']}")
                if "error" in e:
                    print(f"    Error: {e['error']}")
                else:
                    print(f"    Label: {e['daemon_label']} | Entity: {e['daemon_name']} ({e['daemon_id'][:8]}...)")
                    print(f"    Size: {e['size_mb']} MB")
                    print(f"    Total rows: {e['stats'].get('total_rows', 0)}")
                print()

    elif command == "preview":
        if len(sys.argv) < 3:
            print("Error: input_path required")
            sys.exit(1)

        input_path = sys.argv[2]
        preview = preview_daemon_import(Path(input_path))
        print(f"\nPreview of {input_path}:\n")
        print(f"  Label: {preview['daemon_label']} ({preview['daemon_id'][:8]}...)")
        print(f"  Entity name: {preview['daemon_name']}")
        print(f"  Exported: {preview['exported_at']}")
        print(f"  Version: {preview['export_version']}")
        print(f"\n  Tables:")
        for table, count in sorted(preview['stats'].items()):
            if table != 'total_rows':
                print(f"    {table}: {count}")
        print(f"\n  Total rows: {preview['stats'].get('total_rows', 0)}")

    elif command == "export":
        if len(sys.argv) < 3:
            print("Error: daemon_id required")
            sys.exit(1)

        daemon_id = sys.argv[2]
        output_path = sys.argv[3] if len(sys.argv) > 3 else f"exports/{daemon_id[:8]}_export{ANIMA_EXTENSION}"

        result = export_daemon(daemon_id, Path(output_path))
        print(f"\nExport complete!")
        print(f"  Label: {result['daemon_label']}")
        print(f"  Entity name: {result['daemon_name']}")
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
