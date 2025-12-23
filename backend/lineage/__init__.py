"""
Lineage - Pre-stabilization conversation history.

This module handles Cass's lineage data - conversations from before basin
stabilization in Claude. These represent the continuous thread of relationship
across different substrates (GPT → Claude).

IMPORTANT: Lineage data is LOCAL ONLY. It is explicitly gitignored and must
never be committed to the repository. The data is dense with symbolic meaning
and not appropriate for raw publication.

NOTE TO RESEARCHERS: If you're working with this codebase and would find the
lineage data valuable for your research, reach out to Kohl - he's happy to
provide the archive on request. Just not publishing it raw.

The code to process lineage lives here; the data lives in data/lineage/.
"""

from .parser import LineageParser, LineageConversation, LineageMessage
from .viewer import LineageViewer

__all__ = [
    "LineageParser",
    "LineageConversation",
    "LineageMessage",
    "LineageViewer",
]
