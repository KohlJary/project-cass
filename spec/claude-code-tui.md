# Design Requirements: PTY-Based Claude Code Integration for Cass TUI

## Overview

Integrate Claude Code (and other terminal applications) as a first-class citizen within the Cass TUI, using direct PTY management rather than relying on `textual-terminal`. The goal is seamless, responsive interaction with Claude Code instances from within the existing Textual-based interface.

## Problem Statement

The current `textual-terminal` approach hangs during long-running operations and lacks the responsiveness needed for extended Claude Code sessions. We need a more robust solution that:

- Handles long-running operations without blocking the TUI
- Properly renders Claude Code's rich terminal output
- Allows switching between Cass conversations and Claude Code sessions
- Maintains session persistence (survives TUI restarts)

## Architecture

### Core Components

#### 1. PTY Manager (`pty_manager.py`)

Responsible for spawning and managing PTY subprocesses.

```
PTYManager
├── spawn_session(command: str, name: str) -> Session
├── attach_session(name: str) -> Session
├── list_sessions() -> list[Session]
├── kill_session(name: str) -> bool
└── resize_session(name: str, cols: int, rows: int)
```

**Requirements:**
- Use `pty.fork()` for subprocess creation
- Maintain registry of active sessions by name
- Handle SIGCHLD for process cleanup
- Support both new spawns and attaching to existing tmux sessions

#### 2. Terminal Emulator (`terminal_emulator.py`)

Interprets ANSI escape sequences and maintains a virtual terminal buffer.

```
TerminalEmulator
├── feed(data: bytes) -> None
├── get_buffer() -> list[list[Cell]]
├── get_cursor_position() -> tuple[int, int]
├── resize(cols: int, rows: int) -> None
└── get_dirty_lines() -> list[int]
```

**Requirements:**
- Use `pyte` library for terminal emulation
- Track dirty lines for efficient TUI updates
- Support standard VT100/xterm escape sequences
- Handle alternate screen buffer (for vim, htop, Claude Code's TUI)

#### 3. Async I/O Handler (`async_pty_reader.py`)

Non-blocking read/write to PTY file descriptors.

```
AsyncPTYHandler
├── async read() -> bytes
├── async write(data: bytes) -> None
├── set_nonblocking(fd: int) -> None
└── on_data_received: Callback
```

**Requirements:**
- Integrate with asyncio event loop (Textual uses asyncio)
- Use `select` or `asyncio.add_reader()` for fd monitoring
- Buffer writes to prevent blocking on slow consumers
- Handle EAGAIN/EWOULDBLOCK gracefully

#### 4. TUI Widget (`claude_terminal_widget.py`)

Textual widget that renders the terminal emulator buffer.

```
ClaudeTerminalWidget(Widget)
├── on_mount() -> None
├── on_resize(event) -> None
├── on_key(event) -> None
├── render() -> RenderResult
├── attach_session(session: Session) -> None
└── detach_session() -> None
```

**Requirements:**
- Render `pyte` buffer to Textual Rich renderables
- Forward key events to PTY (including special keys, ctrl sequences)
- Handle resize events and propagate to PTY
- Support focus management (when focused, keys go to PTY)
- Efficient rendering - only update changed lines

### Data Flow

```
┌─────────────────┐
│  Claude Code    │
│  (subprocess)   │
└────────┬────────┘
         │ PTY (fd)
         │
┌────────▼────────┐
│  AsyncPTYHandler │ ◄── asyncio event loop
└────────┬────────┘
         │ bytes
         │
┌────────▼────────┐
│ TerminalEmulator │ ◄── pyte screen buffer
└────────┬────────┘
         │ Cell buffer
         │
┌────────▼────────┐
│ ClaudeTerminal  │ ◄── Textual widget
│     Widget      │
└────────┬────────┘
         │ Rich renderables
         │
┌────────▼────────┐
│   Textual App   │
└─────────────────┘
```

### Input Flow (reverse)

```
Key Press → ClaudeTerminalWidget.on_key() → AsyncPTYHandler.write() → PTY fd → Claude Code
```

## Implementation Details

### PTY Spawning

```python
import pty
import os
import fcntl
import struct
import termios

def spawn_claude_session(cols: int = 120, rows: int = 40) -> tuple[int, int]:
    """Spawn Claude Code in a PTY, return (pid, fd)."""
    pid, fd = pty.fork()
    
    if pid == 0:
        # Child process
        os.execlp("claude", "claude")
    else:
        # Parent - set terminal size
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
        
        # Set non-blocking
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        
        return pid, fd
```

### Async Reading

```python
import asyncio

async def read_pty_output(fd: int, callback):
    """Read from PTY fd and invoke callback with data."""
    loop = asyncio.get_event_loop()
    
    def reader():
        try:
            data = os.read(fd, 4096)
            if data:
                callback(data)
        except OSError:
            pass
    
    loop.add_reader(fd, reader)
```

### Terminal Emulation with pyte

```python
import pyte

class TerminalEmulator:
    def __init__(self, cols: int = 120, rows: int = 40):
        self.screen = pyte.Screen(cols, rows)
        self.stream = pyte.Stream(self.screen)
        self.dirty_lines = set()
        
        # Track changes
        original_draw = self.screen.draw
        def tracking_draw(data):
            self.dirty_lines.add(self.screen.cursor.y)
            original_draw(data)
        self.screen.draw = tracking_draw
    
    def feed(self, data: bytes):
        self.stream.feed(data.decode("utf-8", errors="replace"))
    
    def get_rich_output(self) -> list:
        """Convert pyte buffer to Rich Text objects."""
        lines = []
        for y in range(self.screen.lines):
            line = self.screen.buffer[y]
            # Convert to Rich Text with styles...
            lines.append(self._line_to_rich(line))
        return lines
```

### Textual Widget Integration

```python
from textual.widget import Widget
from textual.events import Key, Resize

class ClaudeTerminalWidget(Widget):
    def __init__(self, session_name: str = "claude"):
        super().__init__()
        self.emulator = TerminalEmulator()
        self.pty_handler = None
        self.session_name = session_name
    
    async def on_mount(self):
        # Spawn or attach to Claude Code session
        pid, fd = spawn_claude_session(self.size.width, self.size.height)
        self.pty_handler = AsyncPTYHandler(fd)
        self.pty_handler.on_data = self._handle_pty_output
        await self.pty_handler.start()
    
    def _handle_pty_output(self, data: bytes):
        self.emulator.feed(data)
        self.refresh()
    
    async def on_key(self, event: Key):
        if self.pty_handler:
            # Translate Textual key to terminal escape sequence
            data = self._key_to_bytes(event)
            await self.pty_handler.write(data)
    
    def on_resize(self, event: Resize):
        self.emulator.resize(event.size.width, event.size.height)
        if self.pty_handler:
            self.pty_handler.resize(event.size.width, event.size.height)
    
    def render(self):
        return self.emulator.get_rich_output()
```

## Session Persistence Options

### Option A: Direct PTY Management

Sessions live as long as the TUI process. Simple but sessions die with the app.

### Option B: tmux Backend

Use tmux as the session persistence layer:

```python
def spawn_claude_in_tmux(session_name: str) -> tuple[int, int]:
    """Create tmux session with Claude Code, return PTY to tmux."""
    # Create detached tmux session
    subprocess.run(["tmux", "new-session", "-d", "-s", session_name, "claude"])
    
    # Attach to it via PTY
    pid, fd = pty.fork()
    if pid == 0:
        os.execlp("tmux", "tmux", "attach", "-t", session_name)
    return pid, fd
```

**Recommendation:** Option B (tmux backend) - gives you session persistence for free, and you can still attach from raw terminal if needed.

## Integration with Cass TUI

### Navigation

- Add a new screen/tab type for Claude Code sessions
- Keyboard shortcut to spawn new Claude session (e.g., `ctrl+n`)
- Keyboard shortcut to switch between Cass chat and Claude sessions (e.g., `ctrl+tab`)
- Session list in sidebar showing active Claude Code instances

### Session Naming

Auto-generate names based on working directory or allow user naming:
- `claude-cass-vessel`
- `claude-temple-codex`
- `claude-adhoc-1`

### Context Sharing (Future Enhancement)

- Button/command to "Send to Cass" - takes Claude Code output and sends to Cass conversation
- Button/command to "Send to Claude" - takes Cass response and pastes into Claude Code session
- Shared clipboard between contexts

## Dependencies

```
pyte>=0.8.0          # Terminal emulation
textual>=0.40.0      # TUI framework (already present)
```

## Testing Strategy

### Unit Tests

- PTY spawn/kill lifecycle
- Terminal emulator escape sequence handling
- Key translation (special keys, ctrl sequences)

### Integration Tests

- Spawn Claude Code, send input, verify output rendered
- Resize handling
- Multiple simultaneous sessions

### Manual Testing

- Long-running operations (file edits, searches)
- High output volume (large file diffs)
- Special key handling (ctrl+c, ctrl+z, arrow keys, etc.)

## Open Questions

1. **Window size defaults** - What size should we spawn Claude Code at? Match TUI widget size dynamically?

2. **Scrollback** - Should we maintain scrollback buffer beyond what pyte provides? How much?

3. **Copy/paste** - How to handle selection and clipboard in terminal widget?

4. **Color themes** - Should Claude terminal inherit Cass TUI theme or use its own?

## Success Criteria

- [ ] Can spawn Claude Code instance from within Cass TUI
- [ ] Output renders correctly including colors and cursor positioning
- [ ] Input works including special keys and ctrl sequences
- [ ] No hangs during long operations
- [ ] Sessions persist across TUI restarts (via tmux)
- [ ] Can run multiple Claude Code sessions simultaneously
- [ ] Resize works smoothly
