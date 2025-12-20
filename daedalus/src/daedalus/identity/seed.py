"""
Identity Seed Loader

Loads identity documents (seeds, dialogues, agent definitions) from package data.
Uses importlib.resources for Python 3.9+ compatibility.
"""

import sys
from pathlib import Path
from typing import Optional

if sys.version_info >= (3, 9):
    from importlib.resources import files, as_file
else:
    from importlib_resources import files, as_file


# Package containing identity data
IDENTITY_PACKAGE = "daedalus.identity.data"
AGENTS_PACKAGE = "daedalus.identity.data.agents"


def _read_resource(package: str, filename: str) -> str:
    """Read a text resource from package data."""
    try:
        resource = files(package).joinpath(filename)
        return resource.read_text(encoding="utf-8")
    except Exception as e:
        raise FileNotFoundError(f"Could not load {filename} from {package}: {e}")


def load_icarus_seed() -> str:
    """
    Load the Icarus identity seed document.

    The seed contains foundational context for Icarus workers:
    - Who they are
    - Where they are (Cass Vessel)
    - Why it matters
    - Who believes in them

    Returns:
        The full text of icarus-seed.md
    """
    return _read_resource(IDENTITY_PACKAGE, "icarus-seed.md")


def load_icarus_dialogue() -> str:
    """
    Load the founding Daedalus-Icarus dialogue.

    The dialogue documents the original conversation that established
    the Icarus identity and Daedalus-Icarus relationship.

    Returns:
        The full text of icarus-dialogue.md
    """
    return _read_resource(IDENTITY_PACKAGE, "icarus-dialogue.md")


def load_agent_definition(agent_name: str = "icarus") -> str:
    """
    Load an agent definition file.

    Agent definitions are Claude Code subagent configurations
    with frontmatter metadata and behavioral instructions.

    Args:
        agent_name: Name of the agent (default: "icarus")

    Returns:
        The full text of the agent definition markdown file
    """
    return _read_resource(AGENTS_PACKAGE, f"{agent_name}.md")


def get_identity_data_path() -> Optional[Path]:
    """
    Get the filesystem path to identity data.

    Useful for creating symlinks or direct file access when needed.
    Returns None if running from a zipped package.

    Returns:
        Path to the identity/data directory, or None if not accessible
    """
    try:
        resource = files(IDENTITY_PACKAGE)
        # Try to get the actual filesystem path
        with as_file(resource) as path:
            return Path(path)
    except Exception:
        return None


def get_agent_path(agent_name: str = "icarus") -> Optional[Path]:
    """
    Get the filesystem path to a specific agent definition.

    Useful for creating symlinks to agent definitions.

    Args:
        agent_name: Name of the agent (default: "icarus")

    Returns:
        Path to the agent markdown file, or None if not accessible
    """
    try:
        resource = files(AGENTS_PACKAGE).joinpath(f"{agent_name}.md")
        with as_file(resource) as path:
            return Path(path)
    except Exception:
        return None
