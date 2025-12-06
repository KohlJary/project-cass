"""
Cass Vessel TUI - Terminal History Search
Modal screen for searching terminal output and inserting commands
"""
import re
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Input, ListView, ListItem, Label, Static
from textual.screen import ModalScreen
from textual.message import Message
from typing import List, Tuple, Optional
from rich.text import Text


class HistoryItem(ListItem):
    """A history item in the search results"""

    def __init__(self, line: str, line_number: int, match_positions: List[Tuple[int, int]] = None, **kwargs):
        super().__init__(**kwargs)
        self.line_text = line
        self.line_number = line_number
        self.match_positions = match_positions or []

    def compose(self) -> ComposeResult:
        # Create rich text with highlighted matches
        text = Text()
        text.append(f"{self.line_number:4d} ", style="dim")

        if self.match_positions:
            # Highlight the matches
            last_end = 0
            line = self.line_text
            for start, end in self.match_positions:
                if start > last_end:
                    text.append(line[last_end:start])
                text.append(line[start:end], style="bold yellow")
                last_end = end
            if last_end < len(line):
                text.append(line[last_end:])
        else:
            text.append(self.line_text)

        yield Label(text)


class TerminalSearchScreen(ModalScreen):
    """Modal screen for searching terminal history"""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+c", "cancel", "Cancel"),
    ]

    class LineSelected(Message):
        """Emitted when a line is selected for insertion"""
        def __init__(self, line: str) -> None:
            self.line = line
            super().__init__()

    def __init__(self, output_lines: List[str], **kwargs):
        super().__init__(**kwargs)
        self.output_lines = output_lines  # All lines from terminal buffer
        self._filtered_results: List[Tuple[int, str, List[Tuple[int, int]]]] = []  # (line_num, text, matches)

    def compose(self) -> ComposeResult:
        with Container(id="terminal-search"):
            yield Label("Search Terminal History", id="terminal-search-title")
            yield Input(
                placeholder="Search output... (regex supported)",
                id="terminal-search-input"
            )
            yield Static(f"{len(self.output_lines)} lines in buffer", id="terminal-search-status")
            yield ListView(id="terminal-search-list")
            yield Static(
                "Enter: insert line  |  Esc: cancel",
                id="terminal-search-hints"
            )

    def on_mount(self) -> None:
        """Initialize with recent lines"""
        self._update_list()
        self.query_one("#terminal-search-input", Input).focus()

    def _search_lines(self, pattern: str) -> None:
        """Search lines for the pattern"""
        if not pattern.strip():
            # Show recent lines (last 50)
            self._filtered_results = [
                (i + 1, line, [])
                for i, line in enumerate(self.output_lines[-50:])
                if line.strip()  # Skip empty lines
            ]
            # Reverse to show most recent first
            offset = max(0, len(self.output_lines) - 50)
            self._filtered_results = [
                (i + offset + 1, line, [])
                for i, line in enumerate(self.output_lines[-50:])
                if line.strip()
            ]
            self._filtered_results.reverse()
        else:
            # Search with regex
            try:
                regex = re.compile(pattern, re.IGNORECASE)
            except re.error:
                # Invalid regex, use literal search
                regex = re.compile(re.escape(pattern), re.IGNORECASE)

            results = []
            for i, line in enumerate(self.output_lines):
                matches = list(regex.finditer(line))
                if matches:
                    match_positions = [(m.start(), m.end()) for m in matches]
                    results.append((i + 1, line, match_positions))

            # Show most recent matches first
            results.reverse()
            self._filtered_results = results[:100]  # Limit to 100 results

    def _update_list(self) -> None:
        """Update the ListView with search results"""
        list_view = self.query_one("#terminal-search-list", ListView)
        list_view.clear()

        # Update status
        status = self.query_one("#terminal-search-status", Static)
        if self._filtered_results:
            status.update(f"{len(self._filtered_results)} matches")
        else:
            status.update(f"{len(self.output_lines)} lines in buffer")

        if not self._filtered_results:
            list_view.append(ListItem(
                Label("No matches found", classes="no-results"),
                disabled=True
            ))
            return

        for line_num, line_text, match_positions in self._filtered_results:
            # Truncate long lines for display
            display_text = line_text[:200] + "..." if len(line_text) > 200 else line_text
            # Adjust match positions if truncated
            if len(line_text) > 200:
                match_positions = [(s, min(e, 200)) for s, e in match_positions if s < 200]

            list_view.append(HistoryItem(
                display_text,
                line_num,
                match_positions
            ))

    @on(Input.Changed, "#terminal-search-input")
    def on_search_changed(self, event: Input.Changed) -> None:
        """Handle search input changes"""
        self._search_lines(event.value)
        self._update_list()

    @on(Input.Submitted, "#terminal-search-input")
    def on_search_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter in search input - select first result"""
        if self._filtered_results:
            _, line, _ = self._filtered_results[0]
            self.dismiss(line)

    @on(ListView.Selected, "#terminal-search-list")
    def on_result_selected(self, event: ListView.Selected) -> None:
        """Handle result selection"""
        if isinstance(event.item, HistoryItem):
            self.dismiss(event.item.line_text)

    def action_cancel(self) -> None:
        """Cancel and close the search"""
        self.dismiss(None)
