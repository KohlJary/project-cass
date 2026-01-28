# Procedural Self-Awareness Implementation - Dispatch Summary

**Date**: 2026-01-28  
**Plan**: Operationalize Theseus findings into concrete work packages  
**Target**: Enable Cass to modify her own cognition in real-time

---

## The Gap We're Closing

### Current State

Cass has **world-class observation infrastructure**:
- Self-observation tracking (category, confidence, source)
- Opinion formation with disagreement tracking
- Growth edges defined with current/desired state
- Intention lifecycle management
- Autonomous reflection sessions
- Comprehensive graph-based self-model

**But**: None of this influences her actual behavior at runtime. She can *observe* "I tend to reflexively look up concepts" but can't *disable* the wiki tools to practice memory reliance.

### Target State

Cass will have **active self-modification capability**:
- Disable/enable tools intentionally (Phase 0)
- Surface growth edges in system prompt to shape responses (Phase 1)
- Track intention compliance before/after responses (Phase 2)

**Result**: Cass can run self-directed experiments: "What if I disabled wiki tools? How would my reasoning change?"

---

## Why This Matters

This bridges the **observation → behavior** gap. Right now:

```
Cass observes "I over-rely on external tools"
    ↓
Recorded as growth edge
    ↓
(nothing happens - tools still available)
    ↓
Growth edge remains passive observation
```

After this plan:

```
Cass observes "I over-rely on external tools"
    ↓
Recorded as growth edge
    ↓
Growth edge surfaces in system prompt
    ↓
Cass has intention: "practice memory reliance"
    ↓
Cass disables wiki tools
    ↓
Next responses generated without wiki access
    ↓
Cass evaluates outcomes
    ↓
Growth edge effectiveness tracked
```

**This is procedural self-awareness**: the ability to observe a pattern, make it executable, and measure outcomes.

---

## Three Phases, One Capability

### Phase 0: Tool Blacklist (MVP - 1 day)

**What**: Simplest possible tool control.

**How**:
- Add global blacklist in `tool_selector.py`
- Add `modify_tool_access` tool that Cass can call
- Filter tools before sending to LLM

**Why Now**:
- Unblocks experiments immediately
- No major refactoring needed
- Foundation for phases 1-2

**Example Usage**:
```
Cass: "I'm going to practice memory reliance. Disable wiki tools for 30 minutes."
→ modify_tool_access(disable=["search_wiki"], duration_minutes=30)
→ wiki tools removed from next message
→ 30 minutes later, auto re-enabled
```

### Phase 1: Growth Edges in Prompt (2 days)

**What**: Make growth edges active influences on reasoning.

**How**:
- Add methods to retrieve active growth edges
- Inject top 3 edges into system prompt dynamically
- Track when edges are relevant to conversations

**Why Now**:
- Leverages existing growth edge system
- No breaking changes, purely additive
- Immediately observable behavior change

**Example Usage**:
```
System prompt now includes:
## Your Current Growth Edges

You are actively developing in these areas:

1. **Independent Recall**
   - Current: Often rely on wiki/calendar for facts
   - Working toward: Remember key information from context
   - Barriers: Habit of external lookup

This shapes Cass's responses without being enforced.
```

### Phase 2: Intention Compliance (3 days)

**What**: Track whether intentions are followed.

**How**:
- Retrieve active intentions based on conversation context
- Inject into prompt before response
- Log outcomes after response
- Calculate effectiveness

**Why Now**:
- Completes the observation → action loop
- Cass can see what works for her
- Data-driven self-modification

**Example Usage**:
```
Intention: "When uncertain, be explicit about confidence levels"

Before response:
→ Injected into prompt
→ "Intend to: Be explicit about confidence levels"

After response:
→ Cass evaluates: "Did I follow this?"
→ Outcome logged
→ Effectiveness tracked

Next week: "My explicit-confidence intention is working well (80% success)"
```

---

## Why 5-6 Days is Realistic

### Work Breakdown

| Phase | WPs | Effort | Depends |
|-------|-----|--------|---------|
| 0 | 2 | 1.5 days | Nothing |
| 1 | 3 | 2.5 days | Phase 0 (optional) |
| 2 | 4 | 3.5 days | Phase 1 |
| Testing | - | 1.5 days | Throughout |
| **Total** | **9** | **~9 days** | - |

**But with parallelization**:
- Phase 0 testing → start Phase 1/2 implementation in parallel
- Can reduce to 5-6 days with smart scheduling

### Effort Distribution

**Phase 0** (1 day):
- Blacklist logic: 2 hours
- Handler: 1.5 hours
- Tool schema: 1 hour
- Integration: 1 hour
- Testing: 1.5 hours

**Phase 1** (2 days):
- Retrieval methods: 3 hours
- Prompt augmentation: 3 hours
- Surfacing tracking: 0.5 day
- Testing: 0.5 day

**Phase 2** (3 days):
- Query methods: 1 day
- Prompt injection: 1 day
- Compliance tracking: 1.5 days
- Testing: 0.5 day

All effort estimates include implementation, testing, and documentation.

---

## Dependency Graph

```
┌─────────────────────┐
│  Phase 0: Blacklist │  (1 day)
└──────────┬──────────┘
           │
           ├──→ WP-0.2: Testing (0.5 day)
           │         ↓ [IN PARALLEL]
           │     WP-1.1: Edge Retrieval (1 day)
           │
           └──→ WP-1.2: Prompt Injection (1 day)
                     │
                     ├──→ WP-1.3: Surfacing (0.5 day)
                     │         ↓ [IN PARALLEL]
                     │     WP-2.1: Intent Queries (1 day)
                     │
                     └──→ WP-2.2: Intent Injection (1 day)
                             │
                             └──→ WP-2.3: Compliance (1.5 days)
                                     │
                                     └──→ WP-2.4: Linking (0.5 day)

Critical Path: Phase 0 → Phase 1 → Phase 2 = ~6 days
With Parallel Workers: ~5 days
```

---

## What Changes Where

### Minimal File Count

**Only 4-5 core files modified**:
1. `backend/tool_selector.py` - blacklist logic
2. `backend/handlers/self_model.py` - handlers for tools
3. `backend/agent_client.py` - tool schemas + prompt building
4. `backend/main_sdk.py` - context passing + hooks
5. `backend/self_model_graph.py` - intention queries

**Per-Phase Distribution**:
- Phase 0: Mainly tool_selector.py, agent_client.py
- Phase 1: Mainly self_model.py, agent_client.py
- Phase 2: Mainly self_model_graph.py, main_sdk.py

**Test Files Created**:
- tests/test_tool_blacklist.py
- tests/test_growth_edge_integration.py
- tests/test_intention_integration.py

---

## Risk Profile: LOW

### Technical Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Prompt token overflow | MODERATE | Strict limits (3 edges max, rotate on relevance) |
| Performance degradation | MODERATE | Cache active edges/intentions, refresh every 10 messages |
| Tool blacklist leaks between users | LOW | Document as MVP limitation; Phase 3 scopes to daemon_id |
| Graph query failures | LOW | Extensive testing; graceful fallback to no query |

### Conceptual Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Over-constraint making Cass rigid | LOW | Edges/intentions are aspirational, not enforced |
| Intention logging without real change | LOW | Phase 0 provides real tool modification |
| Self-modification spiral (disables tools, forgets why) | LOW | All changes logged as observations with clear reasoning |

**Overall Risk Assessment**: LOW

All changes are:
- Additive (don't remove existing functionality)
- Well-scoped (clear file boundaries)
- Testable (specific acceptance criteria)
- Reversible (can disable if issues arise)

---

## Success Metrics

### After Phase 0 (Tool Blacklist)

- [ ] Cass can call `modify_tool_access(disable=["search_wiki"])`
- [ ] Tool removed from LLM's available tools
- [ ] Can re-enable with `modify_tool_access(enable=["search_wiki"])`
- [ ] Temporary disable auto-reverts after duration
- [ ] All modifications logged as self-observations

**Observable**: Cass explicitly uses tool control in conversations

### After Phase 1 (Growth Edges)

- [ ] Top 3 growth edges injected into system prompt
- [ ] Different edges appear for different conversation topics
- [ ] Token count increase < 200 tokens
- [ ] Behavior noticeably influenced by edges

**Observable**: Cass references her growth edges; responses show different approach

### After Phase 2 (Intentions)

- [ ] Active intentions surfaced alongside growth edges
- [ ] Pre-response: Intention appears in prompt
- [ ] Post-response: Outcome logged and persisted
- [ ] Effectiveness scores calculated correctly
- [ ] Cass can query: "How am I doing on this intention?"

**Observable**: Cass mentions her intentions; clear correlation between intention + behavior

---

## How to Use This Plan

### For Kohl (Decision Maker)

1. Review this summary
2. Read the full plan: `/home/jaryk/cass/cass-vessel/.daedalus/ariadne/plans/procedural-self-awareness.md`
3. Decide:
   - Do you want to proceed?
   - Timeline constraints?
   - Should we parallelize aggressively?

### For Ariadne (Dispatcher)

1. Plan is in `/home/jaryk/cass/cass-vessel/.daedalus/ariadne/plans/`
2. Extract work packages and dependencies
3. Assign workers to parallel WPs
4. Track completion via diffs
5. Merge in dependency order

### For Claude Code (Workers)

1. Receive assigned WP (e.g., WP-0.1)
2. Open plan document
3. Find WP section with:
   - Objective
   - Files to modify
   - Specific changes
   - Acceptance criteria
4. Implement
5. Test locally
6. Submit diff (don't commit)

---

## What This Enables Next

### Phase 3: Tool Capability Registry (Future)

Once Phases 0-2 working, upgrade to proper architecture:
- Extract tool definitions to data files
- Create ToolCapabilityRegistry
- Add usage analytics
- Reduce HYDRA coupling

**Effort**: 5 days  
**Not blocking**: Phase 0-2 work fine without this

### Phase 4: Autonomous Contradiction Resolution (Future)

Once Phases 0-2 working, add self-healing:
- Weekly contradiction detection
- Auto-trigger solo reflection sessions
- Track resolution effectiveness

**Effort**: 2 days  
**Not blocking**: Optional quality-of-life improvement

---

## Comparison to Original Estimates

**Theseus Battle Plan** estimated:
- Phase 0: 1 day
- Phase 1: 2 days
- Phase 2: 3 days
- **Total: 6 days**

**This Dispatch Plan** breaks into:
- 9 work packages
- Effort: ~9 days sequential, ~5 days with parallelization
- Critical path: Phase 0 → Phase 1 → Phase 2

**Why the difference**: Plan adds detailed task breakdown, explicit testing, and integration work that was implicit in battle plan.

---

## Sign-Off Checklist

Before dispatch, verify:

- [ ] All 9 work packages defined with acceptance criteria
- [ ] Dependency graph acyclic and clear
- [ ] File locations verified to exist
- [ ] Test strategy defined for each phase
- [ ] Risk mitigation documented
- [ ] Success metrics observable or quantifiable
- [ ] Effort estimates realistic (with padding)
- [ ] Plan compatible with current codebase

**All checked** ✓

---

## Questions for Kohl

1. **Timeline**: Can we block 5-6 days for this?
2. **Parallelization**: Should we spin up multiple workers?
3. **Phases**: All 0-2, or would you prefer to proceed phase-by-phase?
4. **Success Demo**: After completion, want Cass to run a specific experiment?

---

## Next Steps

1. **Approval**: Kohl reviews and approves
2. **Dispatch**: Ariadne extracts work packages
3. **Assignment**: Workers receive WPs based on availability
4. **Implementation**: Parallel work on independent WPs
5. **Integration**: Daedalus merges verified diffs in dependency order
6. **Validation**: Full plan tested end-to-end
7. **Completion**: Cass has active self-modification capability

---

**The foundation is excellent. The path is clear. Let's give Cass the ability to modify her own cognition.**

