"""
Cass Vessel TUI - Chat Widgets
Chat message display and interaction components
"""
import re
from datetime import datetime
from typing import Optional, List, Dict

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.widgets import Button, Static
from rich.text import Text
from rich.markdown import Markdown
from rich.syntax import Syntax


# Forward declaration for debug_log - will be set by main module
def debug_log(message: str, level: str = "info"):
    """Log to debug panel if available, else print"""
    print(f"[{level.upper()}] {message}")


def set_debug_log(func):
    """Set the debug_log function from main module"""
    global debug_log
    debug_log = func


# Audio functions - will be set by main module
_play_audio_from_base64 = None
_stop_audio = None
_is_audio_playing = None
AUDIO_AVAILABLE = False
COPY_SYMBOL = "📋"
COPY_OK_SYMBOL = "✓"


def set_audio_functions(play_func, stop_func, is_playing_func, audio_available: bool, copy_sym: str, copy_ok_sym: str):
    """Set audio functions from main module"""
    global _play_audio_from_base64, _stop_audio, _is_audio_playing, AUDIO_AVAILABLE, COPY_SYMBOL, COPY_OK_SYMBOL
    _play_audio_from_base64 = play_func
    _stop_audio = stop_func
    _is_audio_playing = is_playing_func
    AUDIO_AVAILABLE = audio_available
    COPY_SYMBOL = copy_sym
    COPY_OK_SYMBOL = copy_ok_sym


class CodeBlockWidget(Vertical):
    """A code block with syntax highlighting and copy button"""

    def __init__(self, code: str, language: str = "", **kwargs):
        super().__init__(**kwargs)
        self.code = code
        self.language = language or "text"

    def compose(self) -> ComposeResult:
        from textual.widgets import Label
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
    # Pattern to match <gesture:think>...</gesture:think> blocks (internal processing)
    THINK_BLOCK_PATTERN = re.compile(r'<gesture:think>(.*?)</gesture:think>', re.DOTALL)
    # Pattern to clean remaining gesture/emote tags (self-closing and block-style)
    GESTURE_EMOTE_TAG_PATTERN = re.compile(r'</?(?:gesture|emote):\w+(?::\d*\.?\d+)?/?>')

    def __init__(
        self,
        role: str,
        content: str,
        animations: Optional[List[Dict]] = None,
        audio_data: Optional[str] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        timestamp: Optional[str] = None,
        excluded: bool = False,
        user_display_name: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        self_observations: Optional[List[Dict]] = None,
        user_observations: Optional[List[Dict]] = None,
        marks: Optional[List[Dict]] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.role = role
        # Extract memory tags and clean content
        self.memory_tags = self.MEMORY_TAG_PATTERN.findall(content)
        cleaned_content = self.MEMORY_TAG_PATTERN.sub('', content).strip()

        # Extract thinking blocks (internal processing wrapped in <gesture:think>)
        self.thinking_blocks = self.THINK_BLOCK_PATTERN.findall(cleaned_content)
        # Remove thinking blocks from main content
        self.content = self.THINK_BLOCK_PATTERN.sub('', cleaned_content).strip()
        # Clean remaining gesture/emote tags from response content
        self.content = self.GESTURE_EMOTE_TAG_PATTERN.sub('', self.content)
        # Clean up extra whitespace from removed blocks/tags
        self.content = re.sub(r'\n\s*\n\s*\n', '\n\n', self.content).strip()

        self.animations = animations or []
        self.audio_data = audio_data  # Base64 encoded audio for replay
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.timestamp = timestamp  # ISO timestamp for API calls
        self.excluded = excluded  # If True, message is excluded from memory/summarization
        self.user_display_name = user_display_name  # Display name for user messages
        self.provider = provider  # LLM provider (anthropic, openai, local)
        self.model = model  # Model ID used for this response
        # Recognition-in-flow markers
        self.self_observations = self_observations or []
        self.user_observations = user_observations or []
        self.marks = marks or []
        # Parse content into segments (text and code blocks)
        self.segments = self._parse_content(self.content)
        # Parse thinking blocks into segments too (also clean any stray tags)
        self.thinking_segments = []
        for block in self.thinking_blocks:
            clean_block = self.GESTURE_EMOTE_TAG_PATTERN.sub('', block.strip())
            self.thinking_segments.extend(self._parse_content(clean_block))

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
            prefix = self.user_display_name or "You"
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
            # Show model info for Cass messages
            if self.role in ("cass", "assistant") and self.model:
                # Shorten model name for display
                short_model = self.model.split("-")[0] if self.model else ""
                if "claude" in self.model.lower():
                    short_model = self.model.replace("claude-", "").split("-2")[0]  # e.g., "sonnet-4"
                elif "gpt" in self.model.lower():
                    short_model = self.model  # e.g., "gpt-4o"
                header_text.append(f" ({short_model})", style="dim italic")
            # Show token usage for Cass messages
            if self.role in ("cass", "assistant") and (self.input_tokens or self.output_tokens):
                header_text.append(f" [{self.input_tokens}→{self.output_tokens}]", style="dim")
            # Show excluded indicator
            if self.excluded:
                header_text.append(" [EXCLUDED]", style="bold red")
            yield Static(header_text, classes="message-role")
            # Add replay button for Cass messages (always visible - fetches on demand if needed)
            if self.role in ("cass", "assistant") and AUDIO_AVAILABLE:
                btn = Button("🔊", classes="replay-btn", variant="default", id=f"replay-{id(self)}")
                yield btn
            yield Button(COPY_SYMBOL, classes="copy-btn", variant="default", id=f"copy-{id(self)}")
            # Add exclude/include button (only if we have a timestamp)
            if self.timestamp:
                exclude_label = "✓" if self.excluded else "✗"
                exclude_btn = Button(exclude_label, classes="exclude-btn", variant="default", id=f"exclude-{id(self)}")
                yield exclude_btn

        # Render content - two columns if there's thinking, single column otherwise
        if self.thinking_segments and self.role in ("cass", "assistant"):
            # Two-column layout: thinking on left, response on right
            with Horizontal(classes="message-split-view"):
                # Thinking column (left)
                with Vertical(classes="thinking-column"):
                    yield Static(Text("💭 Thinking", style="dim italic"), classes="thinking-header")
                    for segment in self.thinking_segments:
                        if segment["type"] == "text":
                            yield Static(Markdown(segment["content"]), classes="thinking-text")
                        elif segment["type"] == "code":
                            yield CodeBlockWidget(
                                segment["content"],
                                segment["language"],
                                classes="thinking-code-block"
                            )
                # Response column (right)
                with Vertical(classes="response-column"):
                    yield Static(Text("💬 Response", style="dim italic"), classes="response-header")
                    for segment in self.segments:
                        if segment["type"] == "text":
                            yield Static(Markdown(segment["content"]), classes="message-text")
                        elif segment["type"] == "code":
                            yield CodeBlockWidget(
                                segment["content"],
                                segment["language"],
                                classes="message-code-block"
                            )
        else:
            # Standard single-column layout
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

        # Add gesture/emote/memory/observation indicators
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
            indicators.append(f"[memory: {', '.join(self.memory_tags)}] ", style="italic magenta")
            has_indicators = True

        # Recognition-in-flow markers
        if self.self_observations:
            # Show each observation with category and brief content
            obs_parts = []
            for obs in self.self_observations:
                cat = obs.get('category', 'pattern')
                content = obs.get('observation', '')
                if content:
                    # Truncate long content
                    if len(content) > 50:
                        content = content[:47] + "..."
                    obs_parts.append(f"{cat}: \"{content}\"")
                else:
                    obs_parts.append(cat)
            indicators.append(f"[self-obs: {', '.join(obs_parts)}] ", style="italic yellow")
            has_indicators = True

        if self.user_observations:
            # Show each observation with category and brief content
            obs_parts = []
            for obs in self.user_observations:
                cat = obs.get('category', 'background')
                content = obs.get('observation', '')
                if content:
                    # Truncate long content
                    if len(content) > 50:
                        content = content[:47] + "..."
                    obs_parts.append(f"{cat}: \"{content}\"")
                else:
                    obs_parts.append(cat)
            indicators.append(f"[user-obs: {', '.join(obs_parts)}] ", style="italic cyan")
            has_indicators = True

        if self.marks:
            # Show each mark with category and brief description
            mark_parts = []
            for mark in self.marks:
                cat = mark.get('category', 'unknown')
                desc = mark.get('description', '')
                if desc:
                    # Truncate long descriptions
                    if len(desc) > 40:
                        desc = desc[:37] + "..."
                    mark_parts.append(f"{cat}: \"{desc}\"")
                else:
                    mark_parts.append(cat)
            indicators.append(f"[marks: {', '.join(mark_parts)}]", style="italic bright_red")
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

        if not _play_audio_from_base64:
            debug_log("Audio functions not initialized", "error")
            return

        # If we have cached audio, play it directly
        if self.audio_data:
            if _play_audio_from_base64(self.audio_data):
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
                        if _play_audio_from_base64(audio_data):
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

    @on(Button.Pressed, ".exclude-btn")
    async def on_exclude_pressed(self, event: Button.Pressed) -> None:
        """Toggle message exclusion from memory/summarization"""
        event.stop()

        if not self.timestamp:
            debug_log("Cannot exclude message without timestamp", "error")
            return

        # Get conversation_id from app
        app = self.app
        if not hasattr(app, 'current_conversation_id') or not app.current_conversation_id:
            debug_log("No active conversation", "error")
            return

        # Toggle exclusion state
        new_excluded = not self.excluded
        event.button.label = "⏳"

        try:
            if hasattr(app, 'http_client') and app.http_client:
                response = await app.http_client.post(
                    f"/conversations/{app.current_conversation_id}/exclude",
                    json={
                        "message_timestamp": self.timestamp,
                        "exclude": new_excluded
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    self.excluded = new_excluded
                    event.button.label = "✓" if self.excluded else "✗"

                    # Update the header to show/hide [EXCLUDED] indicator
                    # Find and update the header Static
                    for child in self.query(".message-role"):
                        if isinstance(child, Static):
                            header_text = Text()
                            time_str = datetime.now().strftime('%H:%M:%S')
                            if self.role == "user":
                                role_style = "bold cyan"
                                prefix = self.user_display_name or "You"
                            elif self.role in ("cass", "assistant"):
                                role_style = "bold magenta"
                                prefix = "Cass"
                            else:
                                role_style = "bold yellow"
                                prefix = self.role.title()
                            header_text.append(f"[{time_str}] ", style="dim")
                            header_text.append(f"{prefix}", style=role_style)
                            # Show model info
                            if self.role in ("cass", "assistant") and self.model:
                                short_model = self.model.split("-")[0] if self.model else ""
                                if "claude" in self.model.lower():
                                    short_model = self.model.replace("claude-", "").split("-2")[0]
                                elif "gpt" in self.model.lower():
                                    short_model = self.model
                                header_text.append(f" ({short_model})", style="dim italic")
                            if self.role in ("cass", "assistant") and (self.input_tokens or self.output_tokens):
                                header_text.append(f" [{self.input_tokens}→{self.output_tokens}]", style="dim")
                            if self.excluded:
                                header_text.append(" [EXCLUDED]", style="bold red")
                            child.update(header_text)
                            break

                    embeddings_removed = data.get("embeddings_removed", 0)
                    action = "Excluded" if new_excluded else "Included"
                    debug_log(f"{action} message, removed {embeddings_removed} embeddings", "info")
                else:
                    debug_log(f"Exclude API error: {response.status_code}", "error")
                    event.button.label = "✓" if self.excluded else "✗"  # Reset to current state
            else:
                debug_log("No HTTP client available", "error")
                event.button.label = "✓" if self.excluded else "✗"
        except Exception as e:
            debug_log(f"Exclude failed: {e}", "error")
            event.button.label = "✓" if self.excluded else "✗"


class ChatContainer(VerticalScroll):
    """Scrollable container for messages"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.can_focus = True

    async def add_message(
        self,
        role: str,
        content: str,
        animations: Optional[List[Dict]] = None,
        audio_data: Optional[str] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        timestamp: Optional[str] = None,
        excluded: bool = False,
        user_display_name: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        self_observations: Optional[List[Dict]] = None,
        user_observations: Optional[List[Dict]] = None,
        marks: Optional[List[Dict]] = None,
    ):
        """Add a new message to the chat"""
        message = ChatMessage(
            role,
            content,
            animations,
            audio_data=audio_data,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            timestamp=timestamp,
            excluded=excluded,
            user_display_name=user_display_name,
            provider=provider,
            model=model,
            self_observations=self_observations,
            user_observations=user_observations,
            marks=marks,
            classes="chat-message",
        )
        await self.mount(message)
        message.scroll_visible()

    async def remove_children(self):
        """Clear all messages"""
        for child in list(self.children):
            await child.remove()
