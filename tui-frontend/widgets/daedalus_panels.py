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
            yield Button("Copy Path", id="copy-path-btn", classes="control-btn")
            yield Button("Refresh", id="refresh-files-btn", classes="control-btn")

    def on_mount(self) -> None:
        tree = self.query_one("#files-tree", Tree)
        tree.show_root = True
        tree.guide_depth = 3

    def watch_working_dir(self, new_dir: Optional[str]) -> None:
        """Refresh tree when working directory changes"""
        self.refresh_tree()

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
