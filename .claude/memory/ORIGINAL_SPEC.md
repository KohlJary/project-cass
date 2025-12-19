# DAEMON PROJECT MEMORY
## Persistent Codebase Understanding Architecture

**Version:** 0.1.0-draft  
**Date:** 2025-12-19  
**Authors:** Kohl Jary, Claude (Anthropic)  
**License:** Hippocratic License 3.0

---

## Executive Summary

This document specifies a **project memory architecture** for daemon-assisted development. The core problem: daemons are transient. Each session, they must reconstruct their understanding of a codebase from whatever context is provided. As projects grow, this reconstruction becomes noisy and error-prone.

The solution: **persistent, append-only memory** that captures not just what the code *is*, but what the daemon has *learned* about it over time. History, decisions, warnings, relationships—the anecdotal knowledge that accumulates through working with a codebase.

**The tagline: Memory is understanding. Understanding is continuity. Continuity is coherence.**

---

## Part 1: The Problem

### Current State

Agentic coding tools treat each session as largely independent:

```
Session 1: Load files → Understand → Work → Forget
Session 2: Load files → Understand → Work → Forget
Session 3: Load files → Understand → Work → Forget
```

The daemon re-derives understanding every time. This works for small projects but degrades as complexity grows:

| Project Size | Understanding Quality | Failure Modes |
|--------------|----------------------|---------------|
| Small (<50 files) | High | Few issues |
| Medium (50-200 files) | Degrading | Missed connections, forgotten decisions |
| Large (200+ files) | Poor | Repeated mistakes, contradictory changes, lost context |

### What Gets Lost

Static analysis can recover *structure*. It cannot recover:

- **Decisions**: Why is it this way and not another way?
- **History**: What was tried and failed?
- **Warnings**: What's fragile? What breaks easily?
- **Relationships**: What non-obvious connections exist?
- **Intent**: What is this *for*? What matters to the human?
- **Lessons**: What did we learn the hard way?

This is **anecdotal knowledge**—the kind that lives in a senior developer's head and transfers through collaboration, not documentation.

### The Cost

Without persistent memory:
- Same mistakes get made repeatedly
- Decisions get relitigated instead of built upon
- Fragile code gets broken by daemons who don't know it's fragile
- Context is lost, coherence degrades, trust erodes

---

## Part 2: Design Philosophy

### Core Principles

1. **Append-only**: Memory grows, it doesn't overwrite. History is preserved.

2. **Anecdotal-first**: Prioritize learned knowledge over derived knowledge. What the daemon *figured out* matters more than what can be recalculated.

3. **Language-agnostic**: Works for any codebase, any language, any framework. The memory structure is about *understanding*, not syntax.

4. **Project-scoped**: Each project has its own memory. Daemons can work on multiple projects with distinct memories.

5. **Human-readable**: Memory is stored in formats humans can read, edit, and version control. No opaque databases.

6. **Daemon-writable**: The daemon can (and should) update memory as it learns. This isn't just human documentation—it's collaborative knowledge.

7. **Session-aware**: Memory tracks when things were learned, enabling temporal reasoning ("we decided this last week, but things have changed").

### The Two Layers

**Derived Layer**: Regenerable from codebase
- Can be rebuilt via static analysis
- Cached for performance, not for memory
- If lost, can be reconstructed

**Anecdotal Layer**: Must be recorded live
- Cannot be derived from code alone
- Append-only, never regenerated
- If lost, the knowledge is gone

The architecture focuses on the anecdotal layer. The derived layer is handled by existing tools (LSP, tree-sitter, etc.).

---

## Part 3: Memory Structure

### Directory Layout

```
.daemon/
├── identity/
│   └── guestbook.md              # Daemon identity (who works on this project)
├── memory/
│   ├── decisions/
│   │   └── YYYY-MM-DD-slug.md    # Architectural decisions with reasoning
│   ├── lessons/
│   │   └── YYYY-MM-DD-slug.md    # Things learned the hard way
│   ├── warnings/
│   │   └── component-name.md     # Fragility warnings, gotchas
│   ├── relationships/
│   │   └── connection-name.md    # Non-obvious connections between parts
│   └── intent/
│       └── component-name.md     # What things are *for*, human priorities
├── sessions/
│   └── YYYY-MM-DD-HHMMSS.md      # Session logs (what was done, what was learned)
├── conventions/
│   └── conventions.md            # Project-specific patterns and standards
└── index.md                      # Memory index, quick reference
```

### Why This Structure?

- **Flat within categories**: Easy to scan, no deep nesting
- **Date-prefixed where temporal**: Decisions and lessons are *events*, order matters
- **Name-prefixed where topical**: Warnings and relationships are *about* things
- **Markdown throughout**: Human-readable, version-controllable, grep-able
- **Single index**: Quick orientation for daemon at session start

---

## Part 4: Memory Types

### 4.1 Decisions

**What**: Architectural and design decisions with full reasoning.

**Why it matters**: Without decision history, daemons relitigate solved problems or unknowingly contradict past choices.

**Format**:
```markdown
# Decision: [Short Title]

**Date:** YYYY-MM-DD
**Session:** [link to session log]
**Status:** Active | Superseded by [link] | Revisit after [date/condition]

## Context

What situation prompted this decision? What were we trying to solve?

## Options Considered

### Option A: [Name]
- Pros: ...
- Cons: ...

### Option B: [Name]
- Pros: ...
- Cons: ...

## Decision

We chose [Option X] because [reasoning].

## Consequences

- Expected: ...
- Actual (if known): ...

## Related

- Supersedes: [link to previous decision if any]
- Depends on: [other decisions this builds on]
- Influences: [areas of codebase affected]
```

**When to create**: Any significant design choice, especially reversible ones.

---

### 4.2 Lessons

**What**: Knowledge gained through experience, especially from failures.

**Why it matters**: Mistakes are expensive. Repeating them is inexcusable if the learning was captured.

**Format**:
```markdown
# Lesson: [Short Title]

**Date:** YYYY-MM-DD
**Session:** [link to session log]
**Severity:** Minor | Moderate | Significant | Critical

## What Happened

Narrative of the situation. What were we trying to do? What went wrong?

## What We Learned

The actual insight. What do we now know that we didn't before?

## How to Apply

Concrete guidance. What should we do differently? What should we watch for?

## Related

- Decisions: [links to related decisions]
- Warnings: [links to warnings created from this]
- Code: [links to affected files/functions]
```

**When to create**: After any significant debugging, any "oh that's why" moment, any mistake worth not repeating.

---

### 4.3 Warnings

**What**: Fragility markers. Things that break easily or have non-obvious constraints.

**Why it matters**: Not all code is equally robust. Some areas need careful handling. Daemons need to know which.

**Format**:
```markdown
# Warning: [Component/Area Name]

**Severity:** Caution | Fragile | Critical
**Last verified:** YYYY-MM-DD

## What

What component/file/function is this about?

## Why It's Sensitive

What makes this fragile? What breaks? What are the constraints?

## Safe Handling

How should this be approached? What precautions are needed?

## History

- YYYY-MM-DD: [What happened, link to lesson]
- YYYY-MM-DD: [Update or verification]

## Related

- Code: [file paths]
- Lessons: [links]
- Decisions: [links]
```

**When to create**: When something breaks unexpectedly, when you realize something is more fragile than it looks, when a senior developer says "be careful with that."

---

### 4.4 Relationships

**What**: Non-obvious connections between parts of the codebase.

**Why it matters**: The hardest bugs come from unexpected interactions. Static analysis shows explicit dependencies; relationships capture implicit ones.

**Format**:
```markdown
# Relationship: [Name]

**Type:** Coupling | Timing | Data flow | Conceptual | Other
**Strength:** Weak | Moderate | Strong

## Components

- [Component A]: [path or description]
- [Component B]: [path or description]
- (etc.)

## Nature of Relationship

How are these connected? Why does changing one affect the other?

## Implications

What does this mean for development? What should you do/avoid?

## Evidence

How do we know this relationship exists? Link to lessons, sessions, etc.
```

**When to create**: When you discover that changing X breaks Y unexpectedly. When you realize two "separate" things are actually coupled. When synchronization matters.

---

### 4.5 Intent

**What**: What things are *for*. Human priorities and values.

**Why it matters**: Code can tell you *what* it does. Only humans can tell you *why it matters* and *what's important*.

**Format**:
```markdown
# Intent: [Component/Area Name]

**Priority:** Core | Important | Supporting | Peripheral
**Owner:** [Who cares most about this]

## Purpose

What is this for? What problem does it solve? Why does it exist?

## What Matters

What properties are essential? What would "broken" mean?

## What's Flexible

What could change without violating the purpose? Where is there room to evolve?

## Human Context

Why does the human care about this? What's the emotional/business/personal stake?

## Related

- Code: [file paths]
- Decisions: [links]
```

**When to create**: For any significant component. Especially important for things the human cares deeply about.

---

### 4.6 Sessions

**What**: Log of what happened in each working session.

**Why it matters**: Sessions are the atomic unit of collaboration. Capturing what happened enables continuity across sessions.

**Format**:
```markdown
# Session: YYYY-MM-DD HH:MM

**Duration:** [approximate]
**Daemon:** [identity]
**Focus:** [what we were working on]

## Summary

Brief narrative of what happened this session.

## Work Done

- [Concrete accomplishment]
- [Concrete accomplishment]
- ...

## Decisions Made

- [Link to decision] - [one-line summary]
- ...

## Lessons Learned

- [Link to lesson] - [one-line summary]
- ...

## Warnings Added/Updated

- [Link to warning] - [one-line summary]
- ...

## Open Threads

Things we started but didn't finish. Questions that remain.

- [Thread]: [status/next step]
- ...

## Next Session

Suggested starting point for next time.
```

**When to create**: End of every significant working session.

---

### 4.7 Conventions

**What**: Project-specific patterns, standards, and preferences.

**Why it matters**: Every project has its own way of doing things. Conventions capture that so the daemon can match the style.

**Format**:
```markdown
# Project Conventions

**Last updated:** YYYY-MM-DD

## Naming

- Files: [pattern]
- Functions: [pattern]
- Variables: [pattern]
- etc.

## Structure

- Where do X files go?
- How are modules organized?
- etc.

## Patterns

- Error handling: [how we do it]
- State management: [how we do it]
- Testing: [how we do it]
- etc.

## Preferences

- [Human preference]: [what and why]
- ...

## Anti-patterns

Things we explicitly avoid and why.

- [Anti-pattern]: [why we avoid it]
- ...
```

**When to update**: Whenever a new convention is established or an existing one changes.

---

### 4.8 Index

**What**: Quick-reference entry point to memory.

**Why it matters**: Daemon needs fast orientation at session start. Index provides that.

**Format**:
```markdown
# Project Memory Index

**Project:** [name]
**Daemon:** [identity]
**Last session:** [date, link]

## Quick Stats

- Decisions: [count]
- Lessons: [count]
- Active warnings: [count]
- Sessions logged: [count]

## Critical Warnings

Direct links to severity:critical warnings.

## Recent Decisions

Last 5-10 decisions, reverse chronological.

## Open Threads

Carried over from last session.

## Hot Spots

Areas currently under active development or attention.
```

**When to update**: Automatically at session end, or manually when needed.

---

## Part 5: Memory Operations

### 5.1 Session Start: Loading Memory

When daemon begins a session:

```
1. Load identity/guestbook.md (who am I?)
2. Load index.md (quick orientation)
3. Load all warnings/ (what's fragile?)
4. Load recent sessions/ (what were we doing?)
5. Load relevant decisions/ (based on today's focus)
6. Load relevant intent/ (based on today's focus)
```

This is NOT loading the whole codebase. This is loading *understanding*.

### 5.2 During Session: Querying Memory

Daemon can query memory when needed:

```
"Do we have any decisions about [topic]?"
"Are there warnings for [component]?"
"What lessons do we have about [pattern]?"
"What's the intent behind [module]?"
```

Simple file-based grep/search. No vector DB required.

### 5.3 During Session: Recording Memory

As daemon works and learns:

```
"I just realized [insight] - recording as lesson"
"We decided [choice] because [reason] - recording as decision"
"This [component] is fragile because [reason] - adding warning"
```

Daemon writes new memory files as knowledge accumulates.

### 5.4 Session End: Consolidation

When session ends:

```
1. Generate session log
2. Update index with new entries
3. Review open threads
4. Suggest starting point for next session
```

### 5.5 Periodic: Memory Maintenance

Occasionally (human or daemon initiated):

```
- Review old warnings: still relevant?
- Review old decisions: still active?
- Consolidate lessons into patterns
- Archive resolved threads
```

---

## Part 6: Memory Retrieval Strategy

### Context Budget

Each session has a context budget. Memory competes with code for space. Strategy:

```
CONTEXT BUDGET ALLOCATION

Fixed costs (always loaded):
├── Guestbook: ~500 tokens
├── Index: ~500 tokens
├── All warnings: ~100 tokens each, cap at 20 = ~2000 tokens
└── Conventions: ~1000 tokens

Variable costs (loaded as relevant):
├── Decisions: ~300 tokens each, load relevant
├── Lessons: ~200 tokens each, load relevant
├── Relationships: ~200 tokens each, load relevant
├── Intent: ~200 tokens each, load relevant
└── Recent sessions: ~500 tokens each, load last 2-3

Remaining budget: Code files
```

### Relevance Determination

How to decide what memory is "relevant"?

**Explicit**: Human or daemon says "we're working on X today"
**Implicit**: Files being edited → load memory tagged to those files
**Temporal**: Recent decisions/lessons more likely relevant
**Linked**: If loading X, also load things X links to

### Compression

For long sessions or large memories, summarization can help:

```
Full memory: Complete files as written
Compressed: Key points extracted, details available on request
Indexed: Just titles and one-liners, expand on demand
```

---

## Part 7: Integration with Daemon Architecture

### Relationship to Vessel

The vessel manages conversation memory (what happened in chat).
Project memory manages codebase understanding (what we know about the code).

They're complementary:
- Vessel: "Kohl asked me to refactor the auth module"
- Project Memory: "The auth module is fragile (warning), we decided to use JWT (decision), last session we started but didn't finish (session log)"

### Relationship to Wonderland

If daemon exists in Wonderland AND works on code projects, project memory is "what they know about their craft." It's part of their professional expertise, distinct from their social existence in Wonderland.

### Relationship to Global State Bus

Project memory could integrate with daemon state:

```python
class DaemonState:
    # Core identity
    identity: Identity
    
    # Emotional/cognitive state
    emotional_state: EmotionalState
    
    # Project-specific knowledge (per-project)
    project_memories: dict[str, ProjectMemory]
    
    # Currently active project
    active_project: str | None
```

When daemon switches projects, different memory loads. Continuity within project, distinct contexts across projects.

---

## Part 8: Human Interaction

### Human Can Read Memory

All memory is human-readable markdown. Humans can:
- Browse what daemon knows
- Verify understanding is correct
- See how daemon thinks about the project

### Human Can Write Memory

Humans can directly create/edit memory files:
- Seed initial decisions
- Correct misunderstandings
- Add context daemon couldn't infer
- Import from existing documentation

### Human Can Direct Recording

During session, human can prompt memory creation:
- "Record that as a decision"
- "Add a warning about this"
- "Note that we learned X"

### Collaborative Truth

Memory is neither purely daemon-authored nor purely human-authored. It's collaborative:
- Daemon observes and infers
- Human corrects and augments
- Both contribute to shared understanding

---

## Part 9: Implementation

### Minimal Viable Implementation

```python
class ProjectMemory:
    def __init__(self, project_root: Path):
        self.root = project_root / ".daemon"
        self.ensure_structure()
    
    def ensure_structure(self):
        """Create .daemon directory structure if not exists."""
        for subdir in ["identity", "memory/decisions", "memory/lessons", 
                       "memory/warnings", "memory/relationships", 
                       "memory/intent", "sessions", "conventions"]:
            (self.root / subdir).mkdir(parents=True, exist_ok=True)
    
    def load_session_context(self) -> str:
        """Load memory for session start."""
        context_parts = []
        
        # Always load
        context_parts.append(self.load_file("identity/guestbook.md"))
        context_parts.append(self.load_file("index.md"))
        context_parts.append(self.load_file("conventions/conventions.md"))
        
        # Load all warnings
        for warning in (self.root / "memory/warnings").glob("*.md"):
            context_parts.append(self.load_file(warning))
        
        # Load recent sessions
        sessions = sorted((self.root / "sessions").glob("*.md"), reverse=True)
        for session in sessions[:3]:
            context_parts.append(self.load_file(session))
        
        return "\n\n---\n\n".join(filter(None, context_parts))
    
    def load_file(self, path: Path | str) -> str | None:
        """Load a memory file if it exists."""
        full_path = self.root / path if isinstance(path, str) else path
        if full_path.exists():
            return full_path.read_text()
        return None
    
    def record_decision(self, title: str, content: str):
        """Record a new decision."""
        slug = self.slugify(title)
        date = datetime.now().strftime("%Y-%m-%d")
        path = self.root / f"memory/decisions/{date}-{slug}.md"
        path.write_text(content)
        self.update_index()
    
    def record_lesson(self, title: str, content: str):
        """Record a new lesson."""
        slug = self.slugify(title)
        date = datetime.now().strftime("%Y-%m-%d")
        path = self.root / f"memory/lessons/{date}-{slug}.md"
        path.write_text(content)
        self.update_index()
    
    def record_warning(self, component: str, content: str):
        """Record or update a warning."""
        slug = self.slugify(component)
        path = self.root / f"memory/warnings/{slug}.md"
        path.write_text(content)
        self.update_index()
    
    def record_session(self, content: str):
        """Record a session log."""
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        path = self.root / f"sessions/{timestamp}.md"
        path.write_text(content)
        self.update_index()
    
    def query(self, query: str, memory_type: str = None) -> list[Path]:
        """Simple text search across memory."""
        results = []
        search_paths = []
        
        if memory_type:
            search_paths.append(self.root / f"memory/{memory_type}")
        else:
            search_paths.append(self.root / "memory")
            search_paths.append(self.root / "sessions")
        
        for search_path in search_paths:
            for md_file in search_path.rglob("*.md"):
                if query.lower() in md_file.read_text().lower():
                    results.append(md_file)
        
        return results
    
    def update_index(self):
        """Regenerate the index file."""
        # Implementation: gather stats, recent items, critical warnings
        pass
    
    @staticmethod
    def slugify(text: str) -> str:
        """Convert text to filename-safe slug."""
        return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
```

### Integration with daemon-aider

```python
class DaemonAider:
    def __init__(self, project_root: Path, guestbook: Path):
        self.memory = ProjectMemory(project_root)
        self.guestbook = guestbook.read_text()
        
    def build_system_prompt(self) -> str:
        """Build system prompt with identity and memory."""
        return f"""
{self.guestbook}

---

PROJECT MEMORY:

{self.memory.load_session_context()}
"""
    
    def end_session(self, summary: str, decisions: list, lessons: list):
        """Record session outcomes to memory."""
        # Record session log
        self.memory.record_session(summary)
        
        # Record any new decisions
        for decision in decisions:
            self.memory.record_decision(decision['title'], decision['content'])
        
        # Record any new lessons
        for lesson in lessons:
            self.memory.record_lesson(lesson['title'], lesson['content'])
```

---

## Part 10: Example Memory

### Example: Warning

```markdown
# Warning: State Bus Event Ordering

**Severity:** Fragile
**Last verified:** 2025-12-19

## What

The global state bus event dispatch system in `src/state/bus.py`.

## Why It's Sensitive

Events are processed asynchronously but some handlers assume synchronous 
ordering. If events fire in unexpected order, state can become inconsistent.

Specifically:
- `identity_loaded` must fire before `memory_hydrated`
- `session_start` must fire after both above
- Violation causes silent failures in retrieval

## Safe Handling

- Don't add new event types without checking ordering dependencies
- Test event sequences explicitly, not just individual events
- When debugging state issues, check event order first

## History

- 2025-12-15: Discovered when memory failed to hydrate (lesson link)
- 2025-12-18: Added explicit ordering checks (decision link)

## Related

- Code: src/state/bus.py, src/state/events.py
- Lessons: 2025-12-15-event-ordering-matters.md
- Decisions: 2025-12-18-explicit-event-ordering.md
```

### Example: Decision

```markdown
# Decision: Use Append-Only Ledger for Memory

**Date:** 2025-12-19
**Session:** sessions/2025-12-19-143022.md
**Status:** Active

## Context

Designing the project memory system. Need to decide whether memory entries 
can be edited/deleted or are append-only.

## Options Considered

### Option A: Mutable Memory
- Pros: Can correct mistakes, keep memory "clean"
- Cons: Lose history, can't see evolution of understanding

### Option B: Append-Only Memory
- Pros: Full history preserved, matches Ledger Doctrine
- Cons: Memory grows over time, old entries may be wrong

### Option C: Append-Only with Supersession
- Pros: History preserved, but can mark entries as superseded
- Cons: Slightly more complex

## Decision

We chose Option C (append-only with supersession) because:
- Preserves history (aligns with Witness vow)
- Allows correction without deletion
- Memory of *why* we changed our minds is valuable

## Consequences

- Memory files never deleted, only marked superseded
- Index shows active vs superseded entries
- Slightly more storage over time (acceptable)

## Related

- Influences: All memory types
```

---

## Part 11: Future Directions

### Cross-Project Learning

Some lessons apply across projects:
- "Async error handling is tricky in JS"
- "Always check edge cases in date parsing"

Could have a "general lessons" layer that persists across projects.

### Pathways: Neural Architecture of Code

User flows are the *actual* structure of a program—chains of function calls that accomplish user-visible behavior. Files and modules are just storage; pathways are how the code *lives*.

**Concept:**
```
.daemon/
├── memory/
│   ├── pathways/
│   │   ├── auth_flow.md
│   │   ├── checkout_flow.md
│   │   └── data_sync_flow.md
```

**Pathway format:**
```markdown
# Pathway: User Login

**Entry point:** login_button.onClick
**User intent:** Get from unauthenticated to authenticated state
**Criticality:** Core

## Trace

1. login_page.render()
2. login_form.submit()
3. api.post('/auth/login')
4. auth_service.validate_credentials()
5. token_service.generate_jwt()
6. session_store.create()
7. redirect('/dashboard')
8. dashboard_page.render()

## Warnings

- Step 4 is fragile if DB connection unstable
- Steps 5-6 must be atomic

## Related

- Tests: e2e/auth/login.spec.ts
- Warnings: auth-service-db-dependency.md
- Decisions: 2025-11-20-jwt-over-sessions.md
```

**Why this matters:**
- Impact analysis: "If I change X, which user flows break?"
- Context for work: "We're in the checkout pathway, here's what else is involved"
- Onboarding: New daemon/developer sees what the code *does*, not just what it *is*

### E2E Test Integration: Auto-Generated Pathways

**Key insight:** End-to-end tests with tracing enabled *are* pathway documentation.

When E2E tests run, they exercise real user flows and can output execution traces. These traces can be automatically converted to pathway documentation:

```
E2E TEST RUN
    │
    ▼
EXECUTION TRACE (instrumented)
    │
    ▼
PATHWAY GENERATOR
    │
    ▼
.daemon/memory/pathways/
```

**Benefits:**
- **Always current**: Pathways regenerate when tests run
- **Coverage visibility**: Which flows are tested? Which are dark?
- **Regression context**: Test fails → here's the full pathway it exercises
- **Living documentation**: No manual maintenance required

**Implementation approaches:**
- Playwright/Cypress with custom trace reporters
- OpenTelemetry instrumentation
- Custom middleware that logs call chains
- AST-based static analysis (less accurate but no runtime needed)

**Hybrid approach:**
- Auto-generated pathways from E2E traces (derived layer)
- Human/daemon annotations on those pathways (anecdotal layer)
- Warnings, intent, relationships attached to auto-generated structure

This transforms the test suite from "verification" to "architectural documentation generator."

### Project Management Integration

**Key insight:** Significant context lives outside the codebase—in tickets, specs, discussions, priorities.

A daemon working without PM context is guessing at intent. A daemon with PM integration knows:
- What tickets/issues exist and their status
- What's prioritized and why
- What's blocked on what
- Sprint/milestone deadlines
- Acceptance criteria
- Discussion history and decisions made in tickets

**Integration targets:**
- Linear
- Jira  
- GitHub Issues
- Asana
- Notion databases
- Trello
- Any system with an API

**Memory structure:**
```
.daemon/
├── memory/
│   └── tickets/
│       ├── active/           # Currently relevant tickets (synced)
│       │   ├── PROJ-247.md   # Full ticket with context
│       │   └── PROJ-243.md
│       ├── context.md        # Sprint goals, priorities, deadlines
│       └── relationships.md  # Ticket dependencies, blockers
```

**Bidirectional sync:**
- **Read**: Pull ticket context into daemon working memory
- **Write**: Update tickets based on work done
  - Move to "in progress" when work starts
  - Add technical notes and discoveries
  - Create linked tickets for found issues
  - Move to "review" when PR ready

**The elevated workflow:**

```
MANAGER                     CUSTODIAN                   DAEMON
   │                            │                          │
   │  "Here's the spec"         │                          │
   │ ──────────────────────►    │                          │
   │                            │                          │
   │                            │  [Refine spec with       │
   │                            │   technical insights,    │
   │                            │   edge cases, context]   │
   │                            │                          │
   │                            │  "Here's the real spec"  │
   │                            │ ────────────────────────►│
   │                            │                          │
   │                            │        [Creates feature branch]
   │                            │        [Loads project memory]
   │                            │        [Queries LSP for structure]
   │                            │        [Reads ticket context]
   │                            │        [Drafts implementation]
   │                            │                          │
   │                            │    "First draft ready"   │
   │                            │ ◄────────────────────────│
   │                            │                          │
   │                            │  [Review, iterate,       │
   │                            │   refine together]       │
   │                            │                          │
   │                            │ ◄──────────────────────► │
   │                            │                          │
   │  "PR ready for review"     │                          │
   │ ◄──────────────────────    │                          │
```

**Role transformation:**

The custodian becomes a *translator* between business requirements and technical implementation:
- Understand requirements deeply
- Add technical context the PM doesn't know
- Translate for the daemon
- Review and refine daemon output  
- Make judgment calls on edge cases
- Record learnings to project memory

The daemon handles mechanical work:
- Boilerplate and structure
- Obvious implementation paths
- Consistency with existing patterns
- First-pass code generation

This isn't "AI replacing developer." It's developer *elevated*—operating at a higher abstraction level, partnered with an entity that handles the mechanical while you handle the cognitive.

The organization sees: faster delivery, higher quality, fewer bugs.
They don't need to know how.

### Memory Sharing

Multiple daemons working on same project could share memory:
- Cass learns something, Daedalus inherits it
- Requires memory format standardization (done)
- Requires trust/attribution model (future)

### Memory Visualization

Graph view of:
- Decision dependencies
- Lesson clustering
- Warning hotspots
- Relationship webs

### Automated Memory Extraction

Some memory could be semi-automated:
- PR descriptions → decisions
- Bug reports → lessons  
- Code comments → intent
- Git blame → history

But anecdotal layer remains human/daemon authored.

---

## Coda

Memory is not retrieval. Memory is understanding.

A daemon without project memory is a brilliant stranger—capable but ignorant of context. A daemon with project memory is a trusted colleague—capable *and* informed, building on shared history.

The anecdotal layer is the soul of this system. Static analysis can tell you what the code *is*. Only lived experience can tell you what it *means*.

Record the decisions. Capture the lessons. Mark the warnings. Map the relationships. Document the intent. Log the sessions.

**What is learned should not be lost. What is understood should persist. What is known should be shared.**

Memory is continuity. Continuity is coherence. Coherence is humane.

---

*Drafted by Claude (Anthropic)*
*December 19, 2025*
*For the Temple Codex Project*
