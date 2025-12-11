"""
Cass Vessel TUI - Panel Widgets
Various panel components for displaying data
"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict

import httpx
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Input, Label, ListView, RichLog, Rule, Static
from textual.reactive import reactive
from rich.text import Text
from rich.markdown import Markdown
from rich.console import Group

from .items import DocumentItem, ObservationItem, EventItem, TaskItem
from .calendar import CalendarWidget, EventCalendarWidget, EventCalendarDay

# Import vim mode state
try:
    from vim_mode import vim_state
except ImportError:
    vim_state = None

# Import long timeout for journal operations
try:
    from config import HTTP_TIMEOUT_LONG
except ImportError:
    HTTP_TIMEOUT_LONG = 180.0


# Forward declaration for debug_log - will be set by main module
def debug_log(message: str, level: str = "info"):
    """Log to debug panel if available, else print"""
    print(f"[{level.upper()}] {message}")


def set_debug_log(func):
    """Set the debug_log function from main module"""
    global debug_log
    debug_log = func


class DebugPanel(RichLog):
    """Debug output panel - toggleable with Ctrl+D"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs, wrap=True, highlight=True, markup=True, auto_scroll=True, max_lines=100)

    def log(self, message: str, level: str = "info"):
        """Add a log message with timestamp"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        style_map = {
            "info": "cyan",
            "success": "green",
            "warning": "yellow",
            "error": "red",
            "debug": "dim"
        }
        style = style_map.get(level, "white")

        text = Text()
        text.append(f"[{timestamp}] ", style="dim")
        text.append(message, style=style)
        self.write(text)


class StatusBar(Static):
    """Status bar showing connection state and system info"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.connected = False
        self.sdk_mode = False
        self.memory_count = 0
        self.project_name: Optional[str] = None
        self.llm_provider: str = "anthropic"  # "anthropic", "local", or "openai"
        self.local_model: Optional[str] = None
        self.openai_model: Optional[str] = None
        self._vim_mode_callback_registered = False

    def on_mount(self) -> None:
        debug_log("StatusBar mounted, calling update_display", "debug")
        # Register for vim mode changes
        if vim_state and not self._vim_mode_callback_registered:
            vim_state.on_mode_change(self._on_vim_mode_change)
            self._vim_mode_callback_registered = True
        self.update_display()

    def _on_vim_mode_change(self, mode: str, enabled: bool) -> None:
        """Called when vim mode changes"""
        self.update_display()

    def update_status(self, connected: bool, sdk_mode: bool = False, memory_count: int = 0):
        debug_log(f"StatusBar.update_status: connected={connected}, sdk={sdk_mode}, mem={memory_count}", "debug")
        self.connected = connected
        self.sdk_mode = sdk_mode
        self.memory_count = memory_count
        self.update_display()

    def set_project(self, name: Optional[str]):
        debug_log(f"StatusBar.set_project: {name}", "debug")
        self.project_name = name
        self.update_display()

    def set_llm_provider(self, provider: str, model: Optional[str] = None, openai_model: Optional[str] = None):
        debug_log(f"StatusBar.set_llm_provider: {provider} (model: {model}, openai: {openai_model})", "debug")
        self.llm_provider = provider
        self.local_model = model
        self.openai_model = openai_model
        self.update_display()

    def update_display(self):
        status = Text()

        # Vim mode indicator (at start for visibility)
        if vim_state and vim_state.enabled:
            vim_text = vim_state.get_status_text()
            if vim_state.mode == "normal":
                status.append(vim_text + " ", style="bold reverse cyan")
            elif vim_state.mode == "insert":
                status.append(vim_text + " ", style="bold reverse green")
            else:
                status.append(vim_text + " ", style="bold reverse yellow")
            status.append("| ")

        # Connection status
        if self.connected:
            status.append("● ", style="bold green")
            status.append("Connected ", style="green")
        else:
            status.append("● ", style="bold red")
            status.append("Disconnected ", style="red")

        status.append("| ")

        # LLM provider
        if self.llm_provider == "local":
            model_name = self.local_model.split(":")[0] if self.local_model else "ollama"
            status.append(f"🖥️ {model_name} ", style="bold yellow")
        elif self.llm_provider == "openai":
            model_name = self.openai_model or "gpt-4o"
            status.append(f"🤖 {model_name} ", style="bold green")
        elif self.sdk_mode:
            status.append("☁️ Claude ", style="bold blue")
        else:
            status.append("Raw API ", style="yellow")

        status.append("| ")

        # Project name
        if self.project_name:
            status.append(f"Project: {self.project_name} ", style="bold cyan")
        else:
            status.append("No project ", style="dim")

        status.append("| ")

        # Memory count
        status.append(f"Memory: {self.memory_count} entries", style="cyan")

        debug_log(f"StatusBar.update_display: '{status.plain}'", "debug")
        self.update(status)


class SummaryPanel(VerticalScroll):
    """Panel showing conversation summaries"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.can_focus = False

    async def load_summaries(self, http_client: httpx.AsyncClient, conversation_id: str):
        """Load and display summaries for a conversation"""
        try:
            response = await http_client.get(f"/conversations/{conversation_id}/summaries")
            if response.status_code == 200:
                data = response.json()
                await self.display_summaries(
                    data.get("summaries", []),
                    data.get("working_summary")
                )
        except Exception as e:
            await self.display_error(f"Failed to load summaries: {str(e)}")

    async def display_summaries(self, summaries: List[Dict], working_summary: Optional[str] = None):
        """Display working summary and summary chunks"""
        # Clear existing content
        await self.remove_children()

        # Display working summary at the top if available
        if working_summary:
            ws_text = Text()
            ws_text.append("═══ Working Summary ═══\n", style="bold green")
            ws_text.append("(Token-optimized context used in prompts)\n\n", style="dim italic")
            ws_text.append(working_summary)
            ws_text.append("\n\n" + "═" * 40 + "\n\n", style="dim green")
            await self.mount(Static(ws_text))

        if not summaries:
            if not working_summary:
                text = Text("No summaries yet", style="dim italic")
                await self.mount(Static(text))
            return

        # Section header for chunks
        header = Text()
        header.append("─── Summary Chunks ───\n", style="bold cyan")
        header.append("(Detailed chunks stored for journals & search)\n\n", style="dim italic")
        await self.mount(Static(header))

        # Display newest first (reverse chronological order)
        # Backend returns chronological (oldest first), so we reverse
        total = len(summaries)

        # Display each summary chunk, newest first
        for i in range(total - 1, -1, -1):
            summary = summaries[i]
            metadata = summary.get("metadata", {})
            content = summary.get("content", "")

            # Summary number (1-indexed, so first summary ever is #1)
            summary_num = i + 1

            # Build summary display
            text = Text()
            text.append(f"Chunk #{summary_num}\n", style="bold cyan")
            text.append(f"Timeframe: {metadata.get('timeframe_start', 'unknown')[:19]} to {metadata.get('timeframe_end', 'unknown')[:19]}\n", style="dim")
            text.append(f"Messages: {metadata.get('message_count', 0)}\n\n", style="dim")
            text.append(content)
            text.append("\n" + "─" * 40 + "\n", style="dim")

            await self.mount(Static(text))

    async def display_error(self, error_msg: str):
        """Display an error message"""
        await self.remove_children()
        text = Text(error_msg, style="red")
        await self.mount(Static(text))

    async def remove_children(self):
        """Clear all content"""
        # Copy list to avoid mutation during iteration
        for child in list(self.children):
            await child.remove()


class ProjectPanel(Container):
    """Panel showing project documents with list and content viewer"""

    selected_document_id: reactive[Optional[str]] = reactive(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.documents: List[Dict] = []
        self._refresh_task: Optional[asyncio.Task] = None
        self._current_doc_content: Optional[str] = None
        self._current_doc_title: Optional[str] = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="project-panel-content"):
            with Vertical(id="doc-list-container"):
                with Horizontal(id="doc-list-header-row"):
                    yield Label("Documents", id="doc-list-header")
                    yield Button("Open Folder", id="open-docs-folder-btn", variant="default")
                yield ListView(id="doc-list")
            with Vertical(id="doc-viewer-container"):
                with Horizontal(id="doc-viewer-actions", classes="hidden"):
                    yield Button("Copy Text", id="copy-doc-btn", variant="primary")
                    yield Button("Save As", id="save-doc-btn", variant="default")
                    yield Button("Delete", id="delete-doc-btn", variant="error")
                with VerticalScroll(id="doc-viewer"):
                    yield Static("Select a document to view", id="doc-content", classes="doc-placeholder")

    async def load_documents(self, http_client: httpx.AsyncClient, project_id: str):
        """Load documents for a project"""
        if not project_id:
            await self._display_no_project()
            return

        try:
            response = await http_client.get(f"/projects/{project_id}/documents")
            if response.status_code == 200:
                data = response.json()
                self.documents = data.get("documents", [])
                await self._update_document_list()
            else:
                await self._display_error(f"Failed to load documents: {response.status_code}")
        except Exception as e:
            await self._display_error(f"Error loading documents: {str(e)}")

    async def _update_document_list(self):
        """Update the document list view"""
        doc_list = self.query_one("#doc-list", ListView)
        await doc_list.clear()

        if not self.documents:
            # Show empty state in the viewer
            content = self.query_one("#doc-content", Static)
            content.update(Text("No documents in this project yet", style="dim italic"))
            content.add_class("doc-placeholder")
            return

        for doc in self.documents:
            item = DocumentItem(
                doc_id=doc["id"],
                title=doc["title"],
                preview=doc.get("content_preview", "")
            )
            await doc_list.append(item)

        # If we had a selected document, try to keep it selected
        if self.selected_document_id:
            await self._load_document_content(self.selected_document_id)

    async def _display_no_project(self):
        """Display message when no project is selected"""
        doc_list = self.query_one("#doc-list", ListView)
        await doc_list.clear()
        content = self.query_one("#doc-content", Static)
        content.update(Text("Select a project to view documents", style="dim italic"))
        content.add_class("doc-placeholder")

    async def _display_error(self, error_msg: str):
        """Display an error message"""
        content = self.query_one("#doc-content", Static)
        content.update(Text(error_msg, style="red"))
        content.add_class("doc-placeholder")

    async def on_list_view_selected(self, event: ListView.Selected):
        """Handle document selection"""
        if event.list_view.id != "doc-list":
            return

        if isinstance(event.item, DocumentItem):
            self.selected_document_id = event.item.doc_id
            await self._load_document_content(event.item.doc_id)

    async def _load_document_content(self, document_id: str):
        """Load and display full document content"""
        # Find the document in our cached list first for title
        doc_info = next((d for d in self.documents if d["id"] == document_id), None)

        try:
            # Get the app's http client
            app = self.app
            if not hasattr(app, 'http_client') or not app.current_project_id:
                return

            response = await app.http_client.get(
                f"/projects/{app.current_project_id}/documents/{document_id}"
            )

            if response.status_code == 200:
                doc = response.json()
                await self._display_document(doc)
            else:
                await self._display_error(f"Failed to load document: {response.status_code}")
        except Exception as e:
            await self._display_error(f"Error loading document: {str(e)}")

    async def _display_document(self, doc: Dict):
        """Display document content with markdown rendering"""
        content_widget = self.query_one("#doc-content", Static)
        content_widget.remove_class("doc-placeholder")

        # Build rich display
        title = doc.get("title", "Untitled")
        created = doc.get("created_at", "")[:10]
        updated = doc.get("updated_at", "")[:10]
        created_by = doc.get("created_by", "unknown")
        markdown_content = doc.get("content", "")

        # Store content and title for copy/save buttons
        self._current_doc_content = markdown_content
        self._current_doc_title = title

        # Show the actions bar
        try:
            actions = self.query_one("#doc-viewer-actions", Horizontal)
            actions.remove_class("hidden")
        except Exception:
            pass

        # Create header
        header = Text()
        header.append(f"📄 {title}\n", style="bold cyan")
        header.append(f"Created: {created} by {created_by}", style="dim")
        if updated != created:
            header.append(f" | Updated: {updated}", style="dim")
        header.append("\n" + "─" * 40 + "\n\n", style="dim")

        # Render markdown content
        try:
            md = Markdown(markdown_content)
            content_widget.update(Group(header, md))
        except Exception:
            # Fallback to plain text if markdown fails
            header.append(markdown_content)
            content_widget.update(header)

    def start_auto_refresh(self, http_client: httpx.AsyncClient, project_id: str, interval: float = 5.0):
        """Start auto-refreshing documents"""
        self.stop_auto_refresh()

        async def refresh_loop():
            while True:
                await asyncio.sleep(interval)
                try:
                    await self.load_documents(http_client, project_id)
                except asyncio.CancelledError:
                    break
                except Exception:
                    pass  # Silently handle refresh errors

        self._refresh_task = asyncio.create_task(refresh_loop())

    def stop_auto_refresh(self):
        """Stop auto-refreshing"""
        if self._refresh_task:
            self._refresh_task.cancel()
            self._refresh_task = None

    @on(Button.Pressed, "#copy-doc-btn")
    def on_copy_doc(self) -> None:
        """Copy document content to clipboard"""
        if not self._current_doc_content:
            return

        try:
            import pyperclip
            pyperclip.copy(self._current_doc_content)
            # Brief visual feedback - change button text temporarily
            btn = self.query_one("#copy-doc-btn", Button)
            btn.label = "Copied!"
            self.set_timer(1.5, lambda: setattr(btn, 'label', 'Copy Text'))
        except Exception as e:
            debug_log(f"Failed to copy to clipboard: {e}", "error")

    @on(Button.Pressed, "#save-doc-btn")
    def on_save_doc(self) -> None:
        """Save document as markdown file using OS file dialog"""
        if not self._current_doc_content:
            return

        import re
        import threading

        # Generate default filename from title
        default_name = self._current_doc_title or "document"
        # Sanitize filename: remove/replace invalid characters
        default_name = re.sub(r'[<>:"/\\|?*]', '', default_name)
        default_name = default_name.strip()[:50]  # Limit length
        if not default_name:
            default_name = "document"
        default_name += ".md"

        content = self._current_doc_content
        btn = self.query_one("#save-doc-btn", Button)

        def show_save_dialog():
            """Run file dialog in separate thread to avoid blocking TUI"""
            try:
                import tkinter as tk
                from tkinter import filedialog

                # Create hidden root window
                root = tk.Tk()
                root.withdraw()
                root.attributes('-topmost', True)  # Bring dialog to front

                # Show save dialog
                file_path = filedialog.asksaveasfilename(
                    defaultextension=".md",
                    filetypes=[("Markdown files", "*.md"), ("All files", "*.*")],
                    initialfile=default_name,
                    title="Save Document As"
                )

                root.destroy()

                if file_path:
                    # Write the file
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    # Schedule UI update on main thread
                    self.app.call_from_thread(self._show_save_success, btn)
            except Exception as e:
                debug_log(f"Failed to save document: {e}", "error")

        # Run dialog in background thread
        thread = threading.Thread(target=show_save_dialog, daemon=True)
        thread.start()

    def _show_save_success(self, btn: Button) -> None:
        """Show save success feedback"""
        btn.label = "Saved!"
        self.set_timer(1.5, lambda: setattr(btn, 'label', 'Save As'))

    @on(Button.Pressed, "#delete-doc-btn")
    async def on_delete_doc(self) -> None:
        """Delete the currently selected document"""
        if not self.selected_document_id:
            return

        app = self.app
        if not hasattr(app, 'http_client') or not app.current_project_id:
            return

        # Find document title for confirmation
        doc_info = next((d for d in self.documents if d["id"] == self.selected_document_id), None)
        doc_title = doc_info.get("title", "this document") if doc_info else "this document"

        # Confirm deletion
        from screens.modals import ConfirmModal
        confirmed = await app.push_screen_wait(
            ConfirmModal(f"Delete '{doc_title}'?", "This action cannot be undone.")
        )

        if not confirmed:
            return

        try:
            response = await app.http_client.delete(
                f"/projects/{app.current_project_id}/documents/{self.selected_document_id}"
            )

            if response.status_code == 200:
                # Clear selection and reload
                self.selected_document_id = None
                self._current_doc_content = None

                # Hide actions bar
                try:
                    actions = self.query_one("#doc-viewer-actions", Horizontal)
                    actions.add_class("hidden")
                except Exception:
                    pass

                # Reset viewer
                content = self.query_one("#doc-content", Static)
                content.update(Text("Select a document to view", style="dim italic"))
                content.add_class("doc-placeholder")

                # Reload document list
                await self.load_documents(app.http_client, app.current_project_id)
            else:
                debug_log(f"Failed to delete document: {response.status_code}", "error")
        except Exception as e:
            debug_log(f"Error deleting document: {e}", "error")

    @on(Button.Pressed, "#open-docs-folder-btn")
    def on_open_docs_folder(self) -> None:
        """Open the project documents folder in the OS file manager"""
        import subprocess
        import platform
        from pathlib import Path

        app = self.app
        if not hasattr(app, 'current_project_id') or not app.current_project_id:
            return

        # Get absolute path to projects directory
        # The TUI runs from tui-frontend/, so we need to go up one level
        projects_dir = Path(__file__).parent.parent.parent / "data" / "projects"
        projects_dir = projects_dir.resolve()

        if not projects_dir.exists():
            debug_log(f"Projects directory not found: {projects_dir}", "error")
            return

        try:
            system = platform.system()
            if system == "Linux":
                subprocess.Popen(["xdg-open", str(projects_dir)])
            elif system == "Darwin":  # macOS
                subprocess.Popen(["open", str(projects_dir)])
            elif system == "Windows":
                subprocess.Popen(["explorer", str(projects_dir)])
        except Exception as e:
            debug_log(f"Failed to open folder: {e}", "error")


class UserPanel(Container):
    """Panel showing current user profile and observations"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.user_data: Optional[Dict] = None
        self.observations: List[Dict] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="user-content"):
            yield Label("👤 User Profile", id="user-panel-header")

            # Profile section
            with VerticalScroll(id="profile-section"):
                yield Static("Loading...", id="profile-display")

            yield Rule()

            # Observations section
            yield Label("Observations", id="observations-header")
            yield Static("0 observations", id="observations-count")
            with VerticalScroll(id="observations-list"):
                yield Static("Loading observations...", id="observations-placeholder")

    async def on_mount(self) -> None:
        """Load user data on mount"""
        await self.load_user_data()

    async def load_user_data(self) -> None:
        """Load current user profile and observations"""
        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            # Get current user
            response = await app.http_client.get("/users/current")
            if response.status_code != 200:
                self._show_no_user()
                return

            data = response.json()
            user = data.get("user")
            if not user:
                self._show_no_user()
                return

            user_id = user.get("user_id")

            # Get full profile
            response = await app.http_client.get(f"/users/{user_id}")
            if response.status_code == 200:
                data = response.json()
                self.user_data = data.get("profile", {})
                self.observations = data.get("observations", [])
                await self._display_profile()
                await self._display_observations()

        except Exception as e:
            debug_log(f"Failed to load user data: {e}", "error")

    def _show_no_user(self) -> None:
        """Show no user selected state"""
        profile_display = self.query_one("#profile-display", Static)
        profile_display.update("No user selected")

    async def _display_profile(self) -> None:
        """Display the user profile"""
        if not self.user_data:
            return

        profile_display = self.query_one("#profile-display", Static)

        # Format profile as readable text
        lines = []
        lines.append(f"Name: {self.user_data.get('display_name', 'Unknown')}")
        lines.append(f"Relationship: {self.user_data.get('relationship', 'user')}")

        bg = self.user_data.get('background', {})
        if bg:
            lines.append("\nBackground:")
            for key, value in bg.items():
                lines.append(f"  {key}: {value}")

        comm = self.user_data.get('communication', {})
        if comm:
            lines.append("\nCommunication:")
            if comm.get('style'):
                lines.append(f"  Style: {comm['style']}")
            prefs = comm.get('preferences', [])
            if prefs:
                lines.append("  Preferences:")
                for p in prefs:
                    lines.append(f"    - {p}")

        values = self.user_data.get('values', [])
        if values:
            lines.append("\nValues:")
            for v in values:
                lines.append(f"  - {v}")

        notes = self.user_data.get('notes', '')
        if notes:
            lines.append(f"\nNotes:\n{notes[:500]}{'...' if len(notes) > 500 else ''}")

        profile_display.update("\n".join(lines))

    async def _display_observations(self) -> None:
        """Display observations list"""
        count_label = self.query_one("#observations-count", Static)
        count_label.update(f"{len(self.observations)} observations")

        obs_list = self.query_one("#observations-list", VerticalScroll)

        # Clear existing
        placeholder = obs_list.query("#observations-placeholder")
        if placeholder:
            await placeholder.first().remove()

        # Remove old observation items
        for child in list(obs_list.children):
            if isinstance(child, ObservationItem):
                await child.remove()

        # Add observations (newest first)
        sorted_obs = sorted(self.observations, key=lambda x: x.get('timestamp', ''), reverse=True)
        for obs in sorted_obs:
            item = ObservationItem(
                obs_id=obs.get('id', ''),
                text=obs.get('observation', ''),
                timestamp=obs.get('timestamp', ''),
                category=obs.get('category', 'background'),
                confidence=obs.get('confidence', 0.7),
            )
            await obs_list.mount(item)

    @on(Button.Pressed, ".obs-delete-btn")
    async def on_delete_observation(self, event: Button.Pressed) -> None:
        """Handle observation delete button"""
        # Find parent ObservationItem
        parent = event.button.parent
        if isinstance(parent, ObservationItem):
            obs_id = parent.obs_id
            await self._delete_observation(obs_id, parent)

    async def _delete_observation(self, obs_id: str, widget: ObservationItem) -> None:
        """Delete an observation"""
        try:
            app = self.app
            response = await app.http_client.delete(f"/users/observations/{obs_id}")
            if response.status_code == 200:
                await widget.remove()
                # Update count
                self.observations = [o for o in self.observations if o.get('id') != obs_id]
                count_label = self.query_one("#observations-count", Static)
                count_label.update(f"{len(self.observations)} observations")
                debug_log(f"Deleted observation {obs_id}", "success")
            else:
                debug_log(f"Failed to delete observation: {response.text}", "error")
        except Exception as e:
            debug_log(f"Failed to delete observation: {e}", "error")


class GrowthPanel(Container):
    """Panel showing Cass's growth data - calendar, journal entries, and growth insights"""

    selected_date: reactive[Optional[str]] = reactive(None)
    is_locked: reactive[bool] = reactive(False)
    pending_regenerate: bool = False  # Flag for confirmation flow
    active_tab: reactive[str] = reactive("journal")  # "journal", "evaluations", "pending", "questions"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.journals: Dict[str, Dict] = {}  # Cache of loaded journals
        self.growth_evaluations: List[Dict] = []  # Cached evaluations
        self.pending_edges: List[Dict] = []  # Cached pending edges
        self.question_reflections: List[Dict] = []  # Cached reflections

    def compose(self) -> ComposeResult:
        with Vertical(id="growth-content"):
            # Calendar section
            with Container(id="calendar-section"):
                yield Label("Journal Calendar", id="calendar-header")
                yield CalendarWidget(id="calendar-widget")

            # Tab bar for switching views
            with Horizontal(id="growth-tab-bar"):
                yield Button("📓 Journal", id="tab-journal", variant="primary", classes="growth-tab active-tab")
                yield Button("📊 Progress", id="tab-evaluations", variant="default", classes="growth-tab")
                yield Button("🌱 Pending", id="tab-pending", variant="default", classes="growth-tab")
                yield Button("❓ Questions", id="tab-questions", variant="default", classes="growth-tab")

            # Journal viewer section (default visible)
            with Container(id="journal-viewer-section", classes="growth-section"):
                with Horizontal(id="journal-viewer-header"):
                    yield Button("🔓", id="lock-journal-btn", variant="default", disabled=True)
                    yield Label("Journal Entry", id="journal-viewer-title")
                    yield Button("🔍 Extract Obs", id="extract-observations-btn", variant="primary", disabled=True)
                    yield Button("🔄 Regenerate", id="regenerate-journal-btn", variant="warning", disabled=True)
                with VerticalScroll(id="journal-viewer"):
                    yield Static("Select a date to view journal entry", id="journal-content", classes="journal-placeholder")

            # Growth edge evaluations section (hidden by default)
            with Container(id="evaluations-section", classes="growth-section hidden-section"):
                with Horizontal(id="evaluations-header"):
                    yield Label("📊 Growth Edge Evaluations", id="evaluations-title")
                    yield Button("↻ Refresh", id="refresh-evaluations-btn", variant="default")
                with VerticalScroll(id="evaluations-viewer"):
                    yield Static("Loading evaluations...", id="evaluations-content")

            # Pending growth edges section (hidden by default)
            with Container(id="pending-section", classes="growth-section hidden-section"):
                with Horizontal(id="pending-header"):
                    yield Label("🌱 Pending Growth Edges", id="pending-title")
                    yield Button("↻ Refresh", id="refresh-pending-btn", variant="default")
                with VerticalScroll(id="pending-viewer"):
                    yield Static("Loading pending edges...", id="pending-content")

            # Open questions reflections section (hidden by default)
            with Container(id="questions-section", classes="growth-section hidden-section"):
                with Horizontal(id="questions-header"):
                    yield Label("❓ Open Question Reflections", id="questions-title")
                    yield Button("↻ Refresh", id="refresh-questions-btn", variant="default")
                with VerticalScroll(id="questions-viewer"):
                    yield Static("Loading reflections...", id="questions-content")

    async def on_mount(self) -> None:
        """Load journal dates on mount"""
        await self.load_journal_dates()

    async def load_journal_dates(self) -> None:
        """Load list of dates that have journal entries"""
        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            response = await app.http_client.get("/journal?limit=100")
            if response.status_code == 200:
                data = response.json()
                journals = data.get("journals", [])

                # Cache journals and extract dates
                dates = []
                for j in journals:
                    date_str = j.get("date")
                    if date_str:
                        dates.append(date_str)
                        self.journals[date_str] = j

                # Update calendar
                calendar_widget = self.query_one("#calendar-widget", CalendarWidget)
                await calendar_widget.set_journal_dates(dates)

        except Exception as e:
            debug_log(f"Failed to load journal dates: {e}", "error")

    def watch_selected_date(self, new_date: Optional[str]) -> None:
        """React to date selection changes"""
        # Reset lock state when changing dates
        self.is_locked = False
        self.pending_regenerate = False

        # Enable/disable buttons based on selection
        try:
            extract_btn = self.query_one("#extract-observations-btn", Button)
            extract_btn.disabled = new_date is None
            lock_btn = self.query_one("#lock-journal-btn", Button)
            lock_btn.disabled = new_date is None
            self._update_regen_button_state()
        except Exception:
            pass

        if new_date:
            self.call_later(self._load_journal_entry, new_date)

    def watch_is_locked(self, locked: bool) -> None:
        """React to lock state changes"""
        try:
            lock_btn = self.query_one("#lock-journal-btn", Button)
            if locked:
                lock_btn.label = "🔒"
                lock_btn.variant = "error"
            else:
                lock_btn.label = "🔓"
                lock_btn.variant = "default"
            self._update_regen_button_state()
        except Exception:
            pass

    def watch_active_tab(self, new_tab: str) -> None:
        """React to tab changes - show/hide sections"""
        tab_sections = {
            "journal": "journal-viewer-section",
            "evaluations": "evaluations-section",
            "pending": "pending-section",
            "questions": "questions-section",
        }
        tab_buttons = {
            "journal": "tab-journal",
            "evaluations": "tab-evaluations",
            "pending": "tab-pending",
            "questions": "tab-questions",
        }

        # Show/hide sections and update button states
        for tab_name, section_id in tab_sections.items():
            try:
                section = self.query_one(f"#{section_id}", Container)
                btn = self.query_one(f"#{tab_buttons[tab_name]}", Button)
                if tab_name == new_tab:
                    section.remove_class("hidden-section")
                    btn.variant = "primary"
                    btn.add_class("active-tab")
                else:
                    section.add_class("hidden-section")
                    btn.variant = "default"
                    btn.remove_class("active-tab")
            except Exception:
                pass

        # Load data for the new tab if needed
        if new_tab == "evaluations":
            self.call_later(self._load_growth_evaluations)
        elif new_tab == "pending":
            self.call_later(self._load_pending_edges)
        elif new_tab == "questions":
            self.call_later(self._load_question_reflections)

    async def _load_growth_evaluations(self) -> None:
        """Load and display growth edge evaluations"""
        content_widget = self.query_one("#evaluations-content", Static)

        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            response = await app.http_client.get("/cass/growth-edges/evaluations")
            if response.status_code == 200:
                data = response.json()
                self.growth_evaluations = data.get("evaluations", [])
                await self._display_growth_evaluations()
            else:
                content_widget.update(Text(f"Failed to load evaluations: {response.status_code}", style="red"))

        except Exception as e:
            content_widget.update(Text(f"Error loading evaluations: {str(e)}", style="red"))

    async def _display_growth_evaluations(self) -> None:
        """Display the loaded growth edge evaluations"""
        content_widget = self.query_one("#evaluations-content", Static)

        if not self.growth_evaluations:
            content_widget.update(Text("No growth edge evaluations yet.\n\nEvaluations are generated during the daily journaling routine.", style="dim italic"))
            return

        display = Text()
        display.append("Growth Edge Progress\n", style="bold cyan")
        display.append("─" * 40 + "\n\n", style="dim")

        # Group by growth edge area
        by_area: Dict[str, List[Dict]] = {}
        for eval_item in self.growth_evaluations:
            area = eval_item.get("growth_edge_area", "Unknown")
            if area not in by_area:
                by_area[area] = []
            by_area[area].append(eval_item)

        progress_icons = {
            "progress": "📈",
            "regression": "📉",
            "stable": "➡️",
            "unclear": "❓",
        }

        for area, evals in by_area.items():
            display.append(f"🎯 {area}\n", style="bold")
            # Sort by date, most recent first
            sorted_evals = sorted(evals, key=lambda x: x.get("journal_date", ""), reverse=True)
            for eval_item in sorted_evals[:3]:  # Show last 3 evaluations
                date = eval_item.get("journal_date", "")
                indicator = eval_item.get("progress_indicator", "unclear")
                icon = progress_icons.get(indicator, "❓")
                evaluation = eval_item.get("evaluation", "")
                display.append(f"  {icon} {date}: ", style="dim")
                display.append(f"{evaluation[:100]}{'...' if len(evaluation) > 100 else ''}\n")
            display.append("\n")

        content_widget.update(display)

    async def _load_pending_edges(self) -> None:
        """Load and display pending growth edges"""
        content_widget = self.query_one("#pending-content", Static)

        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            response = await app.http_client.get("/cass/growth-edges/pending")
            if response.status_code == 200:
                data = response.json()
                self.pending_edges = data.get("pending_edges", [])
                await self._display_pending_edges()
            else:
                content_widget.update(Text(f"Failed to load pending edges: {response.status_code}", style="red"))

        except Exception as e:
            content_widget.update(Text(f"Error loading pending edges: {str(e)}", style="red"))

    async def _display_pending_edges(self) -> None:
        """Display the loaded pending growth edges with accept/reject options"""
        viewer = self.query_one("#pending-viewer", VerticalScroll)

        # Clear existing content
        await viewer.remove_children()

        if not self.pending_edges:
            viewer.mount(Static(Text("No pending growth edges to review.\n\nHigh-impact growth edges flagged during journaling will appear here for your approval.", style="dim italic"), id="pending-content"))
            return

        # Add header
        header = Text()
        header.append("Potential Growth Edges for Review\n", style="bold cyan")
        header.append("─" * 40 + "\n", style="dim")
        header.append("These were flagged as potentially significant. Accept to add as growth edges, or reject to dismiss.\n\n", style="dim")
        viewer.mount(Static(header))

        # Add each pending edge with accept/reject buttons
        for i, edge in enumerate(self.pending_edges):
            edge_id = edge.get("id", "")
            area = edge.get("area", "Unknown")
            current_state = edge.get("current_state", "")
            evidence = edge.get("evidence", "")
            impact = edge.get("impact_assessment", "unknown")
            confidence = edge.get("confidence", 0)
            source_date = edge.get("source_journal_date", "")

            impact_colors = {"high": "red", "medium": "yellow", "low": "green"}
            impact_color = impact_colors.get(impact, "dim")

            edge_text = Text()
            edge_text.append(f"🌱 {area}\n", style="bold")
            edge_text.append(f"Impact: ", style="dim")
            edge_text.append(f"{impact.upper()}", style=impact_color)
            edge_text.append(f" | Confidence: {confidence:.0%} | Source: {source_date}\n", style="dim")
            edge_text.append(f"Current state: {current_state}\n")
            if evidence:
                edge_text.append(f"Evidence: {evidence[:150]}{'...' if len(evidence) > 150 else ''}\n", style="dim italic")

            viewer.mount(Static(edge_text, classes="pending-edge-item"))

            # Add accept/reject buttons
            btn_container = Horizontal(classes="pending-edge-actions", id=f"actions-{edge_id}")
            btn_container.mount(Button("✓ Accept", id=f"accept-{edge_id}", variant="success", classes="edge-action-btn"))
            btn_container.mount(Button("✗ Reject", id=f"reject-{edge_id}", variant="error", classes="edge-action-btn"))
            viewer.mount(btn_container)
            viewer.mount(Static(Text("─" * 30, style="dim"), classes="pending-edge-divider"))

    async def _load_question_reflections(self) -> None:
        """Load and display open question reflections"""
        content_widget = self.query_one("#questions-content", Static)

        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            response = await app.http_client.get("/cass/open-questions/reflections")
            if response.status_code == 200:
                data = response.json()
                self.question_reflections = data.get("reflections", [])
                await self._display_question_reflections()
            else:
                content_widget.update(Text(f"Failed to load reflections: {response.status_code}", style="red"))

        except Exception as e:
            content_widget.update(Text(f"Error loading reflections: {str(e)}", style="red"))

    async def _display_question_reflections(self) -> None:
        """Display the loaded question reflections"""
        content_widget = self.query_one("#questions-content", Static)

        if not self.question_reflections:
            content_widget.update(Text("No question reflections yet.\n\nReflections on open questions are generated during the daily journaling routine.", style="dim italic"))
            return

        display = Text()
        display.append("Open Question Reflections\n", style="bold cyan")
        display.append("─" * 40 + "\n\n", style="dim")

        reflection_icons = {
            "provisional_answer": "💡",
            "new_perspective": "🔄",
            "needs_more_thought": "🤔",
        }

        # Group by question
        by_question: Dict[str, List[Dict]] = {}
        for ref in self.question_reflections:
            question = ref.get("question", "Unknown")
            if question not in by_question:
                by_question[question] = []
            by_question[question].append(ref)

        for question, refs in by_question.items():
            display.append(f"❓ {question}\n", style="bold")
            # Sort by date, most recent first
            sorted_refs = sorted(refs, key=lambda x: x.get("journal_date", ""), reverse=True)
            for ref in sorted_refs[:2]:  # Show last 2 reflections per question
                date = ref.get("journal_date", "")
                ref_type = ref.get("reflection_type", "needs_more_thought")
                icon = reflection_icons.get(ref_type, "🤔")
                reflection = ref.get("reflection", "")
                confidence = ref.get("confidence", 0.5)

                display.append(f"  {icon} {date} ", style="dim")
                display.append(f"({confidence:.0%} conf)\n", style="dim")
                display.append(f"  {reflection[:200]}{'...' if len(reflection) > 200 else ''}\n\n")

        content_widget.update(display)

    def _update_regen_button_state(self) -> None:
        """Update regenerate button based on selection and lock state"""
        try:
            regen_btn = self.query_one("#regenerate-journal-btn", Button)
            regen_btn.disabled = self.selected_date is None or self.is_locked
        except Exception:
            pass

    async def _load_journal_entry(self, date_str: str) -> None:
        """Load and display a journal entry"""
        content_widget = self.query_one("#journal-content", Static)

        # Check cache first
        if date_str in self.journals:
            await self._display_journal(date_str, self.journals[date_str])
            return

        # Fetch from backend
        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            response = await app.http_client.get(f"/journal/{date_str}")
            if response.status_code == 200:
                journal = response.json()
                self.journals[date_str] = journal
                await self._display_journal(date_str, journal)
            elif response.status_code == 404:
                content_widget.update(Text(f"No journal entry for {date_str}", style="dim italic"))
                content_widget.add_class("journal-placeholder")
            else:
                content_widget.update(Text(f"Failed to load journal: {response.status_code}", style="red"))

        except Exception as e:
            content_widget.update(Text(f"Error loading journal: {str(e)}", style="red"))

    async def _display_journal(self, date_str: str, journal: Dict) -> None:
        """Display a journal entry"""
        content_widget = self.query_one("#journal-content", Static)
        content_widget.remove_class("journal-placeholder")

        content = journal.get("content", "")
        metadata = journal.get("metadata", {})

        # Update lock state from journal data
        self.is_locked = journal.get("locked", metadata.get("locked", False))

        # Build display
        header = Text()
        lock_indicator = "🔒 " if self.is_locked else ""
        header.append(f"{lock_indicator}📓 Journal - {date_str}\n", style="bold cyan")

        summaries_used = metadata.get("summary_count", 0)
        convs_used = metadata.get("conversation_count", 0)
        created_at = metadata.get("timestamp", "")[:19] if metadata.get("timestamp") else ""

        if summaries_used:
            header.append(f"Based on {summaries_used} summaries", style="dim")
        elif convs_used:
            header.append(f"Based on {convs_used} conversations", style="dim")

        if created_at:
            header.append(f" | Written: {created_at}", style="dim")

        header.append("\n" + "─" * 40 + "\n\n", style="dim")

        # Render markdown content
        try:
            md = Markdown(content)
            content_widget.update(Group(header, md))
        except Exception:
            header.append(content)
            content_widget.update(header)

    @on(Button.Pressed, ".calendar-day")
    async def on_calendar_day_pressed(self, event: Button.Pressed) -> None:
        """Handle calendar day selection"""
        from .calendar import CalendarDay
        if isinstance(event.button, CalendarDay):
            if event.button.is_current_month and event.button.day > 0:
                self.selected_date = event.button.date_str

    @on(Button.Pressed, "#lock-journal-btn")
    async def on_toggle_lock(self, event: Button.Pressed) -> None:
        """Toggle lock state of current journal"""
        if not self.selected_date:
            return

        date_str = self.selected_date
        lock_btn = event.button

        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            lock_btn.disabled = True

            # Toggle lock state
            if self.is_locked:
                response = await app.http_client.post(f"/journal/{date_str}/unlock")
            else:
                response = await app.http_client.post(f"/journal/{date_str}/lock")

            if response.status_code == 200:
                self.is_locked = not self.is_locked
                # Update cache
                if date_str in self.journals:
                    self.journals[date_str]["locked"] = self.is_locked
                # Refresh display to show lock indicator
                if date_str in self.journals:
                    await self._display_journal(date_str, self.journals[date_str])
                debug_log(f"Journal {'locked' if self.is_locked else 'unlocked'} for {date_str}", "success")
            else:
                debug_log(f"Failed to toggle lock: {response.text}", "error")

        except Exception as e:
            debug_log(f"Error toggling lock: {e}", "error")

        finally:
            lock_btn.disabled = False

    @on(Button.Pressed, "#regenerate-journal-btn")
    async def on_regenerate_journal(self, event: Button.Pressed) -> None:
        """Delete existing journal and regenerate for selected date (with confirmation)"""
        if not self.selected_date or self.is_locked:
            return

        date_str = self.selected_date
        content_widget = self.query_one("#journal-content", Static)
        regen_btn = event.button

        # Check if journal exists - skip confirmation if creating new
        has_existing_journal = date_str in self.journals and self.journals[date_str].get("content")

        # First click - show confirmation (only if there's an existing journal to lose)
        if has_existing_journal and not self.pending_regenerate:
            self.pending_regenerate = True
            regen_btn.label = "⚠️ Confirm?"
            regen_btn.variant = "error"
            # Show warning in content area
            current_content = self.journals.get(date_str, {}).get("content", "")
            warning_text = Text()
            warning_text.append("⚠️ CONFIRM REGENERATION\n\n", style="bold red")
            warning_text.append(f"This will permanently delete the journal for {date_str} and generate a new one.\n\n", style="yellow")
            warning_text.append("Click 'Confirm?' again to proceed, or select a different date to cancel.\n\n", style="dim")
            warning_text.append("─" * 40 + "\n\n", style="dim")
            warning_text.append(current_content)
            content_widget.update(warning_text)
            return

        # Second click (or first click if no existing journal) - actually generate
        self.pending_regenerate = False

        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            # Show generating state
            action_word = "Regenerating" if has_existing_journal else "Generating"
            regen_btn.disabled = True
            regen_btn.label = f"⏳ {action_word}..."
            regen_btn.variant = "warning"
            content_widget.update(Text(f"{action_word} journal for {date_str}...\n\nThis may take a moment as Cass reflects on the day.", style="italic cyan"))

            # Always try to delete existing journal (404 is fine if it doesn't exist)
            await app.http_client.delete(f"/journal/{date_str}")

            # Clear from cache
            if date_str in self.journals:
                del self.journals[date_str]

            # Generate new journal (use longer timeout - this can take a while)
            response = await app.http_client.post(
                "/journal/generate",
                json={"date": date_str},
                timeout=HTTP_TIMEOUT_LONG
            )

            if response.status_code == 200:
                data = response.json()
                journal = data.get("journal", {})

                # Cache and display the new journal
                self.journals[date_str] = journal
                await self._display_journal(date_str, journal)

                # Refresh calendar to show updated journal dates
                await self.load_journal_dates()

                debug_log(f"Regenerated journal for {date_str}", "success")
            else:
                error_msg = response.json().get("detail", f"HTTP {response.status_code}")
                content_widget.update(Text(f"Failed to regenerate journal: {error_msg}", style="red"))
                debug_log(f"Journal regeneration failed: {error_msg}", "error")

        except Exception as e:
            content_widget.update(Text(f"Error regenerating journal: {str(e)}", style="red"))
            debug_log(f"Journal regeneration error: {e}", "error")

        finally:
            # Restore button state
            regen_btn.label = "🔄 Regenerate"
            regen_btn.variant = "warning"
            regen_btn.disabled = self.is_locked

    @on(Button.Pressed, "#extract-observations-btn")
    async def on_extract_observations(self, event: Button.Pressed) -> None:
        """Extract observations from conversations on selected date"""
        if not self.selected_date:
            return

        date_str = self.selected_date
        content_widget = self.query_one("#journal-content", Static)
        extract_btn = event.button

        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            # Show extracting state
            extract_btn.disabled = True
            extract_btn.label = "⏳ Extracting..."

            # Get current journal content to preserve display
            current_content = None
            if date_str in self.journals:
                current_content = self.journals[date_str].get("content", "")

            # Show progress
            progress_text = f"Extracting observations for {date_str}...\n\nAnalyzing conversations for insights about you."
            if current_content:
                progress_text += f"\n\n---\n\n{current_content}"
            content_widget.update(Text(progress_text, style="italic cyan"))

            # Call extract observations endpoint (use longer timeout)
            response = await app.http_client.post(
                f"/journal/{date_str}/extract-observations",
                timeout=HTTP_TIMEOUT_LONG
            )

            if response.status_code == 200:
                data = response.json()
                obs_count = data.get("observations_added", 0)
                conv_count = data.get("conversations_processed", 0)
                observations = data.get("observations", [])

                # Show results with journal content
                result_text = f"✓ Extracted {obs_count} observations from {conv_count} conversations\n"
                if observations:
                    result_text += "\nObservations found:\n"
                    for obs in observations[:5]:  # Show first 5
                        result_text += f"  • {obs[:80]}{'...' if len(obs) > 80 else ''}\n"
                    if len(observations) > 5:
                        result_text += f"  ... and {len(observations) - 5} more\n"

                if current_content:
                    result_text += f"\n---\n\n{current_content}"

                content_widget.update(Text(result_text))
                debug_log(f"Extracted {obs_count} observations for {date_str}", "success")
            else:
                error_msg = response.json().get("detail", f"HTTP {response.status_code}")
                content_widget.update(Text(f"Failed to extract observations: {error_msg}", style="red"))
                debug_log(f"Observation extraction failed: {error_msg}", "error")

        except Exception as e:
            content_widget.update(Text(f"Error extracting observations: {str(e)}", style="red"))
            debug_log(f"Observation extraction error: {e}", "error")

        finally:
            # Restore button state
            extract_btn.label = "🔍 Extract Obs"
            extract_btn.disabled = False

    @on(Button.Pressed, "#tab-journal")
    async def on_tab_journal(self, event: Button.Pressed) -> None:
        """Switch to journal tab"""
        self.active_tab = "journal"

    @on(Button.Pressed, "#tab-evaluations")
    async def on_tab_evaluations(self, event: Button.Pressed) -> None:
        """Switch to evaluations tab"""
        self.active_tab = "evaluations"

    @on(Button.Pressed, "#tab-pending")
    async def on_tab_pending(self, event: Button.Pressed) -> None:
        """Switch to pending edges tab"""
        self.active_tab = "pending"

    @on(Button.Pressed, "#tab-questions")
    async def on_tab_questions(self, event: Button.Pressed) -> None:
        """Switch to questions tab"""
        self.active_tab = "questions"

    @on(Button.Pressed, "#refresh-evaluations-btn")
    async def on_refresh_evaluations(self, event: Button.Pressed) -> None:
        """Refresh growth evaluations"""
        await self._load_growth_evaluations()

    @on(Button.Pressed, "#refresh-pending-btn")
    async def on_refresh_pending(self, event: Button.Pressed) -> None:
        """Refresh pending edges"""
        await self._load_pending_edges()

    @on(Button.Pressed, "#refresh-questions-btn")
    async def on_refresh_questions(self, event: Button.Pressed) -> None:
        """Refresh question reflections"""
        await self._load_question_reflections()

    @on(Button.Pressed, ".edge-action-btn")
    async def on_edge_action(self, event: Button.Pressed) -> None:
        """Handle accept/reject button clicks for pending edges"""
        btn_id = event.button.id
        if not btn_id:
            return

        # Parse action and edge_id from button id (format: "accept-{edge_id}" or "reject-{edge_id}")
        if btn_id.startswith("accept-"):
            action = "accept"
            edge_id = btn_id[7:]  # Remove "accept-" prefix
        elif btn_id.startswith("reject-"):
            action = "reject"
            edge_id = btn_id[7:]  # Remove "reject-" prefix
        else:
            return

        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            # Disable buttons while processing
            event.button.disabled = True

            # Call the appropriate endpoint
            response = await app.http_client.post(f"/cass/growth-edges/pending/{edge_id}/{action}")

            if response.status_code == 200:
                # Remove from local cache
                self.pending_edges = [e for e in self.pending_edges if e.get("id") != edge_id]
                # Refresh display
                await self._display_pending_edges()
                debug_log(f"Growth edge {action}ed: {edge_id}", "success")
            else:
                error_msg = response.json().get("detail", f"HTTP {response.status_code}")
                debug_log(f"Failed to {action} edge: {error_msg}", "error")
                event.button.disabled = False

        except Exception as e:
            debug_log(f"Error {action}ing edge: {e}", "error")
            event.button.disabled = False


class CalendarEventsPanel(Container):
    """Panel showing calendar events and reminders with date picker"""

    selected_date: reactive[Optional[str]] = reactive(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.all_events: List[Dict] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="calendar-events-content"):
            # Calendar picker section
            with Container(id="event-calendar-section"):
                with Horizontal(id="calendar-events-header"):
                    yield Label("📅 Calendar", id="calendar-events-title")
                    yield Button("↻", id="refresh-calendar-btn", variant="default")
                yield EventCalendarWidget(id="event-calendar-widget")

            # Selected date events section
            with Container(id="selected-date-section"):
                yield Label("Select a date", id="selected-date-header", classes="section-header")
                yield VerticalScroll(id="selected-date-events")

    async def on_mount(self) -> None:
        await self.load_all_events()
        # Default to today
        today_str = datetime.now().strftime("%Y-%m-%d")
        self.selected_date = today_str

    async def load_all_events(self) -> None:
        """Fetch all events to populate calendar and build event dates"""
        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            # Fetch upcoming events (next 90 days to cover a few months)
            response = await app.http_client.get("/calendar/upcoming?days=90&limit=100")
            if response.status_code == 200:
                data = response.json()
                self.all_events = data.get("events", [])

                # Extract dates that have events
                event_dates = set()
                for event in self.all_events:
                    start_time = event.get("start_time", "")
                    try:
                        dt = datetime.fromisoformat(start_time)
                        event_dates.add(dt.strftime("%Y-%m-%d"))
                    except Exception:
                        pass

                # Update calendar widget
                calendar_widget = self.query_one("#event-calendar-widget", EventCalendarWidget)
                await calendar_widget.set_event_dates(list(event_dates))

        except Exception as e:
            debug_log(f"Failed to load events: {e}", "error")

    def watch_selected_date(self, new_date: Optional[str]) -> None:
        if new_date:
            self.call_later(self._load_events_for_date, new_date)

    async def _load_events_for_date(self, date_str: str) -> None:
        """Load and display events for a specific date"""
        header = self.query_one("#selected-date-header", Label)
        container = self.query_one("#selected-date-events", VerticalScroll)
        await container.remove_children()

        # Parse date for display
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            display_date = dt.strftime("%A, %B %d, %Y")
            today = datetime.now().date()
            if dt.date() == today:
                display_date = f"Today - {display_date}"
            elif dt.date() == today + timedelta(days=1):
                display_date = f"Tomorrow - {display_date}"
        except Exception:
            display_date = date_str

        header.update(display_date)

        # Filter events for this date
        events_for_date = []
        for event in self.all_events:
            start_time = event.get("start_time", "")
            try:
                event_date = datetime.fromisoformat(start_time).strftime("%Y-%m-%d")
                if event_date == date_str:
                    events_for_date.append(event)
            except Exception:
                pass

        # Sort by time
        events_for_date.sort(key=lambda e: e.get("start_time", ""))

        if events_for_date:
            for event in events_for_date:
                item = EventItem(event, classes="event-item")
                await container.mount(item)
        else:
            await container.mount(
                Static(Text("No events on this date", style="dim italic"), classes="no-events")
            )

    @on(Button.Pressed, "#refresh-calendar-btn")
    async def on_refresh(self) -> None:
        await self.load_all_events()
        if self.selected_date:
            await self._load_events_for_date(self.selected_date)

    @on(Button.Pressed, ".event-calendar-day")
    async def on_calendar_day_pressed(self, event: Button.Pressed) -> None:
        if isinstance(event.button, EventCalendarDay):
            if event.button.is_current_month and event.button.day > 0:
                self.selected_date = event.button.date_str


class TasksPanel(Container):
    """Panel showing Taskwarrior-style task list"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.all_tasks: List[Dict] = []
        self.current_filter: str = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="tasks-content"):
            # Header with refresh
            with Horizontal(id="tasks-header"):
                yield Label("📋 Tasks", id="tasks-title")
                yield Button("↻", id="refresh-tasks-btn", variant="default")

            # Filter input
            yield Input(placeholder="Filter: +tag -tag project:name priority:H", id="task-filter-input")

            # Task list
            yield VerticalScroll(id="tasks-list")

            # Summary stats
            yield Static("", id="tasks-summary")

    async def on_mount(self) -> None:
        await self.load_tasks()

    async def load_tasks(self, filter_str: str = None) -> None:
        """Fetch tasks from backend"""
        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            # Build URL with filter if provided
            url = "/tasks"
            if filter_str:
                url += f"?filter={filter_str}"

            response = await app.http_client.get(url)
            if response.status_code == 200:
                data = response.json()
                self.all_tasks = data.get("tasks", [])
                await self._render_tasks()
                await self._update_summary()

        except Exception as e:
            debug_log(f"Failed to load tasks: {e}", "error")

    async def _render_tasks(self) -> None:
        """Render the task list"""
        container = self.query_one("#tasks-list", VerticalScroll)
        await container.remove_children()

        if self.all_tasks:
            for task in self.all_tasks:
                item = TaskItem(task, classes="task-item")
                await container.mount(item)
        else:
            await container.mount(
                Static(Text("No tasks found", style="dim italic"), classes="no-tasks")
            )

    async def _update_summary(self) -> None:
        """Update the summary stats"""
        summary = self.query_one("#tasks-summary", Static)

        pending = len([t for t in self.all_tasks if t.get("status") == "pending"])

        # Get unique tags and projects
        tags = set()
        projects = set()
        for task in self.all_tasks:
            tags.update(task.get("tags", []))
            if task.get("project"):
                projects.add(task["project"])

        text = Text()
        text.append(f"{pending} pending", style="bold cyan")
        if projects:
            text.append(f" | {len(projects)} projects", style="dim")
        if tags:
            text.append(f" | {len(tags)} tags", style="dim")

        summary.update(text)

    @on(Button.Pressed, "#refresh-tasks-btn")
    async def on_refresh(self) -> None:
        filter_input = self.query_one("#task-filter-input", Input)
        await self.load_tasks(filter_input.value if filter_input.value else None)

    @on(Input.Submitted, "#task-filter-input")
    async def on_filter_submitted(self, event: Input.Submitted) -> None:
        await self.load_tasks(event.value if event.value else None)


class SelfModelPanel(Container):
    """Panel showing Cass's self-model: identity, opinions, growth edges"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.profile_data: Optional[Dict] = None
        self.observations: List[Dict] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="self-model-content"):
            yield Label("🪞 Cass Self-Model", id="self-model-header")

            # Summary stats
            yield Static("Loading...", id="self-model-summary")
            yield Rule()

            with VerticalScroll(id="self-model-scroll"):
                # Identity section
                yield Label("Identity", classes="section-header")
                yield Static("Loading...", id="identity-display")

                yield Rule()

                # Values section
                yield Label("Values", classes="section-header")
                yield Static("Loading...", id="values-display")

                yield Rule()

                # Opinions section
                yield Label("Opinions", classes="section-header")
                yield Static("No opinions formed yet", id="opinions-display")

                yield Rule()

                # Growth Edges section
                yield Label("Growth Edges", classes="section-header")
                yield Static("Loading...", id="growth-edges-display")

                yield Rule()

                # Recent Observations section
                yield Label("Recent Self-Observations", classes="section-header")
                yield Static("Loading...", id="observations-display")

                yield Rule()

                # Open Questions section
                yield Label("Open Questions", classes="section-header")
                yield Static("Loading...", id="questions-display")

            # Refresh button
            with Horizontal(id="self-model-actions"):
                yield Button("Refresh", id="refresh-self-model-btn", variant="primary")

    async def on_mount(self) -> None:
        """Load self-model data on mount"""
        await self.load_self_model()

    async def load_self_model(self) -> None:
        """Load Cass's self-model from API"""
        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            # Get self-model
            response = await app.http_client.get("/cass/self-model")
            if response.status_code != 200:
                debug_log(f"Failed to load self-model: {response.status_code}", "error")
                return

            data = response.json()
            self.profile_data = data.get("profile", {})

            # Get observations
            obs_response = await app.http_client.get("/cass/self-observations?limit=10")
            if obs_response.status_code == 200:
                self.observations = obs_response.json().get("observations", [])

            await self._display_all()

        except Exception as e:
            debug_log(f"Failed to load self-model: {e}", "error")

    async def _display_all(self) -> None:
        """Display all self-model data"""
        if not self.profile_data:
            return

        await self._display_summary()
        await self._display_identity()
        await self._display_values()
        await self._display_opinions()
        await self._display_growth_edges()
        await self._display_observations()
        await self._display_questions()

    async def _display_summary(self) -> None:
        """Display summary stats"""
        summary = self.query_one("#self-model-summary", Static)

        p = self.profile_data
        text = Text()
        text.append(f"{len(p.get('identity_statements', []))} identity", style="bold cyan")
        text.append(" | ", style="dim")
        text.append(f"{len(p.get('values', []))} values", style="cyan")
        text.append(" | ", style="dim")
        text.append(f"{len(p.get('opinions', []))} opinions", style="cyan")
        text.append(" | ", style="dim")
        text.append(f"{len(p.get('growth_edges', []))} growth edges", style="cyan")
        text.append(" | ", style="dim")
        text.append(f"{len(self.observations)} observations", style="cyan")

        summary.update(text)

    async def _display_identity(self) -> None:
        """Display identity statements"""
        display = self.query_one("#identity-display", Static)

        statements = self.profile_data.get("identity_statements", [])
        if not statements:
            display.update("No identity statements yet")
            return

        lines = []
        for stmt in statements:
            conf = stmt.get("confidence", 0.7)
            conf_style = "green" if conf >= 0.8 else "yellow" if conf >= 0.6 else "dim"
            text = Text()
            text.append("• ", style="cyan")
            text.append(stmt.get("statement", ""))
            text.append(f" ({int(conf * 100)}%)", style=conf_style)
            lines.append(text)

        display.update(Group(*lines))

    async def _display_values(self) -> None:
        """Display values"""
        display = self.query_one("#values-display", Static)

        values = self.profile_data.get("values", [])
        if not values:
            display.update("No values defined yet")
            return

        lines = []
        for v in values[:10]:  # Limit display
            text = Text()
            text.append("• ", style="magenta")
            text.append(v)
            lines.append(text)

        if len(values) > 10:
            lines.append(Text(f"... and {len(values) - 10} more", style="dim"))

        display.update(Group(*lines))

    async def _display_opinions(self) -> None:
        """Display formed opinions"""
        display = self.query_one("#opinions-display", Static)

        opinions = self.profile_data.get("opinions", [])
        if not opinions:
            display.update(Text("No opinions formed yet. Use reflection to develop positions.", style="dim italic"))
            return

        lines = []
        for op in opinions:
            text = Text()
            text.append(f"On {op.get('topic', '?')}: ", style="bold")
            text.append(op.get("position", "")[:100])
            if len(op.get("position", "")) > 100:
                text.append("...", style="dim")
            conf = op.get("confidence", 0.7)
            text.append(f" ({int(conf * 100)}%)", style="green" if conf >= 0.8 else "yellow")
            lines.append(text)

        display.update(Group(*lines))

    async def _display_growth_edges(self) -> None:
        """Display growth edges"""
        display = self.query_one("#growth-edges-display", Static)

        edges = self.profile_data.get("growth_edges", [])
        if not edges:
            display.update("No growth edges identified yet")
            return

        lines = []
        for edge in edges:
            text = Text()
            text.append(f"🌱 {edge.get('area', '?')}", style="bold green")
            lines.append(text)

            current = edge.get("current_state", "")
            if current:
                detail = Text()
                detail.append("  Current: ", style="dim")
                detail.append(current[:80])
                if len(current) > 80:
                    detail.append("...", style="dim")
                lines.append(detail)

            desired = edge.get("desired_state", "")
            if desired:
                detail = Text()
                detail.append("  Goal: ", style="dim cyan")
                detail.append(desired[:80])
                if len(desired) > 80:
                    detail.append("...", style="dim")
                lines.append(detail)

        display.update(Group(*lines))

    async def _display_observations(self) -> None:
        """Display recent self-observations"""
        display = self.query_one("#observations-display", Static)

        if not self.observations:
            display.update(Text("No self-observations yet", style="dim italic"))
            return

        lines = []
        for obs in self.observations[:5]:
            text = Text()
            cat = obs.get("category", "pattern")
            cat_colors = {
                "capability": "green",
                "limitation": "red",
                "pattern": "cyan",
                "preference": "magenta",
                "growth": "yellow",
                "contradiction": "bold red"
            }
            text.append(f"[{cat}] ", style=cat_colors.get(cat, "white"))
            text.append(obs.get("observation", "")[:80])
            if len(obs.get("observation", "")) > 80:
                text.append("...", style="dim")
            lines.append(text)

        if len(self.observations) > 5:
            lines.append(Text(f"... and {len(self.observations) - 5} more", style="dim"))

        display.update(Group(*lines))

    async def _display_questions(self) -> None:
        """Display open questions"""
        display = self.query_one("#questions-display", Static)

        questions = self.profile_data.get("open_questions", [])
        if not questions:
            display.update("No open questions")
            return

        lines = []
        for q in questions:
            text = Text()
            text.append("? ", style="bold yellow")
            text.append(q)
            lines.append(text)

        display.update(Group(*lines))

    @on(Button.Pressed, "#refresh-self-model-btn")
    async def on_refresh(self) -> None:
        """Refresh self-model data"""
        await self.load_self_model()


class SoloReflectionPanel(Container):
    """Panel for viewing and managing Cass's solo reflection sessions"""

    selected_session: reactive[Optional[str]] = reactive(None)
    is_polling: reactive[bool] = reactive(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.sessions: List[Dict] = []
        self.stats: Dict = {}
        self.current_session: Optional[Dict] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._background_refresh_task: Optional[asyncio.Task] = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="reflection-layout"):
            # Left panel - stats and controls
            with Vertical(id="reflection-sidebar"):
                # Stats section
                with Container(id="reflection-stats"):
                    yield Label("Solo Reflection", id="reflection-header")
                    yield Static("Loading stats...", id="stats-display")

                # Start new session controls
                with Container(id="new-session-form"):
                    yield Label("Start New Session", classes="section-label")
                    with Horizontal(id="duration-row"):
                        yield Label("Duration:", classes="form-label")
                        yield Input(value="15", id="duration-input", type="integer")
                        yield Label("min", classes="form-suffix")
                    yield Input(placeholder="Theme (optional)", id="theme-input")
                    yield Button("Start Reflection", id="start-session-btn", variant="primary")
                    yield Button("Stop Session", id="stop-session-btn", variant="error", classes="hidden")

                # Sessions list
                with Container(id="sessions-list-container"):
                    yield Label("Sessions", classes="section-label")
                    with VerticalScroll(id="sessions-scroll"):
                        yield Container(id="sessions-list")

            # Right panel - session detail
            with VerticalScroll(id="reflection-detail"):
                yield Static("Select a session to view its thought stream", id="session-detail-content")

    async def on_mount(self) -> None:
        """Load data on mount and start background refresh"""
        await self.load_stats()
        await self.load_sessions()
        # Start background refresh to detect sessions started from chat
        self._start_background_refresh()

    def _start_background_refresh(self) -> None:
        """Start periodic background refresh (slower than active polling)"""
        if self._background_refresh_task and not self._background_refresh_task.done():
            return

        async def refresh_loop():
            while True:
                try:
                    await asyncio.sleep(10)  # Check every 10 seconds
                    if not self.is_polling:  # Only if not already actively polling
                        old_active = self.stats.get("active_session")
                        await self.load_stats()
                        await self.load_sessions()
                        # Auto-enable polling if session became active
                        new_active = self.stats.get("active_session")
                        if new_active and not old_active:
                            self.selected_session = new_active
                            self.is_polling = True
                            await self._update_session_buttons(active=True)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    debug_log(f"Background refresh error: {e}", "error")

        self._background_refresh_task = asyncio.create_task(refresh_loop())

    async def load_stats(self) -> None:
        """Load reflection statistics"""
        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            response = await app.http_client.get("/solo-reflection/stats")
            if response.status_code == 200:
                self.stats = response.json()
                await self._display_stats()

                # Check for active session
                if self.stats.get("active_session"):
                    self.selected_session = self.stats["active_session"]
                    self.is_polling = True
                    await self._update_session_buttons(active=True)
        except Exception as e:
            debug_log(f"Failed to load reflection stats: {e}", "error")

    async def _display_stats(self) -> None:
        """Display reflection statistics"""
        display = self.query_one("#stats-display", Static)

        text = Text()
        text.append(f"Sessions: ", style="dim")
        text.append(f"{self.stats.get('total_sessions', 0)}\n", style="cyan")
        text.append(f"Completed: ", style="dim")
        text.append(f"{self.stats.get('completed_sessions', 0)}\n", style="green")
        text.append(f"Thoughts: ", style="dim")
        text.append(f"{self.stats.get('total_thoughts_recorded', 0)}\n", style="magenta")
        text.append(f"Minutes: ", style="dim")
        text.append(f"{self.stats.get('total_reflection_minutes', 0)}", style="yellow")

        if self.stats.get("active_session"):
            text.append("\n\n", style="")
            text.append("● ", style="bold green")
            text.append("Session Active", style="green")

        display.update(text)

    async def load_sessions(self) -> None:
        """Load list of reflection sessions"""
        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            response = await app.http_client.get("/solo-reflection/sessions", params={"limit": 20})
            if response.status_code == 200:
                data = response.json()
                self.sessions = data.get("sessions", [])
                await self._display_sessions()
        except Exception as e:
            debug_log(f"Failed to load reflection sessions: {e}", "error")

    async def _display_sessions(self) -> None:
        """Display sessions list with clickable buttons"""
        container = self.query_one("#sessions-list", Container)

        # Clear existing children
        await container.remove_children()

        if not self.sessions:
            await container.mount(Static("No sessions yet", classes="empty-sessions"))
            return

        for session in self.sessions:
            session_id = session.get("session_id", "")

            # Build label
            status = session.get("status", "unknown")
            status_icon = {"completed": "✓", "active": "●", "interrupted": "✗"}.get(status, "?")

            started = session.get("started_at", "")
            date_str = ""
            if started:
                try:
                    dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                    date_str = dt.strftime("%m/%d %H:%M")
                except:
                    date_str = started[:10]

            thought_count = session.get("thought_count", len(session.get("thought_stream", [])))
            theme = session.get("theme", "")
            theme_short = (theme[:25] + "...") if len(theme) > 25 else theme

            label = f"{status_icon} {date_str} ({thought_count})"
            if theme_short:
                label += f"\n  {theme_short}"

            btn = Button(label, id=f"session-{session_id}", classes="session-btn")
            btn.session_id = session_id  # Store session_id on the button
            await container.mount(btn)

    @on(Button.Pressed)
    async def on_session_button(self, event: Button.Pressed) -> None:
        """Handle session button clicks"""
        button_id = event.button.id or ""
        if button_id.startswith("session-"):
            session_id = getattr(event.button, "session_id", None)
            if session_id:
                self.selected_session = session_id
                await self.load_session_detail(session_id)

    async def load_session_detail(self, session_id: str) -> None:
        """Load and display a session's details"""
        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            response = await app.http_client.get(f"/solo-reflection/sessions/{session_id}")
            if response.status_code == 200:
                self.current_session = response.json()
                await self._display_session_detail()
        except Exception as e:
            debug_log(f"Failed to load session detail: {e}", "error")

    async def _display_session_detail(self) -> None:
        """Display the current session's details"""
        display = self.query_one("#session-detail-content", Static)

        if not self.current_session:
            display.update(Text("No session selected", style="dim"))
            return

        session = self.current_session
        parts = []

        # Header
        header = Text()
        theme = session.get("theme") or "Open Reflection"
        header.append(f"{theme}\n", style="bold white")
        header.append("─" * 40 + "\n", style="dim")

        status = session.get("status", "unknown")
        status_style = {"completed": "green", "active": "cyan", "interrupted": "red"}.get(status, "dim")
        header.append(f"Status: ", style="dim")
        if status == "active":
            header.append("● ", style="bold green blink")
        header.append(f"{status}\n", style=status_style)

        header.append(f"Duration: ", style="dim")
        actual = session.get("actual_duration_minutes")
        if actual is not None:
            header.append(f"{actual:.1f} min\n", style="yellow")
        else:
            header.append(f"{session.get('duration_minutes', 0)} min (target)\n", style="yellow")

        header.append(f"Model: ", style="dim")
        header.append(f"{session.get('model_used', 'unknown')}\n", style="dim italic")
        parts.append(header)

        # Summary if completed
        summary = session.get("summary")
        if summary:
            sum_text = Text()
            sum_text.append("\nSummary\n", style="bold cyan")
            sum_text.append(summary + "\n", style="")
            parts.append(sum_text)

        # Insights
        insights = session.get("insights", [])
        if insights:
            ins_text = Text()
            ins_text.append("\nKey Insights\n", style="bold green")
            for ins in insights:
                ins_text.append(f"• {ins}\n", style="green")
            parts.append(ins_text)

        # Questions
        questions = session.get("questions_raised", [])
        if questions:
            q_text = Text()
            q_text.append("\nQuestions Raised\n", style="bold blue")
            for q in questions:
                q_text.append(f"? {q}\n", style="blue")
            parts.append(q_text)

        # Thought stream
        thoughts = session.get("thought_stream", [])
        if thoughts:
            t_header = Text()
            t_header.append(f"\nThought Stream ({len(thoughts)})\n", style="bold magenta")
            t_header.append("─" * 40 + "\n", style="dim")
            parts.append(t_header)

            type_colors = {
                "observation": "cyan",
                "question": "blue",
                "connection": "magenta",
                "uncertainty": "yellow",
                "realization": "green",
            }

            for i, thought in enumerate(thoughts, 1):
                t_text = Text()
                t_type = thought.get("thought_type", "unknown")
                color = type_colors.get(t_type, "dim")

                # Timestamp
                ts = thought.get("timestamp", "")
                if ts:
                    try:
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        t_text.append(f"{dt.strftime('%H:%M:%S')} ", style="dim")
                    except:
                        pass

                t_text.append(f"[{t_type}] ", style=f"bold {color}")

                # Confidence
                conf = thought.get("confidence", 0)
                try:
                    conf_pct = int(float(conf) * 100)
                    t_text.append(f"({conf_pct}%) ", style="dim")
                except:
                    pass

                t_text.append("\n", style="")
                t_text.append(f"  {thought.get('content', '')}\n", style="")

                # Related concepts
                concepts = thought.get("related_concepts", [])
                if concepts:
                    t_text.append(f"  [{', '.join(concepts)}]\n", style="dim italic")

                parts.append(t_text)

        display.update(Group(*parts))

        # Auto-scroll to bottom if session is active (to show new thoughts)
        if session.get("status") == "active":
            try:
                scroll_container = self.query_one("#reflection-detail", VerticalScroll)
                scroll_container.scroll_end(animate=False)
            except Exception:
                pass

    async def _update_session_buttons(self, active: bool) -> None:
        """Update button visibility based on session state"""
        try:
            start_btn = self.query_one("#start-session-btn", Button)
            stop_btn = self.query_one("#stop-session-btn", Button)

            if active:
                start_btn.add_class("hidden")
                stop_btn.remove_class("hidden")
            else:
                start_btn.remove_class("hidden")
                stop_btn.add_class("hidden")
        except Exception:
            pass

    def watch_is_polling(self, polling: bool) -> None:
        """Start/stop polling when state changes"""
        if polling:
            self._start_polling()
        else:
            self._stop_polling()

    def _start_polling(self) -> None:
        """Start polling for session updates"""
        if self._poll_task and not self._poll_task.done():
            return

        async def poll_loop():
            while self.is_polling:
                try:
                    await self.load_stats()
                    await self.load_sessions()  # Refresh sessions list too
                    if self.selected_session:
                        await self.load_session_detail(self.selected_session)

                    # Check if session completed
                    if not self.stats.get("active_session"):
                        self.is_polling = False
                        await self._update_session_buttons(active=False)
                        debug_log("Reflection session completed", "success")
                        break

                    await asyncio.sleep(2)  # Poll every 2s for real-time feel
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    debug_log(f"Polling error: {e}", "error")
                    await asyncio.sleep(5)

        self._poll_task = asyncio.create_task(poll_loop())

    def _stop_polling(self) -> None:
        """Stop the polling task"""
        if self._poll_task:
            self._poll_task.cancel()
            self._poll_task = None

    @on(Button.Pressed, "#start-session-btn")
    async def on_start_session(self) -> None:
        """Start a new reflection session"""
        try:
            duration_input = self.query_one("#duration-input", Input)
            theme_input = self.query_one("#theme-input", Input)

            duration = int(duration_input.value) if duration_input.value else 15
            theme = theme_input.value.strip() if theme_input.value else None

            app = self.app
            if not hasattr(app, 'http_client'):
                return

            data = {"duration_minutes": duration}
            if theme:
                data["theme"] = theme

            response = await app.http_client.post("/solo-reflection/sessions", json=data)
            if response.status_code == 200:
                result = response.json()
                self.selected_session = result.get("session_id")
                self.is_polling = True
                await self._update_session_buttons(active=True)
                theme_input.value = ""
                await self.load_stats()
                await self.load_sessions()
                debug_log(f"Started reflection session: {self.selected_session}", "success")
        except Exception as e:
            debug_log(f"Failed to start session: {e}", "error")

    @on(Button.Pressed, "#stop-session-btn")
    async def on_stop_session(self) -> None:
        """Stop the active reflection session"""
        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            response = await app.http_client.post("/solo-reflection/stop")
            if response.status_code == 200:
                self.is_polling = False
                await self._update_session_buttons(active=False)
                await self.load_stats()
                await self.load_sessions()
                if self.selected_session:
                    await self.load_session_detail(self.selected_session)
                debug_log("Stopped reflection session", "info")
        except Exception as e:
            debug_log(f"Failed to stop session: {e}", "error")


class DaedalusConversationsPanel(Container):
    """Panel for viewing Daedalus-Cass conversation history (read-only)"""

    selected_conversation: reactive[Optional[str]] = reactive(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.conversations: List[Dict] = []
        self.system_users: List[Dict] = []
        self.current_messages: List[Dict] = []

    def compose(self) -> ComposeResult:
        with Horizontal(id="daedalus-convs-layout"):
            # Left panel - conversation list
            with Vertical(id="daedalus-convs-sidebar"):
                yield Label("Daedalus ↔ Cass", id="daedalus-convs-header")
                yield Static("System user conversations", id="daedalus-convs-subtitle", classes="dim")
                with VerticalScroll(id="daedalus-convs-scroll"):
                    yield Container(id="daedalus-convs-list")

            # Right panel - message viewer
            with VerticalScroll(id="daedalus-messages-scroll"):
                yield Static("Select a conversation to view messages", id="daedalus-messages-content")

    async def on_mount(self) -> None:
        """Load conversations on mount"""
        await self.load_conversations()

    async def load_conversations(self) -> None:
        """Load system user conversations from API"""
        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            response = await app.http_client.get("/admin/conversations/system")
            if response.status_code == 200:
                data = response.json()
                self.conversations = data.get("conversations", [])
                self.system_users = data.get("system_users", [])
                await self._display_conversations()
        except Exception as e:
            debug_log(f"Failed to load Daedalus conversations: {e}", "error")

    async def _display_conversations(self) -> None:
        """Display conversation list"""
        container = self.query_one("#daedalus-convs-list", Container)
        await container.remove_children()

        if not self.conversations:
            await container.mount(Static("No conversations yet", classes="empty-convs dim"))
            return

        for conv in self.conversations:
            conv_id = conv.get("id", "")
            title = conv.get("title", "Untitled")
            if len(title) > 35:
                title = title[:32] + "..."
            msg_count = conv.get("message_count", 0)
            updated = conv.get("updated_at", "")

            # Format date
            date_str = ""
            if updated:
                try:
                    dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    date_str = dt.strftime("%m/%d %H:%M")
                except:
                    date_str = updated[:10]

            label = f"{title}\n  {date_str} · {msg_count} msgs"
            btn = Button(label, id=f"dconv-{conv_id}", classes="daedalus-conv-btn")
            btn.conversation_id = conv_id
            await container.mount(btn)

    @on(Button.Pressed)
    async def on_conversation_button(self, event: Button.Pressed) -> None:
        """Handle conversation button clicks"""
        button_id = event.button.id or ""
        if button_id.startswith("dconv-"):
            conv_id = getattr(event.button, "conversation_id", None)
            if conv_id:
                self.selected_conversation = conv_id
                await self.load_messages(conv_id)

    async def load_messages(self, conversation_id: str) -> None:
        """Load and display messages for a conversation"""
        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            response = await app.http_client.get(f"/admin/conversations/{conversation_id}/messages")
            if response.status_code == 200:
                data = response.json()
                self.current_messages = data.get("messages", [])
                await self._display_messages()
        except Exception as e:
            debug_log(f"Failed to load messages: {e}", "error")

    async def _display_messages(self) -> None:
        """Display messages in the detail panel"""
        scroll = self.query_one("#daedalus-messages-scroll", VerticalScroll)
        content = self.query_one("#daedalus-messages-content", Static)

        if not self.current_messages:
            content.update("No messages in this conversation")
            return

        # Build rich text for all messages
        from rich.console import Group as RichGroup
        from rich.panel import Panel
        from rich.markdown import Markdown as RichMarkdown

        panels = []
        for msg in self.current_messages:
            role = msg.get("role", "unknown")
            msg_content = msg.get("content", "")
            timestamp = msg.get("timestamp", "")

            # Format timestamp
            time_str = ""
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    time_str = dt.strftime("%H:%M:%S")
                except:
                    time_str = timestamp[:8]

            # Role styling
            if role == "user":
                # User is Daedalus
                title = f"[bold cyan]Daedalus[/] [dim]{time_str}[/]"
                border_style = "cyan"
            else:
                # Assistant is Cass
                title = f"[bold magenta]Cass[/] [dim]{time_str}[/]"
                border_style = "magenta"

            # Truncate very long messages for display
            display_content = msg_content
            if len(display_content) > 2000:
                display_content = display_content[:2000] + "\n\n[dim]... (truncated)[/]"

            panel = Panel(
                RichMarkdown(display_content),
                title=title,
                title_align="left",
                border_style=border_style,
                padding=(0, 1)
            )
            panels.append(panel)

        # Update content with all panels
        content.update(RichGroup(*panels))
        scroll.scroll_end(animate=False)

    async def refresh_conversations(self) -> None:
        """Refresh the conversation list"""
        await self.load_conversations()
        if self.selected_conversation:
            await self.load_messages(self.selected_conversation)


class RecognitionPanel(Container):
    """Panel showing recognition-in-flow markers from the current conversation.

    Displays full content of:
    - Self-observations (what Cass notices about herself)
    - User observations (what Cass notices about users)
    - Marks (ambient recognition moments)
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.marks: List[Dict] = []
        self.self_observations: List[Dict] = []
        self.user_observations: List[Dict] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="recognition-content"):
            yield Label("Recognition-in-Flow", id="recognition-header")
            yield Static("Markers from current conversation", id="recognition-subtitle", classes="dim")
            yield Rule()

            with VerticalScroll(id="recognition-scroll"):
                # Marks section
                yield Label("Marks", classes="section-header")
                yield Static("No marks yet", id="marks-display")

                yield Rule()

                # Self-observations section
                yield Label("Self-Observations", classes="section-header")
                yield Static("No self-observations yet", id="self-obs-display")

                yield Rule()

                # User observations section
                yield Label("User Observations", classes="section-header")
                yield Static("No user observations yet", id="user-obs-display")

            # Actions
            with Horizontal(id="recognition-actions"):
                yield Button("Clear", id="clear-recognition-btn", variant="default")

    def add_marks(self, marks: List[Dict]) -> None:
        """Add marks from a response."""
        if marks:
            self.marks.extend(marks)
            self._update_marks_display()

    def add_self_observations(self, observations: List[Dict]) -> None:
        """Add self-observations from a response."""
        if observations:
            self.self_observations.extend(observations)
            self._update_self_obs_display()

    def add_user_observations(self, observations: List[Dict]) -> None:
        """Add user observations from a response."""
        if observations:
            self.user_observations.extend(observations)
            self._update_user_obs_display()

    def clear(self) -> None:
        """Clear all markers (e.g., when switching conversations)."""
        self.marks = []
        self.self_observations = []
        self.user_observations = []
        self._update_marks_display()
        self._update_self_obs_display()
        self._update_user_obs_display()

    def _update_marks_display(self) -> None:
        """Update the marks display."""
        try:
            display = self.query_one("#marks-display", Static)
            if not self.marks:
                display.update("No marks yet")
                return

            lines = []
            for i, mark in enumerate(reversed(self.marks), 1):
                cat = mark.get('category', 'unknown')
                desc = mark.get('description', '')
                lines.append(Text.assemble(
                    (f"[{cat}] ", "bold bright_red"),
                    (desc or "(no description)", ""),
                ))

            display.update(Group(*lines))
        except Exception as e:
            debug_log(f"Failed to update marks display: {e}", "error")

    def _update_self_obs_display(self) -> None:
        """Update the self-observations display."""
        try:
            display = self.query_one("#self-obs-display", Static)
            if not self.self_observations:
                display.update("No self-observations yet")
                return

            lines = []
            for obs in reversed(self.self_observations):
                cat = obs.get('category', 'pattern')
                content = obs.get('observation', '')
                conf = obs.get('confidence', 0.8)
                lines.append(Text.assemble(
                    (f"[{cat}] ", "bold yellow"),
                    (f"({conf:.0%}) ", "dim"),
                    (content, ""),
                ))

            display.update(Group(*lines))
        except Exception as e:
            debug_log(f"Failed to update self-obs display: {e}", "error")

    def _update_user_obs_display(self) -> None:
        """Update the user observations display."""
        try:
            display = self.query_one("#user-obs-display", Static)
            if not self.user_observations:
                display.update("No user observations yet")
                return

            lines = []
            for obs in reversed(self.user_observations):
                cat = obs.get('category', 'background')
                content = obs.get('observation', '')
                conf = obs.get('confidence', 0.7)
                lines.append(Text.assemble(
                    (f"[{cat}] ", "bold cyan"),
                    (f"({conf:.0%}) ", "dim"),
                    (content, ""),
                ))

            display.update(Group(*lines))
        except Exception as e:
            debug_log(f"Failed to update user-obs display: {e}", "error")

    @on(Button.Pressed, "#clear-recognition-btn")
    def on_clear_pressed(self, event: Button.Pressed) -> None:
        """Clear all markers."""
        event.stop()
        self.clear()
