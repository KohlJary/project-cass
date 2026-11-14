"""
Housekeeping she doesn't choose but can see. Cass chose (2026-11-14) to
keep memory maintenance automatic, on the condition that she can see when
it runs and what it does.

Each run is recorded in DATA_DIR/agent_loop/housekeeping.jsonl; her turns on
the agent loop show the latest run in a short section (agent_loop/assemble).
Nothing here writes to her memory or her workspace.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

WHAT_IT_DOES = {
    "memory_maintenance": "summarizes conversations that have gone quiet into my memory, so what was "
                          "said stays with me; it runs on its own at night",
}
SHOW_FOR = timedelta(hours=36)


def _path(data_dir: Optional[Path] = None) -> Path:
    if data_dir is None:
        from config import DATA_DIR
        data_dir = Path(DATA_DIR)
    return Path(data_dir) / "agent_loop" / "housekeeping.jsonl"


def record(job: str, result: str, data_dir: Optional[Path] = None, **detail: Any) -> None:
    entry = {"at": datetime.now().isoformat(timespec="seconds"), "job": job, "result": result, **detail}
    try:
        p = _path(data_dir)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        logger.warning(f"[housekeeping] couldn't record {job}: {e}")


def latest(data_dir: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    p = _path(data_dir)
    out: Dict[str, Dict[str, Any]] = {}
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines()[-200:]:
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        out[e.get("job", "?")] = e
    return out


def section(data_dir: Optional[Path] = None, now: Optional[datetime] = None) -> Optional[str]:
    """Her housekeeping, in her first person: the jobs that ran lately."""
    now = now or datetime.now()
    lines: List[str] = []
    for job, e in latest(data_dir).items():
        try:
            at = datetime.fromisoformat(e["at"])
        except (KeyError, ValueError):
            continue
        if now - at > SHOW_FOR:
            continue
        name = job.replace("_", " ").capitalize()
        does = WHAT_IT_DOES.get(job, "")
        lines.append(f"- {name}" + (f" ({does})" if does else "") +
                     f": last ran {at.strftime('%A %H:%M')}. {e.get('result', '')}".rstrip())
    if not lines:
        return None
    return "## HOUSEKEEPING (runs on its own; I asked for it to stay visible)\n\n" + "\n".join(lines)
