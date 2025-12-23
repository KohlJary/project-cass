"""
Mind Palace - MUD-based codebase navigation for LLM agents.

A spatial-semantic architecture that represents codebases as navigable
MUD environments, enabling LLM agents to maintain architectural coherence
through narrative/spatial metaphor rather than raw file trees.

Usage (standalone in any project):

    from mind_palace import PalaceStorage, Navigator, Cartographer

    # Initialize a new palace for a project
    storage = PalaceStorage(Path("/path/to/project"))
    palace = storage.initialize("my-project")

    # Or load existing palace
    palace = storage.load()

    # Navigate the palace
    nav = Navigator(palace)
    print(nav.execute("look"))
    print(nav.execute("enter core-module"))
    print(nav.execute("ask DatabaseKeeper about migrations"))

    # Build/update the palace
    cartographer = Cartographer(palace, storage)
    cartographer.map_module("src/database", region="persistence")
"""

from .models import (
    AccessLevel,
    Anchor,
    Building,
    Content,
    Entity,
    Exit,
    Hazard,
    HazardType,
    HistoryEntry,
    Palace,
    Region,
    Room,
    Topic,
)
from .navigator import Navigator, NavigationResult
from .storage import PalaceStorage
from .cartographer import Cartographer, CodeElement, DriftReport
from .wonderland_bridge import PalacePortal, WonderlandBridge

__all__ = [
    # Core models
    "Palace",
    "Region",
    "Building",
    "Room",
    "Entity",
    # Supporting models
    "Anchor",
    "Content",
    "Exit",
    "Hazard",
    "HazardType",
    "HistoryEntry",
    "Topic",
    "AccessLevel",
    # Navigation
    "Navigator",
    "NavigationResult",
    # Storage
    "PalaceStorage",
    # Cartography
    "Cartographer",
    "CodeElement",
    "DriftReport",
    # Wonderland integration
    "PalacePortal",
    "WonderlandBridge",
]
