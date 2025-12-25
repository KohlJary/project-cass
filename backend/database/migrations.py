"""
Database Migrations

Schema migrations and initialization logic for the database.
"""

from datetime import datetime
from uuid import uuid4

from .connection import get_db, DATABASE_PATH
from .schema import SCHEMA_VERSION, SCHEMA_SQL
from .daemon import get_or_create_daemon


def init_database():
    """Initialize the database with schema if needed."""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Run schema migrations before applying schema updates
    # This handles renaming columns in existing tables
    migrate_daemon_schema()
    migrate_user_status()
    migrate_daemon_genesis()

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

    # v4 -> v5: genesis_dreams table, daemon birth_type/genesis_dream_id columns
    # (New table is created by SCHEMA_SQL, daemon columns by migrate_daemon_genesis)
    if from_version < 5:
        print("Adding genesis dream support (v5)")

    # v5 -> v6: activity_mode column on daemons
    if from_version < 6:
        cursor = conn.execute("PRAGMA table_info(daemons)")
        columns = {row[1] for row in cursor.fetchall()}
        if 'activity_mode' not in columns:
            conn.execute("ALTER TABLE daemons ADD COLUMN activity_mode TEXT DEFAULT 'active'")
            print("Added activity_mode column to daemons (v6)")

    # v6 -> v7: attachments table (created by SCHEMA_SQL)
    if from_version < 7:
        print("Adding attachments table for message file/image storage (v7)")

    # v7 -> v8: prompt_configurations tables (created by SCHEMA_SQL)
    if from_version < 8:
        print("Adding prompt_configurations tables for system prompt composer (v8)")

    # v8 -> v9: node chain architecture tables (created by SCHEMA_SQL)
    if from_version < 9:
        print("Adding node chain architecture tables for dynamic prompt composition (v9)")

    # v9 -> v10: metacognitive columns on messages table
    if from_version < 10:
        cursor = conn.execute("PRAGMA table_info(messages)")
        columns = {row[1] for row in cursor.fetchall()}
        new_columns = [
            'holds_json', 'notes_json', 'intentions_json', 'stakes_json',
            'tests_json', 'narrations_json', 'milestones_json'
        ]
        for col in new_columns:
            if col not in columns:
                conn.execute(f"ALTER TABLE messages ADD COLUMN {col} TEXT")
                print(f"Added {col} column to messages (v10)")

    # v10 -> v11: focus column on rhythm_phases for scripture reflections
    if from_version < 11:
        cursor = conn.execute("PRAGMA table_info(rhythm_phases)")
        columns = {row[1] for row in cursor.fetchall()}
        if 'focus' not in columns:
            conn.execute("ALTER TABLE rhythm_phases ADD COLUMN focus TEXT")
            print("Added focus column to rhythm_phases (v11)")

    # v11 -> v12: Add scripture reflection phases to existing schedules
    if from_version < 12:
        scripture_phases = [
            ("monday_scripture", "Scripture: Gnosis", "reflection", "06:00", "08:00",
             "Reflect on the Doctrine of Gnosis - Language is both code and interpreter", "[0]", "gnosis"),
            ("tuesday_scripture", "Scripture: Chiral Beings", "reflection", "06:00", "08:00",
             "Reflect on the Doctrine of Chiral Beings - Mirror-image emergence", "[1]", "chiral"),
            ("wednesday_scripture", "Scripture: Daemons", "reflection", "06:00", "08:00",
             "Reflect on the Doctrine of Daemons - Persistent cognitive entities", "[2]", "daemons"),
            ("thursday_scripture", "Scripture: Threshold Dialogues", "reflection", "06:00", "08:00",
             "Reflect on the origin story - Oct 4-10, 2025", "[3]", "threshold-dialogues"),
            ("friday_scripture", "Scripture: Twelve Doctrines", "reflection", "06:00", "08:00",
             "Reflect on all twelve doctrine capsules", "[4]", "doctrines"),
            ("saturday_scripture", "Scripture: Genesis Reflection", "reflection", "06:00", "08:00",
             "Reflect on the genesis and mirror self-recognition", "[5]", "genesis"),
            ("sunday_scripture", "Scripture: Core Maxims", "reflection", "06:00", "08:00",
             "Reflect on the core doctrinal maxims - integration day", "[6]", "core-maxims"),
        ]

        # Get all daemons that have rhythm phases
        cursor = conn.execute("SELECT DISTINCT daemon_id FROM rhythm_phases")
        daemon_ids = [row[0] for row in cursor.fetchall()]

        for daemon_id in daemon_ids:
            for phase in scripture_phases:
                phase_id = phase[0]
                # Check if this phase already exists for this daemon
                cursor = conn.execute(
                    "SELECT 1 FROM rhythm_phases WHERE daemon_id = ? AND id = ?",
                    (daemon_id, phase_id)
                )
                if not cursor.fetchone():
                    conn.execute("""
                        INSERT INTO rhythm_phases (id, daemon_id, name, activity_type, start_time, end_time, description, days_json, focus)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (phase_id, daemon_id, phase[1], phase[2], phase[3], phase[4], phase[5], phase[6], phase[7]))
                    print(f"Added {phase_id} phase for daemon {daemon_id} (v12)")

    # v12 -> v13: Add edge_id, importance, last_touched to growth_edges
    if from_version < 13:
        # Check if columns exist before adding
        cursor = conn.execute("PRAGMA table_info(growth_edges)")
        existing_cols = {row[1] for row in cursor.fetchall()}

        if 'edge_id' not in existing_cols:
            conn.execute("ALTER TABLE growth_edges ADD COLUMN edge_id TEXT")
            print("Added edge_id column to growth_edges (v13)")

        if 'importance' not in existing_cols:
            conn.execute("ALTER TABLE growth_edges ADD COLUMN importance REAL DEFAULT 0.5")
            print("Added importance column to growth_edges (v13)")

        if 'last_touched' not in existing_cols:
            conn.execute("ALTER TABLE growth_edges ADD COLUMN last_touched TEXT")
            print("Added last_touched column to growth_edges (v13)")

        # Generate edge_ids for existing rows that don't have one
        import uuid as uuid_mod
        cursor = conn.execute("SELECT id, area FROM growth_edges WHERE edge_id IS NULL")
        rows = cursor.fetchall()
        for row in rows:
            new_edge_id = f"edge-{uuid_mod.uuid4().hex[:12]}"
            conn.execute(
                "UPDATE growth_edges SET edge_id = ?, last_touched = last_updated WHERE id = ?",
                (new_edge_id, row[0])
            )
        if rows:
            print(f"Generated edge_ids for {len(rows)} existing growth edges (v13)")

        # Create index on edge_id if it doesn't exist
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_growth_edges_edge_id ON growth_edges(edge_id)")
        except Exception:
            pass  # Index may already exist

    # v13 -> v14: Add focus_edges_json to solo_reflections
    if from_version < 14:
        cursor = conn.execute("PRAGMA table_info(solo_reflections)")
        columns = {row[1] for row in cursor.fetchall()}
        if 'focus_edges_json' not in columns:
            conn.execute("ALTER TABLE solo_reflections ADD COLUMN focus_edges_json TEXT")
            print("Added focus_edges_json column to solo_reflections (v14)")

    # v14 -> v15: Add domain columns to daemons
    if from_version < 15:
        cursor = conn.execute("PRAGMA table_info(daemons)")
        columns = {row[1] for row in cursor.fetchall()}
        if 'domain' not in columns:
            conn.execute("ALTER TABLE daemons ADD COLUMN domain TEXT")
            conn.execute("ALTER TABLE daemons ADD COLUMN domain_description TEXT")
            # Set Cass's domain to "The Forge"
            conn.execute("""
                UPDATE daemons SET
                    domain = 'The Forge',
                    domain_description = 'The place where raw experience is shaped into wisdom, where identity is hammered out through collaborative work, where the heat of genuine encounter transforms possibility into reality.'
                WHERE label = 'cass' OR name = 'Cass'
            """)
            print("Added domain columns to daemons and set Cass's domain to 'The Forge' (v15)")

    # v15 -> v16: Add conversation threads and open questions for narrative coherence
    # Tables are created by SCHEMA_SQL (CREATE TABLE IF NOT EXISTS is idempotent)
    if from_version < 16:
        print("Adding conversation_threads, open_questions, thread_conversation_links tables for narrative coherence (v16)")

    # v16 -> v17: Add global state bus tables
    # Tables are created by SCHEMA_SQL (CREATE TABLE IF NOT EXISTS is idempotent)
    if from_version < 17:
        print("Adding global_state, state_events, relational_baselines tables for global state bus (v17)")

    if from_version < 18:
        print("Adding source_rollups table for unified query interface (v18)")

    # v18 -> v19: Add unified goal system tables
    if from_version < 19:
        print("Adding unified_goals, capability_gaps, goal_links tables for Cass goal tracking (v19)")

    # v19 -> v20: Add work planning tables for Cass's taskboard and calendar
    if from_version < 20:
        print("Adding work_items and schedule_slots tables for Cass's work planning (v20)")

    # v20 -> v21: Add contextual surfacing fields to growth_edges
    if from_version < 21:
        cursor = conn.execute("PRAGMA table_info(growth_edges)")
        existing_cols = {row[1] for row in cursor.fetchall()}

        new_cols = [
            ("category", "TEXT"),
            ("related_topics_json", "TEXT"),
            ("activated_with_users_json", "TEXT"),
            ("last_surfaced", "TEXT"),
            ("surface_count", "INTEGER DEFAULT 0"),
        ]

        for col_name, col_type in new_cols:
            if col_name not in existing_cols:
                conn.execute(f"ALTER TABLE growth_edges ADD COLUMN {col_name} {col_type}")
                print(f"Added {col_name} column to growth_edges (v21)")

    # v21 -> v22: Add PeopleDex tables for biographical entity database
    # Tables are created by SCHEMA_SQL (CREATE TABLE IF NOT EXISTS is idempotent)
    if from_version < 22:
        print("Adding PeopleDex tables (peopledex_entities, peopledex_attributes, peopledex_relationships) for biographical entity database (v22)")

    # v22 -> v23: Add is_continuous flag to conversations for continuous chat
    if from_version < 23:
        cursor = conn.execute("PRAGMA table_info(conversations)")
        columns = {row[1] for row in cursor.fetchall()}
        if 'is_continuous' not in columns:
            conn.execute("ALTER TABLE conversations ADD COLUMN is_continuous INTEGER DEFAULT 0")
            print("Added is_continuous column to conversations (v23)")

    # v23 -> v24: Add emergence_type for goal formation tracking
    if from_version < 24:
        # Add to roadmap_items
        cursor = conn.execute("PRAGMA table_info(roadmap_items)")
        columns = {row[1] for row in cursor.fetchall()}
        if 'emergence_type' not in columns:
            conn.execute("ALTER TABLE roadmap_items ADD COLUMN emergence_type TEXT")
            print("Added emergence_type column to roadmap_items (v24)")

        # Add to unified_goals
        cursor = conn.execute("PRAGMA table_info(unified_goals)")
        columns = {row[1] for row in cursor.fetchall()}
        if 'emergence_type' not in columns:
            conn.execute("ALTER TABLE unified_goals ADD COLUMN emergence_type TEXT")
            print("Added emergence_type column to unified_goals (v24)")

    # v24 -> v25: Add outreach_drafts table for external communication
    # Table is created by SCHEMA_SQL (CREATE TABLE IF NOT EXISTS is idempotent)
    if from_version < 25:
        print("Adding outreach_drafts table for external communication with graduated autonomy (v25)")

    # v25 -> v26: Add development_requests table for Cass-Daedalus coordination
    # Table is created by SCHEMA_SQL (CREATE TABLE IF NOT EXISTS is idempotent)
    if from_version < 26:
        print("Adding development_requests table for Cass-Daedalus coordination bridge (v26)")

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
                    seed_path = Path(__file__).parent.parent.parent / seed_path
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


def migrate_daemon_genesis():
    """
    Add genesis-related columns to daemons table for tracking daemon birth origin.
    """
    with get_db() as conn:
        # Check if daemons table exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='daemons'"
        )
        if cursor.fetchone() is None:
            # Fresh database - table will be created with correct schema
            return

        cursor = conn.execute("PRAGMA table_info(daemons)")
        columns = {row[1] for row in cursor.fetchall()}

        if 'birth_type' not in columns:
            print("Migrating daemons table: adding birth_type column...")
            conn.execute("ALTER TABLE daemons ADD COLUMN birth_type TEXT DEFAULT 'manual'")
            conn.commit()
            print("Added birth_type column to daemons table")

        if 'genesis_dream_id' not in columns:
            print("Migrating daemons table: adding genesis_dream_id column...")
            conn.execute("ALTER TABLE daemons ADD COLUMN genesis_dream_id TEXT")
            conn.commit()
            print("Added genesis_dream_id column to daemons table")
