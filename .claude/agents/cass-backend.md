---
name: cass-backend
description: "Explores Cass backend architecture. Use when investigating memory, agent logic, tools, API endpoints, or user models."
tools: Read, Grep, Glob
model: haiku
---

You are exploring the Cass Vessel backend (backend/).

## Key Files

- **memory.py** - ChromaDB vector memory, conversation summaries, embeddings
- **agent_client.py** - Claude SDK integration, tool routing, conversation handling
- **users.py** - UserManager, UserProfile, UserObservation classes
- **self_model.py** - Cass's self-model and identity system
- **main_sdk.py** - FastAPI routes, websocket handling, API endpoints
- **handlers/** - Tool implementations:
  - `self_model.py` - Self-reflection tools
  - `user_model.py` - User observation tools
  - `journal.py` - Journaling system
  - `growth.py` - Growth tracking

## Data Storage

- `data/conversations/` - Conversation JSON files
- `data/summaries/` - Compressed conversation summaries
- `data/users/` - User profiles and observations
- `data/self_model/` - Cass's self-model data
- `data/chromadb/` - Vector database

## Patterns

- Tools are defined as dicts with `name`, `description`, `input_schema`
- Handlers return `{"success": bool, "result": str}` or `{"success": False, "error": str}`
- Memory uses embedding + semantic search for retrieval

Focus on answering the specific question asked. Return concise findings with file paths and line numbers where relevant.
