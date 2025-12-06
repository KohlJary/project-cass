"""
Cass Vessel TUI - Session Screens
Modal screens for session switching and creation
"""
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Input, ListView, ListItem, Label, Static, Button
from textual.screen import ModalScreen
from textual.message import Message
from typing import List, Tuple, Optional
import os
import subprocess


class SessionItem(ListItem):
    """A session item in the switcher list"""

    def __init__(self, session_name: str, working_dir: str, **kwargs):
        super().__init__(**kwargs)
        self.session_name = session_name
        self.working_dir = working_dir

    def compose(self) -> ComposeResult:
        # Show the session name (removing daedalus- prefix for display)
        display_name = self.session_name
        if display_name.startswith("daedalus-"):
            display_name = display_name[9:]  # Remove "daedalus-" prefix

        # Truncate UUID-style names and show directory instead
        if len(display_name) > 20 and "-" in display_name:
            # Looks like a UUID, use directory basename
            import os
            dir_name = os.path.basename(self.working_dir) or display_name[:20]
            display_name = dir_name

        with Vertical(classes="session-item-content"):
            yield Label(display_name, classes="session-name")
            yield Static(self.working_dir, classes="session-path")


class SessionSwitcherScreen(ModalScreen):
    """Modal screen for quick session switching"""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+c", "cancel", "Cancel"),
    ]

    class SessionSelected(Message):
        """Emitted when a session is selected"""
        def __init__(self, session_name: str) -> None:
            self.session_name = session_name
            super().__init__()

    def __init__(self, current_session: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.current_session = current_session
        self._sessions: List[Tuple[str, str]] = []  # (name, path) tuples
        self._filtered_sessions: List[Tuple[str, str]] = []

    def compose(self) -> ComposeResult:
        with Container(id="session-switcher"):
            yield Label("Switch Session", id="switcher-title")
            yield Input(
                placeholder="Search sessions...",
                id="session-search-input"
            )
            yield ListView(id="session-list")
            yield Static(
                "Enter: attach  |  Esc: cancel",
                id="switcher-hints"
            )

    def on_mount(self) -> None:
        """Load sessions on mount"""
        self._load_sessions()
        self._update_list()
        self.query_one("#session-search-input", Input).focus()

    def _load_sessions(self) -> None:
        """Load all daedalus sessions from tmux"""
        try:
            result = subprocess.run(
                ["tmux", "list-sessions", "-F", "#{session_name}|#{pane_current_path}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                self._sessions = []
                for line in result.stdout.strip().split('\n'):
                    if line.strip() and '|' in line:
                        parts = line.split('|', 1)
                        session_name = parts[0].strip()
                        working_dir = parts[1].strip() if len(parts) > 1 else ""
                        # Only include daedalus sessions
                        if session_name.startswith('daedalus-'):
                            self._sessions.append((session_name, working_dir))
                # Sort by working directory for easier navigation
                self._sessions.sort(key=lambda x: x[1].lower())
                self._filtered_sessions = self._sessions.copy()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self._sessions = []
            self._filtered_sessions = []

    def _fuzzy_match(self, pattern: str, text: str) -> Tuple[bool, int]:
        """
        Simple fuzzy matching. Returns (matches, score).
        Lower score is better.
        """
        pattern = pattern.lower()
        text = text.lower()

        # Exact substring match - best score
        if pattern in text:
            return True, text.index(pattern)

        # Fuzzy: all chars must appear in order
        pattern_idx = 0
        score = 0
        last_match_idx = -1

        for i, char in enumerate(text):
            if pattern_idx < len(pattern) and char == pattern[pattern_idx]:
                # Penalize gaps between matched characters
                if last_match_idx >= 0:
                    score += (i - last_match_idx - 1) * 10
                last_match_idx = i
                pattern_idx += 1

        if pattern_idx == len(pattern):
            # Bonus for matching at start
            if text.startswith(pattern[0]):
                score -= 50
            return True, score

        return False, 999999

    def _filter_sessions(self, query: str) -> None:
        """Filter sessions based on search query"""
        if not query.strip():
            self._filtered_sessions = self._sessions.copy()
        else:
            matches = []
            for session_name, working_dir in self._sessions:
                # Match against session name and working directory
                name_match, name_score = self._fuzzy_match(query, session_name)
                path_match, path_score = self._fuzzy_match(query, working_dir)

                if name_match or path_match:
                    # Use the better score
                    score = min(name_score, path_score)
                    matches.append((session_name, working_dir, score))

            # Sort by score (lower is better)
            matches.sort(key=lambda x: x[2])
            self._filtered_sessions = [(name, path) for name, path, _ in matches]

    def _update_list(self) -> None:
        """Update the ListView with current filtered sessions"""
        list_view = self.query_one("#session-list", ListView)
        list_view.clear()

        if not self._filtered_sessions:
            # Show a "no sessions" message
            list_view.append(ListItem(
                Static("No matching sessions", classes="no-sessions"),
                disabled=True
            ))
        else:
            for session_name, working_dir in self._filtered_sessions:
                item = SessionItem(session_name, working_dir)
                # Highlight current session
                if session_name == self.current_session:
                    item.add_class("current-session")
                list_view.append(item)

            # Select first item
            list_view.index = 0

    @on(Input.Changed, "#session-search-input")
    def on_search_changed(self, event: Input.Changed) -> None:
        """Handle search input changes"""
        self._filter_sessions(event.value)
        self._update_list()

    @on(Input.Submitted, "#session-search-input")
    def on_search_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter in search input - select first result"""
        if self._filtered_sessions:
            session_name = self._filtered_sessions[0][0]
            self.dismiss({"action": "attach", "session": session_name})

    @on(ListView.Selected, "#session-list")
    def on_session_selected(self, event: ListView.Selected) -> None:
        """Handle session selection from list"""
        item = event.item
        if isinstance(item, SessionItem):
            self.dismiss({"action": "attach", "session": item.session_name})

    def action_cancel(self) -> None:
        """Cancel and close the switcher"""
        self.dismiss(None)


class NewSessionScreen(ModalScreen):
    """Modal screen for creating a new Daedalus session with a custom name"""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, working_dir: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.working_dir = working_dir
        # Default name based on directory
        if working_dir:
            self._default_name = os.path.basename(working_dir) or "session"
        else:
            self._default_name = ""

    def compose(self) -> ComposeResult:
        with Container(id="new-session-dialog"):
            yield Label("New Session", id="new-session-title")
            if self.working_dir:
                yield Static(f"Working directory: {self.working_dir}", classes="dialog-path")
            yield Label("Session name (optional):", classes="input-label")
            yield Input(
                placeholder=self._default_name or "auto-generated",
                id="session-name-input"
            )
            yield Static(
                "Leave blank to use directory name or auto-generate",
                classes="input-hint"
            )
            with Horizontal(id="new-session-buttons"):
                yield Button("Create", variant="primary", id="create-session-btn")
                yield Button("Cancel", variant="default", id="cancel-session-btn")

    def on_mount(self) -> None:
        self.query_one("#session-name-input", Input).focus()

    @on(Button.Pressed, "#create-session-btn")
    async def on_create(self) -> None:
        input_widget = self.query_one("#session-name-input", Input)
        name = input_widget.value.strip()
        # Use default if empty
        if not name and self._default_name:
            name = self._default_name
        self.dismiss({
            "action": "create",
            "name": name or None,  # None triggers auto-generation
            "working_dir": self.working_dir
        })

    @on(Button.Pressed, "#cancel-session-btn")
    async def on_cancel_pressed(self) -> None:
        self.dismiss(None)

    @on(Input.Submitted, "#session-name-input")
    async def on_input_submitted(self) -> None:
        await self.on_create()

    def action_cancel(self) -> None:
        self.dismiss(None)
