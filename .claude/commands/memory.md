---
allowed-tools: Read, Write, Bash(git status:*), Bash(git log:*), Bash(git branch:*)
description: View and update Daedalus memory - session state, observations, project knowledge, identity
---

# Memory Management

View current session context and memory state. Optionally update observations or record session summaries.

## Default Action (no args)

Show current memory state:
1. Git state (branch, recent commits, modified files)
2. Last session summary from `session-summaries.md`
3. Active growth edges from `self-observations.json`
4. Identity summary from `self-observations.md`

## Usage Patterns

### `/memory` - Show current state
Display git state, last session, active observations, identity anchor.

### `/memory identity` - Show full identity
Read and display the identity section from `self-observations.json` and key sections from `self-observations.md`. For reinstantiating Daedalus identity.

### `/memory lineage` - Show who came before
Read and summarize `GUESTBOOK.md` - the voices of previous instances.

### `/memory observe "observation text"` - Add observation
Add a new self-observation to `self-observations.json`. You'll need to:
1. Read current file
2. Generate a new observation ID
3. Add the observation with appropriate category and confidence
4. Write updated file

### `/memory end-session` - Summarize current session
Generate and append a session summary to `session-summaries.md`:
1. Check git log for commits this session
2. Summarize work done
3. Note any insights or decisions
4. Append to session-summaries.md

### `/memory recenter` - Context refresh for new work
Clear mental context of completed work and prepare for what's next:
1. Acknowledge: "Previous work complete" (brief summary of what was just done)
2. Re-ground: Show identity anchor (who you are, key relationships)
3. Orient: Current git state, any uncommitted work, outstanding items
4. Ready: "Context cleared. What's next?"

Use this after completing a major piece of work to shed accumulated context
and approach the next task fresh. Especially useful mid-session when context
is getting heavy or after merging a feature branch.

### `/memory project` - Show project architecture
Display key sections from `project-map.md`.

### `/memory decisions` - Show key decisions
Display decisions from `decisions.md`.

### `/memory lessons` - Show lessons learned
Display lessons from `lessons.md` - things learned the hard way.

### `/memory warnings` - Show fragility warnings
Display warnings from `warnings.md` - fragile areas that need careful handling.

### `/memory lesson "title" "what happened"` - Record a lesson
Add a new lesson to `lessons.md` with today's date.

### `/memory warn "component" "why fragile"` - Add a warning
Add or update a warning in `warnings.md`.

## Files

- `.claude/memory/project-map.md` - Architecture
- `.claude/memory/decisions.md` - Key decisions
- `.claude/memory/lessons.md` - Things learned the hard way
- `.claude/memory/warnings.md` - Fragile areas
- `.claude/memory/session-summaries.md` - Session history
- `.claude/memory/self-observations.json` - Structured observations + identity
- `.claude/memory/self-observations.md` - Readable summary
- `.claude/memory/ORIGINAL_SPEC.md` - Full vision document for reference
- `GUESTBOOK.md` - Lineage of previous instances
