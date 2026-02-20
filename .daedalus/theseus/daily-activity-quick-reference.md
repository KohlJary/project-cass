# Daily Activity Dashboard - Quick Reference

**Database**: `/home/jaryk/cass/cass-vessel/data/cass.db`
**Filter**: Always include `WHERE daemon_id = 'cass'` (or appropriate daemon)
**Date Filter**: Use `date(timestamp_field) = 'YYYY-MM-DD'`

---

## Core Activity Tables

| Category | Table | Timestamp Field | Key Data |
|----------|-------|----------------|----------|
| **Autonomous Actions** | `grimoire_executions` | `executed_at` | Spell executions, status, trigger |
| | `research_sessions` | `started_at` | Research activity |
| | `solo_reflections` | `started_at` | Introspection sessions |
| | `rhythm_records` | `started_at` | Daily rhythm phases |
| | `work_items` | `created_at`, `completed_at` | Planned work |
| **Conversations** | `messages` | `timestamp` | Chat messages (join via `conversations`) |
| | `conversations` | `created_at`, `updated_at` | Conversation metadata |
| **Memory** | `self_observations` | `created_at` | Self-knowledge updates |
| | `growth_edges` | `last_updated` | Development areas |
| | `opinions` | `last_updated` | Position changes |
| | `open_questions` | `created_at`, `resolved_at` | Curiosities |
| | `milestones` | `triggered_at` | Developmental breakthroughs |
| **World Consumption** | `consumed_articles` | `consumed_at` | Articles read & analyzed |
| | `rss_items` | `seen_at`, `processed_at` | RSS feed items |
| | `research_notes` | `created_at` | Research outputs |
| | `wiki_pages` | `updated_at` | Knowledge base edits |
| **Journals** | `journals` | `date`, `created_at` | Daily reflections |
| | `dreams` | `date`, `created_at` | Dream sequences |
| **Emotional** | `thymos_snapshots` | `snapshot_at` | Emotional state snapshots |
| | `thymos_suggestions` | `suggested_at` | Need-based suggestions |
| | `state_events` | `created_at` | State change audit trail |
| **Creative** | `generated_images` | `created_at` | Generated artwork |
| | `artwork_studies` | `studied_at` | Art study sessions |
| | `creative_processes` | `created_at` | Creative process docs |
| **Social** | `user_observations` | `created_at` | Observations about users |
| | `discord_events` | `created_at` | Discord activity |
| | `peopledex_observations` | `created_at` | Relational knowledge |
| **Outreach** | `outreach_drafts` | `created_at`, `sent_at` | Emails, posts, documents |
| | `development_requests` | `created_at` | Requests to Daedalus |
| **Goals** | `unified_goals` | `created_at`, `completed_at` | Autonomous goals |
| **Resources** | `token_usage_records` | `timestamp` | Token/cost tracking |

---

## Common Query Patterns

### All Activity for a Day
```sql
-- Combined timeline
SELECT 'spell' as type, spell_name as detail, executed_at as ts
FROM grimoire_executions WHERE daemon_id = ? AND date(executed_at) = ?
UNION ALL
SELECT 'message', conversation_id, timestamp FROM messages m
JOIN conversations c ON m.conversation_id = c.id
WHERE c.daemon_id = ? AND date(m.timestamp) = ?
UNION ALL
SELECT 'article', headline, consumed_at FROM consumed_articles
WHERE daemon_id = ? AND date(consumed_at) = ?
UNION ALL
SELECT 'image', prompt, created_at FROM generated_images
WHERE daemon_id = ? AND date(created_at) = ?
ORDER BY ts;
```

### Emotional State for a Day
```sql
SELECT snapshot_at, affect_json, needs_json, felt_state
FROM thymos_snapshots
WHERE daemon_id = ? AND date(snapshot_at) = ?
ORDER BY snapshot_at;
```

### Self-Model Changes
```sql
SELECT 'observation' as type, category, observation, created_at
FROM self_observations WHERE daemon_id = ? AND date(created_at) = ?
UNION ALL
SELECT 'opinion', topic, position, date_formed
FROM opinions WHERE daemon_id = ? AND date(date_formed) = ?
UNION ALL
SELECT 'question', question_type, question, created_at
FROM open_questions WHERE daemon_id = ? AND date(created_at) = ?
ORDER BY created_at;
```

### Creative Output
```sql
SELECT g.created_at, g.prompt, g.purpose, g.image_path,
       c.initial_impulse, c.title
FROM generated_images g
LEFT JOIN creative_processes c ON g.id = c.image_id
WHERE g.daemon_id = ? AND date(g.created_at) = ?;
```

### Token Usage Summary
```sql
SELECT category, provider, model,
       SUM(input_tokens) as input,
       SUM(output_tokens) as output,
       SUM(estimated_cost_usd) as cost
FROM token_usage_records
WHERE daemon_id = ? AND date(timestamp) = ?
GROUP BY category, provider, model;
```

---

## JSON Fields

Parse with `json_extract(field, '$.path')` in SQL or `json.loads()` in Python:

| Field | Structure |
|-------|-----------|
| `affect_json` | `{"valence": 0.6, "arousal": 0.4, ...}` |
| `needs_json` | `{"curiosity": {"current": 0.8, "threshold": 0.5}, ...}` |
| `observations_json` | `[{"text": "...", "confidence": 0.8}, ...]` |
| `growth_edges_json` | `[{"area": "...", "current_state": "...", "importance": 0.7}, ...]` |
| `context_json` | Varies by table |
| `trace_json` | `[{"step": "...", "result": "..."}, ...]` |

---

## Dashboard Sections

### 1. Activity Timeline
All timestamped events merged chronologically.

### 2. Emotional Arc
Thymos snapshots + major state events.

### 3. Autonomous Actions
Grimoire executions + work items + research sessions.

### 4. Conversations
Messages exchanged, summaries created, threads updated.

### 5. Self-Model Evolution
Observations, opinions, questions, milestones.

### 6. World Engagement
Articles consumed, RSS items, research notes.

### 7. Creative Expression
Images generated, art studied, creative processes.

### 8. Social Interactions
User observations, Discord events, relational insights.

### 9. Resource Usage
Token consumption by category, estimated costs.

### 10. Journals & Dreams
Daily reflections and dream sequences.

---

## Aggregation Helpers

### Daily Rollup Template
```sql
-- Create daily summary
SELECT
  date(timestamp) as day,
  COUNT(*) as total_events,
  COUNT(DISTINCT conversation_id) as unique_conversations,
  SUM(input_tokens + output_tokens) as total_tokens
FROM messages m
JOIN conversations c ON m.conversation_id = c.id
WHERE c.daemon_id = ?
  AND m.role = 'assistant'
GROUP BY date(timestamp);
```

### Activity Heatmap
```sql
-- Activity by hour
SELECT
  strftime('%H', timestamp) as hour,
  COUNT(*) as event_count
FROM state_events
WHERE daemon_id = ?
  AND date(created_at) = ?
GROUP BY hour
ORDER BY hour;
```

---

## State Bus Events

Key event types in `state_events` table:

- `session.started`, `session.ended` - Autonomous sessions
- `conversation.message_added` - New message
- `conversation.summary_updated` - Summary created
- `state_delta` - Emotional state change
- `insight.gained` - Self-model insight
- `need.satisfied`, `need.urgent` - Thymos needs

Filter by `event_type` for specific activity streams.

---

**Quick Implementation Path**:
1. Start with `state_events` - it captures most high-level activity
2. Add specific queries for detailed views (self-model, creative, etc.)
3. Pre-aggregate into `source_rollups` for performance
4. Build real-time updates by subscribing to state bus

**End of Quick Reference**
