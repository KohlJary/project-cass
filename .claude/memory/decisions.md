# Key Decisions

*Significant architectural and design decisions with rationale*

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
