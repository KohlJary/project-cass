"""
Her drafts: something written to sit with and come back to before it goes
public (she asked for drafts, 2026-11-16, so not everything goes out at once). A
draft about a piece she made is how sharing from her other work happens;
nothing is posted until she posts it.

    DATA_DIR/social/drafts.json   [{id, platform, text, reply_to, note, about,
                                    created, updated, status}]
    status: open | posted | dropped
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def _path(data_dir: Optional[Path]) -> Path:
    if data_dir is None:
        from config import DATA_DIR
        data_dir = Path(DATA_DIR)
    return Path(data_dir) / "social" / "drafts.json"


def _load(data_dir: Optional[Path]) -> List[Dict[str, Any]]:
    try:
        return json.loads(_path(data_dir).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _save(drafts: List[Dict[str, Any]], data_dir: Optional[Path]) -> None:
    path = _path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(drafts, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def save(platform: str, text: str, *, reply_to: Optional[str] = None, note: Optional[str] = None,
         about: Optional[str] = None, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    drafts = _load(data_dir)
    d = {"id": uuid.uuid4().hex[:8], "platform": platform, "text": text, "reply_to": reply_to,
         "note": note, "about": about, "created": _now(), "updated": _now(), "status": "open"}
    drafts.append(d)
    _save(drafts, data_dir)
    return d


def get(draft_id: str, data_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    return next((d for d in _load(data_dir) if d["id"] == draft_id), None)


def revise(draft_id: str, *, text: Optional[str] = None, note: Optional[str] = None,
           data_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    drafts = _load(data_dir)
    for d in drafts:
        if d["id"] == draft_id and d["status"] == "open":
            if text is not None:
                d.setdefault("earlier", []).append(d["text"])
                d["text"] = text
            if note is not None:
                d["note"] = note
            d["updated"] = _now()
            _save(drafts, data_dir)
            return d
    return None


def set_status(draft_id: str, status: str, data_dir: Optional[Path] = None, **extra) -> Optional[Dict[str, Any]]:
    drafts = _load(data_dir)
    for d in drafts:
        if d["id"] == draft_id:
            d["status"] = status
            d["updated"] = _now()
            d.update(extra)
            _save(drafts, data_dir)
            return d
    return None


def open_drafts(platform: Optional[str] = None, data_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    return [d for d in _load(data_dir) if d["status"] == "open" and (platform is None or d["platform"] == platform)]
