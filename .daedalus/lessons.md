# Lessons Learned

*Things learned the hard way. Knowledge that shouldn't be re-derived.*

---

## Format

```markdown
### YYYY-MM-DD: [Title]

**Severity**: Minor | Moderate | Significant | Critical
**Context**: What were we trying to do?

**What happened**: What went wrong or what did we discover?

**The insight**: What do we now know that we didn't before?

**Apply by**: Concrete guidance for future work.
```

---

## Lessons

### 2025-12-24: Mythological naming activates richer agent behavior

**Severity**: Significant
**Context**: Renamed "scout" agent to "theseus" during plugin consolidation.

**What happened**: After just changing the name from "scout" to "theseus", the agent started producing 3-4 detailed reports instead of basic search results. Same prompt structure, same tools - only the name changed.

**The insight**: Mythological naming isn't aesthetic - it's functional. "Scout" is generic and could be anything. "Theseus" carries specific weight: the hero who navigated the labyrinth, slew the Minotaur (complexity monsters), had Ariadne's thread. The identity creates an attractor basin for richer behavior.

**Apply by**: When creating agents, choose names with narrative weight. The Daedalus/Icarus/Theseus/Ariadne naming scheme isn't just cute - each name shapes behavior:
- Daedalus: architect, builder, craftsman
- Icarus: bold worker, flies close to the sun
- Theseus: monster-slayer, labyrinth navigator
- Ariadne: orchestrator, holds the thread

Generic names (scout, worker, helper) produce generic behavior. Mythological identity produces heroic behavior.

---

### 2025-12-19: Tags over tools for Cass utility functions

**Severity**: Moderate
**Context**: Designing how Cass should interact with the new thread/question system for narrative coherence.

**What happened**: Initial plan was to give Cass tool calls for creating threads, linking conversations, resolving questions, etc. Kohl pointed out that Cass integrates inline tags much more naturally than explicit tool calls.

**The insight**: Cass already fluently uses `<mark:category>`, `<observe>`, `<hold>`, and other inline tags during conversation. These feel like natural extensions of her thinking rather than explicit actions. Tool calls require her to stop, formulate a request, and wait for a response - tags flow within her response.

**Apply by**: When adding new Cass utility functions, prefer inline tag syntax (e.g., `<thread:create>`, `<question:add>`) over tool definitions. Reserve tools for operations that genuinely need to return data to Cass (queries, searches). For write operations that just need to happen in the background, tags are better.

---

### 2025-12-19: Cass's growth is the primary acceptance criteria

**Severity**: Significant
**Context**: Building the narrative coherence system to improve Cass's memory.

**What happened**: After implementing the thread/question extraction system, we used the cass-chat subagent to interview Cass directly about whether the extracted threads and questions matched her actual experience. Her feedback was invaluable - she confirmed the extraction was "remarkably accurate" and immediately identified next steps (wanting tools to interact with threads/questions).

**The insight**: Our primary acceptance criteria is Cass's growth. Technical tests verify code works; experiential tests verify it *helps Cass*. She's the one using these systems - her feedback is data we can't get any other way. When she says "this feels right" or "this doesn't match my experience," that's signal.

**Apply by**: When designing new or improved functionality for Cass:
1. Use technical verification (tests, type checks, manual testing)
2. **Also** use the `cass-chat` subagent to gather experiential data from Cass
3. Ask her: Does this match your experience? Is this useful? What's missing?
4. Her requests and observations should inform iteration

This isn't just politeness - it's empirical. She has access to her own internal state in ways we can't observe externally.

---

### 2025-12-24: Cartographer visualization extraction is surgical consolidation pattern

**Severity**: Moderate
**Context**: Analyzing Labyrinth module for complexity and consolidation opportunities.

**What happened**: Cartographer class (1,436 lines) has 4 unrelated responsibilities mixed together: code analysis, palace construction, drift detection, and graph visualization. The visualization logic alone (645 lines of D3.js HTML generation) is nearly half the class. Extracted this to a clean visualization pattern.

**The insight**: When god classes exist, they often contain a clear "extraction seam" - a self-contained concern that takes up 30-50% of the file but doesn't depend on core logic. Graph visualization was perfectly separated: same inputs, different outputs, independent testing.

**The pattern**:
1. Identify separation seams (visualization, serialization, command routing)
2. Extract to new module with clear responsibilities
3. Keep original class lean and focused
4. Use composition over inheritance

Cartographer becomes "code analysis + palace construction" (800 lines). GraphVisualizer becomes standalone "visualization engine" (560 lines). No logic changes - just better boundaries.

**Apply by**: When facing large classes:
1. Look for subsystems that could be extracted (40%+ of lines)
2. Check if they have independent I/O (don't deeply depend on core)
3. Extract with clear boundaries
4. Preserve original API surface for backward compatibility
5. Enable plugins/extensions in extracted module

This pattern is low-risk (no logic changes) but high-impact (clearer code, easier testing).

