"""
Organ state: DATA_DIR/babelr/state.json.

Per place (a DM or a channel) the last message time seen and the ids seen
at or near it, so a poll never hands her the same message twice; the
vessel conversation each place is recorded in; the people she has seen
(username -> Babelr actor id, so her tools can name people); triggered
messages waiting out her quiet hours.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("babelr_organ.state")

SEEN_IDS_KEPT = 200
DEFERRED_KEPT = 50


class OrganState:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.data: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        try:
            self.data = json.loads(self.path.read_text())
            if not isinstance(self.data, dict):
                raise ValueError("not an object")
        except FileNotFoundError:
            self.data = {}
        except (OSError, ValueError) as e:
            logger.warning(f"[Babelr] {self.path} unreadable ({e}); starting fresh cursors")
            self.data = {}
        for key in ("places", "conversations", "people"):
            self.data.setdefault(key, {})
        self.data.setdefault("deferred", [])
        self.data.setdefault("requests_seen", [])

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".state.", suffix=".json")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(self.data, f, indent=2, sort_keys=True)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # -- cursors ----------------------------------------------------------

    def known_place(self, place: str) -> bool:
        return place in self.data["places"]

    def cursor(self, place: str) -> Optional[str]:
        return self.data["places"].get(place, {}).get("last_published")

    def is_new(self, place: str, message_id: str, published: str) -> bool:
        entry = self.data["places"].get(place)
        if not entry:
            return True
        if message_id in entry.get("seen", []):
            return False
        last = entry.get("last_published")
        return last is None or published >= last

    def mark_seen(self, place: str, message_id: str, published: str) -> None:
        entry = self.data["places"].setdefault(place, {"last_published": None, "seen": []})
        if entry["last_published"] is None or published > entry["last_published"]:
            entry["last_published"] = published
        seen: List[str] = entry.setdefault("seen", [])
        if message_id not in seen:
            seen.append(message_id)
            del seen[:-SEEN_IDS_KEPT]

    def baseline(self, place: str) -> None:
        """Mark a place as known with nothing seen yet (an empty DM or channel)."""
        self.data["places"].setdefault(place, {"last_published": None, "seen": []})

    # -- conversations and people ------------------------------------------

    def conversation_for(self, place: str) -> Optional[str]:
        return self.data["conversations"].get(place)

    def set_conversation(self, place: str, conversation_id: str) -> None:
        self.data["conversations"][place] = conversation_id

    def remember_person(self, author: Dict[str, Any]) -> None:
        username = (author or {}).get("preferredUsername")
        actor_id = (author or {}).get("id")
        if username and actor_id:
            self.data["people"][username.lower()] = actor_id

    def person_id(self, name_or_id: str) -> Optional[str]:
        key = name_or_id.lstrip("@").lower()
        if key in self.data["people"]:
            return self.data["people"][key]
        if name_or_id in self.data["people"].values():
            return name_or_id
        return None

    # -- quiet hours --------------------------------------------------------

    def defer(self, event: Dict[str, Any]) -> None:
        self.data["deferred"].append(event)
        del self.data["deferred"][:-DEFERRED_KEPT]

    def take_deferred(self) -> List[Dict[str, Any]]:
        out, self.data["deferred"] = self.data["deferred"], []
        return out
