"""The weekly cognitive snapshot gets the week's conversations (it failed every week without them)."""
from dataclasses import dataclass, field
from typing import List

from journal_tasks import _conversations_between


@dataclass
class Msg:
    role: str
    content: str


@dataclass
class Conv:
    id: str
    user_id: str
    messages: List[Msg] = field(default_factory=list)


class Convs:
    def list_conversations(self, limit=500):
        return [{"id": "a", "updated_at": "2026-11-12T10:00:00"}, {"id": "b", "updated_at": "2026-11-18T00:01:00"},
                {"id": "c", "updated_at": "2026-11-01T10:00:00"}, {"id": "d", "updated_at": "2026-11-15T09:00:00"}]

    def load_conversation(self, cid):
        return Conv(cid, "kohl", [Msg("user", "hi")] if cid != "d" else [])


def test_the_weeks_conversations_in_the_shape_create_snapshot_reads():
    got = _conversations_between(Convs(), "2026-11-11", "2026-11-18")
    assert [c["id"] for c in got] == ["a", "b"]   # c is before the week; d is empty
    assert got[0] == {"id": "a", "messages": [{"role": "user", "content": "hi"}], "user_id": "kohl"}
    assert _conversations_between(None, "2026-11-11", "2026-11-18") == []
