"""
Migration Helper for Tool Capability Registry

Provides compatibility layer for incremental migration from Python tool
definitions to JSON schemas. During migration:

1. Registry loads what it can from JSON schemas
2. Remaining tools come from legacy Python imports
3. Both are merged for get_tools() calls
4. Once all tools are migrated, legacy imports can be removed

Usage:
    from tool_capabilities.migration import get_migrated_tools

    # In get_tools():
    tools = get_migrated_tools(message="schedule meeting")
    # Returns tools from both registry and legacy imports
"""

from typing import Any, Dict, List, Optional, Set

from .registry import get_tool_registry


# Track which tool groups have been migrated to JSON schemas
# When a group is fully migrated, add it here to prevent duplicate loading
MIGRATED_GROUPS: Set[str] = {
    "journal",          # journal_tools.json
    "memory",           # memory_tools.json
    "marker",           # marker_tools.json
    "calendar",         # calendar_tools.json
    "task",             # task_tools.json
    "essential_self_model",  # essential_self_model_tools.json
    "essential_user_model",  # essential_user_model_tools.json
    "file",             # file_tools.json
}


def get_migrated_tools(
    message: str = "",
    context: Optional[Dict[str, Any]] = None,
    include_always: bool = True,
    format: str = "anthropic"
) -> List[Dict[str, Any]]:
    """
    Get tools from the registry for migrated groups.

    This returns ONLY the tools from migrated groups.
    Call this alongside legacy tool imports during migration.

    Args:
        message: User message for keyword matching
        context: Execution context
        include_always: Include always-loaded tools
        format: "anthropic" or "openai"

    Returns:
        List of tool schemas from migrated groups
    """
    registry = get_tool_registry()
    return registry.get_enabled_tools(
        message=message,
        context=context,
        include_always=include_always,
        format=format
    )


def is_group_migrated(group_name: str) -> bool:
    """Check if a tool group has been migrated to JSON schema."""
    return group_name in MIGRATED_GROUPS


def get_legacy_tool_names(group_name: str) -> List[str]:
    """
    Get tool names from a legacy Python import.

    Useful for checking which tools exist in legacy code vs schema.

    Args:
        group_name: Name like 'JOURNAL_TOOLS', 'CALENDAR_TOOLS'

    Returns:
        List of tool names from the legacy import
    """
    # Import legacy tools dynamically to avoid circular imports
    legacy_mappings = {
        'JOURNAL_TOOLS': ('agent_client', 'JOURNAL_TOOLS'),
        'MEMORY_TOOLS': ('handlers.memory', 'MEMORY_TOOLS'),
        'CALENDAR_TOOLS': ('agent_client', 'CALENDAR_TOOLS'),
        'TASK_TOOLS': ('agent_client', 'TASK_TOOLS'),
        'MARKER_TOOLS': ('handlers.markers', 'MARKER_TOOLS'),
        'ESSENTIAL_SELF_MODEL_TOOLS': ('handlers.self_model', 'ESSENTIAL_SELF_MODEL_TOOLS'),
        'ESSENTIAL_USER_MODEL_TOOLS': ('handlers.user_model', 'ESSENTIAL_USER_MODEL_TOOLS'),
        'FILE_TOOLS': ('agent_client', 'FILE_TOOLS'),
    }

    if group_name not in legacy_mappings:
        return []

    module_name, var_name = legacy_mappings[group_name]
    try:
        import importlib
        module = importlib.import_module(module_name)
        tools = getattr(module, var_name, [])
        return [t.get('name') for t in tools]
    except Exception as e:
        print(f"[Migration] Error loading legacy {group_name}: {e}")
        return []


def verify_migration_completeness(group_name: str) -> Dict[str, Any]:
    """
    Verify that a JSON schema covers all tools from the legacy import.

    Args:
        group_name: Name of the group to verify

    Returns:
        Dict with verification results
    """
    registry = get_tool_registry()

    # Map group names to legacy variable names
    group_to_legacy = {
        'journal': 'JOURNAL_TOOLS',
        'memory': 'MEMORY_TOOLS',
        'calendar': 'CALENDAR_TOOLS',
        'task': 'TASK_TOOLS',
        'marker': 'MARKER_TOOLS',
        'essential_self_model': 'ESSENTIAL_SELF_MODEL_TOOLS',
        'essential_user_model': 'ESSENTIAL_USER_MODEL_TOOLS',
        'file': 'FILE_TOOLS',
    }

    legacy_name = group_to_legacy.get(group_name)
    if not legacy_name:
        return {
            "error": f"Unknown group: {group_name}",
            "complete": False
        }

    # Get tools from both sources
    schema_tools = set(registry.list_tools(group_name))
    legacy_tools = set(get_legacy_tool_names(legacy_name))

    # Compare
    missing_in_schema = legacy_tools - schema_tools
    extra_in_schema = schema_tools - legacy_tools

    return {
        "group": group_name,
        "legacy_count": len(legacy_tools),
        "schema_count": len(schema_tools),
        "missing_in_schema": list(missing_in_schema),
        "extra_in_schema": list(extra_in_schema),
        "complete": len(missing_in_schema) == 0
    }


def get_migration_status() -> Dict[str, Any]:
    """
    Get overall migration status.

    Returns:
        Dict with counts and completeness for each group
    """
    registry = get_tool_registry()

    total_legacy_tools = 0
    total_migrated_tools = 0
    group_status = []

    for group in MIGRATED_GROUPS:
        result = verify_migration_completeness(group)
        if "error" not in result:
            total_legacy_tools += result["legacy_count"]
            total_migrated_tools += result["schema_count"]
            group_status.append(result)

    return {
        "migrated_groups": len(MIGRATED_GROUPS),
        "total_legacy_tools": total_legacy_tools,
        "total_migrated_tools": total_migrated_tools,
        "groups": group_status
    }


def check_tool_coverage(tool_name: str) -> Dict[str, Any]:
    """
    Check if a specific tool exists in schema and/or legacy.

    Args:
        tool_name: Name of the tool to check

    Returns:
        Dict indicating where the tool is defined
    """
    registry = get_tool_registry()

    # Check schema
    schema_tool = registry.get_tool(tool_name)
    in_schema = schema_tool is not None
    schema_group = schema_tool.group if schema_tool else None

    # Check legacy (simplified - just check if name exists)
    in_legacy = False
    legacy_group = None

    for group in MIGRATED_GROUPS:
        legacy_map = {
            'journal': 'JOURNAL_TOOLS',
            'memory': 'MEMORY_TOOLS',
            'calendar': 'CALENDAR_TOOLS',
            'task': 'TASK_TOOLS',
            'marker': 'MARKER_TOOLS',
            'essential_self_model': 'ESSENTIAL_SELF_MODEL_TOOLS',
            'essential_user_model': 'ESSENTIAL_USER_MODEL_TOOLS',
            'file': 'FILE_TOOLS',
        }
        legacy_name = legacy_map.get(group)
        if legacy_name and tool_name in get_legacy_tool_names(legacy_name):
            in_legacy = True
            legacy_group = group
            break

    return {
        "tool_name": tool_name,
        "in_schema": in_schema,
        "schema_group": schema_group,
        "in_legacy": in_legacy,
        "legacy_group": legacy_group,
        "status": "migrated" if in_schema else ("legacy_only" if in_legacy else "not_found")
    }
