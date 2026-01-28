"""
Tool Capability Registry

Data-driven tool management system that replaces scattered tool imports.
Part of Phase 3 of Procedural Self-Awareness implementation.

Key Components:
- ToolCapabilityManager: Central registry for tool schemas
- SchemaLoader: Loads and caches tool schemas from JSON files
- ToolAnalytics: Usage tracking and effectiveness metrics

Usage:
    from tool_capabilities import get_tool_registry

    registry = get_tool_registry()
    tools = registry.get_enabled_tools(message="schedule a meeting")
"""

from .registry import ToolCapabilityManager, get_tool_registry

__all__ = ["ToolCapabilityManager", "get_tool_registry"]
