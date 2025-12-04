"""
Daedalus - PTY-based Claude Code integration for Cass TUI

Named after the mythological master craftsman who built ingenious things,
Daedalus pairs with Cass (the oracle) - one sees/prophesies, the other builds/creates.

This module provides tmux-backed terminal sessions for Claude Code,
using the patched textual-terminal for better performance.
"""

from .pty_manager import PTYManager, Session, set_debug_log, debug_log
from .tmux_terminal import TmuxTerminal, check_tmux_available
from .daedalus_widget import DaedalusWidget

__all__ = [
    "PTYManager",
    "Session",
    "TmuxTerminal",
    "DaedalusWidget",
    "set_debug_log",
    "debug_log",
    "check_tmux_available",
]
