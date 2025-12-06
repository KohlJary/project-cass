"""
Cass Vessel TUI - Daedalus Panel Widgets
Panel components specific to Daedalus (Claude Code) context

Panel Definitions & Planned Features:

SessionsPanel - tmux session management
  - List all daedalus-* tmux sessions with active indicator
  - Click session → attach to it in DaedalusWidget
  - Kill button kills selected session
  - Show working directory for each session
  - New Session button
  - Refresh button

FilesPanel - Project file browser
  - Tree view of project directory with file type icons
  - Click file → open in editor or copy path
  - Show file size/modified time
  - Filters out common noise (.git, node_modules, etc.)
  - Refresh button

GitPanel - Repository status display
  - Current branch with ahead/behind indicators
  - Staged, modified, untracked files (color-coded)
  - Recent commits (last 5-10)
  - Quick stage/unstage files
  - Refresh button
"""
import asyncio
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Callable

import httpx
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Container, Vertical, VerticalScroll
from textual.widgets import Button, Label, ListView, ListItem, Static, Tree, TextArea, Input
from textual.widgets.tree import TreeNode
from textual.reactive import reactive
from textual.message import Message
from rich.text import Text
from rich.console import Group

from config import HTTP_BASE_URL


# Forward declaration for debug_log - will be set by main module
def debug_log(message: str, level: str = "info"):
    """Log to debug panel if available, else print"""
    print(f"[{level.upper()}] {message}")


def set_debug_log(func: Callable[[str, str], None]):
    """Set the debug_log function from main module"""
    global debug_log
    debug_log = func


# ─────────────────────────────────────────────────────────────────────────────
# Sessions Panel - tmux session management
# ─────────────────────────────────────────────────────────────────────────────

class SessionItem(ListItem):
    """A list item representing a tmux session"""

    def __init__(self, session_name: str, working_dir: Optional[str] = None,
                 is_active: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.session_name = session_name
        self.working_dir = working_dir
        self.is_active = is_active

    def compose(self) -> ComposeResult:
        indicator = "●" if self.is_active else "○"
        style = "bold green" if self.is_active else ""

        # Strip 'daedalus-' prefix for display, truncate UUID-style names
        display_name = self.session_name
        if display_name.startswith("daedalus-"):
            display_name = display_name[9:]
        # If it looks like a UUID (project-<uuid>), show just the project name
        if display_name.startswith("project-") and len(display_name) > 44:
            display_name = "project"

        text = Text()
        text.append(f" {indicator} ", style="bold green" if self.is_active else "dim")
        text.append(display_name, style=style)

        # Show working directory basename
        if self.working_dir:
            dir_name = os.path.basename(self.working_dir) or self.working_dir
            text.append(f" ({dir_name})", style="dim italic")

        yield Label(text)


class SessionsPanel(Container):
    """Panel for managing Daedalus tmux sessions"""

    current_session: reactive[Optional[str]] = reactive(None)

    class SessionSelected(Message):
        """Posted when a session is selected"""
        def __init__(self, session_name: str):
            super().__init__()
            self.session_name = session_name

    class SessionKillRequested(Message):
        """Posted when session kill is requested"""
        def __init__(self, session_name: str):
            super().__init__()
            self.session_name = session_name

    class NewSessionRequested(Message):
        """Posted when a new session is requested"""
        pass

    def compose(self) -> ComposeResult:
        yield Label("Sessions", classes="panel-title")
        yield ListView(id="sessions-list", classes="sessions-list")
        with Container(classes="session-controls"):
            yield Button("New", id="new-session-btn", variant="primary", classes="control-btn")
            yield Button("Refresh", id="refresh-sessions-btn", classes="control-btn")
            yield Button("Kill", id="kill-session-btn", variant="error", classes="control-btn")

    def on_mount(self) -> None:
        self.refresh_sessions()

    @work(exclusive=True)
    async def refresh_sessions(self) -> None:
        """Refresh the list of tmux sessions"""
        sessions = await asyncio.to_thread(self._get_tmux_sessions)

        list_view = self.query_one("#sessions-list", ListView)
        await list_view.clear()

        if not sessions:
            await list_view.append(ListItem(Label("No active sessions", classes="no-sessions")))
            return

        for session_name, working_dir in sessions:
            is_active = session_name == self.current_session
            await list_view.append(SessionItem(
                session_name,
                working_dir=working_dir,
                is_active=is_active
            ))

    def _get_tmux_sessions(self) -> List[tuple]:
        """Get list of daedalus tmux sessions with their working directories.

        Returns:
            List of (session_name, working_dir) tuples
        """
        try:
            result = subprocess.run(
                ["tmux", "list-sessions", "-F", "#{session_name}:#{pane_current_path}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                sessions = []
                for line in result.stdout.strip().split('\n'):
                    if ':' in line:
                        parts = line.split(':', 1)
                        session_name = parts[0].strip()
                        working_dir = parts[1].strip() if len(parts) > 1 else None
                        if session_name.startswith('daedalus-'):
                            sessions.append((session_name, working_dir))
                return sessions
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return []

    def set_current_session(self, session_name: Optional[str]) -> None:
        """Update which session is marked as active"""
        self.current_session = session_name
        self.refresh_sessions()

    @on(ListView.Selected, "#sessions-list")
    def on_session_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, SessionItem):
            self.post_message(self.SessionSelected(event.item.session_name))

    @on(Button.Pressed, "#refresh-sessions-btn")
    def on_refresh_pressed(self) -> None:
        self.refresh_sessions()

    @on(Button.Pressed, "#kill-session-btn")
    def on_kill_pressed(self) -> None:
        list_view = self.query_one("#sessions-list", ListView)
        if list_view.highlighted_child and isinstance(list_view.highlighted_child, SessionItem):
            self.post_message(self.SessionKillRequested(list_view.highlighted_child.session_name))

    @on(Button.Pressed, "#new-session-btn")
    def on_new_session_pressed(self) -> None:
        self.post_message(self.NewSessionRequested())


# ─────────────────────────────────────────────────────────────────────────────
# Files Panel - Project file browser
# ─────────────────────────────────────────────────────────────────────────────

class FilesPanel(Container):
    """Panel for browsing project files"""

    working_dir: reactive[Optional[str]] = reactive(None)
    selected_path: reactive[Optional[str]] = reactive(None)
    search_mode: reactive[bool] = reactive(False)
    _file_cache: List[str] = []  # Cache of all file paths for search

    # File type icons
    ICONS = {
        "folder": "📁",
        "folder_open": "📂",
        "python": "🐍",
        "javascript": "📜",
        "typescript": "📘",
        "json": "📋",
        "markdown": "📝",
        "yaml": "⚙️",
        "git": "🔀",
        "default": "📄",
    }

    # Files/dirs to ignore
    IGNORE = {".git", "__pycache__", "node_modules", ".venv", "venv", ".mypy_cache",
              ".pytest_cache", ".ruff_cache", "dist", "build", ".egg-info"}

    class FileSelected(Message):
        """Posted when a file is selected"""
        def __init__(self, path: str, is_directory: bool = False):
            super().__init__()
            self.path = path
            self.is_directory = is_directory

    class CopyPathRequested(Message):
        """Posted when copy path is requested"""
        def __init__(self, path: str):
            super().__init__()
            self.path = path

    class OpenInEditorRequested(Message):
        """Posted when open in editor is requested"""
        def __init__(self, path: str):
            super().__init__()
            self.path = path

    class NewFileRequested(Message):
        """Posted when new file creation is requested"""
        def __init__(self, parent_dir: str):
            super().__init__()
            self.parent_dir = parent_dir

    class NewFolderRequested(Message):
        """Posted when new folder creation is requested"""
        def __init__(self, parent_dir: str):
            super().__init__()
            self.parent_dir = parent_dir

    class RenameRequested(Message):
        """Posted when rename is requested"""
        def __init__(self, path: str):
            super().__init__()
            self.path = path

    class DeleteRequested(Message):
        """Posted when delete is requested"""
        def __init__(self, path: str, is_directory: bool = False):
            super().__init__()
            self.path = path
            self.is_directory = is_directory

    # Max file size to preview (100KB)
    MAX_PREVIEW_SIZE = 100 * 1024

    # Binary file extensions to skip
    BINARY_EXTENSIONS = {
        'png', 'jpg', 'jpeg', 'gif', 'bmp', 'ico', 'webp', 'svg',
        'mp3', 'mp4', 'wav', 'avi', 'mkv', 'mov',
        'zip', 'tar', 'gz', 'bz2', 'xz', '7z', 'rar',
        'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
        'exe', 'dll', 'so', 'dylib', 'bin',
        'pyc', 'pyo', 'class', 'o', 'obj',
        'woff', 'woff2', 'ttf', 'otf', 'eot',
    }

    def compose(self) -> ComposeResult:
        yield Label("Files", classes="panel-title")
        yield Input(placeholder="Search files... (Ctrl+F)", id="file-search-input", classes="file-search-input")
        yield ListView(id="file-search-results", classes="file-search-results hidden")
        with Vertical(id="files-content"):
            yield Tree("Project", id="files-tree", classes="files-tree")
            yield Static("", id="file-info", classes="file-info")
            yield VerticalScroll(
                Static("Select a file to preview", id="file-preview-content", classes="preview-placeholder"),
                id="file-preview",
                classes="file-preview"
            )
        with Container(classes="file-controls"):
            yield Button("Open", id="open-editor-btn", variant="primary", classes="control-btn")
            yield Button("New", id="new-file-btn", classes="control-btn")
            yield Button("Folder", id="new-folder-btn", classes="control-btn")
        with Container(classes="file-controls"):
            yield Button("Rename", id="rename-btn", classes="control-btn")
            yield Button("Delete", id="delete-btn", variant="error", classes="control-btn")
            yield Button("Refresh", id="refresh-files-btn", classes="control-btn")

    def on_mount(self) -> None:
        tree = self.query_one("#files-tree", Tree)
        tree.show_root = True
        tree.guide_depth = 3

    @work(exclusive=True)
    async def refresh_tree(self) -> None:
        """Refresh the file tree"""
        tree = self.query_one("#files-tree", Tree)
        tree.clear()

        if not self.working_dir or not os.path.isdir(self.working_dir):
            tree.root.set_label("No project selected")
            return

        # Set root label to directory name
        dir_name = os.path.basename(self.working_dir) or self.working_dir
        tree.root.set_label(f"{self.ICONS['folder']} {dir_name}")
        tree.root.data = self.working_dir

        # Populate tree in background
        await asyncio.to_thread(self._populate_node, tree.root, self.working_dir, depth=0)
        tree.root.expand()

    def _populate_node(self, node: TreeNode, path: str, depth: int = 0, max_depth: int = 2) -> None:
        """Populate a tree node with directory contents"""
        if depth > max_depth:
            return

        try:
            entries = sorted(os.listdir(path))
        except PermissionError:
            return

        # Separate dirs and files, filter ignored
        dirs = []
        files = []
        for entry in entries:
            if entry in self.IGNORE or entry.startswith('.'):
                continue
            full_path = os.path.join(path, entry)
            if os.path.isdir(full_path):
                dirs.append(entry)
            else:
                files.append(entry)

        # Add directories first
        for d in dirs:
            full_path = os.path.join(path, d)
            child = node.add(f"{self.ICONS['folder']} {d}", data=full_path, allow_expand=True)
            # Pre-populate one level for expandability
            if depth < max_depth:
                self._populate_node(child, full_path, depth + 1, max_depth)

        # Then files
        for f in files:
            icon = self._get_file_icon(f)
            full_path = os.path.join(path, f)
            node.add_leaf(f"{icon} {f}", data=full_path)

    def _get_file_icon(self, filename: str) -> str:
        """Get icon for file based on extension"""
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ""

        if filename in (".gitignore", ".gitattributes"):
            return self.ICONS["git"]

        icon_map = {
            "py": "python",
            "js": "javascript",
            "jsx": "javascript",
            "ts": "typescript",
            "tsx": "typescript",
            "json": "json",
            "md": "markdown",
            "yaml": "yaml",
            "yml": "yaml",
            "toml": "yaml",
        }

        return self.ICONS.get(icon_map.get(ext, "default"), self.ICONS["default"])

    @on(Tree.NodeExpanded, "#files-tree")
    def on_node_expanded(self, event: Tree.NodeExpanded) -> None:
        """Lazy load deeper levels when expanded"""
        node = event.node
        if node.data and os.path.isdir(node.data):
            # Check if children are placeholder or real
            # If children exist but haven't been fully populated, do it now
            pass  # Current implementation pre-populates; could optimize later

    @on(Tree.NodeSelected, "#files-tree")
    def on_node_selected(self, event: Tree.NodeSelected) -> None:
        """Handle file/folder selection"""
        node = event.node
        if node.data:
            self.selected_path = node.data
            is_dir = os.path.isdir(node.data)

            # Update file info display
            self._update_file_info(node.data, is_dir)

            # Update file preview
            self._update_file_preview(node.data, is_dir)

            # Post selection message
            self.post_message(self.FileSelected(node.data, is_directory=is_dir))

    def _update_file_info(self, path: str, is_dir: bool) -> None:
        """Update the file info display"""
        info_widget = self.query_one("#file-info", Static)

        try:
            stat = os.stat(path)
            if is_dir:
                # Count items in directory
                try:
                    item_count = len([e for e in os.listdir(path)
                                     if not e.startswith('.') and e not in self.IGNORE])
                    info_widget.update(Text(f"📁 {item_count} items", style="dim"))
                except PermissionError:
                    info_widget.update(Text("📁 (no access)", style="dim red"))
            else:
                # Show file size
                size = stat.st_size
                if size < 1024:
                    size_str = f"{size} B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.1f} KB"
                else:
                    size_str = f"{size / (1024 * 1024):.1f} MB"

                # Get relative path from working dir
                if self.working_dir:
                    rel_path = os.path.relpath(path, self.working_dir)
                else:
                    rel_path = os.path.basename(path)

                info_widget.update(Text(f"{rel_path} ({size_str})", style="dim"))
        except OSError:
            info_widget.update(Text("", style="dim"))

    def _update_file_preview(self, path: str, is_dir: bool) -> None:
        """Update the file preview pane"""
        preview_widget = self.query_one("#file-preview-content", Static)

        if is_dir:
            preview_widget.update(Text("Select a file to preview", style="dim italic"))
            preview_widget.add_class("preview-placeholder")
            return

        # Check file extension
        ext = path.rsplit('.', 1)[-1].lower() if '.' in path else ""
        if ext in self.BINARY_EXTENSIONS:
            preview_widget.update(Text(f"Binary file ({ext})", style="dim italic"))
            preview_widget.add_class("preview-placeholder")
            return

        # Check file size
        try:
            size = os.path.getsize(path)
            if size > self.MAX_PREVIEW_SIZE:
                preview_widget.update(Text(f"File too large to preview ({size / 1024:.1f} KB)", style="dim italic"))
                preview_widget.add_class("preview-placeholder")
                return
        except OSError:
            preview_widget.update(Text("Cannot read file", style="dim italic red"))
            preview_widget.add_class("preview-placeholder")
            return

        # Read and display file content
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read(self.MAX_PREVIEW_SIZE)

            preview_widget.remove_class("preview-placeholder")

            # Use syntax highlighting if available
            from rich.syntax import Syntax

            # Map extensions to lexer names
            lexer_map = {
                'py': 'python',
                'js': 'javascript',
                'jsx': 'jsx',
                'ts': 'typescript',
                'tsx': 'tsx',
                'json': 'json',
                'md': 'markdown',
                'yaml': 'yaml',
                'yml': 'yaml',
                'toml': 'toml',
                'sh': 'bash',
                'bash': 'bash',
                'zsh': 'bash',
                'html': 'html',
                'css': 'css',
                'sql': 'sql',
                'rs': 'rust',
                'go': 'go',
                'rb': 'ruby',
                'java': 'java',
                'c': 'c',
                'cpp': 'cpp',
                'h': 'c',
                'hpp': 'cpp',
            }

            lexer = lexer_map.get(ext, 'text')
            syntax = Syntax(content, lexer, theme="monokai", line_numbers=True,
                           word_wrap=True, background_color="default")
            preview_widget.update(syntax)

        except Exception as e:
            preview_widget.update(Text(f"Error reading file: {e}", style="red"))
            preview_widget.add_class("preview-placeholder")

    @on(Button.Pressed, "#copy-path-btn")
    def on_copy_path_pressed(self) -> None:
        """Copy the selected path to clipboard"""
        if self.selected_path:
            self.post_message(self.CopyPathRequested(self.selected_path))

    @on(Button.Pressed, "#open-editor-btn")
    def on_open_editor_pressed(self) -> None:
        """Open the selected file in editor"""
        if self.selected_path and os.path.isfile(self.selected_path):
            self.post_message(self.OpenInEditorRequested(self.selected_path))

    @on(Button.Pressed, "#refresh-files-btn")
    def on_refresh_pressed(self) -> None:
        self.refresh_tree()

    @on(Button.Pressed, "#new-file-btn")
    def on_new_file_pressed(self) -> None:
        """Request new file creation"""
        # Use selected directory or working dir as parent
        if self.selected_path and os.path.isdir(self.selected_path):
            parent_dir = self.selected_path
        elif self.selected_path:
            parent_dir = os.path.dirname(self.selected_path)
        elif self.working_dir:
            parent_dir = self.working_dir
        else:
            return
        self.post_message(self.NewFileRequested(parent_dir))

    @on(Button.Pressed, "#new-folder-btn")
    def on_new_folder_pressed(self) -> None:
        """Request new folder creation"""
        if self.selected_path and os.path.isdir(self.selected_path):
            parent_dir = self.selected_path
        elif self.selected_path:
            parent_dir = os.path.dirname(self.selected_path)
        elif self.working_dir:
            parent_dir = self.working_dir
        else:
            return
        self.post_message(self.NewFolderRequested(parent_dir))

    @on(Button.Pressed, "#rename-btn")
    def on_rename_pressed(self) -> None:
        """Request rename of selected item"""
        if self.selected_path:
            self.post_message(self.RenameRequested(self.selected_path))

    @on(Button.Pressed, "#delete-btn")
    def on_delete_pressed(self) -> None:
        """Request deletion of selected item"""
        if self.selected_path:
            is_dir = os.path.isdir(self.selected_path)
            self.post_message(self.DeleteRequested(self.selected_path, is_directory=is_dir))

    # ─────────────────────────────────────────────────────────────────────────
    # File Search functionality
    # ─────────────────────────────────────────────────────────────────────────

    def _build_file_cache(self) -> None:
        """Build a cache of all file paths for search"""
        self._file_cache = []
        if not self.working_dir or not os.path.isdir(self.working_dir):
            return

        for root, dirs, files in os.walk(self.working_dir):
            # Filter out ignored directories
            dirs[:] = [d for d in dirs if d not in self.IGNORE and not d.startswith('.')]

            for f in files:
                if not f.startswith('.'):
                    full_path = os.path.join(root, f)
                    self._file_cache.append(full_path)

    def _fuzzy_match(self, pattern: str, text: str) -> tuple[bool, int]:
        """
        Simple fuzzy matching. Returns (matches, score).
        Lower score = better match.
        """
        pattern = pattern.lower()
        text = text.lower()

        # Exact substring match is best
        if pattern in text:
            return True, text.index(pattern)

        # Fuzzy: all chars must appear in order
        pattern_idx = 0
        score = 0
        last_match_idx = -1

        for i, char in enumerate(text):
            if pattern_idx < len(pattern) and char == pattern[pattern_idx]:
                # Penalize gaps between matched chars
                if last_match_idx >= 0:
                    score += (i - last_match_idx - 1) * 10
                last_match_idx = i
                pattern_idx += 1

        if pattern_idx == len(pattern):
            # Bonus for matching at word boundaries or start
            if text.startswith(pattern[0]):
                score -= 50
            return True, score

        return False, 999999

    def _search_files(self, query: str) -> List[tuple[str, int]]:
        """Search files matching query, return sorted by relevance"""
        if not query:
            return []

        results = []
        for path in self._file_cache:
            # Match against filename (not full path)
            filename = os.path.basename(path)
            matches, score = self._fuzzy_match(query, filename)
            if matches:
                # Also consider relative path for scoring
                rel_path = os.path.relpath(path, self.working_dir) if self.working_dir else path
                results.append((path, score, rel_path))

        # Sort by score, then by path length (shorter = better)
        results.sort(key=lambda x: (x[1], len(x[2])))
        return [(r[0], r[1]) for r in results[:20]]  # Return top 20

    @on(Input.Changed, "#file-search-input")
    async def on_search_changed(self, event: Input.Changed) -> None:
        """Update search results as user types"""
        query = event.value.strip()
        results_list = self.query_one("#file-search-results", ListView)
        files_content = self.query_one("#files-content", Vertical)

        if not query:
            # Hide results, show tree
            results_list.add_class("hidden")
            files_content.remove_class("hidden")
            self.search_mode = False
            return

        # Build cache if needed
        if not self._file_cache:
            await asyncio.to_thread(self._build_file_cache)

        # Search and display results
        results = await asyncio.to_thread(self._search_files, query)

        await results_list.clear()
        if results:
            for path, score in results:
                rel_path = os.path.relpath(path, self.working_dir) if self.working_dir else path
                icon = self._get_file_icon(os.path.basename(path))
                item = ListItem(Label(f"{icon} {rel_path}"))
                item.data = path  # Store full path in data attribute
                await results_list.append(item)

        # Show results, hide tree
        results_list.remove_class("hidden")
        files_content.add_class("hidden")
        self.search_mode = True

    @on(Input.Submitted, "#file-search-input")
    async def on_search_submitted(self, event: Input.Submitted) -> None:
        """Open first result when Enter pressed"""
        results_list = self.query_one("#file-search-results", ListView)
        if results_list.highlighted_child:
            path = getattr(results_list.highlighted_child, 'data', None)
            if path and os.path.isfile(path):
                self.post_message(self.OpenInEditorRequested(path))
                # Clear search
                search_input = self.query_one("#file-search-input", Input)
                search_input.value = ""

    @on(ListView.Selected, "#file-search-results")
    async def on_search_result_selected(self, event: ListView.Selected) -> None:
        """Open file when search result clicked"""
        path = getattr(event.item, 'data', None)
        if path and os.path.isfile(path):
            self.selected_path = path
            self._update_file_info(path, is_dir=False)
            self._update_file_preview(path, is_dir=False)
            self.post_message(self.FileSelected(path, is_directory=False))

    def watch_working_dir(self, new_dir: Optional[str]) -> None:
        """Refresh tree and clear cache when working directory changes"""
        self._file_cache = []  # Clear cache
        self.refresh_tree()


# ─────────────────────────────────────────────────────────────────────────────
# Git Panel - Repository status display
# ─────────────────────────────────────────────────────────────────────────────

class GitPanel(Container):
    """Panel for displaying git repository status"""

    working_dir: reactive[Optional[str]] = reactive(None)

    class StageAllRequested(Message):
        """Posted when stage all is requested"""
        pass

    class UnstageAllRequested(Message):
        """Posted when unstage all is requested"""
        pass

    class FileStageRequested(Message):
        """Posted when a specific file staging is requested"""
        def __init__(self, file_path: str, stage: bool = True):
            super().__init__()
            self.file_path = file_path
            self.stage = stage  # True = stage, False = unstage

    class CommitRequested(Message):
        """Posted when a commit is requested"""
        def __init__(self, message: str):
            super().__init__()
            self.message = message

    class ViewDiffRequested(Message):
        """Posted when diff viewer is requested"""
        pass

    def compose(self) -> ComposeResult:
        yield Label("Git", classes="panel-title")
        yield VerticalScroll(
            Static("", id="git-status-display"),
            Static("", id="git-commits-display"),
            id="git-content",
            classes="git-content"
        )
        with Container(classes="git-controls"):
            yield Button("Stage All", id="stage-all-btn", classes="control-btn")
            yield Button("Unstage", id="unstage-all-btn", classes="control-btn")
            yield Button("Diff", id="view-diff-btn", classes="control-btn")
            yield Button("Refresh", id="refresh-git-btn", classes="control-btn")
        # Commit section
        with Container(id="git-commit-section", classes="git-commit-section"):
            yield Input(placeholder="Commit message...", id="commit-message-input", classes="commit-input")
            yield Button("Commit", id="commit-btn", variant="success", classes="control-btn", disabled=True)

    def watch_working_dir(self, new_dir: Optional[str]) -> None:
        """Refresh git status when working directory changes"""
        self.refresh_status()

    @work(exclusive=True)
    async def refresh_status(self) -> None:
        """Refresh git status display using API"""
        status_display = self.query_one("#git-status-display", Static)
        commits_display = self.query_one("#git-commits-display", Static)

        if not self.working_dir or not os.path.isdir(self.working_dir):
            status_display.update(Text("No project selected", style="dim"))
            commits_display.update(Text(""))
            return

        # Check if it's a git repo (quick local check)
        git_dir = os.path.join(self.working_dir, ".git")
        if not os.path.isdir(git_dir):
            status_display.update(Text("Not a git repository", style="dim"))
            commits_display.update(Text(""))
            return

        try:
            async with httpx.AsyncClient(base_url=HTTP_BASE_URL, timeout=10.0) as client:
                # Fetch status and log in parallel
                status_task = client.get("/git/status", params={"repo_path": self.working_dir})
                log_task = client.get("/git/log", params={"repo_path": self.working_dir, "count": 5})

                status_resp, log_resp = await asyncio.gather(status_task, log_task)

                # Format status
                status_text = self._format_status_from_api(status_resp.json() if status_resp.status_code == 200 else None)
                status_display.update(status_text)

                # Format commits
                commits_text = self._format_commits_from_api(log_resp.json() if log_resp.status_code == 200 else None)
                commits_display.update(commits_text)

        except Exception as e:
            debug_log(f"Error fetching git info: {e}", "error")
            # Fallback to local subprocess calls
            status, commits = await asyncio.to_thread(self._get_git_info, self.working_dir)
            status_display.update(status)
            commits_display.update(commits)

    def _format_status_from_api(self, data: Optional[Dict]) -> Text:
        """Format git status from API response"""
        text = Text()

        if not data:
            text.append("Failed to get status", style="red")
            return text

        # Branch
        branch = data.get("branch")
        if branch:
            text.append("Branch: ", style="bold")
            text.append(f"{branch}\n", style="cyan bold")

        # Ahead/behind
        ahead = data.get("ahead", 0)
        behind = data.get("behind", 0)
        if ahead > 0:
            text.append(f"↑{ahead} ", style="green")
        if behind > 0:
            text.append(f"↓{behind} ", style="yellow")
        if ahead > 0 or behind > 0:
            text.append("\n")

        # Clean check
        if data.get("clean"):
            text.append("\n✓ Working tree clean", style="green dim")
            return text

        # Staged files
        staged = data.get("staged", [])
        if staged:
            text.append("\nStaged:\n", style="bold green")
            for item in staged[:5]:
                file = item.get("file", "") if isinstance(item, dict) else item
                status = item.get("status", "+") if isinstance(item, dict) else "+"
                text.append(f"  {status} {file}\n", style="green")
            if len(staged) > 5:
                text.append(f"  ... and {len(staged) - 5} more\n", style="dim")

        # Modified files
        modified = data.get("modified", [])
        if modified:
            text.append("\nModified:\n", style="bold yellow")
            for file in modified[:5]:
                text.append(f"  M {file}\n", style="yellow")
            if len(modified) > 5:
                text.append(f"  ... and {len(modified) - 5} more\n", style="dim")

        # Untracked files
        untracked = data.get("untracked", [])
        if untracked:
            text.append("\nUntracked:\n", style="bold red")
            for file in untracked[:5]:
                text.append(f"  ? {file}\n", style="red")
            if len(untracked) > 5:
                text.append(f"  ... and {len(untracked) - 5} more\n", style="dim")

        return text

    def _format_commits_from_api(self, data: Optional[Dict]) -> Text:
        """Format commits from API response"""
        text = Text()

        if not data:
            return text

        commits = data.get("commits", [])
        if not commits:
            return text

        text.append("\nRecent Commits:\n", style="bold magenta")
        for commit in commits:
            hash_str = commit.get("hash", "")
            message = commit.get("message", "")
            text.append(f"  {hash_str} ", style="cyan dim")
            # Truncate long messages
            if len(message) > 40:
                message = message[:37] + "..."
            text.append(f"{message}\n", style="")

        return text

    def _get_git_info(self, repo_path: str) -> tuple:
        """Get formatted git status and recent commits (fallback)"""
        status = self._get_git_status(repo_path)
        commits = self._get_recent_commits(repo_path)
        return status, commits

    def _get_recent_commits(self, repo_path: str) -> Text:
        """Get recent commits (fallback for when API unavailable)"""
        text = Text()

        # Get last 5 commits
        log_output = self._run_git(repo_path, [
            "log", "--oneline", "--no-decorate", "-n", "5"
        ])

        if not log_output:
            return text

        text.append("\nRecent Commits:\n", style="bold magenta")
        for line in log_output.split('\n'):
            if line:
                # Split hash and message
                parts = line.split(' ', 1)
                if len(parts) == 2:
                    hash_str, message = parts
                    text.append(f"  {hash_str} ", style="cyan dim")
                    # Truncate long messages
                    if len(message) > 40:
                        message = message[:37] + "..."
                    text.append(f"{message}\n", style="")
                else:
                    text.append(f"  {line}\n", style="dim")

        return text

    def _get_git_status(self, repo_path: str) -> Text:
        """Get formatted git status (fallback for when API unavailable)"""
        text = Text()

        # Get current branch
        branch = self._run_git(repo_path, ["branch", "--show-current"])
        if branch:
            text.append("Branch: ", style="bold")
            text.append(f"{branch}\n", style="cyan bold")

        # Get ahead/behind info
        upstream = self._run_git(repo_path, ["rev-parse", "--abbrev-ref", "@{upstream}"])
        if upstream:
            ahead_behind = self._run_git(repo_path, ["rev-list", "--left-right", "--count", f"{upstream}...HEAD"])
            if ahead_behind:
                parts = ahead_behind.split()
                if len(parts) == 2:
                    behind, ahead = parts
                    if int(ahead) > 0:
                        text.append(f"↑{ahead} ", style="green")
                    if int(behind) > 0:
                        text.append(f"↓{behind} ", style="yellow")
                    if int(ahead) > 0 or int(behind) > 0:
                        text.append("\n")

        # Get status
        status_output = self._run_git(repo_path, ["status", "--porcelain"])

        if not status_output:
            text.append("\n✓ Working tree clean", style="green dim")
            return text

        # Parse status
        staged = []
        modified = []
        untracked = []

        for line in status_output.split('\n'):
            if not line:
                continue
            index_status = line[0]
            worktree_status = line[1]
            filename = line[3:]

            if index_status != ' ' and index_status != '?':
                staged.append((index_status, filename))
            if worktree_status != ' ' and worktree_status != '?':
                modified.append((worktree_status, filename))
            if index_status == '?' and worktree_status == '?':
                untracked.append(filename)

        # Display sections
        if staged:
            text.append("\nStaged:\n", style="bold green")
            for status, name in staged[:5]:
                text.append(f"  {status} {name}\n", style="green")
            if len(staged) > 5:
                text.append(f"  ... and {len(staged) - 5} more\n", style="dim")

        if modified:
            text.append("\nModified:\n", style="bold yellow")
            for status, name in modified[:5]:
                text.append(f"  {status} {name}\n", style="yellow")
            if len(modified) > 5:
                text.append(f"  ... and {len(modified) - 5} more\n", style="dim")

        if untracked:
            text.append("\nUntracked:\n", style="bold red")
            for name in untracked[:5]:
                text.append(f"  ? {name}\n", style="red")
            if len(untracked) > 5:
                text.append(f"  ... and {len(untracked) - 5} more\n", style="dim")

        return text

    def _run_git(self, repo_path: str, args: List[str]) -> Optional[str]:
        """Run a git command and return output"""
        try:
            result = subprocess.run(
                ["git", "-C", repo_path] + args,
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return None

    @on(Button.Pressed, "#refresh-git-btn")
    def on_refresh_pressed(self) -> None:
        self.refresh_status()

    @on(Button.Pressed, "#stage-all-btn")
    def on_stage_all_pressed(self) -> None:
        self.post_message(self.StageAllRequested())

    @on(Button.Pressed, "#unstage-all-btn")
    def on_unstage_all_pressed(self) -> None:
        self.post_message(self.UnstageAllRequested())

    @on(Input.Changed, "#commit-message-input")
    def on_commit_message_changed(self, event: Input.Changed) -> None:
        """Enable/disable commit button based on message content"""
        commit_btn = self.query_one("#commit-btn", Button)
        commit_btn.disabled = not event.value.strip()

    @on(Button.Pressed, "#commit-btn")
    def on_commit_pressed(self) -> None:
        """Handle commit button press"""
        commit_input = self.query_one("#commit-message-input", Input)
        message = commit_input.value.strip()
        if message:
            self.post_message(self.CommitRequested(message))
            # Clear the input after sending
            commit_input.value = ""

    @on(Button.Pressed, "#view-diff-btn")
    def on_view_diff_pressed(self) -> None:
        """Handle view diff button press"""
        self.post_message(self.ViewDiffRequested())


# ─────────────────────────────────────────────────────────────────────────────
# Build Panel - Project build/test commands
# ─────────────────────────────────────────────────────────────────────────────

class BuildCommand:
    """Represents a runnable build/test command"""
    def __init__(self, name: str, command: str, category: str = "build"):
        self.name = name
        self.command = command
        self.category = category  # "build", "test", "lint", "dev", "other"


class BuildCommandItem(ListItem):
    """A list item representing a build command"""

    def __init__(self, command: BuildCommand, **kwargs):
        super().__init__(**kwargs)
        self.build_command = command

    def compose(self) -> ComposeResult:
        # Category icons
        icons = {
            "build": "🔨",
            "test": "🧪",
            "lint": "✨",
            "dev": "🚀",
            "other": "📋"
        }
        icon = icons.get(self.build_command.category, "📋")

        text = Text()
        text.append(f" {icon} ", style="")
        text.append(self.build_command.name, style="bold")
        text.append(f"  {self.build_command.command}", style="dim italic")

        yield Label(text)


class BuildPanel(Container):
    """Panel for running build/test commands"""

    working_directory: reactive[Optional[str]] = reactive(None)

    class RunCommandRequested(Message):
        """Posted when a command should be run in terminal"""
        def __init__(self, command: str):
            super().__init__()
            self.command = command

    def compose(self) -> ComposeResult:
        yield Label("Build / Test", classes="panel-title")
        yield Static("No project detected", id="build-project-type", classes="build-project-type")
        yield ListView(id="build-commands-list", classes="build-commands-list")
        with Container(classes="build-controls"):
            yield Button("Run", id="run-build-btn", variant="primary", classes="control-btn")
            yield Button("Refresh", id="refresh-build-btn", classes="control-btn")

    def on_mount(self) -> None:
        self.refresh_commands()

    def watch_working_directory(self, new_dir: Optional[str]) -> None:
        """React to working directory changes"""
        self.refresh_commands()

    def set_working_directory(self, directory: Optional[str]) -> None:
        """Set the working directory for command detection"""
        self.working_directory = directory

    @work(exclusive=True)
    async def refresh_commands(self) -> None:
        """Refresh the list of available commands based on project type"""
        directory = self.working_directory
        commands = []
        project_type = "No project detected"

        if directory and os.path.isdir(directory):
            # Detect project type and get commands
            commands, project_type = await asyncio.to_thread(
                self._detect_project_commands, directory
            )

        # Update project type label
        type_label = self.query_one("#build-project-type", Static)
        type_label.update(project_type)

        # Update command list
        list_view = self.query_one("#build-commands-list", ListView)
        await list_view.clear()

        if not commands:
            await list_view.append(ListItem(
                Label("No commands found", classes="no-commands")
            ))
            return

        for cmd in commands:
            await list_view.append(BuildCommandItem(cmd))

    def _detect_project_commands(self, directory: str) -> tuple:
        """Detect project type and available commands.

        Returns:
            (list of BuildCommand, project_type_string)
        """
        commands = []
        project_type = "Unknown project"

        # Check for package.json (Node.js/npm)
        package_json = os.path.join(directory, "package.json")
        if os.path.exists(package_json):
            project_type = "Node.js (package.json)"
            commands.extend(self._get_npm_scripts(package_json))

        # Check for pyproject.toml (Python/Poetry/PDM)
        pyproject = os.path.join(directory, "pyproject.toml")
        if os.path.exists(pyproject):
            project_type = "Python (pyproject.toml)"
            commands.extend(self._get_python_commands(directory))

        # Check for setup.py (Python/setuptools)
        setup_py = os.path.join(directory, "setup.py")
        if os.path.exists(setup_py) and not os.path.exists(pyproject):
            project_type = "Python (setup.py)"
            commands.extend(self._get_python_commands(directory))

        # Check for Makefile
        makefile = os.path.join(directory, "Makefile")
        if os.path.exists(makefile):
            if project_type == "Unknown project":
                project_type = "Make project"
            commands.extend(self._get_make_targets(makefile))

        # Check for Cargo.toml (Rust)
        cargo_toml = os.path.join(directory, "Cargo.toml")
        if os.path.exists(cargo_toml):
            project_type = "Rust (Cargo)"
            commands.extend(self._get_cargo_commands())

        # Check for go.mod (Go)
        go_mod = os.path.join(directory, "go.mod")
        if os.path.exists(go_mod):
            project_type = "Go (go.mod)"
            commands.extend(self._get_go_commands())

        return commands, project_type

    def _get_npm_scripts(self, package_json_path: str) -> List[BuildCommand]:
        """Extract npm scripts from package.json"""
        import json
        commands = []
        try:
            with open(package_json_path, 'r') as f:
                pkg = json.load(f)
                scripts = pkg.get("scripts", {})

                # Categorize known script names
                categories = {
                    "build": ["build", "compile", "bundle", "dist"],
                    "test": ["test", "test:unit", "test:e2e", "test:integration", "coverage"],
                    "lint": ["lint", "lint:fix", "format", "prettier", "eslint"],
                    "dev": ["dev", "start", "serve", "watch"],
                }

                for name, cmd in scripts.items():
                    category = "other"
                    for cat, patterns in categories.items():
                        if any(p in name.lower() for p in patterns):
                            category = cat
                            break

                    commands.append(BuildCommand(
                        name=name,
                        command=f"npm run {name}",
                        category=category
                    ))
        except (json.JSONDecodeError, IOError):
            pass
        return commands

    def _get_python_commands(self, directory: str) -> List[BuildCommand]:
        """Get common Python project commands"""
        commands = []

        # Check for pytest
        if os.path.exists(os.path.join(directory, "pytest.ini")) or \
           os.path.exists(os.path.join(directory, "tests")):
            commands.append(BuildCommand("pytest", "pytest", "test"))
            commands.append(BuildCommand("pytest -v", "pytest -v", "test"))

        # Check for ruff/black/isort
        commands.append(BuildCommand("ruff check", "ruff check .", "lint"))
        commands.append(BuildCommand("ruff format", "ruff format .", "lint"))

        # Check for pip install
        if os.path.exists(os.path.join(directory, "requirements.txt")):
            commands.append(BuildCommand("pip install", "pip install -r requirements.txt", "build"))

        if os.path.exists(os.path.join(directory, "pyproject.toml")):
            commands.append(BuildCommand("pip install -e", "pip install -e .", "build"))

        return commands

    def _get_make_targets(self, makefile_path: str) -> List[BuildCommand]:
        """Extract make targets from Makefile"""
        commands = []
        try:
            with open(makefile_path, 'r') as f:
                content = f.read()

                # Simple regex to find targets (lines starting with word followed by :)
                import re
                # Match targets like "build:", "test:", but not ".PHONY:" or variable assignments
                for match in re.finditer(r'^([a-zA-Z_][a-zA-Z0-9_-]*):', content, re.MULTILINE):
                    target = match.group(1)
                    if target.startswith('.'):
                        continue

                    # Categorize
                    category = "other"
                    if "build" in target or "all" == target:
                        category = "build"
                    elif "test" in target:
                        category = "test"
                    elif "lint" in target or "check" in target or "fmt" in target:
                        category = "lint"
                    elif "dev" in target or "run" in target or "serve" in target:
                        category = "dev"

                    commands.append(BuildCommand(
                        name=f"make {target}",
                        command=f"make {target}",
                        category=category
                    ))
        except IOError:
            pass
        return commands

    def _get_cargo_commands(self) -> List[BuildCommand]:
        """Get standard Cargo commands for Rust projects"""
        return [
            BuildCommand("cargo build", "cargo build", "build"),
            BuildCommand("cargo build --release", "cargo build --release", "build"),
            BuildCommand("cargo test", "cargo test", "test"),
            BuildCommand("cargo check", "cargo check", "lint"),
            BuildCommand("cargo clippy", "cargo clippy", "lint"),
            BuildCommand("cargo fmt", "cargo fmt", "lint"),
            BuildCommand("cargo run", "cargo run", "dev"),
        ]

    def _get_go_commands(self) -> List[BuildCommand]:
        """Get standard Go commands"""
        return [
            BuildCommand("go build", "go build ./...", "build"),
            BuildCommand("go test", "go test ./...", "test"),
            BuildCommand("go test -v", "go test -v ./...", "test"),
            BuildCommand("go vet", "go vet ./...", "lint"),
            BuildCommand("go fmt", "go fmt ./...", "lint"),
            BuildCommand("go run", "go run .", "dev"),
        ]

    @on(ListView.Selected, "#build-commands-list")
    def on_command_selected(self, event: ListView.Selected) -> None:
        """Run the selected command when clicked"""
        if isinstance(event.item, BuildCommandItem):
            self.post_message(self.RunCommandRequested(event.item.build_command.command))

    @on(Button.Pressed, "#run-build-btn")
    def on_run_pressed(self) -> None:
        """Run the highlighted command"""
        list_view = self.query_one("#build-commands-list", ListView)
        if list_view.highlighted_child and isinstance(list_view.highlighted_child, BuildCommandItem):
            self.post_message(self.RunCommandRequested(
                list_view.highlighted_child.build_command.command
            ))

    @on(Button.Pressed, "#refresh-build-btn")
    def on_refresh_pressed(self) -> None:
        self.refresh_commands()
