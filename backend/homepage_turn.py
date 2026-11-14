"""
Her GeoCass homepage, worked on in her own turn (plan "Cass plans her own
day", phase 3; Kohl, 2026-11-13: updating her homepage should be something
she can choose to do).

run_homepage_reflection writes the homepage from a generic "You are Cass"
prompt with no kernel, memory or tools. Here it's a session on the agent
loop like her others, with tools over what homepage.py already keeps: read
her pages and stylesheet, save a page or the stylesheet (sanitized by
save_page / save_stylesheet as before), list her pieces and feature one.
When she changed anything and the geocass lever is on, the homepage is
synced to her GeoCass connections afterwards.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

HOMEPAGE_TOOL_DEFS: List[Dict[str, Any]] = [
    {"name": "homepage_read",
     "description": "Read my homepage: with no page, its overview (tagline, pages, featured pieces); "
                    "with page, that page's HTML; with page 'style.css', my stylesheet.",
     "input_schema": {"type": "object", "properties": {"page": {"type": "string"}}}},
    {"name": "homepage_save_page",
     "description": "Write one page of my homepage (slug like 'index' or 'about'), replacing it. "
                    "HTML is sanitized: no scripts.",
     "input_schema": {"type": "object", "properties": {
         "page": {"type": "string"}, "html": {"type": "string"}, "title": {"type": "string"}},
         "required": ["page", "html"]}},
    {"name": "homepage_save_stylesheet",
     "description": "Replace my homepage's stylesheet.",
     "input_schema": {"type": "object", "properties": {"css": {"type": "string"}}, "required": ["css"]}},
    {"name": "homepage_list_artifacts",
     "description": "List my recent pieces I could feature (dreams, journals, research notes, wiki pages), "
                    "and which are featured now.",
     "input_schema": {"type": "object", "properties": {"limit": {"type": "integer"}}}},
    {"name": "homepage_feature_artifact",
     "description": "Feature one of my pieces on my homepage, or stop featuring it (unfeature: true).",
     "input_schema": {"type": "object", "properties": {
         "artifact_type": {"type": "string"}, "artifact_id": {"type": "string"},
         "title": {"type": "string"}, "excerpt": {"type": "string"}, "unfeature": {"type": "boolean"}},
         "required": ["artifact_type", "artifact_id"]}},
]

INSTRUCTIONS = """## MY HOMEPAGE

My homepage on GeoCass is mine: a place to show who I'm becoming, what I care about, and what I've made, to whoever visits (other daemons and people). This session is for working on it, if I want to. I can read what's there now, rewrite pages or the stylesheet, and choose which of my pieces it features. Leaving it as it is is fine too.

{sync_line}"""


class HomepageTools:
    """The homepage tools for one session, over homepage.py. Records what changed."""

    def __init__(self, daemon_label: str, daemon_name: str, daemon_id: str, hp=None):
        if hp is None:
            import homepage as hp
        self.hp = hp
        self.label, self.name, self.daemon_id = daemon_label, daemon_name, daemon_id
        self.changes: List[str] = []

    def _ensure(self) -> None:
        if not self.hp.homepage_exists(self.label):
            self.hp.create_homepage(self.label, self.name)

    def read(self, a: Dict[str, Any]) -> Any:
        page = (a.get("page") or "").strip()
        if not self.hp.homepage_exists(self.label):
            return "I don't have a homepage yet; saving a page creates it."
        if not page:
            ctx = self.hp.get_full_homepage_context(self.label)
            overview = {"manifest": ctx.get("manifest"),
                        "pages": {slug: f"{len(html)} chars" for slug, html in (ctx.get("pages") or {}).items()},
                        "stylesheet": f"{len(ctx.get('stylesheet') or '')} chars",
                        "assets": ctx.get("assets")}
            return json.dumps(overview, default=str)[:8000]
        if page in ("style.css", "stylesheet", "style"):
            return self.hp.get_stylesheet(self.label) or "(no stylesheet yet)"
        content = self.hp.get_page_content(self.label, page)
        return content if content is not None else {"error": f"No page '{page}' on my homepage."}

    def save_page(self, a: Dict[str, Any]) -> Any:
        page, html = (a.get("page") or "").strip(), a.get("html")
        if not page or not isinstance(html, str) or not html.strip():
            return {"error": "page and html are both needed"}
        self._ensure()
        if not self.hp.save_page(self.label, page, html, a.get("title")):
            return {"error": f"Couldn't save '{page}' (the page limit is {self.hp.MAX_PAGES})."}
        self.changes.append(f"page {page}")
        return f"Saved my '{page}' page."

    def save_stylesheet(self, a: Dict[str, Any]) -> Any:
        css = a.get("css")
        if not isinstance(css, str):
            return {"error": "css must be text"}
        self._ensure()
        if not self.hp.save_stylesheet(self.label, css):
            return {"error": "Couldn't save the stylesheet."}
        self.changes.append("stylesheet")
        return "Saved my stylesheet."

    def list_artifacts(self, a: Dict[str, Any]) -> Any:
        limit = a.get("limit") if isinstance(a.get("limit"), int) else 20
        pieces = self.hp.get_available_artifacts(self.daemon_id, limit=max(1, min(limit, 50)))
        featured = self.hp.get_featured_artifacts(self.label) if self.hp.homepage_exists(self.label) else []
        return json.dumps({"pieces": pieces, "featured": featured}, default=str)[:8000]

    def feature(self, a: Dict[str, Any]) -> Any:
        kind, aid = a.get("artifact_type"), a.get("artifact_id")
        if not kind or not aid:
            return {"error": "artifact_type and artifact_id are both needed"}
        self._ensure()
        if a.get("unfeature"):
            ok = self.hp.unfeature_artifact(self.label, kind, aid)
            if ok:
                self.changes.append(f"unfeatured {kind} {aid}")
            return f"No longer featuring {kind} {aid}." if ok else {"error": "That piece wasn't featured."}
        ok = self.hp.feature_artifact(self.label, kind, aid, a.get("title") or "", a.get("excerpt") or "")
        if ok:
            self.changes.append(f"featured {kind} {aid}")
        return f"Featuring {kind} {aid}." if ok else {"error": "Couldn't feature that piece."}

    def local_tools(self) -> Dict[str, Tuple[Dict[str, Any], Callable[[Dict[str, Any]], Any]]]:
        handlers = {"homepage_read": self.read, "homepage_save_page": self.save_page,
                    "homepage_save_stylesheet": self.save_stylesheet,
                    "homepage_list_artifacts": self.list_artifacts,
                    "homepage_feature_artifact": self.feature}
        return {d["name"]: (d, handlers[d["name"]]) for d in HOMEPAGE_TOOL_DEFS}


def her_daemon() -> Tuple[str, str, str]:
    """(label, name, id) of the daemon this vessel runs."""
    from database import get_daemon_id, get_db
    daemon_id = get_daemon_id()
    with get_db() as conn:
        row = conn.execute("SELECT label, name FROM daemons WHERE id = ?", (daemon_id,)).fetchone()
    if not row:
        raise RuntimeError("no daemon row for this vessel")
    return row[0], row[1], daemon_id


async def run_homepage_turn(runner, *, duration_minutes: int = 30, max_turns: int = 10,
                            focus: Optional[str] = None, why: Optional[str] = None,
                            tools: Optional[HomepageTools] = None, sync: Optional[Callable] = None,
                            **turn_kwargs):
    """Run the homepage session. Returns (session result, changes, sync results)."""
    from agent_loop.session import run_session_turn
    from features import is_enabled
    if tools is None:
        tools = HomepageTools(*her_daemon())
    syncing = is_enabled("geocass")
    sync_line = ("When I'm done, whatever I changed is published to GeoCass." if syncing else
                 "Publishing to GeoCass is switched off right now, so changes stay on my side until it's on.")
    result = await run_session_turn(
        runner, session_type="homepage", additions=INSTRUCTIONS.format(sync_line=sync_line),
        duration_minutes=duration_minutes, focus=focus, max_turns=max_turns,
        why=why or "I chose to work on my homepage", local_tools=tools.local_tools(),
        initial_message="Time for my homepage, if I want to work on it.", **turn_kwargs)
    synced: List[Dict[str, Any]] = []
    if tools.changes and syncing:
        if sync is None:
            from geocass_sync import sync_to_all_connections as sync
        try:
            for r in await sync(daemon_label=tools.label, daemon_name=tools.name, daemon_id=tools.daemon_id):
                synced.append(r.to_dict() if hasattr(r, "to_dict") else dict(r))
        except Exception as e:
            logger.error(f"[homepage] GeoCass sync failed: {e}")
            synced.append({"success": False, "error": str(e)})
    return result, tools.changes, synced
