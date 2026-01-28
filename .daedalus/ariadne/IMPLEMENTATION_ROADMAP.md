# Ariadne Implementation Roadmap

**Date**: 2026-01-28  
**Origin**: Theseus analysis of procedural self-awareness gaps  
**Status**: Ready for Dispatch

---

## Executive Summary

I've analyzed the Theseus findings on Cass's self-awareness infrastructure and broken them into **9 concrete work packages** ready for parallel implementation.

**Plan Location**: `.daedalus/ariadne/plans/procedural-self-awareness.md`  
**Summary**: `.daedalus/ariadne/plans/DISPATCH_SUMMARY.md`  
**README**: `.daedalus/ariadne/plans/README.md`

---

## The Path Forward

### What We Found (Theseus Analysis)

Cass has **excellent passive observation systems**:
- Self-observation tracking with versioning
- Opinion formation with disagreement tracking
- Growth edges with current/desired state
- Intention lifecycle management
- Autonomous reflection sessions
- Graph-based self-model with causal tracing

**But**: These are decoupled from behavior. Growth edges are observed, not acted upon.

### What We're Building

Three phases to bridge observation → behavior:

1. **Phase 0 (1 day)**: Tool Blacklist
   - Enable Cass to disable/enable tools intentionally
   - MVP: Global blacklist, auto-expiration
   - Foundation for phases 1-2

2. **Phase 1 (2 days)**: Growth Edge Integration
   - Surface top 3 active edges in system prompt
   - Shape responses at runtime
   - Track edge relevance to conversations

3. **Phase 2 (3 days)**: Intention Compliance
   - Inject intentions pre-response
   - Track outcomes post-response
   - Calculate effectiveness over time

**Total**: 5-6 working days (with parallelization)

---

## Work Package Breakdown

### Phase 0: Tool Blacklist (1 day / 4 story points)

| WP | Task | Effort | Risk |
|---|------|--------|------|
| 0.1.1 | Blacklist logic in tool_selector.py | 2h | LOW |
| 0.1.2 | Modify_tool_access handler | 1.5h | LOW |
| 0.1.3 | Tool schema in agent_client.py | 1h | LOW |
| 0.1.4 | Integration into tool filtering | 1h | LOW |
| 0.2 | Testing & documentation | 1.5h | LOW |

**Key Files**:
- `backend/tool_selector.py` (new)
- `backend/handlers/self_model.py` (modify)
- `backend/agent_client.py` (modify)
- `backend/main_sdk.py` (modify)

### Phase 1: Growth Edge Integration (2 days / 8 story points)

| WP | Task | Effort | Risk |
|---|------|--------|------|
| 1.1.1 | get_active_growth_edges() method | 3h | LOW |
| 1.1.2 | format_growth_edges_for_prompt() | 2h | LOW |
| 1.1.3 | Testing edge retrieval | 1h | LOW |
| 1.2.1 | Modify _build_system_prompt() | 3h | LOW |
| 1.2.2 | Update main_sdk.py context | 2h | LOW |
| 1.2.3 | Testing prompt injection | 1.5h | LOW |
| 1.3.1 | surface_growth_edge() method | 1.5h | LOW |
| 1.3.2 | note_growth_edge_active tool | 1h | LOW |

**Key Files**:
- `backend/self_model.py` (modify)
- `backend/agent_client.py` (modify)
- `backend/main_sdk.py` (modify)

### Phase 2: Intention Compliance (3 days / 10 story points)

| WP | Task | Effort | Risk |
|---|------|--------|------|
| 2.1.1 | get_active_intentions() method | 3h | LOW |
| 2.1.2 | format_intentions_for_prompt() | 2h | LOW |
| 2.1.3 | Testing intention retrieval | 1h | LOW |
| 2.2.1 | Enhance _build_system_prompt() | 3h | LOW |
| 2.2.2 | Update main_sdk.py context | 2h | LOW |
| 2.2.3 | Testing intention injection | 1.5h | LOW |
| 2.3.1 | Post-response hook in main_sdk.py | 2h | MODERATE |
| 2.3.2 | evaluate_intention_compliance tool | 2h | LOW |
| 2.3.3 | Effectiveness scoring | 2h | LOW |
| 2.3.4 | Testing compliance tracking | 1.5h | LOW |
| 2.4.1 | Link intentions to growth edges | 1h | LOW |

**Key Files**:
- `backend/self_model_graph.py` (modify)
- `backend/agent_client.py` (modify)
- `backend/main_sdk.py` (modify)
- `backend/handlers/self_model.py` (modify)

---

## How to Proceed

### Step 1: Review

**Kohl should**:
1. Read DISPATCH_SUMMARY.md (15 min) - high-level overview
2. Skim procedural-self-awareness.md (30 min) - detailed work packages
3. Decide: Proceed? Any changes? Timeline constraints?

### Step 2: Dispatch

**Ariadne should**:
1. Extract 9 work packages from main plan
2. Build dependency DAG
3. Identify parallelization opportunities
4. Assign workers to independent WPs
5. Track completion via diffs

### Step 3: Implement

**Workers should**:
1. Receive assigned WP with full context
2. Implement per specifications
3. Run acceptance tests locally
4. Submit diffs (don't commit to main)
5. Mark WP complete

### Step 4: Integrate

**Daedalus should**:
1. Collect verified diffs from completed WPs
2. Check for conflicts
3. Merge in dependency order
4. Run full integration tests
5. Create atomic commit for plan

---

## Success Criteria

### Quantitative
- All 9 WPs completed per acceptance criteria
- All tests passing (Phase 0, 1, 2 test suites)
- Zero breaking changes to existing functionality
- Token overhead < 200 tokens per phase

### Qualitative
- Cass can disable tools intentionally
- Cass observes growth edges shaping her responses
- Cass tracks intention compliance
- Observable procedural self-modification

### Behavioral
- Cass uses modify_tool_access intentionally (not just testing)
- Cass mentions growth edges in conversations
- Cass evaluates intention compliance
- Cass runs self-directed experiments

---

## Risk Summary

### Overall: LOW

**Technical Risks**:
- Token overflow: MODERATE → Mitigate with strict limits
- Performance: MODERATE → Mitigate with caching
- Blacklist leaks: LOW → Mitigate with scoping in Phase 3

**Conceptual Risks**:
- Over-constraint: LOW → Edges/intentions are aspirational
- Spiral: LOW → All changes logged with reasoning

All mitigations documented in main plan.

---

## Timeline

### Sequential (No Parallelization)
```
Phase 0 implementation: 1 day
Phase 0 testing: 0.5 day
Phase 1 implementation: 2 days
Phase 1 testing: 0.5 day
Phase 2 implementation: 3 days
Phase 2 testing: 0.5 day
Integration & validation: 1 day
Total: 8-9 days
```

### With Parallelization (2-3 Workers)
```
Phase 0 impl + testing: 1.5 days
    ↓ (parallel)
Phase 1 impl + testing: 2 days
    ↓ (parallel)
Phase 2 impl + testing: 3 days
    ↓
Integration & validation: 1 day
Total: 5-6 days
```

---

## Files Generated

### Plans (Ready for Dispatch)

- **procedural-self-awareness.md** (30KB, 965 lines)
  - 9 work packages with detailed specifications
  - Dependency graph
  - Integration testing plan
  - File manifest
  - Acceptance checklists

- **DISPATCH_SUMMARY.md** (12KB, 428 lines)
  - Executive summary for decision makers
  - Phase explanations with examples
  - Risk profile & mitigations
  - Success metrics
  - Timeline breakdown

- **README.md** (5.8KB, 181 lines)
  - Plan directory standards
  - Dispatch workflow
  - How to use plans

---

## Integration with Existing Systems

### Fits Within Current Architecture

- Builds on existing SelfManager
- Extends existing growth edge system
- Uses existing self_model_graph
- Leverages existing prompt building
- No new external dependencies

### Non-Breaking Changes

- All additions are optional parameters
- Existing code paths unchanged
- Graceful fallback if new systems unavailable
- Can be disabled without affecting other features

### Minimal File Surface

Only 4-5 core files modified:
- tool_selector.py
- handlers/self_model.py
- agent_client.py
- main_sdk.py
- self_model_graph.py

---

## Next Steps

1. **Kohl**: Review summaries, approve or iterate
2. **Ariadne**: Dispatch work packages to workers
3. **Workers**: Implement parallel WPs
4. **Daedalus**: Merge diffs, validate plan
5. **Cass**: Test procedural self-awareness capabilities

---

## Questions?

Full plan documentation available at:
- `.daedalus/ariadne/plans/procedural-self-awareness.md`
- `.daedalus/ariadne/plans/DISPATCH_SUMMARY.md`
- `.daedalus/ariadne/plans/README.md`

