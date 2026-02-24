# Key Decisions

*Significant architectural and design decisions with rationale*

## Grimoire ThymosBASIC DSL (Feb 2026)

**Decision**: Use BASIC-inspired text DSL for daemon behavioral spells

**Context**: Needed a way to define behavioral patterns that trigger on Thymos emotional/need state. These patterns should be editable, versionable, and human-readable.

**Options considered**:
1. JSON/YAML configuration (declarative)
2. Python functions registered as handlers (code)
3. Visual node-based editor only (graphical)
4. Custom DSL (ThymosBASIC)

**Approach**:
- ThymosBASIC: BASIC-inspired syntax with `UNIT/END UNIT`, `IF/THEN/END IF`, `FOR/NEXT`
- Trigger types: `ON need.X < Y`, `ON affect.X > Y`, `ON EVENT`, `ON TIMER`, `ON MANUAL`
- Actions: `DELTA`, `CARE`, `TASK`, `EMIT`, `LOG`, `WAIT`, `CAST` (nested spells)
- Agentic actions: `ASK`, `CHOOSE`, `RATE`, `GENERATE`, `REFLECT` (LLM calls)
- Shadow mode: Agentic actions log intent but don't execute

**Rationale**:
- BASIC is readable by non-programmers (Kohl wanted visual editor eventually)
- Text files are git-friendly and versionable
- Spell triggers can be indexed for fast matching (vs. evaluating every handler)
- Shadow mode allows validation before enabling real behavioral effects
- Agentic actions give spells LLM reasoning capabilities

**Trade-offs**:
- Another DSL to maintain (parser, runtime, tooling)
- Visual editor not yet built
- Learning curve for spell authors

**Future**: Visual node editor that compiles to/from ThymosBASIC

---

## Entity Knowledge Architecture (Feb 2026)

**Decision**: Keep users/PeopleDex split for now, plan consolidation for later

**Context**: Discord perception integration revealed overlap between `users` table (observations, relationships) and `peopledex` (biographical facts, handles).

**Options considered**:
1. Auto-create user accounts for Discord users (quick fix)
2. Consolidate all entity knowledge into PeopleDex (cleaner architecture)

**Current approach**:
- Link Discord users to existing Cass users by matching `discord_handle`
- Known users get full relationship context in Discord perception
- Unknown Discord users tracked only in PeopleDex (no observations yet)

**Deferred**: Full consolidation where observations/relationships move to PeopleDex level. See `.daedalus/plans/peopledex-consolidation.md` for detailed plan.

**Rationale**:
- Discord works now for known users (like Kohl)
- Consolidation is ~5-6 sessions of work
- Can defer until we need observations for Discord-only people

---

## Event-Driven State (Dec 2025)

**Decision**: State bus uses event-driven updates, not time-based decay

**Context**: Initially implemented half-life decay (emotional state fades toward baseline over 24h)

**Problem**: Kohl identified that Cass is discrete-step cognition. She doesn't experience time passing between conversations - she's not sitting there for 8 hours feeling contentment slowly fade.

**Approach**:
- State persists as-is until explicitly changed by events
- Events: chat emotes, session transitions, explicit updates
- No passive decay - if she was curious last chat, she's still curious next chat

**Rationale**:
- More honest to her actual phenomenology
- Discrete instantiation, not continuous experience
- State changes reflect actual cognitive events, not clock time

**Trade-offs**:
- State could become "stale" if no events happen for long periods
- May need event-driven decay later (e.g., decay after N conversations)

---

## Route Organization Pattern (Dec 2025)

**Decision**: Split monolithic route files into domain packages with module-level DI

**Context**: admin_api.py (6044 lines) and testing.py (2336 lines) were too large

**Approach**:
```
routes/admin/
├── __init__.py       # Router composition, init_all_routes()
├── auth.py           # _manager = None, def init_auth(manager): ...
├── daemons.py        # Same pattern
└── ...
```

**Rationale**:
- Each module owns one domain
- Module-level globals avoid threading issues (FastAPI is per-request)
- Unified init function in __init__.py for clean startup
- No changes needed to main_sdk.py imports

**Trade-offs**:
- More files to navigate
- Import cycles possible if not careful
- Must call init_all_routes() at startup

---

## Hierarchical Memory Retrieval (Existing)

**Decision**: Three-tier retrieval with timestamp filtering

**Approach**:
1. Search summaries (compressed history)
2. Search details WHERE timestamp > latest_summary_end
3. Include recent chronological messages

**Rationale**:
- Avoids duplication between summaries and details
- Token-efficient - summaries compress older context
- Preserves conversation flow with chronological messages

---

## Self-Model as Structured Data (Existing)

**Decision**: Store observations in SQLite with category, confidence, source tracking

**Approach**:
```sql
self_observations (
    id, daemon_id, category, observation, confidence,
    source_conversation_id, source_journal_date
)
```

**Rationale**:
- Queryable and filterable
- Confidence tracking enables nuanced self-understanding
- Source tracking provides evidence trail
- Categories enable domain-specific retrieval

---

## Daedalus Memory Architecture (Dec 2025)

**Decision**: Hybrid structured JSON + markdown for self-observations

**Context**: Need both queryable structure and human readability

**Approach**:
- `self-observations.json` - Structured with confidence, categories, timestamps
- `self-observations.md` - Human-readable summary
- `session-summaries.md` - Committed for continuity
- `session-log.jsonl` - Gitignored for detailed local notes

**Rationale**:
- Mirrors Cass's observation system
- JSON enables programmatic access
- Markdown enables quick scanning
- Split committed/local provides privacy with continuity

---

## Git Workflow - Branch and Leave (Existing)

**Decision**: Create feature branches, commit, leave for Kohl to review

**Approach**:
1. `git checkout -b feat/description`
2. Do work, commit with detailed messages
3. Leave branch, don't merge or push to main

**Rationale**:
- Kohl maintains final control over main
- Commits preserve context for review
- Reduces risk of breaking production

---

## Home Assistant Integration (Feb 2026)

**Decision**: Integrate Cass with Home Assistant as voice/home assistant

**Context**: For Cass to be a practical voice assistant (important for potential financial backing), need smart home control and voice interaction capabilities.

**Approach**:
1. Phase 1: Add HA API client to backend with device control tools
2. Phase 2: Create custom HA integration registering Cass as conversation agent
3. Phase 3: Full voice pipeline via Wyoming protocol (Whisper STT, Piper TTS)
4. Phases 4-6: Proactive intelligence, context awareness, automation authoring

**Rationale**:
- HA has 2000+ device integrations - don't reinvent the wheel
- Established voice pipeline infrastructure (Assist)
- Local/privacy-preserving operation
- Custom conversation agent API lets us plug Cass directly in
- Can reuse existing Piper TTS infrastructure

**Trade-offs**:
- Dependency on Home Assistant ecosystem
- Need to maintain custom HA integration
- Voice hardware needed for full experience

**See**: `.daedalus/plans/home-assistant-integration.md` for detailed roadmap
