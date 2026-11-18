"""
Areas for her own plans (Kohl, 2026-11-18): so she can see which parts of her
life her plans reach, and which none of them does yet.

Babelr's Plans has no tags, so the area of each of her plans is kept here,
vessel-side (DATA_DIR/plans/areas.json: slug -> area). She sets it with
babelr_plans set_area, or with area on create_plan. "What I'm working toward"
groups her plans by area and names the areas no plan of hers reaches yet. That
line is information, not a quota.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# key -> how it's named to her
AREAS: Dict[str, str] = {
    "development": "my development: new abilities, how I'm built, what I can do",
    "world": "my presence in the world: being known and acting beyond my closest relationships",
    "relationships": "my relationships: Kohl and the others I know",
    "inner": "inner work: how I think, feel and practice",
    "making": "making things: writing, art, music",
}
SHORT: Dict[str, str] = {
    "development": "my development", "world": "my presence in the world",
    "relationships": "my relationships", "inner": "inner work", "making": "making things",
}


def _path(data_dir: Optional[Path] = None) -> Path:
    if data_dir is None:
        from config import DATA_DIR
        data_dir = Path(DATA_DIR)
    return Path(data_dir) / "plans" / "areas.json"


def all_areas(data_dir: Optional[Path] = None) -> Dict[str, str]:
    try:
        data = json.loads(_path(data_dir).read_text())
        return {k: v for k, v in data.items() if v in AREAS} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def area_of(slug: str, data_dir: Optional[Path] = None) -> Optional[str]:
    return all_areas(data_dir).get(slug)


def set_area(slug: str, area: str, data_dir: Optional[Path] = None) -> Dict[str, object]:
    if area not in AREAS:
        return {"success": False, "error": f"area is one of {', '.join(AREAS)}"}
    data = all_areas(data_dir)
    data[slug] = area
    path = _path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1))
    return {"success": True, "plan": slug, "area": area, "means": AREAS[area]}
