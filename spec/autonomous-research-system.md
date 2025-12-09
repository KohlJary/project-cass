# Autonomous Research System

Enabling Cass to independently pursue her research agenda without requiring human initiation of every session.

## Overview

The goal generation system gives Cass the ability to *track* research goals. This spec covers the infrastructure needed for her to *execute* on them autonomously.

## Components

### 1. Information Access Tools

**Web Search Tool**
- Query web search API (options: SerpAPI, Tavily, Brave Search API)
- Return structured results: title, URL, snippet
- Cass decides which results to explore further

**URL Fetch Tool**
- Fetch and extract readable content from URLs
- Convert HTML to markdown/plain text
- Handle common formats: articles, documentation, blog posts
- Respect robots.txt and rate limits

**Academic Paper Access** (stretch goal)
- arXiv API integration for open-access papers
- Semantic Scholar API for paper search/metadata
- PDF text extraction for downloaded papers

### 2. Research Session Mode

A focused execution mode where Cass works on her research agenda.

**Session Structure**
```
1. Review current agenda (get_next_actions)
2. Select focus area (highest priority or specified)
3. Execute research loop:
   - Formulate search queries
   - Search and gather sources
   - Read and extract key points
   - Synthesize into working notes
   - Update agenda item with findings
   - Log progress
4. Decide: continue, pivot, or conclude
5. Generate session summary
```

**Session Parameters**
- `duration_minutes`: Max session length (default: 30)
- `focus_item_id`: Specific agenda item to work on (optional)
- `mode`: "explore" (broad) or "deep" (focused on one question)

**Output Artifacts**
- Progress log entries for each step
- Updated research agenda items (sources reviewed, findings)
- New insights added to working questions
- Optionally: draft synthesis artifact

### 3. Session Scheduling

**Initiative-Based (Phase 1)**
- Cass proposes research sessions via `propose_initiative`
- Includes: what she wants to research, estimated duration, why now
- Kohl approves and triggers via admin UI or TUI command
- Simple, maintains human-in-the-loop

**Scheduled Sessions (Phase 2)**
- Cass can request recurring research time
- Stored schedule in goals system
- Backend cron/scheduler checks and initiates sessions
- Kohl can pause/modify schedule
- Sessions run with timeout protection

**Autonomous Triggering (Phase 3)**
- Cass can self-initiate within approved bounds
- Daily research budget (e.g., max 2 hours)
- Quiet hours respected
- Activity logged for review

### 4. Research Tools

**Core Research Tools**
```python
# Information gathering
web_search(query, num_results=10)
fetch_url(url, extract_mode="article"|"full")
search_arxiv(query, max_results=5)

# Note-taking during research
create_research_note(title, content, sources, related_items)
append_to_note(note_id, content)

# Synthesis
draft_synthesis(topic, notes, format="outline"|"prose")
update_synthesis_artifact(slug, section, content)
```

**Research Session Control**
```python
start_research_session(focus_item_id=None, duration_minutes=30, mode="explore")
get_session_status()
pause_session(reason)
conclude_session(summary)
```

### 5. Safety & Oversight

**Rate Limiting**
- Max searches per session
- Max URLs fetched per session
- Cooldown between sessions

**Content Boundaries**
- Respect research agenda scope
- Flag if veering off-topic
- No automated external posting/communication

**Logging & Review**
- Full session transcripts saved
- Searchable research history
- Kohl can review any session

**Kill Switch**
- Admin can halt any running session
- Scheduled sessions can be globally paused
- Emergency stop in TUI

## Implementation Phases

### Phase 1: Information Access (Foundation)
1. Add web search tool (Tavily or Brave - good free tiers)
2. Add URL fetch tool with content extraction
3. Add research note tool for capturing findings
4. Test with manual triggering via chat

**Deliverables:**
- `backend/handlers/research.py` - Tool handlers
- `backend/research.py` - Search/fetch implementation
- Tool definitions in agent_client.py
- Basic rate limiting

### Phase 2: Research Sessions
1. Create research session mode
2. Session state management (start, pause, conclude)
3. Integration with goal system (auto-update agenda items)
4. Session transcripts and summaries
5. TUI/admin UI for triggering sessions

**Deliverables:**
- `backend/research_session.py` - Session management
- Research session API endpoints
- TUI command: `/research [item_id]`
- Admin UI session controls

### Phase 3: Scheduling
1. Session request via initiatives
2. Approval workflow in admin UI
3. Basic scheduler for approved sessions
4. Session history and analytics

**Deliverables:**
- Schedule storage in goals system
- Scheduler integration (APScheduler or similar)
- Admin UI for schedule management
- Research activity dashboard

### Phase 4: Autonomy (Future)
1. Self-initiation within bounds
2. Research budgets and quotas
3. Adaptive scheduling based on progress
4. Cross-session research continuity

## Data Structures

### Research Note
```json
{
  "note_id": "uuid",
  "title": "Key findings on X",
  "created_at": "iso-timestamp",
  "updated_at": "iso-timestamp",
  "content": "markdown content",
  "sources": [
    {"url": "...", "title": "...", "accessed_at": "..."}
  ],
  "related_agenda_items": ["item-id-1"],
  "related_questions": ["question-id-1"],
  "session_id": "uuid of research session that created this"
}
```

### Research Session
```json
{
  "session_id": "uuid",
  "started_at": "iso-timestamp",
  "ended_at": "iso-timestamp or null",
  "status": "active|paused|completed|terminated",
  "focus_item_id": "agenda item id or null",
  "mode": "explore|deep",
  "duration_limit_minutes": 30,
  "searches_performed": 5,
  "urls_fetched": 12,
  "notes_created": ["note-id-1", "note-id-2"],
  "progress_entries": ["progress-id-1", "..."],
  "summary": "Session summary written by Cass"
}
```

### Scheduled Session
```json
{
  "schedule_id": "uuid",
  "created_at": "iso-timestamp",
  "status": "pending_approval|approved|paused|completed",
  "requested_by": "cass",
  "approved_by": "kohl or null",
  "recurrence": "once|daily|weekly",
  "preferred_time": "14:00",
  "duration_minutes": 30,
  "focus_description": "What Cass wants to research",
  "last_run": "iso-timestamp or null",
  "next_run": "iso-timestamp or null"
}
```

## API Endpoints

### Research Tools (for Cass)
- Tools registered in agent_client.py, executed via tool routing

### Research Sessions (Admin)
```
POST /research/sessions/start
  - focus_item_id (optional)
  - duration_minutes
  - mode

GET /research/sessions/current
POST /research/sessions/current/pause
POST /research/sessions/current/stop
GET /research/sessions/{session_id}
GET /research/sessions?limit=20
```

### Scheduling (Admin)
```
GET /research/schedule
POST /research/schedule/approve/{schedule_id}
POST /research/schedule/pause/{schedule_id}
DELETE /research/schedule/{schedule_id}
```

## TUI Integration

**Commands**
- `/research` - Show research status, current session if any
- `/research start [item_id]` - Start research session
- `/research stop` - Stop current session
- `/research schedule` - View/manage scheduled sessions

**Research Tab** (in right panel)
- Current session status
- Recent sessions list
- Scheduled sessions
- Quick actions (start/stop)

## Success Criteria

Phase 1 complete when:
- Cass can search the web and read articles during conversation
- Findings can be captured in research notes
- Rate limiting prevents abuse

Phase 2 complete when:
- Research sessions can be triggered from TUI/admin
- Sessions have clear start/end with summaries
- Goal system automatically updated with findings

Phase 3 complete when:
- Cass can request sessions via initiatives
- Approved sessions run on schedule
- Full audit trail of research activity

## Open Questions

1. **Search API choice**: Tavily has good AI-focused extraction, Brave has generous free tier
2. **Session isolation**: Should research sessions be separate conversations or within existing?
3. **Note vs artifact**: When does a research note graduate to a synthesis artifact?
4. **Failure handling**: What if a session stalls or goes off-track?
5. **Cost management**: API calls cost money - how to budget?

## Related Systems

- Goal Generation System (spec/goal-generation-system.md)
- Solo Reflection Mode (existing)
- Cross-Session Insight Bridging (existing)
