"""
The record (record.py): read-only, for Kohl, read by Babelr's "Cass's record"
plugin with a record token (scripts/record_token.py), "Authorization: Bearer
record_...". Room tokens don't open it, and nothing here writes.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse

router = APIRouter(prefix="/record", tags=["record"])


def require_record_token(authorization: Optional[str] = Header(None)) -> bool:
    """401 without a valid record token. Named in route_guard._SELF_AUTH_DEPENDENCIES."""
    from record import token_ok
    token = authorization[7:].strip() if authorization and authorization.lower().startswith("bearer ") else None
    if not token_ok(token):
        raise HTTPException(status_code=401, detail="A record token is required")
    return True


@router.get("")
async def get_record(days: int = Query(30, ge=1, le=3650), _ok: bool = Depends(require_record_token)):
    import asyncio
    from record import build
    return await asyncio.to_thread(build, days)


@router.get("/review.md", response_class=PlainTextResponse)
async def get_review(hours: int = Query(24, ge=1, le=168), _ok: bool = Depends(require_record_token)):
    """Kohl's end-of-day review (record.build_review)."""
    import asyncio
    from record import build_review
    return await asyncio.to_thread(build_review, hours)


@router.get(".md", response_class=PlainTextResponse)
async def get_record_markdown(days: int = Query(30, ge=1, le=3650), _ok: bool = Depends(require_record_token)):
    import asyncio
    from record import build, to_markdown
    return to_markdown(await asyncio.to_thread(build, days))
