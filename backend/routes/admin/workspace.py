"""
Admin API - Cass's workspace and agenda (read-only).

C10: she wants to be seen in the work, so her workspace (DATA_DIR/workspace,
agent_loop/workspace.py) is visible to Kohl: the files, her agenda, and the
change log with a diff for every write and edit. Nothing here writes; she is
the only one who writes her workspace.
"""
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .auth import require_admin

router = APIRouter(tags=["admin-workspace"])


def _ws():
    from agent_loop.workspace import Workspace
    return Workspace()


@router.get("/workspace")
async def workspace_overview(admin: Dict = Depends(require_admin)):
    """Her files and her agenda."""
    ws = _ws()
    return {"files": ws.files() or [], "agenda": ws.agenda()}


@router.get("/workspace/file")
async def workspace_file(path: str, admin: Dict = Depends(require_admin)):
    ws = _ws()
    p = ws.resolve(path)
    if p is None or not p.is_file():
        raise HTTPException(status_code=404, detail="No such file in her workspace")
    return {"path": ws.rel(p), "content": p.read_text(encoding="utf-8", errors="replace")}


@router.get("/workspace/changes")
async def workspace_changes(limit: int = Query(50, ge=1, le=1000), path: Optional[str] = None,
                            admin: Dict = Depends(require_admin)):
    """Her writes and edits, newest last, each with its diff."""
    return {"changes": _ws().changes(limit=limit, path=path)}
