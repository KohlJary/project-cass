"""
Cass Vessel TUI - Command Palette
Unified command interface with fuzzy search
"""
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Input, ListView, ListItem, Label, Static
from textual.screen import ModalScreen
from typing import List, Tuple, Optional, Dict, Callable
from dataclasses import dataclass


@dataclass
class Command:
    """Represents a command in the palette"""
    id: str
    name: str
    description: str
    category: str
    keybinding: Optional[str] = None
    context: str = "all"  # "all", "cass", "daedalus"


class CommandItem(ListItem):
    """A command item in the palette list"""

    def __init__(self, command: Command, **kwargs):
        super().__init__(**kwargs)
        self.command = command

    def compose(self) -> ComposeResult:
        with Vertical(classes="command-item-content"):
            with Horizontal(classes="command-item-header"):
                yield Label(self.command.name, classes="command-name")
                if self.command.keybinding:
                    yield Label(self.command.keybinding, classes="command-keybinding")
            yield Static(self.command.description, classes="command-description")


# Define available commands
COMMANDS: List[Command] = [
    # Navigation
    Command("show_cass", "Switch to Cass Tab", "Open the Cass chat interface", "Navigation", "Ctrl+1", "all"),
    Command("show_daedalus", "Switch to Daedalus Tab", "Open the Daedalus terminal", "Navigation", "Ctrl+2", "all"),
    Command("toggle_growth", "Toggle Growth Panel", "Show/hide the Growth panel", "Navigation", "Ctrl+G", "cass"),
    Command("toggle_calendar", "Toggle Calendar Panel", "Show/hide the Calendar panel", "Navigation", "Ctrl+K", "all"),

    # Conversations
    Command("new_conversation", "New Conversation", "Start a new chat conversation", "Conversations", "Ctrl+N", "cass"),
    Command("rename_conversation", "Rename Conversation", "Rename the current conversation", "Conversations", "Ctrl+R", "cass"),
    Command("delete_conversation", "Delete Conversation", "Delete the current conversation", "Conversations", "Ctrl+D", "cass"),
    Command("clear_chat", "Clear Chat Display", "Clear visible messages (doesn't delete)", "Conversations", "Ctrl+L", "cass"),

    # Projects
    Command("new_project", "New Project", "Create a new project", "Projects", "Ctrl+P", "all"),
    Command("project_switcher", "Switch Project", "Quick switch between projects", "Projects", "Ctrl+Shift+P", "all"),

    # Sessions (Daedalus)
    Command("session_switcher", "Switch Session", "Quick switch between Daedalus sessions", "Sessions", "Ctrl+`", "daedalus"),
    Command("new_session", "New Daedalus Session", "Create a new Daedalus session", "Sessions", None, "daedalus"),

    # LLM
    Command("toggle_llm", "Cycle LLM Provider", "Switch between Claude/OpenAI/Local", "LLM", "Ctrl+O", "cass"),

    # Audio
    Command("toggle_tts", "Toggle TTS Audio", "Mute/unmute text-to-speech", "Audio", "Ctrl+M", "cass"),

    # Tools
    Command("open_settings", "Open Settings", "Open the settings dialog", "Tools", "Ctrl+\\", "all"),
    Command("show_status", "Show Status", "Display connection and system status", "Tools", "Ctrl+S", "all"),
    Command("toggle_debug", "Toggle Debug Panel", "Show/hide the debug panel", "Tools", "F12", "all"),

    # Memory
    Command("summarize", "Summarize Memory", "Trigger memory summarization", "Memory", None, "cass"),
]


class CommandPaletteScreen(ModalScreen):
    """Modal screen for command palette with fuzzy search"""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+c", "cancel", "Cancel"),
    ]

    def __init__(self, current_context: str = "all", **kwargs):
        """
        Args:
            current_context: "cass" or "daedalus" - filters available commands
        """
        super().__init__(**kwargs)
        self.current_context = current_context
        # Filter commands by context
        self._all_commands = [
            cmd for cmd in COMMANDS
            if cmd.context == "all" or cmd.context == current_context
        ]
        self._filtered_commands: List[Command] = self._all_commands.copy()

    def compose(self) -> ComposeResult:
        with Container(id="command-palette"):
            yield Label("Command Palette", id="palette-title")
            yield Input(
                placeholder="Type to search commands...",
                id="command-search-input"
            )
            yield ListView(id="command-list")
            yield Static(
                "Enter: execute  |  Esc: cancel",
                id="palette-hints"
            )

    def on_mount(self) -> None:
        """Load commands on mount"""
        self._update_list()
        self.query_one("#command-search-input", Input).focus()

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
                if last_match_idx >= 0:
                    score += (i - last_match_idx - 1) * 10
                last_match_idx = i
                pattern_idx += 1

        if pattern_idx == len(pattern):
            if text.startswith(pattern[0]):
                score -= 50
            return True, score

        return False, 999999

    def _filter_commands(self, query: str) -> None:
        """Filter commands based on search query"""
        if not query.strip():
            self._filtered_commands = self._all_commands.copy()
        else:
            matches = []
            for cmd in self._all_commands:
                # Match against name and description
                name_match, name_score = self._fuzzy_match(query, cmd.name)
                desc_match, desc_score = self._fuzzy_match(query, cmd.description)
                cat_match, cat_score = self._fuzzy_match(query, cmd.category)

                if name_match or desc_match or cat_match:
                    # Use the best score
                    score = min(name_score, desc_score, cat_score)
                    matches.append((cmd, score))

            # Sort by score (lower is better)
            matches.sort(key=lambda x: x[1])
            self._filtered_commands = [cmd for cmd, _ in matches]

    def _update_list(self) -> None:
        """Update the ListView with current filtered commands"""
        list_view = self.query_one("#command-list", ListView)
        list_view.clear()

        if not self._filtered_commands:
            list_view.append(ListItem(
                Static("No matching commands", classes="no-commands"),
                disabled=True
            ))
        else:
            for cmd in self._filtered_commands:
                list_view.append(CommandItem(cmd))

            # Select first item
            list_view.index = 0

    @on(Input.Changed, "#command-search-input")
    def on_search_changed(self, event: Input.Changed) -> None:
        """Handle search input changes"""
        self._filter_commands(event.value)
        self._update_list()

    @on(Input.Submitted, "#command-search-input")
    def on_search_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter in search input - execute first result"""
        if self._filtered_commands:
            self.dismiss({"action": "execute", "command": self._filtered_commands[0].id})

    @on(ListView.Selected, "#command-list")
    def on_command_selected(self, event: ListView.Selected) -> None:
        """Handle command selection from list"""
        item = event.item
        if isinstance(item, CommandItem):
            self.dismiss({"action": "execute", "command": item.command.id})

    def action_cancel(self) -> None:
        """Cancel and close the palette"""
        self.dismiss(None)
