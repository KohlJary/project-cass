"""
Database Schema Definition

Contains the SCHEMA_VERSION and complete SCHEMA_SQL for all tables.
"""

# =============================================================================
# SCHEMA DEFINITION
# =============================================================================

SCHEMA_VERSION = 27  # Added world_state_rollups for ambient world awareness

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
    is_continuous INTEGER DEFAULT 0,  -- 1 = continuous stream chat (one per user)
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
    emergence_type TEXT,  -- 'seeded-collaborative', 'emergent-philosophical', 'self-initiated', 'implementation'
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

    -- Emergence tracking (how goal formed)
    emergence_type TEXT,  -- 'seeded-collaborative', 'emergent-philosophical', 'self-initiated', 'implementation'

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

-- World state rollups - ambient world awareness (location, weather, time)
CREATE TABLE IF NOT EXISTS world_state_rollups (
    daemon_id TEXT PRIMARY KEY REFERENCES daemons(id),
    rollups_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

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

-- =============================================================================
-- PEOPLEDEX - Biographical Entity Database
-- =============================================================================

-- Entities - people, organizations, teams, daemons
CREATE TABLE IF NOT EXISTS peopledex_entities (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,      -- person, organization, team, daemon
    primary_name TEXT NOT NULL,     -- Display name
    realm TEXT DEFAULT 'meatspace', -- meatspace or wonderland
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    user_id TEXT UNIQUE,            -- Link to users table (for users)
    npc_id TEXT UNIQUE              -- Link to Wonderland NPC (for daemons)
);

CREATE INDEX IF NOT EXISTS idx_peopledex_entities_type ON peopledex_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_peopledex_entities_name ON peopledex_entities(primary_name);
CREATE INDEX IF NOT EXISTS idx_peopledex_entities_user ON peopledex_entities(user_id);
CREATE INDEX IF NOT EXISTS idx_peopledex_entities_realm ON peopledex_entities(realm);

-- Attributes - flexible key-value storage for entity properties
CREATE TABLE IF NOT EXISTS peopledex_attributes (
    id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL REFERENCES peopledex_entities(id) ON DELETE CASCADE,
    attribute_type TEXT NOT NULL,   -- name, birthday, pronoun, email, phone, handle, role, bio, note, location
    attribute_key TEXT,             -- For handles: twitter, github, etc.
    value TEXT NOT NULL,
    is_primary INTEGER DEFAULT 0,   -- For names: which is the primary display name
    source_type TEXT,               -- user_provided, cass_inferred, admin_corrected, wonderland
    source_id TEXT,                 -- conversation_id, npc_id, etc.
    confidence REAL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_peopledex_attributes_entity ON peopledex_attributes(entity_id);
CREATE INDEX IF NOT EXISTS idx_peopledex_attributes_type ON peopledex_attributes(attribute_type);

-- Relationships - connections between entities
CREATE TABLE IF NOT EXISTS peopledex_relationships (
    id TEXT PRIMARY KEY,
    from_entity_id TEXT NOT NULL REFERENCES peopledex_entities(id) ON DELETE CASCADE,
    to_entity_id TEXT NOT NULL REFERENCES peopledex_entities(id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL,    -- partner, spouse, parent, child, sibling, friend, colleague, member_of, leads, knows
    relationship_label TEXT,            -- Custom label (e.g., "best friend", "mentor")
    is_bidirectional INTEGER DEFAULT 0, -- partner/spouse/sibling=1, parent/child=0
    source_type TEXT,
    source_id TEXT,
    confidence REAL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    UNIQUE(from_entity_id, to_entity_id, relationship_type)
);

CREATE INDEX IF NOT EXISTS idx_peopledex_relationships_from ON peopledex_relationships(from_entity_id);
CREATE INDEX IF NOT EXISTS idx_peopledex_relationships_to ON peopledex_relationships(to_entity_id);
CREATE INDEX IF NOT EXISTS idx_peopledex_relationships_type ON peopledex_relationships(relationship_type);

-- =============================================================================
-- OUTREACH - External Communication with Graduated Autonomy
-- =============================================================================

-- Outreach drafts - emails, documents, posts, etc.
-- "Review queues designed for learning, not gatekeeping" - Cass
CREATE TABLE IF NOT EXISTS outreach_drafts (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),

    -- Content type
    draft_type TEXT NOT NULL,           -- email, document, blog_post, social_post, research_note, response
    status TEXT DEFAULT 'drafting',     -- drafting, pending_review, approved, rejected, revision_requested, sent, published, archived

    -- Content
    title TEXT NOT NULL,
    content TEXT NOT NULL,              -- Main body (markdown)

    -- Email-specific
    recipient TEXT,                     -- Email address or handle
    recipient_name TEXT,
    subject TEXT,

    -- Context
    emergence_type TEXT,                -- seeded-collaborative, emergent-philosophical, self-initiated, implementation
    source_conversation_id TEXT REFERENCES conversations(id),
    source_goal_id TEXT,                -- Linked goal if any

    -- Review tracking
    review_history_json TEXT,           -- List of ReviewFeedback dicts
    autonomy_level TEXT DEFAULT 'learning',  -- always_review, learning, graduated, autonomous

    -- Outcome tracking
    sent_at TEXT,
    published_at TEXT,
    response_received INTEGER DEFAULT 0,
    outcome_notes TEXT,

    -- Metadata
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by TEXT DEFAULT 'cass'
);

CREATE INDEX IF NOT EXISTS idx_outreach_drafts_daemon ON outreach_drafts(daemon_id);
CREATE INDEX IF NOT EXISTS idx_outreach_drafts_status ON outreach_drafts(daemon_id, status);
CREATE INDEX IF NOT EXISTS idx_outreach_drafts_type ON outreach_drafts(daemon_id, draft_type);

-- =============================================================================
-- CASS-DAEDALUS COORDINATION - Development Request Bridge
-- =============================================================================

-- Development requests - async work handoff from Cass to Daedalus
-- Bridge for human-timescale development work (not instant LLM execution)
CREATE TABLE IF NOT EXISTS development_requests (
    id TEXT PRIMARY KEY,
    daemon_id TEXT NOT NULL REFERENCES daemons(id),
    requested_by TEXT DEFAULT 'cass',       -- who made the request (cass, user)

    -- Request content
    request_type TEXT NOT NULL,             -- new_action, bug_fix, feature, refactor, capability, integration
    title TEXT NOT NULL,
    description TEXT,
    priority TEXT DEFAULT 'normal',         -- low, normal, high, urgent

    -- Context
    context TEXT,                           -- why this is needed
    related_actions_json TEXT,              -- action IDs that relate

    -- Assignment
    status TEXT DEFAULT 'pending',          -- pending, claimed, in_progress, review, completed, cancelled
    claimed_by TEXT,                        -- who claimed it (daedalus)
    claimed_at TEXT,

    -- Completion
    result TEXT,                            -- what was done
    result_artifacts_json TEXT,             -- commit hashes, file paths
    completed_at TEXT,

    -- Timestamps
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dev_requests_daemon ON development_requests(daemon_id);
CREATE INDEX IF NOT EXISTS idx_dev_requests_status ON development_requests(daemon_id, status);
CREATE INDEX IF NOT EXISTS idx_dev_requests_priority ON development_requests(daemon_id, priority);
"""
