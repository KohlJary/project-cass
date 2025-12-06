"""
Terminal Output REST API routes
Endpoints for accessing Daedalus terminal output buffer
"""
import subprocess
import shutil
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from config import TMUX_SOCKET


router = APIRouter(prefix="/terminal", tags=["terminal"])

# Find tmux binary - systemd services may not have it in PATH
TMUX_BIN = shutil.which("tmux") or "/sbin/tmux"


# === Response Models ===

class OutputLinesResponse(BaseModel):
    """Response with output lines"""
    lines: List[str]
    count: int
    session: Optional[str] = None


class OutputRawResponse(BaseModel):
    """Response with raw output"""
    output: str
    char_count: int
    session: Optional[str] = None


class SearchResult(BaseModel):
    """A single search result"""
    line: str
    index: int
    timestamp: str


class SearchResponse(BaseModel):
    """Response with search results"""
    results: List[SearchResult]
    count: int
    pattern: str
    session: Optional[str] = None


class OutputStatsResponse(BaseModel):
    """Response with buffer statistics"""
    line_count: int
    char_count: int
    connected: bool
    session: Optional[str] = None


class TmuxSessionInfo(BaseModel):
    """Information about a tmux session"""
    name: str
    working_dir: Optional[str] = None
    created: Optional[str] = None
    attached: bool = False


class TmuxSessionsResponse(BaseModel):
    """Response with list of tmux sessions"""
    sessions: List[TmuxSessionInfo]
    count: int


# === Helper Functions ===

def get_tmux_socket() -> Optional[str]:
    """
    Get the tmux socket path.
    This is needed when running as a systemd service which may have
    a different /tmp namespace (PrivateTmp=yes).
    """
    import os
    import pwd

    # If explicitly configured, use that
    if TMUX_SOCKET:
        return TMUX_SOCKET

    uid = os.getuid()

    # When running as a systemd service with PrivateTmp=yes, /tmp is isolated.
    # We need to check if we're in that situation and look at the real /tmp.

    # Check both the local /tmp and the real system /tmp
    socket_candidates = [
        f"/tmp/tmux-{uid}/default",  # Normal location (works if not isolated)
    ]

    # Also check XDG_RUNTIME_DIR which persists across private tmp
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{uid}")
    socket_candidates.append(f"{runtime_dir}/tmux-default")

    # Try user's home-based socket
    try:
        home = pwd.getpwuid(uid).pw_dir
        socket_candidates.append(f"{home}/.tmux-default")
    except (KeyError, OSError):
        pass

    for socket_path in socket_candidates:
        if os.path.exists(socket_path):
            return socket_path

    # Last resort: if /tmp appears isolated (has systemd-private dirs),
    # the real socket is inaccessible. Return None and let tmux fail gracefully.
    return None


def get_daedalus_sessions() -> List[TmuxSessionInfo]:
    """Get all daedalus-* tmux sessions with their info"""
    try:
        # Build command, optionally with socket path
        cmd = [TMUX_BIN]
        socket = get_tmux_socket()
        if socket:
            cmd.extend(["-S", socket])
        cmd.extend([
            "list-sessions", "-F",
            "#{session_name}|#{pane_current_path}|#{session_created}|#{session_attached}"
        ])

        # Get session info including creation time and attached status
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            return []

        sessions = []
        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue
            parts = line.split('|')
            if len(parts) >= 1:
                name = parts[0].strip()
                if name.startswith('daedalus-'):
                    sessions.append(TmuxSessionInfo(
                        name=name,
                        working_dir=parts[1].strip() if len(parts) > 1 else None,
                        created=parts[2].strip() if len(parts) > 2 else None,
                        attached=parts[3].strip() == '1' if len(parts) > 3 else False
                    ))
        return sessions
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def capture_tmux_pane(session_name: str, lines: int = 100) -> str:
    """
    Capture visible content from a tmux pane.
    This provides a snapshot even without the TUI running.
    """
    try:
        cmd = [TMUX_BIN]
        socket = get_tmux_socket()
        if socket:
            cmd.extend(["-S", socket])
        cmd.extend(["capture-pane", "-t", session_name, "-p", "-S", f"-{lines}"])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout
        return ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


# === Endpoints ===

@router.get("/debug")
async def debug_tmux():
    """Debug endpoint to check tmux connectivity"""
    import os
    uid = os.getuid()
    socket = get_tmux_socket()

    # Try to run tmux directly
    cmd = [TMUX_BIN]
    if socket:
        cmd.extend(["-S", socket])
    cmd.extend(["list-sessions"])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

    # List /tmp contents to diagnose PrivateTmp issues
    tmp_contents = os.listdir("/tmp") if os.path.exists("/tmp") else []

    # Check if we're in a PrivateTmp namespace
    # If /tmp is empty or missing tmux-{uid}, we're likely in a private namespace
    private_tmp = f"tmux-{uid}" not in tmp_contents

    return {
        "uid": uid,
        "tmux_bin": TMUX_BIN,
        "configured_socket": TMUX_SOCKET,
        "resolved_socket": socket,
        "socket_exists": os.path.exists(socket) if socket else False,
        "private_tmp_detected": private_tmp,
        "tmp_contents": tmp_contents,
        "tmux_returncode": result.returncode,
        "tmux_stdout": result.stdout,
        "tmux_stderr": result.stderr,
        "fix_hint": "If socket doesn't exist and tmux fails, disable PrivateTmp: sudo mkdir -p /etc/systemd/system/cass-vessel.service.d/ && echo -e '[Service]\\nPrivateTmp=no' | sudo tee /etc/systemd/system/cass-vessel.service.d/tmux-access.conf && sudo systemctl daemon-reload && sudo systemctl restart cass-vessel",
    }


@router.get("/sessions", response_model=TmuxSessionsResponse)
async def list_sessions():
    """List all daedalus tmux sessions"""
    sessions = get_daedalus_sessions()
    return TmuxSessionsResponse(sessions=sessions, count=len(sessions))


@router.get("/capture/{session_name}", response_model=OutputRawResponse)
async def capture_session_output(
    session_name: str,
    lines: int = Query(default=100, ge=1, le=10000, description="Number of lines to capture")
):
    """
    Capture current visible output from a tmux session.
    This works even when the TUI is not connected to the session.
    """
    # Ensure it's a daedalus session
    if not session_name.startswith("daedalus-"):
        session_name = f"daedalus-{session_name}"

    # Check session exists
    sessions = get_daedalus_sessions()
    session_names = [s.name for s in sessions]
    if session_name not in session_names:
        raise HTTPException(status_code=404, detail=f"Session '{session_name}' not found")

    output = capture_tmux_pane(session_name, lines)
    return OutputRawResponse(
        output=output,
        char_count=len(output),
        session=session_name
    )


@router.get("/capture/{session_name}/search", response_model=SearchResponse)
async def search_session_output(
    session_name: str,
    pattern: str = Query(..., description="Search pattern (regex supported)"),
    lines: int = Query(default=500, ge=1, le=10000, description="Number of lines to search"),
    case_sensitive: bool = Query(default=False, description="Case-sensitive search")
):
    """
    Search captured output from a tmux session.
    """
    import re

    # Ensure it's a daedalus session
    if not session_name.startswith("daedalus-"):
        session_name = f"daedalus-{session_name}"

    # Check session exists
    sessions = get_daedalus_sessions()
    session_names = [s.name for s in sessions]
    if session_name not in session_names:
        raise HTTPException(status_code=404, detail=f"Session '{session_name}' not found")

    output = capture_tmux_pane(session_name, lines)

    # Compile regex
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        regex = re.compile(pattern, flags)
    except re.error:
        regex = re.compile(re.escape(pattern), flags)

    # Search lines
    from datetime import datetime
    results = []
    for i, line in enumerate(output.split('\n')):
        if regex.search(line):
            results.append(SearchResult(
                line=line,
                index=i,
                timestamp=datetime.now().isoformat()
            ))

    return SearchResponse(
        results=results,
        count=len(results),
        pattern=pattern,
        session=session_name
    )


@router.post("/send/{session_name}")
async def send_to_session(
    session_name: str,
    command: str = Query(..., description="Command or text to send")
):
    """
    Send a command to a tmux session.
    Note: This sends keys to the session, not executes a command.
    """
    # Ensure it's a daedalus session
    if not session_name.startswith("daedalus-"):
        session_name = f"daedalus-{session_name}"

    # Check session exists
    sessions = get_daedalus_sessions()
    session_names = [s.name for s in sessions]
    if session_name not in session_names:
        raise HTTPException(status_code=404, detail=f"Session '{session_name}' not found")

    try:
        cmd = [TMUX_BIN]
        socket = get_tmux_socket()
        if socket:
            cmd.extend(["-S", socket])
        cmd.extend(["send-keys", "-t", session_name, command])

        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=5
        )
        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to send keys: {result.stderr.decode()}"
            )
        return {"status": "sent", "session": session_name, "command": command}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Command timed out")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="tmux not found")
