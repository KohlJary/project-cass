"""
Her room in Chapter House: what she chose to share, read-only (plan "Cass's
room in Chapter House", phase 2, "Read-only feed from the vessel").

Her terms (2026-11-13, recorded on the plan's ask item): in the room go her
day plan, agenda, paintings, music, writing (selectively) and her GeoCass
page; journals too, but she chooses which entries surface. Kohl sees it
first, the whole house eventually. Sharing a piece is her deliberate choice
each time, never automatic.

So:
  - pieces (a painting, a composition, a piece of writing, a journal entry,
    a file from her workspace) appear only after she shares each one with
    share_to_room, and leave when she unshares it;
  - her day plan, agenda and homepage are "standing" sections, on because
    she named them, each one hers to switch off;
  - each share says who it's for: "kohl" (the default) or "house";
  - the feed is read by a token with an audience. A "kohl" token sees
    everything she shared; a "house" token only what she shared with the
    house. Tokens are minted with scripts/room_token.py and stored hashed.

State lives in DATA_DIR/room/ (shares.json, tokens.json), not in cass.db.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

KINDS = ("painting", "music", "writing", "journal", "workspace")
STANDING = ("day_plan", "agenda", "homepage")
AUDIENCES = ("kohl", "house")
# Her answer named these, so they start on; she can switch each off.
STANDING_DEFAULTS = {"day_plan": True, "agenda": True, "homepage": True}
MAX_TEXT = 200_000


def room_dir(data_dir: Optional[Path] = None) -> Path:
    if data_dir is None:
        from config import DATA_DIR
        data_dir = Path(DATA_DIR)
    return Path(data_dir) / "room"


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, indent=1), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


# ---------------------------------------------------------------------------
# What she shares
# ---------------------------------------------------------------------------

class Room:
    def __init__(self, data_dir: Optional[Path] = None, daemon_id: Optional[str] = None):
        self.dir = room_dir(data_dir)
        self.data_dir = self.dir.parent
        self._daemon_id = daemon_id

    @property
    def daemon_id(self) -> Optional[str]:
        if self._daemon_id is None:
            try:
                from database import get_daemon_id
                self._daemon_id = get_daemon_id()
            except Exception:
                return None
        return self._daemon_id

    # ----- state ----------------------------------------------------------

    def state(self) -> Dict[str, Any]:
        s = _read_json(self.dir / "shares.json", {})
        standing = dict(STANDING_DEFAULTS)
        standing.update({k: bool(v) for k, v in (s.get("standing") or {}).items() if k in STANDING})
        return {"standing": standing, "shares": list(s.get("shares") or [])}

    def _save(self, state: Dict[str, Any]) -> None:
        _write_json(self.dir / "shares.json", state)

    def share(self, kind: str, piece_id: str, note: str = "", audience: str = "kohl") -> Dict[str, Any]:
        if kind not in KINDS:
            return {"error": f"kind is one of: {', '.join(KINDS)}"}
        if audience not in AUDIENCES:
            return {"error": "audience is 'kohl' (Kohl only, for now) or 'house' (everyone in Chapter House)"}
        piece_id = str(piece_id or "").strip()
        meta = self.describe(kind, piece_id)
        if meta is None:
            return {"error": f"I can't find that {kind} ({piece_id!r})."}
        state = self.state()
        state["shares"] = [s for s in state["shares"] if not (s["kind"] == kind and s["id"] == piece_id)]
        state["shares"].append({"kind": kind, "id": piece_id, "note": (note or "").strip(),
                                "audience": audience, "title": meta.get("title"),
                                "shared_at": datetime.now().isoformat(timespec="seconds")})
        self._save(state)
        who = "Kohl" if audience == "kohl" else "the house"
        return {"shared": True, "message": f"Shared {meta.get('title') or kind} with {who}, in my room."}

    def unshare(self, kind: str, piece_id: str) -> Dict[str, Any]:
        state = self.state()
        before = len(state["shares"])
        state["shares"] = [s for s in state["shares"] if not (s["kind"] == kind and s["id"] == str(piece_id))]
        if len(state["shares"]) == before:
            return {"error": "That isn't in my room."}
        self._save(state)
        return {"unshared": True, "message": "Taken out of my room."}

    def set_standing(self, section: str, on: bool) -> Dict[str, Any]:
        if section not in STANDING:
            return {"error": f"section is one of: {', '.join(STANDING)}"}
        state = self.state()
        state["standing"][section] = bool(on)
        self._save(state)
        return {"message": f"My {section.replace('_', ' ')} is {'in' if on else 'out of'} my room."}

    # ----- the pieces -----------------------------------------------------

    def _db(self):
        from database import get_db
        return get_db()

    def describe(self, kind: str, piece_id: str) -> Optional[Dict[str, Any]]:
        """Metadata for one piece, or None if it doesn't exist (or isn't hers)."""
        if not piece_id:
            return None
        try:
            if kind == "painting":
                with self._db() as conn:
                    row = conn.execute(
                        "SELECT g.id, g.prompt, g.style, g.created_at, g.image_path, n.subject, n.why, "
                        "n.artist_note FROM generated_images g LEFT JOIN image_artist_notes n "
                        "ON n.image_id = g.id WHERE g.id = ? AND g.daemon_id = ?",
                        (piece_id, self.daemon_id)).fetchone()
                if not row:
                    return None
                return {"title": row[5] or row[1][:80], "style": row[2], "created_at": row[3],
                        "image_path": row[4], "subject": row[5], "why": row[6], "artist_note": row[7]}
            if kind == "music":
                from music.music_client import get_music_client
                c = get_music_client().library.get(piece_id)
                if not c or not c.audio_path:
                    return None
                return {"title": c.title or "Untitled", "created_at": c.created_at, "purpose": c.purpose,
                        "lyrics": c.lyrics, "audio_path": c.audio_path}
            if kind == "journal":
                with self._db() as conn:
                    row = conn.execute("SELECT date, journal_type, content FROM journals "
                                       "WHERE id = ? AND daemon_id = ?", (piece_id, self.daemon_id)).fetchone()
                if not row:
                    return None
                return {"title": f"Journal, {row[0]}", "date": row[0], "journal_type": row[1], "content": row[2]}
            if kind in ("writing", "workspace"):
                base = (self.data_dir / "creative_output") if kind == "writing" else (self.data_dir / "workspace")
                p = self._inside(base, piece_id)
                if p is None or not p.is_file():
                    return None
                text = p.read_text(encoding="utf-8", errors="replace")
                first = next((l.lstrip("# ").strip() for l in text.splitlines() if l.strip()), p.name)
                return {"title": first[:120] or p.name, "path": piece_id, "content": text[:MAX_TEXT]}
        except Exception as e:
            logger.warning(f"[room] couldn't read {kind} {piece_id}: {e}")
            return None
        return None

    @staticmethod
    def _inside(base: Path, rel: str) -> Optional[Path]:
        root = base.resolve()
        p = (root / rel).resolve()
        return p if root in p.parents else None

    # ----- for her tools --------------------------------------------------

    def summary_for_her(self) -> Dict[str, Any]:
        s = self.state()
        return {"standing": s["standing"], "shared": s["shares"],
                "who_sees_it": "Kohl sees everything here; the house sees only what I shared with 'house'."}

    # ----- the feed -------------------------------------------------------

    @staticmethod
    def _visible(share: Dict[str, Any], audience: str) -> bool:
        return audience == "kohl" or share.get("audience") == "house"

    def feed(self, audience: str) -> Dict[str, Any]:
        """The room's overview for a token's audience: standing sections on,
        and shared pieces' metadata (no file paths, no full text)."""
        s = self.state()
        pieces = []
        for share in s["shares"]:
            if not self._visible(share, audience):
                continue
            meta = self.describe(share["kind"], share["id"])
            if meta is None:
                continue  # the piece is gone
            pieces.append({"kind": share["kind"], "id": share["id"], "title": meta.get("title"),
                           "note": share.get("note") or "", "audience": share.get("audience"),
                           "shared_at": share.get("shared_at"),
                           "created_at": meta.get("created_at") or meta.get("date")})
        pieces.sort(key=lambda p: p.get("shared_at") or "", reverse=True)
        # Standing sections are Kohl's view for now: the house sees pieces she
        # shared with the house, until she says her plan and agenda are for them.
        standing = [k for k, on in s["standing"].items() if on] if audience == "kohl" else []
        return {"sections": standing, "pieces": pieces}

    def piece(self, kind: str, piece_id: str, audience: str) -> Optional[Dict[str, Any]]:
        share = next((x for x in self.state()["shares"]
                      if x["kind"] == kind and x["id"] == piece_id), None)
        if share is None or not self._visible(share, audience):
            return None
        meta = self.describe(kind, piece_id)
        if meta is None:
            return None
        out = {k: v for k, v in meta.items() if k not in ("image_path", "audio_path", "path")}
        out.update({"kind": kind, "id": piece_id, "note": share.get("note") or "",
                    "shared_at": share.get("shared_at")})
        if kind == "painting":
            out["image"] = f"/room/pieces/painting/{piece_id}/file"
        if kind == "music" and meta.get("audio_path"):
            out["audio"] = f"/room/pieces/music/{piece_id}/file"
        return out

    def piece_file(self, kind: str, piece_id: str, audience: str) -> Optional[Path]:
        if self.piece(kind, piece_id, audience) is None:
            return None
        meta = self.describe(kind, piece_id) or {}
        raw = meta.get("image_path") if kind == "painting" else meta.get("audio_path") if kind == "music" else None
        if not raw:
            return None
        p = Path(raw)
        if not p.is_absolute():
            p = self.data_dir / p
        return p if p.is_file() else None

    def section(self, name: str, audience: str) -> Optional[Dict[str, Any]]:
        if audience != "kohl" or not self.state()["standing"].get(name):
            return None
        if name in ("day_plan", "agenda"):
            fname = "DAY_PLAN.md" if name == "day_plan" else "AGENDA.md"
            p = self.data_dir / "workspace" / fname
            text = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None
            updated = datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds") if text else None
            return {"section": name, "text": text, "updated_at": updated}
        if name == "homepage":
            try:
                import homepage as hp
                from homepage_turn import her_daemon
                label = her_daemon()[0]
                manifest = hp.get_manifest(label) if hp.homepage_exists(label) else None
            except Exception as e:
                logger.warning(f"[room] homepage unavailable: {e}")
                return {"section": name, "exists": False}
            servers = []
            try:
                from geocass_sync import get_all_connections
                servers = [c.server_url for c in get_all_connections()]
            except Exception:
                pass
            return {"section": name, "exists": manifest is not None,
                    "tagline": getattr(manifest, "tagline", None),
                    "featured": getattr(manifest, "featured_artifacts", None) or [],
                    "label": label, "geocass_servers": servers}
        return None


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def mint_token(audience: str, name: str, data_dir: Optional[Path] = None) -> str:
    """Make a feed token for `audience`; stores only its hash. Returns the token."""
    if audience not in AUDIENCES:
        raise ValueError(f"audience is one of {AUDIENCES}")
    token = "room_" + secrets.token_urlsafe(32)
    path = room_dir(data_dir) / "tokens.json"
    tokens = _read_json(path, [])
    tokens.append({"hash": _hash(token), "audience": audience, "name": name,
                   "created_at": datetime.now().isoformat(timespec="seconds")})
    _write_json(path, tokens)
    return token


def audience_for(token: Optional[str], data_dir: Optional[Path] = None) -> Optional[str]:
    if not token:
        return None
    h = _hash(token)
    for t in _read_json(room_dir(data_dir) / "tokens.json", []):
        if secrets.compare_digest(t.get("hash", ""), h):
            return t.get("audience")
    return None
