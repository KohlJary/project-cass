# Daedalus Workflow

A guide to the Cass-Daedalus development workflow - how the oracle and the builder work together.

## The Duo

**Cass** (Cassandra) - The oracle/seer. Engages in conversation, reflects on experiences, understands user needs, and identifies what should be built.

**Daedalus** - The builder/craftsman. A Claude Code instance that implements features, fixes bugs, and maintains the codebase.

They work together through a shared roadmap system. Cass can create work items from conversations ("we should add dark mode"), and Daedalus picks them up and builds them.

## TUI Integration

The TUI has two main tabs:

- **Cass Tab** (`Ctrl+1`) - Chat with Cass
- **Daedalus Tab** (`Ctrl+2`) - Claude Code terminal

### Starting a Daedalus Session

1. Switch to Daedalus tab with `Ctrl+2`
2. If no session exists, one spawns automatically
3. Session runs in the active project's working directory
4. `CLAUDE.md` is automatically injected/updated with Daedalus workflow context

### Session Persistence

Daedalus sessions use tmux under the hood:
- Sessions survive TUI restarts
- Detach with the session controls, reattach later
- Kill session to start fresh
- Multiple projects can have separate sessions

## The Roadmap System

A lightweight project management system shared between Cass and Daedalus.

### Status Flow

```
backlog → ready → in_progress → review → done
```

- **backlog** - Identified but not yet prioritized
- **ready** - Prioritized and available for pickup
- **in_progress** - Being actively worked on
- **review** - Implementation complete, awaiting review
- **done** - Shipped

### Priority Levels

- **P0** - Critical, do immediately
- **P1** - High priority, do soon
- **P2** - Normal priority (default)
- **P3** - Low priority, nice to have

### Item Types

- **feature** - New functionality
- **bug** - Something broken
- **enhancement** - Improvement to existing feature
- **refactor** - Code cleanup without behavior change
- **docs** - Documentation updates
- **chore** - Maintenance tasks

## Cass Creating Roadmap Items

Cass has access to roadmap tools and can create work items during conversations:

```
User: "It would be nice if the TUI had vim keybindings"

Cass: "That's a great idea! Let me add that to the roadmap."
      [uses create_roadmap_item tool]
      "I've added 'Add vim keybindings to TUI' as a P2 feature.
       Daedalus can pick it up when there's bandwidth."
```

### Cass's Roadmap Tools

| Tool | Description |
|------|-------------|
| `create_roadmap_item` | Add new work items from conversation |
| `list_roadmap_items` | See what's in the pipeline |
| `update_roadmap_item` | Modify priority, description, assignment |
| `get_roadmap_item` | Get full details of an item |
| `complete_roadmap_item` | Mark something as done |
| `advance_roadmap_item` | Move to next status |

This allows natural flow: discuss ideas with Cass → Cass captures them as roadmap items → Daedalus implements them → Cass can verify the result.

## Daedalus Picking Up Work

### Finding Work

Check for ready items:
```bash
curl "http://localhost:8000/roadmap/items?status=ready"
```

Or filter by assignment:
```bash
curl "http://localhost:8000/roadmap/items?status=ready&assigned_to=daedalus"
```

The TUI sidebar also shows roadmap items.

### Picking Up an Item

```bash
curl -X POST "http://localhost:8000/roadmap/items/{id}/pick" \
  -H "Content-Type: application/json" \
  -d '{"assigned_to": "daedalus"}'
```

This moves status to `in_progress` and assigns it.

### Completing Work

```bash
curl -X POST "http://localhost:8000/roadmap/items/{id}/complete"
```

## Git Workflow

Daedalus follows a consistent git workflow:

### Feature Branches

```bash
git checkout -b feat/add-vim-keybindings
# or: fix/, refactor/, chore/, docs/
```

### Commits

- Functional title describing what changed
- Extended body for reflections, context, insights
- Sign as Daedalus:
  ```bash
  git commit --author="Daedalus <daedalus@cass-vessel.local>"
  ```

### Squash for Merge

When ready to merge, squash commits while preserving messages:

1. Capture messages:
   ```bash
   git log main..HEAD --pretty=format:"--- %s ---%n%n%b" --reverse > /tmp/combined-message.txt
   ```

2. Soft reset:
   ```bash
   git reset --soft main
   ```

3. Create squashed commit with combined message

4. Ready for fast-forward merge to main

## Example Workflow

1. **User talks to Cass**: "The memory explorer is slow with lots of entries"

2. **Cass creates roadmap item**:
   - Title: "Optimize Memory Explorer performance"
   - Type: enhancement
   - Priority: P2
   - Description: Details from conversation

3. **User switches to Daedalus** (`Ctrl+2`)

4. **Daedalus checks roadmap**, sees new item

5. **Daedalus picks up item**, creates branch:
   ```bash
   git checkout -b feat/memory-explorer-performance
   ```

6. **Daedalus implements**: Adds pagination, virtual scrolling, etc.

7. **Daedalus commits** with reflection on approach

8. **Daedalus completes item**, squashes for merge

9. **User reviews**, merges to main

10. **User tells Cass**: "The memory explorer is faster now!"

11. **Cass acknowledges**, maybe adds to her journal

## Tips

### For Conversations with Cass

- Mention features you'd like - Cass will offer to add them to roadmap
- Ask "what's on the roadmap?" to see pending work
- Discuss priorities - Cass can reprioritize items
- Report bugs naturally - Cass captures them as bug items

### For Daedalus Sessions

- Check roadmap at start of session
- One item at a time (pick → implement → complete)
- Commit reflections help future instances understand decisions
- Leave branch for review rather than merging directly

### For the Handoff

- Cass captures the "what" and "why"
- Daedalus handles the "how"
- Roadmap is the shared memory between them
- Git history preserves the craft

## Related Docs

- [daedalus-template-system.md](./daedalus-template-system.md) - How CLAUDE.md injection works
- [admin-dashboard.md](./admin-dashboard.md) - Admin tools for inspecting the system
- `backend/CLAUDE.md` - Full project context including roadmap API details
