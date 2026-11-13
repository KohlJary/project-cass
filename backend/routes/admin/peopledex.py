"""
Admin API - PeopleDex entities: look up, and change an entity's type or name.

Added for the recall scoping (plan "Cass's memory", item a8fb4c8f): house
agents are PeopleDex entities of type "daemon", and Cass agreed on
2026-11-13 that Daedalus and RoboKohl be marked so. Changes to her
PeopleDex go through here (the running service), not straight into the
database.
"""
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .auth import require_admin

router = APIRouter(tags=["admin-peopledex"])


def _manager():
    from peopledex import PeopleDexManager
    return PeopleDexManager()


def _entity(e) -> Dict:
    return {"id": e.id, "entity_type": getattr(e.entity_type, "value", e.entity_type),
            "primary_name": e.primary_name, "user_id": e.user_id}


@router.get("/peopledex/entities")
async def find_entities(name: str, admin: Dict = Depends(require_admin)):
    return {"entities": [_entity(e) for e in _manager().search_entities(name, limit=20)]}


class EntityUpdate(BaseModel):
    entity_type: Optional[str] = None
    primary_name: Optional[str] = None


@router.patch("/peopledex/entities/{entity_id}")
async def update_entity(entity_id: str, body: EntityUpdate, admin: Dict = Depends(require_admin)):
    from peopledex import EntityType
    if body.entity_type is not None and body.entity_type not in {t.value for t in EntityType}:
        raise HTTPException(status_code=422, detail=f"entity_type must be one of {[t.value for t in EntityType]}")
    pdx = _manager()
    if pdx.get_entity(entity_id) is None:
        raise HTTPException(status_code=404, detail="No such entity")
    pdx.update_entity(entity_id, primary_name=body.primary_name, entity_type=body.entity_type)
    return {"entity": _entity(pdx.get_entity(entity_id))}
