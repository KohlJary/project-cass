"""
Mind Palace API - FastAPI routes for Cass to access palaces.

These endpoints allow Cass to:
1. Query palace structure and navigate
2. Ask entities about topics
3. Check for drift and synchronization status

Mount this router in your FastAPI app to enable Cass integration.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from daedalus.labyrinth import Cartographer, Palace, Navigator, PalaceStorage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mind-palace", tags=["mind-palace"])

# Global palace registry - maps project paths to loaded palaces
_palaces: Dict[str, tuple] = {}  # path -> (palace, navigator, storage)


class NavigateRequest(BaseModel):
    """Request to execute a navigation command."""
    command: str
    project_path: Optional[str] = None


class NavigateResponse(BaseModel):
    """Response from navigation command."""
    output: str
    current_room: Optional[str] = None
    current_building: Optional[str] = None
    current_region: Optional[str] = None


class AskEntityRequest(BaseModel):
    """Request to ask an entity about a topic."""
    entity: str
    topic: str
    project_path: Optional[str] = None


class PalaceInfo(BaseModel):
    """Summary information about a palace."""
    name: str
    version: str
    regions: List[str]
    buildings: List[str]
    room_count: int
    entity_count: int
    created: Optional[str] = None
    last_updated: Optional[str] = None


class DriftItem(BaseModel):
    """A single drift report item."""
    room_name: str
    anchor_file: str
    issues: List[str]
    severity: str
    suggested_fix: Optional[str] = None


def get_palace(project_path: str) -> tuple:
    """Get or load a palace for a project path."""
    if project_path in _palaces:
        return _palaces[project_path]

    path = Path(project_path)
    storage = PalaceStorage(path)

    if not storage.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No Mind Palace found at {project_path}"
        )

    palace = storage.load()
    if not palace:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load palace from {project_path}"
        )

    navigator = Navigator(palace)
    _palaces[project_path] = (palace, navigator, storage)
    return palace, navigator, storage


@router.get("/info")
async def get_palace_info(
    project_path: str = Query(..., description="Path to the project")
) -> PalaceInfo:
    """Get information about a palace."""
    palace, _, _ = get_palace(project_path)

    return PalaceInfo(
        name=palace.name,
        version=palace.version,
        regions=list(palace.regions.keys()),
        buildings=list(palace.buildings.keys()),
        room_count=len(palace.rooms),
        entity_count=len(palace.entities),
        created=palace.created,
        last_updated=palace.last_updated,
    )


@router.post("/navigate")
async def navigate(request: NavigateRequest) -> NavigateResponse:
    """Execute a navigation command in the palace."""
    if not request.project_path:
        raise HTTPException(status_code=400, detail="project_path required")

    palace, navigator, _ = get_palace(request.project_path)

    output = navigator.execute(request.command)

    return NavigateResponse(
        output=output,
        current_room=navigator._current_room,
        current_building=navigator._current_building,
        current_region=navigator._current_region,
    )


@router.get("/look")
async def look(
    project_path: str = Query(..., description="Path to the project")
) -> NavigateResponse:
    """Look at current location in the palace."""
    palace, navigator, _ = get_palace(project_path)

    return NavigateResponse(
        output=navigator.look(),
        current_room=navigator._current_room,
        current_building=navigator._current_building,
        current_region=navigator._current_region,
    )


@router.post("/ask")
async def ask_entity(request: AskEntityRequest) -> Dict[str, Any]:
    """Ask an entity about a topic."""
    if not request.project_path:
        raise HTTPException(status_code=400, detail="project_path required")

    palace, navigator, _ = get_palace(request.project_path)

    response = navigator.ask(request.entity, request.topic)

    return {
        "entity": request.entity,
        "topic": request.topic,
        "response": response,
    }


@router.get("/entities")
async def list_entities(
    project_path: str = Query(..., description="Path to the project")
) -> List[Dict[str, Any]]:
    """List all entities in the palace."""
    palace, _, _ = get_palace(project_path)

    return [
        {
            "name": entity.name,
            "location": entity.location,
            "role": entity.role,
            "topics": [t.name for t in entity.topics],
        }
        for entity in palace.entities.values()
    ]


@router.get("/rooms")
async def list_rooms(
    project_path: str = Query(..., description="Path to the project"),
    building: Optional[str] = Query(None, description="Filter by building"),
) -> List[Dict[str, Any]]:
    """List rooms in the palace."""
    palace, _, _ = get_palace(project_path)

    rooms = palace.rooms.values()
    if building:
        rooms = [r for r in rooms if r.building == building]

    return [
        {
            "name": room.name,
            "building": room.building,
            "floor": room.floor,
            "description": room.description[:100] if room.description else "",
            "hazard_count": len(room.hazards),
            "exit_count": len(room.exits),
        }
        for room in rooms
    ]


@router.get("/room/{room_name}")
async def get_room(
    room_name: str,
    project_path: str = Query(..., description="Path to the project"),
) -> Dict[str, Any]:
    """Get details about a specific room."""
    palace, _, _ = get_palace(project_path)

    room = palace.get_room(room_name)
    if not room:
        raise HTTPException(status_code=404, detail=f"Room not found: {room_name}")

    return room.to_dict()


@router.get("/where-is/{target}")
async def where_is(
    target: str,
    project_path: str = Query(..., description="Path to the project"),
) -> Dict[str, str]:
    """Find something in the palace."""
    palace, navigator, _ = get_palace(project_path)

    result = navigator.where_is(target)

    return {"target": target, "result": result}


@router.get("/drift")
async def check_drift(
    project_path: str = Query(..., description="Path to the project")
) -> List[DriftItem]:
    """Check for drift between palace and code."""
    palace, _, storage = get_palace(project_path)

    cartographer = Cartographer(palace, storage)
    reports = cartographer.check_drift()

    return [
        DriftItem(
            room_name=r.room_name,
            anchor_file=r.anchor_file,
            issues=r.issues,
            severity=r.severity,
            suggested_fix=r.suggested_fix,
        )
        for r in reports
    ]


@router.post("/sync/{room_name}")
async def sync_room(
    room_name: str,
    project_path: str = Query(..., description="Path to the project"),
) -> Dict[str, Any]:
    """Re-sync a room with its code anchor."""
    palace, _, storage = get_palace(project_path)

    cartographer = Cartographer(palace, storage)
    updated = cartographer.sync_room(room_name)

    if not updated:
        raise HTTPException(
            status_code=400,
            detail=f"Could not sync room: {room_name}"
        )

    return {
        "success": True,
        "room": updated.to_dict(),
    }


# Utility to clear cached palaces (for testing/refresh)
@router.post("/reload")
async def reload_palace(
    project_path: str = Query(..., description="Path to the project")
) -> Dict[str, str]:
    """Reload a palace from disk."""
    if project_path in _palaces:
        del _palaces[project_path]

    palace, _, _ = get_palace(project_path)

    return {
        "status": "reloaded",
        "name": palace.name,
    }
