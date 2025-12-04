"""
Daedalus Widget - Textual widget for Claude Code terminal rendering.

Named after the mythological master craftsman, Daedalus is the builder
that pairs with Cass (the oracle/seer).

This refactored version uses TmuxTerminal (based on terminal_fast.py)
for better performance through batched output and debounced refresh.
"""

import os
import re
from pathlib import Path
from typing import Optional

from textual.widget import Widget
from textual.reactive import reactive
from textual import on
from textual.widgets import Button, Static
from textual.containers import Container, Vertical
from textual.app import ComposeResult
from rich.text import Text

from .pty_manager import PTYManager, debug_log
from .tmux_terminal import TmuxTerminal, check_tmux_available

# Check if dependencies are available
try:
    import pyte
    PYTE_AVAILABLE = True
except ImportError:
    PYTE_AVAILABLE = False

# Path to the Daedalus CLAUDE.md template and config
TEMPLATE_PATH = Path(__file__).parent.parent.parent.parent / "backend" / "templates" / "CLAUDE_TEMPLATE.md"
CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "config" / "daedalus.json"

# Markers for the managed section
DAEDALUS_BEGIN = "<!-- DAEDALUS_BEGIN -->"
DAEDALUS_END = "<!-- DAEDALUS_END -->"


def load_daedalus_config() -> dict:
    """Load Daedalus configuration from config file."""
    if not CONFIG_PATH.exists():
        return {}
    try:
        import json
        return json.loads(CONFIG_PATH.read_text())
    except Exception as e:
        debug_log(f"Failed to load config: {e}", "warning")
        return {}


def substitute_template_vars(content: str, config: dict) -> str:
    """Substitute template variables with config values."""
    user_config = config.get("user", {})

    replacements = {
        "{{USER_NAME}}": user_config.get("name", "the user"),
        "{{USER_COMMUNICATION_STYLE}}": user_config.get("communication_style", "Not specified"),
    }

    for placeholder, value in replacements.items():
        content = content.replace(placeholder, value)

    return content


def inject_claude_template(working_dir: str) -> None:
    """
    Inject or update the Daedalus section in a project's CLAUDE.md.

    If CLAUDE.md doesn't exist, creates it from the template.
    If it exists but has no Daedalus section, prepends the section.
    If it exists with a Daedalus section, updates that section only.

    Template variables (e.g., {{USER_NAME}}) are substituted from config/daedalus.json.
    """
    if not working_dir or not os.path.isdir(working_dir):
        return

    claude_md_path = Path(working_dir) / "CLAUDE.md"

    # Read the template
    if not TEMPLATE_PATH.exists():
        debug_log(f"Template not found at {TEMPLATE_PATH}", "warning")
        return

    template_content = TEMPLATE_PATH.read_text()

    # Load config and substitute variables
    config = load_daedalus_config()
    template_content = substitute_template_vars(template_content, config)

    # Extract just the Daedalus section from template
    match = re.search(
        rf'{re.escape(DAEDALUS_BEGIN)}.*?{re.escape(DAEDALUS_END)}',
        template_content,
        re.DOTALL
    )
    if not match:
        debug_log("Could not find Daedalus markers in template", "warning")
        return

    daedalus_section = match.group(0)

    if not claude_md_path.exists():
        # Create new file from template
        claude_md_path.write_text(template_content)
        debug_log(f"Created CLAUDE.md at {claude_md_path}", "info")
    else:
        # Update existing file
        existing_content = claude_md_path.read_text()

        if DAEDALUS_BEGIN in existing_content:
            # Replace existing Daedalus section
            updated_content = re.sub(
                rf'{re.escape(DAEDALUS_BEGIN)}.*?{re.escape(DAEDALUS_END)}',
                daedalus_section,
                existing_content,
                flags=re.DOTALL
            )
            claude_md_path.write_text(updated_content)
            debug_log(f"Updated Daedalus section in {claude_md_path}", "info")
        else:
            # Prepend Daedalus section to existing content
            updated_content = daedalus_section + "\n\n" + existing_content
            claude_md_path.write_text(updated_content)
            debug_log(f"Prepended Daedalus section to {claude_md_path}", "info")


class DaedalusWidget(Widget, can_focus=True):
    """
    Claude Code terminal widget using TmuxTerminal for PTY-based rendering.

    Provides a full terminal emulator interface for Claude Code sessions,
    with tmux backend for session persistence and the performance benefits
    of the patched textual-terminal (batched output, debounced refresh).
    """

    BINDINGS = []  # Capture all keys, don't let them bubble

    DEFAULT_CSS = """
    DaedalusWidget {
        height: 1fr;
        width: 1fr;
    }

    DaedalusWidget .daedalus-content {
        height: 1fr;
        width: 1fr;
        background: #1e1e1e;
        padding: 0;
    }

    DaedalusWidget .daedalus-no-session {
        height: 1fr;
        width: 1fr;
        align: center middle;
        padding: 2;
    }

    DaedalusWidget .session-info {
        text-align: center;
        margin-bottom: 2;
    }

    DaedalusWidget .spawn-btn {
        margin: 1;
    }

    DaedalusWidget .session-list {
        height: auto;
        max-height: 50%;
        margin-top: 2;
    }

    DaedalusWidget .session-item {
        margin: 0 2;
    }

    DaedalusWidget .session-controls {
        dock: bottom;
        height: auto;
        background: #2d2d2d;
        padding: 0 1;
        layout: horizontal;
    }

    DaedalusWidget .session-name {
        width: 1fr;
        padding: 1;
        color: #888888;
    }

    DaedalusWidget .control-btn {
        margin: 0 1;
        min-width: 10;
    }

    DaedalusWidget .hidden {
        display: none;
    }

    DaedalusWidget TmuxTerminal {
        height: 1fr;
        width: 1fr;
    }
    """

    # Reactive properties
    session_name: reactive[Optional[str]] = reactive(None)
    is_connected: reactive[bool] = reactive(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.pty_manager = PTYManager()
        self._terminal: Optional[TmuxTerminal] = None
        self._current_tmux_session: Optional[str] = None

    def compose(self) -> ComposeResult:
        """Compose the widget layout."""
        # No-session view
        with Vertical(id="no-session-view", classes="daedalus-no-session"):
            yield Static(
                Text("🏛️ Daedalus", style="bold cyan") +
                Text("\nClaude Code Terminal", style="dim"),
                classes="session-info"
            )

            if not PYTE_AVAILABLE:
                yield Static(
                    Text("⚠️ pyte library not installed\n", style="yellow") +
                    Text("Run: pip install pyte", style="dim"),
                    classes="session-info"
                )
            elif not check_tmux_available():
                yield Static(
                    Text("⚠️ tmux not installed\n", style="yellow") +
                    Text("Session persistence requires tmux", style="dim"),
                    classes="session-info"
                )
            else:
                yield Button("🚀 Start New Session", id="spawn-session-btn", variant="primary", classes="spawn-btn")

                # Existing sessions list
                with Container(id="existing-sessions", classes="session-list"):
                    yield Static("", id="sessions-list-content")

        # Session controls (hidden initially, shown when connected)
        with Container(id="session-controls", classes="session-controls hidden"):
            yield Static("", id="session-name-display", classes="session-name")
            yield Button("⏹ Detach", id="detach-btn", variant="warning", classes="control-btn")
            yield Button("🗑 Kill", id="kill-btn", variant="error", classes="control-btn")
            yield Button("➕ New", id="new-session-btn", variant="primary", classes="control-btn")

        # Terminal container (hidden initially)
        yield Container(id="terminal-container", classes="daedalus-content hidden")

    async def on_mount(self) -> None:
        """Initialize on mount - check for existing sessions."""
        debug_log("[Daedalus] Widget mounted", "info")
        await self._refresh_session_list()

    async def _refresh_session_list(self) -> None:
        """Refresh the list of existing tmux sessions."""
        if not PYTE_AVAILABLE or not check_tmux_available():
            return

        sessions = self.pty_manager.list_tmux_sessions()

        try:
            content = self.query_one("#sessions-list-content", Static)
            if sessions:
                text = Text("Existing Sessions:\n", style="bold")
                for session in sessions:
                    text.append(f"  • {session}\n", style="cyan")
                text.append("\nClick session name to attach", style="dim")
                content.update(text)

                # Add buttons for existing sessions
                container = self.query_one("#existing-sessions", Container)
                # Remove old session buttons
                for btn in container.query(".session-btn"):
                    btn.remove()
                # Add new buttons
                for session in sessions:
                    btn = Button(f"📎 {session}", id=f"attach-{session}", classes="session-btn session-item")
                    container.mount(btn)
            else:
                content.update(Text("No existing sessions", style="dim"))
                # Remove old session buttons when there are no sessions
                container = self.query_one("#existing-sessions", Container)
                for btn in container.query(".session-btn"):
                    btn.remove()
        except Exception:
            pass

    def watch_is_connected(self, connected: bool) -> None:
        """React to connection state changes."""
        try:
            no_session = self.query_one("#no-session-view")
            terminal_container = self.query_one("#terminal-container")
            controls = self.query_one("#session-controls")
            session_display = self.query_one("#session-name-display", Static)

            if connected:
                no_session.add_class("hidden")
                terminal_container.remove_class("hidden")
                controls.remove_class("hidden")
                # Update session name display
                if self._current_tmux_session:
                    session_display.update(Text(f"📎 {self._current_tmux_session}", style="dim cyan"))
            else:
                no_session.remove_class("hidden")
                terminal_container.add_class("hidden")
                controls.add_class("hidden")
                session_display.update("")
        except Exception:
            pass

    async def spawn_session(
        self,
        name: Optional[str] = None,
        working_dir: Optional[str] = None,
        enable_sidepanes: bool = True,
        lazygit_pane: bool = True,
        editor_pane: bool = True,
        editor_command: Optional[str] = None
    ) -> bool:
        """
        Spawn a new Claude Code session.

        Args:
            name: Session name (auto-generated if not provided)
            working_dir: Working directory for the session
            enable_sidepanes: Enable additional panes (lazygit, editor)
            lazygit_pane: Add lazygit sidebar on the right
            editor_pane: Add text editor pane below Claude
            editor_command: Editor to use (default: $EDITOR or nvim)

        Returns:
            True if successful, False otherwise
        """
        if not PYTE_AVAILABLE:
            return False

        # Inject/update CLAUDE.md template in the working directory
        if working_dir:
            inject_claude_template(working_dir)

        # Generate name if not provided
        if not name:
            from datetime import datetime
            name = f"adhoc-{datetime.now().strftime('%H%M%S')}"

        # Get widget size
        cols = max(80, self.size.width)
        rows = max(24, self.size.height)

        # Spawn the tmux session via PTYManager (this creates the session but doesn't attach)
        debug_log(f"Spawning session: name={name}, cols={cols}, rows={rows}", "info")

        # Create tmux session name
        tmux_session = f"daedalus-{name}" if not name.startswith("daedalus-") else name

        # Create the tmux session
        session = self.pty_manager.spawn_session(
            name=name,
            command="claude",
            cols=cols,
            rows=rows,
            working_dir=working_dir,
            enable_sidepanes=enable_sidepanes,
            lazygit_pane=lazygit_pane,
            editor_pane=editor_pane,
            editor_command=editor_command
        )

        if session:
            debug_log(f"Session created: {tmux_session}", "success")
            # Detach from the session created by spawn_session (it creates a PTY attachment)
            self.pty_manager.detach_session(session.name)
            # Now connect using TmuxTerminal
            await self._connect_to_session(tmux_session)
            return True

        debug_log("Session creation failed", "error")
        return False

    async def attach_session(self, tmux_session: str) -> bool:
        """
        Attach to an existing tmux session.

        Args:
            tmux_session: Name of the tmux session

        Returns:
            True if successful, False otherwise
        """
        if not PYTE_AVAILABLE:
            return False

        if not self.pty_manager.tmux_session_exists(tmux_session):
            debug_log(f"Session {tmux_session} does not exist", "error")
            return False

        await self._connect_to_session(tmux_session)
        return True

    async def _connect_to_session(self, tmux_session: str) -> None:
        """Connect to a tmux session using TmuxTerminal."""
        self._current_tmux_session = tmux_session
        self.session_name = tmux_session

        # Create TmuxTerminal widget
        self._terminal = TmuxTerminal(
            tmux_session=tmux_session,
            default_colors="textual",
            id="daedalus-terminal"
        )

        # Mount the terminal in the container
        try:
            container = self.query_one("#terminal-container")
            # Remove any existing terminal
            for existing in container.query("TmuxTerminal"):
                existing.remove()
            await container.mount(self._terminal)

            # Start the terminal
            self._terminal.start()

            self.is_connected = True

            # Focus the terminal
            self._terminal.focus()

        except Exception as e:
            debug_log(f"Error connecting to session: {e}", "error")
            self._terminal = None
            self._current_tmux_session = None

    @on(Button.Pressed, "#spawn-session-btn")
    async def on_spawn_session(self, event: Button.Pressed) -> None:
        """Handle spawn session button click."""
        # Get project context from app if available
        working_dir = None
        name = None
        try:
            app = self.app
            if hasattr(app, 'current_project_id') and app.current_project_id:
                name = f"project-{app.current_project_id}"
                # Get project working directory from sidebar
                from widgets import Sidebar
                sidebar = app.query_one("#sidebar", Sidebar)
                project = next((p for p in sidebar.projects if p["id"] == app.current_project_id), None)
                if project:
                    working_dir = project.get("working_directory")
                    debug_log(f"Using project working_dir: {working_dir}", "info")
        except Exception as e:
            debug_log(f"Error getting project context: {e}", "error")

        await self.spawn_session(name=name, working_dir=working_dir)

    @on(Button.Pressed, ".session-btn")
    async def on_attach_session(self, event: Button.Pressed) -> None:
        """Handle attach session button click."""
        btn_id = event.button.id
        if btn_id and btn_id.startswith("attach-"):
            session_name = btn_id[7:]  # Remove "attach-" prefix
            await self.attach_session(session_name)

    @on(Button.Pressed, "#detach-btn")
    async def on_detach_session(self, event: Button.Pressed) -> None:
        """Handle detach button click."""
        await self.disconnect()

    @on(Button.Pressed, "#kill-btn")
    async def on_kill_session(self, event: Button.Pressed) -> None:
        """Handle kill session button click."""
        await self.kill_session()

    @on(Button.Pressed, "#new-session-btn")
    async def on_new_session(self, event: Button.Pressed) -> None:
        """Handle new session button click (while connected)."""
        # Disconnect from current session first
        await self.disconnect()
        # Spawn a new session
        await self.on_spawn_session(event)

    async def disconnect(self, refresh_list: bool = True) -> None:
        """Disconnect from current session (without killing tmux)."""
        if self._terminal:
            self._terminal.stop()
            try:
                self._terminal.remove()
            except Exception:
                pass
            self._terminal = None

        self._current_tmux_session = None
        self.session_name = None
        self.is_connected = False

        if refresh_list:
            await self._refresh_session_list()

    async def kill_session(self) -> None:
        """Kill the current session entirely."""
        if self._current_tmux_session:
            session_name = self._current_tmux_session

            # Disconnect first (don't refresh yet - session still exists)
            await self.disconnect(refresh_list=False)

            # Kill tmux session
            self.pty_manager.kill_tmux_session(session_name)

            # Small delay to let tmux finish cleanup
            import asyncio
            await asyncio.sleep(0.1)

            # Now refresh the list
            await self._refresh_session_list()

    def render(self) -> Text:
        """Render the widget."""
        # The actual rendering is handled by the composed widgets
        return Text("")

    async def cleanup(self) -> None:
        """Clean up resources on shutdown."""
        if self._terminal:
            self._terminal.stop()

        self.pty_manager.cleanup()
