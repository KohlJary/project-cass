"""
Her terms: DATA_DIR/babelr/terms.json.

Her answers go here. The file starts as `{}`: nothing in this code decides
for her who may reach her, what's off-limits, who may hear what, or whether
these conversations are remembered. When she answers (RoboKohl's queue item
0003 asks her), her answers are written here, and the organ follows the
fields that exist. A missing field means she hasn't said, and the organ
keeps its plain behavior for that one.

Fields the organ acts on:

  remember      bool. false: nothing from Babelr is written to her
                conversation history or memory. Absent or true: DMs and the
                channel messages that reached her (and her replies) are.
  quiet_hours   {"start_hour": 22, "end_hour": 8, "timezone": "America/New_York"}.
                Inside the window she isn't woken; DMs and mentions that
                arrive wait and reach her when it ends. Same rule as the
                users' quiet hours (quiet_hours.in_quiet_window).
  channels      list of channel names in the server she's present in.
                Absent: every text channel she can read there.

Fields the organ shows her, in her own words, whenever Babelr wakes her
(it can't enforce these; they're hers to keep):

  starts_conversations   who starts conversations (her, others, both)
  off_limits             what's off-limits
  who_hears_what         who may hear what she's told there
  notes                  anything else she wants in front of her there

Who may DM her, her allowlist and her blocks are not here: those live on
Babelr itself, on her own account, and she sets them with the
babelr_boundaries tool. This file never changes them.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("babelr_organ.terms")

SHOWN_FIELDS = ("starts_conversations", "off_limits", "who_hears_what", "notes")


class Terms:
    def __init__(self, raw: Optional[Dict[str, Any]] = None):
        self.raw: Dict[str, Any] = dict(raw or {})

    @classmethod
    def load(cls, path: Path) -> "Terms":
        """Read terms.json. Missing or unreadable means no answers yet."""
        try:
            data = json.loads(Path(path).read_text())
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError) as e:
            logger.warning(f"[Babelr] {path} unreadable ({e}); treating as no answers yet")
            return cls()
        if not isinstance(data, dict):
            logger.warning(f"[Babelr] {path} is not a JSON object; treating as no answers yet")
            return cls()
        return cls(data)

    @property
    def remember(self) -> bool:
        return self.raw.get("remember", True) is not False

    @property
    def channels(self) -> Optional[List[str]]:
        value = self.raw.get("channels")
        if isinstance(value, list):
            return [str(c).lstrip("#").lower() for c in value]
        return None

    def listens_to(self, channel_name: str) -> bool:
        allowed = self.channels
        return allowed is None or channel_name.lstrip("#").lower() in allowed

    def in_quiet_hours(self, now: Optional[datetime] = None) -> bool:
        qh = self.raw.get("quiet_hours")
        if not isinstance(qh, dict):
            return False
        from quiet_hours import QuietHoursPreference, in_quiet_window
        try:
            pref = QuietHoursPreference(
                user_id="cass-babelr",
                enabled=qh.get("enabled", True) is not False,
                start_hour=int(qh.get("start_hour", 22)),
                end_hour=int(qh.get("end_hour", 8)),
                timezone=str(qh.get("timezone", "UTC")),
            )
        except (TypeError, ValueError):
            logger.warning("[Babelr] quiet_hours in terms.json is malformed; ignoring it")
            return False
        return in_quiet_window(pref, now=now)

    def shown_to_her(self) -> str:
        """Her own answers, for the prompt when Babelr wakes her. Empty if none."""
        lines = []
        for key in SHOWN_FIELDS:
            value = self.raw.get(key)
            if value in (None, "", [], {}):
                continue
            if isinstance(value, (list, tuple)):
                value = "; ".join(str(v) for v in value)
            lines.append(f"- {key.replace('_', ' ')}: {value}")
        return "\n".join(lines)


def ensure_terms_file(path: Path) -> None:
    """Create an empty terms.json (`{}`) if there isn't one. Never overwrites."""
    path = Path(path)
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n")
