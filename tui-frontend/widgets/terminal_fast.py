"""
Fast Terminal - A patched version of textual-terminal with better performance.

Fixes the hanging issue during long-running operations by:
1. Batching output chunks instead of one-per-event
2. Debouncing screen rebuilds
3. Better async handling
"""

from __future__ import annotations

import os
import fcntl
import signal
import shlex
import asyncio
from asyncio import Task
import pty
import struct
import termios
import re
from pathlib import Path
from typing import Optional

import pyte
from pyte.screens import Char

from rich.text import Text
from rich.style import Style
from rich.color import ColorParseError

from textual.widget import Widget
from textual import events
from textual import log


class TerminalPyteScreen(pyte.Screen):
    """Overrides the pyte.Screen class to be used with TERM=linux."""

    def set_margins(self, *args, **kwargs):
        kwargs.pop("private", None)
        return super().set_margins(*args, **kwargs)


class TerminalDisplay:
    """Rich display for the terminal."""

    def __init__(self, lines):
        self.lines = lines

    def __rich_console__(self, _console, _options):
        line: Text
        for line in self.lines:
            yield line


_re_ansi_sequence = re.compile(r"(\x1b\[\??[\d;]*[a-zA-Z])")
DECSET_PREFIX = "\x1b[?"

# OSC/DCS/APC sequence patterns to filter
_re_osc_sequence = re.compile(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)')
_re_dcs_sequence = re.compile(r'\x1bP[^\x1b]*\x1b\\')
_re_apc_sequence = re.compile(r'\x1b_[^\x1b]*\x1b\\')


class Terminal(Widget, can_focus=True):
    """Fast terminal textual widget with improved performance."""

    DEFAULT_CSS = """
    Terminal {
        background: $background;
    }
    """

    textual_colors: dict | None

    def __init__(
        self,
        command: str,
        default_colors: str | None = "system",
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self.command = command
        self.default_colors = default_colors

        if default_colors == "textual":
            self.textual_colors = self.detect_textual_colors()
        else:
            self.textual_colors = None

        # default size, will be adapted on_resize
        self.ncol = 80
        self.nrow = 24
        self.mouse_tracking = False

        # variables used when starting the emulator: self.start()
        self.emulator: TerminalEmulator = None
        self.send_queue: asyncio.Queue = None
        self.recv_queue: asyncio.Queue = None
        self.recv_task: Task = None

        # Refresh debouncing
        self._pending_refresh = False
        self._refresh_scheduled = False

        # OPTIMIZE: check a way to use textual.keys
        self.ctrl_keys = {
            # Arrow keys
            "up": "\x1bOA",
            "down": "\x1bOB",
            "right": "\x1bOC",
            "left": "\x1bOD",
            "home": "\x1bOH",
            "end": "\x1b[F",
            "delete": "\x1b[3~",
            "pageup": "\x1b[5~",
            "pagedown": "\x1b[6~",
            "shift+tab": "\x1b[Z",
            # Function keys
            "f1": "\x1bOP",
            "f2": "\x1bOQ",
            "f3": "\x1bOR",
            "f4": "\x1bOS",
            "f5": "\x1b[15~",
            "f6": "\x1b[17~",
            "f7": "\x1b[18~",
            "f8": "\x1b[19~",
            "f9": "\x1b[20~",
            "f10": "\x1b[21~",
            "f11": "\x1b[23~",
            "f12": "\x1b[24~",
            "f13": "\x1b[25~",
            "f14": "\x1b[26~",
            "f15": "\x1b[28~",
            "f16": "\x1b[29~",
            "f17": "\x1b[31~",
            "f18": "\x1b[32~",
            "f19": "\x1b[33~",
            "f20": "\x1b[34~",
            # Ctrl+letter combinations (ASCII control characters)
            # Ctrl+A = 0x01, Ctrl+B = 0x02, etc.
            "ctrl+a": "\x01",
            "ctrl+b": "\x02",  # tmux prefix!
            "ctrl+c": "\x03",
            "ctrl+d": "\x04",
            "ctrl+e": "\x05",
            "ctrl+f": "\x06",
            "ctrl+g": "\x07",
            "ctrl+h": "\x08",
            "ctrl+i": "\x09",  # Tab
            "ctrl+j": "\x0a",  # Newline
            "ctrl+k": "\x0b",
            "ctrl+l": "\x0c",
            "ctrl+m": "\x0d",  # Carriage return
            "ctrl+n": "\x0e",
            "ctrl+o": "\x0f",
            "ctrl+p": "\x10",
            "ctrl+q": "\x11",
            "ctrl+r": "\x12",
            "ctrl+s": "\x13",
            "ctrl+t": "\x14",
            "ctrl+u": "\x15",
            "ctrl+v": "\x16",
            "ctrl+w": "\x17",
            "ctrl+x": "\x18",
            "ctrl+y": "\x19",
            "ctrl+z": "\x1a",
            # Ctrl+special keys
            "escape": "\x1b",  # Escape key
            "ctrl+[": "\x1b",  # Escape (alternative)
            "ctrl+\\": "\x1c",
            "ctrl+]": "\x1d",
            "ctrl+^": "\x1e",
            "ctrl+_": "\x1f",
        }
        self._display = self.initial_display()
        self._screen = TerminalPyteScreen(self.ncol, self.nrow)
        self.stream = pyte.Stream(self._screen)

        super().__init__(name=name, id=id, classes=classes)

    def start(self) -> None:
        if self.emulator is not None:
            return

        self.emulator = TerminalEmulator(command=self.command)
        self.emulator.start()
        self.send_queue = self.emulator.recv_queue
        self.recv_queue = self.emulator.send_queue
        self.recv_task = asyncio.create_task(self.recv())

    def stop(self) -> None:
        if self.emulator is None:
            return

        self._display = self.initial_display()

        self.recv_task.cancel()

        self.emulator.stop()
        self.emulator = None

    def render(self):
        return self._display

    async def on_key(self, event: events.Key) -> None:
        if self.emulator is None:
            return

        if event.key == "ctrl+f1":
            self.app.set_focus(None)
            return

        event.stop()
        char = self.ctrl_keys.get(event.key) or event.character
        if char:
            await self.send_queue.put(["stdin", char])

    async def on_resize(self, _event: events.Resize) -> None:
        if self.emulator is None:
            return

        self.ncol = self.size.width
        self.nrow = self.size.height
        await self.send_queue.put(["set_size", self.nrow, self.ncol])
        self._screen.resize(self.nrow, self.ncol)

    async def on_click(self, event: events.MouseEvent):
        if self.emulator is None:
            return

        if self.mouse_tracking is False:
            return

        await self.send_queue.put(["click", event.x, event.y, event.button])

    async def on_mouse_scroll_down(self, event: events.MouseScrollDown):
        if self.emulator is None:
            return

        if self.mouse_tracking is False:
            return

        await self.send_queue.put(["scroll", "down", event.x, event.y])

    async def on_mouse_scroll_up(self, event: events.MouseScrollUp):
        if self.emulator is None:
            return

        if self.mouse_tracking is False:
            return

        await self.send_queue.put(["scroll", "up", event.x, event.y])

    def _schedule_display_refresh(self) -> None:
        """Schedule a debounced display refresh."""
        self._pending_refresh = True
        if not self._refresh_scheduled:
            self._refresh_scheduled = True
            self.set_timer(0.016, self._do_display_refresh)  # ~60fps

    def _do_display_refresh(self) -> None:
        """Actually rebuild and refresh the display."""
        self._refresh_scheduled = False
        if not self._pending_refresh:
            return
        self._pending_refresh = False

        lines = []
        last_char: Char
        last_style: Style
        for y in range(self._screen.lines):
            line_text = Text()
            line = self._screen.buffer[y]
            style_change_pos: int = 0
            for x in range(self._screen.columns):
                char: Char = line[x]

                line_text.append(char.data)

                # if style changed, stylize it with rich
                if x > 0:
                    last_char = line[x - 1]
                    if not self.char_style_cmp(char, last_char) or x == self._screen.columns - 1:
                        last_style = self.char_rich_style(last_char)
                        line_text.stylize(last_style, style_change_pos, x + 1)
                        style_change_pos = x

                if (
                    self._screen.cursor.x == x
                    and self._screen.cursor.y == y
                ):
                    line_text.stylize("reverse", x, x + 1)

            lines.append(line_text)

        self._display = TerminalDisplay(lines)
        self.refresh()

    async def recv(self):
        try:
            while True:
                message = await self.recv_queue.get()
                cmd = message[0]
                if cmd == "setup":
                    await self.send_queue.put(["set_size", self.nrow, self.ncol])
                elif cmd == "stdout":
                    chars = message[1]

                    # Filter out problematic escape sequences
                    chars = _re_osc_sequence.sub('', chars)
                    chars = _re_dcs_sequence.sub('', chars)
                    chars = _re_apc_sequence.sub('', chars)

                    for sep_match in re.finditer(_re_ansi_sequence, chars):
                        sequence = sep_match.group(0)
                        if sequence.startswith(DECSET_PREFIX):
                            parameters = sequence.removeprefix(DECSET_PREFIX).split(";")
                            if "1000h" in parameters:
                                self.mouse_tracking = True
                            if "1000l" in parameters:
                                self.mouse_tracking = False

                    try:
                        self.stream.feed(chars)
                    except TypeError as error:
                        log.warning("could not feed:", error)

                    # Schedule a debounced refresh instead of immediate rebuild
                    self._schedule_display_refresh()

                elif cmd == "disconnect":
                    self.stop()
        except asyncio.CancelledError:
            pass

    def char_rich_style(self, char: Char) -> Style:
        """Returns a rich.Style from the pyte.Char."""

        foreground = self.detect_color(char.fg)
        background = self.detect_color(char.bg)
        if self.default_colors == "textual" and self.textual_colors:
            if background == "default":
                background = self.textual_colors.get("background", "default")
            if foreground == "default":
                foreground = self.textual_colors.get("foreground", "default")

        style: Style
        try:
            style = Style(
                color=foreground,
                bgcolor=background,
                bold=char.bold,
            )
        except ColorParseError as error:
            log.warning("color parse error:", error)
            style = None

        return style

    def char_style_cmp(self, given: Char, other: Char) -> bool:
        """Compares two pyte.Chars and returns if these are the same."""

        if (
            given.fg == other.fg
            and given.bg == other.bg
            and given.bold == other.bold
            and given.italics == other.italics
            and given.underscore == other.underscore
            and given.strikethrough == other.strikethrough
            and given.reverse == other.reverse
            and given.blink == other.blink
        ):
            return True

        return False

    def char_style_default(self, char: Char) -> bool:
        """Returns True if the given char has a default style."""

        if (
            char.fg == "default"
            and char.bg == "default"
            and char.bold is False
            and char.italics is False
            and char.underscore is False
            and char.strikethrough is False
            and char.reverse is False
            and char.blink is False
        ):
            return True

        return False

    def detect_color(self, color: str) -> str:
        """Tries to detect the correct Rich-Color based on a color name."""

        if color == "brown":
            return "yellow"

        if color == "brightblack":
            return "#808080"

        # Handle hex colors without # prefix
        if re.match("[0-9a-f]{6}", color, re.IGNORECASE):
            return f"#{color}"

        return color

    def detect_textual_colors(self) -> dict:
        """Returns the currently used colors of textual depending on dark-mode."""
        # In newer Textual versions, get colors from the current theme
        try:
            theme = self.app.current_theme
            if theme:
                return {
                    "background": theme.background or "default",
                    "foreground": theme.foreground or "default",
                }
        except Exception:
            pass
        return {"background": "default", "foreground": "default"}

    def initial_display(self) -> TerminalDisplay:
        """Returns the display when initially creating the terminal or clearing it."""

        return TerminalDisplay([Text()])


class TerminalEmulator:
    """Improved terminal emulator with better output handling."""

    def __init__(self, command: str):
        self.ncol = 80
        self.nrow = 24
        self.data_buffer: list[str] = []
        self.run_task: asyncio.Task = None
        self.send_task: asyncio.Task = None

        self.fd = self.open_terminal(command=command)
        self.p_out = os.fdopen(self.fd, "w+b", 0)  # 0: buffering off
        self.recv_queue = asyncio.Queue()
        self.send_queue = asyncio.Queue()
        self.event = asyncio.Event()

    def start(self):
        self.run_task = asyncio.create_task(self._run())
        self.send_task = asyncio.create_task(self._send_data())

    def stop(self):
        self.run_task.cancel()
        self.send_task.cancel()

        try:
            os.kill(self.pid, signal.SIGTERM)
            os.waitpid(self.pid, 0)
        except (OSError, ChildProcessError):
            pass

    def open_terminal(self, command: str):
        self.pid, fd = pty.fork()
        if self.pid == 0:
            argv = shlex.split(command)
            env = dict(TERM="xterm-256color", LC_ALL="en_US.UTF-8", HOME=str(Path.home()))
            # Inherit PATH from parent
            env["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")
            os.execvpe(argv[0], argv, env)

        return fd

    async def _run(self):
        loop = asyncio.get_running_loop()

        def on_output():
            try:
                data = self.p_out.read(65536).decode()
                self.data_buffer.append(data)
                self.event.set()
            except UnicodeDecodeError as error:
                log.warning("decode error:", error)
            except Exception:
                loop.remove_reader(self.p_out)
                self.data_buffer = None  # Signal disconnect
                self.event.set()

        loop.add_reader(self.p_out, on_output)
        await self.send_queue.put(["setup", {}])
        try:
            while True:
                msg = await self.recv_queue.get()
                if msg[0] == "stdin":
                    self.p_out.write(msg[1].encode())
                elif msg[0] == "set_size":
                    winsize = struct.pack("HH", msg[1], msg[2])
                    fcntl.ioctl(self.fd, termios.TIOCSWINSZ, winsize)
                elif msg[0] == "click":
                    x = msg[1] + 1
                    y = msg[2] + 1
                    button = msg[3]

                    if button == 1:
                        self.p_out.write(f"\x1b[<0;{x};{y}M".encode())
                        self.p_out.write(f"\x1b[<0;{x};{y}m".encode())
                elif msg[0] == "scroll":
                    x = msg[2] + 1
                    y = msg[3] + 1

                    if msg[1] == "up":
                        self.p_out.write(f"\x1b[<64;{x};{y}M".encode())
                    if msg[1] == "down":
                        self.p_out.write(f"\x1b[<65;{x};{y}M".encode())
        except asyncio.CancelledError:
            pass

    async def _send_data(self):
        try:
            while True:
                await self.event.wait()
                self.event.clear()

                if self.data_buffer is None:
                    # Disconnect signal
                    await self.send_queue.put(["disconnect", 1])
                    break

                # Drain all buffered data at once
                if self.data_buffer:
                    combined = "".join(self.data_buffer)
                    self.data_buffer.clear()
                    await self.send_queue.put(["stdout", combined])

        except asyncio.CancelledError:
            pass
