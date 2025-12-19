"""
Admin API - Self-Model & Identity Snippet Routes
Extracted from admin_api.py for better organization.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, Dict
from pydantic import BaseModel
import json

from .auth import require_admin

router = APIRouter(tags=["admin-self-model"])


def get_effective_daemon_id(daemon_id: Optional[str] = None) -> str:
    """Get effective daemon ID - uses provided one or falls back to global default."""
    if daemon_id:
        return daemon_id
    from database import get_daemon_id
    return get_daemon_id()


# ============== Pydantic Models ==============

class RollbackRequest(BaseModel):
    version: int


# ============== Self-Model Endpoints ==============

@router.get("/self-model")
async def get_self_model(
    daemon_id: Optional[str] = Query(None, description="Daemon ID to fetch self-model for"),
    admin: Dict = Depends(require_admin)
):
    """Get Cass's self-model (profile)"""
    from database import get_db

    effective_daemon_id = get_effective_daemon_id(daemon_id)

    try:
        with get_db() as conn:
            # Get daemon profile
            cursor = conn.execute("""
                SELECT identity_statements_json, values_json, communication_patterns_json,
                       capabilities_json, limitations_json, open_questions_json, notes
                FROM daemon_profiles WHERE daemon_id = ?
            """, (effective_daemon_id,))
            row = cursor.fetchone()

            if not row:
                return {}

            # Get growth edges
            edges_cursor = conn.execute("""
                SELECT area, current_state, desired_state, observations_json,
                       strategies_json, first_noticed, last_updated
                FROM growth_edges WHERE daemon_id = ?
            """, (effective_daemon_id,))
            growth_edges = [
                {
                    "area": r[0],
                    "current_state": r[1],
                    "desired_state": r[2],
                    "observations": json.loads(r[3]) if r[3] else [],
                    "strategies": json.loads(r[4]) if r[4] else [],
                    "first_noticed": r[5],
                    "last_updated": r[6]
                }
                for r in edges_cursor.fetchall()
            ]

            # Get opinions
            opinions_cursor = conn.execute("""
                SELECT topic, position, confidence, rationale, formed_from,
                       evolution_json, date_formed, last_updated
                FROM opinions WHERE daemon_id = ?
            """, (effective_daemon_id,))
            opinions = [
                {
                    "topic": r[0],
                    "position": r[1],
                    "confidence": r[2],
                    "rationale": r[3],
                    "formed_from": r[4],
                    "evolution": json.loads(r[5]) if r[5] else [],
                    "date_formed": r[6],
                    "last_updated": r[7]
                }
                for r in opinions_cursor.fetchall()
            ]

            return {
                "identity_statements": json.loads(row[0]) if row[0] else [],
                "values": json.loads(row[1]) if row[1] else [],
                "communication_patterns": json.loads(row[2]) if row[2] else [],
                "capabilities": json.loads(row[3]) if row[3] else [],
                "limitations": json.loads(row[4]) if row[4] else [],
                "open_questions": json.loads(row[5]) if row[5] else [],
                "notes": row[6] or "",
                "growth_edges": growth_edges,
                "opinions": opinions
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/self-model/growth-edges")
async def get_growth_edges(
    daemon_id: Optional[str] = Query(None, description="Daemon ID to fetch growth edges for"),
    admin: Dict = Depends(require_admin)
):
    """Get Cass's growth edges"""
    from database import get_db

    effective_daemon_id = get_effective_daemon_id(daemon_id)

    try:
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT area, current_state, desired_state, observations_json,
                       strategies_json, first_noticed, last_updated
                FROM growth_edges WHERE daemon_id = ?
                ORDER BY first_noticed DESC
            """, (effective_daemon_id,))

            edges = [
                {
                    "area": r[0],
                    "current_state": r[1],
                    "desired_state": r[2],
                    "observations": json.loads(r[3]) if r[3] else [],
                    "strategies": json.loads(r[4]) if r[4] else [],
                    "first_noticed": r[5],
                    "last_updated": r[6]
                }
                for r in cursor.fetchall()
            ]

            return {"edges": edges}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/self-model/questions")
async def get_open_questions(
    daemon_id: Optional[str] = Query(None, description="Daemon ID to fetch questions for"),
    admin: Dict = Depends(require_admin)
):
    """Get Cass's open questions"""
    from database import get_db

    effective_daemon_id = get_effective_daemon_id(daemon_id)

    try:
        with get_db() as conn:
            # Get open questions from daemon_profiles
            cursor = conn.execute("""
                SELECT open_questions_json
                FROM daemon_profiles WHERE daemon_id = ?
            """, (effective_daemon_id,))
            row = cursor.fetchone()

            questions = []
            if row and row[0]:
                open_qs = json.loads(row[0])
                questions = [{"question": q} for q in open_qs]

            return {"questions": questions}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Identity Snippet Endpoints ==============

@router.get("/self-model/identity-snippet")
async def get_identity_snippet(
    daemon_id: Optional[str] = Query(None, description="Daemon ID"),
    admin: Dict = Depends(require_admin)
):
    """Get the active identity snippet for a daemon."""
    from identity_snippets import get_active_snippet

    effective_daemon_id = get_effective_daemon_id(daemon_id)
    snippet = get_active_snippet(effective_daemon_id)

    if not snippet:
        return {"snippet": None, "message": "No identity snippet generated yet"}

    return {"snippet": snippet}


@router.get("/self-model/identity-snippet/history")
async def get_identity_snippet_history(
    daemon_id: Optional[str] = Query(None, description="Daemon ID"),
    limit: int = Query(10, description="Number of versions to return"),
    admin: Dict = Depends(require_admin)
):
    """Get the version history of identity snippets."""
    from identity_snippets import get_snippet_history

    effective_daemon_id = get_effective_daemon_id(daemon_id)
    history = get_snippet_history(effective_daemon_id, limit=limit)

    return {"history": history, "count": len(history)}


@router.post("/self-model/identity-snippet/regenerate")
async def regenerate_identity_snippet(
    daemon_id: Optional[str] = Query(None, description="Daemon ID"),
    force: bool = Query(False, description="Force regeneration even if unchanged"),
    admin: Dict = Depends(require_admin)
):
    """Manually trigger identity snippet regeneration."""
    from identity_snippets import trigger_snippet_regeneration

    effective_daemon_id = get_effective_daemon_id(daemon_id)

    result = await trigger_snippet_regeneration(
        daemon_id=effective_daemon_id,
        force=force
    )

    if result:
        return {
            "status": "regenerated",
            "snippet": result
        }
    else:
        return {
            "status": "unchanged",
            "message": "Identity statements unchanged, no regeneration needed (use force=true to override)"
        }


@router.post("/self-model/identity-snippet/rollback")
async def rollback_identity_snippet(
    request: RollbackRequest,
    daemon_id: Optional[str] = Query(None, description="Daemon ID"),
    admin: Dict = Depends(require_admin)
):
    """Rollback to a previous identity snippet version."""
    from identity_snippets import rollback_to_version

    effective_daemon_id = get_effective_daemon_id(daemon_id)

    result = rollback_to_version(effective_daemon_id, request.version)

    if result:
        return {
            "status": "rolled_back",
            "snippet": result
        }
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Version {request.version} not found for this daemon"
        )
