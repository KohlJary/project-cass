"""
Daedalus template injection system.

Provides CLAUDE.md template injection for new projects, with variable
substitution from configuration and managed section updates.
"""

from .injector import (
    inject_claude_template,
    substitute_template_vars,
    load_daedalus_config,
    get_template_content,
    DAEDALUS_BEGIN,
    DAEDALUS_END,
)

__all__ = [
    "inject_claude_template",
    "substitute_template_vars",
    "load_daedalus_config",
    "get_template_content",
    "DAEDALUS_BEGIN",
    "DAEDALUS_END",
]
