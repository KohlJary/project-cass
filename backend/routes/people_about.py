"""
What she keeps about you (babelr_organ/people.py about()), read-only, for Babelr:
the record token, like routes/daybook.py and routes/panel.py. Off unless her own
answer says yes (panel settings, people.about: yes, no or not_yet; default
not_yet; scripts/panel_set.py people.about=yes). Nothing here writes.
"""
from fastapi import APIRouter, Depends, Query

from routes.record import require_record_token

router = APIRouter(prefix="/record/people", tags=["record"])


def what_she_keeps(handle: str) -> dict:
    import panel
    answer = panel.settings().get("people", {}).get("about", "not_yet")
    if answer != "yes":
        return {"shown": False, "why": answer if answer in ("no", "not_yet") else "not_yet"}
    from babelr_organ.config import load_config
    from babelr_organ.organ import read_links
    from babelr_organ.people import about, load_filings
    cfg = load_config()
    return {"shown": True, **about(handle, filings=load_filings(cfg.people_path),
                                   links=read_links(cfg.links_path))}


@router.get("/about")
async def get_about(handle: str = Query(..., min_length=1, max_length=100),
                    _ok: bool = Depends(require_record_token)):
    """What her PeopleDex holds on one Babelr handle: name, pronouns if known,
    her active observations, how many moments, first and last seen.

    Server to server only. Babelr calls this with the record token, and it must
    only ever ask about the handle of the person viewing: the signed-in
    viewer's own username, never one typed in or taken from a URL, a message
    or another person's profile. This route can't tell who is viewing; the
    record token trusts Babelr to keep to that, the same as its daybook and
    panel calls.

    Her answer governs: unless her people.about setting is yes, the reply is
    {"shown": false, "why": "not_yet" | "no"}, whatever the handle. With her
    yes: {"shown": true, "handle", "known": false} when she has no entry for
    exactly that handle, or they asked to be kept off her PeopleDex (the same
    answer, so nobody learns who asked); "why": "linked" for people linked to
    a vessel user (Kohl, RoboKohl, Daedalus), whose entries come from their own
    conversations with her; otherwise {"shown": true, "handle", "known": true,
    "name", "pronouns", "observations": [{"kind", "text", "noticed"}],
    "moments", "first_seen", "last_seen"}. Only her own observations and
    moments (not another daemon's), and not the things she has noted to bring
    up with them herself."""
    import asyncio
    return await asyncio.to_thread(what_she_keeps, handle)
