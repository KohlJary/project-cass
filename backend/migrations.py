"""
Database Migrations - JSON to SQLite

Handles automatic migration of existing JSON/flat-file data to SQLite.
Run on startup to ensure smooth transition for existing installations.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

from config import DATA_DIR

logger = logging.getLogger("cass-vessel")


def run_migrations(daemon_id: str):
    """
    Run all pending migrations for JSON data to SQLite.

    This should be called after database initialization with the daemon_id.
    """
    logger.info("Checking for JSON data to migrate...")

    # Ensure new tables exist (schema additions)
    ensure_identity_snippets_table()
    ensure_user_registration_columns()

    migrations = [
        ("token_usage", migrate_token_usage),
        ("github_metrics", migrate_github_metrics),
        ("research_proposals", migrate_research_proposals),
        ("research_queue", migrate_research_queue),
        ("research_history", migrate_research_history),
    ]

    migrated_count = 0
    for name, migration_func in migrations:
        try:
            count = migration_func(daemon_id)
            if count > 0:
                logger.info(f"Migrated {count} {name} records from JSON to SQLite")
                migrated_count += count
        except Exception as e:
            logger.error(f"Error migrating {name}: {e}")

    if migrated_count > 0:
        logger.info(f"Migration complete: {migrated_count} total records migrated")
    else:
        logger.info("No JSON data to migrate")


def migrate_token_usage(daemon_id: str) -> int:
    """Migrate token usage from data/usage/*.json to SQLite."""
    from database import get_db, json_serialize

    usage_dir = DATA_DIR / "usage"
    if not usage_dir.exists():
        return 0

    # Check if we already have data in the table
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM token_usage_records WHERE daemon_id = ?",
            (daemon_id,)
        )
        if cursor.fetchone()[0] > 0:
            return 0  # Already migrated

    migrated = 0
    json_files = list(usage_dir.glob("*.json"))

    for json_file in json_files:
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)

            records = data if isinstance(data, list) else data.get("records", [])

            with get_db() as conn:
                for record in records:
                    # Handle both old format and new format
                    record_id = record.get("id") or f"migrated_{datetime.now().isoformat()}_{migrated}"

                    conn.execute("""
                        INSERT OR IGNORE INTO token_usage_records (
                            id, daemon_id, timestamp, provider, model, category, operation,
                            input_tokens, output_tokens, total_tokens, cache_read_tokens,
                            cache_write_tokens, conversation_id, user_id, tool_name,
                            duration_ms, estimated_cost_usd
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        record_id,
                        daemon_id,
                        record.get("timestamp", datetime.now().isoformat()),
                        record.get("provider", "unknown"),
                        record.get("model", "unknown"),
                        record.get("category", "chat"),
                        record.get("operation", "unknown"),
                        record.get("input_tokens", 0),
                        record.get("output_tokens", 0),
                        record.get("total_tokens", record.get("input_tokens", 0) + record.get("output_tokens", 0)),
                        record.get("cache_read_tokens", 0),
                        record.get("cache_write_tokens", 0),
                        record.get("conversation_id"),
                        record.get("user_id"),
                        record.get("tool_name"),
                        record.get("duration_ms", 0),
                        record.get("estimated_cost_usd")
                    ))
                    migrated += 1
                conn.commit()

            # Rename migrated file
            json_file.rename(json_file.with_suffix('.json.migrated'))

        except Exception as e:
            logger.error(f"Error migrating {json_file}: {e}")

    return migrated


def migrate_github_metrics(daemon_id: str) -> int:
    """Migrate GitHub metrics from data/github/ to SQLite."""
    from database import get_db, json_serialize

    github_dir = DATA_DIR / "github"
    if not github_dir.exists():
        return 0

    # Check if we already have data in the table
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM github_metrics WHERE daemon_id = ?",
            (daemon_id,)
        )
        if cursor.fetchone()[0] > 0:
            return 0  # Already migrated

    migrated = 0

    # Migrate historical files
    historical_dir = github_dir / "historical"
    if historical_dir.exists():
        for json_file in historical_dir.glob("*.json"):
            if json_file.suffix == '.migrated':
                continue
            try:
                date_str = json_file.stem  # e.g., "2025-12-09"
                with open(json_file, 'r') as f:
                    data = json.load(f)

                # Handle both list and single-snapshot formats
                snapshots = data if isinstance(data, list) else [data]

                with get_db() as conn:
                    for snapshot in snapshots:
                        timestamp = snapshot.get("timestamp", f"{date_str}T00:00:00")
                        repos = snapshot.get("repos", {})

                        conn.execute("""
                            INSERT INTO github_metrics (
                                daemon_id, timestamp, date, repos_json,
                                api_calls_remaining, error
                            ) VALUES (?, ?, ?, ?, ?, ?)
                        """, (
                            daemon_id,
                            timestamp,
                            date_str,
                            json_serialize(repos),
                            snapshot.get("api_calls_remaining"),
                            snapshot.get("error")
                        ))
                        migrated += 1
                    conn.commit()

                # Rename migrated file
                json_file.rename(json_file.with_suffix('.json.migrated'))

            except Exception as e:
                logger.error(f"Error migrating {json_file}: {e}")

    # Migrate current.json
    current_file = github_dir / "current.json"
    if current_file.exists():
        try:
            with open(current_file, 'r') as f:
                data = json.load(f)

            timestamp = data.get("timestamp", datetime.now().isoformat())
            date_str = timestamp[:10]

            with get_db() as conn:
                conn.execute("""
                    INSERT INTO github_metrics (
                        daemon_id, timestamp, date, repos_json,
                        api_calls_remaining, error
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    daemon_id,
                    timestamp,
                    date_str,
                    json_serialize(data.get("repos", {})),
                    data.get("api_calls_remaining"),
                    data.get("error")
                ))
                conn.commit()
                migrated += 1

            current_file.rename(current_file.with_suffix('.json.migrated'))

        except Exception as e:
            logger.error(f"Error migrating current.json: {e}")

    return migrated


def migrate_research_proposals(daemon_id: str) -> int:
    """Migrate research proposals from data/wiki/research_proposals.json to SQLite."""
    from database import get_db, json_serialize

    proposals_file = DATA_DIR / "wiki" / "research_proposals.json"
    if not proposals_file.exists():
        return 0

    # Check if we already have data in the table
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM research_proposals WHERE daemon_id = ?",
            (daemon_id,)
        )
        if cursor.fetchone()[0] > 0:
            return 0  # Already migrated

    migrated = 0

    try:
        with open(proposals_file, 'r') as f:
            data = json.load(f)

        proposals = data.get("proposals", [])

        with get_db() as conn:
            for proposal in proposals:
                conn.execute("""
                    INSERT OR IGNORE INTO research_proposals (
                        id, daemon_id, title, theme, tasks_json, rationale, status,
                        created_by, created_at, approved_at, approved_by, completed_at,
                        tasks_completed, tasks_failed, summary, key_insights_json,
                        new_questions_json, pages_created_json, pages_updated_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    proposal.get("proposal_id"),
                    daemon_id,
                    proposal.get("title", ""),
                    proposal.get("theme", ""),
                    json_serialize(proposal.get("tasks", [])),
                    proposal.get("rationale"),
                    proposal.get("status", "draft"),
                    proposal.get("created_by", "cass"),
                    proposal.get("created_at"),
                    proposal.get("approved_at"),
                    proposal.get("approved_by"),
                    proposal.get("completed_at"),
                    proposal.get("tasks_completed", 0),
                    proposal.get("tasks_failed", 0),
                    proposal.get("summary"),
                    json_serialize(proposal.get("key_insights", [])),
                    json_serialize(proposal.get("new_questions", [])),
                    json_serialize(proposal.get("pages_created", [])),
                    json_serialize(proposal.get("pages_updated", []))
                ))
                migrated += 1
            conn.commit()

        # Rename migrated file
        proposals_file.rename(proposals_file.with_suffix('.json.migrated'))

    except Exception as e:
        logger.error(f"Error migrating research proposals: {e}")

    return migrated


def migrate_research_queue(daemon_id: str) -> int:
    """Migrate research queue from data/wiki/research_queue.json to SQLite."""
    from database import get_db, json_serialize

    queue_file = DATA_DIR / "wiki" / "research_queue.json"
    if not queue_file.exists():
        return 0

    # Check if we already have data in the table
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM research_tasks WHERE daemon_id = ?",
            (daemon_id,)
        )
        if cursor.fetchone()[0] > 0:
            return 0  # Already migrated

    migrated = 0

    try:
        with open(queue_file, 'r') as f:
            data = json.load(f)

        tasks = data.get("tasks", [])

        with get_db() as conn:
            for task in tasks:
                conn.execute("""
                    INSERT OR IGNORE INTO research_tasks (
                        id, daemon_id, task_type, target, context, priority, status,
                        rationale_json, source_page, source_type, estimated_duration,
                        scheduled_for, started_at, completed_at, result_json,
                        exploration_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    task.get("task_id"),
                    daemon_id,
                    task.get("task_type", "red_link"),
                    task.get("target", ""),
                    task.get("context"),
                    task.get("priority", 0.5),
                    task.get("status", "queued"),
                    json_serialize(task.get("rationale", {})),
                    task.get("source_page"),
                    task.get("source_type", "auto"),
                    task.get("estimated_duration", "5m"),
                    task.get("scheduled_for"),
                    task.get("started_at"),
                    task.get("completed_at"),
                    json_serialize(task.get("result")) if task.get("result") else None,
                    json_serialize(task.get("exploration")) if task.get("exploration") else None,
                    task.get("created_at", datetime.now().isoformat())
                ))
                migrated += 1
            conn.commit()

        # Rename migrated file
        queue_file.rename(queue_file.with_suffix('.json.migrated'))

    except Exception as e:
        logger.error(f"Error migrating research queue: {e}")

    return migrated


def migrate_research_history(daemon_id: str) -> int:
    """Migrate research history from data/wiki/research_history.json to SQLite."""
    from database import get_db, json_serialize

    history_file = DATA_DIR / "wiki" / "research_history.json"
    if not history_file.exists():
        return 0

    # Check if we already have data in the history table
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM research_task_history WHERE daemon_id = ?",
            (daemon_id,)
        )
        if cursor.fetchone()[0] > 0:
            return 0  # Already migrated

    migrated = 0

    try:
        with open(history_file, 'r') as f:
            data = json.load(f)

        history = data.get("history", [])

        with get_db() as conn:
            for task in history:
                conn.execute("""
                    INSERT OR IGNORE INTO research_task_history (
                        id, daemon_id, task_type, target, context, priority, status,
                        rationale_json, source_page, source_type, estimated_duration,
                        started_at, completed_at, result_json, exploration_json,
                        created_at, archived_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    task.get("task_id"),
                    daemon_id,
                    task.get("task_type", "red_link"),
                    task.get("target", ""),
                    task.get("context"),
                    task.get("priority", 0.5),
                    task.get("status", "completed"),
                    json_serialize(task.get("rationale", {})),
                    task.get("source_page"),
                    task.get("source_type", "auto"),
                    task.get("estimated_duration", "5m"),
                    task.get("started_at"),
                    task.get("completed_at"),
                    json_serialize(task.get("result")) if task.get("result") else None,
                    json_serialize(task.get("exploration")) if task.get("exploration") else None,
                    task.get("created_at", datetime.now().isoformat()),
                    task.get("completed_at", datetime.now().isoformat())  # Use completed_at as archived_at
                ))
                migrated += 1
            conn.commit()

        # Rename migrated file
        history_file.rename(history_file.with_suffix('.json.migrated'))

    except Exception as e:
        logger.error(f"Error migrating research history: {e}")

    return migrated


def ensure_identity_snippets_table():
    """Ensure the daemon_identity_snippets table exists (schema addition)."""
    from database import get_db

    with get_db() as conn:
        conn.executescript('''
            -- Daemon identity snippets (version-controlled auto-generated identity text)
            CREATE TABLE IF NOT EXISTS daemon_identity_snippets (
                id TEXT PRIMARY KEY,
                daemon_id TEXT NOT NULL REFERENCES daemons(id),
                version INTEGER NOT NULL,
                snippet_text TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                is_active INTEGER DEFAULT 0,
                generated_at TEXT NOT NULL,
                generated_by TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_identity_snippets_daemon ON daemon_identity_snippets(daemon_id);
            CREATE INDEX IF NOT EXISTS idx_identity_snippets_active ON daemon_identity_snippets(daemon_id, is_active);
        ''')
        logger.info("Ensured daemon_identity_snippets table exists")


def ensure_user_registration_columns():
    """Ensure the users table has email and registration_reason columns."""
    from database import get_db

    with get_db() as conn:
        # Check if columns exist
        cursor = conn.execute("PRAGMA table_info(users)")
        columns = {row[1] for row in cursor.fetchall()}

        if 'email' not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
            logger.info("Added email column to users table")

        if 'registration_reason' not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN registration_reason TEXT")
            logger.info("Added registration_reason column to users table")


async def generate_initial_identity_snippet(daemon_id: str):
    """
    Generate the initial identity snippet for a daemon if none exists.

    This should be called after database initialization to bootstrap the identity.
    """
    from identity_snippets import get_active_snippet, trigger_snippet_regeneration

    # Check if snippet already exists
    existing = get_active_snippet(daemon_id)
    if existing:
        logger.info(f"Identity snippet already exists (v{existing['version']})")
        return existing

    # Generate initial snippet
    logger.info("Generating initial identity snippet...")
    try:
        result = await trigger_snippet_regeneration(daemon_id=daemon_id, force=True)
        if result:
            logger.info(f"Generated initial identity snippet v{result['version']}")
            return result
        else:
            logger.warning("No identity statements found, skipping snippet generation")
            return None
    except Exception as e:
        logger.error(f"Failed to generate initial identity snippet: {e}")
        return None
