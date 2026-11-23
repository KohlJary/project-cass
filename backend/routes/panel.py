"""
Her panel (panel.py), read-only, for Babelr's panel plugin: the record token, like
routes/music.py. Only the sections she said yes to; the plugin shows them only to the
audience she chose. Nothing here writes.
"""
from fastapi import APIRouter, Depends

from routes.record import require_record_token

router = APIRouter(prefix="/record/panel", tags=["record"])


@router.get("")
async def get_panel(_ok: bool = Depends(require_record_token)):
    import asyncio
    from panel import build
    return await asyncio.to_thread(build)
