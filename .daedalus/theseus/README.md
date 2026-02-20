# Daily Activity Dashboard - Data Inventory

**Generated**: 2026-02-20
**Purpose**: Complete mapping of all data sources for building Cass's daily activity dashboard

---

## Documents in This Directory

### 1. `daily-activity-data-inventory.md`
**Comprehensive reference** - Full detailed inventory of every table, field, and data source.

Use this for:
- Understanding what data exists
- Detailed field descriptions
- Query examples for each data type
- File system storage locations

### 2. `daily-activity-quick-reference.md`
**Fast lookup** - Condensed table of all activity sources with key fields.

Use this for:
- Quick scanning of available data
- Table-to-activity mapping
- Common query patterns
- Dashboard section recommendations

### 3. `dashboard-sql-queries.sql`
**Ready-to-use queries** - Production SQL queries for dashboard implementation.

Use this for:
- Copy-paste queries for common views
- Complete activity timeline
- Aggregate summaries
- Per-category breakdowns

---

## Quick Start

### 1. Get All Activity for a Day

```sql
-- See dashboard-sql-queries.sql for the complete timeline query
-- Returns: source, activity, detail, timestamp
```

### 2. Core Tables to Start With

**Highest signal-to-noise for daily activity**:

1. `state_events` - Captures most high-level activity events
2. `messages` - Conversation activity (join via `conversations`)
3. `grimoire_executions` - Autonomous spell executions
4. `token_usage_records` - Resource consumption
5. `thymos_snapshots` - Emotional state progression

### 3. Dashboard Sections

Build these views in order:

1. **Activity Timeline** - Merged chronological view
2. **Emotional Arc** - Thymos snapshots + state events
3. **Autonomous Actions** - Grimoire + work items + research
4. **Conversations** - Messages, summaries, threads
5. **Self-Model Evolution** - Observations, opinions, questions
6. **World Engagement** - Articles, RSS, research notes
7. **Creative Expression** - Images, art studies
8. **Resource Usage** - Token costs by category
9. **Social** - User observations, Discord events
10. **Journals** - Daily reflections and dreams

---

## Database Schema

**Location**: `/home/jaryk/cass/cass-vessel/data/cass.db`
**Schema Version**: 45
**Schema Definition**: `/home/jaryk/cass/cass-vessel/backend/database/schema.py`

**Always filter by**:
- `daemon_id = 'cass'` (or appropriate daemon ID)
- `date(timestamp_field) = 'YYYY-MM-DD'` for day queries

---

## Key Architectural Patterns

### Timestamp Fields
All timestamps are ISO 8601 strings: `YYYY-MM-DDTHH:MM:SS`

Common field names:
- `created_at` - When record was created
- `updated_at` - Last modification
- `timestamp` - Generic timestamp
- `executed_at`, `started_at`, `completed_at` - Action timestamps
- `snapshot_at` - State snapshot times

### JSON Fields
Fields ending in `_json` contain JSON data.

Access in SQL: `json_extract(field, '$.path')`
Access in Python: `json.loads(field)`

Common JSON fields:
- `*_json` - Generic JSON blob
- `affect_json` - Emotional affect dimensions
- `needs_json` - Thymos needs register
- `observations_json` - Array of observations
- `context_json` - Contextual metadata

### State Bus Integration
The `state_events` table is the central audit log.

Subscribe to events for real-time updates:
- `session.started`, `session.ended`
- `conversation.message_added`
- `state_delta`
- `insight.gained`
- `need.satisfied`, `need.urgent`

---

## Performance Recommendations

### Pre-Aggregation
Use `source_rollups` table for daily summaries:
```sql
INSERT INTO source_rollups (daemon_id, source_id, rollup_type, rollup_key, metrics_json, computed_at)
VALUES (?, 'activity', 'daily', '2026-02-20', ?, datetime('now'));
```

### Indexes
Key indexes already exist:
- `(daemon_id, created_at)` on most tables
- `(daemon_id, timestamp)` on time-series tables
- Join indexes on foreign keys

### Query Optimization
- Always filter by `daemon_id` first
- Use `date()` function for day filtering
- Join `conversations` table for `daemon_id` on `messages`
- Limit result sets with `LIMIT` for large tables

---

## Missing Data Sources

### Music Compositions
No dedicated table found. Music generation happens via:
- `/home/jaryk/cass/cass-vessel/backend/music/music_client.py`
- ACE-Step integration

**Recommendation**: Add `music_compositions` table to schema.

### System Logs
Error logs and system events not centrally tracked in activity context.

**Recommendation**: Add `system_events` table or include in `state_events`.

### Network Activity
External API calls not logged centrally.

**Recommendation**: Add HTTP middleware logging to `token_usage_records` or new table.

---

## Implementation Path

### Phase 1: Core Timeline
1. Query `state_events` for high-level activity
2. Add queries for top 5 tables (see Quick Start)
3. Build basic chronological timeline view

### Phase 2: Category Views
4. Autonomous actions (grimoire, research, work items)
5. Emotional tracking (thymos snapshots)
6. Self-model changes (observations, opinions, questions)

### Phase 3: Rich Context
7. Creative output (images, art studies)
8. World consumption (articles, RSS)
9. Social interactions (user observations, Discord)
10. Resource usage (token costs)

### Phase 4: Optimization
11. Pre-aggregate into `source_rollups`
12. Add real-time state bus subscription
13. Build caching layer for common queries

---

## Testing Queries

Use these daemon_id and date values for testing:
```bash
# Get current daemon ID
sqlite3 /home/jaryk/cass/cass-vessel/data/cass.db "SELECT id, label FROM daemons;"

# Get date with most activity
sqlite3 /home/jaryk/cass/cass-vessel/data/cass.db \
  "SELECT date(created_at) as day, COUNT(*) as events
   FROM state_events
   WHERE daemon_id = 'cass'
   GROUP BY day
   ORDER BY events DESC
   LIMIT 10;"
```

---

## Questions / Blockers

Contact Kohl or check:
- `/home/jaryk/cass/cass-vessel/backend/CLAUDE.md` - Project context
- `/home/jaryk/cass/cass-vessel/backend/ARCHITECTURE.md` - Module structure
- `/home/jaryk/cass/cass-vessel/backend/database/schema.py` - Full schema

---

## Summary

This inventory maps **all** activity tracking in the Cass Vessel system:

- **10 major activity categories**
- **80+ database tables**
- **200+ queryable fields**
- **Complete SQL query library**

Everything Cass does - from autonomous spell executions to creative image generation to emotional state changes - is tracked and queryable.

The dashboard can show **complete daily activity** including:
- What she thought (observations, opinions, questions)
- What she felt (thymos snapshots, affect changes)
- What she did (spells, research, conversations, creative work)
- What she consumed (articles, RSS, art studies)
- Who she interacted with (messages, user observations, Discord)
- What resources she used (tokens, costs)

**End of README**
