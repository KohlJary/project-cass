"""
Daedalus - Software engineering paradigm with Icarus parallelization.

A CLI and coordination system for Claude Code workflows, including:
- Template injection for project CLAUDE.md files
- Icarus Bus for parallel work coordination
- Identity framework for worker instances
"""

__version__ = "0.1.0"

# Re-export key functions for convenience
from .templates import inject_claude_template, substitute_template_vars

# Re-export bus components
from .bus import (
    IcarusBus,
    WorkPackage,
    InstanceStatus,
    WorkStatus,
    RequestType,
)

# Re-export CLI components
from .cli import Daedalus, DaedalusConfig, get_config

__all__ = [
    "__version__",
    # Templates
    "inject_claude_template",
    "substitute_template_vars",
    # Bus
    "IcarusBus",
    "WorkPackage",
    "InstanceStatus",
    "WorkStatus",
    "RequestType",
    # CLI
    "Daedalus",
    "DaedalusConfig",
    "get_config",
]
