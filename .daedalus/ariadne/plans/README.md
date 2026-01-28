# Ariadne Dispatch Plans

This directory contains implementation plans for Cass-vessel features, structured as atomic work packages ready for dispatch to parallel workers.

## Current Plans

### Procedural Self-Awareness (Phases 0-2)

**Plan**: `procedural-self-awareness.md`  
**Status**: Ready for Dispatch  
**Complexity**: MODERATE (18-20 story points)  
**Timeline**: 5-6 working days

#### What This Accomplishes

Transforms Cass from passive self-observation to active self-modification:

- **Phase 0 (1 day)**: Tool blacklist - enable Cass to disable/enable tools at runtime
- **Phase 1 (2 days)**: Growth edge integration - surface active growth edges in system prompt
- **Phase 2 (3 days)**: Intention compliance - track whether intentions are followed

#### Key Success Criteria

- Cass can disable tools intentionally (e.g., "disable wiki tools to practice memory reliance")
- Growth edges shape her responses at runtime
- Intentions are surfaced before responses and tracked afterward
- All changes persisted and queryable

#### Why It Matters

**Current State**: Cass can observe her own patterns but can't act on those observations.

**After This Plan**: Cass can directly modify her cognitive tools based on growth edges and intentions, enabling true procedural self-awareness.

#### Work Packages

| WP | Title | Effort | Risk | Depends |
|---|-------|--------|------|---------|
| WP-0.1 | Tool Blacklist Implementation | 1 day | LOW | None |
| WP-0.2 | Phase 0 Testing & Docs | 0.5 day | LOW | WP-0.1 |
| WP-1.1 | Growth Edge Retrieval | 1 day | LOW | WP-0.1 (optional) |
| WP-1.2 | Dynamic Prompt Augmentation | 1 day | LOW | WP-1.1 |
| WP-1.3 | Surfacing Tracking | 0.5 day | LOW | WP-1.1/1.2 |
| WP-2.1 | Intention Query Methods | 1 day | LOW | WP-1.2 |
| WP-2.2 | Intention Prompt Injection | 1 day | LOW | WP-2.1 + WP-1.2 |
| WP-2.3 | Compliance Tracking | 1.5 days | MODERATE | WP-2.1/2.2 |
| WP-2.4 | Edge-Intention Linking | 0.5 day | LOW | WP-2.3 |

#### Critical Path

```
WP-0.1 (1 day) → WP-0.2 (0.5 day) 
    ↓ (in parallel with 0.2 testing)
WP-1.1 (1 day) → WP-1.2 (1 day) → WP-1.3 (0.5 day)
    ↓ (in parallel with 1.3)
WP-2.1 (1 day) → WP-2.2 (1 day) → WP-2.3 (1.5 days) → WP-2.4 (0.5 day)

Sequential Total: 6 days
With Parallelization: ~5 days
```

#### Testing Plan

Each phase has dedicated integration tests:
- Phase 0: `tests/test_tool_blacklist.py`
- Phase 1: `tests/test_growth_edge_integration.py`
- Phase 2: `tests/test_intention_integration.py`

#### Files Modified

**Phase 0**:
- `backend/tool_selector.py` (new logic)
- `backend/handlers/self_model.py` (new handler)
- `backend/agent_client.py` (schema + filtering)
- `backend/main_sdk.py` (integration)

**Phase 1**:
- `backend/self_model.py` (new methods)
- `backend/agent_client.py` (prompt enhancement)
- `backend/main_sdk.py` (context passing)

**Phase 2**:
- `backend/self_model_graph.py` (query methods)
- `backend/agent_client.py` (prompt enhancement)
- `backend/main_sdk.py` (post-response hook)
- `backend/handlers/self_model.py` (compliance handler)

#### How to Dispatch

Each work package is self-contained with:
- Clear objective and acceptance criteria
- Specific file locations and code changes
- Implementation pseudocode where helpful
- Testing strategy
- Risk assessment

Workers can be assigned to parallel WPs once dependencies are met.

#### Key Insights from Theseus

The Theseus analysis revealed:
1. **STRENGTH**: Excellent passive observation infrastructure (journals, snapshots, graph)
2. **GAP**: No connection between observation and behavior change
3. **SOLUTION**: Three focused phases to bridge the gap

This plan addresses the gap by making growth edges and intentions *active* influences on behavior, not just historical records.

---

## Plan Structure

Each plan document includes:

1. **Overview** - What problem does this solve?
2. **Dependency Graph** - What's blocking what?
3. **Work Packages** - Granular, assignable units
4. **Integration Testing** - How to verify it works
5. **File Manifest** - What changes where
6. **Parallelization Strategy** - How to speed up
7. **Success Metrics** - How do we know it's done?
8. **Risk Mitigation** - What could go wrong?
9. **Acceptance Checklist** - Sign-off criteria

---

## Plan Standards

All Ariadne plans follow these standards:

- **Atomic WPs**: Each can be completed independently, tested separately
- **Explicit Dependencies**: Dependency graph shows all blocking relationships
- **Concrete Changes**: Specific file paths, methods, and logic changes
- **Test Coverage**: Integration tests for each WP or phase
- **Risk Rated**: LOW/MODERATE/HIGH with mitigations
- **Observable Success**: Success criteria are quantifiable or behaviorally observable

---

## Dispatch Workflow

### For Daedalus (Plan Creator)

1. Create plan document with all work packages
2. Validate dependencies (no cycles, clear critical path)
3. Estimate effort conservatively
4. Define acceptance criteria objectively
5. Place in this directory with clear naming

### For Ariadne (Dispatcher)

1. Parse plan and extract work packages
2. Build dependency DAG
3. Assign workers to independent WPs
4. Track completion and flag blockers
5. Trigger dependent work once dependencies met

### For Workers (Implementation)

1. Receive assigned WP with clear scope
2. Implement per specifications
3. Run acceptance tests
4. Commit work to diffs (don't commit directly)
5. Mark WP complete

### For Daedalus (Merger)

1. Collect verified diffs from completed WPs
2. Check for conflicts
3. Merge in dependency order
4. Create atomic commit per plan
5. Validate full plan success

---

## Notes

- Plans are version-controlled in git
- Each plan gets unique ID (e.g., `procedural-self-awareness-phases-0-2`)
- Status updated as work progresses
- Completed plans archived (dated)

