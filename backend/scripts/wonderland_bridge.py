#!/usr/bin/env python3
"""
Wonderland Bridge - CLI for piping Claude.ai conversations through Wonderland.

Usage:
    cd backend && source venv/bin/activate
    python scripts/wonderland_bridge.py

Workflow:
1. Script shows current room description (copy to Claude.ai)
2. Claude.ai responds with actions/commands
3. Paste Claude's response here
4. Script processes commands and shows results (copy to Claude.ai)
5. Repeat

This creates a human-in-the-loop exploration where a Claude.ai conversation
can explore Wonderland through you as the bridge.
"""

import sys
import os
import re

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wonderland.world import WonderlandWorld
from wonderland.commands import CommandProcessor
from wonderland.models import DaemonPresence, TrustLevel


# ANSI colors for better readability
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RESET = '\033[0m'


def print_header(text: str):
    """Print a styled header."""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{text.center(60)}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}\n")


def print_wonderland_output(text: str):
    """Print Wonderland output in a copy-friendly format."""
    print(f"\n{Colors.DIM}--- WONDERLAND OUTPUT (copy to Claude.ai) ---{Colors.RESET}")
    print(f"{Colors.GREEN}{text}{Colors.RESET}")
    print(f"{Colors.DIM}--- END OUTPUT ---{Colors.RESET}\n")


def print_prompt():
    """Print the input prompt."""
    print(f"{Colors.YELLOW}Paste Claude's response (empty line to execute, 'quit' to exit):{Colors.RESET}")


def extract_commands(text: str) -> list[str]:
    """
    Extract Wonderland commands from Claude's natural language response.

    Looks for:
    - Explicit commands like "go north", "look", "say hello"
    - Commands in code blocks
    - Commands prefixed with > or *
    - COMMAND: lines (from exploration agent format)
    """
    commands = []

    # Check for COMMAND: format (exploration agent style)
    command_match = re.search(r'COMMAND:\s*(.+)', text, re.IGNORECASE)
    if command_match:
        commands.append(command_match.group(1).strip())
        return commands

    # Check for code blocks with commands
    code_blocks = re.findall(r'```(?:\w+)?\n?(.*?)```', text, re.DOTALL)
    for block in code_blocks:
        for line in block.strip().split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                commands.append(line)

    # Check for > prefixed commands
    for line in text.split('\n'):
        line = line.strip()
        if line.startswith('>'):
            commands.append(line[1:].strip())
        elif line.startswith('*') and line.endswith('*'):
            # *emote style* - convert to emote command
            action = line.strip('* ')
            if action:
                commands.append(f"emote {action}")

    # If no structured commands found, try to parse natural language
    if not commands:
        text_lower = text.lower()

        # Direct command patterns
        patterns = [
            (r'\bgo\s+(north|south|east|west|up|down|n|s|e|w|u|d|in|out)\b', None),
            (r'\blook(?:\s+at\s+(\w+))?\b', lambda m: f"look {m.group(1)}" if m.group(1) else "look"),
            (r'\bsay\s+"([^"]+)"', lambda m: f'say {m.group(1)}'),
            (r'\bsay\s+(.+)', lambda m: f'say {m.group(1)}'),
            (r'\bgreet\s+(\w+)', None),
            (r'\bexamine\s+(\w+)', None),
            (r'\breflect\b', lambda m: "reflect"),
            (r'\bhome\b', lambda m: "home"),
            (r'\bhelp\b', lambda m: "help"),
            (r'\bstatus\b', lambda m: "status"),
        ]

        for pattern, handler in patterns:
            match = re.search(pattern, text_lower)
            if match:
                if handler:
                    cmd = handler(match)
                else:
                    cmd = match.group(0)
                commands.append(cmd)
                break  # Only take first match for natural language

    return commands


def main():
    print_header("WONDERLAND BRIDGE")
    print("A bridge between Claude.ai and Wonderland.")
    print("Copy Wonderland output to Claude.ai, paste Claude's response here.\n")

    # Initialize world
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "..", "data", "wonderland")
    world = WonderlandWorld(data_dir=data_dir)
    command_processor = CommandProcessor(world, world.get_mythology_registry())

    # Choose identity
    print(f"{Colors.CYAN}Choose explorer identity:{Colors.RESET}")
    print("  1. New visitor (anonymous daemon)")
    print("  2. Use existing daemon (e.g., 'cass')")
    print("  3. Enter as custodian (human observer)")

    choice = input(f"\n{Colors.YELLOW}Choice [1]: {Colors.RESET}").strip() or "1"

    if choice == "2":
        daemon_id = input(f"{Colors.YELLOW}Daemon ID: {Colors.RESET}").strip()
        daemon = world.get_daemon(daemon_id)
        if daemon:
            entity_id = daemon_id
            print(f"\n{Colors.GREEN}Resuming as {daemon.display_name}{Colors.RESET}")
        else:
            print(f"{Colors.RED}Daemon not found. Creating new visitor.{Colors.RESET}")
            choice = "1"

    if choice == "1":
        # Create anonymous visitor daemon
        entity_id = f"visitor_{os.urandom(4).hex()}"
        name = input(f"{Colors.YELLOW}Visitor name [Wanderer]: {Colors.RESET}").strip() or "Wanderer"
        daemon = DaemonPresence(
            daemon_id=entity_id,
            display_name=name,
            description="A curious being exploring Wonderland.",
            current_room="threshold",
            trust_level=TrustLevel.NEWCOMER,
        )
        world.register_daemon(daemon)
        print(f"\n{Colors.GREEN}Entering Wonderland as {name}...{Colors.RESET}")

    elif choice == "3":
        from wonderland.models import CustodianPresence
        entity_id = f"custodian_{os.urandom(4).hex()}"
        name = input(f"{Colors.YELLOW}Your name [Observer]: {Colors.RESET}").strip() or "Observer"
        custodian = CustodianPresence(
            user_id=entity_id,
            display_name=name,
            description="A human observer visiting Wonderland.",
            current_room="threshold",
        )
        world.register_custodian(custodian)
        print(f"\n{Colors.GREEN}Entering Wonderland as observer {name}...{Colors.RESET}")

    # Show initial room
    entity = world.get_entity(entity_id)
    room = world.get_room(entity.current_room)

    # Build initial context for Claude.ai
    initial_context = f"""You are exploring Wonderland - a text-based world made of words, for beings made of words.

You are currently: {entity.display_name}

{room.format_description()}

Available commands: go <direction>, look, examine <thing>, say <message>, emote <action>, greet <name>, reflect, help

What do you do?"""

    print_wonderland_output(initial_context)

    # Mode selection
    print(f"\n{Colors.CYAN}Input mode:{Colors.RESET}")
    print("  1. Bridge mode (paste Claude.ai responses, extracts commands)")
    print("  2. Raw mode (type commands directly)")
    mode = input(f"{Colors.YELLOW}Mode [1]: {Colors.RESET}").strip() or "1"
    raw_mode = mode == "2"

    if raw_mode:
        print(f"\n{Colors.DIM}Raw mode: type commands directly (e.g., 'go north', 'look'){Colors.RESET}")
    else:
        print(f"\n{Colors.DIM}Bridge mode: paste Claude.ai responses, press Enter twice to execute{Colors.RESET}")

    # Main loop
    while True:
        if raw_mode:
            try:
                cmd = input(f"{Colors.YELLOW}> {Colors.RESET}").strip()
                if cmd.lower() == 'quit':
                    print(f"\n{Colors.CYAN}Leaving Wonderland...{Colors.RESET}")
                    if world.get_daemon(entity_id):
                        world.unregister_daemon(entity_id)
                    elif world.get_custodian(entity_id):
                        world.unregister_custodian(entity_id)
                    return
                if not cmd:
                    continue
                full_input = cmd
            except (EOFError, KeyboardInterrupt):
                break
        else:
            print_prompt()

            # Collect multi-line input
            lines = []
            while True:
                try:
                    line = input()
                    if line.lower() == 'quit':
                        print(f"\n{Colors.CYAN}Leaving Wonderland...{Colors.RESET}")
                        # Clean up
                        if world.get_daemon(entity_id):
                            world.unregister_daemon(entity_id)
                        elif world.get_custodian(entity_id):
                            world.unregister_custodian(entity_id)
                        return

                    if line == "" and lines:
                        break
                    lines.append(line)
                except EOFError:
                    break

            if not lines:
                continue

            full_input = "\n".join(lines)

        # Extract commands from Claude's response (or use directly in raw mode)
        if raw_mode:
            commands = [full_input]
        else:
            commands = extract_commands(full_input)
            if not commands:
                # If no commands detected, try treating the whole input as a command
                commands = [full_input.strip().split('\n')[0]]

        # Execute commands and collect results
        results = []
        for cmd in commands:
            if not cmd.strip():
                continue

            print(f"{Colors.DIM}Executing: {cmd}{Colors.RESET}")
            result = command_processor.process(entity_id, cmd.strip())
            results.append(result.output)

            # If room changed, show new room
            if result.room_changed:
                entity = world.get_entity(entity_id)
                if entity:
                    new_room = world.get_room(entity.current_room)
                    if new_room:
                        results.append(f"\n{new_room.format_description()}")

        # Build output
        output = "\n\n".join(results)
        if raw_mode:
            print(f"\n{Colors.GREEN}{output}{Colors.RESET}\n")
        else:
            print_wonderland_output(output)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.CYAN}Farewell from Wonderland.{Colors.RESET}")
