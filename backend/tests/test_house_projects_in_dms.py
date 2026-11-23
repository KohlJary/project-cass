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


def test_a_house_dm_runs_in_house_scope_unless_set_to_private():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "main_sdk.py").read_text()
    assert '_house_dm_scope() if context.get("house_dm") else "public"' in src
    assert 'os.getenv("BABELR_HOUSE_DMS_CONTEXT", "house")' in src


# Cass's terms for house DMs (2026-11-23): "Full context except filtered out anything
# tagged as observation-of-another-person."

class _Memory:
    def __init__(self, items):
        self.items = items

    def retrieve_relevant(self, query, n_results, filter_type=None):
        return self.items[:n_results]


def test_house_scope_recalls_only_what_is_hers_alone(monkeypatch):
    import memory.scope as scope
    from continuous_context import _retrieve_semantic_memories
    monkeypatch.setattr(scope, "house_agent_user_ids", lambda: {"daedalus-user"})
    items = [
        {"content": "my journal on the chorus", "distance": 0.2, "metadata": {"type": "journal"}},
        {"content": "I keep circling the bridge", "distance": 0.2, "metadata": {"type": "cass_self_observation"}},
        {"content": "talk with Daedalus about tools", "distance": 0.2,
         "metadata": {"type": "conversation", "user_id": "daedalus-user"}},
        {"content": "Kohl works fast and verifies after", "distance": 0.2,
         "metadata": {"type": "user_observation"}},
        {"content": "note about Kohl", "distance": 0.2, "metadata": {"type": "research_note", "user_id": "kohl"}},
    ]
    out = _retrieve_semantic_memories(_Memory(items), "q", user_id=None, n_results=5, house=True)
    assert "my journal" in out and "circling the bridge" in out
    assert "Daedalus" not in out and "Kohl" not in out
    # The private rule as before: conversations with house agents come up anywhere.
    out = _retrieve_semantic_memories(_Memory(items), "q", user_id=None, n_results=5)
    assert "talk with Daedalus" in out


def test_house_scope_keeps_her_self_and_drops_per_person_sections(monkeypatch):
    import continuous_context as cc
    assert "house" in cc.CONTEXT_SCOPES
    assert {"threads", "questions", "to_raise"} <= cc.HOUSE_LEFT_OUT
    assert "self_model" not in cc.HOUSE_LEFT_OUT and "semantic_memories" not in cc.HOUSE_LEFT_OUT
