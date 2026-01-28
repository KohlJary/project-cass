"""
Tool Capability Registry

Central registry for tool schemas and capability control.
Replaces scattered tool imports with data-driven management.

This module provides:
1. Schema loading from JSON files
2. Dynamic tool selection (keyword matching, context checks)
3. Capability control (disable/enable tools - Phase 0 blacklist integration)
4. Usage analytics tracking

Architecture:
- Tool schemas defined in JSON (backend/tool_capabilities/schemas/*.json)
- Registry loads and caches schemas at startup
- Tools selected based on message keywords and context
- Blacklist functionality integrated for procedural self-awareness
"""

import json
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, FrozenSet, List, Optional, Set, Union


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ToolSchema:
    """Represents a single tool schema."""
    name: str
    description: str
    input_schema: Dict[str, Any]
    group: str
    category: str = "retrieval"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_anthropic_format(self) -> Dict[str, Any]:
        """Convert to Anthropic tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema
        }

    def to_openai_format(self) -> Dict[str, Any]:
        """Convert to OpenAI function format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema
            }
        }


@dataclass
class ToolGroup:
    """Represents a group of related tools."""
    name: str
    version: str
    description: str
    selection_strategy: str  # "always", "keyword", "context"
    keywords: FrozenSet[str]
    tools: List[ToolSchema]
    context_check: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolGroup":
        """Create ToolGroup from parsed JSON."""
        selection = data.get("selection", {})
        keywords = frozenset(selection.get("keywords", []))

        tools = []
        for tool_data in data.get("tools", []):
            tool = ToolSchema(
                name=tool_data["name"],
                description=tool_data["description"],
                input_schema=tool_data.get("input_schema", {"type": "object", "properties": {}}),
                group=data["group"],
                category=tool_data.get("category", "retrieval"),
                metadata=tool_data.get("metadata", {})
            )
            tools.append(tool)

        return cls(
            name=data["group"],
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            selection_strategy=selection.get("strategy", "keyword"),
            keywords=keywords,
            tools=tools,
            context_check=selection.get("context_check")
        )


# =============================================================================
# SCHEMA LOADER
# =============================================================================

class SchemaLoader:
    """Loads and caches tool schemas from JSON files."""

    def __init__(self, schema_dir: Path):
        self.schema_dir = schema_dir
        self._groups: Dict[str, ToolGroup] = {}
        self._tools: Dict[str, ToolSchema] = {}
        self._loaded = False

    def load_all(self) -> int:
        """
        Load all schema files from disk.

        Returns:
            Number of tools loaded
        """
        if not self.schema_dir.exists():
            print(f"[Registry] Schema directory not found: {self.schema_dir}")
            return 0

        tool_count = 0

        for schema_file in self.schema_dir.glob("*.json"):
            try:
                with open(schema_file, 'r') as f:
                    data = json.load(f)

                group = ToolGroup.from_dict(data)
                self._groups[group.name] = group

                for tool in group.tools:
                    self._tools[tool.name] = tool
                    tool_count += 1

                print(f"[Registry] Loaded {len(group.tools)} tools from {group.name}")

            except json.JSONDecodeError as e:
                print(f"[Registry] JSON error in {schema_file}: {e}")
            except KeyError as e:
                print(f"[Registry] Missing required field in {schema_file}: {e}")
            except Exception as e:
                print(f"[Registry] Error loading {schema_file}: {e}")

        self._loaded = True
        return tool_count

    def get_tool(self, name: str) -> Optional[ToolSchema]:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_group(self, name: str) -> Optional[ToolGroup]:
        """Get a tool group by name."""
        return self._groups.get(name)

    def get_all_groups(self) -> List[ToolGroup]:
        """Get all loaded tool groups."""
        return list(self._groups.values())

    def get_all_tools(self) -> List[ToolSchema]:
        """Get all loaded tools."""
        return list(self._tools.values())

    @property
    def is_loaded(self) -> bool:
        """Check if schemas have been loaded."""
        return self._loaded


# =============================================================================
# CAPABILITY MANAGER
# =============================================================================

class ToolCapabilityManager:
    """
    Central registry for tool capabilities.

    Manages tool schemas, selection, and access control.
    Integrates Phase 0 blacklist functionality.
    """

    def __init__(
        self,
        schema_dir: Optional[Union[str, Path]] = None,
        auto_load: bool = True
    ):
        """
        Initialize the capability manager.

        Args:
            schema_dir: Path to schema JSON files. Defaults to ./tool_capabilities/schemas
            auto_load: Whether to load schemas immediately
        """
        if schema_dir is None:
            # Default to relative path from this file's location
            schema_path = Path(__file__).parent / "schemas"
        elif isinstance(schema_dir, str):
            schema_path = Path(schema_dir)
        else:
            schema_path = schema_dir

        self.schema_dir = schema_path
        self.loader = SchemaLoader(schema_path)

        # Capability control (Phase 0 blacklist integration)
        self._disabled_tools: Set[str] = set()
        self._expiration_times: Dict[str, datetime] = {}
        self._disable_reasons: Dict[str, str] = {}

        # Usage analytics (optional)
        self._usage_tracking_enabled = True
        self._usage_events: List[Dict] = []

        if auto_load:
            self.loader.load_all()

    # =========================================================================
    # TOOL RETRIEVAL
    # =========================================================================

    def get_enabled_tools(
        self,
        message: str = "",
        context: Optional[Dict[str, Any]] = None,
        format: str = "anthropic",
        include_always: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get tools enabled for the current context.

        Args:
            message: User message for keyword matching
            context: Execution context (project_id, user_id, etc.)
            format: "anthropic" or "openai"
            include_always: Include always-loaded tools

        Returns:
            List of tool schemas in requested format
        """
        self._check_expirations()
        context = context or {}

        selected_tools: List[ToolSchema] = []
        message_lower = message.lower()

        for group in self.loader.get_all_groups():
            # Check selection strategy
            include_group = False

            if group.selection_strategy == "always" and include_always:
                include_group = True
            elif group.selection_strategy == "keyword":
                include_group = any(kw in message_lower for kw in group.keywords)
            elif group.selection_strategy == "context":
                # Context-based checks (e.g., project_id present)
                include_group = self._check_context_condition(group, context)

            if include_group:
                for tool in group.tools:
                    # Skip disabled tools
                    if tool.name in self._disabled_tools:
                        continue
                    selected_tools.append(tool)

        # Convert to requested format
        if format == "anthropic":
            return [t.to_anthropic_format() for t in selected_tools]
        elif format == "openai":
            return [t.to_openai_format() for t in selected_tools]
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _check_context_condition(
        self,
        group: ToolGroup,
        context: Dict[str, Any]
    ) -> bool:
        """Check if context-based selection should include group."""
        check = group.context_check

        if check == "has_project":
            return bool(context.get("project_id"))
        elif check == "enable_memory":
            return context.get("enable_memory", True)
        elif check == "enable_tools":
            return context.get("enable_tools", True)

        # Default: include if any keyword matches or always strategy
        return False

    def get_tool(self, name: str) -> Optional[ToolSchema]:
        """Get a specific tool by name."""
        return self.loader.get_tool(name)

    def get_tool_metadata(self, name: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a specific tool."""
        tool = self.loader.get_tool(name)
        if not tool:
            return None

        return {
            "name": tool.name,
            "group": tool.group,
            "description": tool.description,
            "category": tool.category,
            **tool.metadata
        }

    def list_groups(self) -> List[str]:
        """List all loaded tool groups."""
        return [g.name for g in self.loader.get_all_groups()]

    def list_tools(self, group: Optional[str] = None) -> List[str]:
        """List all tools, optionally filtered by group."""
        if group:
            g = self.loader.get_group(group)
            if g:
                return [t.name for t in g.tools]
            return []
        return [t.name for t in self.loader.get_all_tools()]

    # =========================================================================
    # CAPABILITY CONTROL (Phase 0 Blacklist Integration)
    # =========================================================================

    def set_capability_status(
        self,
        tool_name: str,
        enabled: bool,
        reason: str = "",
        duration_minutes: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Enable or disable a tool capability.

        This is the core mechanism for Cass's self-directed tool control.
        Replaces tool_selector.set_tool_blacklist().

        Args:
            tool_name: Name of the tool to enable/disable
            enabled: True to enable, False to disable
            reason: Why this change is being made
            duration_minutes: Optional auto-revert duration

        Returns:
            Dict with action details and current state
        """
        self._check_expirations()

        if not enabled:
            # Disable tool
            self._disabled_tools.add(tool_name)

            if reason:
                self._disable_reasons[tool_name] = reason

            if duration_minutes:
                expiration = datetime.now() + timedelta(minutes=duration_minutes)
                self._expiration_times[tool_name] = expiration

            return {
                "success": True,
                "action": "disabled",
                "tool": tool_name,
                "reason": reason,
                "duration_minutes": duration_minutes,
                "disabled_tools": list(self._disabled_tools)
            }
        else:
            # Enable tool
            self._disabled_tools.discard(tool_name)
            self._expiration_times.pop(tool_name, None)
            self._disable_reasons.pop(tool_name, None)

            return {
                "success": True,
                "action": "enabled",
                "tool": tool_name,
                "disabled_tools": list(self._disabled_tools)
            }

    def get_capability_status(self) -> Dict[str, Any]:
        """Get current capability control state."""
        self._check_expirations()

        return {
            "disabled_tools": list(self._disabled_tools),
            "expirations": {
                tool: exp.isoformat()
                for tool, exp in self._expiration_times.items()
            },
            "reasons": dict(self._disable_reasons)
        }

    def is_tool_disabled(self, tool_name: str) -> bool:
        """Check if a specific tool is disabled."""
        self._check_expirations()
        return tool_name in self._disabled_tools

    def _check_expirations(self) -> List[str]:
        """
        Remove expired disabled tools.

        Returns:
            List of tools that were auto-re-enabled
        """
        now = datetime.now()
        expired = []

        for tool, expiration in list(self._expiration_times.items()):
            if now >= expiration:
                self._disabled_tools.discard(tool)
                del self._expiration_times[tool]
                self._disable_reasons.pop(tool, None)
                expired.append(tool)

        if expired:
            print(f"[Registry] Auto-enabled expired tools: {expired}")

        return expired

    # =========================================================================
    # LEGACY COMPATIBILITY
    # =========================================================================

    def filter_blacklisted_tools(self, tools: List[Dict]) -> List[Dict]:
        """
        Filter disabled tools from a tool list.

        Compatibility method for existing code using tool_selector pattern.

        Args:
            tools: List of tool dicts (each has a "name" key)

        Returns:
            Filtered list with disabled tools removed
        """
        self._check_expirations()

        if not self._disabled_tools:
            return tools

        return [
            tool for tool in tools
            if tool.get("name") not in self._disabled_tools
        ]

    # =========================================================================
    # USAGE ANALYTICS
    # =========================================================================

    def log_tool_usage(
        self,
        tool_name: str,
        success: bool,
        latency_ms: float = 0.0,
        context: Optional[Dict] = None
    ):
        """
        Log a tool usage event.

        Args:
            tool_name: Name of the tool used
            success: Whether the tool call succeeded
            latency_ms: Execution time in milliseconds
            context: Optional context about the usage
        """
        if not self._usage_tracking_enabled:
            return

        event = {
            "tool_name": tool_name,
            "timestamp": datetime.now().isoformat(),
            "success": success,
            "latency_ms": latency_ms,
            "context": context or {}
        }

        self._usage_events.append(event)

        # Keep only last 1000 events in memory
        if len(self._usage_events) > 1000:
            self._usage_events = self._usage_events[-1000:]

    def get_usage_stats(
        self,
        tool_name: Optional[str] = None,
        time_range_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get usage statistics for tools.

        Args:
            tool_name: Filter to specific tool (None = all tools)
            time_range_hours: Time window to analyze

        Returns:
            Dict with usage statistics
        """
        cutoff = datetime.now() - timedelta(hours=time_range_hours)

        events = [
            e for e in self._usage_events
            if datetime.fromisoformat(e["timestamp"]) >= cutoff
            and (tool_name is None or e["tool_name"] == tool_name)
        ]

        if not events:
            return {
                "time_range_hours": time_range_hours,
                "total_calls": 0,
                "message": "No usage data in time range"
            }

        total_calls = len(events)
        successful = sum(1 for e in events if e["success"])
        avg_latency = sum(e["latency_ms"] for e in events) / total_calls

        # Breakdown by tool
        by_tool: Dict[str, int] = {}
        for e in events:
            name = e["tool_name"]
            by_tool[name] = by_tool.get(name, 0) + 1

        return {
            "time_range_hours": time_range_hours,
            "total_calls": total_calls,
            "successful_calls": successful,
            "success_rate": successful / total_calls,
            "avg_latency_ms": avg_latency,
            "by_tool": by_tool
        }


# =============================================================================
# SINGLETON & FACTORY
# =============================================================================

_registry_instance: Optional[ToolCapabilityManager] = None


def get_tool_registry(
    schema_dir: Optional[str] = None,
    force_reload: bool = False
) -> ToolCapabilityManager:
    """
    Get the singleton tool registry instance.

    Args:
        schema_dir: Override default schema directory
        force_reload: Force re-initialization

    Returns:
        ToolCapabilityManager instance
    """
    global _registry_instance

    if _registry_instance is None or force_reload:
        _registry_instance = ToolCapabilityManager(schema_dir=schema_dir)

    return _registry_instance


def reload_registry() -> int:
    """
    Reload all schemas from disk.

    Returns:
        Number of tools loaded
    """
    registry = get_tool_registry()
    return registry.loader.load_all()
