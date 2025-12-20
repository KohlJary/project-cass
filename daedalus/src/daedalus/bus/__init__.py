"""
Icarus Bus - File-based coordination for Daedalus/Icarus parallelization.

Provides work dispatch, status tracking, and result collection for
parallel Claude Code sessions.
"""

from .icarus_bus import (
    IcarusBus,
    IcarusInstance,
    WorkPackage,
    Request,
    Response,
    InstanceStatus,
    WorkStatus,
    RequestType,
    BUS_ROOT,
)

__all__ = [
    "IcarusBus",
    "IcarusInstance",
    "WorkPackage",
    "Request",
    "Response",
    "InstanceStatus",
    "WorkStatus",
    "RequestType",
    "BUS_ROOT",
]
