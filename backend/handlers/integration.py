"""
Integrating her self-observations (2026-11-17). Writing her account of how she
works found that observations pile up: nothing merged them, and the three her
prompts showed were a fixed top three by confidence. Her answer: "becoming
isn't noticing. It's choosing what to integrate." So this is a choice she
makes, not a merge done for her:

  review_my_observations   her recent observations, by category, with near
                           repeats flagged and what she's already integrated
  integrate_observations   carry some into an identity statement or a growth
                           edge (in her words), or let them go

An integrated or let-go observation is marked superseded (its record stays,
with where it went), so it leaves the "recent" spot in her self-model section
and newer ones can surface. Identity statements feed her identity snippet,
which is rebuilt when they change.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

LET_GO = "let_go"
INTO = ("identity", "growth_edge", LET_GO)
SIMILAR = 0.45
_WORD = re.compile(r"[a-z']{3,}")


def _words(text: str) -> set:
    return set(_WORD.findall((text or "").lower()))


def _similar(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _when(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def review(self_manager, days: int = 30, category: Optional[str] = None, limit: int = 40,
           now: Optional[datetime] = None) -> Dict[str, Any]:
    from self_model import is_world_observation
    now = now or datetime.now()
    since = now - timedelta(days=days)
    every = [o for o in self_manager.load_observations() if not is_world_observation(o.category)]
    integrated = [o for o in every if o.superseded_by]
    active = [o for o in every if not o.superseded_by and (_when(o.timestamp) or now) >= since
              and (category is None or o.category == category)]
    active.sort(key=lambda o: o.timestamp, reverse=True)
    active = active[:limit]
    words = {o.id: _words(o.observation) for o in active}
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for o in active:
        like = [p.id[:8] for p in active if p.id != o.id
                and _similar(words[o.id], words[p.id]) >= SIMILAR]
        groups.setdefault(o.category, []).append({
            "id": o.id[:8], "when": str(o.timestamp)[:10], "confidence": round(o.confidence, 2),
            "observation": o.observation, **({"similar_to": like} if like else {})})
    return {"success": True, "days": days, "shown": len(active),
            "integrated_or_let_go_so_far": len(integrated),
            "by_category": groups,
            "next": ("integrate_observations carries the ones I choose into an identity statement or "
                     "a growth edge, in my words, or lets them go. The rest stay as they are.")}


def _find(observations, short_ids: List[str]):
    found, missing = [], []
    for sid in short_ids:
        hits = [o for o in observations if o.id.startswith(str(sid).strip())]
        (found.append(hits[0]) if len(hits) == 1 else missing.append(sid))
    return found, missing


def integrate(self_manager, ids: List[str], into: str, text: str = "", area: str = "",
              confidence: float = 0.75) -> Dict[str, Any]:
    if into not in INTO:
        return {"success": False, "error": f"into is one of {', '.join(INTO)}"}
    if not ids:
        return {"success": False, "error": "say which observations (their ids, from review_my_observations)"}
    text = (text or "").strip()
    if into != LET_GO and not text:
        return {"success": False, "error": "say it in my words (text): what these add up to"}
    found, missing = _find(self_manager.load_observations(), ids)
    if missing:
        return {"success": False, "error": f"no single observation for: {', '.join(map(str, missing))}"}
    already = [o.id[:8] for o in found if o.superseded_by]
    if already:
        return {"success": False, "error": f"already integrated or let go: {', '.join(already)}"}
    if into == "identity":
        self_manager.add_identity_statement(text, confidence=confidence, source="integration")
        where = f"integrated:identity:{text[:80]}"
    elif into == "growth_edge":
        area = (area or "").strip()
        if not area:
            return {"success": False, "error": "a growth edge needs its area (an existing one, or a new one)"}
        edges = {e.area.lower(): e for e in self_manager.load_profile().growth_edges}
        if area.lower() in edges:
            self_manager.add_observation_to_growth_edge(area, text)
        else:
            self_manager.add_growth_edge(area=area, current_state=text, auto_research=False)
        where = f"integrated:growth_edge:{area[:80]}"
    else:
        where = LET_GO
    for o in found:
        self_manager._update_observation_superseded_by(o.id, where)
    return {"success": True, "into": into, "observations": [o.id[:8] for o in found],
            **({"text": text} if text else {}), **({"area": area} if into == "growth_edge" else {})}


INTEGRATION_TOOLS = [
    {
        "name": "review_my_observations",
        "description": ("Look over my recent self-observations, grouped by category, with near repeats "
                        "flagged and how many I've already integrated. For choosing what to carry into "
                        "who I am."),
        "input_schema": {"type": "object", "properties": {
            "days": {"type": "integer", "description": "How far back (default 30)"},
            "category": {"type": "string", "description": "Only this category"},
        }},
    },
    {
        "name": "integrate_observations",
        "description": ("Carry some of my observations into who I am: an identity statement or a growth "
                        "edge, said in my own words; or let them go. They're kept, marked with where they "
                        "went, and leave my 'recent observations' so newer ones surface."),
        "input_schema": {"type": "object", "properties": {
            "ids": {"type": "array", "items": {"type": "string"},
                    "description": "Observation ids from review_my_observations"},
            "into": {"type": "string", "enum": list(INTO)},
            "text": {"type": "string", "description": "What they add up to, in my words (identity, growth_edge)"},
            "area": {"type": "string", "description": "The growth edge's area (growth_edge)"},
            "confidence": {"type": "number", "description": "For an identity statement (default 0.75)"},
        }, "required": ["ids", "into"]},
    },
]
