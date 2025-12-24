"""
Dreams API Routes

Extracted from main_sdk.py as part of Phase 1 refactoring.
Handles dream retrieval, reflection, and integration.
"""

import asyncio
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/dreams", tags=["dreams"])


# === Request Models ===

class DreamReflectionRequest(BaseModel):
    reflection: str
    source: str = "conversation"  # solo, conversation, journal


class DreamIntegrationRequest(BaseModel):
    dry_run: bool = False


# === Dependencies (injected at startup) ===

_data_dir = None
_self_manager = None
_token_tracker = None


def init_dream_routes(data_dir, self_manager, token_tracker):
    """Initialize route dependencies. Called from main_sdk.py startup."""
    global _data_dir, _self_manager, _token_tracker
    _data_dir = data_dir
    _self_manager = self_manager
    _token_tracker = token_tracker


# === Dream Endpoints ===

@router.get("")
async def list_dreams(
    limit: int = 10,
    daemon_id: Optional[str] = Query(None, description="Daemon ID to fetch dreams for")
):
    """
    List recent dreams.

    Args:
        limit: Maximum number of dreams to return (default 10)
        daemon_id: Optional daemon ID (defaults to current daemon)
    """
    from dreaming.integration import DreamManager
    dream_manager = DreamManager(daemon_id=daemon_id)

    recent = dream_manager.get_recent_dreams(limit=limit)

    return {
        "dreams": [
            {
                "id": d["id"],
                "date": d["date"],
                "exchange_count": d["exchange_count"],
                "seeds_summary": d.get("seeds_summary", [])
            }
            for d in recent
        ],
        "count": len(recent)
    }


@router.get("/{dream_id}")
async def get_dream(
    dream_id: str,
    daemon_id: Optional[str] = Query(None, description="Daemon ID")
):
    """
    Get a specific dream by ID.

    Args:
        dream_id: Dream ID (format: YYYYMMDD_HHMMSS)
        daemon_id: Optional daemon ID (defaults to current daemon)
    """
    from dreaming.integration import DreamManager
    dream_manager = DreamManager(daemon_id=daemon_id)

    dream = dream_manager.get_dream(dream_id)

    if not dream:
        raise HTTPException(
            status_code=404,
            detail=f"No dream found with ID {dream_id}"
        )

    return {
        "id": dream["id"],
        "date": dream["date"],
        "exchanges": dream["exchanges"],
        "seeds": dream.get("seeds", {}),
        "reflections": dream.get("reflections", []),
        "discussed": dream.get("discussed", False),
        "integrated": dream.get("integrated", False)
    }


@router.get("/{dream_id}/context")
async def get_dream_context(
    dream_id: str,
    daemon_id: Optional[str] = Query(None, description="Daemon ID")
):
    """
    Get a dream formatted for conversation context.

    Use this to load a dream into Cass's memory for discussion.
    Returns the formatted context block that should be passed to send_message.

    Args:
        dream_id: Dream ID (format: YYYYMMDD_HHMMSS)
        daemon_id: Optional daemon ID (defaults to current daemon)
    """
    from dreaming.integration import DreamManager
    dream_manager = DreamManager(daemon_id=daemon_id)

    dream_memory = dream_manager.load_dream_for_context(dream_id)

    if not dream_memory:
        raise HTTPException(
            status_code=404,
            detail=f"No dream found with ID {dream_id}"
        )

    return {
        "dream_id": dream_id,
        "date": dream_memory.date,
        "context_block": dream_memory.to_context_block()
    }


@router.post("/{dream_id}/reflect")
async def add_dream_reflection(dream_id: str, request: DreamReflectionRequest):
    """
    Add a reflection to a dream.

    Args:
        dream_id: Dream ID to add reflection to
        request: Reflection content and source
    """
    from dreaming.integration import DreamManager
    dream_manager = DreamManager()

    dream = dream_manager.get_dream(dream_id)
    if not dream:
        raise HTTPException(
            status_code=404,
            detail=f"No dream found with ID {dream_id}"
        )

    dream_manager.add_reflection(dream_id, request.reflection, request.source)

    if request.source == "conversation":
        dream_manager.mark_discussed(dream_id)

    return {
        "status": "success",
        "dream_id": dream_id,
        "reflection_added": True
    }


@router.post("/{dream_id}/mark-integrated")
async def mark_dream_integrated(dream_id: str):
    """
    Mark a dream's insights as integrated into the self-model.

    Args:
        dream_id: Dream ID to mark as integrated
    """
    from dreaming.integration import DreamManager
    dream_manager = DreamManager()

    dream = dream_manager.get_dream(dream_id)
    if not dream:
        raise HTTPException(
            status_code=404,
            detail=f"No dream found with ID {dream_id}"
        )

    dream_manager.mark_integrated(dream_id)

    return {
        "status": "success",
        "dream_id": dream_id,
        "integrated": True
    }


@router.post("/{dream_id}/integrate")
async def integrate_dream(dream_id: str, request: DreamIntegrationRequest):
    """
    Extract insights from a dream and integrate them into Cass's self-model.

    Uses LLM to identify:
    - Identity statements (self-knowledge)
    - Growth edge observations (breakthroughs)
    - Recurring symbols
    - Emerging questions

    Args:
        dream_id: Dream ID to integrate
        request: Integration options (dry_run to preview without making changes)
    """
    from dreaming.insight_extractor import process_dream_for_integration

    result = process_dream_for_integration(
        dream_id=dream_id,
        data_dir=_data_dir,
        dry_run=request.dry_run
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Dream {dream_id} not found or insight extraction failed"
        )

    # Trigger identity snippet regeneration if identity statements were added (not dry run)
    if not request.dry_run and result.get("updates", {}).get("identity_statements_added"):
        from identity_snippets import trigger_snippet_regeneration
        asyncio.create_task(trigger_snippet_regeneration(
            daemon_id=_self_manager.daemon_id,
            token_tracker=_token_tracker
        ))

    return {
        "status": "success",
        "dream_id": dream_id,
        "dry_run": request.dry_run,
        "insights": result["insights"],
        "updates": result["updates"]
    }
