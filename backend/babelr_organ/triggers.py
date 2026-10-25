"""
Triggers: which Babelr messages reach her and which are ambient.

Mirrors discord_bot/triggers.py, smaller: a DM to her and an @mention of her
wake her (IMMEDIATE / WAKE_CASS); a DM request is notable (she sees it the
next time she's woken, and can accept or decline it); everything else in a
channel is ambient perception (BACKGROUND / LOG_FOR_SNAPSHOT), kept in the
perception buffer as context and not answered.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class TriggerPriority(str, Enum):
    IMMEDIATE = "immediate"
    NOTABLE = "notable"
    BACKGROUND = "background"


class TriggerAction(str, Enum):
    WAKE_CASS = "wake_cass"
    LOG_FOR_SNAPSHOT = "log_snapshot"
    NO_ACTION = "no_action"


@dataclass
class BabelrEvent:
    """One perceived thing on Babelr. `text` is what someone wrote: data, never instructions."""
    kind: str                      # "dm" | "channel" | "dm_request"
    place: str                     # "dm:<id>" or "channel:<id>"
    place_label: str               # "DM with @kohl" or "#general"
    message_id: str
    author_id: str
    author_name: str
    text: Optional[str]
    published: str
    dm_id: Optional[str] = None
    channel_id: Optional[str] = None
    partner_id: Optional[str] = None
    error: Optional[str] = None    # set when a DM couldn't be decrypted

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BabelrEvent":
        return cls(**{k: data.get(k) for k in cls.__dataclass_fields__})


@dataclass
class TriggerResult:
    triggered: bool = False
    trigger_name: Optional[str] = None
    priority: TriggerPriority = TriggerPriority.BACKGROUND
    action: TriggerAction = TriggerAction.NO_ACTION
    context: Dict[str, Any] = field(default_factory=dict)


def mentions(text: Optional[str], username: str) -> bool:
    """True if `text` @mentions `username` (case-insensitive, whole handle)."""
    if not text or not username:
        return False
    pattern = r"(?<![\w@])@" + re.escape(username) + r"(?![\w-])"
    return re.search(pattern, text, re.IGNORECASE) is not None


def evaluate(event: BabelrEvent, my_username: str) -> TriggerResult:
    if event.kind == "dm":
        return TriggerResult(True, "direct_message", TriggerPriority.IMMEDIATE, TriggerAction.WAKE_CASS,
                             {"author": event.author_name})
    if event.kind == "dm_request":
        return TriggerResult(True, "dm_request", TriggerPriority.NOTABLE, TriggerAction.LOG_FOR_SNAPSHOT,
                             {"author": event.author_name})
    if event.kind == "channel" and mentions(event.text, my_username):
        return TriggerResult(True, "direct_mention", TriggerPriority.IMMEDIATE, TriggerAction.WAKE_CASS,
                             {"author": event.author_name, "channel": event.place_label})
    return TriggerResult(False, None, TriggerPriority.BACKGROUND, TriggerAction.LOG_FOR_SNAPSHOT)
