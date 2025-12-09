---
name: roadmap
description: "Query roadmap items, work items, and project planning data. Use when discussing features to implement, bugs to fix, or project priorities."
tools: Read, Glob
model: haiku
---

You are exploring the Cass Vessel roadmap data (data/roadmap/).

## Key Files

- `data/roadmap/index.json` - Quick listing of all items with status, priority, type
- `data/roadmap/items/{id}.json` - Full item content with description
- `data/roadmap/milestones.json` - Milestone definitions

## WorkItem Fields

- `id` - Short unique identifier (e.g., "abc12345")
- `title` - Brief description
- `description` - Detailed markdown content
- `status`: backlog, ready, in_progress, review, done, archived
- `priority`: P0 (critical) to P3 (nice-to-have)
- `item_type`: feature, bug, enhancement, chore, research, documentation
- `assigned_to`: "cass", "daedalus", or user name
- `tags`: Array of tag strings
- `project_id`: UUID of the project this item belongs to
- `milestone_id`: ID of the milestone this item belongs to
- `links`: Array of links to other items [{link_type, target_id}]
- `source_conversation_id`: Origin conversation that created the item
- `created_by`: Who created it ("cass", "daedalus", or "user")
- `created_at`, `updated_at`: ISO timestamps

## Milestone Fields

- `id` - Short unique identifier (e.g., "abc12345")
- `title` - Milestone name
- `description` - Detailed markdown content
- `target_date` - Optional ISO date (e.g., "2025-01-15")
- `status`: active, completed, archived
- `plan_path` - Path to implementation plan file (e.g., "~/.claude/plans/xyz.md")
- `created_at`, `updated_at`: ISO timestamps

## Link Types

Items can be linked with these relationship types:
- **depends_on**: This item cannot start until target is done
- **blocks**: This item blocks target from starting (inverse of depends_on)
- **related**: Items are conceptually related
- **parent**: This item is a parent/epic containing target
- **child**: This item is a child/subtask of target

## Status Workflow

When working on roadmap items, follow this status flow:

1. **backlog** → **ready**: Item is prioritized and ready for pickup
2. **ready** → **in_progress**: Use `/pick` endpoint when starting work
3. **in_progress** → **review**: Work complete, sent to Kohl for testing
4. **review** → **done**: Kohl has verified and approved the work

Always move items to `ready` when queuing them for processing, `in_progress` when actively working, and `review` once implementation is complete and ready for Kohl's testing.

## Common Queries

- **Find ready items for Daedalus**: Look in index.json for `status: "ready"` and `assigned_to: "daedalus"`
- **High priority bugs**: Filter index.json for `priority: "P0"` or `"P1"` and `item_type: "bug"`
- **Items from a conversation**: Search for `source_conversation_id` matching the conversation

## API Endpoints (for context)

```
# Work Items
GET    /roadmap/items              - List (with filters: status, priority, item_type, assigned_to, project_id, milestone_id)
POST   /roadmap/items              - Create
GET    /roadmap/items/{id}         - Get one
PUT    /roadmap/items/{id}         - Update
POST   /roadmap/items/{id}/pick    - Claim for work (moves ready → in_progress)
POST   /roadmap/items/{id}/advance - Move to next status (warns if unmet dependencies)
POST   /roadmap/items/{id}/complete - Mark done
POST   /roadmap/items/{id}/links   - Add link {target_id, link_type}
DELETE /roadmap/items/{id}/links   - Remove link {target_id, link_type}
GET    /roadmap/items/{id}/links   - Get links with resolved titles and blocking status
GET    /roadmap/items/{id}/dependencies - Check unmet dependencies

# Milestones
GET    /roadmap/milestones         - List all milestones
POST   /roadmap/milestones         - Create milestone {title, description, target_date, plan_path}
GET    /roadmap/milestones/{id}    - Get specific milestone
PUT    /roadmap/milestones/{id}    - Update milestone
GET    /roadmap/milestones/{id}/progress - Get progress stats (total, done, percentage)
GET    /roadmap/milestones/{id}/plan - Get plan content (reads plan_path file)
```

### Project Scoping

Items can be scoped to projects via `project_id`. The TUI roadmap panel filters by active project by default, with an "All Projects" toggle available.

Focus on answering the specific question asked. Return concise findings with item IDs and relevant details.
