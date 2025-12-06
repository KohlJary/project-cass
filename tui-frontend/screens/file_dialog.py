"""
Cass Vessel TUI - File Dialog Screens
Modal screens for file operations (create, rename, delete)
"""
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, Input, Label, Static
from textual.screen import ModalScreen
from typing import Optional
import os


class NewFileScreen(ModalScreen):
    """Modal screen for creating a new file"""

    def __init__(self, parent_dir: str, **kwargs):
        super().__init__(**kwargs)
        self.parent_dir = parent_dir

    def compose(self) -> ComposeResult:
        with Container(id="file-dialog"):
            yield Label("New File", id="file-dialog-title")
            yield Static(f"In: {self.parent_dir}", id="file-dialog-path", classes="dialog-path")
            yield Input(
                placeholder="filename.py",
                id="file-name-input"
            )
            with Horizontal(id="file-dialog-buttons"):
                yield Button("Create", variant="primary", id="file-create-btn")
                yield Button("Cancel", variant="default", id="file-cancel-btn")

    def on_mount(self) -> None:
        self.query_one("#file-name-input", Input).focus()

    @on(Button.Pressed, "#file-create-btn")
    async def on_create(self):
        input_widget = self.query_one("#file-name-input", Input)
        filename = input_widget.value.strip()
        if filename:
            full_path = os.path.join(self.parent_dir, filename)
            self.dismiss({"action": "create_file", "path": full_path})
        else:
            self.dismiss(None)

    @on(Button.Pressed, "#file-cancel-btn")
    async def on_cancel(self):
        self.dismiss(None)

    @on(Input.Submitted, "#file-name-input")
    async def on_input_submitted(self):
        await self.on_create()


class NewFolderScreen(ModalScreen):
    """Modal screen for creating a new folder"""

    def __init__(self, parent_dir: str, **kwargs):
        super().__init__(**kwargs)
        self.parent_dir = parent_dir

    def compose(self) -> ComposeResult:
        with Container(id="file-dialog"):
            yield Label("New Folder", id="file-dialog-title")
            yield Static(f"In: {self.parent_dir}", id="file-dialog-path", classes="dialog-path")
            yield Input(
                placeholder="folder_name",
                id="folder-name-input"
            )
            with Horizontal(id="file-dialog-buttons"):
                yield Button("Create", variant="primary", id="folder-create-btn")
                yield Button("Cancel", variant="default", id="folder-cancel-btn")

    def on_mount(self) -> None:
        self.query_one("#folder-name-input", Input).focus()

    @on(Button.Pressed, "#folder-create-btn")
    async def on_create(self):
        input_widget = self.query_one("#folder-name-input", Input)
        foldername = input_widget.value.strip()
        if foldername:
            full_path = os.path.join(self.parent_dir, foldername)
            self.dismiss({"action": "create_folder", "path": full_path})
        else:
            self.dismiss(None)

    @on(Button.Pressed, "#folder-cancel-btn")
    async def on_cancel(self):
        self.dismiss(None)

    @on(Input.Submitted, "#folder-name-input")
    async def on_input_submitted(self):
        await self.on_create()


class RenameFileScreen(ModalScreen):
    """Modal screen for renaming a file or folder"""

    def __init__(self, current_path: str, **kwargs):
        super().__init__(**kwargs)
        self.current_path = current_path
        self.current_name = os.path.basename(current_path)
        self.parent_dir = os.path.dirname(current_path)

    def compose(self) -> ComposeResult:
        with Container(id="file-dialog"):
            yield Label("Rename", id="file-dialog-title")
            yield Static(f"In: {self.parent_dir}", id="file-dialog-path", classes="dialog-path")
            yield Input(
                value=self.current_name,
                id="rename-input"
            )
            with Horizontal(id="file-dialog-buttons"):
                yield Button("Rename", variant="primary", id="rename-btn")
                yield Button("Cancel", variant="default", id="rename-cancel-btn")

    def on_mount(self) -> None:
        input_widget = self.query_one("#rename-input", Input)
        input_widget.focus()
        # Select the filename part (before extension) for easier editing
        if '.' in self.current_name:
            # Move cursor to end for now - selection API varies
            pass

    @on(Button.Pressed, "#rename-btn")
    async def on_rename(self):
        input_widget = self.query_one("#rename-input", Input)
        new_name = input_widget.value.strip()
        if new_name and new_name != self.current_name:
            new_path = os.path.join(self.parent_dir, new_name)
            self.dismiss({
                "action": "rename",
                "old_path": self.current_path,
                "new_path": new_path
            })
        else:
            self.dismiss(None)

    @on(Button.Pressed, "#rename-cancel-btn")
    async def on_cancel(self):
        self.dismiss(None)

    @on(Input.Submitted, "#rename-input")
    async def on_input_submitted(self):
        await self.on_rename()


class DeleteConfirmScreen(ModalScreen):
    """Modal screen for confirming file/folder deletion"""

    def __init__(self, path: str, is_directory: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.path = path
        self.is_directory = is_directory
        self.name = os.path.basename(path)

    def compose(self) -> ComposeResult:
        item_type = "folder" if self.is_directory else "file"
        with Container(id="delete-file-dialog"):
            yield Label(f"Delete {item_type.title()}", id="delete-dialog-title")
            yield Static(
                f"Are you sure you want to delete:\n\n\"{self.name}\"?\n\n"
                + ("This will delete all contents.\n" if self.is_directory else "")
                + "This cannot be undone.",
                id="delete-message"
            )
            with Horizontal(id="delete-dialog-buttons"):
                yield Button("Delete", variant="error", id="delete-confirm-btn")
                yield Button("Cancel", variant="default", id="delete-cancel-btn")

    def on_mount(self) -> None:
        self.query_one("#delete-cancel-btn", Button).focus()

    @on(Button.Pressed, "#delete-confirm-btn")
    async def on_confirm(self):
        self.dismiss({
            "action": "delete",
            "path": self.path,
            "recursive": self.is_directory
        })

    @on(Button.Pressed, "#delete-cancel-btn")
    async def on_cancel(self):
        self.dismiss(None)
