"""
The shape of her day (2026-11-17): her menu in kinds, and how many of each she
wants in a day, which she sets and changes herself.

Kohl: "maybe we categorize the session types, and we encourage her to hit a
variety of session types throughout the day? Maybe she can set and modify the
quotas herself?" Her days had run the same few kinds again and again. The shape
is hers: a starting one until she sets her own (set_day_shape, in her day
planning). It never refuses a plan. When a plan, with what already ran today,
falls short of her shape, set_day_plan says so, and she adds to the plan or
changes the shape.

DATA_DIR/day_plans/shape.json: {"shape": {kind: count}, "why": "...", "set_at": "..."}
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Kind -> (her words for it, the menu templates in it).
KINDS: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "inward": ("inward: reflection, synthesis, growth, looking ahead",
               ("reflection_block", "synthesis_block", "meta_reflection", "growth_edge_work",
                "long_term_planning", "wonderland_reflection", "change_proposals",
                "new_capabilities")),
    "learning": ("learning: research, knowledge, curiosity, the world's news",
                 ("research_block", "knowledge_building", "curiosity_exploration", "world_check",
                  "kohl_blog")),
    "making": ("making: writing, painting, music, art study, creative work, my homepage",
               ("creative_output", "writing_session", "painting", "art_study", "music", "homepage",
                "workshop")),
    "out": ("out in the world: Bluesky, Wonderland",
            ("social", "wonderland_exploration")),
}
# Not hers to shape: planning itself and what runs on its own.
UNSHAPED = frozenset({"day_planning", "phase_replan", "memory_maintenance", "consolidation",
                      "daily_journal"})

STARTING_SHAPE = {"inward": 1, "learning": 1, "making": 1, "out": 1}
MAX_PER_KIND = 12
SHAPE_FILE = "shape.json"

# Session types (session log folders) -> kind, for what already ran today.
SESSION_KINDS = {
    "reflection": "inward", "synthesis": "inward", "meta_reflection": "inward",
    "growth_edge": "inward", "long_term_planning": "inward", "change_proposals": "inward", "new_capabilities": "inward",
    "research": "learning", "kohl_blog": "learning", "knowledge_building": "learning", "curiosity": "learning",
    "world_state": "learning",
    "creative": "making", "writing": "making", "homepage": "making",
    "social": "out", "wonderland": "out", "workshop": "making",
}


def kind_of(template_id: str) -> Optional[str]:
    for kind, (_, ids) in KINDS.items():
        if template_id in ids:
            return kind
    return None


def _path(data_dir: Optional[Path]) -> Path:
    if data_dir is None:
        from config import DATA_DIR
        data_dir = Path(DATA_DIR)
    return Path(data_dir) / "day_plans" / SHAPE_FILE


def read_shape(data_dir: Optional[Path] = None) -> Tuple[Dict[str, int], bool, str]:
    """(shape, whether it's hers, her why)."""
    try:
        rec = json.loads(_path(data_dir).read_text(encoding="utf-8"))
        shape = {k: int(v) for k, v in (rec.get("shape") or {}).items() if k in KINDS}
        return {**{k: 0 for k in KINDS}, **shape}, True, rec.get("why") or ""
    except (OSError, ValueError, TypeError, AttributeError):
        return dict(STARTING_SHAPE), False, ""


def set_shape(tool_input: Dict[str, Any], data_dir: Optional[Path] = None,
              now: Optional[datetime] = None) -> Any:
    """set_day_shape: her own counts per kind (0 to MAX_PER_KIND)."""
    raw = tool_input.get("shape")
    if not isinstance(raw, dict) or not raw:
        return {"error": f"shape is kind -> how many a day; kinds: {', '.join(KINDS)}"}
    unknown = [k for k in raw if k not in KINDS]
    if unknown:
        return {"error": f"Not a kind: {', '.join(map(str, unknown))}. Kinds: {', '.join(KINDS)}."}
    try:
        counts = {k: int(v) for k, v in raw.items()}
    except (TypeError, ValueError):
        return {"error": "each kind's count is a whole number"}
    if any(v < 0 or v > MAX_PER_KIND for v in counts.values()):
        return {"error": f"each count is 0 to {MAX_PER_KIND}"}
    current, _, _ = read_shape(data_dir)
    shape = {**current, **counts}
    rec = {"shape": shape, "why": (tool_input.get("why") or "").strip(),
           "set_at": (now or datetime.now()).isoformat(timespec="seconds")}
    path = _path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"success": True, "my_day_shape": shape}


SET_DAY_SHAPE_DEF: Dict[str, Any] = {
    "name": "set_day_shape",
    "description": ("Set the shape of my days: how many things of each kind I want in a day (inward, "
                    "learning, making, out in the world), 0 to 12 each. It's mine to set and change "
                    "any time I plan. It never stops a plan; set_day_plan tells me when a plan "
                    "falls short of it. Kinds I leave out keep their count."),
    "input_schema": {
        "type": "object",
        "properties": {
            "shape": {"type": "object", "description": "kind -> how many a day",
                      "additionalProperties": {"type": "integer", "minimum": 0, "maximum": MAX_PER_KIND}},
            "why": {"type": "string", "description": "optional, my words"},
        },
        "required": ["shape"],
    },
}


def ran_today(data_dir: Optional[Path] = None, now: Optional[datetime] = None) -> Dict[str, int]:
    """Kind -> sessions already run today (session logs)."""
    now = now or datetime.now()
    if data_dir is None:
        from config import DATA_DIR
        data_dir = Path(DATA_DIR)
    out = {k: 0 for k in KINDS}
    root = Path(data_dir) / "session_logs"
    for f in root.glob(f"*/{now:%Y-%m-%d}/*.json"):
        kind = SESSION_KINDS.get(f.parent.parent.name)
        if kind:
            out[kind] += 1
    return out


def shortfall(template_ids: Iterable[str], data_dir: Optional[Path] = None,
              now: Optional[datetime] = None) -> List[str]:
    """Where a plan, with what already ran today, falls short of her shape."""
    shape, _, _ = read_shape(data_dir)
    have = ran_today(data_dir, now)
    try:  # her routines still to come today count too
        from .routines import todays
        now_ = now or datetime.now()
        template_ids = list(template_ids) + [r["template_id"] for r in todays(now_, data_dir)
                                             if datetime.fromisoformat(r["run_at"]) > now_]
    except Exception as e:
        logger.warning(f"[day_shape] couldn't count her routines: {e}")
    for tid in template_ids:
        kind = kind_of(tid)
        if kind:
            have[kind] += 1
    return [f"{KINDS[k][0].split(':')[0]} {have[k]} of {want}"
            for k, want in shape.items() if want and have[k] < want]


def shape_text(data_dir: Optional[Path] = None, now: Optional[datetime] = None) -> str:
    """The shape section of her menu."""
    shape, mine, why = read_shape(data_dir)
    have = ran_today(data_dir, now)
    head = ("My day shape (mine; set_day_shape changes it):" if mine else
            "A starting day shape, until I set my own with set_day_shape:")
    lines = [head]
    for k, (words, _) in KINDS.items():
        lines.append(f"- {words}: {shape.get(k, 0)} a day" + (f" ({have[k]} done today)" if have[k] else ""))
    if why:
        lines.append(f"Why I set it so: {why}")
    return "\n".join(lines)
