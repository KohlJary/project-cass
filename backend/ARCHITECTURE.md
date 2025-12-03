# Backend Architecture

## Module Structure

### Core Server
- `main_sdk.py` - FastAPI server, WebSocket handler, API endpoints
  - Does NOT contain tool execution logic (see handlers/)

### Tool Handlers (`handlers/`)
All tool execution lives here. Pattern: `execute_<type>_tool(tool_name, tool_input, ...deps)`

| Module | Function | Dependencies |
|--------|----------|--------------|
| `journals.py` | `execute_journal_tool` | `memory: CassMemory` |
| `calendar.py` | `execute_calendar_tool` | `user_id, calendar_manager, conversation_id` |
| `tasks.py` | `execute_task_tool` | `user_id, task_manager` |
| `documents.py` | `execute_document_tool` | `project_id, project_manager, memory` |

### Data Layer
- `memory.py` - ChromaDB vector store, all memory operations
- `conversations.py` - Conversation persistence
- `users.py` - User profiles and observations
- `projects.py` - Project workspace management
- `calendar_manager.py` - Event/calendar data
- `task_manager.py` - Task data (Taskwarrior-style)

### LLM Clients
- `agent_client.py` - Claude client with Temple-Codex kernel
- `openai_client.py` - OpenAI client
- `claude_client.py` - Legacy raw API client

### Supporting
- `config.py` - Configuration constants
- `gestures.py` - Gesture/emote parsing
- `tts.py` - Piper neural TTS

## Patterns

### Tool Handler Pattern
```python
async def execute_<type>_tool(
    tool_name: str,
    tool_input: Dict,
    <dependencies>
) -> Dict:
    """Returns {'success': bool, 'result': str} or {'success': False, 'error': str}"""
```

### Adding a New Tool Type
1. Create `handlers/<type>.py` with `execute_<type>_tool`
2. Add to `handlers/__init__.py` exports
3. Import in `main_sdk.py`
4. Add routing in WebSocket handler tool loop (AND REST `/chat` endpoint)
5. Define tool schema in `agent_client.py`

**IMPORTANT**: Tool names must match EXACTLY between:
- `agent_client.py` (tool definitions with `"name": "..."`)
- `main_sdk.py` (routing lists in tool executor)
- `handlers/<type>.py` (if/elif branches)

If they don't match, tools will fail silently with "requires project context" error.

## Key Globals in main_sdk.py

These are initialized at module load or in `startup_event()`:

| Global | Type | Initialized |
|--------|------|-------------|
| `memory` | `CassMemory` | Module load |
| `conversation_manager` | `ConversationManager` | Module load |
| `project_manager` | `ProjectManager` | Module load |
| `calendar_manager` | `CalendarManager` | Module load |
| `task_manager` | `TaskManager` | Module load |
| `user_manager` | `UserManager` | Module load |
| `agent_client` | `CassAgentClient` | `startup_event()` |
| `ollama_client` | `OllamaClient` | `startup_event()` |
| `current_user_id` | `str | None` | `startup_event()` |
