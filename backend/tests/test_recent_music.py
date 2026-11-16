"""Her recent songs reach her creative context (return-paths map, item 13).

_get_recent_activity_context queried a music_compositions table that never
existed, so recent_music was always empty. Her songs live in the music
library's JSON index.
"""
from music import music_client as mc
from music.music_client import MusicComposition, MusicLibrary
from scheduler.actions.creative_handlers import _get_recent_activity_context


class _Client:
    def __init__(self, library):
        self.library = library


def test_recent_music_comes_from_her_library(tmp_path, monkeypatch):
    library = MusicLibrary(tmp_path)
    library.add(MusicComposition(id="m1", created_at="2026-11-15T21:00:00", prompt="p",
                                 lyrics=None, purpose="creative", audio_path=None,
                                 audio_url=None, status="completed", title="Low Tide"))
    monkeypatch.setattr(mc, "get_music_client", lambda: _Client(library))
    recent = _get_recent_activity_context("cass")["recent_music"]
    assert [m["title"] for m in recent] == ["Low Tide"]
    assert recent[0]["when"] == "2026-11-15T21:00:00"
