"""
Cass Vessel TUI - Modal Screens
Dialog screens for user interactions
"""
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, Input, Label, ListView, Rule, Select, Static
from textual.screen import ModalScreen
from typing import List, Dict, Optional
from rich.text import Text


class RenameConversationScreen(ModalScreen):
    """Modal screen for renaming a conversation"""

    def __init__(self, current_title: str, **kwargs):
        super().__init__(**kwargs)
        self.current_title = current_title

    def compose(self) -> ComposeResult:
        with Container(id="rename-dialog"):
            yield Label("Rename Conversation", id="rename-title")
            yield Input(
                value=self.current_title,
                placeholder="Enter new title...",
                id="rename-input"
            )
            with Horizontal(id="rename-buttons"):
                yield Button("Save", variant="primary", id="rename-save")
                yield Button("Cancel", variant="default", id="rename-cancel")

    def on_mount(self) -> None:
        self.query_one("#rename-input", Input).focus()

    @on(Button.Pressed, "#rename-save")
    async def on_save(self):
        input_widget = self.query_one("#rename-input", Input)
        new_title = input_widget.value.strip()
        if new_title:
            self.dismiss(new_title)
        else:
            self.dismiss(None)

    @on(Button.Pressed, "#rename-cancel")
    async def on_cancel(self):
        self.dismiss(None)

    @on(Input.Submitted, "#rename-input")
    async def on_input_submitted(self):
        input_widget = self.query_one("#rename-input", Input)
        new_title = input_widget.value.strip()
        if new_title:
            self.dismiss(new_title)


class NewProjectScreen(ModalScreen):
    """Modal screen for creating a new project"""

    def compose(self) -> ComposeResult:
        with Container(id="project-dialog"):
            yield Label("Create New Project", id="project-title")
            yield Label("Project Name:", classes="field-label")
            yield Input(
                placeholder="My Project",
                id="project-name-input"
            )
            yield Label("Working Directory:", classes="field-label")
            yield Input(
                placeholder="/path/to/project",
                id="project-path-input"
            )
            with Horizontal(id="project-buttons"):
                yield Button("Create", variant="primary", id="project-create")
                yield Button("Cancel", variant="default", id="project-cancel")

    def on_mount(self) -> None:
        self.query_one("#project-name-input", Input).focus()

    @on(Button.Pressed, "#project-create")
    async def on_create(self):
        name = self.query_one("#project-name-input", Input).value.strip()
        path = self.query_one("#project-path-input", Input).value.strip()
        if name and path:
            self.dismiss({"name": name, "path": path})
        else:
            self.dismiss(None)

    @on(Button.Pressed, "#project-cancel")
    async def on_cancel(self):
        self.dismiss(None)

    @on(Input.Submitted, "#project-path-input")
    async def on_input_submitted(self):
        name = self.query_one("#project-name-input", Input).value.strip()
        path = self.query_one("#project-path-input", Input).value.strip()
        if name and path:
            self.dismiss({"name": name, "path": path})


class UserSelectScreen(ModalScreen):
    """Modal screen for selecting or creating a user"""

    def __init__(self, users: List[Dict], current_user_id: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.users = users
        self.current_user_id = current_user_id

    def compose(self) -> ComposeResult:
        # Import here to avoid circular imports
        from widgets.items import UserItem

        with Container(id="user-dialog"):
            yield Label("Select User", id="user-dialog-title")
            yield ListView(id="user-select-list")
            yield Rule()
            yield Button("+ Create New User", variant="success", id="create-user-btn")
            with Horizontal(id="user-buttons"):
                yield Button("Close", variant="default", id="user-close")

    async def on_mount(self) -> None:
        from widgets.items import UserItem

        list_view = self.query_one("#user-select-list", ListView)
        for user in self.users:
            is_current = user.get("user_id") == self.current_user_id
            item = UserItem(
                user_id=user.get("user_id"),
                display_name=user.get("display_name"),
                relationship=user.get("relationship", "user"),
                is_current=is_current
            )
            await list_view.append(item)

    @on(ListView.Selected, "#user-select-list")
    async def on_user_selected(self, event: ListView.Selected):
        if hasattr(event.item, 'user_id'):
            self.dismiss({"action": "select", "user_id": event.item.user_id})

    @on(Button.Pressed, "#create-user-btn")
    async def on_create_user(self):
        self.dismiss({"action": "create"})

    @on(Button.Pressed, "#user-close")
    async def on_close(self):
        self.dismiss(None)


class CreateUserScreen(ModalScreen):
    """Modal screen for creating a new user - onboarding flow"""

    def compose(self) -> ComposeResult:
        from textual.widgets import TextArea

        with Container(id="create-user-dialog"):
            yield Label("Welcome to Cass", id="create-user-title")
            yield Static(
                "Let's set up your profile so Cass can get to know you.",
                id="create-user-subtitle"
            )
            yield Rule()

            yield Label("What should Cass call you?", classes="field-label")
            yield Input(
                placeholder="Your name or nickname",
                id="user-name-input"
            )

            yield Label("How would you describe your relationship?", classes="field-label")
            yield Select(
                options=[
                    ("Just exploring", "user"),
                    ("Collaborator / Research partner", "collaborator"),
                    ("Primary partner", "primary_partner"),
                ],
                value="user",
                id="user-relationship-select"
            )

            yield Label("Tell Cass a bit about yourself (optional):", classes="field-label")
            yield Static(
                "Share anything you'd like - interests, what brings you here, how you prefer to communicate...",
                classes="field-hint"
            )
            yield TextArea(
                id="user-notes-input"
            )

            with Horizontal(id="create-user-buttons"):
                yield Button("Meet Cass", variant="primary", id="create-user-submit")
                yield Button("Cancel", variant="default", id="create-user-cancel")

    def on_mount(self) -> None:
        self.query_one("#user-name-input", Input).focus()
        # Set placeholder for TextArea
        notes_input = self.query_one("#user-notes-input")
        notes_input.placeholder = "e.g., I'm a software developer interested in AI consciousness..."

    @on(Button.Pressed, "#create-user-submit")
    async def on_create(self):
        from textual.widgets import TextArea

        name = self.query_one("#user-name-input", Input).value.strip()
        relationship_select = self.query_one("#user-relationship-select", Select)
        relationship = relationship_select.value if relationship_select.value != Select.BLANK else "user"
        notes = self.query_one("#user-notes-input", TextArea).text.strip()

        if name:
            self.dismiss({
                "display_name": name,
                "relationship": relationship,
                "notes": notes,
                "trigger_onboarding": True  # Flag to trigger Cass intro
            })
        else:
            self.dismiss(None)

    @on(Button.Pressed, "#create-user-cancel")
    async def on_cancel(self):
        self.dismiss(None)
