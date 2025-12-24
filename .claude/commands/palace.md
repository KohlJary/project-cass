---
allowed-tools: Read, Glob, Grep
description: Navigate Mind Palace - query entities, explore codebase architecture, check drift
---

# Mind Palace Navigation

Query the Mind Palace for codebase knowledge. Entities are keepers of subsystem knowledge with HOW/WHY/WATCH_OUT topics.

## File Locations

- `.mind-palace/palace.yaml` - Palace index (entities list)
- `.mind-palace/entities/*.yaml` - Entity definitions with topics
- `backend/mind_palace/` - Palace implementation

## Usage

### `/palace` - Show available entities
List all 22 keeper entities and their domains.

### `/palace ask <Entity> about <topic>` - Query an entity
Ask a keeper about their domain knowledge.

Examples:
- `/palace ask MemoryKeeper about semantic search`
- `/palace ask SchedulingKeeper about day phases`
- `/palace ask AgentKeeper about tool execution`

### `/palace topics <Entity>` - Show entity's topics
List what topics an entity knows about.

### `/palace find <keyword>` - Search for relevant entity
Find which entity knows about a concept.

## How to Execute

### For `/palace` (list entities):
1. Read `.mind-palace/palace.yaml` to get entity list
2. For each entity, read `.mind-palace/entities/<name>.yaml`
3. Display: Entity name, location, role summary, available topics

### For `/palace ask <Entity> about <topic>`:
1. Read `.mind-palace/entities/<entity>.yaml` (use slug or lowercase name)
2. Find the topic in the `topics` list (partial match OK)
3. Display the topic's `how`, `why`, and `watch_out` fields
4. If topic not found, list available topics for that entity

### For `/palace go <path>`:
Navigate by slug path. Sub-palaces are scoped to directories:
- `backend/memory/memory-add-message` - Full path in backend sub-palace
- `admin-frontend/components/sidebar` - Path in admin-frontend sub-palace
- `memory-add-message` - Room slug only (searches current/all sub-palaces)

Sub-palaces: `backend/`, `admin-frontend/`, `tui-frontend/`, `mobile-frontend/`

### For `/palace topics <Entity>`:
1. Read `.mind-palace/entities/<entity>.yaml`
2. List all topic names from the `topics` array

### For `/palace find <keyword>`:
1. Grep through `.mind-palace/entities/*.yaml` for the keyword
2. Report which entities mention it and in what context

## Entity YAML Format

```yaml
name: MemoryKeeper
location: backend/memory/
role: "Guardian of hierarchical vector memory..."
personality: "Ancient and wise..."
topics:
  - name: semantic search
    how: "Vector-based memory using ChromaDB..."
    why: "Finding relevant context requires semantic understanding..."
    watch_out: "Attractor basins use specific marker format..."
```

## Available Entities

Memory & State:
- MemoryKeeper - ChromaDB, summaries, retrieval
- ConversationKeeper - Message persistence, threading
- SelfModelKeeper - Identity, observations, growth edges

Scheduling:
- SchedulingKeeper - Day phases, decision engine
- SynkratosKeeper - Autonomous scheduler orchestration

Agent & Tools:
- AgentKeeper - Claude SDK, tool execution, Temple-Codex
- ToolRouterKeeper - Tool dispatch, handlers

And 15 more... Run `/palace` to see all.
