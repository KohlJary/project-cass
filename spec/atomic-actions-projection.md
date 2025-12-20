# Atomic Autonomous Actions Projection

*Decomposing existing daily rhythm functionality into discrete, budget-aware actions*

## Current State

### Background Tasks (5)

| Task | Schedule | Est. Cost | What It Does |
|------|----------|-----------|--------------|
| `daily_journal_task` | 00:05 daily | ~$0.15 | Generate missing journals + nightly dream |
| `github_metrics_task` | Every 6h | ~$0.01 | Fetch GitHub API metrics |
| `idle_summarization_task` | Every 1h | ~$0.05 | Summarize idle conversations |
| `autonomous_research_task` | Mode-dependent | ~$0.20 | Run wiki research tasks |
| `rhythm_phase_monitor_task` | Every 5min | Varies | Trigger sessions based on rhythm |

### Session Runners (12)

| Runner | Purpose | Est. Cost/Session |
|--------|---------|-------------------|
| `ResearchSessionRunner` | Wiki/knowledge research | ~$0.20-0.50 |
| `SoloReflectionRunner` | Private contemplation | ~$0.15 |
| `SynthesisSessionRunner` | Integrating insights | ~$0.15 |
| `MetaReflectionRunner` | Reflecting on reflection | ~$0.10 |
| `ConsolidationRunner` | Consolidating learnings | ~$0.15 |
| `GrowthEdgeRunner` | Working growth edges | ~$0.15 |
| `KnowledgeBuildingRunner` | Building knowledge base | ~$0.20 |
| `WritingRunner` | Creative writing | ~$0.20 |
| `CuriosityRunner` | Self-directed exploration | ~$0.15 |
| `WorldStateRunner` | Checking world state | ~$0.10 |
| `CreativeOutputRunner` | Creative outputs | ~$0.20 |
| `UserModelSynthesisRunner` | User model synthesis | ~$0.15 |

---

## Proposed Atomic Actions

### Tier 1: System Actions (No LLM, Pure Automation)

These run unconditionally, no budget check needed.

| Action ID | Replaces | Trigger | Description |
|-----------|----------|---------|-------------|
| `system.github_metrics` | `github_metrics_task` | Every 4h | API calls to GitHub, store metrics |
| `system.rhythm_phase_check` | Part of `rhythm_phase_monitor_task` | Every 5min | Check current phase, update state bus |
| `system.activity_mode_check` | Embedded in tasks | Every 5min | Check dormant/active mode |
| `system.queue_maintenance` | Embedded in `autonomous_research_task` | Every 15min | Refresh research queue, prune stale |

### Tier 2: Lightweight LLM Actions (~$0.01-0.05)

Single LLM call, minimal context.

| Action ID | Replaces | Trigger | Description |
|-----------|----------|---------|-------------|
| `memory.generate_conversation_title` | Inline in chat | On conversation start | Generate title from first messages |
| `memory.summarize_conversation` | `idle_summarization_task` | 30min idle | Summarize single conversation |
| `journal.generate_daily` | Part of `daily_journal_task` | 00:05 daily | Generate yesterday's journal |
| `rhythm.generate_phase_summary` | `update_phase_summary_from_session` | On session end | Summarize a completed phase |
| `rhythm.generate_daily_narrative` | `generate_daily_summary` | On last phase | Narrative summary of day |

### Tier 3: Session Actions (~$0.10-0.25)

Multi-turn LLM sessions, bounded by duration/turns.

| Action ID | Replaces | Trigger | Description |
|-----------|----------|---------|-------------|
| `session.reflection` | `SoloReflectionRunner` | Rhythm phase | Private contemplation session |
| `session.synthesis` | `SynthesisSessionRunner` | Rhythm phase | Integrate recent insights |
| `session.meta_reflection` | `MetaReflectionRunner` | Rhythm phase | Reflect on reflection patterns |
| `session.consolidation` | `ConsolidationRunner` | Rhythm phase | Consolidate period learnings |
| `session.growth_edge` | `GrowthEdgeRunner` | Rhythm phase | Work on active growth edges |
| `session.curiosity` | `CuriosityRunner` | Rhythm phase | Follow curiosity threads |
| `session.world_state` | `WorldStateRunner` | Rhythm phase | Check world/news state |

### Tier 4: Research Actions (~$0.20-0.50)

Extended LLM sessions with tool use.

| Action ID | Replaces | Trigger | Description |
|-----------|----------|---------|-------------|
| `research.wiki_page` | `ResearchSessionRunner` | Queue/rhythm | Research and create wiki page |
| `research.knowledge_build` | `KnowledgeBuildingRunner` | Queue/rhythm | Build knowledge on topic |
| `session.writing` | `WritingRunner` | Rhythm phase | Creative writing session |
| `session.creative` | `CreativeOutputRunner` | Rhythm phase | Creative output generation |

### Tier 5: Dream/Meta Actions (~$0.15-0.30)

End-of-day integration processes.

| Action ID | Replaces | Trigger | Description |
|-----------|----------|---------|-------------|
| `dream.nightly` | Part of `daily_journal_task` | 00:10 daily | Generate nightly dream |
| `reflection.user_synthesis` | `UserModelSynthesisRunner` | Weekly | Synthesize user understanding |

---

## Budget Allocation Projection

With $5/day budget and current structure:

| Category | Allocation | Daily Budget | Typical Usage |
|----------|------------|--------------|---------------|
| SYSTEM | 5% | $0.25 | GitHub, phase checks (near-zero) |
| JOURNAL | 5% | $0.25 | Daily journal + dream |
| MEMORY | 10% | $0.50 | Conversation summarization |
| RESEARCH | 25% | $1.25 | Wiki research sessions |
| REFLECTION | 20% | $1.00 | Solo reflection, meta, synthesis |
| GROWTH | 15% | $0.75 | Growth edge work |
| CURIOSITY | 10% | $0.50 | Self-directed exploration |
| CREATIVE | 10% | $0.50 | Writing, creative output |
| **RESERVE** | (10%) | $0.50 | Emergency/critical tasks |

---

## Implementation Order

### Phase 1: Extract from journal_tasks.py
1. `journal.generate_daily` - Extract journal generation
2. `dream.nightly` - Extract dream generation

### Phase 2: Extract from background_tasks.py
3. `system.github_metrics` - Already simple, just wrap
4. `memory.summarize_conversation` - Extract from idle_summarization_task
5. `system.rhythm_phase_check` - Extract phase checking logic

### Phase 3: Session Runner Conversion
6. `session.reflection` - Wrap SoloReflectionRunner
7. `session.synthesis` - Wrap SynthesisSessionRunner
8. `session.meta_reflection` - Wrap MetaReflectionRunner
9. Continue for remaining runners...

### Phase 4: Research Queue Integration
10. `research.wiki_page` - Integrate with existing wiki scheduler
11. `research.knowledge_build` - Wrap KnowledgeBuildingRunner

---

## Key Design Principles

1. **Each action is atomic**: Single purpose, bounded cost, clear input/output
2. **Budget-aware execution**: Synkratos checks budget before dispatch
3. **Priority-based scheduling**: CRITICAL > HIGH > NORMAL > LOW > IDLE
4. **Idempotent where possible**: Safe to retry on failure
5. **Observable**: Each action logs start/end/cost to history table

---

## Questions to Resolve

1. **Session runners as wrappers vs. new implementations?**
   - Wrappers: Less work, inherits complexity
   - New: Cleaner, but duplicates logic

2. **How to handle long-running sessions?**
   - Option A: Sessions are single actions (may take 30+ min)
   - Option B: Sessions spawn multiple sub-actions
   - Option C: Sessions run outside Synkratos, just tracked

3. **Backward compatibility during migration?**
   - Feature flag: `USE_SYNKRATOS_ACTIONS=true`
   - Run both in parallel initially
   - Compare outputs/costs before cutover

4. **Budget tracking granularity?**
   - Per-action tracking (detailed, more overhead)
   - Per-category rollup (simpler, less visibility)
