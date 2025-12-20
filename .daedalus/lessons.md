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

