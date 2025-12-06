"""
Cass Vessel TUI - Project Quick Switcher
Modal screen for fast project switching with fuzzy search
"""
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Input, ListView, ListItem, Label, Static, Button, Checkbox
from textual.screen import ModalScreen
from typing import List, Tuple, Optional, Dict


class ProjectItem(ListItem):
    """A project item in the switcher list"""

    def __init__(self, project_data: Dict, is_current: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.project_data = project_data
        self.project_id = project_data.get("id", "")
        self.project_name = project_data.get("name", "Unknown")
        self.working_dir = project_data.get("working_directory", "")
        self.is_current = is_current

    def compose(self) -> ComposeResult:
        indicator = "●" if self.is_current else "○"

        with Vertical(classes="project-item-content"):
            with Horizontal(classes="project-item-header"):
                yield Label(f"{indicator} ", classes="project-indicator")
                yield Label(self.project_name, classes="project-name")
            if self.working_dir:
                yield Static(self.working_dir, classes="project-path")


class ProjectSwitcherScreen(ModalScreen):
    """Modal screen for quick project switching"""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+c", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        projects: List[Dict],
        current_project_id: Optional[str] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.projects = projects
        self.current_project_id = current_project_id
        self._filtered_projects: List[Dict] = projects.copy()

    def compose(self) -> ComposeResult:
        with Container(id="project-switcher"):
            yield Label("Switch Project", id="project-switcher-title")
            yield Input(
                placeholder="Search projects...",
                id="project-search-input"
            )
            yield ListView(id="project-list")
            with Horizontal(id="project-switcher-options"):
                yield Checkbox("Spawn Daedalus session", id="spawn-session-checkbox", value=True)
            yield Static(
                "Enter: switch  |  Esc: cancel",
                id="project-switcher-hints"
            )

    def on_mount(self) -> None:
        """Load projects on mount"""
        self._update_list()
        self.query_one("#project-search-input", Input).focus()

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

    def _filter_projects(self, query: str) -> None:
        """Filter projects based on search query"""
        if not query.strip():
            self._filtered_projects = self.projects.copy()
        else:
            matches = []
            for project in self.projects:
                name = project.get("name", "")
                working_dir = project.get("working_directory", "")

                # Match against project name and working directory
                name_match, name_score = self._fuzzy_match(query, name)
                path_match, path_score = self._fuzzy_match(query, working_dir)

                if name_match or path_match:
                    # Use the better score
                    score = min(name_score, path_score)
                    matches.append((project, score))

            # Sort by score (lower is better)
            matches.sort(key=lambda x: x[1])
            self._filtered_projects = [proj for proj, _ in matches]

    def _update_list(self) -> None:
        """Update the ListView with current filtered projects"""
        list_view = self.query_one("#project-list", ListView)
        list_view.clear()

        if not self._filtered_projects:
            # Show a "no projects" message
            list_view.append(ListItem(
                Static("No matching projects", classes="no-projects"),
                disabled=True
            ))
        else:
            for project in self._filtered_projects:
                is_current = project.get("id") == self.current_project_id
                item = ProjectItem(project, is_current=is_current)
                if is_current:
                    item.add_class("current-project")
                list_view.append(item)

            # Select first item
            list_view.index = 0

    @on(Input.Changed, "#project-search-input")
    def on_search_changed(self, event: Input.Changed) -> None:
        """Handle search input changes"""
        self._filter_projects(event.value)
        self._update_list()

    @on(Input.Submitted, "#project-search-input")
    def on_search_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter in search input - select first result"""
        if self._filtered_projects:
            self._select_project(self._filtered_projects[0])

    @on(ListView.Selected, "#project-list")
    def on_project_selected(self, event: ListView.Selected) -> None:
        """Handle project selection from list"""
        item = event.item
        if isinstance(item, ProjectItem):
            self._select_project(item.project_data)

    def _select_project(self, project: Dict) -> None:
        """Select a project and dismiss"""
        spawn_session = self.query_one("#spawn-session-checkbox", Checkbox).value
        self.dismiss({
            "action": "switch",
            "project": project,
            "spawn_session": spawn_session
        })

    def action_cancel(self) -> None:
        """Cancel and close the switcher"""
        self.dismiss(None)
