# Autonomous Scheduler - Tactical Roadmap

**Status**: System 0% operational - needs integration work
**Time to MVP**: 8-12 hours focused work
**Priority**: HIGH - blocking Cass's autonomous capabilities

---

## Quick Start (2-3 hours to first execution)

### 1. Fix Template Execution Paths
**File**: `backend/scheduling/templates.py`
**Problem**: Templates have deprecated `runner_key` set, causing execution to fail
**Fix**:
```python
# For ALL templates in WORK_TEMPLATES dict:
# REMOVE: runner_key="reflection"  (or any runner_key)
# KEEP: action_sequence=["session.reflection"]
# VERIFY: action_sequence is non-empty for all templates
```

### 2. Start the Scheduler
**File**: `backend/main_sdk.py` (around line 1250, after scheduler instantiation)
**Add**:
```python
# After: autonomous_scheduler.set_phase_queue(phase_queue)

# Instantiate day phase tracker
day_phase_tracker = DayPhaseTracker(
    state_bus=global_state_bus,
)

# Wire up phase change callbacks
day_phase_tracker.on_phase_change(autonomous_scheduler.on_phase_changed)
day_phase_tracker.on_phase_change(phase_queue.on_phase_changed)

# Start both background services
await day_phase_tracker.start()
await autonomous_scheduler.start()

logger.info("Autonomous scheduling system started")
```

### 3. Test Minimal Flow
**Terminal**:
```bash
# Restart backend
sudo systemctl restart cass-vessel

# Watch logs for:
# - "Autonomous scheduler started"
# - "DayPhaseTracker starting in phase: {phase}"
# - "Planning the day's autonomous work..."
# - Work units being queued/dispatched

journalctl -u cass-vessel -f | grep -i "autonomous\|phase\|work unit"
```

**Expected**: At least one work unit should execute within first hour of operation.

---

## Phase 1: Core Loop Operational (additional 6-8 hours)

### 4. Create Action Definitions JSON
**File**: `backend/scheduler/actions/definitions.json` (NEW FILE)
**Content**: Define all 30+ actions from `spec/atomic-actions-projection.md`

**Minimal structure**:
```json
{
  "actions": {
    "session.reflection": {
      "id": "session.reflection",
      "name": "Reflection Session",
      "description": "Private contemplation and self-examination",
      "category": "reflection",
      "handler": "session_handlers.reflection_action",
      "estimated_cost_usd": 0.15,
      "default_duration_minutes": 30,
      "priority": "normal",
      "requires_idle": false
    },
    "journal.generate_daily": {
      "id": "journal.generate_daily",
      "name": "Generate Daily Journal",
      "description": "Generate yesterday's journal entry",
      "category": "system",
      "handler": "journal_handlers.generate_daily_action",
      "estimated_cost_usd": 0.10,
      "default_duration_minutes": 15,
      "priority": "high",
      "requires_idle": false
    }
    // ... repeat for all 30+ actions
  }
}
```

**Priority actions to define first**:
- `session.reflection`
- `session.synthesis`
- `journal.generate_daily`
- `memory.summarize_idle_conversations`
- `session.growth_edge`
- `session.curiosity`

### 5. Validate Template Action Sequences
**File**: `backend/scheduling/templates.py` (or new `validation.py`)
**Add**:
```python
def validate_template_actions(templates: Dict[str, WorkUnitTemplate], registry: ActionRegistry) -> List[str]:
    """Validate that all template action sequences reference real actions."""
    errors = []
    for template_id, template in templates.items():
        for action_id in template.action_sequence:
            if not registry.get_definition(action_id):
                errors.append(f"Template '{template_id}' references unknown action: '{action_id}'")
    return errors

# Call at startup in main_sdk.py after action_registry is initialized:
validation_errors = validate_template_actions(WORK_TEMPLATES, action_registry)
if validation_errors:
    for error in validation_errors:
        logger.warning(error)
```

### 6. Test Full Loop
**Verify**:
- [ ] Morning planning triggers automatically
- [ ] Work units appear in phase queues
- [ ] Phase transitions dispatch queued work
- [ ] Actions execute successfully
- [ ] Work summaries are saved
- [ ] Budget is tracked and respected

**Tools**:
```bash
# Check scheduler status
curl http://localhost:8000/admin/scheduler/status | jq

# Check phase queue state
curl http://localhost:8000/admin/scheduler/status | jq '.phase_queue'

# Check budget
curl http://localhost:8000/admin/scheduler/budget | jq
```

---

## Phase 2: Production-Ready (additional 10-12 hours)

### 7. Error Handling
**Files**: `autonomous_scheduler.py`, `phase_queue.py`, `decision_engine.py`
**Add**:
- Try/catch around LLM calls (network failures)
- Graceful degradation on budget exhaustion
- Retry logic for transient failures
- Dead letter queue for failed work units

### 8. Budget Integration Verification
**Verify**:
- Action costs are tracked correctly
- Category budgets are enforced
- Daily budget resets at midnight
- Budget exhaustion stops scheduling

### 9. Admin Dashboard Integration
**File**: `backend/routes/admin/scheduler.py`
**Add endpoints**:
```python
@router.get("/autonomous/status")
async def get_autonomous_status():
    """Get autonomous scheduler state."""
    # Return: current_work, is_enabled, today's plan, work history

@router.get("/autonomous/plan")
async def get_todays_plan():
    """Get today's planned work by phase."""
    # Return: phase -> [work units]

@router.post("/autonomous/trigger/{work_unit_id}")
async def manually_trigger_work(work_unit_id: str):
    """Manually trigger a specific work unit."""
    # For testing/debugging

@router.post("/autonomous/pause")
async def pause_scheduling():
    """Temporarily pause autonomous scheduling."""

@router.post("/autonomous/resume")
async def resume_scheduling():
    """Resume autonomous scheduling."""
```

### 10. Work Summary Improvements
**File**: `autonomous_scheduler.py` (`_generate_work_summary()`)
**Enhance**:
- Extract key insights from action results
- Parse artifacts (journals, wiki pages) and link
- Generate questions raised/addressed
- Better narrative summary generation

### 11. Observability & Metrics
**Add**:
- Prometheus metrics (work units executed, cost per category, etc.)
- Structured logging (JSON logs for parsing)
- Admin dashboard graphs (daily work distribution, budget usage over time)
- Alert on budget exhaustion

---

## Quick Reference: Key Files

| File | Purpose | Status | Action Needed |
|------|---------|--------|---------------|
| `backend/scheduling/autonomous_scheduler.py` | Main orchestrator | Incomplete | Remove session runner stubs |
| `backend/scheduling/templates.py` | Work unit templates | Needs fix | Remove runner_keys |
| `backend/scheduling/decision_engine.py` | Cass decides what to work on | Complete | None |
| `backend/scheduling/phase_queue.py` | Phase-based queuing | Complete | None |
| `backend/scheduling/day_phase.py` | Time-of-day tracking | Complete | None |
| `backend/scheduler/actions/__init__.py` | Action registry | Complete | Create definitions.json |
| `backend/main_sdk.py` | Startup integration | Missing | Add start() calls |

---

## Testing Checklist

### Minimal Viable Test
- [ ] Backend starts without errors
- [ ] Autonomous scheduler logs "started"
- [ ] Day phase tracker logs current phase
- [ ] At least one work unit executes within 1 hour
- [ ] Work summary is saved
- [ ] No critical errors in logs

### Full Integration Test
- [ ] Morning planning triggers automatically
- [ ] Work queued for all 4 phases (morning/afternoon/evening/night)
- [ ] Phase transitions dispatch queued work
- [ ] Multiple work units execute in sequence
- [ ] Budget tracking shows cost deductions
- [ ] Work summaries queryable via API
- [ ] System runs for 24 hours without crashes

### Production Readiness Test
- [ ] Budget exhaustion stops work gracefully
- [ ] LLM call failures are retried
- [ ] Manual pause/resume works
- [ ] Admin dashboard shows real-time state
- [ ] Logs are structured and parseable
- [ ] System runs for 7 days continuously

---

## Common Pitfalls

1. **Action handler not registered**: Check `scheduler/actions/__init__.py` - handler must be in `_register_all_handlers()`

2. **Budget exceeded**: Work won't run if category budget exhausted. Check `/admin/scheduler/budget`

3. **Phase transition not firing**: Verify `day_phase_tracker.start()` was called

4. **Work unit fails silently**: Check work unit status via autonomous scheduler API, look for error in result

5. **LLM context too large**: Decision engine prompts can get big. Monitor token usage, may need to trim context.

---

## Next Steps After MVP

Once core loop is working:
1. Expand action library (Wonderland, creative, research)
2. Improve decision engine (learning from past work)
3. Add approval workflows for certain actions
4. Integrate with goal planning system
5. Multi-day work planning (not just daily)

---

**Last Updated**: 2025-12-24
**Author**: Theseus (Daedalus analysis agent)
