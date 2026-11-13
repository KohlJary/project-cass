"""
When a recalled memory is from, and newer first among similar matches
(plan "Cass's memory", items 5110da04 and 32c8e38f).

Found 2026-11-13: her own self-observations from Oct 30 and Nov 1, written
when something really was unresolved, outranked the conversation that
resolved it the same day, and a session concluded it was still open.
Nothing stored changes: retrieval orders and labels what it returns.
"""
from __future__ import annotations

from typing import Dict, List, Optional

# Matches whose distances fall in the same band count as similar; within a
# band, the newer one comes first. Chroma's default (squared L2 on unit
# vectors) runs 0..4; 0.1 is a narrow band.
SIMILAR_BAND = 0.1


def date_of(metadata: Dict) -> Optional[str]:
    for key in ("timeframe_end", "timestamp", "journal_date", "created_at"):
        value = metadata.get(key)
        if value:
            return str(value)[:10]
    return None


def label(metadata: Dict) -> str:
    """"as of 2026-10-30" for her conclusions about herself; the date otherwise."""
    when = date_of(metadata)
    if not when:
        return ""
    kind = metadata.get("type") or ""
    return f"as of {when}" if kind in ("cass_self_observation", "user_observation", "cass_opinion") else when


def newer_first_among_similar(memories: List[Dict]) -> List[Dict]:
    """Closest first, by band; within a band, newest first; undated last."""
    by_date = sorted(memories, key=lambda m: date_of(m.get("metadata") or {}) or "", reverse=True)

    def band(m):
        d = m.get("distance")
        return round(d / SIMILAR_BAND) if isinstance(d, (int, float)) else 10**6
    return sorted(by_date, key=band)  # stable: keeps newest-first inside a band
