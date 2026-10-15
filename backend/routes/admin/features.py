"""
Admin API - feature levers (read-only).

GET /admin/features lists every lever from features.py with its effective
value and where that value came from (default, env var, profile, override).
Changing levers is deliberately not exposed over HTTP: set env vars and restart.
"""
from typing import Dict

from fastapi import APIRouter, Depends

from features import active_profile, lever_table
from .auth import require_admin

router = APIRouter(tags=["admin-features"])


@router.get("/features")
async def list_feature_levers(admin: Dict = Depends(require_admin)):
    """Effective value and source of every feature lever."""
    return {"profile": active_profile(), "levers": lever_table()}
