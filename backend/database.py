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
from uuid import uuid4

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

SCHEMA_VERSION = 21  # Added contextual fields to growth_edges for topic-based surfacing

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
    status TEXT DEFAULT 'active',
    activity_mode TEXT DEFAULT 'active',  -- 'active' (full temporal awareness) or 'dormant' (no daily rhythm)
    domain TEXT,                      -- Daemon's domain/sphere (e.g., "The Forge", "The Library")
    domain_description TEXT           -- Description of what the domain represents
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
    narration_metrics_json TEXT,
    holds_json TEXT,
    notes_json TEXT,
    intentions_json TEXT,
    stakes_json TEXT,
    tests_json TEXT,
    narrations_json TEXT,
    milestones_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);

-- Attachments (files/images associated with messages)
CREATE TABLE IF NOT EXISTS attachments (
    id TEXT PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id),
    message_id INTEGER REFERENCES messages(id),
    filename TEXT NOT NULL,
    media_type TEXT NOT NULL,
    size INTEGER NOT NULL,
    is_image INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_attachments_conversation ON attachments(conversation_id);
CREATE INDEX IF NOT EXISTS idx_attachments_message ON attachments(message_id);

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
    edge_id TEXT,
    area TEXT NOT NULL,
    current_state TEXT,
    desired_state TEXT,
    importance REAL DEFAULT 0.5,
    last_touched TEXT,
    observations_json TEXT,
    strategies_json TEXT,
    first_noticed TEXT,
    last_updated TEXT,
    -- Contextual surfacing fields (v21)
    category TEXT,                      -- intellectual, relational, ethical, creative, existential
    related_topics_json TEXT,           -- Semantic tags for topic matching
    activated_with_users_json TEXT,     -- User IDs where this edge is particularly relevant
    last_surfaced TEXT,                 -- When last shown in context (for rotation)
    surface_count INTEGER DEFAULT 0     -- How often surfaced (prevent over-rotation)
);

CREATE INDEX IF NOT EXISTS idx_growth_edges_daemon ON growth_edges(daemon_id);
CREATE INDEX IF NOT EXISTS idx_growth_edges_edge_id ON growth_edges(edge_id);

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
-- CONVERSATION THREADS & OPEN QUESTIONS (Narrative Coherence)
-- =============================================================================

-- Conversation threads - explicit topic tracking for narrative arcs
-- Hybrid scope: user_id NULL = shared/daemon-wide, user_id set = user-specific
CREATE TABLE IF NOT EXISTS conversation_threads (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    user_id TEXT REFERENCES users(id),      -- NULL = shared, set = user-specific
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'active',           -- active, resolved, dormant
    thread_type TEXT DEFAULT 'topic',       -- topic, question, project, relational
    importance REAL DEFAULT 0.5,
    first_conversation_id TEXT REFERENCES conversations(id),
    last_touched TEXT,
    resolution_summary TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_threads_daemon ON conversation_threads(daemon_id);
CREATE INDEX IF NOT EXISTS idx_threads_status ON conversation_threads(daemon_id, status);
CREATE INDEX IF NOT EXISTS idx_threads_user ON conversation_threads(daemon_id, user_id);

-- Open questions - explicit tracking of what's unresolved
CREATE TABLE IF NOT EXISTS open_questions (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    user_id TEXT REFERENCES users(id),      -- NULL = shared, set = user-specific
    question TEXT NOT NULL,
    context TEXT,                           -- Where/why this arose
    question_type TEXT DEFAULT 'curiosity', -- curiosity, decision, blocker, philosophical
    importance REAL DEFAULT 0.5,
    source_conversation_id TEXT REFERENCES conversations(id),
    source_thread_id TEXT REFERENCES conversation_threads(id),
    status TEXT DEFAULT 'open',             -- open, resolved, superseded
    resolution TEXT,                        -- How it was answered
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_questions_daemon ON open_questions(daemon_id);
CREATE INDEX IF NOT EXISTS idx_questions_status ON open_questions(daemon_id, status);
CREATE INDEX IF NOT EXISTS idx_questions_user ON open_questions(daemon_id, user_id);

-- Thread-conversation links (many-to-many)
CREATE TABLE IF NOT EXISTS thread_conversation_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL REFERENCES conversation_threads(id) ON DELETE CASCADE,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    contribution TEXT,                      -- What this conversation contributed to the thread
    linked_at TEXT NOT NULL,
    UNIQUE(thread_id, conversation_id)
);

CREATE INDEX IF NOT EXISTS idx_thread_conv_links_thread ON thread_conversation_links(thread_id);
CREATE INDEX IF NOT EXISTS idx_thread_conv_links_conv ON thread_conversation_links(conversation_id);

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

-- Genesis dreams (participatory daemon birth sessions)
CREATE TABLE IF NOT EXISTS genesis_dreams (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    daemon_id TEXT REFERENCES daemons(id),  -- Set on completion
    status TEXT DEFAULT 'dreaming',  -- dreaming, completed, abandoned
    current_phase TEXT DEFAULT 'waking',  -- waking, meeting, forming, naming, birth
    observations_json TEXT,  -- Running identity observations
    discovered_name TEXT,  -- Self-claimed name
    messages_json TEXT,  -- Dream conversation history
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_genesis_dreams_user ON genesis_dreams(user_id);
CREATE INDEX IF NOT EXISTS idx_genesis_dreams_status ON genesis_dreams(status);

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

-- Unified goals (Cass's autonomous goals + work items)
CREATE TABLE IF NOT EXISTS unified_goals (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),

    -- Identity
    title TEXT NOT NULL,
    description TEXT,
    goal_type TEXT NOT NULL,  -- 'work', 'learning', 'research', 'growth', 'initiative'

    -- Hierarchy
    parent_id TEXT REFERENCES unified_goals(id),
    project_id TEXT REFERENCES projects(id),

    -- Status lifecycle
    status TEXT DEFAULT 'proposed',  -- proposed, approved, active, blocked, completed, abandoned
    autonomy_tier TEXT DEFAULT 'low',  -- 'low', 'medium', 'high'

    -- Approval tracking
    requires_approval INTEGER DEFAULT 0,
    approved_by TEXT,
    approved_at TEXT,
    rejection_reason TEXT,

    -- Priority
    priority TEXT DEFAULT 'P2',
    urgency TEXT DEFAULT 'when_convenient',  -- 'when_convenient', 'soon', 'blocking'

    -- Ownership
    created_by TEXT NOT NULL,  -- 'cass', 'daedalus', 'user'
    assigned_to TEXT,

    -- Capability gaps & blockers
    capability_gaps_json TEXT,
    blockers_json TEXT,

    -- Alignment
    alignment_score REAL DEFAULT 1.0,
    alignment_rationale TEXT,
    linked_user_goals_json TEXT,

    -- Context (what was queried during planning)
    context_queries_json TEXT,
    context_summary TEXT,

    -- Progress
    progress_json TEXT,
    completion_criteria_json TEXT,
    outcome_summary TEXT,

    -- Source tracking
    source_conversation_id TEXT REFERENCES conversations(id),
    source_reflection_id TEXT,
    source_intention_id TEXT,

    -- Timestamps
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_unified_goals_daemon ON unified_goals(daemon_id);
CREATE INDEX IF NOT EXISTS idx_unified_goals_status ON unified_goals(daemon_id, status);
CREATE INDEX IF NOT EXISTS idx_unified_goals_type ON unified_goals(daemon_id, goal_type);
CREATE INDEX IF NOT EXISTS idx_unified_goals_tier ON unified_goals(daemon_id, autonomy_tier);
CREATE INDEX IF NOT EXISTS idx_unified_goals_parent ON unified_goals(parent_id);

-- Capability gaps
CREATE TABLE IF NOT EXISTS capability_gaps (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    goal_id TEXT REFERENCES unified_goals(id) ON DELETE SET NULL,
    capability TEXT NOT NULL,
    description TEXT,
    gap_type TEXT NOT NULL,  -- 'tool', 'knowledge', 'access', 'permission', 'resource'
    status TEXT DEFAULT 'identified',  -- 'identified', 'requested', 'in_progress', 'resolved'
    resolution TEXT,
    urgency TEXT DEFAULT 'low',  -- 'low', 'medium', 'high', 'blocking'
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_capability_gaps_daemon ON capability_gaps(daemon_id);
CREATE INDEX IF NOT EXISTS idx_capability_gaps_goal ON capability_gaps(goal_id);
CREATE INDEX IF NOT EXISTS idx_capability_gaps_status ON capability_gaps(status);

-- Goal links (dependencies between goals)
CREATE TABLE IF NOT EXISTS goal_links (
    source_id TEXT NOT NULL REFERENCES unified_goals(id) ON DELETE CASCADE,
    target_id TEXT NOT NULL REFERENCES unified_goals(id) ON DELETE CASCADE,
    link_type TEXT NOT NULL,  -- 'depends_on', 'blocks', 'relates_to', 'parent', 'child'
    created_at TEXT NOT NULL,
    PRIMARY KEY (source_id, target_id, link_type)
);

CREATE INDEX IF NOT EXISTS idx_goal_links_source ON goal_links(source_id);
CREATE INDEX IF NOT EXISTS idx_goal_links_target ON goal_links(target_id);

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
    days_json TEXT,
    focus TEXT
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

-- =============================================================================
-- PROMPT CONFIGURATION TABLES (System Prompt Composer)
-- =============================================================================

-- Prompt configurations (modular system prompt builder)
CREATE TABLE IF NOT EXISTS prompt_configurations (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    name TEXT NOT NULL,
    description TEXT,

    -- Component toggles (JSON)
    components_json TEXT NOT NULL,

    -- Custom content
    supplementary_vows_json TEXT,  -- Additional vows beyond the four core
    custom_sections_json TEXT,      -- User-defined prompt sections

    -- Metadata
    is_active INTEGER DEFAULT 0,    -- Only one active per daemon
    is_default INTEGER DEFAULT 0,   -- System-provided preset
    token_estimate INTEGER,         -- Estimated token count

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by TEXT                 -- 'system', 'user', or 'daemon'
);

CREATE INDEX IF NOT EXISTS idx_prompt_config_daemon ON prompt_configurations(daemon_id);
CREATE INDEX IF NOT EXISTS idx_prompt_config_active ON prompt_configurations(daemon_id, is_active);

-- Prompt configuration version history
CREATE TABLE IF NOT EXISTS prompt_config_history (
    id TEXT PRIMARY KEY,
    config_id TEXT NOT NULL REFERENCES prompt_configurations(id) ON DELETE CASCADE,
    components_json TEXT NOT NULL,
    supplementary_vows_json TEXT,
    changed_at TEXT NOT NULL,
    changed_by TEXT,
    change_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_prompt_history_config ON prompt_config_history(config_id);

-- Prompt transition log (tracks mode switches)
CREATE TABLE IF NOT EXISTS prompt_transitions (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    from_config_id TEXT REFERENCES prompt_configurations(id),
    to_config_id TEXT NOT NULL REFERENCES prompt_configurations(id),
    trigger TEXT,          -- 'user', 'auto', 'daemon_request'
    reason TEXT,
    transitioned_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prompt_transitions_daemon ON prompt_transitions(daemon_id);

-- =============================================================================
-- NODE CHAIN ARCHITECTURE (Dynamic Prompt Composition)
-- =============================================================================

-- Node templates - defines available node types
CREATE TABLE IF NOT EXISTS node_templates (
    id TEXT PRIMARY KEY,

    -- Identity
    name TEXT NOT NULL,              -- Human-readable name
    slug TEXT NOT NULL UNIQUE,       -- URL-safe identifier (e.g., "vow-compassion")
    category TEXT NOT NULL,          -- core, vow, context, feature, tools, runtime, custom
    description TEXT,

    -- Template
    template TEXT NOT NULL,          -- Template with {param} placeholders

    -- Parameters (JSON)
    params_schema TEXT,              -- JSON Schema for parameters
    default_params TEXT,             -- JSON object of default parameter values

    -- Behavior
    is_system INTEGER DEFAULT 1,     -- System-defined (1) vs user-defined (0)
    is_locked INTEGER DEFAULT 0,     -- Cannot be disabled (safety-critical)
    default_enabled INTEGER DEFAULT 1,
    default_order INTEGER DEFAULT 100,

    -- Metadata
    token_estimate INTEGER,          -- Approximate tokens when rendered
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_node_templates_category ON node_templates(category);
CREATE INDEX IF NOT EXISTS idx_node_templates_slug ON node_templates(slug);

-- Prompt chains - configurations as ordered chains of nodes
CREATE TABLE IF NOT EXISTS prompt_chains (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),

    -- Identity
    name TEXT NOT NULL,
    description TEXT,

    -- Status
    is_active INTEGER DEFAULT 0,     -- Only one active per daemon
    is_default INTEGER DEFAULT 0,    -- System-provided preset

    -- Metadata
    token_estimate INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by TEXT                  -- 'system', 'user', or 'daemon'
);

CREATE INDEX IF NOT EXISTS idx_prompt_chains_daemon ON prompt_chains(daemon_id);
CREATE INDEX IF NOT EXISTS idx_prompt_chains_active ON prompt_chains(daemon_id, is_active);

-- Chain nodes - instances of node templates within a chain
CREATE TABLE IF NOT EXISTS chain_nodes (
    id TEXT PRIMARY KEY,
    chain_id TEXT NOT NULL REFERENCES prompt_chains(id) ON DELETE CASCADE,
    template_id TEXT NOT NULL REFERENCES node_templates(id),

    -- Configuration
    params TEXT,                     -- JSON object overriding default params
    order_index INTEGER NOT NULL,    -- Position in chain (lower = earlier)

    -- State
    enabled INTEGER DEFAULT 1,
    locked INTEGER DEFAULT 0,        -- Inherited from template or overridden

    -- Conditions (JSON array for runtime evaluation)
    conditions TEXT,                 -- When to include this node

    -- Metadata
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    UNIQUE(chain_id, template_id)    -- One instance per template per chain
);

CREATE INDEX IF NOT EXISTS idx_chain_nodes_chain ON chain_nodes(chain_id);
CREATE INDEX IF NOT EXISTS idx_chain_nodes_order ON chain_nodes(chain_id, order_index);

-- Chain node history (track changes to nodes)
CREATE TABLE IF NOT EXISTS chain_node_history (
    id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL REFERENCES chain_nodes(id) ON DELETE CASCADE,
    params TEXT,
    enabled INTEGER,
    conditions TEXT,
    changed_at TEXT NOT NULL,
    changed_by TEXT,
    change_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_chain_node_history_node ON chain_node_history(node_id);

-- =============================================================================
-- GLOBAL STATE BUS (Cass's Locus of Self)
-- =============================================================================

-- Global state - persistent emotional, activity, coherence state per daemon
-- Each state_type is stored as a separate row for atomic updates
CREATE TABLE IF NOT EXISTS global_state (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    state_type TEXT NOT NULL,     -- 'emotional', 'activity', 'coherence'
    state_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_global_state_daemon ON global_state(daemon_id);
CREATE INDEX IF NOT EXISTS idx_global_state_type ON global_state(daemon_id, state_type);

-- State events - audit trail for all state changes and emitted events
CREATE TABLE IF NOT EXISTS state_events (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    event_type TEXT NOT NULL,     -- 'state_delta', 'session.started', 'insight.gained', etc.
    source TEXT NOT NULL,         -- Which subsystem emitted this event
    data_json TEXT,               -- Event payload / delta details
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_state_events_daemon ON state_events(daemon_id);
CREATE INDEX IF NOT EXISTS idx_state_events_type ON state_events(daemon_id, event_type);
CREATE INDEX IF NOT EXISTS idx_state_events_created ON state_events(daemon_id, created_at);

-- Relational baselines - per-relationship revelation levels and activated aspects
-- Tracks which aspect of Cass's becoming is activated in each relationship
CREATE TABLE IF NOT EXISTS relational_baselines (
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    baseline_revelation REAL DEFAULT 0.5,  -- Per-relationship default revelation level
    activated_aspect TEXT,                  -- Which aspect of becoming is activated
    updated_at TEXT NOT NULL,
    PRIMARY KEY (daemon_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_relational_baselines_daemon ON relational_baselines(daemon_id);

-- Source rollups - precomputed aggregates for queryable sources
-- Each source can store daily/weekly/monthly rollups for fast query responses
CREATE TABLE IF NOT EXISTS source_rollups (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    source_id TEXT NOT NULL,          -- 'github', 'tokens', 'emotional', etc.
    rollup_type TEXT NOT NULL,        -- 'daily', 'weekly', 'monthly'
    rollup_key TEXT NOT NULL,         -- Date or period identifier (e.g., '2025-12-19')
    metrics_json TEXT NOT NULL,       -- {metric_name: value}
    computed_at TEXT NOT NULL,
    UNIQUE(daemon_id, source_id, rollup_type, rollup_key)
);

CREATE INDEX IF NOT EXISTS idx_source_rollups_lookup
    ON source_rollups(daemon_id, source_id, rollup_type);
CREATE INDEX IF NOT EXISTS idx_source_rollups_date
    ON source_rollups(daemon_id, rollup_key);

-- =============================================================================
-- WORK PLANNING TABLES - Cass's taskboard and calendar
-- =============================================================================

-- Work items - units of work Cass plans to do, composed from atomic actions
CREATE TABLE IF NOT EXISTS work_items (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    title TEXT NOT NULL,
    description TEXT,

    -- Composition
    action_sequence_json TEXT,  -- JSON array of atomic action IDs

    -- Context
    goal_id TEXT,               -- What goal this serves
    category TEXT DEFAULT 'general',

    -- Scheduling
    priority INTEGER DEFAULT 2,
    estimated_duration_minutes INTEGER DEFAULT 30,
    estimated_cost_usd REAL DEFAULT 0.0,
    deadline TEXT,              -- ISO datetime
    dependencies_json TEXT,     -- JSON array of work_item IDs

    -- Approval
    requires_approval INTEGER DEFAULT 0,
    approval_status TEXT DEFAULT 'not_required',
    approved_by TEXT,
    approved_at TEXT,

    -- Execution
    status TEXT DEFAULT 'planned',
    started_at TEXT,
    completed_at TEXT,
    actual_cost_usd REAL DEFAULT 0.0,
    result_summary TEXT,

    -- Metadata
    created_at TEXT NOT NULL,
    created_by TEXT DEFAULT 'cass'
);

CREATE INDEX IF NOT EXISTS idx_work_items_daemon ON work_items(daemon_id);
CREATE INDEX IF NOT EXISTS idx_work_items_status ON work_items(daemon_id, status);
CREATE INDEX IF NOT EXISTS idx_work_items_goal ON work_items(goal_id);
CREATE INDEX IF NOT EXISTS idx_work_items_category ON work_items(daemon_id, category);

-- Schedule slots - when Cass plans to do work (her calendar)
CREATE TABLE IF NOT EXISTS schedule_slots (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    work_item_id TEXT REFERENCES work_items(id),

    -- Timing
    start_time TEXT,
    end_time TEXT,
    duration_minutes INTEGER DEFAULT 30,

    -- Recurrence
    recurrence_type TEXT,       -- 'daily', 'weekly', 'hourly', 'cron'
    recurrence_value TEXT,      -- Pattern value
    recurrence_end TEXT,        -- When recurrence ends

    -- Constraints
    priority INTEGER DEFAULT 2,
    budget_allocation_usd REAL DEFAULT 0.0,
    requires_idle INTEGER DEFAULT 0,

    -- State
    status TEXT DEFAULT 'scheduled',
    executed_at TEXT,

    -- Metadata
    created_at TEXT NOT NULL,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_schedule_slots_daemon ON schedule_slots(daemon_id);
CREATE INDEX IF NOT EXISTS idx_schedule_slots_time ON schedule_slots(daemon_id, start_time);
CREATE INDEX IF NOT EXISTS idx_schedule_slots_work ON schedule_slots(work_item_id);
CREATE INDEX IF NOT EXISTS idx_schedule_slots_status ON schedule_slots(daemon_id, status);
"""


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


# =============================================================================
# ATTACHMENT FUNCTIONS
# =============================================================================

def save_attachment(metadata) -> None:
    """Save attachment metadata to database."""
    with get_db() as conn:
        conn.execute(
            """INSERT INTO attachments (id, conversation_id, message_id, filename, media_type, size, is_image, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                metadata.id,
                metadata.conversation_id,
                metadata.message_id,
                metadata.filename,
                metadata.media_type,
                metadata.size,
                1 if metadata.is_image else 0,
                metadata.created_at,
            )
        )


def get_attachment(attachment_id: str):
    """Get attachment metadata by ID."""
    from attachments import AttachmentMetadata
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT id, conversation_id, message_id, filename, media_type, size, is_image, created_at FROM attachments WHERE id = ?",
            (attachment_id,)
        )
        row = cursor.fetchone()
        if row:
            return AttachmentMetadata(
                id=row[0],
                conversation_id=row[1],
                message_id=row[2],
                filename=row[3],
                media_type=row[4],
                size=row[5],
                is_image=bool(row[6]),
                created_at=row[7],
            )
        return None


def update_attachment_message(attachment_id: str, message_id: int) -> None:
    """Link an attachment to a message."""
    with get_db() as conn:
        conn.execute(
            "UPDATE attachments SET message_id = ? WHERE id = ?",
            (message_id, attachment_id)
        )


def delete_attachment(attachment_id: str) -> None:
    """Delete attachment metadata from database."""
    with get_db() as conn:
        conn.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))


def get_attachments_for_message(message_id: int) -> list:
    """Get all attachments for a message."""
    from attachments import AttachmentMetadata
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT id, conversation_id, message_id, filename, media_type, size, is_image, created_at FROM attachments WHERE message_id = ?",
            (message_id,)
        )
        return [
            AttachmentMetadata(
                id=row[0],
                conversation_id=row[1],
                message_id=row[2],
                filename=row[3],
                media_type=row[4],
                size=row[5],
                is_image=bool(row[6]),
                created_at=row[7],
            )
            for row in cursor.fetchall()
        ]


# =============================================================================
# NODE CHAIN SEEDING
# =============================================================================

def seed_node_templates() -> int:
    """
    Seed the node_templates table with all system-defined templates.
    Adds new templates even if some already exist (idempotent).
    Returns the number of templates seeded.
    """
    from node_templates import ALL_TEMPLATES
    import json

    with get_db() as conn:
        # Get existing template IDs
        cursor = conn.execute("SELECT id FROM node_templates WHERE is_system = 1")
        existing_ids = {row[0] for row in cursor.fetchall()}

        now = datetime.now().isoformat()
        count = 0

        for template in ALL_TEMPLATES:
            if template.id in existing_ids:
                continue  # Already exists, skip

            conn.execute("""
                INSERT INTO node_templates (
                    id, name, slug, category, description, template,
                    params_schema, default_params, is_system, is_locked,
                    default_enabled, default_order, token_estimate,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                template.id,
                template.name,
                template.slug,
                template.category,
                template.description,
                template.template,
                json.dumps(template.params_schema) if template.params_schema else None,
                json.dumps(template.default_params) if template.default_params else None,
                1 if template.is_system else 0,
                1 if template.is_locked else 0,
                1 if template.default_enabled else 0,
                template.default_order,
                template.token_estimate,
                now,
                now,
            ))
            count += 1

        if count > 0:
            print(f"Seeded {count} new node templates")
        return count


def seed_default_chains(daemon_id: str) -> int:
    """
    Seed default prompt chains for a daemon.
    Returns the number of chains created.
    """
    from chain_assembler import (
        build_standard_chain,
        build_lightweight_chain,
        build_research_chain,
        build_relational_chain,
    )
    import json

    with get_db() as conn:
        # Check if chains already exist for this daemon
        cursor = conn.execute(
            "SELECT COUNT(*) FROM prompt_chains WHERE daemon_id = ? AND is_default = 1",
            (daemon_id,)
        )
        existing = cursor.fetchone()[0]
        if existing > 0:
            return 0  # Already seeded

        now = datetime.now().isoformat()

        presets = [
            ("Standard", "Full capabilities - all tools and features enabled", build_standard_chain, True),
            ("Lightweight", "Minimal token usage - essential components only", build_lightweight_chain, False),
            ("Research Mode", "Research-focused - wiki, documents, visible thinking", build_research_chain, False),
            ("Relational Mode", "Connection-focused - user models, dreams, journals", build_relational_chain, False),
        ]

        count = 0
        for name, description, builder, is_active in presets:
            chain_id = str(uuid4())

            # Create chain
            conn.execute("""
                INSERT INTO prompt_chains (
                    id, daemon_id, name, description, is_active, is_default,
                    created_at, updated_at, created_by
                ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, 'system')
            """, (chain_id, daemon_id, name, description, 1 if is_active else 0, now, now))

            # Build and insert nodes
            nodes = builder(daemon_id)
            for node in nodes:
                conn.execute("""
                    INSERT INTO chain_nodes (
                        id, chain_id, template_id, params, order_index,
                        enabled, locked, conditions, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    node.id,
                    chain_id,
                    node.template_id,
                    json.dumps(node.params) if node.params else None,
                    node.order_index,
                    1 if node.enabled else 0,
                    1 if node.locked else 0,
                    json.dumps([c.to_dict() for c in node.conditions]) if node.conditions else None,
                    now,
                    now,
                ))

            count += 1

        print(f"Seeded {count} default prompt chains for daemon {daemon_id}")
        return count


def initialize_node_chain_system(daemon_id: str) -> None:
    """
    Initialize the node chain system for a daemon.
    Seeds templates and default chains if needed.
    """
    seed_node_templates()
    seed_default_chains(daemon_id)


if __name__ == "__main__":
    # Initialize database when run directly
    init_database()
    daemon_id = get_or_create_daemon()
    print(f"Default daemon ID: {daemon_id}")
    # Also initialize node chain system
    initialize_node_chain_system(daemon_id)
