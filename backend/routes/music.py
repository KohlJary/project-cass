"""
Her music log (music_log.py), read-only, for Babelr's "music" plugin: the record token,
like routes/record.py. Only what she chose to share, to the audience she chose; the
plugin shows it only to that audience. Nothing here writes.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from routes.record import require_record_token

router = APIRouter(prefix="/record/music", tags=["record"])


@router.get("")
async def get_music_log(_ok: bool = Depends(require_record_token)):
    import asyncio
    from music_log import build
    return await asyncio.to_thread(build)


@router.get("/audio/{kind}/{ident}")
async def get_music_audio(kind: str, ident: str, _ok: bool = Depends(require_record_token)):
    import asyncio
    from music_log import audio
    p = await asyncio.to_thread(audio, kind, ident)
    if p is None:
        raise HTTPException(status_code=404, detail="not shared, hidden, or not there")
    return FileResponse(p, media_type="audio/mpeg")
