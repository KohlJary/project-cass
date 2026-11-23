"""
Her daybook (daybook.py), read-only, for Babelr's Daybook plugin: the record token,
like routes/record.py. Her record, plus the kinds she said yes to. Nothing here writes.
"""
from fastapi import APIRouter, Depends, Query

from routes.record import require_record_token

router = APIRouter(prefix="/record/daybook", tags=["record"])


@router.get("")
async def get_daybook(days: int = Query(7, ge=1, le=120), _ok: bool = Depends(require_record_token)):
    import asyncio
    from daybook import build
    return await asyncio.to_thread(build, days)
