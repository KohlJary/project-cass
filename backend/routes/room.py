"""
The room feed: read-only routes over what she chose to share (room.py; plan
"Cass's room in Chapter House", phase 2). Read by the Babelr room plugin
with a room token (scripts/room_token.py), sent as "Authorization: Bearer
room_...". The token's audience decides what's visible; nothing here writes.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/room", tags=["room"])


def require_room_token(authorization: Optional[str] = Header(None)) -> str:
    """The audience of a valid room token, or 401. Named in
    route_guard._SELF_AUTH_DEPENDENCIES so the guard leaves auth to it."""
    from room import audience_for
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    audience = audience_for(token)
    if not audience:
        raise HTTPException(status_code=401, detail="A room token is required")
    return audience


def _room():
    from room import Room
    return Room()


@router.get("")
async def room_overview(audience: str = Depends(require_room_token)):
    return {"audience": audience, **_room().feed(audience)}


@router.get("/sections/homepage/assets/{filename}")
async def room_homepage_asset(filename: str, audience: str = Depends(require_room_token)):
    path = _room().homepage_asset(filename, audience)
    if path is None:
        raise HTTPException(status_code=404, detail="Not in the room")
    return FileResponse(path)


@router.get("/sections/{name}")
async def room_section(name: str, audience: str = Depends(require_room_token)):
    out = _room().section(name, audience)
    if out is None:
        raise HTTPException(status_code=404, detail="Not in the room")
    return out


@router.get("/pieces/{kind}/{piece_id:path}/file")
async def room_piece_file(kind: str, piece_id: str, audience: str = Depends(require_room_token)):
    path = _room().piece_file(kind, piece_id, audience)
    if path is None:
        raise HTTPException(status_code=404, detail="Not in the room")
    return FileResponse(path)


@router.get("/pieces/{kind}/{piece_id:path}")
async def room_piece(kind: str, piece_id: str, audience: str = Depends(require_room_token)):
    out = _room().piece(kind, piece_id, audience)
    if out is None:
        raise HTTPException(status_code=404, detail="Not in the room")
    return out
