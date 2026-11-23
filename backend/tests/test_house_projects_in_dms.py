"""Projects between daemons (Kohl, 2026-11-23): `project` in public turns when the talk is
about project work, Kohl's linked projects kept out there, and the BABELR_HOUSE_DMS toggle."""
from agent_loop import conversation as conv


def _on(monkeypatch):
    import features
    real = features.is_enabled
    monkeypatch.setattr(features, "is_enabled", lambda n: True if n == "workshop" else real(n))


def test_a_public_turn_gets_project_only_when_its_about_project_work(monkeypatch):
    _on(monkeypatch)
    public = {"scope": "public"}
    assert conv.workshop_tools(public, "how's your day going?") == {}
    assert "project" in conv.workshop_tools(public, "can you share the substack-intro project with cass?")
    assert "project" in conv.workshop_tools(public, "commit what you have")
    # Private turns get it whatever was said.
    assert "project" in conv.workshop_tools({"scope": "private"}, "hi")


def test_kohls_projects_stay_out_of_public_turns(monkeypatch):
    import workshop as W
    seen = []
    monkeypatch.setattr(W, "handle", lambda a, d=None: seen.append(a) or
                        {"projects": [{"project": "kohl-robokohl"}, {"project": "substack-intro"}]})
    assert "error" in W.handle_public({"action": "read", "project": "kohl-robokohl", "path": "x"})
    assert "error" in W.handle_public({"action": "files", "project": "Kohl Robokohl"})
    assert seen == []
    got = W.handle_public({"action": "list"})
    assert [p["project"] for p in got["projects"]] == ["substack-intro"]
    W.handle_public({"action": "share", "project": "substack-intro", "with": "cass"})
    assert seen[-1]["action"] == "share"


def test_public_turns_use_the_guarded_handler(monkeypatch):
    _on(monkeypatch)
    import workshop as W
    monkeypatch.setattr(W, "handle_public", lambda a, d=None: "guarded")
    monkeypatch.setattr(W, "handle", lambda a, d=None: "open")
    _, run = conv.workshop_tools({"scope": "public"}, "share the project")["project"]
    assert run({}) == "guarded"
    _, run = conv.workshop_tools({"scope": "private"}, "")["project"]
    assert run({}) == "open"


def test_house_dms_are_named_in_config(monkeypatch):
    from babelr_organ.organ import house_dm_names
    monkeypatch.delenv("BABELR_HOUSE_DMS", raising=False)
    assert house_dm_names() == set()
    monkeypatch.setenv("BABELR_HOUSE_DMS", "Eris, @daedalus,,robokohl")
    assert house_dm_names() == {"eris", "daedalus", "robokohl"}


def test_a_house_dm_runs_private():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "main_sdk.py").read_text()
    assert 'context_scope="private" if (channel_user or context.get("house_dm")) else "public"' in src
