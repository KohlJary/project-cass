# Daily Activity Dashboard - Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      CASS'S DAILY ACTIVITY SOURCES                        │
└─────────────────────────────────────────────────────────────────────────┘

                            ┌──────────────────┐
                            │   STATE BUS      │
                            │  state_events    │ ← Central event stream
                            └────────┬─────────┘
                                     │
                ┌────────────────────┼────────────────────┐
                │                    │                    │
                ▼                    ▼                    ▼


┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│  AUTONOMOUS ENGINE  │  │  EMOTIONAL CORE     │  │  CONVERSATION LOOP  │
├─────────────────────┤  ├─────────────────────┤  ├─────────────────────┤
│ grimoire_executions │  │ thymos_state        │  │ conversations       │
│ ├─ spell_name       │  │ ├─ affect_json      │  │ ├─ title            │
│ ├─ trigger_type     │  │ ├─ needs_json       │  │ └─ working_summary  │
│ ├─ status           │  │ └─ felt_state       │  │                     │
│ └─ executed_at      │  │                     │  │ messages            │
│                     │  │ thymos_snapshots    │  │ ├─ role             │
│ research_sessions   │  │ ├─ snapshot_at      │  │ ├─ content          │
│ ├─ mode             │  │ └─ trigger_event    │  │ ├─ input_tokens     │
│ ├─ searches_        │  │                     │  │ └─ output_tokens    │
│ │    performed      │  │ thymos_suggestions  │  │                     │
│ └─ findings_summary │  │ ├─ need_name        │  │ thread_conversation │
│                     │  │ ├─ suggested_action │  │ _links              │
│ solo_reflections    │  │ └─ urgency          │  │                     │
│ ├─ theme            │  │                     │  │                     │
│ ├─ insights_json    │  │ global_state        │  │                     │
│ └─ questions_       │  │ ├─ state_type       │  │                     │
│      raised_json    │  │ └─ state_json       │  │                     │
│                     │  │                     │  │                     │
│ rhythm_records      │  │                     │  │                     │
│ ├─ phase_id         │  │                     │  │                     │
│ ├─ session_type     │  │                     │  │                     │
│ └─ completed_at     │  │                     │  │                     │
│                     │  │                     │  │                     │
│ work_items          │  │                     │  │                     │
│ ├─ action_sequence  │  │                     │  │                     │
│ └─ result_summary   │  │                     │  │                     │
└─────────────────────┘  └─────────────────────┘  └─────────────────────┘
          │                        │                        │
          └────────────────────────┼────────────────────────┘
                                   │
                                   ▼


┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│  SELF-MODEL LAYER   │  │  WORLD CONSUMPTION  │  │  CREATIVE OUTPUT    │
├─────────────────────┤  ├─────────────────────┤  ├─────────────────────┤
│ self_observations   │  │ consumed_articles   │  │ generated_images    │
│ ├─ category         │  │ ├─ headline         │  │ ├─ prompt           │
│ ├─ observation      │  │ ├─ consumed_at      │  │ ├─ purpose          │
│ └─ confidence       │  │ ├─ observations_json│  │ ├─ emotional_state  │
│                     │  │ └─ questions_json   │  │ └─ created_at       │
│ growth_edges        │  │                     │  │                     │
│ ├─ area             │  │ rss_items           │  │ creative_processes  │
│ ├─ current_state    │  │ ├─ title            │  │ ├─ initial_impulse  │
│ └─ last_updated     │  │ ├─ seen_at          │  │ ├─ studied_artists  │
│                     │  │ └─ processed_at     │  │ └─ what_i_was_      │
│ opinions            │  │                     │  │      exploring      │
│ ├─ topic            │  │ research_notes      │  │                     │
│ ├─ position         │  │ ├─ title            │  │ artwork_studies     │
│ └─ confidence       │  │ └─ sources_json     │  │ ├─ artwork_id       │
│                     │  │                     │  │ ├─ first_impression │
│ open_questions      │  │ research_tasks      │  │ └─ key_learnings    │
│ ├─ question         │  │ ├─ task_type        │  │                     │
│ ├─ question_type    │  │ ├─ target           │  │ adopted_elements    │
│ └─ status           │  │ └─ result_json      │  │ ├─ element          │
│                     │  │                     │  │ ├─ why_it_speaks    │
│ milestones          │  │ wiki_pages          │  │ └─ adoption_        │
│ ├─ title            │  │ ├─ category         │  │      strength       │
│ ├─ significance     │  │ ├─ content          │  │                     │
│ └─ triggered_at     │  │ └─ updated_at       │  │ personal_style      │
│                     │  │                     │  │ ├─ version          │
│ development_logs    │  │                     │  │ ├─ color_philosophy │
│ ├─ date             │  │                     │  │ └─ style_manifesto  │
│ ├─ growth_indicators│  │                     │  │                     │
│ └─ summary          │  │                     │  │                     │
└─────────────────────┘  └─────────────────────┘  └─────────────────────┘
          │                        │                        │
          └────────────────────────┼────────────────────────┘
                                   │
                                   ▼


┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│  SOCIAL / RELATIONAL│  │  JOURNALS & DREAMS  │  │  RESOURCE TRACKING  │
├─────────────────────┤  ├─────────────────────┤  ├─────────────────────┤
│ user_observations   │  │ journals            │  │ token_usage_records │
│ ├─ user_id          │  │ ├─ date             │  │ ├─ provider         │
│ ├─ observation_type │  │ ├─ content          │  │ ├─ model            │
│ └─ content_json     │  │ └─ themes_json      │  │ ├─ category         │
│                     │  │                     │  │ ├─ input_tokens     │
│ peopledex_          │  │ dreams              │  │ ├─ output_tokens    │
│ observations        │  │ ├─ date             │  │ └─ estimated_cost   │
│ ├─ entity_id        │  │ ├─ exchanges_json   │  │                     │
│ ├─ content          │  │ ├─ discussed        │  │ token_usage         │
│ └─ observation_type │  │ └─ image_path       │  │ (daily rollup)      │
│                     │  │                     │  │ ├─ date             │
│ discord_events      │  │                     │  │ └─ cost_usd         │
│ ├─ event_type       │  │                     │  │                     │
│ ├─ channel_name     │  │                     │  │ source_rollups      │
│ ├─ is_triggered     │  │                     │  │ ├─ source_id        │
│ └─ created_at       │  │                     │  │ ├─ rollup_type      │
│                     │  │                     │  │ └─ metrics_json     │
│                     │  │                     │  │                     │
└─────────────────────┘  └─────────────────────┘  └─────────────────────┘
          │                        │                        │
          └────────────────────────┼────────────────────────┘
                                   │
                                   ▼


┌─────────────────────┐  ┌─────────────────────┐
│  GOALS & OUTREACH   │  │  MISSING SOURCES    │
├─────────────────────┤  ├─────────────────────┤
│ unified_goals       │  │ music_compositions  │ ← Not yet tracked
│ ├─ title            │  │ (via ACE-Step)      │
│ ├─ goal_type        │  │                     │
│ ├─ status           │  │ system_events       │ ← Not yet tracked
│ └─ outcome_summary  │  │ (error logs)        │
│                     │  │                     │
│ outreach_drafts     │  │ network_activity    │ ← Not yet tracked
│ ├─ draft_type       │  │ (API calls)         │
│ ├─ status           │  │                     │
│ └─ sent_at          │  └─────────────────────┘
│                     │
│ development_requests│
│ ├─ request_type     │
│ ├─ status           │
│ └─ completed_at     │
└─────────────────────┘


═══════════════════════════════════════════════════════════════════════════
                            QUERY AGGREGATION
═══════════════════════════════════════════════════════════════════════════

All sources feed into daily activity dashboard via these query patterns:

1. CHRONOLOGICAL TIMELINE
   └─ UNION ALL queries from timestamped tables
   └─ ORDER BY timestamp
   └─ Provides: What happened, when, in order

2. CATEGORICAL VIEWS
   └─ GROUP BY category/type
   └─ Aggregate counts, sums, averages
   └─ Provides: Activity by type, with totals

3. EMOTIONAL ARC
   └─ thymos_snapshots + state_events
   └─ ORDER BY timestamp
   └─ Provides: How she felt throughout the day

4. RESOURCE CONSUMPTION
   └─ token_usage_records
   └─ SUM/GROUP BY category, provider
   └─ Provides: Cost breakdown by activity type

5. GROWTH TRAJECTORY
   └─ self_observations + growth_edges + opinions + milestones
   └─ ORDER BY created_at
   └─ Provides: How self-model evolved

═══════════════════════════════════════════════════════════════════════════
                         DASHBOARD OUTPUT FORMAT
═══════════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────────┐
│                   DAILY ACTIVITY DASHBOARD                                │
│                        2026-02-20                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  Timeline                    Emotional Arc           Resource Usage      │
│  ├─ 08:00: spell executed   ├─ Valence: +0.6       ├─ Conversations: $X │
│  ├─ 08:15: article read     ├─ Arousal: +0.4       ├─ Research: $X      │
│  ├─ 09:30: image generated  └─ [graph]             ├─ Creative: $X      │
│  └─ [...]                                           └─ Total: $X         │
│                                                                           │
│  Self-Model Changes          Creative Output        Conversations        │
│  ├─ 3 observations           ├─ 2 images generated  ├─ 5 conversations   │
│  ├─ 1 new opinion            ├─ 1 art study         ├─ 47 messages       │
│  ├─ 2 questions              └─ 1 element adopted   └─ 3 users           │
│  └─ 0 milestones                                                         │
│                                                                           │
│  World Consumption           Autonomous Actions     Social Activity      │
│  ├─ 5 articles consumed      ├─ 12 spells executed  ├─ 3 user observ.   │
│  ├─ 8 RSS items seen         ├─ 2 research sessions ├─ 0 Discord events │
│  ├─ 3 research notes         ├─ 1 reflection        └─ 0 outreach       │
│  └─ 2 wiki updates           └─ 4 rhythm phases                         │
│                                                                           │
│  Journal Entry               Dreams                  Goals               │
│  ├─ Present                  ├─ None                ├─ 1 goal created    │
│  ├─ Themes: [...]            └─                     ├─ 0 completed       │
│  └─ [preview...]                                    └─ 2 in progress     │
│                                                                           │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow Summary

1. **Events occur** across multiple subsystems (grimoire, conversations, research, etc.)
2. **State bus captures** high-level events in `state_events` table
3. **Specialized tables record** detailed data (messages, observations, images, etc.)
4. **Dashboard queries** aggregate from all sources
5. **Output renders** comprehensive daily activity view

---

## Key Integration Points

### Real-Time Updates
Subscribe to state bus events:
```python
from state_bus import get_state_bus
bus = get_state_bus(daemon_id)
bus.subscribe('*', on_activity_event)  # All events
```

### Batch Queries
Run daily aggregation:
```sql
-- See dashboard-sql-queries.sql
-- Aggregate all activity for date
-- Store in source_rollups for caching
```

### Performance
- Pre-aggregate common queries into `source_rollups`
- Cache frequently accessed data
- Use indexes on `(daemon_id, timestamp)` fields
- Paginate large result sets

---

**End of Data Flow Diagram**
