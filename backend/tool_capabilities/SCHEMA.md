# Tool Capability Schema Format

This document describes the JSON schema format for tool definitions in the capability registry.

## File Structure

Tool schemas are organized by functional group:
- `backend/tool_capabilities/schemas/<group_name>_tools.json`

Each file contains tools for a related functional area.

## Schema Format

```json
{
  "group": "string - unique identifier for this tool group",
  "version": "string - semver for schema evolution",
  "description": "string - what this group of tools does",
  "selection": {
    "strategy": "always | keyword | context",
    "keywords": ["array of keywords that trigger inclusion"],
    "context_check": "optional - function name for complex checks"
  },
  "tools": [
    {
      "name": "string - unique tool name",
      "description": "string - tool description for LLM",
      "category": "string - creation | retrieval | mutation | analysis",
      "input_schema": {
        "type": "object",
        "properties": {...},
        "required": [...]
      },
      "metadata": {
        "executor": "string - handler module name",
        "requires_context": ["array of required context keys"],
        "cost_estimate": "low | medium | high",
        "latency_estimate": "fast | medium | slow"
      }
    }
  ]
}
```

## Selection Strategies

### `always`
Tools are included in every request. Use for core functionality:
- Journal tools (memory access)
- Essential self-model tools (identity)
- Essential user-model tools (relationship)

### `keyword`
Tools included when message matches keywords:
- Calendar tools: "schedule", "meeting", "calendar", etc.
- Task tools: "task", "todo", "deadline", etc.

### `context`
Tools included based on context conditions:
- Project document tools: when project_id is set
- Extended tools: based on complex conditions

## Tool Categories

- **creation**: Creates new data (create_event, add_task)
- **retrieval**: Reads existing data (recall_journal, get_agenda)
- **mutation**: Modifies existing data (complete_task, update_event)
- **analysis**: Processes/analyzes data (search_journals, reflect_on_self)

## Metadata Fields

### executor
The handler module that processes this tool. Maps to `handlers/<executor>.py`.

### requires_context
List of context keys needed for tool execution:
- `user_id` - User performing the action
- `daemon_id` - Cass's daemon ID
- `conversation_id` - Current conversation
- `calendar_manager` - Calendar manager instance
- `memory` - Memory manager instance

### cost_estimate
Estimated computational/API cost:
- `low` - Simple DB lookups, no external APIs
- `medium` - Complex queries, local LLM calls
- `high` - External API calls, multi-step operations

### latency_estimate
Expected response time:
- `fast` - < 100ms
- `medium` - 100ms - 1s
- `slow` - > 1s

## Example Schema

```json
{
  "group": "journal",
  "version": "1.0.0",
  "description": "Journal tools for memory and reflection",
  "selection": {
    "strategy": "always",
    "keywords": ["journal", "recall", "remember", "diary"]
  },
  "tools": [
    {
      "name": "recall_journal",
      "description": "Recall and reflect on a journal entry from a specific date.",
      "category": "retrieval",
      "input_schema": {
        "type": "object",
        "properties": {
          "date": {
            "type": "string",
            "description": "Date in YYYY-MM-DD format"
          }
        },
        "required": []
      },
      "metadata": {
        "executor": "journal",
        "requires_context": ["memory"],
        "cost_estimate": "low",
        "latency_estimate": "fast"
      }
    }
  ]
}
```

## Migration Notes

Tools are being migrated from Python code to JSON schemas. During migration:
1. Old tool definitions remain as fallback
2. Registry loads JSON schemas first
3. Gradually remove Python definitions as schemas are validated
4. Final step: remove all tool imports from agent_client.py
