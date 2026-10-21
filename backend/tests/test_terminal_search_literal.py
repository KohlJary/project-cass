"""
Issue #43: terminal search compiled the user-supplied pattern as a regex
and ran it over up to 10k captured lines inside an async handler, so a
catastrophic-backtracking pattern could stall the event loop. Search is now
a literal substring match.
"""
import asyncio
import time
from types import SimpleNamespace

import pytest

# Importing the routes package needs the runtime deps (python-multipart);
# the fast CI job skips this file, the full job runs it.
pytest.importorskip("multipart")

from routes import terminal  # noqa: E402


@pytest.fixture
def fake_session(monkeypatch):
    def install(output):
        monkeypatch.setattr(terminal, "get_daedalus_sessions",
                            lambda: [SimpleNamespace(name="daedalus-x")])
        monkeypatch.setattr(terminal, "capture_tmux_pane", lambda name, lines: output)
    return install


def _search(pattern, **kw):
    kw.setdefault("lines", 500)
    kw.setdefault("case_sensitive", False)
    return asyncio.run(terminal.search_session_output("x", pattern=pattern, **kw))


def test_backtracking_pattern_returns_quickly(fake_session):
    fake_session("\n".join(["a" * 40 + "b"] * 50))
    start = time.monotonic()
    result = _search("(a+)+$")
    assert time.monotonic() - start < 1.0
    assert result.count == 0


def test_pattern_is_matched_literally(fake_session):
    fake_session("error: a.b failed\naxb ok\nsee (a+)+$ here")
    assert [r.index for r in _search("a.b").results] == [0]
    assert [r.index for r in _search("(a+)+$").results] == [2]


def test_case_sensitivity(fake_session):
    fake_session("Error here\nerror there")
    assert _search("error").count == 2
    assert [r.index for r in _search("error", case_sensitive=True).results] == [1]
