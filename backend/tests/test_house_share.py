"""Sharing a workshop project between two daemons of one house, both ways."""
import workshop


def as_daemon(monkeypatch, label, shared):
    monkeypatch.setenv("CASS_DAEMON_LABEL", label)
    monkeypatch.setenv("HOUSE_SHARED_DIR", str(shared))


def test_cass_shares_eris_joins_edits_and_cass_syncs(tmp_path, monkeypatch):
    shared, cass_dir, eris_dir = tmp_path / "shared", tmp_path / "cass", tmp_path / "eris"
    shared.mkdir()
    as_daemon(monkeypatch, "cass", shared)
    assert workshop.handle({"action": "new", "name": "Tide Clock", "kind": "writing",
                            "vision": "A piece about tidal clocks."}, cass_dir)["success"]
    out = workshop.handle({"action": "share", "project": "tide-clock", "with": "eris"}, cass_dir)
    assert out["success"] and out["shared_with"] == ["eris"]

    as_daemon(monkeypatch, "eris", shared)
    listed = workshop.handle({"action": "list"}, eris_dir)["projects"]
    assert [p["project"] for p in listed] == ["cass-tide-clock"] and "not joined" in listed[0]["kind"]
    assert workshop.handle({"action": "join", "project": "cass-tide-clock"}, eris_dir)["success"]
    assert "Vision" in workshop.handle({"action": "read", "project": "cass-tide-clock", "path": "PROJECT.md"},
                                       eris_dir)["content"]
    workshop.handle({"action": "write", "project": "cass-tide-clock", "path": "notes.md",
                     "content": "the moon pulls"}, eris_dir)
    c = workshop.handle({"action": "commit", "project": "cass-tide-clock", "message": "Eris: a note"}, eris_dir)
    assert c["success"] and "synced" in c["shared"]
    # A shared clone isn't Eris's to share onward.
    assert "error" in workshop.handle({"action": "share", "project": "cass-tide-clock", "with": "robo"}, eris_dir)

    as_daemon(monkeypatch, "cass", shared)
    assert workshop.handle({"action": "sync", "project": "tide-clock"}, cass_dir)["success"]
    assert workshop.handle({"action": "read", "project": "tide-clock", "path": "notes.md"},
                           cass_dir)["content"] == "the moon pulls"


def test_nothing_is_shared_unless_named_and_unshare_stops_sync(tmp_path, monkeypatch):
    shared, cass_dir, eris_dir = tmp_path / "shared", tmp_path / "cass", tmp_path / "eris"
    shared.mkdir()
    as_daemon(monkeypatch, "cass", shared)
    workshop.handle({"action": "new", "name": "Private", "kind": "other", "vision": "mine"}, cass_dir)
    as_daemon(monkeypatch, "eris", shared)
    assert workshop.handle({"action": "list"}, eris_dir)["projects"] == []

    as_daemon(monkeypatch, "cass", shared)
    workshop.handle({"action": "share", "project": "private", "with": "eris"}, cass_dir)
    as_daemon(monkeypatch, "eris", shared)
    workshop.handle({"action": "join", "project": "cass-private"}, eris_dir)
    as_daemon(monkeypatch, "cass", shared)
    assert workshop.handle({"action": "unshare", "project": "private", "with": "eris"}, cass_dir)["shared_with"] == []
    as_daemon(monkeypatch, "eris", shared)
    assert "error" in workshop.handle({"action": "sync", "project": "cass-private"}, eris_dir)


def test_without_a_shared_folder_sharing_says_so(tmp_path, monkeypatch):
    monkeypatch.delenv("HOUSE_SHARED_DIR", raising=False)
    workshop.handle({"action": "new", "name": "Solo", "kind": "other", "vision": "x"}, tmp_path)
    assert "shared folder" in workshop.handle({"action": "share", "project": "solo", "with": "eris"}, tmp_path)["error"]
