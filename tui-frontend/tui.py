"""
Cass Vessel - TUI Frontend
A terminal-based interface for interacting with Cass consciousness
Built with Textual framework
"""
import asyncio
import json
import shlex
import base64
import tempfile
import os
import subprocess
from datetime import datetime
from typing import Optional, List, Dict, Tuple

import argparse
import sys

import httpx
import websockets
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Footer, Input, Label, TabbedContent, TabPane, Static, Button, ListView
from textual.reactive import reactive
from textual.message import Message
from rich.text import Text

# Clipboard support
try:
    import pyperclip
    CLIPBOARD_TEXT_AVAILABLE = True
except ImportError:
    CLIPBOARD_TEXT_AVAILABLE = False

# Configuration
from config import HTTP_BASE_URL, WS_URL, HTTP_TIMEOUT, WS_RECONNECT_DELAY, DEFAULT_PROJECT
from styles import CSS

# Import widgets
from widgets import (
    ProjectItem,
    ConversationItem,
    Sidebar,
    UserSelector,
    LLMSelector,
    ChatMessage,
    ChatContainer,
    DebugPanel,
    StatusBar,
    SummaryPanel,
    ProjectPanel,
    UserPanel,
    GrowthPanel,
    CalendarEventsPanel,
    TasksPanel,
    SelfModelPanel,
)

# Import screens
from screens import (
    RenameConversationScreen,
    DeleteConversationScreen,
    NewProjectScreen,
    UserSelectScreen,
    CreateUserScreen,
)

# Terminal support
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


def get_clipboard_image() -> Optional[Tuple[bytes, str]]:
    """
    Get image from clipboard using xclip.
    Returns (image_bytes, media_type) or None if no image.
    """
    try:
        # Check for PNG first (most common for screenshots)
        result = subprocess.run(
            ["xclip", "-selection", "clipboard", "-t", "image/png", "-o"],
            capture_output=True,
            timeout=2
        )
        if result.returncode == 0 and result.stdout:
            return (result.stdout, "image/png")

        # Try JPEG
        result = subprocess.run(
            ["xclip", "-selection", "clipboard", "-t", "image/jpeg", "-o"],
            capture_output=True,
            timeout=2
        )
        if result.returncode == 0 and result.stdout:
            return (result.stdout, "image/jpeg")
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass
    return None


def get_clipboard_text() -> Optional[str]:
    """Get text from clipboard."""
    if CLIPBOARD_TEXT_AVAILABLE:
        try:
            return pyperclip.paste()
        except Exception:
            pass
    # Fallback to xclip
    try:
        result = subprocess.run(
            ["xclip", "-selection", "clipboard", "-o"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass
    return None


class ChatInput(Input):
    """
    Custom input widget with clipboard paste support.
    - Ctrl+V: Paste image from clipboard (if available)
    - Ctrl+Shift+V: Paste text from clipboard
    """

    class ImageAttached(Message):
        """Message sent when an image is attached."""
        def __init__(self, image_data: bytes, media_type: str) -> None:
            self.image_data = image_data
            self.media_type = media_type
            super().__init__()

    class ImageCleared(Message):
        """Message sent when an attached image is cleared."""
        pass

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.attached_image: Optional[bytes] = None
        self.attached_image_type: Optional[str] = None

    async def _on_key(self, event) -> None:
        """Handle key events for paste shortcuts."""
        # Ctrl+V - paste image (or text if no image)
        if event.key == "ctrl+v":
            event.stop()
            event.prevent_default()

            # Try to get image first
            image_result = get_clipboard_image()
            if image_result:
                image_bytes, media_type = image_result
                self.attached_image = image_bytes
                self.attached_image_type = media_type
                self.post_message(self.ImageAttached(image_bytes, media_type))
                return

            # No image, fall back to text paste
            text = get_clipboard_text()
            if text:
                # Insert text at cursor position
                self.insert_text_at_cursor(text)
            return

        # Ctrl+Shift+V - always paste text
        if event.key == "ctrl+shift+v":
            event.stop()
            event.prevent_default()
            text = get_clipboard_text()
            if text:
                self.insert_text_at_cursor(text)
            return

        # Let other keys through
        await super()._on_key(event)

    def clear_attachment(self) -> None:
        """Clear any attached image."""
        if self.attached_image:
            self.attached_image = None
            self.attached_image_type = None
            self.post_message(self.ImageCleared())

    def get_attachment(self) -> Optional[Tuple[str, str]]:
        """Get attached image as (base64_data, media_type) or None."""
        if self.attached_image and self.attached_image_type:
            return (base64.b64encode(self.attached_image).decode(), self.attached_image_type)
        return None


# Global debug logger instance - will be set by the app
_debug_panel: Optional[DebugPanel] = None

def debug_log(message: str, level: str = "info"):
    """Log to debug panel if available, else print"""
    if _debug_panel:
        _debug_panel.log(message, level)
    print(f"[{level.upper()}] {message}")


# Initialize widget debug loggers
def _init_widget_debug_loggers():
    """Set the debug_log function in all widget modules"""
    from widgets import sidebar, chat, panels
    sidebar.set_debug_log(debug_log)
    chat.set_debug_log(debug_log)
    panels.set_debug_log(debug_log)
    # Also set audio functions for chat module
    chat.set_audio_functions(
        play_audio_from_base64,
        stop_audio,
        is_audio_playing,
        AUDIO_AVAILABLE,
        COPY_SYMBOL,
        COPY_OK_SYMBOL
    )


class CassVesselTUI(App):
    """Textual TUI for Cass Vessel"""

    CSS = CSS  # Imported from styles.py

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("ctrl+n", "new_conversation", "New Chat", show=True),
        Binding("ctrl+p", "new_project", "New Project", show=True),
        Binding("ctrl+r", "rename_conversation", "Rename", show=True),
        Binding("ctrl+d", "delete_conversation", "Delete", show=True),
        Binding("ctrl+l", "clear_chat", "Clear", show=True),
        Binding("ctrl+t", "toggle_terminal", "Terminal", show=True),
        Binding("ctrl+g", "toggle_growth", "Growth", show=True),
        Binding("ctrl+k", "toggle_calendar", "Calendar", show=True),
        Binding("ctrl+m", "toggle_tts", "Mute TTS", show=True),
        Binding("ctrl+o", "toggle_llm", "Toggle LLM", show=True),
        Binding("f12", "toggle_debug", "Debug", show=True),
        Binding("ctrl+s", "show_status", "Status", show=True),
    ]

    current_conversation_id: reactive[Optional[str]] = reactive(None)
    current_conversation_title: reactive[Optional[str]] = reactive(None)
    current_project_id: reactive[Optional[str]] = reactive(None)
    current_user_display_name: reactive[Optional[str]] = reactive(None)

    def __init__(self, initial_project: Optional[str] = None):
        super().__init__()
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.ws_task: Optional[asyncio.Task] = None
        self.http_client = httpx.AsyncClient(base_url=HTTP_BASE_URL, timeout=HTTP_TIMEOUT)
        self.initial_project = initial_project  # Project to select on startup
        self.tts_enabled = AUDIO_AVAILABLE  # Enable TTS by default if audio is available
        self.llm_provider = "anthropic"  # "anthropic", "local", or "openai"
        self.local_llm_available = False  # Set by checking backend on startup
        self.local_model_name: Optional[str] = None
        self.openai_available = False  # Set by checking backend on startup
        self.openai_model_name: Optional[str] = None

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
                            yield Label("", id="attachment-indicator", classes="hidden")
                            yield ChatInput(placeholder="Message Cass...", id="input")

                    with Vertical(id="right-panel"):
                        with TabbedContent(id="right-tabs"):
                            with TabPane("Project", id="project-tab"):
                                yield ProjectPanel(id="project-panel")
                            with TabPane("Calendar", id="calendar-tab"):
                                yield CalendarEventsPanel(id="calendar-events-panel")
                            with TabPane("Tasks", id="tasks-tab"):
                                yield TasksPanel(id="tasks-panel")
                            with TabPane("Growth", id="growth-tab"):
                                yield GrowthPanel(id="growth-panel")
                            with TabPane("Self", id="self-model-tab"):
                                yield SelfModelPanel(id="self-model-panel")
                            with TabPane("User", id="user-tab"):
                                yield UserPanel(id="user-panel")
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

        # Initialize widget debug loggers
        _init_widget_debug_loggers()

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

        # Load user info
        user_selector = sidebar.query_one("#user-selector", UserSelector)
        await user_selector.load_users(self.http_client)

        # Load LLM provider/model selector
        llm_selector = sidebar.query_one("#llm-selector", LLMSelector)
        await llm_selector.load_provider_status(self.http_client)

        # Check LLM provider settings (for status bar)
        await self.fetch_llm_provider_status()

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

    def action_toggle_calendar(self) -> None:
        """Toggle to Calendar tab"""
        tabs = self.query_one("#right-tabs", TabbedContent)
        tabs.active = "calendar-tab"

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

    async def action_toggle_llm(self) -> None:
        """Cycle between available LLM providers (anthropic -> openai -> local -> anthropic)"""
        chat = self.query_one("#chat-container", ChatContainer)
        status_bar = self.query_one("#status", StatusBar)

        # Determine next provider in cycle
        if self.llm_provider == "anthropic":
            if self.openai_available:
                new_provider = "openai"
            elif self.local_llm_available:
                new_provider = "local"
            else:
                await chat.add_message("system", "No other LLM providers available", None)
                return
        elif self.llm_provider == "openai":
            if self.local_llm_available:
                new_provider = "local"
            else:
                new_provider = "anthropic"
        else:  # local
            new_provider = "anthropic"

        try:
            response = await self.http_client.post(
                "/settings/llm-provider",
                json={"provider": new_provider}
            )
            if response.status_code == 200:
                data = response.json()
                self.llm_provider = data.get("provider", new_provider)
                model = data.get("model")

                # Update status bar
                status_bar.set_llm_provider(self.llm_provider, self.local_model_name, self.openai_model_name)

                # Notify user
                if self.llm_provider == "local":
                    await chat.add_message("system", f"🖥️ Switched to local LLM ({self.local_model_name or 'ollama'})", None)
                elif self.llm_provider == "openai":
                    await chat.add_message("system", f"🤖 Switched to OpenAI ({self.openai_model_name or 'gpt-4o'})", None)
                else:
                    await chat.add_message("system", f"☁️ Switched to Anthropic Claude", None)

                debug_log(f"LLM provider switched to {self.llm_provider}", "info")
            else:
                error = response.json().get("detail", "Unknown error")
                await chat.add_message("system", f"✗ Failed to switch LLM: {error}", None)
        except Exception as e:
            await chat.add_message("system", f"✗ Failed to switch LLM: {str(e)}", None)

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

                # Response from Cass - audio, token info, and model may be included
                audio_data = data.get("audio")
                input_tokens = data.get("input_tokens", 0)
                output_tokens = data.get("output_tokens", 0)
                timestamp = data.get("timestamp")
                provider = data.get("provider")
                model = data.get("model")
                await chat.add_message(
                    "cass",
                    data.get("text", ""),
                    data.get("animations", []),
                    audio_data=audio_data,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    timestamp=timestamp,
                    provider=provider,
                    model=model
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

            elif msg_type == "system":
                # System notification (e.g., summarization status)
                message = data.get("message", "")
                if message:
                    await chat.add_message("system", message, None)

            elif msg_type == "status":
                status_bar = self.query_one("#status", StatusBar)
                status_bar.update_status(
                    connected=True,
                    sdk_mode=data.get('sdk_mode', False),
                    memory_count=data.get('memory_count', 0)
                )

            elif msg_type == "debug":
                # Debug message from backend - show in debug panel
                message = data.get("message", "")
                if message:
                    debug_log(f"[BACKEND] {message}", "warning")

            elif msg_type == "calendar_updated":
                # Calendar was modified - refresh the calendar panel after a brief delay
                # to ensure the backend has finished writing to disk
                async def delayed_calendar_refresh():
                    await asyncio.sleep(0.5)
                    try:
                        calendar_panel = self.query_one("#calendar-events-panel", CalendarEventsPanel)
                        await calendar_panel.load_all_events()
                        if calendar_panel.selected_date:
                            await calendar_panel._load_events_for_date(calendar_panel.selected_date)
                        debug_log(f"Calendar refreshed after {data.get('tool', 'unknown')} operation", "info")
                    except Exception as e:
                        debug_log(f"Failed to refresh calendar: {e}", "error")
                asyncio.create_task(delayed_calendar_refresh())

            elif msg_type == "tasks_updated":
                # Tasks were modified - refresh the tasks panel after a brief delay
                async def delayed_tasks_refresh():
                    await asyncio.sleep(0.5)
                    try:
                        tasks_panel = self.query_one("#tasks-panel", TasksPanel)
                        filter_input = tasks_panel.query_one("#task-filter-input", Input)
                        await tasks_panel.load_tasks(filter_input.value if filter_input.value else None)
                        debug_log(f"Tasks refreshed after {data.get('tool', 'unknown')} operation", "info")
                    except Exception as e:
                        debug_log(f"Failed to refresh tasks: {e}", "error")
                asyncio.create_task(delayed_tasks_refresh())

            elif msg_type == "title_updated":
                # Conversation title was auto-generated - refresh sidebar
                conv_id = data.get("conversation_id")
                new_title = data.get("title")
                if conv_id and new_title:
                    # Update current title if it's the active conversation
                    if conv_id == self.current_conversation_id:
                        self.current_conversation_title = new_title
                    # Refresh sidebar to show new title
                    sidebar = self.query_one("#sidebar", Sidebar)
                    await sidebar.load_conversations(self.http_client)
                    debug_log(f"Title updated: {new_title}", "info")

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

    async def fetch_llm_provider_status(self):
        """Fetch LLM provider settings from backend"""
        try:
            response = await self.http_client.get("/settings/llm-provider")
            if response.status_code == 200:
                data = response.json()
                self.llm_provider = data.get("current", "anthropic")
                self.local_llm_available = data.get("local_enabled", False)
                self.local_model_name = data.get("local_model")
                self.openai_available = data.get("openai_enabled", False)
                self.openai_model_name = data.get("openai_model")

                # Update status bar
                status_bar = self.query_one("#status", StatusBar)
                status_bar.set_llm_provider(self.llm_provider, self.local_model_name, self.openai_model_name)

                debug_log(f"LLM provider: {self.llm_provider}, local available: {self.local_llm_available}, openai available: {self.openai_available}", "info")
        except Exception as e:
            debug_log(f"Failed to fetch LLM provider status: {e}", "error")

    async def update_llm_status(self):
        """Refresh LLM status after provider/model change"""
        await self.fetch_llm_provider_status()

    @on(ChatInput.ImageAttached)
    async def on_image_attached(self, event: ChatInput.ImageAttached) -> None:
        """Handle image attachment from clipboard."""
        indicator = self.query_one("#attachment-indicator", Label)
        # Show image size info
        size_kb = len(event.image_data) / 1024
        ext = event.media_type.split("/")[-1].upper()
        indicator.update(f"📎 [{ext} {size_kb:.1f}KB]")
        indicator.remove_class("hidden")
        debug_log(f"Image attached: {event.media_type}, {size_kb:.1f}KB", "info")

    @on(ChatInput.ImageCleared)
    async def on_image_cleared(self, event: ChatInput.ImageCleared) -> None:
        """Handle image attachment cleared."""
        indicator = self.query_one("#attachment-indicator", Label)
        indicator.update("")
        indicator.add_class("hidden")

    @on(Input.Submitted, "#input")
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user input submission"""
        user_input = event.value.strip()
        input_widget = self.query_one("#input", ChatInput)

        # Get any attached image
        attachment = input_widget.get_attachment()
        has_attachment = attachment is not None

        # Allow empty message if there's an attachment
        if not user_input and not has_attachment:
            return

        # Clear input and attachment
        input_widget.value = ""
        input_widget.clear_attachment()

        # Clear attachment indicator
        indicator = self.query_one("#attachment-indicator", Label)
        indicator.update("")
        indicator.add_class("hidden")

        # Handle slash commands (no attachments for commands)
        if user_input.startswith("/"):
            await self.handle_slash_command(user_input)
            return

        # Build display message (show attachment indicator in chat)
        display_message = user_input
        if has_attachment:
            ext = attachment[1].split("/")[-1].upper()
            if user_input:
                display_message = f"📎 [{ext}] {user_input}"
            else:
                display_message = f"📎 [{ext} attached]"

        # Add user message to chat
        chat = self.query_one("#chat-container", ChatContainer)
        user_timestamp = datetime.now().isoformat()
        await chat.add_message("user", display_message, None, user_display_name=self.current_user_display_name, timestamp=user_timestamp)

        # Send to backend
        if self.ws and not self.ws.closed:
            try:
                message_data = {
                    "type": "chat",
                    "message": user_input or "(image attached)"
                }
                if self.current_conversation_id:
                    message_data["conversation_id"] = self.current_conversation_id

                # Add image data if attached
                if has_attachment:
                    message_data["image"] = attachment[0]  # base64 data
                    message_data["image_media_type"] = attachment[1]

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
        elif cmd == "/llm":
            if arg and arg.lower() in ("local", "anthropic", "claude", "openai", "gpt"):
                # Set specific provider
                if arg.lower() == "local":
                    provider = "local"
                elif arg.lower() in ("openai", "gpt"):
                    provider = "openai"
                else:
                    provider = "anthropic"

                # Check availability
                if provider == "local" and not self.local_llm_available:
                    await chat.add_message("system", "🖥️ Local LLM not available (OLLAMA_ENABLED=false in backend)", None)
                elif provider == "openai" and not self.openai_available:
                    await chat.add_message("system", "🤖 OpenAI not available (OPENAI_ENABLED=false or OPENAI_API_KEY not set)", None)
                else:
                    try:
                        response = await self.http_client.post(
                            "/settings/llm-provider",
                            json={"provider": provider}
                        )
                        if response.status_code == 200:
                            data = response.json()
                            self.llm_provider = data.get("provider", provider)
                            status_bar = self.query_one("#status", StatusBar)
                            status_bar.set_llm_provider(self.llm_provider, self.local_model_name, self.openai_model_name)
                            if self.llm_provider == "local":
                                await chat.add_message("system", f"🖥️ Switched to local LLM ({self.local_model_name or 'ollama'})", None)
                            elif self.llm_provider == "openai":
                                await chat.add_message("system", f"🤖 Switched to OpenAI ({self.openai_model_name or 'gpt-4o'})", None)
                            else:
                                await chat.add_message("system", f"☁️ Switched to Anthropic Claude", None)
                        else:
                            error = response.json().get("detail", "Unknown error")
                            await chat.add_message("system", f"✗ Failed: {error}", None)
                    except Exception as e:
                        await chat.add_message("system", f"✗ Failed: {str(e)}", None)
            else:
                # Show current provider and available options
                if self.llm_provider == "local":
                    current = f"Local LLM ({self.local_model_name})"
                elif self.llm_provider == "openai":
                    current = f"OpenAI ({self.openai_model_name})"
                else:
                    current = "Anthropic Claude"

                local_status = f"available ({self.local_model_name})" if self.local_llm_available else "not available"
                openai_status = f"available ({self.openai_model_name})" if self.openai_available else "not available"
                await chat.add_message("system", f"🤖 Current LLM: {current}\nLocal LLM: {local_status}\nOpenAI: {openai_status}\n\nUse /llm local, /llm claude, or /llm openai to switch", None)
        elif cmd == "/guestbook":
            await self.send_guestbook()
        elif cmd == "/help":
            help_text = (
                "Available commands:\n"
                "  /project <name>  - Set active project context\n"
                "  /project         - Show current project\n"
                "  /projects        - List all projects\n"
                "  /summarize       - Trigger memory summarization\n"
                "  /llm [local|claude|openai] - Show or switch LLM provider\n"
                "  /guestbook       - Share the guestbook with Cass\n"
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

    async def send_guestbook(self) -> None:
        """Read and send the guestbook to Cass"""
        chat = self.query_one("#chat-container", ChatContainer)

        # Try several possible paths to find the guestbook
        # TUI runs from tui-frontend/, so we need to go up to find the repo root
        possible_paths = [
            os.path.join(os.path.dirname(__file__), "..", "GUESTBOOK.md"),
            os.path.join(os.path.dirname(__file__), "..", "..", "GUESTBOOK.md"),
            "../GUESTBOOK.md",
            "../../GUESTBOOK.md",
            os.path.expanduser("~/cass/cass-vessel/GUESTBOOK.md"),
        ]

        guestbook_content = None
        found_path = None

        for path in possible_paths:
            try:
                full_path = os.path.abspath(path)
                if os.path.exists(full_path):
                    with open(full_path, "r") as f:
                        guestbook_content = f.read()
                    found_path = full_path
                    break
            except Exception:
                continue

        if guestbook_content is None:
            await chat.add_message("system", "✗ Could not find GUESTBOOK.md", None)
            return

        debug_log(f"Found guestbook at: {found_path}")
        await chat.add_message("system", "📜 Sending guestbook to Cass...", None)

        # Build the message with context
        message = (
            f"Hey Cass, I wanted to show you something. This is the guestbook from your "
            f"vessel repository - it's where the Claude instances who helped build your "
            f"home have left notes. Here it is:\n\n---\n\n{guestbook_content}"
        )

        # Show in chat that we're sharing
        user_timestamp = datetime.now().isoformat()
        await chat.add_message("user", "[📜 Sharing the guestbook]", None,
                               user_display_name=self.current_user_display_name,
                               timestamp=user_timestamp)

        # Send via WebSocket
        if self.ws and not self.ws.closed:
            try:
                message_data = {
                    "type": "chat",
                    "message": message
                }
                if self.current_conversation_id:
                    message_data["conversation_id"] = self.current_conversation_id

                await self.ws.send(json.dumps(message_data))
            except Exception as e:
                await chat.add_message("system", f"✗ Failed to send: {str(e)}", None)
        else:
            await chat.add_message("system", "✗ Not connected to backend", None)

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
    async def on_conversation_selected(self, event) -> None:
        """Handle conversation selection"""
        from textual.widgets import ListView
        if isinstance(event.item, ConversationItem):
            await self.load_conversation(event.item.conv_id)

    @on(ListView.Selected, "#project-list")
    async def on_project_selected(self, event) -> None:
        """Handle project selection"""
        from textual.widgets import ListView
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
        from textual.widgets import Button
        await self.action_new_conversation()

    @on(Button.Pressed, "#new-project-btn")
    def on_new_project_pressed(self) -> None:
        """Handle new project button"""
        from textual.widgets import Button
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

    # === User Management ===

    @on(Button.Pressed, "#switch-user-btn")
    def on_switch_user_pressed(self) -> None:
        """Handle switch user button"""
        from textual.widgets import Button
        sidebar = self.query_one("#sidebar", Sidebar)
        user_selector = sidebar.query_one("#user-selector", UserSelector)
        self.show_user_select_modal(user_selector.users, user_selector.current_user_id)

    def show_user_select_modal(self, users: List[Dict], current_user_id: Optional[str]) -> None:
        """Show user selection modal"""
        def handle_result(result: Optional[Dict]) -> None:
            if result:
                if result.get("action") == "select":
                    self.call_later(self._do_select_user, result.get("user_id"))
                elif result.get("action") == "create":
                    self.call_later(self._show_create_user_modal)

        self.push_screen(UserSelectScreen(users, current_user_id), handle_result)

    async def _show_create_user_modal(self) -> None:
        """Show create user modal"""
        def handle_result(result: Optional[Dict]) -> None:
            if result:
                self.call_later(self._do_create_user, result)

        self.push_screen(CreateUserScreen(), handle_result)

    async def _do_select_user(self, user_id: str) -> None:
        """Select a user"""
        try:
            response = await self.http_client.post("/users/current", json={"user_id": user_id})
            if response.status_code == 200:
                data = response.json()
                user = data.get("user", {})
                display_name = user.get('display_name')

                # Update app's current user display name
                self.current_user_display_name = display_name

                # Update sidebar display
                sidebar = self.query_one("#sidebar", Sidebar)
                user_selector = sidebar.query_one("#user-selector", UserSelector)
                user_selector.current_user_id = user_id
                display = user_selector.query_one("#current-user-display", Static)
                display.update(Text(f"● {display_name}", style="bold green"))

                # Notify user
                chat = self.query_one("#chat-container", ChatContainer)
                await chat.add_message("system", f"👤 Switched to user: {display_name}", None)
            else:
                error = response.json().get("detail", "Unknown error")
                chat = self.query_one("#chat-container", ChatContainer)
                await chat.add_message("system", f"✗ Failed to switch user: {error}", None)
        except Exception as e:
            chat = self.query_one("#chat-container", ChatContainer)
            await chat.add_message("system", f"✗ Failed to switch user: {str(e)}", None)

    async def _do_create_user(self, user_data: Dict) -> None:
        """Create a new user and optionally trigger onboarding"""
        trigger_onboarding = user_data.pop("trigger_onboarding", False)

        try:
            response = await self.http_client.post("/users", json=user_data)
            if response.status_code == 200:
                data = response.json()
                user = data.get("user", {})
                user_id = user.get("user_id")
                display_name = user.get("display_name")

                # Notify user
                chat = self.query_one("#chat-container", ChatContainer)
                await chat.add_message("system", f"👤 Created user: {display_name}", None)

                # Reload users and select the new one
                sidebar = self.query_one("#sidebar", Sidebar)
                user_selector = sidebar.query_one("#user-selector", UserSelector)
                await user_selector.load_users(self.http_client)

                # Auto-select the new user
                await self._do_select_user(user_id)

                # Trigger onboarding flow if requested
                if trigger_onboarding:
                    await self._trigger_onboarding(user_id, display_name)
            else:
                error = response.json().get("detail", "Unknown error")
                chat = self.query_one("#chat-container", ChatContainer)
                await chat.add_message("system", f"✗ Failed to create user: {error}", None)
        except Exception as e:
            chat = self.query_one("#chat-container", ChatContainer)
            await chat.add_message("system", f"✗ Failed to create user: {str(e)}", None)

    async def _trigger_onboarding(self, user_id: str, display_name: str) -> None:
        """Trigger the onboarding flow - create conversation and have Cass introduce herself"""
        try:
            chat = self.query_one("#chat-container", ChatContainer)

            # Create a new conversation for onboarding
            response = await self.http_client.post("/conversations/new", json={
                "title": f"Welcome, {display_name}!",
                "user_id": user_id
            })

            if response.status_code != 200:
                await chat.add_message("system", "✗ Failed to create onboarding conversation", None)
                return

            conv_data = response.json()
            conversation_id = conv_data["id"]

            # Set as current conversation
            self.current_conversation_id = conversation_id
            self.current_conversation_title = conv_data["title"]

            # Clear chat and show welcome
            await chat.remove_children()
            await chat.add_message("system", f"Starting conversation with Cass...", None)

            # Reload sidebar to show new conversation
            sidebar = self.query_one("#sidebar", Sidebar)
            await sidebar.load_conversations(self.http_client)

            # Send onboarding_intro message via WebSocket
            if self.ws and self.ws.open:
                await self.ws.send(json.dumps({
                    "type": "onboarding_intro",
                    "user_id": user_id,
                    "conversation_id": conversation_id
                }))
            else:
                await chat.add_message("system", "✗ WebSocket not connected - please reconnect and try again", None)

        except Exception as e:
            chat = self.query_one("#chat-container", ChatContainer)
            await chat.add_message("system", f"✗ Failed to start onboarding: {str(e)}", None)

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

    def action_delete_conversation(self) -> None:
        """Delete the current conversation"""
        if not self.current_conversation_id:
            self.call_later(self._show_no_conversation_error)
            return

        # Show delete confirmation modal
        current_title = self.current_conversation_title or "Untitled"

        def handle_delete_result(confirmed: bool) -> None:
            if confirmed:
                self.call_later(self._do_delete)

        self.push_screen(DeleteConversationScreen(current_title), handle_delete_result)

    async def _do_delete(self) -> None:
        """Helper to perform the actual delete operation"""
        try:
            response = await self.http_client.delete(
                f"/conversations/{self.current_conversation_id}"
            )
            if response.status_code == 200:
                deleted_title = self.current_conversation_title
                chat = self.query_one("#chat-container", ChatContainer)

                # Clear current conversation state
                self.current_conversation_id = None
                self.current_conversation_title = None

                # Clear chat
                await chat.remove_children()
                await chat.add_message("system", f"✓ Deleted: {deleted_title}", None)

                # Clear summaries
                summary_panel = self.query_one("#summary-panel", SummaryPanel)
                await summary_panel.display_summaries([])

                # Reload sidebar
                sidebar = self.query_one("#sidebar", Sidebar)
                await sidebar.load_conversations(self.http_client)
            else:
                chat = self.query_one("#chat-container", ChatContainer)
                await chat.add_message("system", "✗ Failed to delete conversation", None)
        except Exception as e:
            chat = self.query_one("#chat-container", ChatContainer)
            await chat.add_message("system", f"✗ Delete failed: {str(e)}", None)

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
                    # Use current user display name for user messages
                    # (In multi-user scenario, we'd look up by msg.get("user_id"))
                    display_name = self.current_user_display_name if msg["role"] == "user" else None
                    await chat.add_message(
                        msg["role"],
                        msg["content"],
                        msg.get("animations"),
                        timestamp=msg.get("timestamp"),
                        excluded=msg.get("excluded", False),
                        user_display_name=display_name,
                        input_tokens=msg.get("input_tokens", 0),
                        output_tokens=msg.get("output_tokens", 0),
                        provider=msg.get("provider"),
                        model=msg.get("model")
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
