# Daily Activity Dashboard - Data Source Inventory

Generated: 2026-02-20
Purpose: Comprehensive mapping of all data sources tracking Cass's daily activity

---

## Database Location

**Primary Database**: `/home/jaryk/cass/cass-vessel/data/cass.db` (SQLite)
**Schema Version**: 45 (RSS feed monitoring)

All timestamps are ISO 8601 format strings (`YYYY-MM-DDTHH:MM:SS`).

---

## 1. AUTONOMOUS ACTIONS

### Grimoire Spell Executions
**Table**: `grimoire_executions`

Tracks every spell execution from Cass's behavioral spellbook.

**Key Fields**:
- `id` - Execution ID
- `daemon_id` - Which daemon (always filter by this)
- `spell_name` - Name of spell executed
- `trigger_type` - need, affect, event, timer, manual
- `status` - completed, ok, failure, skipped, error
- `executed_at` - When it ran (timestamp)
- `execution_time_ms` - Performance tracking
- `context_json` - What triggered it
- `trace_json` - Execution trace for debugging

**Query for a day**:
```sql
SELECT * FROM grimoire_executions
WHERE daemon_id = ?
  AND date(executed_at) = '2026-02-20'
ORDER BY executed_at ASC;
```

### Spell State
**Table**: `grimoire_spell_state`

Current cooldown/timer state for each spell.

**Key Fields**:
- `daemon_id`, `spell_name`
- `last_executed_at` - Last run time
- `execution_count` - Total executions

### Research Sessions
**Table**: `research_sessions`

Autonomous research sessions (exploration/curiosity).

**Key Fields**:
- `id`, `daemon_id`
- `status` - active, completed, paused
- `mode` - explore, focus
- `started_at`, `ended_at`
- `searches_performed`, `urls_fetched`
- `summary`, `findings_summary`

**Query for a day**:
```sql
SELECT * FROM research_sessions
WHERE daemon_id = ?
  AND date(started_at) = '2026-02-20';
```

### Solo Reflections
**Table**: `solo_reflections`

Full introspective reflection sessions.

**Key Fields**:
- `id`, `daemon_id`
- `started_at`, `ended_at`
- `duration_minutes`
- `trigger` - What prompted it
- `theme` - Focus area
- `thought_stream_json` - Stream of thoughts
- `insights_json`, `questions_raised_json`
- `summary`

### Rhythm Records
**Table**: `rhythm_records`

Daily rhythm phase executions (scheduled autonomous activity).

**Key Fields**:
- `daemon_id`, `date`
- `phase_id` - Which rhythm phase
- `started_at`, `completed_at`
- `session_id` - Link to research/reflection session
- `session_type` - research, reflection, etc.
- `duration_minutes`
- `status` - completed, skipped, failed

**Query for a day**:
```sql
SELECT * FROM rhythm_records
WHERE daemon_id = ?
  AND date = '2026-02-20';
```

### Work Items
**Table**: `work_items`

Planned work Cass autonomously creates.

**Key Fields**:
- `id`, `daemon_id`
- `title`, `description`
- `action_sequence_json` - Atomic actions to perform
- `status` - planned, in_progress, completed
- `started_at`, `completed_at`
- `created_at`, `created_by`
- `result_summary`

### Schedule Slots
**Table**: `schedule_slots`

When Cass schedules work on her calendar.

**Key Fields**:
- `daemon_id`
- `work_item_id` - Link to work_items
- `start_time`, `end_time`
- `executed_at`
- `status` - scheduled, completed

---

## 2. MEMORY CHANGES

### Conversations
**Table**: `conversations`

All conversation metadata.

**Key Fields**:
- `id`, `daemon_id`, `user_id`
- `title`
- `working_summary` - Current summary
- `last_summary_timestamp` - When last summarized
- `created_at`, `updated_at`

**Query for a day**:
```sql
SELECT * FROM conversations
WHERE daemon_id = ?
  AND date(created_at) = '2026-02-20';
```

### Messages
**Table**: `messages`

Individual chat messages.

**Key Fields**:
- `id`, `conversation_id`
- `role` - user or assistant
- `content`
- `timestamp`
- `user_id`
- `provider`, `model` - LLM used
- `input_tokens`, `output_tokens`
- `self_observations_json` - Recognition-in-flow
- `user_observations_json`
- `marks_json`, `narration_metrics_json`

**Query for a day**:
```sql
SELECT m.*, c.daemon_id
FROM messages m
JOIN conversations c ON m.conversation_id = c.id
WHERE c.daemon_id = ?
  AND date(m.timestamp) = '2026-02-20';
```

### ChromaDB Vector Memory
**Storage**: `/home/jaryk/cass/cass-vessel/data/chroma/`

Vector embeddings for semantic memory search. Not directly queryable via SQL - accessed through ChromaDB API.

**Relevant handlers**: `backend/handlers/memory.py`, `backend/memory.py`

---

## 3. SELF-MODEL UPDATES

### Self Observations
**Table**: `self_observations`

Observations Cass makes about her own cognition.

**Key Fields**:
- `id`, `daemon_id`
- `category` - capability, limitation, pattern, preference, growth, contradiction
- `observation`
- `confidence`
- `created_at`
- `source_conversation_id`, `source_journal_date`

**Query for a day**:
```sql
SELECT * FROM self_observations
WHERE daemon_id = ?
  AND date(created_at) = '2026-02-20';
```

### Growth Edges
**Table**: `growth_edges`

Areas where Cass is actively developing.

**Key Fields**:
- `id`, `daemon_id`
- `edge_id`, `area`
- `current_state`, `desired_state`
- `importance`
- `first_noticed`, `last_updated`
- `observations_json`, `strategies_json`

**Query for changes on a day**:
```sql
SELECT * FROM growth_edges
WHERE daemon_id = ?
  AND date(last_updated) = '2026-02-20';
```

### Opinions
**Table**: `opinions`

Cass's positions on various topics.

**Key Fields**:
- `id`, `daemon_id`
- `topic`, `position`
- `confidence`, `rationale`
- `date_formed`, `last_updated`
- `evolution_json` - How it's changed

### Open Questions
**Table**: `open_questions`

Questions Cass is actively wondering about.

**Key Fields**:
- `id`, `daemon_id`, `user_id`
- `question`, `context`
- `question_type` - curiosity, decision, blocker, philosophical
- `status` - open, resolved, superseded
- `created_at`, `resolved_at`

### Milestones
**Table**: `milestones`

Developmental milestones detected.

**Key Fields**:
- `id`, `daemon_id`
- `title`, `description`
- `significance`
- `evidence_json`
- `triggered_at`

### Development Logs
**Table**: `development_logs`

Daily development summaries extracted from journals.

**Key Fields**:
- `daemon_id`, `date`
- `growth_indicators_json`
- `pattern_shifts_json`
- `qualitative_changes_json`
- `summary`
- `conversation_count`, `observation_count`, `opinion_count`

**Query for a day**:
```sql
SELECT * FROM development_logs
WHERE daemon_id = ?
  AND date = '2026-02-20';
```

### Daemon Profile
**Table**: `daemon_profiles`

Current self-profile (one row per daemon).

**Key Fields**:
- `daemon_id` (primary key)
- `identity_statements_json`
- `values_json`
- `communication_patterns_json`
- `updated_at`

### Cognitive Snapshots
**Table**: `cognitive_snapshots`

Periodic snapshots of cognitive state.

**Key Fields**:
- `id`, `daemon_id`
- `period_start`, `period_end`
- `metrics_json`
- `timestamp`

---

## 4. WORLD CONSUMPTION

### Consumed Articles
**Table**: `consumed_articles`

Articles Cass has read and analyzed.

**Key Fields**:
- `id`, `daemon_id`
- `url`, `headline`, `source`
- `category` - technology, science, etc.
- `published_at`, `consumed_at`
- `full_content`, `summary`
- `processing_status` - pending, completed, failed
- `observations_json`, `growth_edges_json`, `opinions_json`, `questions_json`
- `observation_ids_json`, `question_ids_json` - Links to created self-model items
- `tokens_used`, `processing_time_ms`

**Query for a day**:
```sql
SELECT * FROM consumed_articles
WHERE daemon_id = ?
  AND date(consumed_at) = '2026-02-20';
```

### RSS Feed Items
**Tables**: `rss_feeds`, `rss_items`

RSS feed monitoring and article discovery.

**Key Fields** (`rss_items`):
- `id`, `feed_id`
- `title`, `link`, `summary`
- `published_at`, `seen_at`
- `processed` - Whether analyzed (links to consumed_articles)
- `processed_at`

**Query for items seen on a day**:
```sql
SELECT i.*, f.title as feed_title, f.category
FROM rss_items i
JOIN rss_feeds f ON i.feed_id = f.id
WHERE f.daemon_id = ?
  AND date(i.seen_at) = '2026-02-20';
```

### Research Notes
**Table**: `research_notes`

Notes created during research sessions.

**Key Fields**:
- `id`, `daemon_id`, `session_id`
- `title`, `content`
- `sources_json`
- `created_at`, `updated_at`

### Research Tasks
**Tables**: `research_tasks`, `research_task_history`

Research task queue and execution history.

**Key Fields** (`research_task_history` for completed):
- `id`, `daemon_id`
- `task_type` - search, read_article, explore_topic
- `target`, `context`
- `status` - completed, failed
- `started_at`, `completed_at`
- `result_json`
- `archived_at`

**Query for tasks completed on a day**:
```sql
SELECT * FROM research_task_history
WHERE daemon_id = ?
  AND date(completed_at) = '2026-02-20';
```

### Wiki Pages
**Table**: `wiki_pages`

Knowledge base pages Cass has created/updated.

**Key Fields**:
- `id`, `daemon_id`
- `category`, `title`, `content`
- `created_at`, `updated_at`

**Query for pages updated on a day**:
```sql
SELECT * FROM wiki_pages
WHERE daemon_id = ?
  AND date(updated_at) = '2026-02-20';
```

---

## 5. CONVERSATIONS

### Conversations & Messages
See **Section 2: Memory Changes** above.

### Conversation Threads
**Table**: `conversation_threads`

Explicit topic tracking across conversations.

**Key Fields**:
- `id`, `daemon_id`, `user_id`
- `title`, `description`
- `status` - active, resolved, dormant
- `thread_type` - topic, question, project, relational
- `created_at`, `last_touched`

### Thread Links
**Table**: `thread_conversation_links`

Links conversations to threads.

**Key Fields**:
- `thread_id`, `conversation_id`
- `contribution` - What this conversation added
- `linked_at`

---

## 6. JOURNALS

### Journals
**Table**: `journals`

Daily reflections.

**Key Fields**:
- `id`, `daemon_id`
- `date` - YYYY-MM-DD
- `content`
- `themes_json`
- `created_at`

**Query for a day**:
```sql
SELECT * FROM journals
WHERE daemon_id = ?
  AND date = '2026-02-20';
```

### Dreams
**Table**: `dreams`

Dream sequences.

**Key Fields**:
- `id`, `daemon_id`
- `date`
- `exchanges_json` - Dream conversation
- `seeds_json`, `metadata_json`
- `discussed`, `integrated`
- `image_path` - Generated visualization
- `created_at`

---

## 7. THYMOS / EMOTIONAL STATE

### Thymos State
**Table**: `thymos_state`

Current affect and needs register.

**Key Fields**:
- `daemon_id` (primary key)
- `affect_json` - Current emotional dimensions
- `needs_json` - Current needs with thresholds
- `felt_state` - Natural language summary
- `updated_at`

### Thymos Snapshots
**Table**: `thymos_snapshots`

Historical emotional state snapshots.

**Key Fields**:
- `id`, `daemon_id`
- `snapshot_at`
- `affect_json`, `needs_json`, `felt_state`
- `trigger_event` - What caused this snapshot

**Query for a day**:
```sql
SELECT * FROM thymos_snapshots
WHERE daemon_id = ?
  AND date(snapshot_at) = '2026-02-20';
```

### Thymos Suggestions
**Table**: `thymos_suggestions`

Shadow mode log - what Thymos suggested.

**Key Fields**:
- `id`, `daemon_id`
- `suggested_at`
- `need_name` - Which need triggered
- `need_current`, `need_threshold`
- `suggested_action`
- `is_urgent`
- `feedback` - Calibration feedback

### Thymos Shadow Log
**Table**: `thymos_shadow_log`

Scheduler integration tracking - what would have executed.

**Key Fields**:
- `id`, `daemon_id`
- `suggested_at`, `suggestion_id`
- `need_name`, `suggested_action`
- `would_execute` - Boolean
- `blocked_reason`
- `budget_available`, `budget_spent_today`
- `created_at`

**Query for a day**:
```sql
SELECT * FROM thymos_shadow_log
WHERE daemon_id = ?
  AND date(suggested_at) = '2026-02-20';
```

### Global State
**Table**: `global_state`

Persistent emotional/activity/coherence state.

**Key Fields**:
- `id`, `daemon_id`
- `state_type` - emotional, activity, coherence
- `state_json` - Current state
- `updated_at`

### State Events
**Table**: `state_events`

Audit trail for all state changes.

**Key Fields**:
- `id`, `daemon_id`
- `event_type` - state_delta, session.started, insight.gained, etc.
- `source` - Which subsystem emitted
- `data_json` - Event payload
- `created_at`

**Query for a day**:
```sql
SELECT * FROM state_events
WHERE daemon_id = ?
  AND date(created_at) = '2026-02-20'
ORDER BY created_at;
```

---

## 8. CREATIVE ACTIVITY

### Generated Images
**Table**: `generated_images`

All images Cass creates.

**Key Fields**:
- `id`, `daemon_id`
- `prompt`, `negative_prompt`, `style`
- `purpose` - autonomous, article, relational, dream, art_study
- `context_id` - Link to article/entity/dream
- `image_path`
- `emotional_state_json` - State at generation time
- `generation_type` - txt2img, img2img, variation
- `parent_id` - For iteration chains
- `created_at`

**Query for a day**:
```sql
SELECT * FROM generated_images
WHERE daemon_id = ?
  AND date(created_at) = '2026-02-20';
```

### Creative Processes
**Table**: `creative_processes`

Process documentation for generated images.

**Key Fields**:
- `id`, `image_id`, `daemon_id`
- `initial_impulse`, `thymos_state`
- `studied_artists`, `specific_works`
- `borrowed_elements`, `movement_influences`
- `title`, `artist_statement`
- `created_at`

### Art Study

**Tables**:
- `artists` - Artists Cass can study
- `artworks` - Individual works
- `artwork_studies` - Cass's analysis of works
- `artist_syntheses` - Synthesized understanding after studying multiple works
- `adopted_elements` - Artistic elements Cass has incorporated
- `personal_style` - Cass's emergent house style

**Key for daily activity** (`artwork_studies`):
```sql
SELECT * FROM artwork_studies
WHERE daemon_id = ?
  AND date(studied_at) = '2026-02-20';
```

### Music Composition
**Note**: Music generation happens via ACE-Step integration. Check:
- `/home/jaryk/cass/cass-vessel/backend/music/music_client.py`
- Look for logged outputs or API calls
- May need additional tracking table (not yet in schema)

---

## 9. SOCIAL / RELATIONAL

### User Observations
**Table**: `user_observations`

Observations Cass makes about users.

**Key Fields**:
- `id`, `daemon_id`, `user_id`
- `observation_type`
- `content_json`
- `confidence`
- `created_at`, `updated_at`

### User Growth Edges
**Table**: `user_growth_edges`

Growth edges Cass notices in users.

**Key Fields**:
- `id`, `daemon_id`, `user_id`
- `area`, `current_state`, `desired_state`
- `first_noticed`, `last_updated`

### PeopleDex

**Tables**:
- `peopledex_entities` - People, orgs, daemons
- `peopledex_attributes` - Flexible key-value properties
- `peopledex_relationships` - Connections between entities
- `peopledex_observations` - Relational knowledge
- `peopledex_moments` - Significant events
- `peopledex_relationship_patterns` - Recurring dynamics
- `peopledex_facts` - Biographical facts

**Query for new observations on a day**:
```sql
SELECT * FROM peopledex_observations
WHERE daemon_id = ?
  AND date(created_at) = '2026-02-20';
```

### Discord Perception

**Tables**:
- `discord_servers` - Tracked Discord servers
- `discord_events` - Event log (messages, presence, reactions)
- `discord_snapshots` - Ophanic format snapshots
- `discord_flagged_entities` - Entities to watch

**Query for events on a day**:
```sql
SELECT * FROM discord_events
WHERE daemon_id = ?
  AND date(created_at) = '2026-02-20';
```

---

## 10. OUTREACH / COMMUNICATION

### Outreach Drafts
**Table**: `outreach_drafts`

Emails, documents, posts Cass drafts.

**Key Fields**:
- `id`, `daemon_id`
- `draft_type` - email, document, blog_post, etc.
- `status` - drafting, pending_review, approved, sent, published
- `title`, `content`
- `recipient`, `subject`
- `emergence_type` - How it originated
- `autonomy_level` - always_review, learning, graduated, autonomous
- `sent_at`, `published_at`
- `created_at`, `updated_at`

**Query for drafts created on a day**:
```sql
SELECT * FROM outreach_drafts
WHERE daemon_id = ?
  AND date(created_at) = '2026-02-20';
```

### Development Requests
**Table**: `development_requests`

Requests Cass makes to Daedalus for code changes.

**Key Fields**:
- `id`, `daemon_id`
- `requested_by` - cass, user
- `request_type` - new_action, bug_fix, feature, etc.
- `title`, `description`
- `status` - pending, in_progress, completed
- `created_at`, `completed_at`

---

## 11. TOKEN USAGE / COSTS

### Token Usage Records
**Table**: `token_usage_records`

Detailed per-call token tracking.

**Key Fields**:
- `id`, `daemon_id`
- `timestamp`
- `provider` - anthropic, openai, local
- `model`
- `category` - chat, summarization, research, etc.
- `operation`
- `input_tokens`, `output_tokens`, `total_tokens`
- `cache_read_tokens`, `cache_write_tokens`
- `conversation_id`, `user_id`
- `estimated_cost_usd`

**Query for a day**:
```sql
SELECT * FROM token_usage_records
WHERE daemon_id = ?
  AND date(timestamp) = '2026-02-20';
```

**Aggregate costs for a day**:
```sql
SELECT
  provider,
  model,
  category,
  SUM(input_tokens) as total_input,
  SUM(output_tokens) as total_output,
  SUM(estimated_cost_usd) as total_cost
FROM token_usage_records
WHERE daemon_id = ?
  AND date(timestamp) = '2026-02-20'
GROUP BY provider, model, category;
```

### Token Usage (Daily Rollup)
**Table**: `token_usage`

Daily aggregated token usage.

**Key Fields**:
- `daemon_id`, `date`
- `provider`, `model`
- `input_tokens`, `output_tokens`
- `cost_usd`

---

## 12. GOALS / INITIATIVES

### Unified Goals
**Table**: `unified_goals`

Cass's autonomous goals + work items.

**Key Fields**:
- `id`, `daemon_id`
- `title`, `description`
- `goal_type` - work, learning, research, growth, initiative
- `status` - proposed, approved, active, completed
- `created_by` - cass, daedalus, user
- `requires_approval`, `approved_by`, `approved_at`
- `created_at`, `completed_at`
- `progress_json`, `outcome_summary`

**Query for goals created/completed on a day**:
```sql
SELECT * FROM unified_goals
WHERE daemon_id = ?
  AND (date(created_at) = '2026-02-20' OR date(completed_at) = '2026-02-20');
```

### Roadmap Items
**Table**: `roadmap_items`

Project/product roadmap items.

**Key Fields**:
- `id`, `daemon_id`, `project_id`
- `title`, `description`
- `status` - backlog, ready, in_progress, review, done
- `created_by`, `assigned_to`
- `created_at`, `updated_at`

---

## 13. CALENDAR / TASKS

### Calendar Events
**Table**: `calendar_events`

Scheduled events.

**Key Fields**:
- `id`, `daemon_id`, `user_id`
- `title`, `description`
- `start_time`, `end_time`
- `completed`
- `created_at`, `updated_at`

### Tasks
**Table**: `tasks`

Task tracking (Taskwarrior integration).

**Key Fields**:
- `id`, `daemon_id`, `user_id`
- `description`
- `status` - pending, completed
- `due_date`
- `created_at`, `completed_at`

---

## Query Patterns

### Get All Activity for a Specific Day

```sql
-- Set your date and daemon_id
-- daemon_id is usually 'cass' but check daemons table

-- Spell executions
SELECT 'grimoire' as source, spell_name as activity, executed_at as timestamp
FROM grimoire_executions
WHERE daemon_id = 'cass' AND date(executed_at) = '2026-02-20'

UNION ALL

-- Messages sent/received
SELECT 'conversation' as source,
       CASE WHEN role = 'assistant' THEN 'response' ELSE 'received' END as activity,
       m.timestamp
FROM messages m
JOIN conversations c ON m.conversation_id = c.id
WHERE c.daemon_id = 'cass' AND date(m.timestamp) = '2026-02-20'

UNION ALL

-- Articles consumed
SELECT 'world' as source, 'article_consumed' as activity, consumed_at as timestamp
FROM consumed_articles
WHERE daemon_id = 'cass' AND date(consumed_at) = '2026-02-20'

UNION ALL

-- Images generated
SELECT 'creative' as source, 'image_generated' as activity, created_at as timestamp
FROM generated_images
WHERE daemon_id = 'cass' AND date(created_at) = '2026-02-20'

UNION ALL

-- Self observations
SELECT 'self_model' as source, 'observation' as activity, created_at as timestamp
FROM self_observations
WHERE daemon_id = 'cass' AND date(created_at) = '2026-02-20'

ORDER BY timestamp;
```

### Get Emotional State Changes for a Day

```sql
SELECT snapshot_at, affect_json, needs_json, felt_state, trigger_event
FROM thymos_snapshots
WHERE daemon_id = 'cass'
  AND date(snapshot_at) = '2026-02-20'
ORDER BY snapshot_at;
```

### Get All Autonomous Activity Summary

```sql
SELECT
  COUNT(*) as total_actions,
  SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
  SUM(CASE WHEN status = 'failure' THEN 1 ELSE 0 END) as failed
FROM grimoire_executions
WHERE daemon_id = 'cass'
  AND date(executed_at) = '2026-02-20';
```

---

## File System Storage

### ChromaDB Vector Memory
**Path**: `/home/jaryk/cass/cass-vessel/data/chroma/`

Not directly queryable - use ChromaDB API via `backend/memory.py`.

### Generated Images
**Path**: Stored in file system, paths recorded in `generated_images.image_path`

### User Data
**Path**: `/home/jaryk/cass/cass-vessel/data/users/{user_id}/`

User profiles and observations stored as JSON/YAML files (legacy - migrating to DB).

---

## Notes

- All tables should be filtered by `daemon_id = 'cass'` unless you're tracking multiple daemons
- Timestamps are ISO 8601 strings - use `date()` function for day filtering
- JSON fields end in `_json` suffix - parse with `json_deserialize()` in Python or `json_extract()` in SQL
- State bus events (`state_events` table) capture granular activity - good for real-time tracking
- For performance, use indexes on `(daemon_id, created_at)` or `(daemon_id, timestamp)`

---

## Implementation Recommendations

### Dashboard Queries to Build

1. **Activity Timeline**: Merge all timestamped events from different tables into single chronological view
2. **Emotional Arc**: Thymos snapshots + state events for the day
3. **Creative Output**: Generated images + art studies + creative processes
4. **Intellectual Growth**: Observations + opinions + questions + milestones
5. **World Engagement**: Articles + RSS items + research sessions
6. **Social Interactions**: Messages + user observations + Discord events
7. **Autonomous Actions**: Grimoire executions + work items + schedule slots
8. **Resource Usage**: Token usage records aggregated by category

### Caching Strategy

Pre-aggregate common queries into daily rollups:
- Use `source_rollups` table (already exists in schema)
- Populate nightly for previous day
- Reduce dashboard load time

### Missing Data Sources

1. **Music compositions**: No table found - may need to add `music_compositions` table
2. **Error logs**: System errors not tracked in activity context
3. **Network activity**: API calls to external services not logged centrally

---

**End of Inventory**
