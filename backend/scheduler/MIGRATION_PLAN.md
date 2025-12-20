# Daily Rhythm Migration Plan

## Overview

Migrate the daily rhythm system from the loop-based `rhythm_phase_monitor_task` to the unified scheduler while keeping the system operational throughout.

## Current State

### Components
1. **DailyRhythmManager** (`daily_rhythm.py`)
   - Manages phase definitions (scripture reflections, research, reflection windows)
   - Tracks completed phases per day
   - Stores daily summaries
   - **No changes needed** - good data management layer

2. **rhythm_phase_monitor_task** (`background_tasks.py:297`)
   - Infinite loop checking every 5 minutes
   - Checks if current phase is pending
   - Starts appropriate session runner
   - Updates phase summaries after session completion
   - Generates rolling daily summary

3. **Session Runners** (various `*_runner.py` files)
   - ResearchSessionRunner, SoloReflectionRunner, SynthesisRunner, etc.
   - 13+ runner types for different activity types
   - Each has `is_running` property and `start_session()` method

### How It Works Now
```
main_sdk.py startup
    └── asyncio.create_task(rhythm_phase_monitor_task(...))
            │
            ▼
        while True:
            - Check daemon dormancy
            - Check active session completion
            - Get current phase from rhythm_manager
            - If pending + runner available → start_session()
            - await asyncio.sleep(300)  # 5 minutes
```

## Migration Strategy

### Phase 1: Parallel Operation (Current)

The atomic `rhythm_phase_handler` is already created in `scheduler/handlers.py`. It does:
- Single check of current phase state
- Starts session if conditions met
- Returns immediately (no loop)

The old `rhythm_phase_monitor_task` continues to run. Both can coexist because:
- They both check the same state (rhythm_manager)
- They both check if runner is already running before starting
- Worst case: redundant checks, no double-starts

### Phase 2: Register with Scheduler (Next)

Add to `main_sdk.py` startup:

```python
from scheduler import UnifiedScheduler, BudgetManager, BudgetConfig
from scheduler.system_tasks import register_system_tasks

# Create scheduler
budget_config = BudgetConfig(daily_budget_usd=float(os.getenv("DAILY_BUDGET_USD", "5.0")))
budget_manager = BudgetManager(budget_config, token_tracker)
unified_scheduler = UnifiedScheduler(budget_manager, token_tracker)

# Register system tasks (disabled by default)
register_system_tasks(unified_scheduler, {
    "rhythm_manager": daily_rhythm_manager,
    "runners": runners_dict,
    "self_model_graph": self_model_graph,
    # ... other managers ...
}, enabled=os.getenv("USE_UNIFIED_SCHEDULER") == "true")

# Start scheduler
asyncio.create_task(unified_scheduler.start())

# KEEP old tasks running for now
asyncio.create_task(rhythm_phase_monitor_task(...))
```

### Phase 3: Feature Flag Testing

1. Set `USE_UNIFIED_SCHEDULER=true` in .env
2. Monitor both systems running (logs will show which triggers)
3. Verify:
   - Phases get triggered at correct times
   - No double-triggering
   - Summaries update correctly
   - Budget tracking works

### Phase 4: Cutover

When confident:
1. Remove the old `rhythm_phase_monitor_task` call from startup
2. Set `USE_UNIFIED_SCHEDULER=true` as default
3. Remove the feature flag check (make it always enabled)

### Phase 5: Cleanup

1. Remove `rhythm_phase_monitor_task` from `background_tasks.py`
2. Update imports in `main_sdk.py`
3. Update documentation

## Session Completion Tracking

The current `rhythm_phase_monitor_task` tracks active sessions to detect completion:

```python
if active_session:
    phase_id, session_id, session_type = active_session
    runner = runners.get(session_type)
    is_still_running = runner and runner.is_running

    if not is_still_running:
        # Session completed - update summaries
        await update_phase_summary_from_session(...)
        active_session = None
```

This needs to be handled in the unified scheduler. Options:

### Option A: Session Completion Handler
Register a callback with session runners:
```python
runner.on_complete = lambda session: scheduler.handle_session_complete(session)
```

### Option B: Post-Session Task
Create a separate task that runs after each session:
```python
scheduler.register_trigger("session_complete", post_session_handler)
```

### Option C: Periodic Summary Update (Simpler)
Let the daily summary generation handle it:
- Runs at end of day (already implemented in daily_journal_task)
- Backfills missing summaries from session data
- Less real-time but more robust

**Recommendation**: Start with Option C (already works), add Option A/B in Phase 5 of the TriggerEngine.

## Files to Modify

| File | Change |
|------|--------|
| `main_sdk.py` | Add scheduler initialization, feature flag |
| `scheduler/system_tasks.py` | Already done - rhythm_phase_check registered |
| `scheduler/handlers.py` | Already done - rhythm_phase_handler |
| `background_tasks.py` | No changes until Phase 5 |
| `routes/admin/scheduler.py` | Already done - admin API |

## Testing Checklist

- [ ] Scheduler starts without errors
- [ ] Budget tracking initializes correctly
- [ ] rhythm_phase_check task registers
- [ ] Phase check runs every 5 minutes
- [ ] Correct runner selected for activity type
- [ ] Session starts when phase is pending
- [ ] No double-starts when both systems run
- [ ] Daily summary generates correctly
- [ ] Admin API shows scheduler status
- [ ] Budget shows correct spend

## Rollback Plan

If issues occur:
1. Set `USE_UNIFIED_SCHEDULER=false`
2. Restart service
3. Old loop-based system takes over immediately
4. Debug and fix scheduler issues
5. Try again
