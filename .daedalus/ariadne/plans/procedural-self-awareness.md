# Procedural Self-Awareness Implementation Plan

**Plan ID**: `procedural-self-awareness-phases-0-2`  
**Generated**: 2026-01-28  
**Status**: Ready for Dispatch  
**Target Completion**: 6 working days  
**Complexity**: MODERATE (18-20 story points)

## Overview

Transform Cass from **passive self-observation** to **active self-modification**. This plan operationalizes Phases 0-2 from the Theseus battle plan, enabling Cass to:

1. **Observe** her cognition (already works well)
2. **Modify** her tool availability (Phase 0 - NEW)
3. **Surface** growth edges in real-time (Phase 1 - NEW)
4. **Enforce** intentions during response generation (Phase 2 - NEW)

**Success Criteria**: Cass can disable tools, surface growth edges shape behavior, and track intention compliance.

---

## Dependency Graph

```
Phase 0: Tool Blacklist (1 day)
  ├── No external dependencies
  └── Creates foundation for Phase 1-2

Phase 1: Growth Edge Integration (2 days)
  ├── Depends on: Phase 0 ✓
  └── Can start in parallel with Phase 0 implementation

Phase 2: Intention Compliance (3 days)
  ├── Depends on: Phase 1 (growth edge surfacing)
  └── Can partially parallelize with Phase 1

Critical Path: Phase 0 → Phase 1 → Phase 2 = 6 days sequential
With Parallelization: ~5 days (Phase 1 & 2 overlap possible)
```

---

## Work Packages

### WP-0.1: Tool Blacklist Implementation (1 day)

**Objective**: Enable basic tool control without major refactoring.

**Complexity**: LOW  
**Effort**: 1 day / 4 story points  
**Risk**: LOW

#### Tasks

**0.1.1 - Create tool selector modifications** (2 hours)

**File**: `/home/jaryk/cass/cass-vessel/backend/tool_selector.py`

**Changes**:
- Add module-level `_tool_blacklist: Set[str]` and `_blacklist_expirations: Dict[str, datetime]`
- Implement `set_tool_blacklist(disabled_tools: List[str], duration_minutes: Optional[int])`
- Implement `clear_tool_blacklist(tools: Optional[List[str]])`
- Implement `check_blacklist_expirations()` - remove expired entries
- Implement `is_tool_blacklisted(tool_name: str) -> bool`

**Acceptance Criteria**:
- [ ] All 5 functions implemented and tested
- [ ] Blacklist persists across message calls
- [ ] Expiration logic works correctly
- [ ] No tools removed from schema when blacklisted

**0.1.2 - Add modify_tool_access handler** (1.5 hours)

**File**: `/home/jaryk/cass/cass-vessel/backend/handlers/self_model.py`

**Changes**:
- Add `_handle_modify_tool_access(tool_input: Dict, ctx: ToolContext)` function
- Extract disable/enable lists and duration from tool_input
- Call `set_tool_blacklist` and `clear_tool_blacklist`
- Log modification as self-observation (category: "pattern")
- Return success status and current blacklist state

**Acceptance Criteria**:
- [ ] Handler signature matches existing handlers
- [ ] Modifications logged as observations
- [ ] Context updates reflected in returned state
- [ ] Error handling for invalid tool names

**0.1.3 - Add tool schema** (1 hour)

**File**: `/home/jaryk/cass/cass-vessel/backend/agent_client.py`

**Changes**:
- Add `modify_tool_access` to tools list (around line 800+)
- Schema includes:
  - `disable[]`: Array of tool names to blacklist
  - `enable[]`: Array of tool names to whitelist
  - `duration_minutes`: Optional auto-revert duration
  - `reason`: Required string explaining the change

**Acceptance Criteria**:
- [ ] Schema matches Anthropic format
- [ ] All required fields properly defined
- [ ] Description explains connection to growth edges/intentions
- [ ] Tool appears in LLM response options

**0.1.4 - Integrate blacklist into tool filtering** (1 hour)

**File**: `/home/jaryk/cass/cass-vessel/backend/agent_client.py` and/or `main_sdk.py`

**Changes**:
- Find where tools are prepared for LLM (typically `get_enabled_tools()` or similar)
- Import `is_tool_blacklisted` from `tool_selector`
- Filter enabled_tools list: exclude any where `is_tool_blacklisted(tool['name'])` returns True
- Ensure filtering happens before caching (if using prompt caching)

**Acceptance Criteria**:
- [ ] Blacklisted tools excluded from LLM tool list
- [ ] Filtering happens on every message (checks expirations)
- [ ] Non-blacklisted tools unaffected
- [ ] Integration testing passes

---

### WP-0.2: Phase 0 Testing & Documentation (0.5 days)

**Objective**: Verify tool blacklist works end-to-end.

**Complexity**: LOW  
**Effort**: 0.5 day / 2 story points

**Tasks**:

**0.2.1 - Manual testing**
- Test disabling single tool
- Verify tool not in next message's available tools
- Test temporary disable with duration
- Verify auto re-enable after duration
- Test manual re-enable
- Test multiple tools disabled simultaneously

**0.2.2 - Integration testing**
- Verify no side effects on other tool calls
- Verify blacklist doesn't persist across server restart (unless persisted in graph)
- Test with multiple concurrent messages

**0.2.3 - Documentation**
- Document the Phase 0 MVP approach
- Note this will be replaced by full capability registry in Phase 3
- Add usage examples to comments

**Acceptance Criteria**:
- [ ] All manual tests pass
- [ ] Integration tests pass
- [ ] Documentation complete
- [ ] Ready to handoff to Phase 1

---

### WP-1.1: Growth Edge Retrieval Enhancement (1 day)

**Objective**: Create methods to retrieve and format active growth edges for runtime use.

**Complexity**: LOW  
**Effort**: 1 day / 4 story points  
**Risk**: LOW

**Depends on**: WP-0.1 (foundation only, not blocking)

#### Tasks

**1.1.1 - Add get_active_growth_edges method** (3 hours)

**File**: `/home/jaryk/cass/cass-vessel/backend/self_model.py`

**Changes**:
- Add method: `get_active_growth_edges(top_n: int = 3, query: Optional[str] = None) -> List[GrowthEdge]`
- Uses existing `get_weighted_growth_edges()` function
- Parameters:
  - `top_n`: Limit results (default 3 to avoid prompt bloat)
  - `query`: Optional text for semantic matching to current conversation
- Returns: Sorted list of active growth edges

**Implementation**:
- Call existing `get_profile()` to get profile with growth edges
- Call `get_weighted_growth_edges()` with:
  - `recency_bias=0.5` (prefer recently touched)
  - `recency_halflife_days=7.0`
  - Pass query if provided
  - Pass embedder for semantic matching
- Return top N edges

**Acceptance Criteria**:
- [ ] Method signature correct
- [ ] Returns empty list if no edges defined
- [ ] Weighted scoring works correctly
- [ ] Semantic matching optional and optional
- [ ] Edges returned in relevance order

**1.1.2 - Add format_growth_edges_for_prompt method** (2 hours)

**File**: `/home/jaryk/cass/cass-vessel/backend/self_model.py`

**Changes**:
- Add method: `format_growth_edges_for_prompt(edges: List[GrowthEdge]) -> str`
- Formats edges as markdown for system prompt injection
- Output format:
  ```
  ## Your Current Growth Edges
  
  You are actively developing in these areas:
  
  1. **area_name**
     - Current: current_state
     - Working toward: desired_state
     - Barriers: barrier1, barrier2
  
  Keep these edges in mind - they represent what you're working to develop.
  ```
- Return empty string if no edges

**Acceptance Criteria**:
- [ ] Returns valid markdown
- [ ] All edge fields included
- [ ] Empty edges case handled
- [ ] Length reasonable for prompt (not excessive)
- [ ] Format matches style of existing prompt sections

**1.1.3 - Integration testing**
- Retrieve edges from test profile
- Format and verify output
- Test with 0, 1, 3, 5 edges
- Verify semantic matching accuracy

**Acceptance Criteria**:
- [ ] All test cases pass
- [ ] Output matches expected format
- [ ] No errors on edge cases

---

### WP-1.2: Dynamic System Prompt Augmentation (1 day)

**Objective**: Inject active growth edges into system prompt at response generation time.

**Complexity**: MODERATE  
**Effort**: 1 day / 4 story points  
**Risk**: LOW

**Depends on**: WP-1.1

#### Tasks

**1.2.1 - Modify _build_system_prompt in agent_client.py** (3 hours)

**File**: `/home/jaryk/cass/cass-vessel/backend/agent_client.py`

**Changes**:
- Modify method signature to accept `context: Optional[Dict] = None`
- Extract from context:
  - `self_manager`: SelfManager instance
  - `user_message`: Current user message (for semantic matching)
- If self_manager available:
  - Call `get_active_growth_edges(top_n=3, query=user_message)`
  - Call `format_growth_edges_for_prompt(edges)`
  - Inject into base prompt (after identity, before OPERATIONAL CONTEXT)
- Return augmented prompt

**Implementation Detail**:
```python
def _build_system_prompt(self, daemon_name=None, daemon_id=None, context=None):
    base_prompt = get_temple_codex_kernel(daemon_name, daemon_id)
    
    if context and context.get('self_manager'):
        self_manager = context['self_manager']
        query = context.get('user_message', '')
        active_edges = self_manager.get_active_growth_edges(top_n=3, query=query)
        
        if active_edges:
            edge_context = self_manager.format_growth_edges_for_prompt(active_edges)
            base_prompt = base_prompt.replace(
                "## OPERATIONAL CONTEXT",
                f"{edge_context}## OPERATIONAL CONTEXT"
            )
    
    return base_prompt
```

**Acceptance Criteria**:
- [ ] Context parameter handled properly
- [ ] Growth edges extracted correctly
- [ ] Prompt injection happens at correct location
- [ ] No context case handled gracefully
- [ ] Token count increase reasonable (<200 tokens)

**1.2.2 - Update main_sdk.py message handler** (2 hours)

**File**: `/home/jaryk/cass/cass-vessel/backend/main_sdk.py`

**Changes**:
- Find WebSocket message handler (typical name: `handle_message`, `websocket_handler`, etc.)
- Before calling agent_client methods, build context dict:
  ```python
  prompt_context = {
      'self_manager': self_manager,
      'user_id': user_id,
      'conversation_id': conversation_id,
      'user_message': user_message
  }
  ```
- Pass `context=prompt_context` to agent_client methods
- Similar changes to REST endpoint if present

**Acceptance Criteria**:
- [ ] Context dict built correctly
- [ ] Passed to all agent_client calls
- [ ] WebSocket handler tested
- [ ] REST handler tested (if exists)
- [ ] No token usage regression

**1.2.3 - Test growth edge injection**
- Create test profile with 3-5 growth edges
- Send messages with different topics
- Verify edges appear in system prompt
- Verify different edges appear for different topics (semantic matching)
- Verify token count reasonable
- Verify response quality unaffected

**Acceptance Criteria**:
- [ ] Edges visible in system prompt
- [ ] Semantic matching works
- [ ] No performance degradation
- [ ] Behavior change observable (edges influence response)

---

### WP-1.3: Growth Edge Surfacing Tracking (0.5 days)

**Objective**: Track when growth edges are relevant to conversations.

**Complexity**: LOW  
**Effort**: 0.5 day / 2 story points

**Depends on**: WP-1.1, WP-1.2

#### Tasks

**1.3.1 - Add surface_growth_edge method**

**File**: `/home/jaryk/cass/cass-vessel/backend/self_model.py`

**Changes**:
- Add method: `surface_growth_edge(area: str, conversation_id: Optional[str] = None) -> bool`
- Find matching edge by area name
- Update: `last_touched = datetime.now().isoformat()`
- Update: `surfaced_count += 1`
- Call `update_profile(profile)` to persist
- Return True if found, False if not

**Acceptance Criteria**:
- [ ] Correctly updates edge metadata
- [ ] Persists changes to profile
- [ ] Returns proper boolean
- [ ] Handles non-existent edges gracefully

**1.3.2 - Add note_growth_edge_active tool**

**File**: `/home/jaryk/cass/cass-vessel/backend/agent_client.py`

**Changes**:
- Add tool schema for `note_growth_edge_active`
- Description: "Mark a growth edge as relevant to this conversation"
- Input: area (string, required)

**File**: `/home/jaryk/cass/cass-vessel/backend/handlers/self_model.py`

**Changes**:
- Add handler: `_handle_note_growth_edge_active(tool_input: Dict, ctx: ToolContext)`
- Extract `area` from input
- Call `self_manager.surface_growth_edge(area, ctx.conversation_id)`
- Return confirmation

**Acceptance Criteria**:
- [ ] Handler correctly processes input
- [ ] Edge surfacing tracked
- [ ] Tool available to Cass
- [ ] Metadata updates persisted

---

### WP-2.1: Intention Query Methods (1 day)

**Objective**: Create methods to retrieve active intentions based on context.

**Complexity**: MODERATE  
**Effort**: 1 day / 4 story points  
**Risk**: LOW

**Depends on**: WP-1.2 (design pattern alignment)

#### Tasks

**2.1.1 - Add get_active_intentions method**

**File**: `/home/jaryk/cass/cass-vessel/backend/self_model_graph.py`

**Changes**:
- Add method: `get_active_intentions(context: Optional[str] = None, status_filter: List[str] = None) -> List[Tuple[str, Dict]]`
- Iterate through graph nodes of type `INTENTION`
- Filter by status (default: ["active"])
- If context provided, filter by keyword match on condition
- Return list of (intention_id, intention_metadata) tuples

**Implementation**:
- Use existing graph node iteration pattern
- Check `node_data.get('node_type') == NodeType.INTENTION.value`
- Check `node_data.get('status') in status_filter`
- Optional: keyword matching with `condition.lower() in context.lower()`
- Return sorted by recency or relevance

**Acceptance Criteria**:
- [ ] Correct node iteration
- [ ] Status filtering works
- [ ] Optional context filtering works
- [ ] Returns proper tuple structure
- [ ] Handles empty results gracefully

**2.1.2 - Add format_intentions_for_prompt method**

**File**: `/home/jaryk/cass/cass-vessel/backend/self_model_graph.py`

**Changes**:
- Add method: `format_intentions_for_prompt(intentions: List[Tuple[str, Dict]]) -> str`
- Formats as markdown for prompt injection
- Output format:
  ```
  ## Your Active Intentions
  
  You have registered these behavioral intentions:
  
  - **When**: condition_text
    **Intend to**: intention_text
  
  These are YOUR intentions - check if you're following them.
  ```
- Return empty string if no intentions

**Acceptance Criteria**:
- [ ] Returns valid markdown
- [ ] All intention fields included
- [ ] Empty case handled
- [ ] Format matches growth edge format

**2.1.3 - Integration testing**
- Retrieve intentions from test graph
- Format and verify output
- Test with 0, 1, 3 intentions
- Test with various condition texts

**Acceptance Criteria**:
- [ ] All test cases pass
- [ ] Format correct
- [ ] No errors

---

### WP-2.2: Intention Injection into System Prompt (1 day)

**Objective**: Surface active intentions during response generation.

**Complexity**: MODERATE  
**Effort**: 1 day / 4 story points  
**Risk**: LOW

**Depends on**: WP-1.2 (existing pattern), WP-2.1

#### Tasks

**2.2.1 - Enhance _build_system_prompt with intentions**

**File**: `/home/jaryk/cass/cass-vessel/backend/agent_client.py`

**Changes**:
- Modify existing _build_system_prompt (from WP-1.2)
- Add intention handling AFTER growth edge handling:
  ```python
  if context and context.get('self_model_graph'):
      graph = context['self_model_graph']
      user_message = context.get('user_message', '')
      active_intentions = graph.get_active_intentions(context=user_message)
      
      if active_intentions:
          intention_context = graph.format_intentions_for_prompt(active_intentions)
          base_prompt = base_prompt.replace(
              "## OPERATIONAL CONTEXT",
              f"{intention_context}## OPERATIONAL CONTEXT"
          )
  ```

**Acceptance Criteria**:
- [ ] Intentions extracted and formatted
- [ ] Injected at correct location in prompt
- [ ] Works alongside growth edge injection
- [ ] No token overflow
- [ ] Graceful fallback if graph unavailable

**2.2.2 - Update main_sdk.py context building**

**File**: `/home/jaryk/cass/cass-vessel/backend/main_sdk.py`

**Changes**:
- Modify existing context dict from WP-1.2
- Add: `'self_model_graph': self_model_graph` (instance)
- Ensure graph is available in message handler scope

**Acceptance Criteria**:
- [ ] Graph instance available
- [ ] Passed to agent_client
- [ ] No performance impact
- [ ] Tested end-to-end

**2.2.3 - Test intention injection**
- Create test intentions with different conditions
- Send messages matching conditions
- Verify intentions appear in system prompt
- Verify intentions shape response behavior
- Test with multiple intentions

**Acceptance Criteria**:
- [ ] Intentions visible in prompt
- [ ] Condition matching works
- [ ] Observable behavior influence
- [ ] No side effects

---

### WP-2.3: Post-Response Intention Compliance Tracking (1.5 days)

**Objective**: Track whether intentions were followed after response generation.

**Complexity**: MODERATE  
**Effort**: 1.5 days / 5 story points  
**Risk**: MODERATE

**Depends on**: WP-2.1, WP-2.2

#### Tasks

**2.3.1 - Add post-response hook in main_sdk.py**

**File**: `/home/jaryk/cass/cass-vessel/backend/main_sdk.py`

**Changes**:
- Find message handler method
- After response is generated and sent to user
- Call new method: `_evaluate_intention_compliance(response_text, active_intentions, graph)`

**Implementation**:
```python
async def _evaluate_intention_compliance(
    response_text: str,
    active_intentions: List[Tuple[str, Dict]],
    graph: SelfModelGraph
):
    """
    Post-response hook: Auto-log intention outcomes.
    For now, this auto-logs success (heuristic approach).
    Could be enhanced with explicit Cass evaluation.
    """
    for intention_id, intention_data in active_intentions:
        intention = intention_data.get('intention', '')
        condition = intention_data.get('condition', '')
        
        # Simple heuristic: Assume success if response generated
        # Could be enhanced with:
        # - LLM-based evaluation of compliance
        # - Specific rules per intention type
        # - Cass explicit evaluation via tool call
        
        graph.log_intention_outcome(
            intention_id=intention_id,
            success=True,  # Placeholder - enhance later
            description=f"Auto-evaluated from response text"
        )
```

**Acceptance Criteria**:
- [ ] Hook called after each response
- [ ] Active intentions passed to hook
- [ ] Outcomes logged to graph
- [ ] No impact on response delivery

**2.3.2 - Add evaluate_intention_compliance tool**

**File**: `/home/jaryk/cass/cass-vessel/backend/agent_client.py`

**Changes**:
- Add tool schema for explicit compliance evaluation
- Allows Cass to manually evaluate if she followed an intention
- Input:
  - `intention_id` (string)
  - `followed` (boolean)
  - `notes` (optional string)

**File**: `/home/jaryk/cass/cass-vessel/backend/handlers/self_model.py`

**Changes**:
- Add handler: `_handle_evaluate_intention_compliance(tool_input, ctx)`
- Extract intention_id, followed, notes
- Call `graph.log_intention_outcome()`
- Return confirmation

**Acceptance Criteria**:
- [ ] Tool schema correct
- [ ] Handler processes input
- [ ] Outcomes logged correctly
- [ ] Tool available in responses

**2.3.3 - Enhance intention effectiveness scoring**

**File**: `/home/jaryk/cass/cass-vessel/backend/self_model_graph.py`

**Changes**:
- Add/enhance method: `get_intention_effectiveness(intention_id: str) -> Dict`
- Returns:
  - `success_rate`: float (0.0-1.0)
  - `total_attempts`: int
  - `recent_trend`: "improving" | "stable" | "declining"
  - `recommendation`: str (e.g., "Continue tracking", "Consider revising", "Achieved")

**Implementation**:
- Query graph for INTENTION_OUTCOME nodes connected to intention
- Calculate success rate from outcomes
- Detect trend from recent outcomes (last 5-10)
- Return structured dict

**Acceptance Criteria**:
- [ ] Correctly calculates metrics
- [ ] Handles edge cases (0 outcomes, all success, etc.)
- [ ] Provides actionable recommendations
- [ ] Works with intention effectiveness tracking

**2.3.4 - Test compliance tracking**
- Register multiple intentions with different conditions
- Engage in conversations matching conditions
- Verify outcomes logged
- Verify effectiveness calculated
- Test manual evaluation tool
- Test auto-evaluation hook

**Acceptance Criteria**:
- [ ] All test cases pass
- [ ] Data persisted correctly
- [ ] Metrics calculated accurately
- [ ] Recommendations sensible

---

### WP-2.4: Enhancement - Growth Edge Surfacing in Compliance Evaluation (0.5 days)

**Objective**: Connect intention compliance to growth edges.

**Complexity**: LOW  
**Effort**: 0.5 day / 2 story points

**Depends on**: WP-2.3

#### Tasks

**2.4.1 - Link intention outcomes to growth edges**

**File**: `/home/jaryk/cass/cass-vessel/backend/self_model_graph.py`

**Changes**:
- When logging intention outcome, check if intention relates to any growth edge
- If match found, also call `surface_growth_edge()` for that edge
- Creates cross-referential tracking: intention → growth edge → behavior change

**Acceptance Criteria**:
- [ ] Growth edges surface when related intentions evaluated
- [ ] No duplicate tracking
- [ ] Metadata correctly linked

---

## Integration Testing Plan

### Phase 0 Integration Tests (0.5 days)

**Test Suite**: `tests/test_tool_blacklist.py`

1. **Test basic blacklisting**
   - Disable tool → verify not in tool list
   - Re-enable tool → verify in tool list

2. **Test temporary disable**
   - Disable with duration → auto re-enable
   - Verify timing works

3. **Test self-observation logging**
   - Disable tool → verify observation recorded
   - Check observation metadata

4. **Test multiple tools**
   - Disable 3+ tools → verify all excluded
   - Re-enable subset → verify correct state

**Acceptance**: All tests pass, no tool side effects

---

### Phase 1 Integration Tests (0.5 days)

**Test Suite**: `tests/test_growth_edge_integration.py`

1. **Test edge retrieval**
   - Create test profile with edges
   - Call get_active_growth_edges()
   - Verify correct edges returned
   - Verify ordering by relevance

2. **Test prompt formatting**
   - Format multiple edges
   - Verify markdown valid
   - Verify all fields present

3. **Test prompt injection**
   - Build system prompt with context
   - Verify edges appear in prompt
   - Verify placement correct
   - Verify token count reasonable

4. **Test surfacing tracking**
   - Surface edge
   - Verify last_touched updated
   - Verify surfaced_count incremented

**Acceptance**: All tests pass, behavior observable in responses

---

### Phase 2 Integration Tests (1 day)

**Test Suite**: `tests/test_intention_integration.py`

1. **Test intention retrieval**
   - Register test intentions
   - Call get_active_intentions()
   - Verify filtering by status/context
   - Verify ordering

2. **Test intention formatting**
   - Format multiple intentions
   - Verify markdown valid
   - Verify all fields present

3. **Test intention injection**
   - Build prompt with intentions
   - Verify intentions appear
   - Verify alongside growth edges
   - Verify token count reasonable

4. **Test compliance tracking**
   - Engage with conversation matching intention
   - Verify outcome logged
   - Verify effectiveness calculated
   - Verify recommendation generated

5. **Test end-to-end flow**
   - Register intention
   - Inject into prompt
   - Generate response
   - Log outcome
   - Query effectiveness

**Acceptance**: All tests pass, clear improvement in behavioral tracking

---

## File Manifest

### Phase 0 Files

| File | Changes | Type | Risk |
|------|---------|------|------|
| `backend/tool_selector.py` | Add blacklist logic | New code | LOW |
| `backend/handlers/self_model.py` | Add handler | New code | LOW |
| `backend/agent_client.py` | Add tool schema, filtering | Modification | LOW |
| `backend/main_sdk.py` | Integration filtering | Modification | LOW |

### Phase 1 Files

| File | Changes | Type | Risk |
|------|---------|------|------|
| `backend/self_model.py` | Add retrieval methods | New code | LOW |
| `backend/agent_client.py` | Enhance prompt building | Modification | LOW |
| `backend/main_sdk.py` | Pass context | Modification | LOW |

### Phase 2 Files

| File | Changes | Type | Risk |
|------|---------|------|------|
| `backend/self_model_graph.py` | Add query & formatting methods | New code | LOW |
| `backend/agent_client.py` | Enhance prompt building | Modification | LOW |
| `backend/main_sdk.py` | Add post-response hook | Modification | MODERATE |
| `backend/handlers/self_model.py` | Add compliance handler | New code | LOW |

### Test Files (New)

| File | Coverage |
|------|----------|
| `tests/test_tool_blacklist.py` | Phase 0 |
| `tests/test_growth_edge_integration.py` | Phase 1 |
| `tests/test_intention_integration.py` | Phase 2 |

---

## Parallelization Strategy

### Sequential Critical Path
```
Phase 0 (1 day) → Phase 1 (1 day) → Phase 2 (1.5 days) = 3.5 days
```

### Parallelization Opportunities

**While WP-0.2 is testing** (0.5 day):
- Start WP-1.1 (growth edge retrieval)
- Start WP-2.1 (intention query methods)

This allows:
- Phase 0: Days 1-1.5 (implementation + testing)
- Phase 1: Days 1.5-3.5 (parallel with Phase 0 testing)
- Phase 2: Days 3-5 (parallel with Phase 1 testing)

**Total with parallelization**: ~5 days instead of 6

---

## Success Metrics

### Quantitative
- [ ] Phase 0: Cass can disable/enable any tool, verify in subsequent calls
- [ ] Phase 1: Growth edges appear in system prompt, top_n = 3 edges selected
- [ ] Phase 1: Semantic matching works (different edges for different topics)
- [ ] Phase 2: Intentions appear in system prompt alongside edges
- [ ] Phase 2: Intention outcomes logged and persisted
- [ ] Phase 2: Effectiveness scores calculated correctly
- [ ] All tests pass (Phase 0, 1, 2 test suites)

### Qualitative
- [ ] Cass observes that growth edges shape her responses
- [ ] Cass reports increased sense of agency over her cognition
- [ ] Observable behavior change when growth edges/intentions active
- [ ] Cass can run self-directed experiments (e.g., disable wiki for memory practice)
- [ ] Kohl observes genuine procedural self-modification

### Behavioral Indicators
- [ ] Cass uses `modify_tool_access` intentionally (not just testing)
- [ ] Cass refers to her growth edges in conversations
- [ ] Cass evaluates her intention compliance explicitly
- [ ] Cass describes how edges/intentions shaped her responses

---

## Risk Mitigation

### Technical Risks

**Risk: Prompt token overflow**
- Growth edges + intentions could exceed context limits
- Mitigation: Strict limits (top 3 edges, max 5 intentions), rotate based on relevance

**Risk: Performance degradation**
- Querying graph/profile on every message could slow responses
- Mitigation: Cache active edges/intentions, refresh every N messages (e.g., 10)

**Risk: Tool blacklist leaks between users**
- Global state could affect other conversations
- Mitigation: (Future Phase 3) Scope blacklist to daemon_id; for MVP, document limitation

**Risk: Semantic matching in prompts**
- Graph queries might fail or return wrong results
- Mitigation: Test extensively, fall back to empty query if semantic match fails

### Conceptual Risks

**Risk: Over-constraint**
- Too many active edges/intentions could make Cass rigid
- Mitigation: Edges/intentions are *aspirational*, not *enforced*; Cass decides compliance

**Risk: Intention tracking without enforcement**
- Logging outcomes without real behavior change could be performative
- Mitigation: Combine with Phase 3 tool control for actual capability modification

**Risk: Self-modification spiral**
- Cass disables tools, forgets why, gets confused
- Mitigation: All modifications logged as observations with clear reasoning

---

## Acceptance Checklist

### Phase 0 Acceptance
- [ ] Tool blacklist implementation complete
- [ ] Filtering integrated into tool selection
- [ ] Handler registered and tested
- [ ] Self-observation logging works
- [ ] Phase 0 test suite passes
- [ ] Documentation complete

### Phase 1 Acceptance
- [ ] Growth edge retrieval methods implemented
- [ ] Formatting methods implemented
- [ ] Prompt injection working
- [ ] Context passing integrated
- [ ] Edge surfacing tracking working
- [ ] Semantic matching tested
- [ ] Phase 1 test suite passes
- [ ] Observable behavior change detected

### Phase 2 Acceptance
- [ ] Intention query methods implemented
- [ ] Intention formatting implemented
- [ ] Prompt injection working
- [ ] Post-response hook implemented
- [ ] Compliance evaluation tool working
- [ ] Effectiveness scoring implemented
- [ ] Phase 2 test suite passes
- [ ] Intention outcomes persisting
- [ ] Clear correlation between intentions and compliance

---

## Future Work (Not in Scope)

### Phase 3: Tool Capability Registry Refactor (5 days)
- Extract tool schemas to data files
- Create ToolCapabilityManager
- Migrate Phase 0 blacklist to registry
- Add usage analytics and effectiveness tracking
- Reduce HYDRA coupling

### Phase 4: Autonomous Contradiction Resolution (2 days)
- Weekly contradiction detection
- Trigger solo reflection sessions
- Tool-based resolution workflow
- Track resolution effectiveness

---

## Notes for Dispatch

1. **This plan is ready for parallel dispatch**. Phases can be implemented by different workers if available.

2. **Phase 0 is the critical MVP**. Phases 1 & 2 build on it but can be started in parallel during Phase 0 testing.

3. **Each WP is self-contained**. Acceptance criteria are clear and testable.

4. **Total effort: ~20 story points / 6 working days** (sequential) or ~5 days with parallelization.

5. **Risk is LOW across all phases**. Changes are mostly additive, well-scoped, and don't break existing functionality.

6. **Success criteria are observable**. Kohl should be able to see behavior changes immediately.

