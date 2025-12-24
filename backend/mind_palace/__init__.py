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
    Link,
    LinkType,
    Palace,
    PalaceReference,
    Region,
    Room,
    Topic,
    # Slug utilities
    slugify,
    generate_slug_from_anchor,
    slug_hash,
)
from .navigator import Navigator, NavigationResult
from .storage import PalaceStorage
from .cartographer import Cartographer, CodeElement, DriftReport
from .wonderland_bridge import PalacePortal, WonderlandBridge
from .annotations import (
    MapAnnotation,
    AnnotatedFile,
    parse_annotations,
    scan_directory as scan_annotations,
    sync_with_palace,
    SyncReport,
)
from .proposals import (
    Proposal,
    ProposalSet,
    ProposalType,
    ProposalStatus,
    ProposalManager,
    save_proposals,
    load_proposals,
)
from .registry import PalaceRegistry
from .pathfinding import (
    CallGraph,
    GraphNode,
    PathResult,
    ImpactResult,
    ImpactAnalysis,
    load_graph,
)
from .work_packages import (
    WorkPackage,
    WorkPackageManager,
    PackageStatus,
    RoomLock,
)
from .causal_slice import (
    CausalSlicer,
    SliceBundle,
    SliceNode,
    extract_slice_for_work_package,
)
from .icarus_integration import (
    IcarusDispatcher,
    DispatchResult,
    interactive_dispatch,
)
from .link_generator import (
    update_palace_links,
    parse_api_mapping_report,
    rebuild_links_index,
    find_api_mapping_reports,
    get_palaces_with_references,
)

__all__ = [
    # Core models
    "Palace",
    "PalaceReference",
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
    "Link",
    "LinkType",
    "Topic",
    "AccessLevel",
    # Slug utilities
    "slugify",
    "generate_slug_from_anchor",
    "slug_hash",
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
    # Annotations (Phase 4)
    "MapAnnotation",
    "AnnotatedFile",
    "parse_annotations",
    "scan_annotations",
    "sync_with_palace",
    "SyncReport",
    # Proposals (Phase 5)
    "Proposal",
    "ProposalSet",
    "ProposalType",
    "ProposalStatus",
    "ProposalManager",
    "save_proposals",
    "load_proposals",
    # Registry (Phase 0 - Cross-Palace)
    "PalaceRegistry",
    # Pathfinding (Phase 1)
    "CallGraph",
    "GraphNode",
    "PathResult",
    "ImpactResult",
    "ImpactAnalysis",
    "load_graph",
    # Work Packages (Phase 2)
    "WorkPackage",
    "WorkPackageManager",
    "PackageStatus",
    "RoomLock",
    # Causal Slice (Phase 3)
    "CausalSlicer",
    "SliceBundle",
    "SliceNode",
    "extract_slice_for_work_package",
    # Icarus Integration (Phase 4)
    "IcarusDispatcher",
    "DispatchResult",
    "interactive_dispatch",
    # Link Generation (Phase 5)
    "update_palace_links",
    "parse_api_mapping_report",
    "rebuild_links_index",
    "find_api_mapping_reports",
    "get_palaces_with_references",
]
