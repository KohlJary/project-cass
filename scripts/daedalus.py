#!/usr/bin/env python3
"""
Daedalus - Workspace orchestrator for parallel Claude Code sessions.

This is the command-line interface for managing Daedalus/Icarus workspaces.
Designed to grow into a full console application.

Usage:
    daedalus              # Attach to existing session or show status
    daedalus new          # Create new workspace
    daedalus status       # Show detailed status
    daedalus spawn N      # Spawn N Icarus workers
    daedalus dispatch     # Interactive work dispatch
    daedalus monitor      # Live monitoring view (future: full TUI)
"""

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.icarus_bus import IcarusBus, WorkPackage, InstanceStatus, RequestType, Response


# =============================================================================
# Configuration
# =============================================================================

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


# =============================================================================
# Core Commands
# =============================================================================

class Daedalus:
    """Main orchestrator class."""

    def __init__(self, config: DaedalusConfig = None):
        self.config = config or get_config()
        self.bus = IcarusBus()

    # -------------------------------------------------------------------------
    # Session Management
    # -------------------------------------------------------------------------

    def create_workspace(self) -> bool:
        """Create new Daedalus workspace with full layout."""
        cfg = self.config

        if tmux_session_exists(cfg.session_name):
            print(f"Session '{cfg.session_name}' already exists.")
            print(f"Use: daedalus attach")
            return False

        print(f"Creating Daedalus workspace...")

        # Initialize the bus
        self.bus.initialize()
        print(f"  Bus initialized at {self.bus.root}")

        # Create swarm session first
        self._create_swarm_session()

        # Create main session
        tmux_run([
            "new-session", "-d",
            "-s", cfg.session_name,
            "-c", cfg.project_dir,
            "-x", "200", "-y", "50"
        ])

        # Split for lazygit at bottom (25% height)
        tmux_run(["split-window", "-t", cfg.session_name, "-v", "-p", "25", "-c", cfg.project_dir])
        tmux_send_keys(f"{cfg.session_name}:0.1", "lazygit")

        # Select top pane and split for Icarus swarm (60% width on right)
        tmux_run(["select-pane", "-t", f"{cfg.session_name}:0.0"])
        tmux_run(["split-window", "-t", cfg.session_name, "-h", "-p", "60", "-c", cfg.project_dir])

        # Right pane - attach to swarm session
        tmux_send_keys(
            f"{cfg.session_name}:0.1",
            f"tmux attach -t {cfg.swarm_session}"
        )

        # Left pane - start Claude for Daedalus
        tmux_run(["select-pane", "-t", f"{cfg.session_name}:0.0"])
        tmux_send_keys(f"{cfg.session_name}:0.0", "claude")

        print(f"  Workspace created!")
        print(f"  Layout: Daedalus (left) | Icarus Swarm (right) | lazygit (bottom)")

        return True

    def _create_swarm_session(self) -> None:
        """Create the Icarus swarm session."""
        cfg = self.config

        if tmux_session_exists(cfg.swarm_session):
            print(f"  Swarm session already exists")
            return

        tmux_run([
            "new-session", "-d",
            "-s", cfg.swarm_session,
            "-c", cfg.project_dir
        ])
        tmux_send_keys(
            cfg.swarm_session,
            "echo 'Icarus Swarm ready. Workers will appear here.'"
        )
        print(f"  Swarm session created: {cfg.swarm_session}")

    def attach(self) -> None:
        """Attach to existing Daedalus session."""
        cfg = self.config

        if not tmux_session_exists(cfg.session_name):
            print(f"No session '{cfg.session_name}' found.")
            print("Run: daedalus new")
            return

        os.execvp("tmux", ["tmux", "attach", "-t", cfg.session_name])

    def status(self) -> None:
        """Show detailed workspace status."""
        cfg = self.config

        print("=" * 60)
        print("  DAEDALUS WORKSPACE STATUS")
        print("=" * 60)
        print()

        # Session status
        main_active = tmux_session_exists(cfg.session_name)
        swarm_active = tmux_session_exists(cfg.swarm_session)

        print("Sessions:")
        status_str = "\033[92mactive\033[0m" if main_active else "\033[93mnot running\033[0m"
        print(f"  Main ({cfg.session_name}): {status_str}")

        status_str = "\033[92mactive\033[0m" if swarm_active else "\033[93mnot running\033[0m"
        swarm_panes = tmux_pane_count(cfg.swarm_session) if swarm_active else 0
        print(f"  Swarm ({cfg.swarm_session}): {status_str} ({swarm_panes} panes)")

        print()

        # Bus status
        print("Icarus Bus:")
        if self.bus.is_initialized():
            summary = self.bus.status_summary()
            inst = summary["instances"]
            work = summary["work"]
            reqs = summary["requests"]

            print(f"  Instances: {inst['total']} total")
            if inst["total"] > 0:
                for status, count in inst["by_status"].items():
                    if count > 0:
                        print(f"    - {status}: {count}")

            print(f"  Work: {work['pending']} pending, {work['claimed']} in progress, {work['completed']} done")
            print(f"  Requests: {reqs['pending']} pending")
        else:
            print("  Not initialized")

        print()

        # Pending requests that need attention
        if self.bus.is_initialized():
            requests = self.bus.list_pending_requests()
            if requests:
                print("\033[93mPending Requests (need attention):\033[0m")
                for req in requests:
                    print(f"  [{req.type.value}] {req.message[:60]}")
                    print(f"    From: {req.instance_id} | ID: {req.id}")

    # -------------------------------------------------------------------------
    # Worker Management
    # -------------------------------------------------------------------------

    def spawn_workers(self, count: int = 1) -> None:
        """Spawn Icarus workers in the swarm."""
        cfg = self.config

        if not tmux_session_exists(cfg.swarm_session):
            print("Swarm session not found. Creating...")
            self._create_swarm_session()

        print(f"Spawning {count} Icarus worker(s)...")

        current_panes = tmux_pane_count(cfg.swarm_session)

        for i in range(count):
            if i == 0 and current_panes == 1:
                # First worker uses existing pane if it's the only one
                # Check if it's just the welcome message
                tmux_send_keys(f"{cfg.swarm_session}:0.0", "claude")
            else:
                # Create new pane
                tmux_run(["split-window", "-t", cfg.swarm_session, "-c", cfg.project_dir])
                tmux_send_keys(cfg.swarm_session, "claude")
                # Re-tile
                tmux_run(["select-layout", "-t", cfg.swarm_session, "tiled"])

        # Final tiling
        tmux_run(["select-layout", "-t", cfg.swarm_session, "tiled"])

        final_panes = tmux_pane_count(cfg.swarm_session)
        print(f"  Spawned {count} worker(s). Total panes: {final_panes}")

    def kill_swarm(self) -> None:
        """Kill all Icarus workers."""
        cfg = self.config

        if not tmux_session_exists(cfg.swarm_session):
            print("Swarm session not found.")
            return

        tmux_run(["kill-session", "-t", cfg.swarm_session], check=False)
        print("Swarm session terminated.")

    # -------------------------------------------------------------------------
    # Work Management
    # -------------------------------------------------------------------------

    def dispatch_work(self, work_type: str, description: str, priority: int = 5) -> str:
        """Dispatch a work package to the queue."""
        if not self.bus.is_initialized():
            self.bus.initialize()

        work = WorkPackage(
            id="",
            type=work_type,
            description=description,
            inputs={},
            outputs={},
            priority=priority,
        )
        work_id = self.bus.post_work(work)
        print(f"Dispatched: {work_id}")
        print(f"  Type: {work_type}")
        print(f"  Priority: {priority}")
        print(f"  Description: {description[:80]}")
        return work_id

    def list_work(self) -> None:
        """List all work packages."""
        if not self.bus.is_initialized():
            print("Bus not initialized.")
            return

        pending = self.bus.list_pending_work()
        claimed = self.bus.list_claimed_work()
        results = self.bus.collect_results(clear=False)

        print("Pending Work:")
        if pending:
            for w in pending:
                print(f"  [{w.priority}] {w.id}: {w.description[:50]}")
        else:
            print("  (none)")

        print("\nIn Progress:")
        if claimed:
            for w in claimed:
                print(f"  {w.id}: {w.claimed_by} - {w.description[:50]}")
        else:
            print("  (none)")

        print("\nCompleted:")
        if results:
            for r in results:
                status = "OK" if r["result"].get("success") else "FAIL"
                print(f"  {r['work_id']}: [{status}] {r['instance_id']}")
        else:
            print("  (none)")

    def respond_to_request(self, request_id: str, decision: str, message: str) -> None:
        """Respond to a pending request."""
        response = Response(
            request_id=request_id,
            decision=decision,
            message=message,
        )
        self.bus.respond_to_request(request_id, response)
        print(f"Responded to {request_id}: {decision}")

    # -------------------------------------------------------------------------
    # Monitoring (placeholder for future TUI)
    # -------------------------------------------------------------------------

    def monitor(self) -> None:
        """
        Live monitoring view.

        TODO: Expand this into a full Textual TUI with:
        - Real-time instance status
        - Work queue visualization
        - Stream output from workers
        - Interactive request handling
        """
        print("Monitor mode - press Ctrl+C to exit")
        print("(Future: full TUI with Textual)")
        print()

        import time
        try:
            while True:
                # Clear screen
                print("\033[2J\033[H", end="")
                self.status()
                print()
                print("Refreshing in 2s... (Ctrl+C to exit)")
                time.sleep(2)
        except KeyboardInterrupt:
            print("\nExiting monitor.")


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Daedalus - Workspace orchestrator for parallel Claude sessions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  daedalus new              Create new workspace
  daedalus attach           Attach to existing workspace
  daedalus spawn 3          Spawn 3 Icarus workers
  daedalus status           Show workspace status
  daedalus dispatch impl "Build feature X"
  daedalus work             List all work packages
  daedalus monitor          Live monitoring view
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # new
    subparsers.add_parser("new", help="Create new Daedalus workspace")

    # attach
    subparsers.add_parser("attach", help="Attach to existing workspace")

    # status
    subparsers.add_parser("status", help="Show workspace status")

    # spawn
    spawn_parser = subparsers.add_parser("spawn", help="Spawn Icarus workers")
    spawn_parser.add_argument("count", type=int, nargs="?", default=1, help="Number of workers")

    # kill-swarm
    subparsers.add_parser("kill-swarm", help="Kill all Icarus workers")

    # dispatch
    dispatch_parser = subparsers.add_parser("dispatch", help="Dispatch work package")
    dispatch_parser.add_argument("type", help="Work type (impl, refactor, test, research)")
    dispatch_parser.add_argument("description", help="Work description")
    dispatch_parser.add_argument("--priority", "-p", type=int, default=5, help="Priority 1-10")

    # work
    subparsers.add_parser("work", help="List work packages")

    # respond
    respond_parser = subparsers.add_parser("respond", help="Respond to request")
    respond_parser.add_argument("request_id", help="Request ID")
    respond_parser.add_argument("decision", help="Decision (approved, denied, etc)")
    respond_parser.add_argument("message", help="Response message")

    # monitor
    subparsers.add_parser("monitor", help="Live monitoring view")

    # bus (pass-through to icarus_bus.py)
    bus_parser = subparsers.add_parser("bus", help="Direct bus commands")
    bus_parser.add_argument("bus_args", nargs=argparse.REMAINDER, help="Arguments for icarus_bus.py")

    args = parser.parse_args()
    daedalus = Daedalus()

    if args.command == "new":
        if daedalus.create_workspace():
            daedalus.attach()

    elif args.command == "attach":
        daedalus.attach()

    elif args.command == "status":
        daedalus.status()

    elif args.command == "spawn":
        daedalus.spawn_workers(args.count)

    elif args.command == "kill-swarm":
        daedalus.kill_swarm()

    elif args.command == "dispatch":
        daedalus.dispatch_work(args.type, args.description, args.priority)

    elif args.command == "work":
        daedalus.list_work()

    elif args.command == "respond":
        daedalus.respond_to_request(args.request_id, args.decision, args.message)

    elif args.command == "monitor":
        daedalus.monitor()

    elif args.command == "bus":
        # Pass through to icarus_bus.py
        bus_script = Path(__file__).parent / "icarus_bus.py"
        os.execvp("python3", ["python3", str(bus_script)] + args.bus_args)

    elif args.command is None:
        # Default: attach if exists, otherwise show status
        cfg = get_config()
        if tmux_session_exists(cfg.session_name):
            daedalus.attach()
        else:
            daedalus.status()
            print()
            print("No active session. Run: daedalus new")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
