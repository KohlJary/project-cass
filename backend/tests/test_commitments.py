"""Her commitments (commitments.py): what she said she'd do, for whom, by when;
pressing ones come back to her; in chat and every session."""
import asyncio
from datetime import datetime

import commitments as C

NOW = datetime(2026, 11, 18, 9, 0)


def test_she_keeps_what_she_said_and_it_comes_back(tmp_path):
    a = C.add("Send Kohl the song notes", "Kohl", "tomorrow", data_dir=tmp_path, now=NOW)["commitment"]
    b = C.add("Read Ann's essay", "Ann", "2026-11-17", data_dir=tmp_path, now=NOW)["commitment"]
    C.add("Someday: a tide poem", data_dir=tmp_path, now=NOW)
    assert a["due"] == "2026-11-19T23:59" and b["due"] == "2026-11-17T23:59"
    states = {c["what"]: c["state"] for c in C.listing(tmp_path, NOW)}
    assert states == {"Read Ann's essay": "overdue", "Send Kohl the song notes": "due soon", "Someday: a tide poem": "open"}
    lines = C.lines(tmp_path, NOW)
    assert lines[0].startswith(f"- [{b['id']}] OVERDUE: Read Ann's essay for Ann") and len(lines) == 2
    assert "says why" in C.set_status(b["id"], "dropped", data_dir=tmp_path)["error"]
    assert C.set_status(b["id"], "dropped", "Told Ann I can't this week", tmp_path, NOW)["success"]
    assert C.set_status(a["id"], "done", data_dir=tmp_path, now=NOW)["commitment"]["status"] == "done"
    assert C.pressing(tmp_path, NOW) == []
    assert "isn't a date" in C.add("x", due="whenever", data_dir=tmp_path)["error"]
    assert C.add("x", due="in 3 days", data_dir=tmp_path, now=NOW)["commitment"]["due"] == "2026-11-21T23:59"


def test_it_is_in_chat_and_every_session():
    from agent_loop.spec import conversation_spec, session_spec
    from handlers.tool_router import TOOL_REGISTRY
    assert "commitment" in conversation_spec().tool_names()
    for kind in ("reflection", "workshop", "social", "day_planning"):
        assert "commitment" in session_spec(kind).tool_names(), kind
    assert TOOL_REGISTRY["commitment"] == "commitments"


def test_the_tool_answers(monkeypatch, tmp_path):
    monkeypatch.setattr(C, "_path", lambda data_dir=None: tmp_path / "c.json")
    out = asyncio.run(C.execute_commitment_tool("commitment", {"action": "add", "what": "Write back to Ann", "due": "today"}))
    assert out["success"] and out["result"]["commitment"]["what"] == "Write back to Ann"
    assert asyncio.run(C.execute_commitment_tool("commitment", {"action": "nope"}))["success"] is False


def test_the_recap_and_record_show_them(tmp_path):
    from types import SimpleNamespace
    import record as R
    from scheduling.day_recap import since_last_plan
    C.add("Send the song notes", "Kohl", "2026-11-17", data_dir=tmp_path, now=NOW)
    text = since_last_plan(SimpleNamespace(root=tmp_path), tmp_path, now=NOW, refused=lambda s: [], sent=lambda s: [])
    assert "What I've promised that's pressing:" in text and "OVERDUE: Send the song notes for Kohl" in text
    titles = [e["title"] for e in R.from_commitments(tmp_path)]
    assert "promised for Kohl: Send the song notes by 2026-11-17 23:59" in titles
    assert "commitment overdue: Send the song notes" in titles
