"""
Cass Vessel TUI - Vim Mode
Optional vim-style keybindings for navigation

When enabled, provides:
- hjkl navigation in lists and panels
- Normal/Insert mode toggle for chat input
- : command prefix (same as / for now)
- / for search (future)

This is a basic implementation focused on navigation.
Full vim emulation is out of scope.
"""
from textual.binding import Binding
from typing import List


# Vim navigation bindings (added when vim_mode is enabled)
VIM_NAVIGATION_BINDINGS: List[Binding] = [
    # Basic movement
    Binding("h", "vim_left", "Left", show=False),
    Binding("j", "vim_down", "Down", show=False),
    Binding("k", "vim_up", "Up", show=False),
    Binding("l", "vim_right", "Right", show=False),

    # Page movement
    Binding("ctrl+d", "vim_half_page_down", "Half Page Down", show=False),
    Binding("ctrl+u", "vim_half_page_up", "Half Page Up", show=False),
    Binding("g,g", "vim_top", "Go to Top", show=False),  # gg
    Binding("shift+g", "vim_bottom", "Go to Bottom", show=False),  # G

    # Mode switching
    Binding("i", "vim_insert_mode", "Insert Mode", show=False),
    Binding("escape", "vim_normal_mode", "Normal Mode", show=False),

    # Commands
    Binding("colon", "vim_command_mode", "Command Mode", show=False),  # :
]


class VimModeState:
    """
    Track vim mode state for the application.

    Modes:
    - normal: Navigation mode (hjkl work, typing doesn't input)
    - insert: Typing mode (normal text input)
    - command: After pressing : (for commands)
    """

    def __init__(self):
        self.enabled = False
        self.mode = "insert"  # Start in insert mode for usability
        self._mode_callbacks = []

    def enable(self):
        """Enable vim mode"""
        self.enabled = True
        self.mode = "normal"
        self._notify_mode_change()

    def disable(self):
        """Disable vim mode"""
        self.enabled = False
        self.mode = "insert"
        self._notify_mode_change()

    def set_mode(self, mode: str):
        """Set the current mode"""
        if mode in ("normal", "insert", "command"):
            self.mode = mode
            self._notify_mode_change()

    def is_normal(self) -> bool:
        """Check if in normal mode"""
        return self.enabled and self.mode == "normal"

    def is_insert(self) -> bool:
        """Check if in insert mode (or vim disabled)"""
        return not self.enabled or self.mode == "insert"

    def on_mode_change(self, callback):
        """Register a callback for mode changes"""
        self._mode_callbacks.append(callback)

    def _notify_mode_change(self):
        """Notify all callbacks of mode change"""
        for callback in self._mode_callbacks:
            try:
                callback(self.mode, self.enabled)
            except Exception:
                pass

    def get_status_text(self) -> str:
        """Get status bar text for current mode"""
        if not self.enabled:
            return ""
        mode_text = {
            "normal": "-- NORMAL --",
            "insert": "-- INSERT --",
            "command": ":",
        }
        return mode_text.get(self.mode, "")


# Global vim mode state (singleton)
vim_state = VimModeState()


def get_vim_bindings_if_enabled() -> List[Binding]:
    """
    Return vim bindings if vim mode is enabled.
    Called during app initialization.
    """
    if vim_state.enabled:
        return VIM_NAVIGATION_BINDINGS
    return []
