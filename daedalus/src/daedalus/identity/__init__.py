"""
Daedalus Identity Framework

Provides identity documents (seeds, dialogues) for Icarus workers
and agent definitions for Claude Code integration.
"""

from .seed import (
    load_icarus_seed,
    load_icarus_dialogue,
    load_agent_definition,
    get_identity_data_path,
)

__all__ = [
    "load_icarus_seed",
    "load_icarus_dialogue",
    "load_agent_definition",
    "get_identity_data_path",
]
