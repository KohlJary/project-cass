"""
Cass Vessel TUI - Diff Viewer Screen
Modal screen for viewing git diffs with syntax highlighting
"""
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Button, Label, Static, ListView, ListItem
from textual.screen import ModalScreen
from textual.reactive import reactive
from typing import List, Dict, Optional
from rich.text import Text
from rich.syntax import Syntax


class DiffFileItem(ListItem):
    """List item for a changed file"""

    def __init__(self, filename: str, status: str, staged: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.filename = filename
        self.status = status
        self.staged = staged

    def compose(self) -> ComposeResult:
        text = Text()
        # Status indicator
        status_styles = {
            "M": ("M", "yellow"),
            "A": ("+", "green"),
            "D": ("-", "red"),
            "R": ("R", "cyan"),
            "?": ("?", "red dim"),
        }
        indicator, style = status_styles.get(self.status, (self.status, ""))
        text.append(f" {indicator} ", style=style)
        text.append(self.filename)
        if self.staged:
            text.append(" (staged)", style="green dim")
        yield Label(text)


class DiffViewerScreen(ModalScreen):
    """Modal screen for viewing git diffs"""

    BINDINGS = [
        ("escape", "close", "Close"),
        ("q", "close", "Close"),
        ("j", "next_file", "Next file"),
        ("k", "prev_file", "Prev file"),
        ("s", "toggle_staged", "Toggle staged/unstaged"),
    ]

    current_file: reactive[Optional[str]] = reactive(None)
    show_staged: reactive[bool] = reactive(False)

    def __init__(
        self,
        repo_path: str,
        files: List[Dict],
        http_client,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.repo_path = repo_path
        self.files = files  # List of {file, status, staged}
        self.http_client = http_client
        self._diff_cache: Dict[str, str] = {}

    def compose(self) -> ComposeResult:
        with Container(id="diff-viewer-dialog"):
            yield Label("Diff Viewer", id="diff-viewer-title")
            with Horizontal(id="diff-viewer-content"):
                # File list on left
                with Container(id="diff-file-list-container"):
                    yield Label("Changed Files", classes="section-label")
                    yield ListView(id="diff-file-list")
                    with Horizontal(id="diff-file-controls"):
                        yield Button("Staged", id="show-staged-btn", variant="default")
                        yield Button("Unstaged", id="show-unstaged-btn", variant="primary")
                # Diff content on right
                with VerticalScroll(id="diff-content-container"):
                    yield Static("Select a file to view diff", id="diff-content")
            with Horizontal(id="diff-viewer-buttons"):
                yield Button("Close", variant="default", id="diff-close")

    async def on_mount(self) -> None:
        await self._populate_file_list()
        # Select first file if available
        if self.files:
            self.current_file = self.files[0].get("file")
            await self._load_diff(self.current_file)

    async def _populate_file_list(self) -> None:
        """Populate the file list based on staged/unstaged filter"""
        file_list = self.query_one("#diff-file-list", ListView)
        await file_list.clear()

        for file_info in self.files:
            filename = file_info.get("file", "")
            status = file_info.get("status", "M")
            staged = file_info.get("staged", False)

            # Filter based on show_staged
            if self.show_staged and not staged:
                continue
            if not self.show_staged and staged:
                continue

            await file_list.append(DiffFileItem(
                filename=filename,
                status=status,
                staged=staged,
                id=f"diff-file-{filename.replace('/', '-').replace('.', '-')}"
            ))

    async def _load_diff(self, filename: Optional[str]) -> None:
        """Load diff for a specific file"""
        diff_content = self.query_one("#diff-content", Static)

        if not filename:
            diff_content.update("Select a file to view diff")
            return

        # Check cache
        cache_key = f"{filename}:{self.show_staged}"
        if cache_key in self._diff_cache:
            diff_text = self._diff_cache[cache_key]
        else:
            # Fetch from API
            try:
                response = await self.http_client.get(
                    "/git/diff",
                    params={
                        "repo_path": self.repo_path,
                        "file": filename,
                        "staged": self.show_staged
                    }
                )
                if response.status_code == 200:
                    diff_text = response.json().get("diff", "")
                    self._diff_cache[cache_key] = diff_text
                else:
                    diff_text = f"Error loading diff: {response.json().get('detail', 'Unknown error')}"
            except Exception as e:
                diff_text = f"Error loading diff: {e}"

        if not diff_text.strip():
            diff_content.update(Text("No changes", style="dim"))
            return

        # Use Rich Syntax for highlighting
        syntax = Syntax(
            diff_text,
            "diff",
            theme="monokai",
            line_numbers=True,
            word_wrap=True
        )
        diff_content.update(syntax)

    def watch_show_staged(self, show_staged: bool) -> None:
        """Update UI when staged filter changes"""
        # Update button states
        try:
            staged_btn = self.query_one("#show-staged-btn", Button)
            unstaged_btn = self.query_one("#show-unstaged-btn", Button)
            staged_btn.variant = "primary" if show_staged else "default"
            unstaged_btn.variant = "default" if show_staged else "primary"
        except Exception:
            pass

    @on(Button.Pressed, "#show-staged-btn")
    async def on_show_staged(self) -> None:
        self.show_staged = True
        await self._populate_file_list()
        # Reload current file's diff
        if self.current_file:
            await self._load_diff(self.current_file)

    @on(Button.Pressed, "#show-unstaged-btn")
    async def on_show_unstaged(self) -> None:
        self.show_staged = False
        await self._populate_file_list()
        if self.current_file:
            await self._load_diff(self.current_file)

    @on(ListView.Selected, "#diff-file-list")
    async def on_file_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, DiffFileItem):
            self.current_file = event.item.filename
            await self._load_diff(self.current_file)

    @on(Button.Pressed, "#diff-close")
    def on_close(self) -> None:
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)

    def action_toggle_staged(self) -> None:
        self.show_staged = not self.show_staged
        self.run_worker(self._populate_file_list())
        if self.current_file:
            self.run_worker(self._load_diff(self.current_file))

    def action_next_file(self) -> None:
        """Move to next file in list"""
        file_list = self.query_one("#diff-file-list", ListView)
        if file_list.index is not None and file_list.index < len(file_list) - 1:
            file_list.index += 1

    def action_prev_file(self) -> None:
        """Move to previous file in list"""
        file_list = self.query_one("#diff-file-list", ListView)
        if file_list.index is not None and file_list.index > 0:
            file_list.index -= 1
