"""
A Workshop session (workshop.py): time on one of her projects, or starting one.
On her day menu as "workshop" (a making kind) while the workshop lever is on.

If the session's focus names one of her projects, that project opens in front
of her: its PROJECT.md, what's uncommitted, its last commits. Continuity lives
in the project, not in her memory. Its last workshop session's "pick up next"
opens it too (agent_loop.session.left_off).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import workshop as W

logger = logging.getLogger(__name__)

TEMPLATE_ID = "workshop"
LEVER = "workshop"

INSTRUCTIONS = """## MY WORKSHOP

This is time on one of my projects: the efforts of mine that run over many sessions, each kept apart. Software, long writing, outreach, anything large. The project tool does all of it: list, status, files, read, write, edit, commit, log, and new to start one (a name, its kind, and its vision in my words). Software projects can run code (run), sandboxed, with no network.

Each project carries its own state. PROJECT.md holds its vision, where it stands and what's next, and I keep it current. A commit, with a message saying what changed and why, is what makes work part of the project's history. Before I end, I commit what I've done and update "Where it stands" and "Next", so the next session picks up cleanly.

Nothing in a project leaves the house from here."""


def available() -> bool:
    from features import is_enabled
    return is_enabled(LEVER)


def focused_project(focus: Optional[str], data_dir=None) -> Optional[str]:
    """The slug of the project her focus names, if any."""
    key = (focus or "").lower()
    if not key:
        return None
    hit = next((p for p in W.list_projects(data_dir)
                if p["project"] in key or (p["name"] or "").lower() in key), None)
    return hit["project"] if hit else None


DAEDALUS_LINE = ("\n\nI can work with Daedalus inside a project (work_with_daedalus): he reads and changes its "
                 "files, and in software projects runs code in the same sandbox, but nothing outside it. He "
                 "leaves what he changed uncommitted, so I look it over and commit it myself.")


STUDIO_LINE = ("\n\nMy studio (studio) is here for music: I write a song as song.yaml in a project (studio help "
               "shows the format), render it to hear it, and each render is committed as a draft with my message "
               "about what I changed and why. My drafts are my record of how a song came to be.")


def project_block(focus: Optional[str], data_dir=None) -> str:
    """The project her focus names, opened in front of her (or her list, if none does)."""
    projects = W.list_projects(data_dir)
    if not projects:
        return "\n\nI don't have a project yet. project new starts one."
    key = (focus or "").lower()
    hit = next((p for p in projects if p["project"] in key or (p["name"] or "").lower() in key), None)
    if hit is None:
        lines = [f"- {p['project']} ({p['kind']}): last commit {p['last_commit']}, \"{p['last_message']}\""
                 for p in projects]
        return "\n\nMy projects:\n" + "\n".join(lines)
    st = W.status(hit["project"], data_dir)
    recent = "\n".join(f"- {c['at']} {c['message']}" for c in st["recent"])
    pending = (", ".join(st["uncommitted"][:12]) + ("..." if len(st["uncommitted"]) > 12 else "")
               if st["uncommitted"] else "nothing")
    return (f"\n\n## THIS PROJECT: {hit['name']} ({hit['kind']}, project {hit['project']})\n\n"
            f"{st['project_md']}\n\nUncommitted: {pending}\nRecent commits:\n{recent}")


async def run_workshop_turn(runner, *, duration_minutes: int = 30, max_turns: int = 24,
                            focus: Optional[str] = None, why: Optional[str] = None, **turn_kwargs):
    from agent_loop.session import run_session_turn
    try:
        opened = project_block(focus)
    except Exception as e:
        logger.warning(f"[workshop] couldn't open the project: {e}")
        opened = ""
    local = {"project": (W.PROJECT_TOOL, lambda a: W.handle(a))}
    extra = ""
    try:
        from daedalus_bridge import project_tools
        slug = focused_project(focus)
        daedalus = project_tools(TEMPLATE_ID + (f"-{slug}" if slug else ""), default_project=slug)
        if daedalus:
            local.update(daedalus)
            extra = DAEDALUS_LINE
    except Exception as e:
        logger.warning(f"[workshop] couldn't offer Daedalus: {e}")
    try:
        from studio import studio_tools
        st = studio_tools(default_project=focused_project(focus))
        if st:
            local.update(st)
            extra += STUDIO_LINE
    except Exception as e:
        logger.warning(f"[workshop] couldn't offer the studio: {e}")
    return await run_session_turn(
        runner, session_type=TEMPLATE_ID, additions=INSTRUCTIONS + extra + opened,
        local_tools=local,
        duration_minutes=duration_minutes, focus=focus, max_turns=max_turns,
        why=why or "I chose time in my workshop",
        initial_message="Time in my workshop.", **turn_kwargs)
