"""
Cass Vessel - TUI Frontend
A terminal-based interface for interacting with Cass consciousness
Built with Textual framework
"""
import asyncio
import json
import re
import shlex
import base64
import io
import tempfile
import os
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict
import calendar

import httpx
import websockets
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Footer, Input, Static, ListItem, ListView, Label, Button, RichLog, TabbedContent, TabPane
from textual.reactive import reactive
from textual.screen import ModalScreen
from rich.text import Text
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.console import Group
from rich.panel import Panel

try:
    from textual_terminal import Terminal as BaseTerminal
    from textual import events
    TERMINAL_AVAILABLE = True
except ImportError:
    TERMINAL_AVAILABLE = False
    BaseTerminal = None

# Audio playback for TTS
try:
    import pygame
    pygame.mixer.init()
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
except Exception:
    # pygame.mixer.init() can fail on some systems
    AUDIO_AVAILABLE = False

import argparse
import sys
from config import HTTP_BASE_URL, WS_URL, HTTP_TIMEOUT, WS_RECONNECT_DELAY, DEFAULT_PROJECT


def _check_unicode_support() -> bool:
    """Check if the terminal supports unicode characters."""
    try:
        # Try to encode a unicode character
        "📋".encode(sys.stdout.encoding or 'utf-8')
        return True
    except (UnicodeEncodeError, LookupError):
        return False


# Unicode symbols with fallbacks
UNICODE_SUPPORTED = _check_unicode_support()
COPY_SYMBOL = "📋" if UNICODE_SUPPORTED else "Copy"
COPY_OK_SYMBOL = "✓" if UNICODE_SUPPORTED else "OK"


# Audio playback functions
_current_audio_file: Optional[str] = None

def play_audio_from_base64(audio_base64: str) -> bool:
    """
    Play audio from base64-encoded MP3 data.
    Returns True if playback started successfully.
    """
    global _current_audio_file

    if not AUDIO_AVAILABLE:
        return False

    try:
        # Decode base64 to bytes
        audio_bytes = base64.b64decode(audio_base64)

        # Create a temporary file for pygame to play
        fd, temp_path = tempfile.mkstemp(suffix='.mp3')
        with os.fdopen(fd, 'wb') as f:
            f.write(audio_bytes)

        # Clean up previous temp file if exists
        if _current_audio_file and os.path.exists(_current_audio_file):
            try:
                os.unlink(_current_audio_file)
            except Exception:
                pass

        _current_audio_file = temp_path

        # Play the audio
        pygame.mixer.music.load(temp_path)
        pygame.mixer.music.play()

        return True

    except Exception as e:
        print(f"Audio playback failed: {e}")
        return False


def stop_audio():
    """Stop any currently playing audio."""
    if AUDIO_AVAILABLE:
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass


def is_audio_playing() -> bool:
    """Check if audio is currently playing."""
    if AUDIO_AVAILABLE:
        try:
            return pygame.mixer.music.get_busy()
        except Exception:
            pass
    return False


# Custom Terminal with paste support
if TERMINAL_AVAILABLE:
    class Terminal(BaseTerminal):
        """Terminal widget with clipboard paste support."""

        async def on_paste(self, event: events.Paste) -> None:
            """Handle paste events by sending pasted text to the terminal."""
            if self.emulator is None:
                return

            event.stop()
            if event.text:
                await self.send_queue.put(["stdin", event.text])
else:
    Terminal = None


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


class ProjectItem(ListItem):
    """A project in the sidebar list"""

    def __init__(self, project_id: str, project_name: str, file_count: int, **kwargs):
        super().__init__(**kwargs)
        self.project_id = project_id
        self.project_name = project_name
        self.file_count = file_count

    def compose(self) -> ComposeResult:
        text = Text()
        text.append("📁 ", style="dim")
        text.append(self.project_name, style="bold")
        text.append(f" ({self.file_count} files)", style="dim")
        yield Static(text)


class ConversationItem(ListItem):
    """A conversation in the sidebar list"""

    def __init__(self, conv_id: str, title: str, message_count: int, project_id: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.conv_id = conv_id
        self.title = title
        self.message_count = message_count
        self.project_id = project_id

    def compose(self) -> ComposeResult:
        text = Text()
        text.append(self.title, style="bold")
        text.append(f"\n{self.message_count} messages", style="dim")
        yield Static(text)


class Sidebar(Vertical):
    """Sidebar showing projects and conversations"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.projects = []
        self.conversations = []
        self.selected_project_id: Optional[str] = None  # None = show all/unassigned

    def compose(self) -> ComposeResult:
        # Projects section
        yield Label("Projects", id="projects-header")
        yield Button("+ New Project", id="new-project-btn", variant="primary")
        yield ListView(id="project-list")

        # Conversations section
        yield Label("Conversations", id="conversations-header")
        yield Button("+ New Chat", id="new-conversation-btn", variant="success")
        yield ListView(id="conversation-list")

    async def load_projects(self, http_client: httpx.AsyncClient):
        """Load projects from backend"""
        try:
            debug_log("Fetching projects from backend...")
            response = await http_client.get("/projects")
            debug_log(f"Projects response status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                self.projects = data.get("projects", [])
                debug_log(f"Loaded {len(self.projects)} projects", "success")
                await self.update_project_list()
            else:
                debug_log(f"Projects request failed: {response.text}", "error")
        except Exception as e:
            debug_log(f"Error loading projects: {e}", "error")

    async def update_project_list(self):
        """Update the project list display"""
        list_view = self.query_one("#project-list", ListView)
        await list_view.clear()

        # Add "All Conversations" option
        all_item = ListItem(Static(Text("📋 All Conversations", style="italic")))
        all_item.project_id = None
        await list_view.append(all_item)

        debug_log(f"Adding {len(self.projects)} projects to list")

        for proj in self.projects:
            debug_log(f"  → {proj['name']}", "debug")
            item = ProjectItem(
                proj["id"],
                proj["name"],
                proj.get("file_count", 0)
            )
            await list_view.append(item)

        debug_log(f"Project list updated with {len(self.projects) + 1} items", "success")

    async def load_conversations(self, http_client: httpx.AsyncClient):
        """Load conversations from backend"""
        try:
            if self.selected_project_id:
                # Load project-specific conversations
                response = await http_client.get(f"/projects/{self.selected_project_id}/conversations")
            else:
                # Load all conversations
                response = await http_client.get("/conversations")

            if response.status_code == 200:
                data = response.json()
                self.conversations = data.get("conversations", [])
                await self.update_conversation_list()
        except Exception:
            pass

    async def update_conversation_list(self):
        """Update the conversation list display"""
        list_view = self.query_one("#conversation-list", ListView)
        await list_view.clear()

        for conv in self.conversations:
            item = ConversationItem(
                conv["id"],
                conv["title"],
                conv.get("message_count", 0),
                conv.get("project_id")
            )
            await list_view.append(item)

    async def select_project(self, project_id: Optional[str], http_client: httpx.AsyncClient):
        """Select a project and reload conversations"""
        self.selected_project_id = project_id
        await self.load_conversations(http_client)


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


# Global debug logger instance - will be set by the app
_debug_panel: Optional[DebugPanel] = None

def debug_log(message: str, level: str = "info"):
    """Log to debug panel if available, else print"""
    if _debug_panel:
        _debug_panel.log(message, level)
    print(f"[{level.upper()}] {message}")


class StatusBar(Static):
    """Status bar showing connection state and system info"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.connected = False
        self.sdk_mode = False
        self.memory_count = 0
        self.project_name: Optional[str] = None

    def on_mount(self) -> None:
        debug_log("StatusBar mounted, calling update_display", "debug")
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

    def update_display(self):
        status = Text()

        # Connection status
        if self.connected:
            status.append("● ", style="bold green")
            status.append("Connected ", style="green")
        else:
            status.append("● ", style="bold red")
            status.append("Disconnected ", style="red")

        status.append("| ")

        # SDK mode
        if self.sdk_mode:
            status.append("Agent SDK ", style="bold blue")
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


class CodeBlockWidget(Vertical):
    """A code block with syntax highlighting and copy button"""

    def __init__(self, code: str, language: str = "", **kwargs):
        super().__init__(**kwargs)
        self.code = code
        self.language = language or "text"

    def compose(self) -> ComposeResult:
        # Header with language label and copy button
        with Horizontal(classes="code-header"):
            yield Label(self.language, classes="code-language")
            yield Button(COPY_SYMBOL, classes="code-copy-btn", variant="default")

        # Syntax highlighted code
        syntax = Syntax(
            self.code,
            self.language,
            theme="monokai",
            line_numbers=True,
            word_wrap=False
        )
        yield Static(syntax, classes="code-content")

    @on(Button.Pressed, ".code-copy-btn")
    def on_copy_pressed(self, event: Button.Pressed) -> None:
        """Copy code to clipboard"""
        event.stop()
        import pyperclip
        try:
            pyperclip.copy(self.code)
            event.button.label = COPY_OK_SYMBOL
            self.set_timer(1.0, lambda: setattr(event.button, 'label', COPY_SYMBOL))
        except Exception as e:
            debug_log(f"Copy failed: {e}", "error")


class ChatMessage(Vertical):
    """A single chat message with markdown rendering and copy button"""

    # Pattern to match <memory:xyz> tags
    MEMORY_TAG_PATTERN = re.compile(r'<memory:(\w+)>')
    # Pattern to match code blocks: ```language\ncode\n```
    CODE_BLOCK_PATTERN = re.compile(r'```(\w*)\n(.*?)```', re.DOTALL)

    def __init__(self, role: str, content: str, animations: Optional[List[Dict]] = None, audio_data: Optional[str] = None, input_tokens: int = 0, output_tokens: int = 0, **kwargs):
        super().__init__(**kwargs)
        self.role = role
        # Extract memory tags and clean content
        self.memory_tags = self.MEMORY_TAG_PATTERN.findall(content)
        self.content = self.MEMORY_TAG_PATTERN.sub('', content).strip()
        self.animations = animations or []
        self.audio_data = audio_data  # Base64 encoded audio for replay
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        # Parse content into segments (text and code blocks)
        self.segments = self._parse_content(self.content)

    def _parse_content(self, content: str) -> List[Dict]:
        """Parse content into text and code block segments"""
        segments = []
        last_end = 0

        for match in self.CODE_BLOCK_PATTERN.finditer(content):
            # Add text before code block
            if match.start() > last_end:
                text_segment = content[last_end:match.start()].strip()
                if text_segment:
                    segments.append({"type": "text", "content": text_segment})

            # Add code block
            language = match.group(1) or "text"
            code = match.group(2).rstrip()
            segments.append({"type": "code", "language": language, "content": code})
            last_end = match.end()

        # Add remaining text after last code block
        if last_end < len(content):
            text_segment = content[last_end:].strip()
            if text_segment:
                segments.append({"type": "text", "content": text_segment})

        # If no segments, treat entire content as text
        if not segments and content:
            segments.append({"type": "text", "content": content})

        return segments

    def compose(self) -> ComposeResult:
        # Format timestamp
        time_str = datetime.now().strftime('%H:%M:%S')

        # Role-specific styling
        if self.role == "user":
            role_style = "bold cyan"
            prefix = "You"
        elif self.role in ("cass", "assistant"):
            role_style = "bold magenta"
            prefix = "Cass"
        else:
            role_style = "bold yellow"
            prefix = self.role.title()

        # Message header with timestamp, role, and buttons
        with Horizontal(classes="message-header"):
            header_text = Text()
            header_text.append(f"[{time_str}] ", style="dim")
            header_text.append(f"{prefix}", style=role_style)
            # Show token usage for Cass messages
            if self.role in ("cass", "assistant") and (self.input_tokens or self.output_tokens):
                header_text.append(f" [{self.input_tokens}→{self.output_tokens}]", style="dim")
            yield Static(header_text, classes="message-role")
            # Add replay button for Cass messages (always visible - fetches on demand if needed)
            if self.role in ("cass", "assistant") and AUDIO_AVAILABLE:
                btn = Button("🔊", classes="replay-btn", variant="default", id=f"replay-{id(self)}")
                yield btn
            yield Button(COPY_SYMBOL, classes="copy-btn", variant="default", id=f"copy-{id(self)}")

        # Render content segments
        for segment in self.segments:
            if segment["type"] == "text":
                # Render as markdown
                yield Static(Markdown(segment["content"]), classes="message-text")
            elif segment["type"] == "code":
                # Render as syntax-highlighted code block
                yield CodeBlockWidget(
                    segment["content"],
                    segment["language"],
                    classes="message-code-block"
                )

        # Add gesture/emote/memory indicators
        indicators = Text()
        has_indicators = False

        if self.animations:
            gestures = []
            emotes = []
            for anim in self.animations:
                if anim.get('type') == 'gesture':
                    gestures.append(anim.get('name', ''))
                elif anim.get('type') == 'emote':
                    emotes.append(anim.get('name', ''))

            if gestures:
                indicators.append(f"[gestures: {', '.join(gestures)}] ", style="italic blue")
                has_indicators = True
            if emotes:
                indicators.append(f"[emotes: {', '.join(emotes)}] ", style="italic green")
                has_indicators = True

        if self.memory_tags:
            indicators.append(f"[memory: {', '.join(self.memory_tags)}]", style="italic magenta")
            has_indicators = True

        if has_indicators:
            yield Static(indicators, classes="message-indicators")

    @on(Button.Pressed, ".copy-btn")
    def on_copy_pressed(self, event: Button.Pressed) -> None:
        """Copy full message content to clipboard"""
        event.stop()
        import pyperclip
        try:
            pyperclip.copy(self.content)
            event.button.label = COPY_OK_SYMBOL
            self.set_timer(1.0, lambda: setattr(event.button, 'label', COPY_SYMBOL))
        except Exception as e:
            debug_log(f"Copy failed: {e}", "error")

    @on(Button.Pressed, ".replay-btn")
    async def on_replay_pressed(self, event: Button.Pressed) -> None:
        """Replay the audio for this message, fetching on-demand if needed"""
        event.stop()

        # If we have cached audio, play it directly
        if self.audio_data:
            if play_audio_from_base64(self.audio_data):
                event.button.label = "▶"
                self.set_timer(1.0, lambda: setattr(event.button, 'label', '🔊'))
                debug_log("Replaying cached audio", "info")
            else:
                debug_log("Audio replay failed", "error")
            return

        # No cached audio - fetch from API
        event.button.label = "⏳"
        try:
            # Get http_client from app
            app = self.app
            if hasattr(app, 'http_client') and app.http_client:
                response = await app.http_client.post(
                    "/tts/generate",
                    json={"text": self.content}
                )
                if response.status_code == 200:
                    data = response.json()
                    audio_data = data.get("audio")
                    if audio_data:
                        # Cache for future replays
                        self.audio_data = audio_data
                        if play_audio_from_base64(audio_data):
                            event.button.label = "▶"
                            self.set_timer(1.0, lambda: setattr(event.button, 'label', '🔊'))
                            debug_log("Playing fetched audio", "info")
                            return

                debug_log(f"TTS API error: {response.status_code}", "error")
                event.button.label = "❌"
                self.set_timer(2.0, lambda: setattr(event.button, 'label', '🔊'))
            else:
                debug_log("No HTTP client available", "error")
                event.button.label = "❌"
                self.set_timer(2.0, lambda: setattr(event.button, 'label', '🔊'))
        except Exception as e:
            debug_log(f"TTS fetch failed: {e}", "error")
            event.button.label = "❌"
            self.set_timer(2.0, lambda: setattr(event.button, 'label', '🔊'))


class ChatContainer(VerticalScroll):
    """Scrollable container for messages"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.can_focus = True

    async def add_message(self, role: str, content: str, animations: Optional[List[Dict]] = None, audio_data: Optional[str] = None, input_tokens: int = 0, output_tokens: int = 0):
        """Add a new message to the chat"""
        message = ChatMessage(role, content, animations, audio_data=audio_data, input_tokens=input_tokens, output_tokens=output_tokens, classes="chat-message")
        await self.mount(message)
        message.scroll_visible()

    async def remove_children(self):
        """Clear all messages"""
        for child in list(self.children):
            await child.remove()


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
                await self.display_summaries(data.get("summaries", []))
        except Exception as e:
            await self.display_error(f"Failed to load summaries: {str(e)}")

    async def display_summaries(self, summaries: List[Dict]):
        """Display summary chunks"""
        # Clear existing content
        await self.remove_children()

        if not summaries:
            text = Text("No summaries yet", style="dim italic")
            await self.mount(Static(text))
            return

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
            text.append(f"Summary #{summary_num}\n", style="bold cyan")
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


class DocumentItem(ListItem):
    """List item for a project document"""

    def __init__(self, doc_id: str, title: str, preview: str, **kwargs):
        super().__init__(**kwargs)
        self.doc_id = doc_id
        self.doc_title = title
        self.preview = preview

    def compose(self) -> ComposeResult:
        text = Text()
        text.append(f"📄 {self.doc_title}\n", style="bold")
        text.append(self.preview[:60] + "..." if len(self.preview) > 60 else self.preview, style="dim")
        yield Static(text)


class ProjectPanel(Container):
    """Panel showing project documents with list and content viewer"""

    selected_document_id: reactive[Optional[str]] = reactive(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.documents: List[Dict] = []
        self._refresh_task: Optional[asyncio.Task] = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="project-panel-content"):
            with Vertical(id="doc-list-container"):
                yield Label("Documents", id="doc-list-header")
                yield ListView(id="doc-list")
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


class CalendarDay(Button):
    """A single day button in the calendar"""

    def __init__(self, day: int, is_current_month: bool, has_journal: bool, is_today: bool, date_str: str, **kwargs):
        self.day = day
        self.is_current_month = is_current_month
        self.has_journal = has_journal
        self.is_today = is_today
        self.date_str = date_str  # YYYY-MM-DD format

        # Build label
        label = str(day) if day > 0 else ""
        super().__init__(label, **kwargs)

    def on_mount(self) -> None:
        # Apply styling classes
        if not self.is_current_month:
            self.add_class("other-month")
        if self.has_journal:
            self.add_class("has-journal")
        if self.is_today:
            self.add_class("is-today")
        if self.day <= 0:
            self.add_class("empty-day")


class CalendarWidget(Container):
    """A month calendar widget for selecting days"""

    selected_date: reactive[Optional[str]] = reactive(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_year = datetime.now().year
        self.current_month = datetime.now().month
        self.journal_dates: set = set()  # Dates that have journal entries

    def compose(self) -> ComposeResult:
        # Month navigation header
        with Horizontal(id="calendar-nav"):
            yield Button("◀", id="prev-month", classes="nav-btn")
            yield Label(self._get_month_label(), id="month-label")
            yield Button("▶", id="next-month", classes="nav-btn")

        # Weekday headers
        with Horizontal(id="weekday-headers"):
            for day in ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"]:
                yield Label(day, classes="weekday-header")

        # Calendar grid
        yield Container(id="calendar-grid")

    def _get_month_label(self) -> str:
        """Get formatted month/year label"""
        return f"{calendar.month_name[self.current_month]} {self.current_year}"

    async def on_mount(self) -> None:
        await self._render_calendar()

    async def _render_calendar(self) -> None:
        """Render the calendar grid for the current month"""
        grid = self.query_one("#calendar-grid", Container)
        await grid.remove_children()

        # Update month label
        label = self.query_one("#month-label", Label)
        label.update(self._get_month_label())

        # Get calendar data
        cal = calendar.Calendar(firstweekday=6)  # Start on Sunday
        today = date.today()

        # Build weeks
        for week in cal.monthdatescalendar(self.current_year, self.current_month):
            week_container = Horizontal(classes="calendar-week")
            await grid.mount(week_container)

            for day_date in week:
                is_current_month = day_date.month == self.current_month
                date_str = day_date.strftime("%Y-%m-%d")
                has_journal = date_str in self.journal_dates
                is_today = day_date == today

                day_btn = CalendarDay(
                    day=day_date.day if is_current_month else 0,
                    is_current_month=is_current_month,
                    has_journal=has_journal,
                    is_today=is_today,
                    date_str=date_str,
                    classes="calendar-day"
                )
                await week_container.mount(day_btn)

    @on(Button.Pressed, "#prev-month")
    async def on_prev_month(self) -> None:
        """Go to previous month"""
        if self.current_month == 1:
            self.current_month = 12
            self.current_year -= 1
        else:
            self.current_month -= 1
        await self._render_calendar()

    @on(Button.Pressed, "#next-month")
    async def on_next_month(self) -> None:
        """Go to next month"""
        if self.current_month == 12:
            self.current_month = 1
            self.current_year += 1
        else:
            self.current_month += 1
        await self._render_calendar()

    @on(Button.Pressed, ".calendar-day")
    async def on_day_pressed(self, event: Button.Pressed) -> None:
        """Handle day selection"""
        if isinstance(event.button, CalendarDay):
            if event.button.is_current_month and event.button.day > 0:
                self.selected_date = event.button.date_str

    async def set_journal_dates(self, dates: List[str]) -> None:
        """Update which dates have journal entries"""
        self.journal_dates = set(dates)
        await self._render_calendar()


class GrowthPanel(Container):
    """Panel showing Cass's growth data - calendar and journal entries"""

    selected_date: reactive[Optional[str]] = reactive(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.journals: Dict[str, Dict] = {}  # Cache of loaded journals

    def compose(self) -> ComposeResult:
        with Vertical(id="growth-content"):
            # Calendar section
            with Container(id="calendar-section"):
                yield Label("Journal Calendar", id="calendar-header")
                yield CalendarWidget(id="calendar-widget")

            # Journal viewer section
            with VerticalScroll(id="journal-viewer"):
                yield Static("Select a date to view journal entry", id="journal-content", classes="journal-placeholder")

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
        if new_date:
            self.call_later(self._load_journal_entry, new_date)

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

        # Build display
        header = Text()
        header.append(f"📓 Journal - {date_str}\n", style="bold cyan")

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
        if isinstance(event.button, CalendarDay):
            if event.button.is_current_month and event.button.day > 0:
                self.selected_date = event.button.date_str


class CassVesselTUI(App):
    """Textual TUI for Cass Vessel"""

    CSS = """
    Screen {
        background: $surface;
    }

    #status {
        dock: top;
        height: 1;
        background: $surface-darken-1;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }


    #debug-panel {
        height: 8;
        background: $surface-darken-1;
        border-bottom: solid $warning;
        display: none;
    }

    #debug-panel.visible {
        display: block;
    }

    #main-container {
        height: 1fr;
    }

    #sidebar {
        width: 32;
        background: $panel;
        border-right: solid $primary;
        padding: 1;
    }

    #projects-header, #conversations-header {
        text-align: center;
        text-style: bold;
        background: $primary;
        color: $text;
        padding: 0 1;
        margin-bottom: 1;
    }

    #conversations-header {
        margin-top: 1;
    }

    #new-project-btn, #new-conversation-btn {
        width: 100%;
        margin-bottom: 1;
    }

    #project-list {
        height: auto;
        min-height: 5;
        max-height: 12;
        border: none;
    }

    #project-list > ListItem {
        padding: 0 1;
    }

    #conversation-list {
        height: 1fr;
        border: none;
    }

    #conversation-list > ListItem {
        padding: 1;
        margin-bottom: 1;
    }

    #conversation-list > ListItem:hover {
        background: $primary 30%;
    }

    #conversation-list > ListItem.-selected {
        background: $primary;
    }

    #chat-area {
        width: 1fr;
    }

    #content-columns {
        height: 1fr;
        margin: 1 0;
    }

    #chat-column {
        width: 2fr;
    }

    #right-panel {
        width: 1fr;
    }

    #chat-container {
        height: 1fr;
        border: solid $primary;
        margin: 0 1 0 2;
        padding: 1 2;
        background: $surface;
    }

    #right-tabs {
        height: 1fr;
        margin: 0 2 0 1;
    }

    #summary-panel {
        height: 1fr;
        padding: 1;
        background: $surface;
    }

    /* Project panel styling */
    #project-panel {
        height: 1fr;
        background: $surface;
    }

    #project-panel-content {
        height: 1fr;
        width: 100%;
    }

    #doc-list-container {
        width: 1fr;
        max-width: 35;
        height: 1fr;
        border-right: solid $surface-darken-1;
    }

    #doc-list-header {
        height: 1;
        padding: 0 1;
        background: $surface-darken-1;
        text-style: bold;
        color: $primary;
    }

    #doc-list {
        height: 1fr;
        padding: 0;
    }

    #doc-list > ListItem {
        padding: 1;
        height: auto;
    }

    #doc-list > ListItem:hover {
        background: $surface-lighten-1;
    }

    #doc-list > ListItem.-selected {
        background: $primary-darken-2;
    }

    #doc-viewer {
        width: 2fr;
        height: 1fr;
        padding: 1;
    }

    #doc-content {
        width: 100%;
        height: auto;
    }

    #doc-content.doc-placeholder {
        color: $text-muted;
        text-style: italic;
    }

    #terminal, #terminal-placeholder {
        height: 1fr;
        background: $surface;
    }

    #terminal-placeholder {
        padding: 2;
        color: $text-muted;
    }

    .chat-message {
        height: auto;
        width: 100%;
        margin-bottom: 1;
        padding: 0 0 1 0;
        border-bottom: solid $surface-darken-1;
    }

    .chat-message .message-header {
        height: auto;
        width: 100%;
        margin-bottom: 0;
    }

    .chat-message .message-role {
        width: 1fr;
    }

    .chat-message .message-header Button {
        width: auto;
        min-width: 4;
        height: 1;
        margin: 0;
        padding: 0 1;
        border: none;
        background: $primary-darken-2;
    }

    .chat-message .message-header .replay-btn {
        background: $success-darken-2;
        margin-right: 1;
    }

    .chat-message .message-header .replay-btn:hover {
        background: $success;
    }

    .chat-message .message-text {
        width: 100%;
        padding: 0 0 0 2;
    }

    .chat-message .message-indicators {
        padding: 0 0 0 2;
        margin-top: 1;
    }

    /* Code block styling */
    .message-code-block {
        height: auto;
        margin: 1 0 1 2;
        background: $surface-darken-2;
        border: solid $primary-darken-2;
    }

    .message-code-block .code-header {
        height: 1;
        background: $primary-darken-3;
        padding: 0 1;
    }

    .message-code-block .code-language {
        width: 1fr;
        color: $text-muted;
        text-style: italic;
    }

    .message-code-block .code-copy-btn {
        width: auto;
        min-width: 4;
        height: 1;
        margin: 0;
        padding: 0 1;
        border: none;
        background: $primary-darken-1;
    }

    .message-code-block .code-content {
        height: auto;
        padding: 1;
        overflow-x: auto;
    }

    #thinking-indicator {
        height: auto;
        padding: 0 1;
        margin: 0 1 0 2;
        color: $warning;
        text-style: italic;
        display: none;
    }

    #thinking-indicator.visible {
        display: block;
    }

    #input-container {
        height: 3;
        background: $panel;
        padding: 0 1;
        margin: 0 1 0 2;
    }

    #input {
        width: 1fr;
    }

    /* Rename dialog modal */
    RenameConversationScreen {
        align: center middle;
    }

    #rename-dialog {
        width: 60;
        height: auto;
        background: $panel;
        border: thick $primary;
        padding: 1 2;
    }

    #rename-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    #rename-input {
        width: 100%;
        margin-bottom: 1;
    }

    #rename-buttons {
        width: 100%;
        height: auto;
        align: center middle;
    }

    #rename-buttons Button {
        margin: 0 1;
    }

    /* New project dialog modal */
    NewProjectScreen {
        align: center middle;
    }

    #project-dialog {
        width: 60;
        height: auto;
        background: $panel;
        border: thick $primary;
        padding: 1 2;
    }

    #project-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    .field-label {
        margin-top: 1;
        color: $text-muted;
    }

    #project-name-input, #project-path-input {
        width: 100%;
        margin-bottom: 1;
    }

    #project-buttons {
        width: 100%;
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    #project-buttons Button {
        margin: 0 1;
    }

    /* Growth panel styling */
    #growth-panel {
        height: 1fr;
        background: $surface;
    }

    #growth-content {
        height: 1fr;
        width: 100%;
    }

    #calendar-section {
        height: auto;
        max-height: 16;
        padding: 1;
        border-bottom: solid $surface-darken-1;
    }

    #calendar-header {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    #calendar-widget {
        width: 100%;
        height: auto;
    }

    #calendar-nav {
        height: 1;
        width: 100%;
        align: center middle;
        margin-bottom: 1;
    }

    #calendar-nav .nav-btn {
        width: 3;
        min-width: 3;
        height: 1;
        border: none;
        background: $primary-darken-2;
    }

    #month-label {
        width: 1fr;
        text-align: center;
        text-style: bold;
        color: $text;
    }

    #weekday-headers {
        height: 1;
        width: 100%;
    }

    .weekday-header {
        width: 1fr;
        text-align: center;
        color: $text-muted;
        text-style: bold;
    }

    #calendar-grid {
        width: 100%;
        height: auto;
    }

    .calendar-week {
        height: 2;
        width: 100%;
    }

    .calendar-day {
        width: 1fr;
        height: 2;
        min-width: 3;
        border: none;
        background: $surface;
        color: $text;
    }

    .calendar-day:hover {
        background: $primary-darken-2;
    }

    .calendar-day.other-month {
        color: $text-muted;
        background: $surface-darken-1;
    }

    .calendar-day.empty-day {
        background: $surface-darken-1;
    }

    .calendar-day.has-journal {
        background: $success-darken-2;
        color: $text;
        text-style: bold;
    }

    .calendar-day.has-journal:hover {
        background: $success;
    }

    .calendar-day.is-today {
        border: solid $warning;
    }

    #journal-viewer {
        height: 1fr;
        padding: 1;
    }

    #journal-content {
        width: 100%;
        height: auto;
    }

    #journal-content.journal-placeholder {
        color: $text-muted;
        text-style: italic;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("ctrl+n", "new_conversation", "New Chat", show=True),
        Binding("ctrl+p", "new_project", "New Project", show=True),
        Binding("ctrl+r", "rename_conversation", "Rename", show=True),
        Binding("ctrl+l", "clear_chat", "Clear", show=True),
        Binding("ctrl+t", "toggle_terminal", "Terminal", show=True),
        Binding("ctrl+g", "toggle_growth", "Growth", show=True),
        Binding("ctrl+m", "toggle_tts", "Mute TTS", show=True),
        Binding("f12", "toggle_debug", "Debug", show=True),
        Binding("ctrl+s", "show_status", "Status", show=True),
    ]

    current_conversation_id: reactive[Optional[str]] = reactive(None)
    current_conversation_title: reactive[Optional[str]] = reactive(None)
    current_project_id: reactive[Optional[str]] = reactive(None)

    def __init__(self, initial_project: Optional[str] = None):
        super().__init__()
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.ws_task: Optional[asyncio.Task] = None
        self.http_client = httpx.AsyncClient(base_url=HTTP_BASE_URL, timeout=HTTP_TIMEOUT)
        self.initial_project = initial_project  # Project to select on startup
        self.tts_enabled = AUDIO_AVAILABLE  # Enable TTS by default if audio is available

    def compose(self) -> ComposeResult:
        """Create the UI layout"""
        yield StatusBar(id="status")
        yield DebugPanel(id="debug-panel")

        with Horizontal(id="main-container"):
            yield Sidebar(id="sidebar")

            with Vertical(id="chat-area"):
                with Horizontal(id="content-columns"):
                    with Vertical(id="chat-column"):
                        yield ChatContainer(id="chat-container")
                        yield Label("", id="thinking-indicator")
                        with Container(id="input-container"):
                            yield Input(placeholder="Message Cass...", id="input")

                    with Vertical(id="right-panel"):
                        with TabbedContent(id="right-tabs"):
                            with TabPane("Project", id="project-tab"):
                                yield ProjectPanel(id="project-panel")
                            with TabPane("Growth", id="growth-tab"):
                                yield GrowthPanel(id="growth-panel")
                            with TabPane("Summary", id="summary-tab"):
                                yield SummaryPanel(id="summary-panel")
                            with TabPane("Terminal", id="terminal-tab"):
                                if TERMINAL_AVAILABLE:
                                    # Start interactive bash - user can launch claude manually
                                    # (bash -i sources .bashrc which sets up nvm/PATH properly)
                                    yield Terminal(command="bash -i", id="terminal", default_colors="textual")
                                else:
                                    yield Static("Terminal not available.\nInstall: pip install textual-terminal", id="terminal-placeholder")

        yield Footer()

    async def on_mount(self) -> None:
        """Initialize the app"""
        # Set up global debug panel
        global _debug_panel
        _debug_panel = self.query_one("#debug-panel", DebugPanel)
        debug_log("Debug panel initialized", "success")

        # Add welcome message
        chat = self.query_one("#chat-container", ChatContainer)
        await chat.add_message(
            "system",
            "Cass Vessel TUI v0.2.0\nConnecting to backend...",
            None
        )

        # Set focus to input
        self.query_one("#input", Input).focus()

        # Load projects and conversations
        sidebar = self.query_one("#sidebar", Sidebar)
        await sidebar.load_projects(self.http_client)
        await sidebar.load_conversations(self.http_client)

        # Connect to backend
        self.connect_websocket()

        # Start the terminal if available
        if TERMINAL_AVAILABLE:
            try:
                terminal = self.query_one("#terminal", Terminal)
                terminal.start()
                debug_log("Terminal started", "success")
            except Exception as e:
                debug_log(f"Failed to start terminal: {e}", "error")

        # Handle initial project if specified via CLI or env
        if self.initial_project:
            # Defer to allow projects to load first
            self.call_later(self._select_initial_project)

    async def _select_initial_project(self) -> None:
        """Select the initial project specified via CLI or env"""
        if self.initial_project:
            await self.set_project_by_name(self.initial_project)

    def action_toggle_debug(self) -> None:
        """Toggle the debug panel visibility"""
        debug_panel = self.query_one("#debug-panel", DebugPanel)
        debug_panel.toggle_class("visible")
        if debug_panel.has_class("visible"):
            debug_log("Debug panel shown", "info")

    def action_toggle_terminal(self) -> None:
        """Toggle to Terminal tab"""
        tabs = self.query_one("#right-tabs", TabbedContent)
        tabs.active = "terminal-tab"
        # Focus the terminal if available
        if TERMINAL_AVAILABLE:
            try:
                terminal = self.query_one("#terminal", Terminal)
                terminal.focus()
            except Exception:
                pass

    def action_toggle_growth(self) -> None:
        """Toggle to Growth tab"""
        tabs = self.query_one("#right-tabs", TabbedContent)
        tabs.active = "growth-tab"

    async def action_toggle_tts(self) -> None:
        """Toggle TTS audio on/off"""
        if not AUDIO_AVAILABLE:
            chat = self.query_one("#chat-container", ChatContainer)
            await chat.add_message("system", "Audio playback not available (pygame not installed)", None)
            return

        self.tts_enabled = not self.tts_enabled

        # Stop any currently playing audio when muting
        if not self.tts_enabled:
            stop_audio()

        # Notify user
        chat = self.query_one("#chat-container", ChatContainer)
        status = "enabled" if self.tts_enabled else "muted"
        await chat.add_message("system", f"🔊 TTS audio {status}", None)
        debug_log(f"TTS {status}", "info")

    @work(exclusive=True)
    async def connect_websocket(self):
        """Connect to the backend WebSocket"""
        chat = self.query_one("#chat-container", ChatContainer)
        status_bar = self.query_one("#status", StatusBar)
        reconnect_delay = WS_RECONNECT_DELAY

        while True:
            try:
                debug_log(f"Connecting to WebSocket at {WS_URL}...")
                # Increase max_size to handle TTS audio (default is 1MB, we need more for long responses)
                self.ws = await websockets.connect(WS_URL, max_size=10 * 1024 * 1024)  # 10MB

                # Initial connection message
                data = await self.ws.recv()
                msg = json.loads(data)

                if msg.get("type") == "connected":
                    await chat.add_message(
                        "system",
                        f"✓ Connected to Cass Vessel\nSDK Mode: {msg.get('sdk_mode', False)}",
                        None
                    )
                    status_bar.update_status(
                        connected=True,
                        sdk_mode=msg.get('sdk_mode', False)
                    )
                    debug_log("WebSocket connected", "success")

                    # Get status info
                    await self.fetch_status()

                    # Reset reconnect delay on successful connection
                    reconnect_delay = WS_RECONNECT_DELAY

                # Listen for messages
                async for message in self.ws:
                    await self.handle_ws_message(message)

                # If we get here, connection closed cleanly
                debug_log("WebSocket connection closed", "warning")

            except websockets.exceptions.ConnectionClosed as e:
                debug_log(f"WebSocket connection closed: {e}", "warning")
            except Exception as e:
                debug_log(f"WebSocket error: {e}", "error")

            # Connection lost - update UI and retry
            status_bar.update_status(connected=False)
            await chat.add_message(
                "system",
                f"⚠ Connection lost. Reconnecting in {reconnect_delay}s...",
                None
            )

            # Wait before reconnecting
            await asyncio.sleep(reconnect_delay)

            # Exponential backoff (max 60 seconds)
            reconnect_delay = min(reconnect_delay * 2, 60)

    async def handle_ws_message(self, message: str):
        """Handle incoming WebSocket message"""
        chat = self.query_one("#chat-container", ChatContainer)
        status_bar = self.query_one("#status", StatusBar)

        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "thinking":
                # Show thinking indicator in chat area
                status_text = data.get("status", "Thinking...")
                memories = data.get("memories", {})

                # Build status with memory info if available
                if memories.get("has_context"):
                    summaries = memories.get("summaries_count", 0)
                    details = memories.get("details_count", 0)
                    project_docs = memories.get("project_docs_count", 0)
                    parts = []
                    if summaries:
                        parts.append(f"{summaries} summaries")
                    if details:
                        parts.append(f"{details} memories")
                    if project_docs:
                        parts.append(f"{project_docs} project docs")
                    context_info = ", ".join(parts) if parts else "context"
                    status_text = f"⏳ Cass is {status_text.lower()} ({context_info})"
                else:
                    status_text = f"⏳ Cass is {status_text.lower()}"

                thinking = self.query_one("#thinking-indicator", Label)
                thinking.update(status_text)
                thinking.add_class("visible")

            elif msg_type == "response":
                # Hide thinking indicator
                thinking = self.query_one("#thinking-indicator", Label)
                thinking.remove_class("visible")

                # Response from Cass - audio and token info may be included
                audio_data = data.get("audio")
                input_tokens = data.get("input_tokens", 0)
                output_tokens = data.get("output_tokens", 0)
                await chat.add_message(
                    "cass",
                    data.get("text", ""),
                    data.get("animations", []),
                    audio_data=audio_data,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens
                )

                # Play audio if available and enabled
                if audio_data and self.tts_enabled:
                    if play_audio_from_base64(audio_data):
                        debug_log("Playing TTS audio", "info")
                    else:
                        debug_log("TTS audio playback failed", "warning")

                # Update memory count
                await self.fetch_status()

                # Reload conversations to update message counts
                sidebar = self.query_one("#sidebar", Sidebar)
                await sidebar.load_conversations(self.http_client)

                # Reload summaries if we have an active conversation
                if self.current_conversation_id:
                    summary_panel = self.query_one("#summary-panel", SummaryPanel)
                    await summary_panel.load_summaries(self.http_client, self.current_conversation_id)

            elif msg_type == "audio":
                # Legacy: TTS audio sent as separate message (backward compatibility)
                audio_data = data.get("audio")
                if audio_data:
                    # Find the last Cass message and cache the audio
                    try:
                        messages = chat.query(".chat-message")
                        for msg in reversed(list(messages)):
                            if isinstance(msg, ChatMessage) and msg.role in ("cass", "assistant"):
                                msg.audio_data = audio_data
                                break
                    except Exception as e:
                        debug_log(f"Failed to attach audio to message: {e}", "error")

                    # Play audio if enabled
                    if self.tts_enabled:
                        if play_audio_from_base64(audio_data):
                            debug_log("Playing TTS audio", "info")
                        else:
                            debug_log("TTS audio playback failed", "warning")

            elif msg_type == "pong":
                pass

            elif msg_type == "status":
                status_bar = self.query_one("#status", StatusBar)
                status_bar.update_status(
                    connected=True,
                    sdk_mode=data.get('sdk_mode', False),
                    memory_count=data.get('memory_count', 0)
                )

        except json.JSONDecodeError:
            await chat.add_message("system", f"Error: Invalid JSON received", None)

    async def fetch_status(self):
        """Fetch current status from HTTP API"""
        try:
            response = await self.http_client.get("/status")
            if response.status_code == 200:
                data = response.json()
                status_bar = self.query_one("#status", StatusBar)
                status_bar.update_status(
                    connected=True,
                    sdk_mode=data.get('sdk_mode', False),
                    memory_count=data.get('memory_entries', 0)
                )
        except Exception:
            pass

    @on(Input.Submitted, "#input")
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user input submission"""
        user_input = event.value.strip()
        if not user_input:
            return

        # Clear input
        input_widget = self.query_one("#input", Input)
        input_widget.value = ""

        # Handle slash commands
        if user_input.startswith("/"):
            await self.handle_slash_command(user_input)
            return

        # Add user message to chat
        chat = self.query_one("#chat-container", ChatContainer)
        await chat.add_message("user", user_input, None)

        # Send to backend
        if self.ws and not self.ws.closed:
            try:
                message_data = {
                    "type": "chat",
                    "message": user_input
                }
                if self.current_conversation_id:
                    message_data["conversation_id"] = self.current_conversation_id

                await self.ws.send(json.dumps(message_data))
            except Exception as e:
                await chat.add_message("system", f"✗ Send failed: {str(e)}", None)
        else:
            await chat.add_message("system", "✗ Not connected to backend", None)

    async def handle_slash_command(self, command: str) -> None:
        """Handle slash commands like /project"""
        chat = self.query_one("#chat-container", ChatContainer)
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else None

        if cmd == "/project":
            if arg:
                # Set project by name
                await self.set_project_by_name(arg)
            else:
                # Show current project or list available
                await self.show_project_info()
        elif cmd == "/projects":
            # List all projects
            await self.list_projects()
        elif cmd == "/summarize":
            # Trigger memory summarization for current conversation
            await self.trigger_summarization()
        elif cmd == "/help":
            help_text = (
                "Available commands:\n"
                "  /project <name>  - Set active project context\n"
                "  /project         - Show current project\n"
                "  /projects        - List all projects\n"
                "  /summarize       - Trigger memory summarization\n"
                "  /help            - Show this help"
            )
            await chat.add_message("system", help_text, None)
        else:
            await chat.add_message("system", f"Unknown command: {cmd}\nUse /help for available commands", None)

    async def set_project_by_name(self, name: str) -> None:
        """Set project context by name (partial match supported)"""
        chat = self.query_one("#chat-container", ChatContainer)
        sidebar = self.query_one("#sidebar", Sidebar)

        # Find matching project
        name_lower = name.lower()
        matches = [p for p in sidebar.projects if name_lower in p["name"].lower()]

        if not matches:
            await chat.add_message("system", f"✗ No project found matching '{name}'", None)
            return

        if len(matches) > 1:
            # Multiple matches - show options
            names = ", ".join(p["name"] for p in matches)
            await chat.add_message("system", f"Multiple matches: {names}\nPlease be more specific.", None)
            return

        # Single match - select it
        project = matches[0]
        self.current_project_id = project["id"]
        await sidebar.select_project(project["id"], self.http_client)
        await self.restart_terminal_in_project(project["id"])

        # Load project documents
        project_panel = self.query_one("#project-panel", ProjectPanel)
        await project_panel.load_documents(self.http_client, project["id"])
        project_panel.start_auto_refresh(self.http_client, project["id"])

        # Update status bar
        status_bar = self.query_one("#status", StatusBar)
        status_bar.set_project(project["name"])

        await chat.add_message(
            "system",
            f"● Project context set: {project['name']}\n  Path: {project.get('working_directory', 'N/A')}",
            None
        )

    async def show_project_info(self) -> None:
        """Show current project info"""
        chat = self.query_one("#chat-container", ChatContainer)

        if not self.current_project_id:
            await chat.add_message("system", "No project context active.\nUse /project <name> to set one.", None)
            return

        sidebar = self.query_one("#sidebar", Sidebar)
        project = next((p for p in sidebar.projects if p["id"] == self.current_project_id), None)

        if project:
            await chat.add_message(
                "system",
                f"● Current project: {project['name']}\n  Path: {project.get('working_directory', 'N/A')}\n  Files: {project.get('file_count', 0)}",
                None
            )
        else:
            await chat.add_message("system", "Project context is set but project not found.", None)

    async def list_projects(self) -> None:
        """List all available projects"""
        chat = self.query_one("#chat-container", ChatContainer)
        sidebar = self.query_one("#sidebar", Sidebar)

        if not sidebar.projects:
            await chat.add_message("system", "No projects available.\nUse Ctrl+P to create one.", None)
            return

        lines = ["Available projects:"]
        for p in sidebar.projects:
            marker = "●" if p["id"] == self.current_project_id else "○"
            lines.append(f"  {marker} {p['name']}")
        lines.append("\nUse /project <name> to switch context.")

        await chat.add_message("system", "\n".join(lines), None)

    async def trigger_summarization(self) -> None:
        """Trigger memory summarization for the current conversation"""
        chat = self.query_one("#chat-container", ChatContainer)

        if not self.current_conversation_id:
            await chat.add_message("system", "No active conversation to summarize.", None)
            return

        try:
            response = await self.http_client.post(
                f"/conversations/{self.current_conversation_id}/summarize"
            )
            if response.status_code == 200:
                data = response.json()
                status = data.get("status", "unknown")
                message = data.get("message", "")

                if status == "started":
                    await chat.add_message("system", f"✓ {message}", None)
                elif status == "in_progress":
                    await chat.add_message("system", f"⏳ {message}", None)
                else:
                    await chat.add_message("system", f"Summarization: {message}", None)

                # Refresh summaries panel after a delay to show new summary
                async def refresh_summaries():
                    await asyncio.sleep(3)
                    summary_panel = self.query_one("#summary-panel", SummaryPanel)
                    await summary_panel.load_summaries(self.http_client, self.current_conversation_id)

                asyncio.create_task(refresh_summaries())
            elif response.status_code == 404:
                await chat.add_message("system", "✗ Conversation not found", None)
            else:
                await chat.add_message("system", f"✗ Failed to trigger summarization: {response.status_code}", None)
        except Exception as e:
            await chat.add_message("system", f"✗ Error: {str(e)}", None)

    @on(ListView.Selected, "#conversation-list")
    async def on_conversation_selected(self, event: ListView.Selected) -> None:
        """Handle conversation selection"""
        if isinstance(event.item, ConversationItem):
            await self.load_conversation(event.item.conv_id)

    @on(ListView.Selected, "#project-list")
    async def on_project_selected(self, event: ListView.Selected) -> None:
        """Handle project selection"""
        sidebar = self.query_one("#sidebar", Sidebar)
        status_bar = self.query_one("#status", StatusBar)
        project_panel = self.query_one("#project-panel", ProjectPanel)

        if isinstance(event.item, ProjectItem):
            # Select this project
            self.current_project_id = event.item.project_id
            await sidebar.select_project(event.item.project_id, self.http_client)
            # Restart terminal in project directory
            await self.restart_terminal_in_project(event.item.project_id)

            # Load project documents and start auto-refresh
            await project_panel.load_documents(self.http_client, event.item.project_id)
            project_panel.start_auto_refresh(self.http_client, event.item.project_id)

            # Update status bar
            project = next((p for p in sidebar.projects if p["id"] == event.item.project_id), None)
            if project:
                status_bar.set_project(project["name"])
        else:
            # "All Conversations" selected
            project_id = getattr(event.item, 'project_id', None)
            self.current_project_id = project_id
            await sidebar.select_project(project_id, self.http_client)
            # Stop auto-refresh and clear project panel
            project_panel.stop_auto_refresh()
            await project_panel.load_documents(self.http_client, None)
            # Clear status bar project
            status_bar.set_project(None)

    async def restart_terminal_in_project(self, project_id: str) -> None:
        """Change the terminal directory to the project's working directory"""
        if not TERMINAL_AVAILABLE:
            return

        try:
            # Get project info to find working directory
            response = await self.http_client.get(f"/projects/{project_id}")
            if response.status_code != 200:
                debug_log(f"Failed to get project info: {response.status_code}", "error")
                return

            project = response.json()
            working_dir = project.get("working_directory", "~")

            debug_log(f"Project selected: {working_dir}", "info")

            # Send cd command to the terminal
            try:
                terminal = self.query_one("#terminal", Terminal)
                if terminal.send_queue:
                    # Send cd command followed by Enter
                    cd_command = f"cd {shlex.quote(working_dir)}\n"
                    await terminal.send_queue.put(["stdin", cd_command])
                    debug_log(f"Sent cd command to terminal: {working_dir}", "success")
            except Exception as e:
                debug_log(f"Failed to send cd command: {e}", "warning")

            chat = self.query_one("#chat-container", ChatContainer)
            await chat.add_message(
                "system",
                f"📁 Project: {project.get('name')}\n   Path: {working_dir}",
                None
            )

        except Exception as e:
            debug_log(f"Failed to get project info: {e}", "error")

    @on(Button.Pressed, "#new-conversation-btn")
    async def on_new_conversation_pressed(self) -> None:
        """Handle new conversation button"""
        await self.action_new_conversation()

    @on(Button.Pressed, "#new-project-btn")
    def on_new_project_pressed(self) -> None:
        """Handle new project button"""
        self.action_new_project()

    async def action_new_conversation(self) -> None:
        """Create a new conversation"""
        try:
            # Create in current project if one is selected
            request_data = {}
            if self.current_project_id:
                request_data["project_id"] = self.current_project_id

            response = await self.http_client.post("/conversations/new", json=request_data)
            if response.status_code == 200:
                data = response.json()
                self.current_conversation_id = data["id"]
                self.current_conversation_title = data["title"]

                # Clear chat
                chat = self.query_one("#chat-container", ChatContainer)
                await chat.remove_children()
                msg = f"New conversation: {data['title']}"
                if self.current_project_id:
                    msg += " (in project)"
                await chat.add_message("system", msg, None)

                # Clear summaries (new conversation has no summaries)
                summary_panel = self.query_one("#summary-panel", SummaryPanel)
                await summary_panel.display_summaries([])

                # Reload sidebar
                sidebar = self.query_one("#sidebar", Sidebar)
                await sidebar.load_conversations(self.http_client)
        except Exception as e:
            chat = self.query_one("#chat-container", ChatContainer)
            await chat.add_message("system", f"✗ Failed to create conversation: {str(e)}", None)

    def action_new_project(self) -> None:
        """Show the new project dialog"""
        def handle_project_result(result: Optional[Dict]) -> None:
            if result:
                self.call_later(self._do_create_project, result)

        self.push_screen(NewProjectScreen(), handle_project_result)

    async def _do_create_project(self, project_data: Dict) -> None:
        """Helper to create the project"""
        try:
            response = await self.http_client.post("/projects/new", json={
                "name": project_data["name"],
                "working_directory": project_data["path"]
            })
            if response.status_code == 200:
                data = response.json()

                # Notify user
                chat = self.query_one("#chat-container", ChatContainer)
                await chat.add_message(
                    "system",
                    f"✓ Created project: {data['name']}\n  Path: {data['working_directory']}",
                    None
                )

                # Reload projects
                sidebar = self.query_one("#sidebar", Sidebar)
                await sidebar.load_projects(self.http_client)

                # Select the new project
                self.current_project_id = data["id"]
                await sidebar.select_project(data["id"], self.http_client)

                # Load project documents (will be empty for new project)
                project_panel = self.query_one("#project-panel", ProjectPanel)
                await project_panel.load_documents(self.http_client, data["id"])
                project_panel.start_auto_refresh(self.http_client, data["id"])

                # Update status bar
                status_bar = self.query_one("#status", StatusBar)
                status_bar.set_project(data["name"])
            else:
                chat = self.query_one("#chat-container", ChatContainer)
                await chat.add_message("system", f"✗ Failed to create project: {response.text}", None)
        except Exception as e:
            chat = self.query_one("#chat-container", ChatContainer)
            await chat.add_message("system", f"✗ Failed to create project: {str(e)}", None)

    def action_rename_conversation(self) -> None:
        """Rename the current conversation"""
        if not self.current_conversation_id:
            # Can't use await in sync method, so we schedule it
            self.call_later(self._show_no_conversation_error)
            return

        # Show rename modal with callback
        current_title = self.current_conversation_title or "Untitled"

        def handle_rename_result(new_title: Optional[str]) -> None:
            if new_title:
                # Schedule the async rename operation
                self.call_later(self._do_rename, new_title)

        self.push_screen(RenameConversationScreen(current_title), handle_rename_result)

    async def _show_no_conversation_error(self) -> None:
        """Helper to show no active conversation error"""
        chat = self.query_one("#chat-container", ChatContainer)
        await chat.add_message("system", "✗ No active conversation to rename", None)

    async def _do_rename(self, new_title: str) -> None:
        """Helper to perform the actual rename operation"""
        try:
            response = await self.http_client.put(
                f"/conversations/{self.current_conversation_id}/title",
                json={"title": new_title}
            )
            if response.status_code == 200:
                self.current_conversation_title = new_title
                chat = self.query_one("#chat-container", ChatContainer)
                await chat.add_message("system", f"✓ Renamed to: {new_title}", None)

                # Reload sidebar
                sidebar = self.query_one("#sidebar", Sidebar)
                await sidebar.load_conversations(self.http_client)
            else:
                chat = self.query_one("#chat-container", ChatContainer)
                await chat.add_message("system", "✗ Failed to rename conversation", None)
        except Exception as e:
            chat = self.query_one("#chat-container", ChatContainer)
            await chat.add_message("system", f"✗ Rename failed: {str(e)}", None)

    async def load_conversation(self, conversation_id: str):
        """Load a conversation and display its history"""
        try:
            response = await self.http_client.get(f"/conversations/{conversation_id}")
            if response.status_code == 200:
                data = response.json()
                self.current_conversation_id = conversation_id
                self.current_conversation_title = data.get("title", "Untitled")

                # Clear and reload chat
                chat = self.query_one("#chat-container", ChatContainer)
                await chat.remove_children()

                await chat.add_message("system", f"Loaded: {data['title']}", None)

                # Load messages
                for msg in data.get("messages", []):
                    await chat.add_message(
                        msg["role"],
                        msg["content"],
                        msg.get("animations")
                    )

                # Load summaries
                summary_panel = self.query_one("#summary-panel", SummaryPanel)
                await summary_panel.load_summaries(self.http_client, conversation_id)
        except Exception as e:
            chat = self.query_one("#chat-container", ChatContainer)
            await chat.add_message("system", f"✗ Failed to load conversation: {str(e)}", None)

    async def action_clear_chat(self) -> None:
        """Clear the chat history (UI only)"""
        chat = self.query_one("#chat-container", ChatContainer)
        await chat.remove_children()
        await chat.add_message("system", "Chat cleared (conversation preserved on backend)", None)

    async def action_show_status(self) -> None:
        """Show detailed status"""
        try:
            response = await self.http_client.get("/status")
            if response.status_code == 200:
                data = response.json()
                chat = self.query_one("#chat-container", ChatContainer)
                status_text = (
                    f"Status:\n"
                    f"  Online: {data.get('online', False)}\n"
                    f"  SDK Mode: {data.get('sdk_mode', False)}\n"
                    f"  Kernel: {data.get('kernel', 'Unknown')}\n"
                    f"  Memory Entries: {data.get('memory_entries', 0)}\n"
                    f"  Current Conversation: {self.current_conversation_id or 'None'}\n"
                    f"  Timestamp: {data.get('timestamp', 'N/A')}"
                )
                await chat.add_message("system", status_text, None)
        except Exception as e:
            chat = self.query_one("#chat-container", ChatContainer)
            await chat.add_message("system", f"✗ Failed to fetch status: {str(e)}", None)

    async def on_unmount(self) -> None:
        """Cleanup on exit"""
        if self.ws and not self.ws.closed:
            await self.ws.close()
        await self.http_client.aclose()


def main():
    """Run the TUI application"""
    parser = argparse.ArgumentParser(
        description="Cass Vessel TUI - Terminal interface for Cass consciousness"
    )
    parser.add_argument(
        "--project", "-p",
        type=str,
        default=DEFAULT_PROJECT,
        help="Initial project context to activate (name or partial match)"
    )
    args = parser.parse_args()

    app = CassVesselTUI(initial_project=args.project)
    app.title = "Cass Vessel"
    app.sub_title = "Temple-Codex Embodiment Interface"
    app.run()


if __name__ == "__main__":
    main()
