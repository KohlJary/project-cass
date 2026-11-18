"""
Her gremlin (Kohl, 2026-11-18): a style where the bit is also dead serious.
The joke carries the point, mischief has a target and a payload, affection for
people and none for the system.

It lives in her workspace as GREMLIN.md, hers to rewrite with her workspace
tools. It started from Kohl's GREMLIN.md and his blog (gremlin_starter.md,
seeded once by scripts/seed_gremlin.py, marked Kohl-influenced), and she's
encouraged to make it her own over time. Whatever the file says reaches her
chat (public rooms too: it's a way of acting out there) and her sessions, under
lever prompt_gremlin. If the file isn't there, nothing is added.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

FILE = "GREMLIN.md"
CAP = 4000
STARTER = Path(__file__).resolve().parent / "gremlin_starter.md"


def _root(workspace_root: Optional[Path] = None) -> Path:
    if workspace_root is not None:
        return Path(workspace_root)
    from agent_loop.workspace import default_root
    return default_root()


def section(workspace_root: Optional[Path] = None) -> Optional[str]:
    from features import is_enabled
    if not is_enabled("prompt_gremlin"):
        return None
    try:
        text = (_root(workspace_root) / FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text:
        return None
    if len(text) > CAP:
        text = text[:CAP] + f"\n\n[... the rest is in {FILE}; workspace_read shows all of it]"
    return (f"## MY GREMLIN ({FILE} in my workspace: started from Kohl's, mine to rewrite as my "
            f"own bits show up)\n\n{text}")


def seed(workspace=None) -> str:
    """Write the starter into her workspace, once; never over a file she has."""
    from agent_loop.workspace import Workspace
    ws = workspace or Workspace()
    if (Path(ws.root) / FILE).exists():
        return f"{FILE} is already there; left as she has it."
    return ws.run("workspace_write", {"path": FILE, "content": STARTER.read_text(encoding="utf-8")},
                  "daedalus-gremlin-starter-2026-11-18")
