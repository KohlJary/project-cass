#!/usr/bin/env python3
"""
Daedalus CLI - Entry point.

Workspace orchestrator for parallel Claude Code sessions.

Usage:
    daedalus              # Attach to existing session or show status
    daedalus new          # Create new workspace
    daedalus status       # Show detailed status
    daedalus spawn N      # Spawn N Icarus workers
    daedalus dispatch     # Interactive work dispatch
    daedalus monitor      # Live monitoring view (future: full TUI)
"""

import argparse
import os
from pathlib import Path

from .config import get_config, tmux_session_exists
from .commands import Daedalus


def main():
    parser = argparse.ArgumentParser(
        description="Daedalus - Workspace orchestrator for parallel Claude sessions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  daedalus new              Create new workspace
  daedalus attach           Attach to existing workspace
  daedalus detach           Detach (leaves workspace running)
  daedalus exit             Terminate entire workspace
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

    # detach
    subparsers.add_parser("detach", help="Detach from workspace (leaves it running)")

    # exit
    subparsers.add_parser("exit", help="Terminate entire workspace")

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

    # bus (pass-through to icarus_bus CLI)
    bus_parser = subparsers.add_parser("bus", help="Direct bus commands")
    bus_parser.add_argument("bus_args", nargs=argparse.REMAINDER, help="Arguments for bus CLI")

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

    elif args.command == "detach":
        daedalus.detach()

    elif args.command == "exit":
        daedalus.exit_workspace()

    elif args.command == "dispatch":
        daedalus.dispatch_work(args.type, args.description, args.priority)

    elif args.command == "work":
        daedalus.list_work()

    elif args.command == "respond":
        daedalus.respond_to_request(args.request_id, args.decision, args.message)

    elif args.command == "monitor":
        daedalus.monitor()

    elif args.command == "bus":
        # Pass through to icarus_bus CLI
        from ..bus.icarus_bus import main as bus_main
        import sys
        # Replace sys.argv with bus args
        sys.argv = ["icarus-bus"] + args.bus_args
        bus_main()

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
