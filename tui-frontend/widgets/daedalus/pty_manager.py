"""
PTY Manager - Manages PTY subprocess lifecycle and tmux session coordination.
"""

import fcntl
import os
import pty
import signal
import struct
import subprocess
import termios
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple


# Debug logging function - can be set by the widget
_debug_log: Optional[Callable[[str, str], None]] = None


def set_debug_log(func: Callable[[str, str], None]) -> None:
    """Set the debug logging function."""
    global _debug_log
    _debug_log = func


def debug_log(message: str, level: str = "info") -> None:
    """Log a debug message."""
    if _debug_log:
        _debug_log(f"[Daedalus] {message}", level)
    else:
        print(f"[Daedalus] [{level}] {message}")


@dataclass
class Session:
    """Represents an active PTY session."""
    name: str
    pid: int
    fd: int
    cols: int
    rows: int
    tmux_session: str
    created_at: datetime


class PTYManager:
    """Manages PTY subprocesses and tmux session coordination."""

    def __init__(self):
        self.sessions: Dict[str, Session] = {}
        self._setup_sigchld_handler()

    def _setup_sigchld_handler(self) -> None:
        """Setup SIGCHLD handler for process cleanup."""
        # Don't override SIGCHLD - it interferes with subprocess.run
        # We'll handle cleanup differently
        pass

    def _handle_sigchld(self, signum, frame) -> None:
        """Handle SIGCHLD to clean up dead processes."""
        try:
            while True:
                pid, status = os.waitpid(-1, os.WNOHANG)
                if pid == 0:
                    break
                debug_log(f"SIGCHLD received for pid={pid}, status={status}", "warning")
                # Find and remove the dead session
                dead_sessions = [
                    name for name, session in self.sessions.items()
                    if session.pid == pid
                ]
                for name in dead_sessions:
                    debug_log(f"Removing dead session: {name}", "warning")
                    del self.sessions[name]
        except ChildProcessError:
            pass

        # Chain to original handler if it was a function
        if callable(self._original_sigchld):
            self._original_sigchld(signum, frame)

    @staticmethod
    def check_tmux_available() -> bool:
        """Check if tmux is installed and available."""
        try:
            result = subprocess.run(
                ["tmux", "-V"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def list_tmux_sessions(self) -> List[str]:
        """List existing daedalus-* tmux sessions."""
        try:
            result = subprocess.run(
                ["tmux", "list-sessions", "-F", "#{session_name}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return [
                    s.strip() for s in result.stdout.strip().split('\n')
                    if s.strip().startswith('daedalus-')
                ]
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return []

    def tmux_session_exists(self, session_name: str) -> bool:
        """Check if a specific tmux session exists."""
        try:
            result = subprocess.run(
                ["tmux", "has-session", "-t", session_name],
                capture_output=True,
                timeout=5
            )
            exists = result.returncode == 0
            debug_log(f"tmux_session_exists({session_name}): {exists}", "debug")
            return exists
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            debug_log(f"tmux_session_exists({session_name}) exception: {e}", "error")
            return False

    def spawn_session(
        self,
        name: str,
        command: str = "claude",
        cols: int = 120,
        rows: int = 40,
        working_dir: Optional[str] = None,
        enable_sidepanes: bool = True,
        lazygit_pane: bool = True,
        editor_pane: bool = True,
        editor_command: Optional[str] = None
    ) -> Optional[Session]:
        """
        Spawn Claude Code in a tmux session and attach via PTY.

        Args:
            name: Session name (will be prefixed with 'daedalus-' for tmux)
            command: Command to run (default: 'claude')
            cols: Terminal columns
            rows: Terminal rows
            working_dir: Working directory for the session
            enable_sidepanes: Enable additional panes (lazygit, editor)
            lazygit_pane: Add lazygit sidebar on the right
            editor_pane: Add text editor pane below Claude
            editor_command: Editor to use (default: $EDITOR or nvim)

        Returns:
            Session object if successful, None otherwise
        """
        # Clean session name for tmux
        tmux_session = f"daedalus-{name}" if not name.startswith("daedalus-") else name

        # Check if session already exists
        if tmux_session in self.sessions:
            return self.sessions[tmux_session]

        # Create tmux session if it doesn't exist
        if not self.tmux_session_exists(tmux_session):
            # Start claude directly via bash to ensure proper PATH
            # Using bash -l to get login shell environment, then exec claude
            shell_command = f"bash -l -c '{command}'"

            create_cmd = [
                "tmux", "new-session",
                "-d",  # Detached
                "-s", tmux_session,
                "-x", str(cols),
                "-y", str(rows),
            ]

            if working_dir and os.path.isdir(working_dir):
                create_cmd.extend(["-c", working_dir])

            create_cmd.append(shell_command)

            debug_log(f"Creating tmux session: {tmux_session}", "info")
            debug_log(f"Command: {' '.join(create_cmd)}", "debug")

            try:
                result = subprocess.run(
                    create_cmd,
                    capture_output=True,
                    timeout=10
                )
                debug_log(f"tmux create returncode: {result.returncode}", "debug")
                if result.stdout:
                    debug_log(f"tmux stdout: {result.stdout.decode()}", "debug")
                if result.stderr:
                    debug_log(f"tmux stderr: {result.stderr.decode()}", "debug")
                if result.returncode != 0:
                    debug_log(f"tmux create failed: {result.stderr.decode()}", "error")
                    return None
            except (FileNotFoundError, subprocess.TimeoutExpired) as e:
                debug_log(f"tmux create exception: {e}", "error")
                return None

            # Verify session was created (longer pause to let tmux and command initialize)
            time.sleep(0.5)

            # List all sessions for debugging
            list_result = subprocess.run(["tmux", "list-sessions"], capture_output=True, text=True, timeout=5)
            debug_log(f"All tmux sessions after create: {list_result.stdout.strip()}", "debug")

            if not self.tmux_session_exists(tmux_session):
                debug_log(f"tmux session {tmux_session} not found after creation", "error")
                return None

            debug_log(f"tmux session {tmux_session} created successfully", "success")

            # Create additional panes if enabled
            if enable_sidepanes:
                self._setup_sidepanes(
                    tmux_session,
                    working_dir,
                    lazygit_pane=lazygit_pane,
                    editor_pane=editor_pane,
                    editor_command=editor_command
                )

        # Attach to tmux session via PTY
        return self._attach_to_tmux(tmux_session, cols, rows)

    def _setup_sidepanes(
        self,
        tmux_session: str,
        working_dir: Optional[str],
        lazygit_pane: bool = True,
        editor_pane: bool = True,
        editor_command: Optional[str] = None
    ) -> None:
        """
        Setup additional panes in the tmux session.

        Layout:
        +------------------+----------+
        |                  |          |
        |  Claude Code     | lazygit  |
        |  (pane 0)        | (pane 2) |
        |                  |          |
        +------------------+          |
        |  Editor (pane 1) |          |
        +------------------+----------+

        Args:
            tmux_session: Name of the tmux session
            working_dir: Working directory for new panes
            lazygit_pane: Whether to create lazygit pane
            editor_pane: Whether to create editor pane
            editor_command: Editor command to run (default: $EDITOR or nvim)
        """
        # Determine working directory option
        wd_opts = ["-c", working_dir] if working_dir and os.path.isdir(working_dir) else []

        # First, create the lazygit pane on the right (horizontal split)
        # This creates pane 1 to the right of pane 0
        if lazygit_pane:
            try:
                # Split horizontally: creates new pane to the right, 25% width
                split_cmd = [
                    "tmux", "split-window",
                    "-t", f"{tmux_session}:0.0",  # Target pane 0
                    "-h",  # Horizontal split (side by side)
                    "-p", "25",  # 25% of width for lazygit
                    *wd_opts,
                    "lazygit"
                ]
                result = subprocess.run(split_cmd, capture_output=True, timeout=5)
                if result.returncode == 0:
                    debug_log(f"Created lazygit pane in {tmux_session}", "info")
                else:
                    debug_log(f"Failed to create lazygit pane: {result.stderr.decode()}", "warning")
            except (FileNotFoundError, subprocess.TimeoutExpired) as e:
                debug_log(f"lazygit pane exception: {e}", "warning")

        # Now create the shell pane below Claude (vertical split of pane 0)
        if editor_pane:
            try:
                # Just a plain bash shell - more reliable than complex TUI editors
                shell_cmd = "bash"

                # Split vertically: creates new pane below pane 0, 25% height
                split_cmd = [
                    "tmux", "split-window",
                    "-t", f"{tmux_session}:0.0",  # Target the Claude pane
                    "-v",  # Vertical split (stacked)
                    "-p", "25",  # 25% of height for shell
                    *wd_opts,
                    shell_cmd
                ]
                result = subprocess.run(split_cmd, capture_output=True, timeout=5)
                if result.returncode == 0:
                    debug_log(f"Created shell pane in {tmux_session}", "info")
                else:
                    debug_log(f"Failed to create shell pane: {result.stderr.decode()}", "warning")
            except (FileNotFoundError, subprocess.TimeoutExpired) as e:
                debug_log(f"shell pane exception: {e}", "warning")

        # Select the Claude pane (pane 0) to be active
        try:
            subprocess.run(
                ["tmux", "select-pane", "-t", f"{tmux_session}:0.0"],
                capture_output=True,
                timeout=5
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    def attach_existing(self, tmux_session: str) -> Optional[Session]:
        """
        Attach to an existing tmux session.

        Args:
            tmux_session: Name of the tmux session to attach to

        Returns:
            Session object if successful, None otherwise
        """
        if not self.tmux_session_exists(tmux_session):
            return None

        # Get current tmux window size
        cols, rows = self._get_tmux_size(tmux_session)
        return self._attach_to_tmux(tmux_session, cols, rows)

    def _attach_to_tmux(
        self,
        tmux_session: str,
        cols: int,
        rows: int
    ) -> Optional[Session]:
        """Internal method to attach to a tmux session via PTY."""
        debug_log(f"Attaching to tmux session: {tmux_session}", "info")

        # Verify session exists before attempting attach
        if not self.tmux_session_exists(tmux_session):
            debug_log(f"Session {tmux_session} does not exist, cannot attach", "error")
            return None

        debug_log(f"Session {tmux_session} verified to exist, forking PTY", "info")
        try:
            pid, fd = pty.fork()

            if pid == 0:
                # Child process - exec tmux attach
                # Small delay to ensure parent has set up fd
                import time
                time.sleep(0.1)
                # Debug: write pre-exec info to temp file
                try:
                    with open("/tmp/daedalus-child-debug.log", "w") as f:
                        f.write(f"Child process starting\n")
                        f.write(f"Target session: {tmux_session}\n")
                        import subprocess
                        result = subprocess.run(["tmux", "list-sessions"], capture_output=True, text=True)
                        f.write(f"tmux list-sessions:\n{result.stdout}\n{result.stderr}\n")
                        result = subprocess.run(["tmux", "has-session", "-t", tmux_session], capture_output=True, text=True)
                        f.write(f"has-session exit code: {result.returncode}\n")
                        f.write(f"has-session stderr: {result.stderr}\n")
                except Exception as e:
                    pass
                os.execlp("tmux", "tmux", "attach-session", "-t", tmux_session)
                # execlp doesn't return on success
                os._exit(1)
            else:
                debug_log(f"Forked child pid={pid}, fd={fd}", "debug")
                # Parent process - configure PTY
                self._set_nonblocking(fd)
                self._set_pty_size(fd, cols, rows)

                session = Session(
                    name=tmux_session,
                    pid=pid,
                    fd=fd,
                    cols=cols,
                    rows=rows,
                    tmux_session=tmux_session,
                    created_at=datetime.now()
                )
                self.sessions[tmux_session] = session
                return session

        except OSError:
            return None

    def _get_tmux_size(self, tmux_session: str) -> Tuple[int, int]:
        """Get the current size of a tmux session."""
        try:
            result = subprocess.run(
                ["tmux", "display-message", "-t", tmux_session, "-p", "#{window_width} #{window_height}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split()
                if len(parts) == 2:
                    return int(parts[0]), int(parts[1])
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
            pass
        return 120, 40  # Default

    @staticmethod
    def _set_nonblocking(fd: int) -> None:
        """Set file descriptor to non-blocking mode."""
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    @staticmethod
    def _set_pty_size(fd: int, cols: int, rows: int) -> None:
        """Set PTY terminal size."""
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

    def resize_session(self, name: str, cols: int, rows: int) -> bool:
        """
        Resize an active session.

        Args:
            name: Session name
            cols: New column count
            rows: New row count

        Returns:
            True if successful, False otherwise
        """
        session = self.sessions.get(name)
        if not session:
            return False

        try:
            # Resize PTY
            self._set_pty_size(session.fd, cols, rows)

            # Resize tmux session
            subprocess.run(
                ["tmux", "resize-window", "-t", session.tmux_session, "-x", str(cols), "-y", str(rows)],
                capture_output=True,
                timeout=5
            )

            session.cols = cols
            session.rows = rows
            return True

        except (OSError, subprocess.TimeoutExpired):
            return False

    def kill_session(self, name: str) -> bool:
        """
        Kill a session and clean up resources.

        Args:
            name: Session name to kill

        Returns:
            True if successful, False otherwise
        """
        session = self.sessions.get(name)
        if not session:
            return False

        try:
            # Close PTY fd
            try:
                os.close(session.fd)
            except OSError:
                pass

            # Kill the tmux attach process
            try:
                os.kill(session.pid, signal.SIGTERM)
            except OSError:
                pass

            # Optionally kill the tmux session itself
            # (commented out to preserve session for reattach)
            # subprocess.run(["tmux", "kill-session", "-t", session.tmux_session])

            del self.sessions[name]
            return True

        except Exception:
            return False

    def kill_tmux_session(self, tmux_session: str) -> bool:
        """Kill a tmux session entirely."""
        try:
            result = subprocess.run(
                ["tmux", "kill-session", "-t", tmux_session],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def detach_session(self, name: str) -> bool:
        """
        Detach from a session without killing the tmux session.

        Args:
            name: Session name to detach from

        Returns:
            True if successful, False otherwise
        """
        session = self.sessions.get(name)
        if not session:
            return False

        try:
            # Close PTY fd
            os.close(session.fd)

            # Kill the tmux attach process
            os.kill(session.pid, signal.SIGTERM)

            del self.sessions[name]
            return True

        except OSError:
            return False

    def get_session(self, name: str) -> Optional[Session]:
        """Get a session by name."""
        return self.sessions.get(name)

    def cleanup(self) -> None:
        """Clean up all sessions (call on shutdown)."""
        for name in list(self.sessions.keys()):
            self.detach_session(name)

        # Restore original SIGCHLD handler
        signal.signal(signal.SIGCHLD, self._original_sigchld or signal.SIG_DFL)
