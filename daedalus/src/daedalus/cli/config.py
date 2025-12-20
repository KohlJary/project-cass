"""
Daedalus CLI Configuration.

Contains configuration dataclass and tmux helper functions.
"""

import os
import subprocess
from dataclasses import dataclass
from typing import List


@dataclass
class DaedalusConfig:
    """Configuration for Daedalus workspace."""
    session_name: str = "daedalus"
    swarm_session: str = "icarus-swarm"
    project_dir: str = ""
    bus_root: str = "/tmp/icarus-bus"

    def __post_init__(self):
        if not self.project_dir:
            self.project_dir = os.getcwd()


def get_config() -> DaedalusConfig:
    """Load configuration from environment and defaults."""
    return DaedalusConfig(
        session_name=os.environ.get("DAEDALUS_SESSION", "daedalus"),
        swarm_session=os.environ.get("DAEDALUS_SWARM", "icarus-swarm"),
        project_dir=os.environ.get("DAEDALUS_PROJECT_DIR", os.getcwd()),
    )


# =============================================================================
# Tmux Helpers
# =============================================================================

def tmux_session_exists(session: str) -> bool:
    """Check if a tmux session exists."""
    result = subprocess.run(
        ["tmux", "has-session", "-t", session],
        capture_output=True
    )
    return result.returncode == 0


def tmux_run(cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a tmux command."""
    full_cmd = ["tmux"] + cmd
    return subprocess.run(full_cmd, capture_output=True, text=True, check=check)


def tmux_send_keys(target: str, keys: str, enter: bool = True) -> None:
    """Send keys to a tmux pane."""
    cmd = ["send-keys", "-t", target, keys]
    if enter:
        cmd.append("Enter")
    tmux_run(cmd)


def tmux_pane_count(session: str) -> int:
    """Get number of panes in a session."""
    result = tmux_run(["list-panes", "-t", session], check=False)
    if result.returncode != 0:
        return 0
    return len(result.stdout.strip().split("\n"))
