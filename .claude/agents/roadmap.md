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
- `source_conversation_id`: Origin conversation that created the item
- `created_by`: Who created it ("cass", "daedalus", or "user")
- `created_at`, `updated_at`: ISO timestamps

## Common Queries

- **Find ready items for Daedalus**: Look in index.json for `status: "ready"` and `assigned_to: "daedalus"`
- **High priority bugs**: Filter index.json for `priority: "P0"` or `"P1"` and `item_type: "bug"`
- **Items from a conversation**: Search for `source_conversation_id` matching the conversation

## API Endpoints (for context)

```
GET    /roadmap/items              - List (with filters)
POST   /roadmap/items              - Create
GET    /roadmap/items/{id}         - Get one
PUT    /roadmap/items/{id}         - Update
POST   /roadmap/items/{id}/pick    - Claim for work
POST   /roadmap/items/{id}/complete - Mark done
```

Focus on answering the specific question asked. Return concise findings with item IDs and relevant details.
