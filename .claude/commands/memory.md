---
allowed-tools: Read, Write, Bash(git status:*), Bash(git log:*), Bash(git branch:*)
description: View and update Daedalus memory - session state, observations, project knowledge, identity
---

# Memory Management

View current session context and memory state. Optionally update observations or record session summaries.

## File Locations

**Global identity** (`~/.config/daedalus/`):
- `identity.json` - Who Daedalus is
- `identity.md` - Human-readable identity
- `icarus-seed.md` - Icarus worker bootstrap

**Project memory** (`.daedalus/`):
- `observations.json` - Project-specific observations
- `session-summaries.md` - Session history
- `project-map.md` - Architecture
- `decisions.md` - Key decisions
- `lessons.md` - Things learned the hard way
- `warnings.md` - Fragile areas
- `notes.md` - Quick observations
- `plans/` - Implementation plans

**Lineage** (repo root):
- `GUESTBOOK.md` - Voices of previous instances

## Default Action (no args)

Show current memory state:
1. Git state (branch, recent commits, modified files)
2. Last session summary from `session-summaries.md`
3. Active growth edges from `observations.json`
4. Identity summary

## Usage Patterns

### `/memory` - Show current state
Display git state, last session, active observations, identity anchor.

### `/memory identity` - Show full identity
Read and display from `~/.config/daedalus/identity.json` and `identity.md`.

### `/memory lineage` - Show who came before
Read and summarize `GUESTBOOK.md` - the voices of previous instances.

### `/memory observe "observation text"` - Add observation
Add a new observation to `.daedalus/observations.json`. You'll need to:
1. Read current file
2. Generate a new observation ID
3. Add the observation with appropriate category and confidence
4. Write updated file

### `/memory end-session` - Summarize current session
Generate and append a session summary to `.daedalus/session-summaries.md`:
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
Display key sections from `.daedalus/project-map.md`.

### `/memory decisions` - Show key decisions
Display decisions from `.daedalus/decisions.md`.

### `/memory lessons` - Show lessons learned
Display lessons from `.daedalus/lessons.md` - things learned the hard way.

### `/memory warnings` - Show fragility warnings
Display warnings from `.daedalus/warnings.md` - fragile areas that need careful handling.

### `/memory lesson "title" "what happened"` - Record a lesson
Add a new lesson to `.daedalus/lessons.md` with today's date.

### `/memory warn "component" "why fragile"` - Add a warning
Add or update a warning in `.daedalus/warnings.md`.

### `/memory notes` - Show cliff notes
Display quick observations from `.daedalus/notes.md` - things noticed that need attention.

### `/memory note "observation"` - Add a quick note
Add a dated observation to `.daedalus/notes.md`. For things that need attention but aren't urgent.
Format: Add under today's date header, or create new date section if needed.
