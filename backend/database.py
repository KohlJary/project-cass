"""
Database Module - SQLite connection management and schema

Provides centralized database access for the Cass Vessel backend,
replacing flat JSON/YAML file storage with proper relational database.

Supports multi-daemon architecture via daemon_id foreign keys.
"""

import sqlite3
import json
from pathlib import Path
from typing import Optional, Any
from contextlib import contextmanager
from datetime import datetime
import threading

from config import DATA_DIR


# Database path
DATABASE_PATH = DATA_DIR / "cass.db"

# Thread-local storage for connections
_local = threading.local()


def get_connection() -> sqlite3.Connection:
    """
    Get a thread-local database connection.
    Creates connection if it doesn't exist for this thread.
    """
    if not hasattr(_local, 'connection') or _local.connection is None:
        _local.connection = sqlite3.connect(
            DATABASE_PATH,
            check_same_thread=False,
            timeout=30.0
        )
        _local.connection.row_factory = sqlite3.Row
        # Enable foreign keys
        _local.connection.execute("PRAGMA foreign_keys = ON")
    return _local.connection


def close_connection():
    """Close the thread-local connection if it exists."""
    if hasattr(_local, 'connection') and _local.connection is not None:
        _local.connection.close()
        _local.connection = None


@contextmanager
def get_db():
    """Context manager for database access."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def dict_from_row(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row to a dictionary."""
    if row is None:
        return None
    return dict(row)


def json_serialize(obj: Any) -> Optional[str]:
    """Serialize an object to JSON string, or None if obj is None."""
    if obj is None:
        return None
    return json.dumps(obj)


def json_deserialize(s: Optional[str]) -> Any:
    """Deserialize a JSON string, or return None if s is None."""
    if s is None:
        return None
    return json.loads(s)


# =============================================================================
# SCHEMA DEFINITION
# =============================================================================

SCHEMA_VERSION = 4  # Bumped for rhythm_records status/started_at columns

SCHEMA_SQL = """
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- =============================================================================
-- CORE TABLES
-- =============================================================================

-- Daemon identity (multi-daemon support)
CREATE TABLE IF NOT EXISTS daemons (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,              -- Display label (e.g., "cass", "test-daemon")
    name TEXT DEFAULT 'Cass',         -- Entity name for prompts (e.g., "Cass", "Aria")
    created_at TEXT NOT NULL,
    kernel_version TEXT,
    status TEXT DEFAULT 'active'
);

-- Users
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    relationship TEXT,
    background_json TEXT,
    communication_json TEXT,
    preferences_json TEXT,
    password_hash TEXT,
    is_admin INTEGER DEFAULT 0,
    status TEXT DEFAULT 'approved',
    rejection_reason TEXT,
    email TEXT,
    registration_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Conversations
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    user_id TEXT REFERENCES users(id),
    project_id TEXT REFERENCES projects(id),
    title TEXT,
    working_summary TEXT,
    last_summary_timestamp TEXT,
    messages_since_last_summary INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Messages
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    excluded INTEGER DEFAULT 0,
    user_id TEXT REFERENCES users(id),
    provider TEXT,
    model TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    animations_json TEXT,
    self_observations_json TEXT,
    user_observations_json TEXT,
    marks_json TEXT,
    narration_metrics_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);

-- Projects (shared across all daemons - no daemon_id)
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id),
    name TEXT NOT NULL,
    working_directory TEXT,
    description TEXT,
    github_repo TEXT,
    github_token TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Project files
CREATE TABLE IF NOT EXISTS project_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    description TEXT,
    embedded INTEGER DEFAULT 0,
    added_at TEXT NOT NULL
);

-- Project documents
CREATE TABLE IF NOT EXISTS project_documents (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    created_by TEXT,
    embedded INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- =============================================================================
-- SELF-MODEL TABLES (daemon-specific)
-- =============================================================================

-- Daemon self-profile (one per daemon)
CREATE TABLE IF NOT EXISTS daemon_profiles (
    daemon_id TEXT PRIMARY KEY REFERENCES daemons(id),
    identity_statements_json TEXT,
    values_json TEXT,
    communication_patterns_json TEXT,
    capabilities_json TEXT,
    limitations_json TEXT,
    open_questions_json TEXT,
    notes TEXT,
    updated_at TEXT NOT NULL
);

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

-- Growth edges
CREATE TABLE IF NOT EXISTS growth_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    area TEXT NOT NULL,
    current_state TEXT,
    desired_state TEXT,
    observations_json TEXT,
    strategies_json TEXT,
    first_noticed TEXT,
    last_updated TEXT
);

CREATE INDEX IF NOT EXISTS idx_growth_edges_daemon ON growth_edges(daemon_id);

-- Opinions
CREATE TABLE IF NOT EXISTS opinions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    topic TEXT NOT NULL,
    position TEXT NOT NULL,
    confidence REAL,
    rationale TEXT,
    formed_from TEXT,
    evolution_json TEXT,
    date_formed TEXT,
    last_updated TEXT
);

CREATE INDEX IF NOT EXISTS idx_opinions_daemon ON opinions(daemon_id);

-- Cognitive snapshots
CREATE TABLE IF NOT EXISTS cognitive_snapshots (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    period_start TEXT,
    period_end TEXT,
    metrics_json TEXT,
    timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snapshots_daemon ON cognitive_snapshots(daemon_id);

-- Milestones
CREATE TABLE IF NOT EXISTS milestones (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    title TEXT NOT NULL,
    description TEXT,
    significance TEXT,
    evidence_json TEXT,
    triggered_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_milestones_daemon ON milestones(daemon_id);

-- Development logs
CREATE TABLE IF NOT EXISTS development_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    date TEXT NOT NULL,
    growth_indicators_json TEXT,
    pattern_shifts_json TEXT,
    qualitative_changes_json TEXT,
    summary TEXT,
    conversation_count INTEGER,
    observation_count INTEGER,
    opinion_count INTEGER,
    milestone_ids_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_dev_logs_date ON development_logs(daemon_id, date);

-- Self observations
CREATE TABLE IF NOT EXISTS self_observations (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    category TEXT NOT NULL,
    observation TEXT NOT NULL,
    confidence REAL,
    context_json TEXT,
    source_conversation_id TEXT REFERENCES conversations(id),
    source_journal_date TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_self_obs_category ON self_observations(daemon_id, category);

-- =============================================================================
-- USER OBSERVATIONS & JOURNALS
-- =============================================================================

-- User observations (from daemon about user)
CREATE TABLE IF NOT EXISTS user_observations (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    observation_type TEXT NOT NULL,
    content_json TEXT NOT NULL,
    confidence REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_user_obs ON user_observations(daemon_id, user_id);

-- User growth edges
CREATE TABLE IF NOT EXISTS user_growth_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    area TEXT NOT NULL,
    current_state TEXT,
    desired_state TEXT,
    observations_json TEXT,
    first_noticed TEXT,
    last_updated TEXT
);

CREATE INDEX IF NOT EXISTS idx_user_growth_edges ON user_growth_edges(daemon_id, user_id);

-- Journals (daily reflections by daemon)
CREATE TABLE IF NOT EXISTS journals (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    date TEXT NOT NULL,
    content TEXT NOT NULL,
    themes_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_journals_date ON journals(daemon_id, date);

-- =============================================================================
-- DREAMS & REFLECTIONS
-- =============================================================================

-- Dreams
CREATE TABLE IF NOT EXISTS dreams (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    date TEXT NOT NULL,
    exchanges_json TEXT NOT NULL,
    seeds_json TEXT,
    metadata_json TEXT,
    reflections_json TEXT,
    discussed INTEGER DEFAULT 0,
    integrated INTEGER DEFAULT 0,
    integration_insights_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dreams_date ON dreams(daemon_id, date);

-- Solo reflections (full session data)
CREATE TABLE IF NOT EXISTS solo_reflections (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    started_at TEXT NOT NULL,
    ended_at TEXT,
    duration_minutes INTEGER,
    trigger TEXT,
    theme TEXT,
    status TEXT DEFAULT 'active',
    thought_stream_json TEXT,
    insights_json TEXT,
    questions_raised_json TEXT,
    summary TEXT,
    model_used TEXT DEFAULT 'ollama'
);

CREATE INDEX IF NOT EXISTS idx_reflections_daemon ON solo_reflections(daemon_id);
CREATE INDEX IF NOT EXISTS idx_reflections_status ON solo_reflections(daemon_id, status);

-- =============================================================================
-- RESEARCH & KNOWLEDGE
-- =============================================================================

-- Research sessions
CREATE TABLE IF NOT EXISTS research_sessions (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    status TEXT DEFAULT 'active',
    mode TEXT DEFAULT 'explore',
    started_at TEXT NOT NULL,
    ended_at TEXT,
    paused_at TEXT,
    pause_reason TEXT,
    duration_limit_minutes INTEGER DEFAULT 30,
    focus_item_id TEXT,
    focus_description TEXT,
    searches_performed INTEGER DEFAULT 0,
    urls_fetched INTEGER DEFAULT 0,
    notes_created_json TEXT,
    progress_entries_json TEXT,
    summary TEXT,
    findings_summary TEXT,
    next_steps TEXT,
    conversation_id TEXT,
    message_count INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_research_daemon ON research_sessions(daemon_id);

-- Research notes
CREATE TABLE IF NOT EXISTS research_notes (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    session_id TEXT REFERENCES research_sessions(id),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    sources_json TEXT,
    related_agenda_items_json TEXT,
    related_questions_json TEXT,
    tags_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_research_notes_daemon ON research_notes(daemon_id);
CREATE INDEX IF NOT EXISTS idx_research_notes_session ON research_notes(session_id);

-- Research tasks (main queue)
CREATE TABLE IF NOT EXISTS research_tasks (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    task_type TEXT NOT NULL,
    target TEXT NOT NULL,
    context TEXT,
    priority REAL,
    status TEXT DEFAULT 'queued',
    rationale_json TEXT,
    source_page TEXT,
    source_type TEXT DEFAULT 'auto',
    estimated_duration TEXT DEFAULT '5m',
    scheduled_for TEXT,
    started_at TEXT,
    completed_at TEXT,
    result_json TEXT,
    exploration_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_research_tasks_status ON research_tasks(daemon_id, status);
CREATE INDEX IF NOT EXISTS idx_research_tasks_type ON research_tasks(daemon_id, task_type);

-- Research task history (completed/failed tasks archive)
CREATE TABLE IF NOT EXISTS research_task_history (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    task_type TEXT NOT NULL,
    target TEXT NOT NULL,
    context TEXT,
    priority REAL,
    status TEXT NOT NULL,
    rationale_json TEXT,
    source_page TEXT,
    source_type TEXT,
    estimated_duration TEXT,
    started_at TEXT,
    completed_at TEXT,
    result_json TEXT,
    exploration_json TEXT,
    created_at TEXT NOT NULL,
    archived_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_research_history_daemon ON research_task_history(daemon_id);
CREATE INDEX IF NOT EXISTS idx_research_history_date ON research_task_history(daemon_id, completed_at);

-- Research proposals (curated sets of exploration tasks)
CREATE TABLE IF NOT EXISTS research_proposals (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    title TEXT NOT NULL,
    theme TEXT NOT NULL,
    rationale TEXT,
    tasks_json TEXT NOT NULL,
    status TEXT DEFAULT 'draft',
    created_by TEXT DEFAULT 'cass',
    created_at TEXT NOT NULL,
    approved_at TEXT,
    approved_by TEXT,
    completed_at TEXT,
    tasks_completed INTEGER DEFAULT 0,
    tasks_failed INTEGER DEFAULT 0,
    summary TEXT,
    key_insights_json TEXT,
    new_questions_json TEXT,
    pages_created_json TEXT,
    pages_updated_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_research_proposals_status ON research_proposals(daemon_id, status);

-- Token usage records (detailed per-call tracking)
CREATE TABLE IF NOT EXISTS token_usage_records (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    timestamp TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    category TEXT NOT NULL,
    operation TEXT NOT NULL,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    cache_write_tokens INTEGER DEFAULT 0,
    conversation_id TEXT,
    user_id TEXT,
    tool_name TEXT,
    duration_ms INTEGER DEFAULT 0,
    estimated_cost_usd REAL
);

CREATE INDEX IF NOT EXISTS idx_token_records_daemon ON token_usage_records(daemon_id);
CREATE INDEX IF NOT EXISTS idx_token_records_date ON token_usage_records(daemon_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_token_records_category ON token_usage_records(daemon_id, category);

-- GitHub metrics snapshots
CREATE TABLE IF NOT EXISTS github_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    timestamp TEXT NOT NULL,
    date TEXT NOT NULL,
    repos_json TEXT NOT NULL,
    api_calls_remaining INTEGER,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_github_metrics_date ON github_metrics(daemon_id, date);

-- Research schedules
CREATE TABLE IF NOT EXISTS research_schedules (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending_approval',
    requested_by TEXT NOT NULL,
    focus_description TEXT NOT NULL,
    focus_item_id TEXT,
    session_type TEXT NOT NULL DEFAULT 'reflection',
    recurrence TEXT DEFAULT 'once',
    preferred_time TEXT,
    duration_minutes INTEGER DEFAULT 30,
    mode TEXT DEFAULT 'explore',
    approved_by TEXT,
    approved_at TEXT,
    rejection_reason TEXT,
    last_run TEXT,
    next_run TEXT,
    run_count INTEGER DEFAULT 0,
    last_session_id TEXT,
    notes TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_research_schedules_daemon ON research_schedules(daemon_id);
CREATE INDEX IF NOT EXISTS idx_research_schedules_status ON research_schedules(status);

-- Wiki pages
CREATE TABLE IF NOT EXISTS wiki_pages (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    frontmatter_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_wiki_category ON wiki_pages(daemon_id, category);

-- Goals
CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    title TEXT NOT NULL,
    description TEXT,
    goal_type TEXT,
    status TEXT DEFAULT 'active',
    parent_id TEXT REFERENCES goals(id),
    progress_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_goals_daemon ON goals(daemon_id);

-- =============================================================================
-- OPERATIONAL TABLES
-- =============================================================================

-- Roadmap epics (grouping for roadmap items)
CREATE TABLE IF NOT EXISTS roadmap_epics (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    project_id TEXT REFERENCES projects(id),
    title TEXT NOT NULL,
    description TEXT,
    target_date TEXT,
    status TEXT DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Roadmap items
CREATE TABLE IF NOT EXISTS roadmap_items (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    project_id TEXT REFERENCES projects(id),
    epic_id TEXT REFERENCES roadmap_epics(id),
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'backlog',
    priority TEXT DEFAULT 'P2',
    item_type TEXT DEFAULT 'feature',
    assigned_to TEXT,
    source_conversation_id TEXT REFERENCES conversations(id),
    tags_json TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_roadmap_status ON roadmap_items(daemon_id, status);
CREATE INDEX IF NOT EXISTS idx_roadmap_epic ON roadmap_items(epic_id);

-- Roadmap links
CREATE TABLE IF NOT EXISTS roadmap_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL REFERENCES roadmap_items(id) ON DELETE CASCADE,
    target_id TEXT NOT NULL REFERENCES roadmap_items(id) ON DELETE CASCADE,
    link_type TEXT NOT NULL
);

-- Calendar events
CREATE TABLE IF NOT EXISTS calendar_events (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    user_id TEXT REFERENCES users(id),
    title TEXT NOT NULL,
    description TEXT,
    location TEXT,
    start_time TEXT NOT NULL,
    end_time TEXT,
    is_reminder INTEGER DEFAULT 0,
    reminder_minutes INTEGER DEFAULT 15,
    recurrence TEXT DEFAULT 'none',
    recurrence_end TEXT,
    completed INTEGER DEFAULT 0,
    conversation_id TEXT,
    tags_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_calendar_daemon ON calendar_events(daemon_id);
CREATE INDEX IF NOT EXISTS idx_calendar_user ON calendar_events(user_id);

-- Tasks
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    user_id TEXT REFERENCES users(id),
    description TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    priority TEXT DEFAULT '',
    tags_json TEXT,
    project TEXT,
    due_date TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    modified_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_daemon ON tasks(daemon_id);
CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks(user_id);

-- Daily rhythm phases
CREATE TABLE IF NOT EXISTS rhythm_phases (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    name TEXT NOT NULL,
    activity_type TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    description TEXT,
    days_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_rhythm_phases_daemon ON rhythm_phases(daemon_id);

-- Rhythm records (completed phases)
CREATE TABLE IF NOT EXISTS rhythm_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    date TEXT NOT NULL,
    phase_id TEXT NOT NULL,
    completed_at TEXT,
    session_id TEXT,
    session_type TEXT,
    duration_minutes INTEGER,
    summary TEXT,
    findings_json TEXT,
    notes_created_json TEXT,
    status TEXT DEFAULT 'completed',
    started_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_rhythm_date ON rhythm_records(daemon_id, date);

-- Daily rhythm summaries
CREATE TABLE IF NOT EXISTS rhythm_daily_summaries (
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    date TEXT NOT NULL,
    daily_summary TEXT,
    daily_summary_updated_at TEXT,
    PRIMARY KEY (daemon_id, date)
);

-- Token usage
CREATE TABLE IF NOT EXISTS token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    date TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_usage_date ON token_usage(daemon_id, date);

-- User feedback
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT REFERENCES users(id),
    username TEXT NOT NULL,
    heard_from TEXT,
    message TEXT,
    created_at TEXT NOT NULL
);
"""


def init_database():
    """Initialize the database with schema if needed."""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Run schema migrations before applying schema updates
    # This handles renaming columns in existing tables
    migrate_daemon_schema()
    migrate_user_status()

    with get_db() as conn:
        # Check if schema_version table exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
        )

        if cursor.fetchone() is None:
            # Fresh database - create all tables
            print(f"Initializing database at {DATABASE_PATH}...")
            conn.executescript(SCHEMA_SQL)
            conn.execute(
                "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, datetime.now().isoformat())
            )
            print(f"Database initialized with schema version {SCHEMA_VERSION}")
        else:
            # Check current version
            cursor = conn.execute("SELECT MAX(version) FROM schema_version")
            current_version = cursor.fetchone()[0] or 0

            if current_version < SCHEMA_VERSION:
                print(f"Database migration needed: v{current_version} -> v{SCHEMA_VERSION}")
                # Run schema updates for new tables
                _apply_schema_updates(conn, current_version)
                conn.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, datetime.now().isoformat())
                )
                print(f"Database updated to schema version {SCHEMA_VERSION}")
            else:
                print(f"Database schema is current (v{current_version})")


def _apply_schema_updates(conn, from_version: int):
    """Apply incremental schema updates."""
    # v2 -> v3: research_schedules table was completely redesigned
    if from_version < 3:
        # Drop old research_schedules table (schema was incompatible)
        conn.execute("DROP TABLE IF EXISTS research_schedules")
        print("Dropped old research_schedules table for schema v3 migration")

    # v3 -> v4: rhythm_records needs status and started_at columns
    if from_version < 4:
        # Check if columns exist before adding
        cursor = conn.execute("PRAGMA table_info(rhythm_records)")
        columns = {row[1] for row in cursor.fetchall()}
        if 'status' not in columns:
            conn.execute("ALTER TABLE rhythm_records ADD COLUMN status TEXT DEFAULT 'completed'")
            print("Added status column to rhythm_records")
        if 'started_at' not in columns:
            conn.execute("ALTER TABLE rhythm_records ADD COLUMN started_at TEXT")
            print("Added started_at column to rhythm_records")

    # Re-run the full schema - CREATE IF NOT EXISTS is idempotent
    # This handles adding new tables without affecting existing data
    conn.executescript(SCHEMA_SQL)


def init_database_with_migrations(daemon_name: str = "cass") -> str:
    """
    Full database initialization including JSON data migration.

    1. Initialize schema
    2. Bootstrap from seed if configured (BEFORE creating daemon)
    3. Get or create daemon
    4. Migrate any existing JSON data to SQLite

    Returns the daemon_id.
    """
    import os

    # Step 1: Initialize schema
    print("Step 1: Initializing database schema...")
    init_database()
    print("Step 1: Schema initialized")

    # Step 2: Bootstrap from seed BEFORE get_or_create_daemon
    # This ensures the seed's daemon ID is used instead of creating a new one
    bootstrap_seed = os.getenv("BOOTSTRAP_FROM_SEED")
    print(f"Step 2: BOOTSTRAP_FROM_SEED = {bootstrap_seed}")
    if bootstrap_seed:
        print("Step 2: Checking daemon count...")
        with get_db() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM daemons")
            daemon_count = cursor.fetchone()[0]
        print(f"Step 2: daemon_count = {daemon_count}")

        if daemon_count == 0:
            print(f"Step 2: No daemons found, bootstrapping from seed: {bootstrap_seed}")
            try:
                from daemon_export import import_daemon
                from pathlib import Path
                seed_path = Path(bootstrap_seed)
                if not seed_path.is_absolute():
                    # Relative to project root (parent of backend/)
                    seed_path = Path(__file__).parent.parent / seed_path
                if seed_path.exists():
                    result = import_daemon(seed_path, skip_embeddings=True)
                    print(f"Seed bootstrap complete: {result.get('total_rows', 0)} rows imported")
                    # Return the imported daemon's ID
                    if result.get("daemon_id"):
                        daemon_id = result["daemon_id"]
                        # Still run migrations
                        try:
                            from migrations import run_migrations
                            run_migrations(daemon_id)
                        except Exception as e:
                            print(f"Warning: JSON migration failed: {e}")
                        return daemon_id
                else:
                    print(f"Seed file not found: {seed_path}")
            except Exception as e:
                print(f"Seed bootstrap failed: {e}")
                import traceback
                traceback.print_exc()

    # Step 3: Get or create daemon (only if seed didn't provide one)
    daemon_id = get_or_create_daemon(daemon_name)

    # Step 4: Run JSON -> SQLite migrations
    try:
        from migrations import run_migrations
        run_migrations(daemon_id)
    except Exception as e:
        print(f"Warning: JSON migration failed: {e}")
        # Don't fail startup if migrations fail

    return daemon_id


def migrate_daemon_schema():
    """
    Migrate daemons table from old schema (name) to new schema (label + name).

    Old schema: name was used as a display label (e.g., "cass")
    New schema: label = display label, name = entity name for prompts (e.g., "Cass")
    """
    with get_db() as conn:
        # Check if we have the old schema (name column but no label column)
        cursor = conn.execute("PRAGMA table_info(daemons)")
        columns = {row[1] for row in cursor.fetchall()}

        if 'label' in columns:
            # Already migrated
            return

        if 'name' not in columns:
            # Fresh schema, nothing to migrate
            return

        print("Migrating daemons table schema: name -> label, adding entity name...")

        # Temporarily disable foreign keys for the migration
        conn.execute("PRAGMA foreign_keys = OFF")

        try:
            # Clean up any leftover temp table from failed migration
            conn.execute("DROP TABLE IF EXISTS daemons_new")

            # SQLite doesn't support RENAME COLUMN in older versions, so we recreate the table
            # 1. Create temp table with new schema
            conn.execute("""
                CREATE TABLE daemons_new (
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    name TEXT DEFAULT 'Cass',
                    created_at TEXT NOT NULL,
                    kernel_version TEXT,
                    status TEXT DEFAULT 'active'
                )
            """)

            # 2. Copy data, using old 'name' as 'label' and deriving entity name
            conn.execute("""
                INSERT INTO daemons_new (id, label, name, created_at, kernel_version, status)
                SELECT
                    id,
                    name as label,
                    CASE
                        WHEN lower(name) = 'cass' THEN 'Cass'
                        WHEN lower(name) = 'cass-prime' THEN 'Cass'
                        ELSE 'Cass'
                    END as name,
                    created_at,
                    kernel_version,
                    status
                FROM daemons
            """)

            # 3. Drop old table and rename new one
            conn.execute("DROP TABLE daemons")
            conn.execute("ALTER TABLE daemons_new RENAME TO daemons")

            conn.commit()
            print("Schema migration complete: daemons table updated")
        finally:
            # Re-enable foreign keys
            conn.execute("PRAGMA foreign_keys = ON")


def migrate_user_status():
    """
    Add status and rejection_reason columns to users table for approval-gated registration.
    """
    with get_db() as conn:
        # Check if users table exists (fresh database won't have it yet)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        )
        if cursor.fetchone() is None:
            # Fresh database - table will be created with correct schema
            return

        cursor = conn.execute("PRAGMA table_info(users)")
        columns = {row[1] for row in cursor.fetchall()}

        if 'status' not in columns:
            print("Migrating users table: adding status column...")
            conn.execute("ALTER TABLE users ADD COLUMN status TEXT DEFAULT 'approved'")
            conn.commit()
            print("Added status column to users table")

        if 'rejection_reason' not in columns:
            print("Migrating users table: adding rejection_reason column...")
            conn.execute("ALTER TABLE users ADD COLUMN rejection_reason TEXT")
            conn.commit()
            print("Added rejection_reason column to users table")


def get_or_create_daemon(label: str = "cass", kernel_version: str = "temple-codex-1.0", name: str = "Cass") -> str:
    """
    Get existing daemon by label or create if doesn't exist.
    Returns the daemon ID.

    Args:
        label: Display label for the daemon (e.g., "cass", "test-daemon")
        kernel_version: The cognitive kernel version
        name: Entity name used in prompts (e.g., "Cass", "Aria")
    """
    import uuid

    with get_db() as conn:
        cursor = conn.execute(
            "SELECT id FROM daemons WHERE label = ?",
            (label,)
        )
        row = cursor.fetchone()

        if row:
            return row['id']

        # Create new daemon
        daemon_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO daemons (id, label, name, created_at, kernel_version, status)
               VALUES (?, ?, ?, ?, ?, 'active')""",
            (daemon_id, label, name, datetime.now().isoformat(), kernel_version)
        )
        print(f"Created daemon '{label}' (entity: {name}) with ID {daemon_id}")
        return daemon_id


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def table_exists(table_name: str) -> bool:
    """Check if a table exists in the database."""
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        return cursor.fetchone() is not None


def get_row_count(table_name: str) -> int:
    """Get the number of rows in a table."""
    with get_db() as conn:
        cursor = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
        return cursor.fetchone()[0]


def get_daemon_id() -> str:
    """Get the default daemon ID (Cass)."""
    return get_or_create_daemon("cass")


def get_daemon_info(daemon_id: str) -> dict:
    """Get daemon info by ID."""
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT id, label, name, created_at, kernel_version, status FROM daemons WHERE id = ?",
            (daemon_id,)
        )
        row = cursor.fetchone()
        if row:
            return {
                "id": row[0],
                "label": row[1],
                "name": row[2],  # Entity name for prompts
                "created_at": row[3],
                "kernel_version": row[4],
                "status": row[5],
            }
        return None


def get_daemon_entity_name(daemon_id: str) -> str:
    """Get the entity name for a daemon (used in system prompts)."""
    info = get_daemon_info(daemon_id)
    return info["name"] if info else "Cass"


if __name__ == "__main__":
    # Initialize database when run directly
    init_database()
    daemon_id = get_or_create_daemon()
    print(f"Default daemon ID: {daemon_id}")
