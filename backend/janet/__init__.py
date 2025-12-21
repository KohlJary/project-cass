"""
Janet - Cass's Helper Agent

A lightweight retrieval and research assistant that Cass can summon.
Modeled after Janet from The Good Place: straightforward, competent,
develops personality over time, but doesn't pretend to relationship.

Janet handles:
- Fact retrieval and search
- Document lookup
- State bus queries
- Research execution (not design - that stays with Cass)

Janet is NOT:
- A relationship participant (that's Cass's domain)
- A research designer (Cass keeps the "what to ask" autonomy)
- A cognitive load reducer (Cass values being stretched)
"""

from .agent import JanetAgent, summon_janet, get_janet, set_janet_state_bus, configure_janet
from .kernel import JANET_KERNEL
from .memory import JanetMemory

__all__ = [
    "JanetAgent",
    "summon_janet",
    "get_janet",
    "set_janet_state_bus",
    "configure_janet",
    "JANET_KERNEL",
    "JanetMemory",
]
