"""
Consolidated Session Runner - Single runner for all autonomous session types.

Instead of 12+ separate session runners, this provides one GenericSessionRunner
that can be configured with session-specific prompts and tools.
"""

from .generic_runner import GenericSessionRunner, SessionResult, SessionTurn
from .prompts import SESSION_PROMPTS, get_session_prompt
from .tools import SESSION_TOOLS, get_session_tools, get_default_handlers

__all__ = [
    "GenericSessionRunner",
    "SessionResult",
    "SessionTurn",
    "SESSION_PROMPTS",
    "get_session_prompt",
    "SESSION_TOOLS",
    "get_session_tools",
    "get_default_handlers",
]
