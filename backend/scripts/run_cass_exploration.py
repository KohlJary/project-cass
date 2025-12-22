#!/usr/bin/env python3
"""
Run Cass Exploration in Wonderland

This script runs Cass through an autonomous exploration of Wonderland,
using her real identity from the GlobalState bus. She explores, meets NPCs,
and records what she learns in PeopleDex.

The exploration log is saved for review.

Usage:
    python scripts/run_cass_exploration.py [--rooms N] [--npcs N] [--realm REALM]
"""

import asyncio
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables from .env (override=True to use .env over shell env)
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"), override=True)

from wonderland.session_controller import SessionController, ExplorationSession, SessionStatus
from wonderland.world import WonderlandWorld
from wonderland.integration import WonderlandPeopleDexBridge
from wonderland.mythology import create_all_realms


class ExplorationLogger:
    """Detailed logger for exploration events."""

    def __init__(self, log_file: str):
        self.log_file = log_file
        self.events = []
        self.start_time = datetime.now()

        # Create log directory if needed
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)

        # Write header
        with open(log_file, 'w') as f:
            f.write(f"# Cass Wonderland Exploration Log\n")
            f.write(f"## Started: {self.start_time.isoformat()}\n\n")
            f.write("---\n\n")

    def log(self, category: str, message: str, details: dict = None):
        """Log an event."""
        timestamp = datetime.now()
        elapsed = (timestamp - self.start_time).total_seconds()

        event = {
            "timestamp": timestamp.isoformat(),
            "elapsed_seconds": elapsed,
            "category": category,
            "message": message,
            "details": details or {}
        }
        self.events.append(event)

        # Append to file
        with open(self.log_file, 'a') as f:
            f.write(f"### [{elapsed:.1f}s] {category}\n\n")
            f.write(f"{message}\n\n")
            if details:
                f.write("```json\n")
                f.write(json.dumps(details, indent=2, default=str))
                f.write("\n```\n\n")
            f.write("---\n\n")

        # Also print to console
        print(f"[{elapsed:.1f}s] {category}: {message}")

    def finalize(self, summary: dict):
        """Write final summary."""
        with open(self.log_file, 'a') as f:
            f.write("## Summary\n\n")
            f.write("```json\n")
            f.write(json.dumps(summary, indent=2, default=str))
            f.write("\n```\n")


async def run_exploration(
    target_rooms: int = 5,
    target_npcs: int = 3,
    target_realm: str = None,
    max_steps: int = 30,
    log_dir: str = "data/wonderland/exploration_logs"
):
    """
    Run Cass through Wonderland exploration.

    Args:
        target_rooms: Number of rooms to visit
        target_npcs: Number of NPCs to greet/talk to
        target_realm: Specific realm to visit (e.g., "greek", "norse")
        max_steps: Maximum exploration steps
        log_dir: Directory for exploration logs
    """

    # Create log file
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_file = f"{log_dir}/exploration-{timestamp}.md"
    logger = ExplorationLogger(log_file)

    logger.log("INIT", "Starting Cass Wonderland exploration", {
        "target_rooms": target_rooms,
        "target_npcs": target_npcs,
        "target_realm": target_realm,
        "max_steps": max_steps
    })

    # Initialize world
    logger.log("WORLD", "Initializing Wonderland world")
    world = WonderlandWorld()

    # Initialize PeopleDex bridge
    logger.log("PEOPLEDEX", "Initializing PeopleDex bridge")
    pdex_bridge = WonderlandPeopleDexBridge()

    # Check initial NPC stubs
    if world.mythology_registry:
        npc_count = len(world.mythology_registry.npcs)
        logger.log("NPCS", f"Found {npc_count} NPCs in mythology registry")

        # Sync as stubs if not already done
        stats = pdex_bridge.sync_all_npcs(world, stub_only=True)
        logger.log("PEOPLEDEX", f"Synced NPC stubs", stats)

        # Get initial discovery progress
        progress = pdex_bridge.get_discovery_progress(world)
        logger.log("DISCOVERY", "Initial discovery progress", {
            "total_npcs": progress.get("total_npcs", 0),
            "discovered": progress.get("discovered", 0),
            "discovery_rate": f"{progress.get('discovery_rate', 0):.1%}"
        })

    # Initialize session controller
    logger.log("SESSION", "Initializing exploration session controller")
    controller = SessionController(world=world)

    # Determine goal preset
    if target_rooms >= 10:
        goal_preset = "VISIT_ROOMS_10"
    elif target_rooms >= 5:
        goal_preset = "VISIT_ROOMS_5"
    else:
        goal_preset = "VISIT_ROOMS_3"

    # Start session with Cass's identity
    # Using "cass" as the daemon_id to pull her identity from GlobalState
    logger.log("SESSION", f"Starting exploration session with goal: {goal_preset}")

    try:
        session = await controller.start_session(
            user_id="kohl",  # Session owner
            daemon_name="Cass",
            goal_preset=goal_preset,
            source_daemon_id="cass",  # Pull identity from real Cass
        )

        logger.log("SESSION", f"Session started: {session.session_id}", {
            "daemon_id": session.daemon_id,
            "current_room": session.current_room,
            "status": session.status.value
        })

    except Exception as e:
        logger.log("ERROR", f"Failed to start session: {e}")
        return

    # Monitor exploration (it runs as a background task)
    logger.log("MONITOR", "Monitoring exploration session...")

    last_event_count = 0
    last_rooms_count = 0
    step = 0
    max_idle_checks = 10
    idle_checks = 0

    while step < max_steps:
        step += 1
        await asyncio.sleep(3.0)  # Check every 3 seconds

        # Get current session state
        current_session = controller.get_session(session.session_id)
        if not current_session:
            logger.log("ERROR", "Session no longer exists")
            break

        # Check if session ended
        if current_session.status != SessionStatus.ACTIVE:
            logger.log("STATUS", f"Session status: {current_session.status.value}")
            break

        # Log new events
        if len(current_session.events) > last_event_count:
            for event in current_session.events[last_event_count:]:
                event_dict = event.to_dict() if hasattr(event, 'to_dict') else {
                    "type": event.event_type,
                    "location": event.location,
                    "description": event.description,
                    "thought": event.daemon_thought,
                }
                logger.log("EVENT", event.description or event.event_type, event_dict)

                # Check for NPC conversations
                if event.event_type in ("conversation_start", "npc_greet"):
                    logger.log("NPC_ENCOUNTER", f"Cass met an NPC in {event.location}")

            last_event_count = len(current_session.events)
            idle_checks = 0  # Reset idle counter on activity
        else:
            idle_checks += 1

        # Log room changes
        if len(current_session.rooms_visited) > last_rooms_count:
            new_rooms = list(current_session.rooms_visited)[last_rooms_count:]
            for room in new_rooms:
                logger.log("ROOM_VISITED", f"New room: {room}")
            last_rooms_count = len(current_session.rooms_visited)

        # Progress update every 10 checks
        if step % 10 == 0:
            logger.log("PROGRESS", f"Step {step}", {
                "rooms_visited": len(current_session.rooms_visited),
                "events": len(current_session.events),
                "current_room": current_session.current_room,
            })

        # Check for idle timeout
        if idle_checks >= max_idle_checks:
            logger.log("IDLE", "Session appears idle, ending")
            break

        # Check goals
        if len(current_session.rooms_visited) >= target_rooms:
            logger.log("GOAL", f"Visited {target_rooms}+ rooms!")
            npcs_met_count = len(current_session.npcs_met) if hasattr(current_session, 'npcs_met') else 0
            if npcs_met_count >= target_npcs:
                logger.log("GOAL", f"Met {target_npcs}+ NPCs!")
                break

    # Get final session state
    final_session = controller.get_session(session.session_id)

    # End session if still active
    if final_session and final_session.status == SessionStatus.ACTIVE:
        logger.log("SESSION", "Ending exploration session")
        try:
            await controller.end_session(session.session_id)
        except Exception as e:
            logger.log("WARN", f"Error ending session: {e}")

    # Get final discovery progress
    final_progress = pdex_bridge.get_discovery_progress(world)

    # Generate summary
    final_session = controller.get_session(session.session_id) or session
    summary = {
        "duration_seconds": (datetime.now() - logger.start_time).total_seconds(),
        "monitoring_steps": step,
        "rooms_visited": len(final_session.rooms_visited),
        "rooms_list": list(final_session.rooms_visited),
        "npcs_met": len(final_session.npcs_met) if hasattr(final_session, 'npcs_met') else 0,
        "events_count": len(final_session.events),
        "final_status": final_session.status.value,
        "final_room": final_session.current_room,
        "discovery_progress": {
            "total_npcs": final_progress.get("total_npcs", 0),
            "discovered": final_progress.get("discovered", 0),
            "fully_discovered": final_progress.get("fully_discovered", 0),
            "discovery_rate": f"{final_progress.get('discovery_rate', 0):.1%}"
        }
    }

    logger.log("COMPLETE", "Exploration complete", summary)
    logger.finalize(summary)

    print(f"\n{'='*60}")
    print(f"Exploration log saved to: {log_file}")
    print(f"{'='*60}")

    return summary


def main():
    parser = argparse.ArgumentParser(description="Run Cass Wonderland Exploration")
    parser.add_argument("--rooms", type=int, default=5, help="Target rooms to visit")
    parser.add_argument("--npcs", type=int, default=3, help="Target NPCs to greet")
    parser.add_argument("--realm", type=str, default=None, help="Specific realm to visit")
    parser.add_argument("--max-steps", type=int, default=30, help="Maximum exploration steps")

    args = parser.parse_args()

    summary = asyncio.run(run_exploration(
        target_rooms=args.rooms,
        target_npcs=args.npcs,
        target_realm=args.realm,
        max_steps=args.max_steps
    ))

    if summary:
        print(f"\nFinal Results:")
        print(f"  Rooms visited: {summary['rooms_visited']}")
        print(f"  NPCs met: {summary['npcs_met']}")
        print(f"  Discovery rate: {summary['discovery_progress']['discovery_rate']}")


if __name__ == "__main__":
    main()
